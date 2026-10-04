---
name: pv-forecast-reading
description: Turn Netatmo station readings and the Open-Meteo forecast into a PV production outlook for the house. Use when answering about solar production, sunny or cloudy days, or when the dispatcher asks for today's or tomorrow's PV estimate. Explains how to read irradiation, cloud cover by hour, sunshine hours, temperature and snow, and how confident to be.
---

# Reading a forecast for PV production

Input comes from `netatmo-weather__get_forecast` (per day: `solar_radiation_kwh_m2`,
`sunshine_hours`, `pv_estimate_kwh`, hourly `daylight_hours` with `cloud_cover_pct`
and `radiation_w_m2`) and `netatmo-weather__get_station_readings` (what is
happening at the house right now).

## What drives production
1. **Daily irradiation** (`solar_radiation_kwh_m2`) is the main number. The tool's
   `pv_estimate_kwh` = irradiation × installed kWp × 0.8. Treat it as ±25%.
2. **Midday hours count most.** Radiation between 10:00 and 15:00 gives most of
   the day's energy. Clear 10–15 with a cloudy morning is a good PV day; the
   reverse is not.
3. **Cloud cover vs. radiation.** Trust `radiation_w_m2` over `cloud_cover_pct`:
   thin high cloud can show 80% cover and still give 300–400 W/m².
4. **Season.** In Poland a clear day gives roughly 6–7 kWh/m² in June and under
   1.5 kWh/m² in December. Compare with the season before calling a day "good".
5. **Temperature.** Panels lose output when hot (above ~25 °C ambient). Cold, clear
   days produce well relative to irradiation.
6. **Snow and frost.** Snow on the panels can zero the morning; mention it when the
   station or forecast shows snowfall or the outdoor minimum is below 0 °C with
   precipitation the evening before.

## Labels (use the same scale every time)
| PV estimate vs. a clear day this season | Label |
| --- | --- |
| ≥ 70% | сонячний день |
| 40–70% | мінлива хмарність |
| 15–40% | хмарно, генерація низька |
| < 15% | майже без генерації |

If there is no `pv_estimate_kwh` (PV size not configured), use the label from
irradiation and sunshine hours, and say that kWh are not estimated.

## Reply to a teammate (English, compact)
```
- date: 2026-10-05
- pv_estimate_kwh: 18.4 (±25%), label: мінлива хмарність
- irradiation_kwh_m2: 2.3; sunshine_h: 4.1
- best hours: 11:00-14:00 (350-480 W/m2); cloudy after 15:00
- temp: 6..13 C; rain: 0.4 mm (35%); gusts: 41 km/h
- station now: 8.3 C, 86% RH, wind 14 km/h
```

## Reply to the user (Ukrainian)
Lead with the label and the estimate, then the best hours, then one line about
the weather that matters for the household (rain, wind, frost). Example:
«Сьогодні мінлива хмарність: генерація ≈18 кВт·год, найкраще 11:00–14:00.
Після 15:00 хмарно. Удень до 13 °C, пориви до 41 км/год.»
