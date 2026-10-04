---
name: energy-history-analysis
description: Summarise past energy data from memory/energy-log.md for a day, week, month or custom period. Use when the user asks about history or trends ("скільки вироблено за тиждень", "порівняй з минулим місяцем", "яка самодостатність"), or for a weekly/monthly summary. Defines the metrics, how to compute them from cumulative counters, data-quality checks and the reply format.
---

# Energy history analysis

Source: `memory/energy-log.md` (and rotated `memory/energy-log-YYYY-MM.md` files if
they exist). Columns:

`| time | kind | soc_% | import_total_kWh | export_total_kWh | yield_total_kWh | batt_charge_total_kWh | batt_discharge_total_kWh | daily_yield_kWh | daily_consumption_kWh |`

Read the file with `memory_get`/`read`; use `memory_search` only to find older files.

## 1. Pick the boundary rows
- A period runs from the **evening row before the first day** to the **evening row
  of the last day**. Example: week 6–12 Oct = evening row of 5 Oct → evening row of 12 Oct.
- If the exact boundary row is missing, use the nearest row of either kind and
  say which timestamps you used.
- "Today so far": latest morning row → a fresh `get_realtime_data`.

## 2. Compute from cumulative counters (not by summing rows)
Subtract the boundary values. Two subtractions per metric are reliable; adding 30
daily values by hand is not.

| Metric | Formula (Δ = last − first boundary) |
| --- | --- |
| Production `P` | Δ `yield_total_kWh` |
| Import `I` | Δ `import_total_kWh` |
| Export `E` | Δ `export_total_kWh` |
| Battery in / out | Δ `batt_charge_total_kWh` / Δ `batt_discharge_total_kWh` |
| Consumption `C` | `P + I − E − (battery in − battery out)` |
| Self-consumption | `(P − E) / P` — share of own production used at home |
| Self-sufficiency | `(C − I) / C` — share of consumption covered without the grid |
| Battery cycles | battery out / capacity (capacity from `estimate_grid_charge_need` assumptions or `MEMORY.md`) |
| Average per day | metric / number of days |

Cross-check: the sum of `daily_consumption_kWh` over the evening rows should be
within ~10% of `C`. If not, report `C` from counters and mention the mismatch.

## 3. Data-quality checks (always run, report briefly)
- **Gaps**: days with no evening row. Report "дані за N з M днів".
- **Counter reset**: a negative Δ on any total (inverter replaced or reset). Split
  the period at the reset and add the parts; say so.
- **Outliers**: a day with production or consumption more than 3× the period
  median. Mention it, do not drop it silently.
- Fewer than 2 rows in the period: say there is not enough data yet and when there
  will be (the log grows by two rows a day).

## 4. Comparisons
- Compare with the previous period of the same length ("тиждень до цього") and, if
  the log has it, the same period last year. Give the difference in kWh and %.
- Explain differences with facts you have: fewer sunny days (ask `weather-cast`
  for a short history only if the user wants a reason), more grid charging
  (Decisions log in `MEMORY.md`), heating season.
- Money: only if the user gave their import price or tariff (in `MEMORY.md`). Never
  value imported energy at RCE. Without a tariff, report energy only and offer to
  calculate once they tell you the price.

## 5. Reply format (Ukrainian)
```
📊 Енергія за 6–12 жовтня (7 днів)
☀️ Вироблено: 84,3 кВт·год (≈12,0 на день; −18% до попереднього тижня)
🏠 Спожито: ≈96,1 кВт·год (≈13,7 на день)
🔌 Мережа: імпорт 31,2 / експорт 19,4 кВт·год
🔋 Батарея: віддала 38,5 кВт·год (≈3,9 циклу)
♻️ Власне споживання 77% · самодостатність 68%
ℹ️ Дані за 7 з 7 днів.
```
Follow with at most two sentences of interpretation backed by the numbers.
Values are estimates from the inverter counters; say «≈» where the formula
estimates (consumption, cycles).
