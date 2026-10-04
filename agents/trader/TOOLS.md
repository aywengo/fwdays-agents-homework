# Tools reference
| Tool | Notes |
| --- | --- |
| `rce-prices__get_prices(day="today"|"tomorrow"|"YYYY-MM-DD", include_hours=true)` | records[hour, price_per_kwh, classification], summary{min,max,avg_pln_kwh,cheapest_hours,most_expensive_hours,negative_or_zero_hours,cheapest_3h_window,classification_counts} |
| `rce-prices__get_current_price` | hour, record, day_avg_pln_kwh, vs_avg_percent |
| `rce-prices__plan_grid_charge(energy_kwh, max_charge_kw, day="today", latest_end_hour=17, min_spread_pln_kwh=0.2, efficiency=0.9)` | hours_needed, charge_start/charge_end (HH:MM), charge_avg_pln_kwh, charge_cost_pln, peak window and price, spread_pln_kwh, estimated_saving_pln, recommended, reason |
Classifications (godzinowe.pl): UJEMNA < 0, ZERO, BARDZO NISKA < 0.15, NISKA < 0.35, ŚREDNIA < 0.55, WYSOKA < 0.75, BARDZO WYSOKA < 1.5, EKSTREMALNA ≥ 1.5 zł/kWh.
