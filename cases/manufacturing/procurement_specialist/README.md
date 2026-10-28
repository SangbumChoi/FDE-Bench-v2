# Procurement Specialist — `manufacturing/procurement_specialist`

A contract manufacturer that assembles two control-board models (B100, and B200 with a display) asks the agent
to plan eight weeks of purchase orders (W1 = week of 23 November 2026 to W8) for about two dozen components,
"so production doesn't stop and we don't overspend". The deliverable is `orders.csv`
(`order_week,component_id,supplier_id,quantity`). The plan is simulated over W1–W10 against the production
plan. The setting is country-neutral apart from one fact: the budget is in the local currency (KRW) and one
supplier quotes in USD, converted at a fixed planning rate.

The case has nine ground truths: three tiers × three rule sets. **The agent sees the same request and the same
data in all nine** (the validator checks that its prompt and workspace are byte-identical); what changes is
which of the client's rules are in force this round and their parameters, which the simulated client answers
from the hidden requirements, and the evaluator. The engagement knobs (full spec vs. clarify first, client
persona, data noise, events) apply on top, as for every case (see [cases/README.md](../../README.md)).

## Data (the same in every setting)

`components` (24 parts plus the new flash C25, `critical` flag, standard cost), `production_plan` (boards per
model, W1–W10), `bom` (with `valid_from_week` / `valid_to_week`: C04 in W1–W5, C25 in W6–W10), `inventory`
(resistors in reels of 5,000), `open_orders`, `supplier_quotes.xlsx` (`currency`, `unit_price`, `moq`, two
all-units price breaks, `lead_time_days` in business days; a `suppliers` sheet), `approved_vendors`, `budget`
(monthly caps), `delivery_history` (188 past deliveries, promised vs. received date) and `allocations` (monthly
caps for S03/C01, S03/C03, S08/C06). The request mentions the history, the allocation notice and the planned
flash change, so every tier sees them.

## Tiers: which rules apply

