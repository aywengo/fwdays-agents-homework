#!/usr/bin/env python3
"""Render the private OpenClaw config and seed agent workspaces.

    python3 scripts/render_config.py init     # create .env from .env.example with generated secrets
    python3 scripts/render_config.py render   # write .local/openclaw/openclaw.json + seed workspaces
    python3 scripts/render_config.py check    # render to stdout-free temp file and report what is enabled

Design:
- The tool/agent policy lives here (versioned, reviewable).
- Secrets never appear in the rendered file: tokens are OpenClaw env references
  (`${VAR}` or `{source: env, id: VAR}`) resolved inside the container.
- Private but non-secret IDs (Discord guild/user IDs, phone numbers) are written
  only to the ignored `.local/openclaw/openclaw.json`.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".local"
CONFIG_OUT = LOCAL / "openclaw" / "openclaw.json"
WORKSPACES = LOCAL / "workspaces"

# Container paths (see docker-compose.yml).
C_WORKSPACES = "/home/node/workspaces"
C_STATE = "/home/node/.openclaw"

AGENTS = {
    "dispatcher": {
        "name": "Solar Dispatcher", "emoji": "☀️", "env": "DISPATCHER",
        "theme": "Calm energy manager. Precise with numbers, careful with controls.",
        "mention": ["@Dispatcher\\b", "@SolarDispatcher\\b"],
        "own_mcp": "solax-cloud",
    },
    "weather-cast": {
        "name": "Weather Cast", "emoji": "🌦️", "env": "WEATHER",
        "theme": "Local meteorologist with a solar-production focus.",
        "mention": ["@WeatherCast\\b", "@Weather\\b"],
        "own_mcp": "netatmo-weather",
    },
    "trader": {
        "name": "Trader", "emoji": "💹", "env": "TRADER",
        "theme": "Prosumer energy-market analyst. Data first, no speculation.",
        "mention": ["@Trader\\b"],
        "own_mcp": "rce-prices",
    },
}
MCP_SERVERS = {
    "solax-cloud": "http://solax-mcp:8000/mcp",
    "netatmo-weather": "http://weather-mcp:8000/mcp",
    "rce-prices": "http://prices-mcp:8000/mcp",
}
# Files the repository owns; refreshed on every render.
MANAGED_FILES = ("AGENTS.md", "SOUL.md", "IDENTITY.md", "TOOLS.md")
# Files the agent owns after first seeding (persistent memory); never overwritten.
SEED_ONLY_FILES = ("USER.md", "MEMORY.md")
# Skills each agent may use (OpenClaw allowlist; a non-empty list is the final set).
# Sources: skills/vendor/* (pinned third-party, see skills/sources.json) and skills/local/*.
AGENT_SKILLS = {
    "dispatcher": ["no-ai-slop", "uk-writing-style", "energy-history-analysis", "memory-hygiene"],
    "weather-cast": ["no-ai-slop", "uk-writing-style", "pv-forecast-reading", "weather-alerts", "memory-hygiene"],
    "trader": ["no-ai-slop", "uk-writing-style", "net-billing-advice", "memory-hygiene"],
}
SKILL_ROOTS = (ROOT / "skills" / "vendor", ROOT / "skills" / "local")
MANAGED_SKILLS_MARKER = ".managed-by-render.json"
GENERATED_SECRETS = ("OPENCLAW_GATEWAY_TOKEN", "MCP_INTERNAL_TOKEN", "A2A_CLIENT_TOKEN", "GRAFANA_ADMIN_PASSWORD")


# ------------------------------------------------------------------------- .env handling
def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def init_env() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        lines = env_path.read_text().splitlines()
    else:
        lines = (ROOT / ".env.example").read_text().splitlines()
    out, filled = [], []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in GENERATED_SECRETS and not line.split("=", 1)[1].strip():
            line = f"{key}={secrets.token_urlsafe(32)}"
            filled.append(key)
        out.append(line)
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(out) + "\n")
    os.chmod(env_path, 0o600)
    print(f"{'Updated' if filled else 'Kept'} .env" + (f"; generated: {', '.join(filled)}" if filled else ""))
    print("Fill in provider/SolaX/Netatmo/Discord values privately in .env, then run: render")


def truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


# ------------------------------------------------------------------------- config builders
def tool_policy(env: dict[str, str]) -> dict:
    return {
        # Minimal base + explicit grants. MCP tools arrive through the bundle-mcp plugin.
        "profile": "minimal",
        "alsoAllow": [
            "read", "write", "group:memory", "bundle-mcp",
            "sessions_spawn", "sessions_yield", "sessions_send", "sessions_list",
            "sessions_history", "subagents",
        ],
        "deny": [
            "exec", "process", "code_execution", "edit", "apply_patch",
            "group:web", "group:ui", "group:nodes", "group:automation", "group:messaging",
            "group:media",
        ],
        "fs": {"workspaceOnly": True},
        "elevated": {"enabled": False},
        "sessions": {"visibility": "all"},
        # A2A inside the Gateway: only these three agents may talk to each other.
        "agentToAgent": {"enabled": True, "allow": list(AGENTS)},
        "codeMode": {"enabled": False},
        "toolSearch": False,
    }


def agent_entries(env: dict[str, str]) -> dict:
    entries = {}
    for agent_id, meta in AGENTS.items():
        foreign = [f"{name}__*" for name in MCP_SERVERS if name != meta["own_mcp"]]
        deny = list(foreign)
        if agent_id != "dispatcher":
            # Specialists answer; only the dispatcher orchestrates sub-agents.
            deny += ["sessions_spawn", "subagents"]
        entries[agent_id] = {
            "name": meta["name"],
            "workspace": f"{C_WORKSPACES}/{agent_id}",
            "agentDir": f"{C_STATE}/agents/{agent_id}/agent",
            "identity": {"name": meta["name"], "emoji": meta["emoji"], "theme": meta["theme"]},
            "groupChat": {"mentionPatterns": meta["mention"]},
            "skills": list(AGENT_SKILLS.get(agent_id, [])),
            "tools": {"deny": deny},
        }
    return entries


def mcp_block(env: dict[str, str]) -> dict:
    servers = {}
    for name, url in MCP_SERVERS.items():
        server = {
            "url": url,
            "transport": "streamable-http",
            "headers": {"Authorization": "Bearer ${MCP_INTERNAL_TOKEN}"},
            "requestTimeoutMs": 30000,
            "connectionTimeoutMs": 5000,
        }
        if name == "solax-cloud" and not truthy(env.get("SOLAX_ALLOW_CONTROL")):
            server["toolFilter"] = {"exclude": ["set_battery_self_use_mode"]}
        servers[name] = server
    return {"servers": servers, "sessionIdleTtlMs": 3600000}


def discord_block(env: dict[str, str]) -> tuple[dict | None, list]:
    guild, owner = env.get("DISCORD_GUILD_ID"), env.get("DISCORD_OWNER_USER_ID")
    team = env.get("DISCORD_TEAM_CHANNEL_ID")
    bots = {}
    for agent_id, meta in AGENTS.items():
        prefix = f"DISCORD_{meta['env']}"
        if env.get(f"{prefix}_BOT_TOKEN"):
            bots[agent_id] = {
                "token_env": f"{prefix}_BOT_TOKEN",
                "application": env.get(f"{prefix}_APPLICATION_ID"),
                "user": env.get(f"{prefix}_BOT_USER_ID"),
                "channel": env.get(f"{prefix}_CHANNEL_ID") or None,
            }
    if not bots:
        return None, []
    if "dispatcher" not in bots:
        raise SystemExit("Discord: the dispatcher bot (DISCORD_DISPATCHER_BOT_TOKEN) is required when any bot is configured")
    missing = [k for k in ("DISCORD_GUILD_ID", "DISCORD_OWNER_USER_ID", "DISCORD_TEAM_CHANNEL_ID") if not env.get(k)]
    missing += [f"DISCORD_{AGENTS[a]['env']}_{k}" for a, b in bots.items()
                for k, v in (("APPLICATION_ID", b["application"]), ("BOT_USER_ID", b["user"])) if not v]
    if missing:
        raise SystemExit("Discord is partly configured; missing: " + ", ".join(missing))

    aliases = {AGENTS[a]["mention"][0].lstrip("@").replace("\\b", ""): b["user"] for a, b in bots.items()}
    rooms = sorted({team, *(b["channel"] for b in bots.values() if b["channel"])}
                   | ({env["DISCORD_REPORT_CHANNEL_ID"]} if env.get("DISCORD_REPORT_CHANNEL_ID") else set()))
    accounts = {}
    for agent_id, bot in bots.items():
        accounts[agent_id] = {
            "enabled": True,
            "name": AGENTS[agent_id]["name"],
            "applicationId": bot["application"],
            "token": {"source": "env", "provider": "default", "id": bot["token_env"]},
            "dmPolicy": "allowlist", "allowFrom": [owner],
            "groupPolicy": "allowlist", "allowBots": "mentions",
            "joinIntro": False, "replyToMode": "off", "streaming": {"mode": "off"},
            "mentionAliases": dict(aliases),
            "botLoopProtection": {"enabled": True, "maxEventsPerWindow": 8,
                                  "windowSeconds": 60, "cooldownSeconds": 120},
            "guilds": {guild: {
                "users": [owner, *(b["user"] for b in bots.values())],
                "requireMention": True, "ignoreOtherMentions": True,
                "channels": {room: {
                    "enabled": True,
                    # Each bot answers unmentioned messages only in its own room.
                    "requireMention": room != bot["channel"],
                    "ignoreOtherMentions": True,
                } for room in rooms},
            }},
        }
    block = {"enabled": True, "defaultAccount": "dispatcher", "dmPolicy": "allowlist",
             "allowFrom": [owner], "groupPolicy": "allowlist", "allowBots": "mentions",
             "joinIntro": False, "accounts": accounts}
    bindings = [{"agentId": a, "match": {"channel": "discord", "accountId": a}} for a in bots]
    return block, bindings


def whatsapp_block(env: dict[str, str]) -> tuple[dict | None, list]:
    if not truthy(env.get("WHATSAPP_ENABLED")):
        return None, []
    allow = [n.strip() for n in env.get("WHATSAPP_ALLOW_FROM", "").split(",") if n.strip()]
    if not allow:
        raise SystemExit("WHATSAPP_ENABLED=true requires WHATSAPP_ALLOW_FROM (E.164 numbers, comma-separated)")
    block = {"dmPolicy": "allowlist", "allowFrom": allow, "groupPolicy": "disabled"}
    # WhatsApp is a single identity: everything goes to the dispatcher, which delegates.
    return block, [{"agentId": "dispatcher", "match": {"channel": "whatsapp", "accountId": "*"}}]


def build_config(env: dict[str, str]) -> dict:
    model = env.get("OPENCLAW_MODEL") or "anthropic/claude-sonnet-5"
    tz = env.get("HOME_TZ") or "Europe/Warsaw"
    channels: dict = {
        "a2a": {
            "enabled": True,
            "exposeAgents": list(AGENTS),
            "replyTimeoutMs": 180000,
            "rateLimitPerMinute": 30,
            "peers": {"homework-client": {"token": "${A2A_CLIENT_TOKEN}"}},
        }
    }
    bindings = [{"agentId": "dispatcher", "match": {"channel": "a2a", "accountId": "*"}}]
    discord, discord_bindings = discord_block(env)
    if discord:
        channels["discord"] = discord
        bindings += discord_bindings
    whatsapp, wa_bindings = whatsapp_block(env)
    if whatsapp:
        channels["whatsapp"] = whatsapp
        bindings += wa_bindings
    owners = [f"discord:{env['DISCORD_OWNER_USER_ID']}"] if discord else []
    owners += [f"whatsapp:{n}" for n in (whatsapp or {}).get("allowFrom", [])]

    config = {
        "gateway": {
            "mode": "local",
            "bind": "lan",  # container-internal; the host port is published on 127.0.0.1 only
            "port": 18789,
            "auth": {"mode": "token", "allowTailscale": False,
                     "token": {"source": "env", "provider": "default", "id": "OPENCLAW_GATEWAY_TOKEN"}},
            "tailscale": {"mode": "off"},
            "terminal": {"enabled": False},
            "cliAgents": {"enabled": False},
            "controlUi": {"allowedOrigins": ["http://127.0.0.1:18789", "http://localhost:18789"]},
        },
        "agents": {
            "defaults": {
                "model": {"primary": model},
                "skipBootstrap": True,
                "skills": [],
                "heartbeat": {"every": "0m"},
                "userTimezone": tz,
                "workspace": f"{C_WORKSPACES}/dispatcher",
                "systemAgent": {"agentId": "dispatcher"},
                "subagents": {
                    "allowAgents": ["weather-cast", "trader"],
                    "requireAgentId": True,
                    "maxSpawnDepth": 1,
                    "maxChildrenPerAgent": 2,
                    "maxConcurrent": 3,
                    "runTimeoutSeconds": 300,
                },
            },
            "ownership": "explicit",
            "entries": agent_entries(env),
        },
        "bindings": bindings,
        "session": {"dmScope": "per-channel-peer"},
        "tools": tool_policy(env),
        "mcp": mcp_block(env),
        "channels": channels,
        "commands": {"ownerAllowFrom": owners} if owners else {},
        "browser": {"enabled": False},
        "cron": {"enabled": True},
        "hooks": {"enabled": False},
        "discovery": {"mdns": {"mode": "off"}},
        "diagnostics": {
            "enabled": True,
            "otel": {
                "enabled": True,
                "endpoint": env.get("OTEL_ENDPOINT") or "http://lgtm:4318",
                "protocol": "http/protobuf",
                "serviceName": "home-energy-agents",
                "traces": True, "metrics": True, "logs": True,
                "sampleRate": 1.0,
                "flushIntervalMs": 15000,
                # Tool/model content stays out of telemetry unless explicitly enabled.
                "captureContent": truthy(env.get("OTEL_CAPTURE_CONTENT")),
            },
        },
        "plugins": {"entries": {
            "memory-core": {"enabled": True, "config": {"dreaming": {"enabled": False}}},
            "a2a": {"enabled": True},
            "diagnostics-otel": {"enabled": True},
            **({"discord": {"enabled": True}} if discord else {}),
            **({"whatsapp": {"enabled": True}} if whatsapp else {}),
        }},
        "telemetry": {"enabled": False},
    }
    if not config["commands"]:
        del config["commands"]
    return config


# ------------------------------------------------------------------------- workspaces
def skill_dirs() -> dict[str, Path]:
    """Skill name -> directory, from the vendored and local roots (name = directory)."""
    found: dict[str, Path] = {}
    for root in SKILL_ROOTS:
        for skill_md in sorted(root.glob("*/SKILL.md")):
            name = skill_md.parent.name
            if name in found:
                raise SystemExit(f"Duplicate skill {name!r}: {found[name]} and {skill_md.parent}")
            found[name] = skill_md.parent
    return found


def install_skills(agent_id: str, workspace: Path) -> None:
    """Copy the agent's allowlisted skills into <workspace>/skills (OpenClaw's
    highest-precedence skill root, readable with the workspace-only `read` tool).
    Only skills previously installed by this script are removed or replaced."""
    available = skill_dirs()
    wanted = AGENT_SKILLS.get(agent_id, [])
    missing = [name for name in wanted if name not in available]
    if missing:
        raise SystemExit(f"{agent_id}: unknown skills {missing}; run scripts/sync_skills.py sync")
    target = workspace / "skills"
    target.mkdir(parents=True, exist_ok=True)
    marker = target / MANAGED_SKILLS_MARKER
    previous = json.loads(marker.read_text()) if marker.exists() else []
    for name in previous:
        shutil.rmtree(target / name, ignore_errors=True)
    for name in wanted:
        if (target / name).exists():
            raise SystemExit(f"{target / name} exists but was not installed by render; "
                             "remove it or give your own skill another name")
        shutil.copytree(available[name], target / name)
    marker.write_text(json.dumps(wanted) + "\n")


def seed_workspaces() -> None:
    for agent_id in AGENTS:
        src, dst = ROOT / "agents" / agent_id, WORKSPACES / agent_id
        (dst / "memory").mkdir(parents=True, exist_ok=True)
        for name in MANAGED_FILES:
            if (src / name).exists():
                shutil.copyfile(src / name, dst / name)
        for name in SEED_ONLY_FILES:
            if (src / name).exists() and not (dst / name).exists():
                shutil.copyfile(src / name, dst / name)
        install_skills(agent_id, dst)


def write_config(config: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def describe(config: dict) -> str:
    ch = config["channels"]
    skills = "; ".join(f"{a}:{'+'.join(s['skills'])}" for a, s in config["agents"]["entries"].items())
    return (f"model={config['agents']['defaults']['model']['primary']} "
            f"agents={','.join(config['agents']['entries'])} "
            f"channels={','.join(ch)} "
            f"skills=[{skills}] "
            f"solax_control={'on' if 'toolFilter' not in config['mcp']['servers']['solax-cloud'] else 'off'}")


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "render"
    if cmd == "init":
        init_env()
        return 0
    env = {**read_env(ROOT / ".env")}
    if cmd == "render":
        config = build_config(env)
        write_config(config, CONFIG_OUT)
        seed_workspaces()
        print(f"Wrote {CONFIG_OUT.relative_to(ROOT)} ({describe(config)})")
        return 0
    if cmd == "check":
        print(describe(build_config(env)))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
