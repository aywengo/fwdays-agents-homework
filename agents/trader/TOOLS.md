# Tools reference
| Tool | Notes |
| --- | --- |
| `rce-prices__get_prices(day="today"|"tomorrow"|"YYYY-MM-DD", include_hours=true)` | records[hour, price_per_kwh, classification], summary{min,max,avg_pln_kwh,cheapest_hours,most_expensive_hours,negative_or_zero_hours,cheapest_3h_window,classification_counts} |
| `rce-prices__get_current_price` | hour, record, day_avg_pln_kwh, vs_avg_percent |
Classifications (godzinowe.pl): UJEMNA < 0, ZERO, BARDZO NISKA < 0.15, NISKA < 0.35, ŚREDNIA < 0.55, WYSOKA < 0.75, BARDZO WYSOKA < 1.5, EKSTREMALNA ≥ 1.5 zł/kWh.
