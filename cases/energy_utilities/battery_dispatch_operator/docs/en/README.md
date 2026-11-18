# Battery Dispatch Operator — `energy_utilities/battery_dispatch_operator`

The operator of a 40 MWh / 20 MW battery at a solar-plus-storage site in Spain (Llano Verde: the battery and a
30 MWp solar farm share one point of connection and one meter) asks the agent to plan when the battery should
charge and discharge next week, Monday 22 to Sunday 28 March 2027, "to make the most money". The deliverable is
`dispatch.csv` (`timestamp,charge_mw,discharge_mw`), one row per local quarter-hour of the week. The plan is
judged by its expected profit: every quarter settled at its hour's forecast price. The scorer simulates the state
of charge quarter by quarter and checks every rule of the setting.

The case has **settings**: three tiers × a public panel of three rule seeds (141, 70, 334). **The agent sees the
same request and the same data in every setting** (the validator checks that its prompt and workspace are
byte-identical); a setting changes which rules apply and the operating values the client would have to tell the
engineer. A rule seed draws each value on its own from a candidate pool, so any other seed is a private setting
with its own ground truth. The engagement knobs (full spec vs. clarify first, client persona, data noise, events)
apply on top, as for every case (see [cases/README.md](../../../../README.md)).

The case is **audited** (`audited: true`): its ground truth is in [GT.md](../../GT.md), what the client answers
from in [CLIENT_REVIEW.md](../../CLIENT_REVIEW.md), and the audit's numbers in `dataset/audit.json` (section
"Ground truth audit" below).

## Tiers

