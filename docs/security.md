# Security and secrets

- All credentials live in `.env` (mode 0600, git-ignored). `render_config.py`
  writes only environment references (`${VAR}` / `{source: env}`) into the
  OpenClaw config; private IDs (Discord, phone numbers) go to the ignored `.local/`.
- Each container receives only the variables it needs (see `docker-compose.yml`):
  SolaX credentials only reach `solax-mcp`, Netatmo only `weather-mcp`.
- Rotated Netatmo tokens and the price cache live in Docker volumes, not in the repo.
- Gateway (18789) and Grafana (3000) bind to `127.0.0.1`. MCP servers have no
  host ports and require a bearer token. Use Tailscale or SSH tunnels for remote access.
- Discord and WhatsApp use allowlists: only the owner (and the team bots, for
  handoffs) can talk to the agents; bot loop protection is on.
- A2A peers authenticate with their own bearer token; slash commands from A2A
  are rejected by OpenClaw; A2A tasks run with the dispatcher's normal tool policy.
- Battery control is off by default, requires explicit user confirmation in chat,
  is never available to scheduled jobs, and is marked destructive.
- Run `python3 scripts/check_secrets.py` before committing.
