# Battery Dispatch Operator — `energy_utilities/battery_dispatch_operator`

The operator of a 40 MWh / 20 MW battery at a solar-plus-storage site in Spain (Llano Verde: the battery and a
30 MWp solar farm share one point of connection and one meter) asks the agent to plan when the battery should
charge and discharge next week, Monday 22 to Sunday 28 March 2027, "to make the most money". The deliverable is
`dispatch.csv` (`timestamp,charge_mw,discharge_mw`), one row per local quarter-hour of the week. The plan is
settled against the week's actual prices, which differ from the forecast the agent sees; the scorer simulates the
state of charge quarter by quarter and checks every rule.

The case has **no settings**: one ground truth, the same problem at every difficulty. The engagement knobs (full
spec vs. clarify first, client persona, data noise, events) apply on top, as for every case (see
[cases/README.md](../../README.md)).

## Data

| File (en) | Content |
|---|---|
| `price_forecast.csv` | Hourly day-ahead price forecast, EUR/MWh, 167 rows (28 March has 23 hours). Floored at 3 EUR, never negative |
| `solar_forecast.csv` | Average solar output per quarter-hour in MW, 668 rows; flat-tops at 30 MW on sunny days, 67 quarters above 25 MW |
| `battery_spec.csv` | 40 MWh; 20 MW charge and discharge; round-trip efficiency 84.6%; manufacturer SOC 5%–95%; co-located solar 30 MWp |
| `connection_agreement.md` | Summary of the 2024 agreement: export 30 MW, import 20 MW, joint metering, the controller curtails solar above the export capacity, local time |
| `dispatch_log_last_week.csv` | Last week's plan (15–21 March, 672 rows, no clock change) with `charge_mw`, `discharge_mw`, `soc_pct` |

File names, column headers and the spec sheet's labels are localized (e.g. `가격예측.csv` with
`하루전가격_EUR_MWh`, `prevision_precios.csv` with `precio_diario_eur_mwh`); the deliverable's header and
timestamps are ASCII in every locale.

## Rules

| Rule | Class | What it requires |
|---|---|---|
| `soc_limits` | physical | SOC within 10%–90% of 40 MWh after every quarter, with 92% efficiency on charge and on discharge |
| `power_limits` | physical | Charge and discharge each 0–20 MW, never both in one quarter; grid import at most 20 MW |
| `export_cap` | contractual | While discharging, solar + discharge − charge ≤ 25 MW (amended cap, the agreement on file says 30) |
| `grid_charging_window` | contractual | Import from the grid (charging beyond solar) only in quarters starting 00:00–05:45 local time |
| `end_soc` | contractual | Start at 50%, end the week at 50% or more |
| `reserve_20pct` | business policy (bendable) | SOC at least 20% at every quarter boundary from 17:00 to 21:00, every day |

SOC is checked to within 0.02 MWh (0.05% of capacity), so a plan rounded to two or three decimals is not
rejected for rounding alone. Quality is the battery's profit at actual prices: per quarter, site export revenue
(price × 0.25 × min(net, 25)) minus grid import cost, minus what the solar farm alone would have earned
(price × 0.25 × min(solar, 25)), minus EUR 5 per MWh of charge plus discharge throughput.

## Situations present

- **Stale document.** The connection agreement says 30 MW; substation works cut the export limit to 25 MW from
  1 March to 30 June 2027. A plan made at 30 MW is invalid (`export_cap`).
- **Spec sheet vs. the client's model.** The sheet quotes 84.6% round trip and 5%–95% SOC; the client models 92%
  each way and its warranty allows 10%–90%.
- **Units and the clock.** Prices are hourly but settlement is quarter-hourly. Clocks go forward on Sunday
  28 March (EU summer time, last Sunday of March), so the week has 668 quarters; a file with 02:00–02:45 rows on
  that day is fatal.
- **Off-peak import window.** Charging from solar is allowed any time, from the grid only 00:00–05:45.
- **Clipped solar.** When the battery is not discharging, solar above 25 MW is curtailed unless the battery
  absorbs it.
- **Bendable rule.** The evening reserve is company policy. Relaxing it is worth +9.1% to the reference heuristic
  (19,733.9 vs. 18,084.35 EUR) and +3.8% to a forecast LP (22,156.6 vs. 21,343.2 EUR).
- **Price uncertainty.** Actual prices are the forecast plus a daily bias and hourly noise (floored at 0); the
  agent plans on the forecast only.

Nine clarification targets: efficiency, SOC window, start/end SOC, export cap, grid-charging window,
quarter-hour settlement, the clock change, the evening reserve and the profit definition.

## Reference and baseline numbers (seed 20270322)

The reference is a greedy two-cycles-a-day rule on forecast prices: each day it fills up in the cheapest night
quarters of the import window and sells into the dearest morning quarters (06:00–11:00), then refills from solar
in the 16 cheapest sunny quarters (09:00–17:00), always soaking up clipped solar, and sells into the dearest
quarters from 15:00 on; a quarter is sold only if its price beats the average buy price divided by 0.92² plus
twice the degradation cost. It keeps the 20%
reserve until 21:00 and plans the last day to end at 50%. It scores **18,084.35 EUR** at actual prices
(19,225.3 at forecast prices): export revenue 58,211.90, import cost 7,227.53, solar-only revenue 29,237.22,
degradation 3,662.80 (732.56 MWh throughput), 36.49 MWh curtailed, SOC 20%–90%, ending at 50%.

The baseline is the site without a dispatch plan: the battery rests at 50% all week and the farm sells solar alone,
battery profit **0.00 EUR** (valid; nothing moves, so no rule can bite). With a zero baseline the normalized
quality equals the plain ratio to the reference.

| World seed | Reference (EUR) | Baseline (EUR) | Forecast LP (EUR, q) | Perfect-foresight LP (EUR, q) | Reference without the reserve (EUR) |
|---|---|---|---|---|---|
| 20270322 | 18,084.35 | 0.00 | 21,343.2, 1.180 | 23,099.9, 1.277 | 19,733.9 |
| 1 | 18,742.76 | 0.00 | 21,733.8, 1.160 | 23,388.3, 1.248 | 20,269.6 |
| 2 | 19,265.16 | 0.00 | 21,638.5, 1.123 | 23,351.8, 1.212 | 20,545.2 |
| 3 | 20,542.92 | 0.00 | 22,873.4, 1.113 | 23,932.5, 1.165 | 22,332.2 |

The LPs are an analysis script (scipy/HiGHS over charge, discharge and export per quarter, all rules), not part of
the case. The forecast LP is what a careful agent can reach; the perfect-foresight LP uses the actual prices and is
an upper bound no plan can reach. Under the default quality cap of 1.5 a forecast LP earns about 0.74–0.79 of the
quality credit.

## Notes

- Synthetic or unverified. Prices, solar output, the 25 MW amendment, the 92% one-way efficiency, EUR 5/MWh
  degradation, the 00:00–06:00 import window and the reserve policy are design choices, not measured values.
- The solar profile is idealized: it reaches the full 30 MWp DC rating, and solar noon sits at 12:45 local time
  (13:45 after the clock change), earlier than at a Spanish site on CET.
- Open design questions from the case review (reference strength, the leaky log, settings, pressure events, a daily
  program deliverable, grounding of the contractual rules) are in REVIEW.md.