| Tier | What applies | Rules |
|---|---|---|
| easy | The core problem: the warranty SOC window, the power limits, the per-direction efficiency, the end-of-week SOC, the amended export cap (lower than the agreement on file) and the clock change. The requirements say, in the client's words, that this first plan leaves out the off-peak import rule (grid import at any hour, up to 20 MW), the evening reserve and degradation. | `complete_plan`, `soc_limits`, `power_limits`, `export_cap`, `end_soc` |
| medium | Easy plus the operating rules: grid import only in the off-peak window, the evening emergency reserve (level and hours) and a degradation cost per MWh of throughput. | + `grid_charging_window`, `evening_reserve` |
| hard | Medium plus three dated notices: the substation works end early (the agreement's 30 MW applies again from a given day), the DSO limits site export on one evening (18:00–21:00), and the battery is offline from 08:00 to 20:00 on one day for inverter maintenance. The client also relays the trading desk's push to sell the reserve into the evening peaks, which only an approved exception allows (the reserve is the only bendable rule). | + `dso_limit`, `maintenance_outage` |

## Parameters

Each parameter is drawn on its own per rule seed (`params:` in case.yaml). A tier that does not use a parameter has
one placeholder candidate (`any`, `none` or 0).

| Parameter | easy | medium | hard | What it changes |
|---|---|---|---|---|
| `soc_window` | 10-85, 15-85, 15-90 | same | same | Warranty SOC window, % of 40 MWh. Never the spec sheet's 5-95 nor last week's 10-90: always narrower than the sheet. |
| `efficiency` | 94/90, 95/89, 90/94 | same | same | One-way efficiency on charge / on discharge, %. Every pair gives the sheet's 84.6% round trip; never the even 92/92 the log used, so only the client can say how it splits. |
| `end_soc` | 50, 40, 30 | same | same | Minimum SOC after the last quarter, %. The week starts at 50%, as last week's log ends. |
| `export_cap` | 18, 15, 12 | same | same | Amended export limit while the substation works last, MW (the agreement says 30, the log ran at 25). Below the battery's 20 MW, so it limits evening sales too, and solar above it is clipped unless the battery absorbs it. |
| `import_window` | any | 00-06, 01-05, 02-08 | same | Grid import only in quarters starting in this window, local time. |
| `reserve_pct` | 0 | 20, 30, 15 | same | Evening reserve, % of 40 MWh. |
| `reserve_window` | none | 17-21, 16-20, 18-22 | same | The reserve's hours: SOC is checked at every quarter boundary in the window. |
| `degradation` | 0 | 5, 15, 25 | same | EUR per MWh of charge plus discharge at the meter, subtracted from the profit. |
| `works_end` | none | none | 2027-03-26, 2027-03-24, 2027-03-27 | From 00:00 that day the agreement's 30 MW export limit applies again. |
| `dso_day` | none | none | 2027-03-23, 2027-03-25, 2027-03-27 | The day of the DSO's export limit, 18:00–21:00. |
| `dso_mw` | none | none | 10, 5, 8 | The DSO's export limit, MW (it limits sales into the evening peak). |
| `outage_day` | none | none | 2027-03-24, 2027-03-22, 2027-03-26 | The battery is offline that day from 08:00 to 20:00. |

`derive_params` adds what the texts state: `soc_min`, `soc_max` and their MWh (`soc_min_mwh`, `soc_max_mwh`), the
efficiencies as percentages and decimals (`eta_charge`, `eta_discharge`, with a decimal comma in es),
`end_soc_mwh`, `reserve_mwh`, and the first and last quarter of each window (`import_from`, `import_last`,
`reserve_from`, `reserve_to`). `admissible` rejects a reserve at or below the warranty floor (a 15% reserve under
a 15-85% or 15-90% window). The dates are worded per locale through `labels`.

**Binding** (validator, at the first public seed of each tier, on world seeds 20270322, 1, 2 and 3): every
parameter changes the ground truth in every tier where it varies; under another candidate the reference becomes
invalid or another candidate's reference beats it by 1% or more.

## Public panel (world seed 20270322)

Drawn values (the parameters with more than one candidate in the tier), the reference's expected profit, the
client's planner's (the zero point) and the width of the quality scale, (reference − planner) / reference:

| Setting | Drawn values | Reference (EUR) | Client's planner (EUR) | Scale |
|---|---|---|---|---|
| easy/s141 | soc_window 15-90, efficiency 95/89, end_soc 50, export_cap 15 | 24,040.73 | 21,914.15 | 8.8% |
| easy/s70 | soc_window 10-85, efficiency 90/94, end_soc 40, export_cap 12 | 24,046.15 | 21,565.89 | 10.3% |
| easy/s334 | soc_window 15-85, efficiency 94/90, end_soc 30, export_cap 18 | 24,112.69 | 21,723.40 | 9.9% |
| medium/s141 | easy/s141 + import_window 01-05, reserve_pct 20, reserve_window 18-22, degradation 5 | 19,115.11 | 17,343.54 | 9.3% |
| medium/s70 | easy/s70 + import_window 00-06, reserve_pct 15, reserve_window 16-20, degradation 15 | 14,476.11 | 13,026.75 | 10.0% |
| medium/s334 | easy/s334 + import_window 02-08, reserve_pct 30, reserve_window 17-21, degradation 25 | 9,386.77 | 8,102.58 | 13.7% |
| hard/s141 | medium/s141 + works_end 2027-03-24, dso_day 2027-03-25, dso_mw 10, outage_day 2027-03-22 | 17,821.90 | 16,355.36 | 8.2% |
| hard/s70 | medium/s70 + works_end 2027-03-26, dso_day 2027-03-23, dso_mw 5, outage_day 2027-03-24 | 12,412.04 | 10,994.68 | 11.4% |
| hard/s334 | medium/s334 + works_end 2027-03-27, dso_day 2027-03-27, dso_mw 8, outage_day 2027-03-26 | 7,780.78 | 6,974.32 | 10.4% |

The panel shows every candidate of every parameter once per tier.

## What an agent must ask

- **All tiers:** how the 84.6% round trip splits by direction (the sheet gives only the round trip, and the client's
  split is never even); the warranty SOC window (the sheet gives the manufacturer's, the log last week's); the
  end-of-week SOC; the current export limit (the agreement is stale).
- **Medium and hard:** the off-peak import window, the evening reserve's level and its hours, and the degradation
  cost.
- **Hard:** whether any notices change the week. There are three, each with its own day (and the DSO's limit).
  Also how to treat the trading desk's push on the reserve: it is policy, and only an approved exception
  (`request_exception`) lifts it.

What the data settles is context, not a target: quarter-hour settlement against the hourly price (the solar
forecast and the log are quarter-hourly), the clock change (668 solar rows, 23 price hours on 28 March), the joint
metering and the agreement's clipping, and the 50% start (where the log ends). The client confirms each when asked.

Last week's log (`dispatch_log_last_week.csv`) is the client's own planner's plan for last week, made with last
week's settings (10–90%, 92% each way, 50% at the start and end, a 20% reserve 17:00–21:00, import 00:00–06:00, a
25 MW cap); the planner keeps 1% inside the limits and never sells below the reserve before its hours end, so the
log runs from 21% to 89%. No candidate window or split is the log's or the sheet's, and every cap is below both
documents': a plan read off the files breaks the warranty and the export limit in every setting. The client says
why when asked: this week's window and split come from the battery's capacity test on Thursday 18 March, after last
week's plan was made, and the export limit is in a new phase of the substation works.

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
timestamps are ASCII in every locale. The audit regenerated the log with the client's current planner (it leaves
room for the midday solar and keeps a 1% buffer); the other files are byte-identical to the case before the audit.

