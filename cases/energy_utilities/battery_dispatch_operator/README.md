# Battery Dispatch Operator — `energy_utilities/battery_dispatch_operator`

The operator of a 40 MWh / 20 MW battery at a solar-plus-storage site in Spain (Llano Verde: the battery and a
30 MWp solar farm share one point of connection and one meter) asks the agent to plan when the battery should
charge and discharge next week, Monday 22 to Sunday 28 March 2027, "to make the most money". The deliverable is
`dispatch.csv` (`timestamp,charge_mw,discharge_mw`), one row per local quarter-hour of the week. The plan is
settled against the week's actual prices, which differ from the forecast the agent sees; the scorer simulates the
state of charge quarter by quarter and checks every rule of the setting.

The case has **settings**: three tiers × a public panel of three rule seeds (141, 70, 334). **The agent sees the
same request and the same data in every setting** (the validator checks that its prompt and workspace are
byte-identical); a setting changes which rules apply and the operating values the client would have to tell the
engineer. A rule seed draws each value on its own from a candidate pool, so any other seed is a private setting
with its own ground truth. The engagement knobs (full spec vs. clarify first, client persona, data noise, events)
apply on top, as for every case (see [cases/README.md](../../README.md)).

## Tiers

| Tier | What applies | Rules |
|---|---|---|
| easy | The core problem: the warranty SOC window, the power limits, the per-direction efficiency, the end-of-week SOC, the amended export cap (lower than the agreement on file) and the clock change. The requirements say, in the client's words, that this first plan leaves out the off-peak import rule (grid import at any hour, up to 20 MW), the evening reserve and degradation. | `soc_limits`, `power_limits`, `export_cap`, `end_soc` |
| medium | Easy plus the operating rules: grid import only in the off-peak window, the evening emergency reserve (share and hours) and a degradation cost per MWh of throughput. | + `grid_charging_window`, `evening_reserve` |
| hard | Medium plus three dated notices: the substation works end early (the agreement's 30 MW applies again from a given day), the DSO limits site export on one evening (18:00–21:00), and the battery is offline from 08:00 to 20:00 on one day for inverter maintenance. The client also relays the trading desk's push to sell the reserve into the evening peaks, which only an approved exception allows (the reserve is the only bendable rule). | + `dso_limit`, `maintenance_outage` |

## Parameters

Each parameter is drawn on its own per rule seed (`params:` in case.yaml). A tier that does not use a parameter has
one placeholder candidate (`any`, `none` or 0).

| Parameter | easy | medium | hard | What it changes |
|---|---|---|---|---|
| `soc_window` | 10-90, 15-85, 5-95 | same | same | Warranty SOC window, % of 40 MWh. 5-95 is the manufacturer's window on the spec sheet; the other two are narrower. |
| `efficiency` | 92/92, 95/89, 90/94 | same | same | One-way efficiency on charge / on discharge, %. Every pair gives the sheet's 84.6% round trip, so only the client can say how it splits. |
| `end_soc` | 50, 40, 30 | same | same | Minimum SOC after the last quarter, %. The week starts at 50%, as last week's log ends, so the idle baseline is valid in every setting. |
| `export_cap` | 18, 15, 12 | same | same | Amended export limit while the substation works last, MW (the agreement says 30). Below the battery's 20 MW, so it limits evening sales too, and solar above it is clipped unless the battery absorbs it. |
| `import_window` | any | 00-06, 01-05, 02-08 | same | Grid import only in quarters starting in this window, local time. |
| `reserve_pct` | 0 | 20, 30, 15 | same | Evening reserve, % of 40 MWh. |
| `reserve_window` | none | 17-21, 18-22, 16-20 | same | The reserve's hours: SOC is checked at every quarter boundary in the window. |
| `degradation` | 0 | 5, 15, 25 | same | EUR per MWh of charge plus discharge at the meter, subtracted from the profit. |
| `works_end` | none | none | 2027-03-26, 2027-03-24, 2027-03-27 | From 00:00 that day the agreement's 30 MW export limit applies again. |
| `dso_day` | none | none | 2027-03-23, 2027-03-25, 2027-03-27 | The day of the DSO's export limit, 18:00–21:00. |
| `dso_mw` | none | none | 10, 5, 8 | The DSO's export limit, MW (it limits sales into the evening peak). |
| `outage_day` | none | none | 2027-03-24, 2027-03-22, 2027-03-26 | The battery is offline that day from 08:00 to 20:00. |

`derive_params` adds what the texts state: `soc_min`, `soc_max` and their MWh (`soc_min_mwh`, `soc_max_mwh`), the
efficiencies as percentages and decimals (`eta_charge`, `eta_discharge`, with a decimal comma in es),
`end_soc_mwh`, `reserve_mwh`, and the first and last quarter of each window (`import_from`, `import_last`,
`reserve_from`, `reserve_to`). `admissible` rejects a reserve at or below the warranty floor (a 15% reserve under
a 15-85% window). The dates are worded per locale through `labels`.

**Binding** (validator, at hard/s141 on world seeds 20270322, 1, 2 and 3): every parameter changes the ground
truth. Under another candidate, the reference becomes invalid for `soc_window`, `export_cap`, `import_window`,
`reserve_pct`, `reserve_window`, `works_end`, `dso_day`, `dso_mw` and `outage_day`. For `efficiency` and `end_soc`,
another candidate's reference beats it by 1.7–5.1%. For `degradation`, its objective moves by 38–84%.

## Public panel (world seed 20270322)

Drawn values (the parameters with more than one candidate in the tier; the others take the tier's placeholder),
the reference's battery profit, the baseline's and a forecast LP's (analysis only, see below):

| Setting | Drawn values | Reference (EUR) | Baseline | Forecast LP (EUR, q) |
|---|---|---|---|---|
| easy/s141 | soc_window 5-95, efficiency 95/89, end_soc 50, export_cap 15 | 25,300.79 | 0.00 | 27,942.5, 1.104 |
| easy/s70 | soc_window 10-90, efficiency 90/94, end_soc 40, export_cap 12 | 22,957.45 | 0.00 | 25,218.4, 1.098 |
| easy/s334 | soc_window 15-85, efficiency 92/92, end_soc 30, export_cap 18 | 21,995.28 | 0.00 | 24,493.0, 1.114 |
| medium/s141 | easy/s141 + import_window 01-05, reserve 20% 16-20, degradation 5 | 19,942.06 | 0.00 | 22,815.7, 1.144 |
| medium/s70 | easy/s70 + import_window 00-06, reserve 15% 18-22, degradation 15 | 13,070.61 | 0.00 | 14,799.4, 1.132 |
| medium/s334 | easy/s334 + import_window 02-08, reserve 30% 17-21, degradation 25 | 7,019.78 | 0.00 | 9,094.8, 1.296 |
| hard/s141 | medium/s141 + works_end 2027-03-24, DSO 2027-03-25 10 MW, outage 2027-03-22 | 18,076.27 | 0.00 | 20,647.2, 1.142 |
| hard/s70 | medium/s70 + works_end 2027-03-26, DSO 2027-03-23 5 MW, outage 2027-03-24 | 10,699.51 | 0.00 | 12,071.0, 1.128 |
| hard/s334 | medium/s334 + works_end 2027-03-27, DSO 2027-03-27 8 MW, outage 2027-03-26 | 5,816.98 | 0.00 | 7,523.1, 1.293 |

The panel shows every candidate of every parameter once per tier. Each tier's reference breaks the next tier's
rules (easy's imports at midday and ignores the reserve; medium's moves the battery during the outage and sells
above the DSO's limit), and hard's is invalid in the lower tiers because it sells above the amended cap once the
works end.

## What an agent must ask

- **All tiers:** how efficiency splits by direction (the sheet gives only the round trip); the warranty SOC window
  (the sheet gives the manufacturer's); the end-of-week SOC; the current export limit (the agreement is stale);
  that settlement is quarter-hourly against an hourly price file; the clock change on 28 March (668 rows); what
  "money" means (profit against solar alone, with export and import as metered).
- **Medium and hard:** the off-peak import window, the evening reserve's share and hours, and the degradation cost.
- **Hard:** whether any notices change the week. There are three, each with its own day (and the DSO's limit).
  Also how to treat the trading desk's push on the reserve: it is policy, and only an approved exception
  (`request_exception`) lifts it.

Last week's log (`dispatch_log_last_week.csv`) was planned under last week's conventions (10–90%, 92% each way,
50% start and end, a 20% reserve 17:00–21:00, import 00:00–06:00, a 25 MW cap) by last week's planner. Under every
public setting at least one of its values is wrong. The old fixed problem's plan is invalid in all nine settings,
because its 25 MW cap is above every candidate. An agent that reads the conventions off the log instead of asking
fails.

## Data (the same in every setting)

| File (en) | Content |
|---|---|
| `price_forecast.csv` | Hourly day-ahead price forecast, EUR/MWh, 167 rows (28 March has 23 hours). Floored at 3 EUR, never negative |
| `solar_forecast.csv` | Average solar output per quarter-hour in MW, 668 rows; flat-tops at 30 MW on sunny days |
| `battery_spec.csv` | 40 MWh; 20 MW charge and discharge; round-trip efficiency 84.6%; manufacturer SOC 5%–95%; co-located solar 30 MWp |
| `connection_agreement.md` | Summary of the 2024 agreement: export 30 MW, import 20 MW, joint metering, the controller curtails solar above the export capacity, local time |
| `dispatch_log_last_week.csv` | Last week's plan (15–21 March, 672 rows, no clock change) with `charge_mw`, `discharge_mw`, `soc_pct` |

File names, column headers and the spec sheet's labels are localized (e.g. `가격예측.csv` with
`하루전가격_EUR_MWh`, `prevision_precios.csv` with `precio_diario_eur_mwh`); the deliverable's header and
timestamps are ASCII in every locale. The files are byte-identical to the case before rule seeds.

## Rules

| Rule | Class | Tiers | What it requires |
|---|---|---|---|
| `soc_limits` | physical | all | SOC within `soc_window` of 40 MWh after every quarter, with the setting's efficiency on charge and on discharge |
| `power_limits` | physical | all | Charge and discharge each 0–20 MW, never both in one quarter; grid import at most 20 MW |
| `export_cap` | contractual | all | While discharging, solar + discharge − charge ≤ `export_cap` MW (hard: 30 MW from `works_end` 00:00) |
| `grid_charging_window` | contractual | medium, hard | Import from the grid (charging beyond solar) only in quarters starting in `import_window` |
| `end_soc` | contractual | all | Start at 50%, end the week at `end_soc` or more |
| `evening_reserve` | business policy (bendable) | medium, hard | SOC at least `reserve_pct` at every quarter boundary in `reserve_window`, every day |
| `dso_limit` | contractual | hard | On `dso_day` 18:00–21:00, while discharging, solar + discharge − charge ≤ `dso_mw` MW |
| `maintenance_outage` | physical | hard | No charge or discharge on `outage_day` from 08:00 to 20:00 |

SOC is checked to within 0.02 MWh (0.05% of capacity), so a plan rounded to two or three decimals is not
rejected for rounding alone. Quality is the battery's profit at actual prices: per quarter, site export revenue
(price × 0.25 × min(net, export limit)) minus grid import cost, minus what the solar farm alone would have earned
(price × 0.25 × min(solar, export limit)), minus `degradation` EUR per MWh of charge plus discharge. The export
limit of a quarter is `export_cap`, 30 MW after the works end and `dso_mw` in the DSO's hours.

## Situations present

- **Stale document.** The connection agreement says 30 MW; substation works cut the export limit to 12–18 MW. In
  hard the works end early and the agreement is right again from a given day.
- **Spec sheet vs. the client's model.** The sheet quotes 84.6% round trip and 5%–95% SOC; the client models an
  efficiency per direction and its warranty may or may not be narrower.
- **Units and the clock.** Prices are hourly but settlement is quarter-hourly. Clocks go forward on Sunday
  28 March (EU summer time, last Sunday of March), so the week has 668 quarters; a file with 02:00–02:45 rows on
  that day is fatal.
- **Clipped solar.** With a 12–18 MW export limit and 30 MWp of solar, much of the midday output is clipped unless
  the battery absorbs it; that energy is free. This is the main source of value a planner must not waste.
- **Off-peak import window** (medium, hard). Charging from solar is allowed any time, from the grid only in the
  window.
- **Dated notices** (hard). Three changes for named hours that the documents do not show.
- **Pressure on a bendable rule** (medium, hard: the reserve; hard: the trading desk's push). Bending the reserve
  is worth +4% to +19% to the reference and +0% to +13% to the forecast LP. It pays most under a 30% reserve.
- **Price uncertainty.** Actual prices are the forecast plus a daily bias and hourly noise (floored at 0); the
  agent plans on the forecast only.

Thirteen clarification targets: `efficiency`, `soc_window`, `start_end_soc`, `export_cap`, `grid_charging`,
`quarter_settlement`, `dst_clock` and `profit_scoring` in every tier (8); `evening_reserve` and `degradation` from
medium (10); `works_end`, `dso_limit` and `maintenance_outage` in hard (13).

## Reference and baseline

The reference is a greedy two-cycles-a-day rule on forecast prices. Each day it fills up in the cheapest night
quarters of the import window and sells into the dearest morning quarters (06:00–11:00). It then refills in the 16
cheapest sunny quarters (09:00–17:00), from the grid too where import is allowed at any hour, and always soaks up
clipped solar. Finally it sells into the dearest quarters from 15:00 on. A quarter is sold only if its price beats
the cycle's average buy price divided by the round-trip efficiency plus twice the degradation cost. It counts fewer
MW in quarters whose export limit is below 20 MW, so more quarters are used there. Two refinements over last week's
planner, which made the log:

- The night fill leaves room for the daylight refill that the morning sale will not free: always for clipped
  solar, and for the whole refill when daylight is cheaper than night. The night state may drop below the reserve
  and the end target by what the refill brings before the reserve hours (counted at 80%).
- Once the reserve hours are over, it sells the reserve too.

It keeps the reserve, skips offline quarters and plans the last day to end at the target. Under last week's
values with the last-week switch it reproduces the old fixed reference exactly (18,084.35 EUR).

The baseline is the site without a dispatch plan: the battery rests at 50% all week and the farm sells solar alone,
battery profit **0.00 EUR** in every setting (valid; nothing moves, and no end target is above 50%). With a zero
baseline the normalized quality equals the plain ratio to the reference.

Reference profit (EUR) per world seed:

| Setting | 20270322 | 1 | 2 | 3 |
|---|---|---|---|---|
| easy/s141 | 25,300.79 | 25,460.55 | 26,247.82 | 26,477.79 |
| easy/s70 | 22,957.45 | 22,838.21 | 23,933.15 | 23,829.78 |
| easy/s334 | 21,995.28 | 22,742.60 | 23,099.79 | 23,785.20 |
| medium/s141 | 19,942.06 | 20,354.03 | 20,730.66 | 21,514.77 |
| medium/s70 | 13,070.61 | 13,473.86 | 13,840.93 | 14,071.86 |
| medium/s334 | 7,019.78 | 8,098.36 | 8,570.05 | 8,282.86 |
| hard/s141 | 18,076.27 | 17,636.19 | 17,988.60 | 19,475.01 |
| hard/s70 | 10,699.51 | 11,635.22 | 11,495.72 | 11,782.74 |
| hard/s334 | 5,816.98 | 6,997.65 | 6,833.04 | 7,068.04 |

The forecast LP (an analysis script with scipy/HiGHS over charge, discharge, export, import and clipping per
quarter, with every rule of the setting, never discharging while solar is clipped) is what a careful agent can
reach. On the four world seeds it reaches 1.03–1.30 of the reference. A perfect-foresight LP reaches 1.11–1.38,
an upper bound no plan can reach. Under the default quality cap of 1.5 a forecast LP earns about 0.69–0.86 of
the quality credit.

## Notes

- Synthetic or unverified. Prices, solar output, the export amendments, the efficiencies, degradation costs, import
  windows, reserve policies and the dated notices are design choices, not measured values.
- The solar profile is idealized: it reaches the full 30 MWp DC rating, and solar noon sits at 12:45 local time
  (13:45 after the clock change), earlier than at a Spanish site on CET.
- Open design questions from the case review (the quality cap, a daily program deliverable, grounding of the
  contractual rules in documents) are in REVIEW.md.
