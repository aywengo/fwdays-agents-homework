# home-mcp

MCP servers used by the agent team. All three run over stdio or authenticated
streamable HTTP (`MCP_TRANSPORT=http`, bearer token `MCP_AUTH_TOKEN`, health at `/healthz`).

| Command | Server | Tools | Used by |
| --- | --- | --- | --- |
| `solax-http-mcp` | Upstream [solax-cloud-mcp](https://github.com/mouldiwarp/solax-cloud-mcp) (pinned commit) + planning tools | `get_realtime_data`, `estimate_grid_charge_need`, `build_tou_settings`, `set_battery_self_use_mode` (only with `SOLAX_ALLOW_CONTROL=true`) | dispatcher |
| `netatmo-weather-mcp` | Netatmo station + Open-Meteo forecast | `get_station_readings`, `get_forecast` | weather-cast |
| `rce-prices-mcp` | godzinowe.pl RCE prices with disk cache | `get_prices`, `get_current_price`, `plan_grid_charge` | trader |

```bash
uv venv && uv pip install -e ".[solax,dev]"
pytest -q
MCP_TRANSPORT=stdio rce-prices-mcp      # stdio, e.g. for Claude Code or native OpenClaw
```

State (rotated Netatmo tokens, price cache) lives in `HOME_MCP_STATE_DIR`
(`/data` volume in Docker), never in the repository.