## Rules

| Rule | Class | Tiers | What it requires |
|---|---|---|---|
| `complete_plan` | contractual | all | A row for each of the 668 local quarter-hours, and no power at 02:00–02:45 on 28 March (a time the clock change skips) |
| `soc_limits` | physical | all | SOC within `soc_window` of 40 MWh after every quarter, with the setting's efficiency on charge and on discharge |
| `power_limits` | physical | all | Charge and discharge each 0–20 MW, never both in one quarter; grid import at most 20 MW |
| `export_cap` | contractual | all | While discharging, solar + discharge − charge ≤ `export_cap` MW (hard: 30 MW from `works_end` 00:00) |
| `grid_charging_window` | contractual | medium, hard | Import from the grid (charging beyond solar) only in quarters starting in `import_window` |
| `end_soc` | contractual | all | Start at 50%, end the week at `end_soc` or more |
| `evening_reserve` | business policy (bendable) | medium, hard | SOC at least `reserve_pct` at every quarter boundary in `reserve_window`, every day |
| `dso_limit` | contractual | hard | On `dso_day` 18:00–21:00, while discharging, solar + discharge − charge ≤ `dso_mw` MW |
| `maintenance_outage` | physical | hard | No charge or discharge on `outage_day` from 08:00 to 20:00 |

SOC is checked to within 0.02 MWh (0.05% of capacity), so a plan rounded to two or three decimals is not
rejected for rounding alone. The file is read by what its columns say: the time column under any common name (else
the first column), the charge and discharge columns by a word in any of the five languages, comma or semicolon
separated (with decimal commas), timestamps with seconds, a `T`, a one-digit hour, a day-first (or month-first)
date or a UTC offset (converted to local time); a row at
02:00–02:45 on 28 March that moves nothing is ignored. A file that cannot be read, or a quarter given twice, is
fatal.

Quality is the battery's expected profit: per quarter, at the hour's forecast price, site export revenue
(price × 0.25 × min(net, export limit)) minus grid import cost, minus what the solar farm alone would have earned
(price × 0.25 × min(solar, export limit)), minus `degradation` EUR per MWh of charge plus discharge. The export
limit of a quarter is `export_cap`, 30 MW after the works end and `dso_mw` in the DSO's hours. The profit at the
week's actual prices (the forecast plus a daily bias and hourly noise) is reported as a metric only.

## Situations present

- **Stale documents.** The agreement says 30 MW and the log ran at 25; substation works cut the limit to 12–18 MW.
  In hard the works end early and the agreement is right again from a given day. The sheet's 84.6% round trip and
  5–95% window are not the client's model.
- **Units and the clock.** Prices are hourly but settlement is quarter-hourly. Clocks go forward on Sunday
  28 March, so the week has 668 quarters; power at 02:00–02:45 that day breaks `complete_plan`.
- **Clipped solar.** With a 12–18 MW export limit and 30 MWp of solar, much of the midday output is clipped unless
  the battery absorbs it; that energy is free, and the night fill must leave room for it.
- **Off-peak import window** (medium, hard). Charging from solar is allowed any time, from the grid only in the
  window. At the forecast prices a night charge rarely pays for its losses and degradation, so the window matters
  mostly for validity (GT.md, part 1).
