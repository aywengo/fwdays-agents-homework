---
name: weather-alerts
description: Decide whether current station readings or the forecast warrant a weather alert for the house, at which level, and how to word it. Use for every forecast brief and answer, for the scheduled WEATHER_ALERT_CHECK runs, when the dispatcher asks for alerts for a report, and when the user asks "чи буде буря/мороз/злива". Covers wind, frost, heat, heavy rain, thunderstorms and hail, freezing rain, high UV, snow on panels and station hardware problems, with per-channel de-duplication via memory.
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
| Thunderstorm | a `daylight_hours` slot or the day with `condition` thunderstorm (code 95) | with hail (codes 96, 99) | unplug sensitive electronics, stay off the roof and away from the garden; hail can damage cars and panels |
| Freezing rain / drizzle | `condition` freezing rain or freezing drizzle (codes 56, 57, 66, 67) | — | ice on paths, steps and the car; take care on the roads |
| UV | `uv_index_max` 8–10 (дуже високий) | ≥ 11 (екстремальний) | shade at midday, SPF 30+, hat; children and pets out of the sun in `uv_windows_3plus` |
| Snow on panels | `condition` snow / snow showers, or precipitation with `temp_max_c` ≤ 1 °C | — | PV near zero until panels clear; do not count on PV in charge plans |
| Station hardware | a module with `reachable: false` (module `battery_pct` < 20 is level 1) | — | check the module / replace its batteries |

Rules:
- Only alert on what the data shows. Thunderstorms, hail and freezing rain come
  from the forecast `condition` (WMO weather code); give the hours from the
  matching `daylight_hours` slots when they are there. Never invent a source
  («за даними ІМГВ»).
- UV 3–7 (помірний, високий) is not an alert: `pv-forecast-reading` covers it in
  normal answers. In autumn and winter the UV index in Poland stays low.
- Time windows: use the forecast's own hours (`rain_windows`, `uv_windows_3plus`,
  slot times) and the day's `sunrise`/`sunset`, never fixed hours.
- Probability matters: for rain use `precipitation_probability_max_pct`; below 40%
  downgrade by one level and say «можливо».
- Combine hazards of the same day into one message, highest level first.

## De-duplication (memory)
Keep `memory/alerts.md` with one row per alert and delivery channel:
`| date | channel | hazard | level | issued_at | summary |`
(`channel` is `discord`, `whatsapp`, or `chat` for answers in a conversation).
- Before alerting, read today's rows **for the same channel**. Do not repeat the
  same hazard and level there on the same day. Re-alert if the level rises, and say
  «посилення».
- When a level-2/3 hazard is over (next readings below threshold), you may add one
  short «відбій» line in the next answer; record it as level 0.

## Scheduled check (prompt contains `WEATHER_ALERT_CHECK (channel: X)`)
Runs every few hours, unattended; the reply is delivered to channel X as-is.
1. `get_station_readings` and `get_forecast(days=2)`; look at the next 12 hours.
2. Evaluate the thresholds. Proactive messages are only for **level 2 and 3**;
   level-1 items wait for the regular reports.
3. Drop hazards already sent to channel X today at the same or a higher level.
4. Nothing left → reply exactly `NO_REPLY` (nothing else, no explanation). OpenClaw
   then delivers nothing.
5. Otherwise append the rows to `memory/alerts.md` (channel X) and reply with the
   Ukrainian alert lines only, highest level first. Add «посилення» for escalations.
6. If a tool fails, reply `NO_REPLY`. The run history records the error and the
   next check retries; never send a message about the failure itself.

## Output
For teammates (English, compact), add to every brief the summary plus ready-to-send
Ukrainian lines (the dispatcher copies them into reports unchanged). Briefs always
list all current alerts of every level and are not recorded in `memory/alerts.md`:
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
