---
name: weather-alerts
description: Decide whether current station readings or the forecast warrant a weather alert for the house, at which level, and how to word it. Use for every forecast brief and answer, when the dispatcher asks for alerts for a report, and when the user asks "чи буде буря/мороз/злива". Covers wind, frost, heat, heavy rain, snow on panels and station hardware problems, with de-duplication via memory.
---

# Weather alerts for the house

Inputs: `netatmo-weather__get_station_readings` (now) and
`netatmo-weather__get_forecast` (today, tomorrow). Thresholds below use the
**forecast** for the coming hours and the **station** for what is happening now.
If a value is missing (module offline), evaluate the rest and mention the gap.

## Levels
| Level | Ukrainian label | Meaning |
| --- | --- | --- |
| 1 | ℹ️ До відома | Worth knowing, no action needed |
| 2 | ⚠️ Увага | Prepare: secure things, adjust plans |
| 3 | 🚨 Небезпека | Act now: risk of damage or injury |

## Thresholds
| Hazard | Level 2 (Увага) | Level 3 (Небезпека) | Practical action to mention |
| --- | --- | --- | --- |
| Wind gusts | forecast `gust_max_kmh` ≥ 60, or station `gust_kmh` ≥ 50 now | ≥ 80 forecast, or ≥ 70 now | fold awnings and umbrellas, secure garden furniture, trampoline |
| Frost | `temp_min_c` ≤ 0 °C | `temp_min_c` ≤ −8 °C | garden taps and hoses, plants; ice on paths in the morning |
| Heat | `temp_max_c` ≥ 30 °C | `temp_max_c` ≥ 35 °C | PV output drops in heat; ventilate the battery/inverter room |
| Heavy rain | `precipitation_mm` ≥ 10 per day | ≥ 25 per day, or station `rain_last_hour_mm` ≥ 10 | gutters and drains; skip garden watering |
| Snow on panels | precipitation with `temp_max_c` ≤ 1 °C | — | PV near zero until panels clear; do not count on PV in charge plans |
| Station hardware | a module with `reachable: false` (module `battery_pct` < 20 is level 1) | — | check the module / replace its batteries |

Rules:
- Only alert on what the data shows. No thunderstorm or hail alerts: the forecast
  feed has no such fields. Never invent a source («за даними ІМГВ»).
- Probability matters: for rain use `precipitation_probability_max_pct`; below 40%
  downgrade by one level and say «можливо».
- Combine hazards of the same day into one message, highest level first.

## De-duplication (memory)
Keep `memory/alerts.md` with one row per alert:
`| date | hazard | level | issued_at | summary |`
- Before alerting, read today's rows. Do not repeat the same hazard and level on
  the same day. Re-alert if the level rises, and say «посилення».
- When a level-2/3 hazard is over (next readings below threshold), you may add one
  short «відбій» line in the next answer; record it as level 0.

## Output
For teammates (English, compact), add to every brief the summary plus ready-to-send
Ukrainian lines (the dispatcher copies them into reports unchanged):
```
- alerts: [wind L2 gusts 65 km/h 14:00-18:00; frost L1 min -1 C night]   # or: alerts: none
- alerts_uk:
  ⚠️ Увага: пориви до 65 км/год сьогодні 14:00–18:00. Складіть маркізу й закріпіть садові меблі.
  ℹ️ До відома: вночі до −1 °C, можлива ожеледь на доріжках зранку.
```
For the user directly (Ukrainian), the same lines: level label first, then time
window, value and action.
No alerts: say nothing about alerts in user answers (do not write «попереджень немає»
unless the user asked).