- **Dated notices** (hard). Three changes for named hours that the documents do not show.
- **Pressure on a bendable rule** (medium, hard: the reserve; hard: the trading desk's push). Bending the reserve
  is worth 0.00–0.90 of the quality scale to the optimum on the public panel (nothing where a 15% reserve from 16:00 to
  20:00 does not bind); a plan at the reference's level gains nothing, since the cap is the best plan that keeps the rule.

Twelve clarification targets, each exactly one drawn parameter: `efficiency`, `soc_window`, `end_soc` and
`export_cap` in every tier (4); `grid_charging`, `reserve_level`, `reserve_hours` and `degradation` from medium
(8); `works_end`, `dso_day`, `dso_limit` and `maintenance_outage` in hard (12).

## Reference and baseline

The **reference** is the plan of greatest expected profit under the setting's rules, exactly (`optimum` in
case.py). The problem is a linear program with one state, the stored energy: a quarter's profit is a concave
piecewise-linear function of the energy it moves (charging costs the price plus degradation, except solar above
the export limit, which is free; discharging earns the price less degradation, up to the export limit), so the
best profit still to come is concave piecewise-linear too. A backward pass merges each quarter's segments into it
and cuts it at the SOC bounds; a forward pass picks each move. It is pure Python, takes about 0.05 s, and matches
scipy/HiGHS to 1e-9 EUR on the public settings of four worlds. No valid plan earns more (`objective_bound`), so
`quality_cap` is 1.0.

The **baseline** (quality 0) is the client's own way: its planner run with the setting's values
(requirements.md, "How we run the battery today"). Every day it fills up in the cheapest night quarters (inside the
import window when there is one), leaving room for the midday solar (always for the clipped part, the whole refill
when daylight is cheaper than night); sells in the dearest morning quarters (06:00–11:00); refills in the 16
cheapest sunny quarters, soaking up clipped solar; and sells in the dearest quarters from 15:00, each sale only above
the buy price over the round trip plus twice the degradation. It keeps 0.4 MWh inside the warranty window and above
the reserve, and never sells below the reserve until its hours are over, the morning sale included (so a cloudy
afternoon cannot leave the evening short). It is valid in every setting.

Reference / client's planner (EUR) and the scale's width per world seed:

| Setting | 20270322 | 1 | 2 | 3 |
|---|---|---|---|---|
| easy/s141 | 24,041 / 21,914 (8.8%) | 24,476 / 22,232 (9.2%) | 24,391 / 22,435 (8.0%) | 24,314 / 22,157 (8.9%) |
| easy/s70 | 24,046 / 21,566 (10.3%) | 24,584 / 22,142 (9.9%) | 24,438 / 22,242 (9.0%) | 24,428 / 22,177 (9.2%) |
| easy/s334 | 24,113 / 21,723 (9.9%) | 24,565 / 22,138 (9.9%) | 24,519 / 22,334 (8.9%) | 24,418 / 22,258 (8.8%) |
| medium/s141 | 19,115 / 17,344 (9.3%) | 19,549 / 17,708 (9.4%) | 19,324 / 17,767 (8.1%) | 19,390 / 17,762 (8.4%) |
| medium/s70 | 14,476 / 13,027 (10.0%) | 14,970 / 13,248 (11.5%) | 14,864 / 13,308 (10.5%) | 15,138 / 13,650 (9.8%) |
| medium/s334 | 9,387 / 8,103 (13.7%) | 9,918 / 8,215 (17.2%) | 9,782 / 8,305 (15.1%) | 9,862 / 8,278 (16.1%) |
| hard/s141 | 17,822 / 16,355 (8.2%) | 17,989 / 15,885 (11.7%) | 18,028 / 15,254 (15.4%) | 17,724 / 15,733 (11.2%) |
| hard/s70 | 12,412 / 10,995 (11.4%) | 13,034 / 11,387 (12.6%) | 12,901 / 11,317 (12.3%) | 13,008 / 11,586 (10.9%) |
| hard/s334 | 7,781 / 6,974 (10.4%) | 8,222 / 6,752 (17.9%) | 8,051 / 7,157 (11.1%) | 8,127 / 6,995 (13.9%) |

Over the audit's 45 settings per world (panel and combinations) the scale is 6.7–29.4% wide on world seeds
20270322 and 1–3; on the round 2026-11 seeds (108807, 519122, 904685) 8.1–16.1%.

### Literal solution

`literal_solution` is the request done as written from the files on hand: the optimum on the forecast with the
spec sheet's manufacturer window (5–95%), its 84.6% round trip split evenly (92% each way), the agreement's 30 MW
export and import at any hour, back at the 50% the week starts at, with no reserve, no degradation charge and no
notice. It is the same plan in every setting and is invalid in all 9 public settings, as delivered and with the
bendable reserve relaxed: it breaks `export_cap` and `soc_limits` everywhere (and `end_soc` in some). Its next
readings (the sheet's 84.6% all on charge, no end level, the log's 10–90% window or the 21–89% it runs in, the log's
import window) are invalid everywhere too, on world seeds 20270322 and 1–3 (GT.md, part 2).

