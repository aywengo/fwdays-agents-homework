# Setup

Requirements: Docker with Compose v2, Python 3.11+ on the host (for the helper
scripts), a model provider account (Anthropic by default), SolaX Developer
Platform app, Netatmo app. Discord and WhatsApp are optional.

## 1. Secrets and config

```bash
python3 scripts/render_config.py init     # creates .env (0600) with generated internal tokens
$EDITOR .env                              # fill SolaX, Netatmo, model, Discord/WhatsApp values
python3 scripts/netatmo_auth.py           # one-time browser consent -> NETATMO_REFRESH_TOKEN
python3 scripts/render_config.py render   # -> .local/openclaw/openclaw.json + .local/workspaces/*
```

`render` is safe to re-run after every `.env` or `agents/*.md` change; it keeps
agent memory. Set `HOST_UID`/`HOST_GID` to `id -u`/`id -g` on Linux.
Every variable is described in [configuration.md](configuration.md).

## 2. Start

```bash
docker compose up -d --build
docker compose logs -f openclaw-init   # installs discord/whatsapp/diagnostics-otel plugins (pinned)
scripts/smoke_test.sh                  # health, A2A auth, config, MCP probe, Grafana
```

If you did not set an API key, log in to the model provider once:

```bash
docker compose exec openclaw openclaw models auth login --provider anthropic
```

Control UI: http://127.0.0.1:18789 (gateway token from `.env`). Grafana:
http://127.0.0.1:3000 (`admin` / `GRAFANA_ADMIN_PASSWORD`).

## 3. Channels

### Discord (one bot per agent)
1. Create three applications in the Discord Developer Portal (Dispatcher,
   WeatherCast, Trader), enable the **Message Content** intent, invite each bot to
   your server with Send Messages / Read Message History.
2. Enable Developer Mode, copy the server ID, your user ID, a team channel ID and
   a reports channel ID (can be the same), each bot's application ID and bot user ID.
3. Put tokens and IDs in `.env` (`DISCORD_*`). Only the dispatcher bot is required;
   bots without a token are skipped.
4. `python3 scripts/render_config.py render && docker compose up -d openclaw`.
5. DM a bot or @mention it in the team channel. Each bot answers without a mention
   in its own optional room (`DISCORD_<ROLE>_CHANNEL_ID`).

### WhatsApp (dispatcher)
1. Set `WHATSAPP_ENABLED=true`, `WHATSAPP_ALLOW_FROM=+48…` (and
   `WHATSAPP_REPORT_TO` for reports), then render and restart.
2. Link the account by QR (a dedicated number is recommended):
   `docker compose exec -it openclaw openclaw channels login --channel whatsapp`

## 4. Scheduled reports

```bash
scripts/setup_automations.sh          # creates morning + evening jobs per report channel
scripts/setup_automations.sh --list
docker compose exec openclaw openclaw automations run <job-id>   # test now
```

The first morning report has no previous evening snapshot; overnight figures
appear from the second day.

## 5. A2A from outside

```bash
python3 scripts/a2a_client.py card
python3 scripts/a2a_client.py send "Який зараз заряд батареї і чи варто ввечері економити?"
```

## Native (without Docker)

The MCP servers also run over stdio (`MCP_TRANSPORT=stdio rce-prices-mcp`). If
you run them over HTTP on the same host, use `http://127.0.0.1:<port>/mcp` or a
`*.localhost` name in `mcp.servers`: OpenClaw's SSRF guard trusts the exact
configured origin, but blocks a custom hostname that resolves to loopback.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `openclaw mcp probe` fails | `docker compose ps` health of `*-mcp`; same `MCP_INTERNAL_TOKEN` in both places (re-render + restart) |
| `mcp doctor` warns about a literal Authorization header | Expected: headers are strings; the value is `${MCP_INTERNAL_TOKEN}`, resolved from the container env |
| Netatmo `token refresh failed` | Re-run `scripts/netatmo_auth.py`, then `docker compose rm -sf weather-mcp && docker volume rm <project>_weather-state && docker compose up -d weather-mcp` |
| Prices `rate limit` | Wait a few minutes; cached days are still served |
| Report not delivered | `openclaw automations runs <job-id>`; Discord bot must see the reports channel |
