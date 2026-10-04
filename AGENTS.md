# Instructions for coding agents (Claude Code, Codex)

This repo runs a three-agent OpenClaw team for home energy (see README.md,
docs/architecture.md). When helping the operator set it up or change it:

- Never print, paste or commit values from `.env`. Ask the operator to type
  secrets into `.env` themselves. Run `python3 scripts/check_secrets.py` before commits.
- The OpenClaw config is **generated**: edit policy in `scripts/render_config.py`
  and agent behaviour in `agents/<id>/*.md`, then `python3 scripts/render_config.py render`.
  Do not hand-edit `.local/openclaw/openclaw.json` except for experiments.
- Re-rendering refreshes `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `TOOLS.md` in
  `.local/workspaces/*` and never touches `MEMORY.md`, `USER.md`, `memory/`.
- Keep OpenClaw and its plugins on the same pinned version (2026.9.6 by default:
  `OPENCLAW_IMAGE_TAG`, `scripts/install_plugins.sh`).
- MCP servers: `cd mcp-servers && uv venv && uv pip install -e ".[solax,dev]" && pytest -q`.
  Keep `mcp<2` (FastMCP API; the upstream SolaX server depends on it).
- Battery control (`set_battery_self_use_mode`) stays disabled unless the
  operator explicitly sets `SOLAX_ALLOW_CONTROL=true`.
- Verify with `scripts/smoke_test.sh` and `docker compose exec openclaw openclaw mcp probe`.
