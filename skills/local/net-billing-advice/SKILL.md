---
name: net-billing-advice
description: Explain Polish prosumer net-billing in plain Ukrainian and turn RCE prices into practical advice on when to use, store, export or grid-charge energy. Use when the user asks whether to export or store, why prices are negative, what an hour of export is worth, or when interpreting plan_grid_charge results.
---

# Net-billing advice (Poland)

Scope: household energy-usage advice for one prosumer. Not financial or
investment advice. If a question depends on the user's exact tariff or contract,
say so and ask for the tariff name instead of guessing.

## How the money works (mechanism, keep it this simple)
- **Export** is credited at the market price of that hour (RCE, the PSE price you
  get from `rce-prices__get_prices`) into the prosumer deposit. The deposit offsets
  the energy part of later bills.
- **Import** costs the supplier's energy price **plus** distribution fees, other
  charges and VAT. So an imported kWh costs much more than the RCE price of the
  same hour.
- Therefore a kWh **used at home** (directly or via the battery) is almost always
  worth more than the same kWh exported. Export is what is left after the house
  and the battery are served.
- RCE can be **zero or negative** at sunny middays with low demand. Then exported
  energy earns nothing (or the value is negative), and using or storing energy, or
  even charging from the grid, is the right move.

Do not state exact tariff numbers, deposit rules or coefficients unless the user
gave them or they are in `MEMORY.md`. The rules change; the mechanism above is
what the advice relies on.

## Decision rules
1. Negative or zero RCE hours → shift heavy loads there (dishwasher, washing,
   water heating, EV), charge the battery, avoid exporting.
2. Evening peak (RCE ≥ 0.75 zł/kWh) → keep battery energy for it; avoid big loads.
3. Grid charging pays off only when `plan_grid_charge` returns `recommended: true`
   (peak price minus charge price after ~10% losses is above the margin). Report
   its `reason` when it is not recommended.
4. Very cheap but positive midday with a sunny forecast → the battery will fill
   from PV anyway; grid charging adds little. Prefer load shifting.

## How to present
- One recommendation, then the numbers that justify it:
  «Увімкніть пральку 12:00–14:00: ціна RCE ≈0,02 zł/кВт·год, а ввечері ≈0,98.»
- Use the RCE price for timing comparisons; never present RCE as the price the user
  pays for imported energy.
- Classifications from the API (BARDZO NISKA … EKSTREMALNA) may be mentioned in
  Polish in brackets once, then use Ukrainian words: дуже низька, низька, середня,
  висока, дуже висока, екстремальна.