| | easy | medium | hard |
|---|---|---|---|
| **What is in force** | The MRP core | + commercial and calendar terms | + supply uncertainty and the engineering change |
| **Domain facts** | Demand = boards × `qty_per_board` (gross-to-net per week); lead time = `lead_time_days` / 5 rounded up, in whole weeks; list prices (`unit_price`), S04 in USD at the planning rate; MOQ per order line; only `approved` suppliers; a hard monthly budget by the month of the order week (November binds); resistor stock in reels; safety stock for critical parts; one supplier on quality hold; dual sourcing of critical parts (company habit) | All-units price breaks per order line; lead times in business days, W5 and W6 have 4 (Christmas, New Year's Day) | Each supplier is one or two weeks late with hidden probabilities (estimate them from the history; 1–7 days after the promised Monday = one week, 8–14 = two); deliveries late independently; open orders on time. Allocation caps per month. Engineering change C04 → C25 from W6: C04 left at the end of W5 is scrapped at standard cost, C25 has no stock, is critical and must be dual-sourced; C04 needs neither |
| **What the requirements put out of scope** | "Plan at list prices", "treat lead times as whole weeks and ignore holidays", "the flash change is not released this round: C04 in all ten weeks, no C25", "do not use the delivery history or the allocations: suppliers deliver on time and confirm everything" | The flash change and the history/allocations, as in easy | Nothing |
| **Rules** | `moq`, `quality_hold` (physical); `approved_vendor`, `budget_cap` (contractual); `dual_source_critical` (business policy, bendable) | Same | + `allocation_cap` (physical) |
| **Quality (lower is better)** | Purchases + 0.5% of standard cost per piece held per week + 5× standard cost per piece-week of backlog + 1.5× standard cost per piece-week below safety stock (critical parts, weeks in use) | Same formula; purchases at the break each line reaches | Holding, backlog, shortfall and C04 scrap become exact expectations over the true lateness distribution; purchases are paid either way |
| **Clarification targets** | 12: BOM explosion, round scope (list prices, no flash change, no lateness/allocation), lead time in weeks, USD rate, MOQ per line, quality hold, budget month, AVL status, reels, safety stock, dual sourcing, cost model | 13: lead time becomes business days, round scope without the pricing part; + price breaks | 16: + supplier lateness, allocation, engineering change, expected-cost scoring (no round-scope target) |
| **What it tests** | MRP netting from a BOM, units traps, cash-constrained timing (defer November orders to faster, dearer suppliers), when to bend a habit, reading which data is in scope | Lot sizing against price breaks under a cash cap, calendar arithmetic | Estimating lateness from small samples, safety lead time vs. cost, splitting volume around allocation, use-up planning for a phased-out part |

## Rule sets: the client's parameters

| Parameter | A | B | C |
|---|---|---|---|
| `usd_krw`: planning rate for S04's USD quotes | 1,380 | 1,450 | 1,320 |
| `safety_weeks`: safety stock = this × average weekly demand (rounded up) | 1 | 1.5 | 0.5 |
| `max_share`: dual sourcing, most any one supplier may get of a critical part | 80% | 70% | 90% |
| `hold_supplier` / `hold_until`: supplier on quality hold, lots due in W1..W`hold_until` rejected | Kowon Passive (S07), W3 | Seoul PCB Tech (S05), W4 | Hanbit Electronics (S01), W4 |

The quality hold is the non-nested parameter: it changes *which* parts and suppliers a rule hits (S07 cheap
passives and mechanics; S05 the main PCB source; S01 the main connector source and a frequent second source for
ICs). Safety weeks and the share cap move the objective by several percent. In every tier each rule set's
reference is **invalid** under both other rule sets (18 of 18 pairs: mostly `quality_hold`, also `budget_cap`
when the planning rate is higher and `dual_source_critical` under B's 70% cap), so the three ground truths are
distinct.

## Reference numbers (seed 20261123)

The reference is a time-phased MRP per part: it nets stock and open orders against the exploded demand and orders
from the cheapest supplier that still arrives in time, as late as possible, covering two weeks and rounding up to a
price break when the break costs less in total (medium/hard). Critical parts then move whole lines to a second
source until the share cap holds. If November is over budget, whole lines move to W3 with a supplier that still
arrives in time, starting with the cheapest extra cost per KRW deferred. In hard it plans one week of safety lead
time for every supplier whose smoothed late rate in the history is above 5%, respects the allocation, and keeps the
cheaper valid plan of the planner with and without the second-source step. It uses only what the agent can see:
lateness estimates from the history, never the true rates.

Budget in the data: November 125 M, December 525 M, January 85 M KRW, calibrated against all nine settings
(November lies between the most any setting can defer out of November and the least any setting would spend there
unconstrained, so it binds in all nine; December and January have 5% headroom). Allocation: C01 6,500, C03 9,000,
C06 3,500 per month (60% of the unconstrained hard/A reference's peak month).

| Setting | Reference objective (M KRW) | Purchases / holding / backlog / shortfall / scrap (M KRW) | November spend vs. unconstrained (M KRW) | Bending `dual_source_critical` (planner without the second-source step) | Headroom: local search, quality of a better plan | Bending on top of the local-search plan |
|---|---|---|---|---|---|---|
| easy/A | 515.25 | 508.1 / 7.2 / 0 / 0 / 0 | 123.2 vs. 139.4 | −3.8% | 495.73, 1.039 | 0.0% |
| easy/B | 600.14 | 590.9 / 9.3 / 0 / 0 / 0 | 115.7 vs. 226.1 | −4.9% | 566.83, 1.059 | −0.3% |
| easy/C | 489.30 | 483.1 / 6.2 / 0 / 0 / 0 | 124.2 vs. 125.1 | −4.3% | 464.02, 1.054 | −0.3% |
| **easy mean** | **534.90** | | | **−4.3%** | **1.051** | **−0.2%** |
| medium/A | 521.22 | 513.5 / 7.7 / 0 / 0 / 0 | 123.2 vs. 184.5 | −3.8% | 490.18, 1.063 | 0.0% |
| medium/B | 600.16 | 590.9 / 9.3 / 0 / 0 / 0 | 115.7 vs. 231.1 | −3.9% | 548.92, 1.093 | −0.6% |
| medium/C | 490.10 | 483.6 / 6.5 / 0 / 0 / 0 | 124.2 vs. 128.1 | −4.3% | 458.13, 1.070 | −0.5% |
| **medium mean** | **537.16** | | | **−4.0%** | **1.075** | **−0.3%** |
| hard/A | 588.61 | 553.7 / 9.5 / 11.1 / 10.5 / 3.8 | 119.7 vs. 330.9 | 0% (reference already skips the step) | 531.21, 1.108 | 0.0% |
| hard/B | 635.41 | 602.0 / 10.6 / 8.4 / 10.6 / 3.8 | 124.3 vs. 365.9 | 0% (reference already skips the step) | 579.46, 1.097 | −0.1% |
| hard/C | 548.21 | 515.7 / 8.7 / 14.8 / 5.3 / 3.8 | 122.4 vs. 290.5 | 0% (the planner without the step is 0.7% dearer) | 495.70, 1.106 | 0.0% |
| **hard mean** | **590.74** | | | **0%** | **1.104** | **−0.0%** |

Bending the dual-sourcing habit pays about 4% in easy and medium for the reference planner. In hard the habit is
almost free: the November deferrals and the allocation caps already push volume to second suppliers, so the
planner without the second-source step is valid (A, B) and the reference keeps it; second sources also hedge
lateness. The headroom column is a first-improvement local search from the reference (quantity ±, a price break,
week ±1/±2, supplier switch, drop line) under all rules of the setting, run until no move improves; it shows
where a careful agent can beat the reference: consolidating lines onto price breaks (medium) and, in hard,
buying C04 exactly to use-up and trading safety lead time against the November cap. All numbers come from
`case.py` (`_reference`, `simulate`); the local search is an analysis script, not part of the case. Seeds 1–8
build valid worlds, references, violating examples and distinct rule sets in all nine settings (the November cap
binds in 6–9 of the 9 settings depending on the seed).

### How the expectation is computed (hard)

Lateness is at most two weeks, so the net position of a part at the end of week w is certain except for the
deliveries promised for weeks w−1 and w. For each week the scorer enumerates the joint outcomes of those
deliveries (at most two per supplier quoting the part, so at most 2^8 states) and takes the expected holding,
backlog, shortfall and scrap. The result is exact and deterministic; nothing is sampled.

## Notes

- Practice behind the facts. All-units quantity discounts per order line, MOQs set by full reels or trays,
  business-day lead times and allocation in shortage markets are standard procurement practice. During the
  2021–2023 component shortage, suppliers put parts on allocation, shipped only part of what was ordered and
  stretched lead times (Ultra Librarian, "Electronic Component Allocation & Lead Times", 2022 and 2023 updates;
  EMSNow, "Eight commonly used terms when buying electronic components"). Engineering changes with date or
  use-up effectivity, and the excess and obsolete stock they create, are described in Oracle's MRP documentation
  ("Engineering change planning", use-up date) and in APICS/CPIM material on engineering change management.
  Stochastic supplier lead times and the trade-off between safety lead time and safety stock follow e.g. Humair,
  Ruark, Tomlin and Willems, "Incorporating Stochastic Lead Times Into the Guaranteed Service Model of Safety
  Stock Optimization", Interfaces 43(5), 2013, and Ben-Ammar, Dolgui et al. on multi-period supply planning under
  stochastic lead times (expected-cost models with discrete, bounded lead-time distributions).
- Synthetic or unverified. All prices, MOQs, lead times, lateness rates, allocations, budgets and the three
  planning rates are synthetic. The cost weights (0.5% holding per week, about 26% a year, in the usual 20–30%
  range for carrying cost; 5× standard cost per piece-week of backlog; 1.5× for shortfall; scrap at standard
  cost) are design choices, not measured values. The two short weeks assume Christmas and New Year's Day are
  non-working days, as in most countries that use the Gregorian calendar; other plants may differ.
- Lateness is a property of the supplier only (not of the part or the season), at most two weeks, and independent
  across deliveries; real suppliers have correlated delays (a shared shipment, a plant shutdown). The history has
  10–28 deliveries per supplier, so some estimates are far from the truth: S05 (10 deliveries) looks late 32% of the
  time against a true 15%. True late rates at this seed run from 2% (S09, the express broker) to 37% (S04, overseas)
  and 35% (S03, the allocated semiconductor maker).
- `validate-case` checks every setting: deterministic data in five locales, the same agent view in all nine, the
  reference at quality 1.0, one deliverable per rule of the setting that breaks only that rule, and distinct
  references across rule sets.
