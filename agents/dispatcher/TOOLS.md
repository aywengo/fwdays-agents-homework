# Tools reference
| Tool | What it returns |
| --- | --- |
| `solax-cloud__get_realtime_data` | status, pv strings, ac phases, energy.dailyYield_kWh/totalYield_kWh, meter1/meter2 today/total import & export (kWh), battery soc/soh/power/temperature/totalCharge/totalDischarge |
| `solax-cloud__estimate_grid_charge_need(soc_pct, pv_estimate_kwh, daily_consumption_kwh?, pv_start?, pv_end?)` | grid_charge_kwh, needed, max_charge_kw, usable_now_kwh, evening_from (end of the PV window, or 17:00), projected_usable_at_evening_kwh, evening_night_need_kwh, daytime_use_kwh, assumptions |
| `solax-cloud__build_tou_settings(charge_start?, charge_end?)` | apply_args (grid charge window up to target SOC) and baseline_args (self-use, no grid charging) — pass verbatim to the set tool |
| `solax-cloud__set_battery_self_use_mode` | only if enabled; overwrites min_soc, charge_upper_soc, charge_from_grid_enable and time periods (HH:MM). Always pass every key |
| `sessions_send(agentId, message, timeoutSeconds=150)` | ask `weather-cast` or `trader`; returns their reply in the same turn |
| `memory_search` / `memory_get` / `read` / `write` | your workspace and `memory/` (`energy-log.md`, `tou-proposal.md`) |
Power is W, energy kWh. Battery power: negative = discharging.
Trader's `plan_grid_charge` returns charge_start/charge_end (HH:MM), charge and
peak prices, spread, estimated saving and `recommended` with a reason.