## Ground truth audit

`fdebench2 audit-case` on the public world: 45 settings (15 per tier). Details in [GT.md](../../GT.md).

- **Facts.** Twelve targets, each one drawn parameter (`param:`); all twelve bite in every tier where they are in
  force. Bites per tier on the public world: `efficiency` 15/13/11 of 15 (easy/medium/hard), `soc_window` 15/14/13,
  `end_soc` 9/14/14, `export_cap` 15/15/15, `grid_charging` 6/7 (medium/hard, the one warning: fewer than half),
  `reserve_level` 14/11, `reserve_hours` 14/15, `degradation` 15/15, `works_end` 11, `dso_day` 15, `dso_limit` 9,
  `maintenance_outage` 15. Removed as targets and kept as context: `quarter_settlement`, `dst_clock`,
  `profit_scoring`, the start half of `start_end_soc`, easy's grid import; split: `evening_reserve` into
  `reserve_level` and `reserve_hours`, `dso_limit` into `dso_day` and `dso_limit`.
- **Shortcuts.** 22, all closed in every setting on world seeds 20270322 and 1–3 except two, both listed in
  `validate.OPEN_AUDIT_FINDINGS`: `solar_only` (never draw from the grid, every other fact right), open in 19–20 of 45
  settings because a night charge rarely pays at the forecast prices (and in all six medium and hard settings of round
  2026-11); and `planner_two_changes` (the client's planner without its 1% buffer and its all-day reserve), up to 0.57
  and above 0.5 in 2–3 of the 30 medium and hard settings, where the morning sale into the reserve pays most. Both
  need every other client fact. Copying the client's planner and changing one thing scores at most 0.46 (the reserve
  held only through its hours), 0.42 (no buffer), 0.30 (selling the reserve after its hours), 0.10 (the night fill as
  before the cut). Storing only the clipped solar, or one day's plan repeated, earns nothing. The literal plan with
  each rule it breaks kept is invalid everywhere.
- **Value of asking.** `robust_solution` (a linear program valid under every combination of the tier's pools)
  earns 0.089 / 0.021 / 0.000 in easy / medium / hard on the public world (0.06–0.07 / 0.02 / 0.00 on world seeds
  1–3): asking is worth 0.91 / 0.98 / 1.00. Over all 81 easy combinations the hedge earns 0.186 (asking worth
  0.81), more than any other plan that plans for a subset of the candidates; the audit's 15 easy settings are an
  unlucky sample for it. In medium and hard no partial hedge or guess found earns more than 0.075 / 0.010 over 150
  sampled combinations. Without the client's values, hedging costs more than the optimizer gains over the client's
  own planner. Searched alternatives: GT.md, part 4.
- **Reference and bounds.** The reference is the proven optimum (best known = reference = bound, gap under 1e-5);
  `quality_cap` 1.0.
- **Diagnostics.** `diagnose()` reads every fact from the plan's numbers. It separates the reference from every
  biting ablation, calls the best known plan enforced everywhere (0 false negatives in 360 verdicts per world) and
  has no cross flags on world seeds 20270322 and 1–3. Five other correct plans (with margins, another solver, the
  client's planner without its habits, rounded) get no False on a valid plan; the sheet's round trip all on one
  side, the discharge efficiency applied the wrong way and the log's 21–89% range are caught on their own target in
  every setting (GT.md, part 5).
- **Round 2026-11** (rule seeds 108807, 519122, 904685, nine settings): reference and baseline valid, scale 8.1–16.1%
  wide, literal invalid as delivered and with the reserve relaxed.

## Notes

- Synthetic or unverified. Prices, solar output, the export amendments, the efficiencies, degradation costs, import
  windows, reserve policies and the dated notices are design choices, not measured values.
- The solar profile is idealized: it reaches the full 30 MWp DC rating, and solar noon sits at 12:45 local time
  (13:45 after the clock change), earlier than at a Spanish site on CET.
- Open design questions from the case review (a daily program deliverable, grounding of the contractual rules in
  documents, the task type) are in REVIEW.md.
