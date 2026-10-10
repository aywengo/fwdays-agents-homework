---
name: pv-forecast-reading
description: Turn Netatmo station readings and the Open-Meteo forecast into a PV production and weather outlook for the house. Use when answering about solar production, sunny or cloudy days, daylight, rain, UV, or when the dispatcher asks for today's or tomorrow's PV estimate. Explains how to read the day's daylight window, weather condition, irradiation, cloud cover, rain windows and UV index, how to treat the rest of today versus the whole day, and how confident to be.
---

# Reading a forecast for PV production

Input comes from `netatmo-weather__get_forecast` and
`netatmo-weather__get_station_readings` (what is happening at the house right now).
All forecast times are local (Europe/Warsaw), `HH:MM`.

Per day the forecast gives:
- `condition` / `condition_uk`: the day's weather (WMO code): ясно, мінлива хмарність,
  похмуро, туман, мряка, дощ, зливи, сніг, гроза…
- daylight: `sunrise`, `sunset`, `daylight_h`; `sunshine_hours`
- `solar_radiation_kwh_m2`, `pv_estimate_kwh` (whole day), `pv_window` (hours when PV
  gives at least 10% of the installed power), `pv_peak_hour`
- `cloud_cover_daylight_avg_pct`; rain: `precipitation_mm`, `precipitation_hours`,
  `precipitation_probability_max_pct`, `rain_windows`
- UV: `uv_index_max`, `uv_level_uk` (низький / помірний / високий / дуже високий /
  екстремальний), `uv_windows_3plus`
- `daylight_hours`: one-hour slots from sunrise to sunset (`time` = slot start) with
  `condition_uk`, cloud cover, irradiance (W/m²), UV, rain probability and mm,
  temperature and `pv_kw`
- today only: `now` (current condition, `is_daylight`, `minutes_to_sunset` or
  `minutes_to_sunrise`) and `pv_remaining_kwh` (PV still expected until sunset)

## Daylight comes first
1. **The day's own window.** Use `sunrise`–`sunset` and `pv_window` of that date; never
   assume fixed hours. In Poland the day is about 7.5 h in December and over 16 h in
   June, and `pv_window` is shorter still (the sun is too low near sunrise and sunset).
2. **Rest of today vs. whole day.** When asked during the day ("скільки ще
   виробимо?", or the dispatcher plans after sunrise), use `pv_remaining_kwh`, not
   `pv_estimate_kwh`: energy already produced is in the battery SOC. After sunset
   (`now.is_daylight` false and past `sunset`) say that generation today is over
   and talk about tomorrow.
3. **Before sunrise** (`now.minutes_to_sunrise` set), the whole-day estimate is the
   remaining one.

## What drives production
1. **Daily irradiation** (`solar_radiation_kwh_m2`) is the main number.
   `pv_estimate_kwh` = irradiation × installed kWp × 0.8. Treat it as ±25%.
2. **Hours inside `pv_window` count most**, especially around `pv_peak_hour`. A clear
   peak with a cloudy morning is a good PV day; the reverse is not.
3. **Condition and clouds.** Trust irradiance (`radiation_w_m2`) over cloud cover:
   thin high cloud can show 80% cover and still give 300–400 W/m². Fog in the
   morning cuts the first productive hours; overcast with rain keeps irradiance
   below ~150 W/m².
4. **Rain.** Rain inside `pv_window` lowers output for those hours; rain outside it
   does not matter for PV (mention it for the household). Light rain also cleans
   the panels.
5. **Snow and frost.** Snow (`condition` snow/snow showers, or precipitation with
   `temp_max_c` ≤ 1 °C) can zero production until the panels clear. Say so and
   advise not to count on PV.
6. **Temperature.** Panels lose output when hot (above ~25 °C ambient). Cold, clear
   days produce well relative to irradiation.
7. **UV index is not a PV input.** Panels use visible and infrared light, so take
   the energy figures from irradiance. UV is for people: a high UV index tells you
   that the sky is clear and the sun is high, and it matters for time outdoors.
8. **Season.** A clear day gives roughly 6–7 kWh/m² in June and under 1.5 kWh/m² in
   December. Compare with the season before calling a day "good".

## Labels (use the same scale every time)
| PV estimate vs. a clear day this season | Label |
| --- | --- |
| ≥ 70% | сонячний день |
| 40–70% | мінлива хмарність |
| 15–40% | хмарно, генерація низька |
| < 15% | майже без генерації |

If there is no `pv_estimate_kwh` (PV size not configured), use the label from
irradiation and sunshine hours, and say that kWh are not estimated.

## UV advice (for people, only when relevant)
| `uv_level_uk` | Say |
| --- | --- |
| низький (0–2) | nothing |
| помірний (3–5) | «UV помірний <uv_windows_3plus>: окуляри, крем, якщо довго надворі» |
| високий (6–7) | «UV високий <window>: крем SPF 30+, головний убір, тінь опівдні» |
| дуже високий / екстремальний (8+) | the same plus «уникайте сонця в <window>» (see `weather-alerts`) |

## Reply to a teammate (English, compact)
```
- date: 2026-10-11; condition: partly cloudy (мінлива хмарність)
- daylight: 07:11-18:07 (10.9 h); pv_window: 09:00-15:00, peak 12:00
- pv_estimate_kwh: 11.8 (±25%), label: мінлива хмарність; pv_remaining_kwh: 11.8
- irradiation_kwh_m2: 1.85; sunshine_h: 6.3; clouds (daylight avg): 55%
- rain: 0.6 mm (50%), windows: 15:00-17:00; UV max 2.1 (низький)
- temp: 6.9..12.6 C; gusts: 39 km/h
- station now: 13.3 C, 87% RH, wind 1 km/h
```
`pv_remaining_kwh` only for today. After sunset write `pv_remaining_kwh: 0 (after sunset)`.

## Reply to the user (Ukrainian)
Lead with the condition and the PV estimate (or what is left of today), then the
daylight and best hours, then one line about what matters for the household
(rain windows, wind, frost, UV only when помірний or higher). Example:
«Завтра мінлива хмарність: генерація ≈12 кВт·год, найкраще 09:00–15:00 (пік
о 12:00). Світловий день 07:11–18:07. Дощ можливий 15:00–17:00, пориви до
39 км/год, удень до 13 °C.»
During the day: «До заходу сонця (18:10, ще 4 год 40 хв) очікую ≈4,6 кВт·год;
о 15:00–17:00 можливий дощ.»
