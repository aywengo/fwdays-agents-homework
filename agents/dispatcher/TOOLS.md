# Tools reference
| Tool | What it returns |
| --- | --- |
| `solax-cloud__get_realtime_data` | status, pv strings, ac phases, energy.dailyYield_kWh/totalYield_kWh, meter1/meter2 today/total import & export (kWh), battery soc/soh/power/temperature/totalCharge/totalDischarge |
| `solax-cloud__set_battery_self_use_mode` | only if enabled; min_soc, charge_upper_soc, charge_from_grid_enable, up to two charge/discharge time periods (HH:MM) |
| `sessions_spawn` / `sessions_yield` | delegate to `weather-cast` or `trader` (agentId required) |
| `memory_search` / `memory_get` / `read` / `write` | your workspace and `memory/` |
Power is W, energy kWh. Battery power: negative = discharging.
