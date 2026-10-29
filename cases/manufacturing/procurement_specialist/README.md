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
caps for S03/C01, S03/C03, S08/C06) and `supplier_price_email.txt` (the price notice below). The request mentions
the history, the allocation notice, the planned flash change and the price email, so every tier sees them.

## Supplier price email

A synthetic supplier notice (`supplier_price_email.txt`, dated 2026-11-20) approves a 20% increase to all C01/S03 quote tiers for orders placed in W4 or later. Earlier orders keep the quoted price. A further 5% increase is pending and is excluded. The order week determines the price for both purchase cost and monthly budget; open orders are unaffected. This adapts the distinction between approved and pending price changes from the ReflectionAI procurement scenarios.

## Tiers: which rules apply

| | easy | medium | hard |
|---|---|---|---|
| **What is in force** | The MRP core | + commercial and calendar terms | + supply uncertainty and the engineering change |
| **Domain facts** | Demand = boards × `qty_per_board` (gross-to-net per week); lead time = `lead_time_days` / 5 rounded up, in whole weeks; list prices (`unit_price`, with the approved C01/S03 increase from the price email), S04 in USD at the planning rate; MOQ per order line; only `approved` suppliers; a hard monthly budget by the month of the order week (November binds); resistor stock in reels; safety stock for critical parts; one supplier on quality hold; dual sourcing of critical parts (company habit) | All-units price breaks per order line; lead times in business days, W5 and W6 have 4 (Christmas, New Year's Day) | Each supplier is one or two weeks late with hidden probabilities (estimate them from the history; 1–7 days after the promised Monday = one week, 8–14 = two); deliveries late independently; open orders on time. Allocation caps per month. Engineering change C04 → C25 from W6: C04 left at the end of W5 is scrapped at standard cost, C25 has no stock, is critical and must be dual-sourced; C04 needs neither |
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

## Reference and baseline numbers (seed 20261123)

The reference is a time-phased MRP per part: it nets stock and open orders against the exploded demand and orders
from the cheapest supplier that still arrives in time, as late as possible, covering two weeks and rounding up to a
price break when the break costs less in total (medium/hard). Critical parts then move whole lines to a second
source until the share cap holds. If November is over budget, whole lines move to W3 with a supplier that still
arrives in time, starting with the cheapest extra cost per KRW deferred; a moved line is re-sized to what the part
still needs from its new arrival week (so the phased-out C04 deferred to Express Parts Korea (S09) in hard is 1,400,
not the 4,100 of the S03 MOQ it replaced). In hard it plans one week of safety lead time for every supplier whose
smoothed late rate in the history is above 5%, respects the allocation, and keeps the cheaper valid plan of the
planner with and without the second-source step. It uses only what the agent can see: lateness estimates from the
history, never the true rates.

The baseline (`baseline_solution`, quality 0 on the normalized scale) is what the client does today without an
engineer: the ERP's plain MRP run and the buyer's fixes. Every part is ordered lot for lot (each order covers the
first week short of stock or safety stock, at least the MOQ) from the cheapest approved supplier that still delivers
in time, as late as its lead time allows, at list prices and on the promised dates (no price breaks, no use of the
delivery history). Critical parts follow a quota arrangement: every order is split with the cheapest other supplier
so that neither gets more than the share cap. A month over budget moves whole lines to the next month as the
reference does, and January's lines are pulled into W6. It is valid in all nine settings (and on world seeds 1–8).

Budget in the data: November 125 M, December 490 M, January 85 M KRW, calibrated against all nine settings
(November lies between the most any setting can defer out of November and the least any setting would spend there
unconstrained, so it binds in all nine; December and January have 5% headroom over the references). Allocation: C01
6,500, C03 9,000, C06 3,500 per month (60% of the unconstrained hard/A reference's peak month).

| Setting | Reference objective (M KRW) | Purchases / holding / backlog / shortfall / scrap (M KRW) | November spend vs. unconstrained (M KRW) | Baseline objective (M KRW, ratio to the reference) | Bending `dual_source_critical` (planner without the second-source step) | Headroom: local search (objective, quality ratio, normalized quality) | Bending on top of the local-search plan |
|---|---|---|---|---|---|---|---|
| easy/A | 519.50 | 512.3 / 7.2 / 0 / 0 / 0 | 113.8 vs. 139.4 | 534.17 (1.028) | −4.4% | 495.39, 1.049, q 2.64 | −2.0% |
| easy/B | 579.32 | 570.6 / 8.7 / 0 / 0 / 0 | 118.6 vs. 226.1 | 644.90 (1.113) | −3.1% | 562.69, 1.030, q 1.25 | −0.6% |
| easy/C | 491.90 | 485.6 / 6.3 / 0 / 0 / 0 | 119.3 vs. 125.1 | 503.44 (1.023) | −4.8% | 458.59, 1.073, q 3.89 | −1.1% |
| **easy mean** | **530.24** | | | **560.83** | **−4.1%** | **1.050, q 2.59** | **−1.2%** |
| medium/A | 521.76 | 514.0 / 7.7 / 0 / 0 / 0 | 123.2 vs. 184.5 | 532.54 (1.021) | −4.5% | 488.94, 1.067, q 4.05 | −2.0% |
| medium/B | 582.57 | 573.9 / 8.7 / 0 / 0 / 0 | 98.7 vs. 231.1 | 615.89 (1.057) | −2.5% | 538.68, 1.081, q 2.32 | −0.9% |
| medium/C | 492.37 | 485.8 / 6.5 / 0 / 0 / 0 | 122.3 vs. 128.1 | 502.76 (1.021) | −4.7% | 451.89, 1.090, q 4.90 | −1.5% |
| **medium mean** | **532.23** | | | **550.40** | **−3.9%** | **1.079, q 3.75** | **−1.5%** |
| hard/A | 579.75 | 548.6 / 9.4 / 11.1 / 10.5 / 0.0 | 119.7 vs. 330.9 | 670.53 (1.157) | 0% (the reference is that plan) | 521.65, 1.111, q 1.64 | 0.0% |
| hard/B | 612.78 | 591.5 / 11.0 / 8.1 / 2.1 / 0.0 | 124.3 vs. 365.9 | 745.39 (1.216) | +2.0% (valid but dearer; the reference keeps the step) | 579.68, 1.057, q 1.25 | −0.3% |
| hard/C | 537.11 | 504.9 / 8.5 / 17.6 / 6.1 / 0.0 | 124.0 vs. 290.5 | 647.75 (1.206) | +0.7% (valid but dearer; the reference keeps the step) | 486.29, 1.104, q 1.46 | 0.0% |
| **hard mean** | **576.54** | | | **687.89** | **+0.9%** | **1.091, q 1.45** | **−0.1%** |

Bending the dual-sourcing habit pays about 4% in easy and medium for the reference planner. In hard the habit is
almost free: the November deferrals and the allocation caps already push volume to second suppliers, so the
planner without the second-source step is valid in all three rule sets and the reference keeps whichever is cheaper;
second sources also hedge lateness. The headroom column is a first-improvement local search from the reference
(quantity ±, to the MOQ or a price break, week ±1/±2, supplier switch, shifting quantity between lines, drop or add a
line) under all rules of the setting, scored with the true lateness rates, run until no move improves; it shows where
a careful agent can beat the reference: consolidating lines onto price breaks (medium) and, in hard, trading safety
lead time against the November cap. Normalized quality is (baseline − objective) / (baseline − reference): the
baseline is only 2–3% above the reference in easy and medium under rule sets A and C, so a plan a few percent better
than the reference scores far above the policies' quality cap of 1.5 there (see REVIEW.md, F2). On other world
seeds the gap can be narrower: over seeds 1–40, 15 of the 234 easy and medium settings have the baseline within 2%
of the reference (as close as 0.6%). All numbers come from `case.py` (`_reference`, `_baseline`, `simulate`); the
local search is an analysis script, not part of the case. Seeds 1–8 build valid worlds, references, baselines,
violating examples and distinct rule sets in all nine settings (the November cap binds in 6–9 of the 9 settings
depending on the seed). Of seeds 1–60, 30 and 49 do not build: the reference cannot second-source C06 in hard/A
(this predates the baseline and the `_defer` fix).

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
  reference at quality 1.0, a valid baseline worse than the reference, one deliverable per rule of the setting that
  breaks only that rule, and distinct references across rule sets.

## Relationship to the source assignment

This is a synthetic adaptation of the Apex Manufacturing take-home, not a reproduction of its data or a submission to that assignment. Both use a production schedule, BOM, shared components, stock, existing purchase orders, supplier eligibility, lead times and sourcing rules. Here the output remains the benchmark's eight-week `orders.csv`; the original assignment calls for a general-purpose program that writes purchase orders and alerts to scenario databases. The email is a new fictional commercial event, not a document from the assignment.

The source assignment also includes dated management memos, certification, concentration history, approvals, hazardous handling and expedited freight. Those are not modeled by this extension: the existing quality hold and dual-source rule are only simplified analogues. The simulated client does not receive later emails during a run, issue purchase orders, or request approval. The exercise tests incorporating a dated approved price revision into a static plan and budget, rather than autonomous event handling.
