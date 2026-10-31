# Procurement Specialist — `manufacturing/procurement_specialist`

A contract manufacturer that assembles two control-board models (B100, and B200 with a display) asks the agent
to plan eight weeks of purchase orders (W1 = week of 23 November 2026 to W8) for about two dozen components,
"so production doesn't stop and we don't overspend". The deliverable is `orders.csv`
(`order_week,component_id,supplier_id,quantity`). The plan is simulated over W1–W10 against the production
plan. The setting is country-neutral apart from one fact: the budget is in the local currency (KRW) and one
supplier quotes in USD, converted at a fixed planning rate.

A setting is a tier and a rule seed: the tier decides which of the client's rules are in force this round, the
rule seed draws their parameters (planning rate, safety stock, share cap, quality hold) from candidate pools. The
public panel has three rule seeds (42, 3, 78), so nine public ground truths; any other rule seed is a private draw
of the same candidates. **The agent sees the same request and the same data in every setting** (the validator
checks that its prompt and workspace are byte-identical); what changes is the hidden requirements, which the
simulated client answers from, and the evaluator. The engagement knobs (full spec vs. clarify first, client
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
| **Domain facts** | Demand = boards × `qty_per_board` (gross-to-net per week); lead time = `lead_time_days` / 5 rounded up, in whole weeks; list prices (`unit_price`, with the approved C01/S03 increase from the price email), S04 in USD at the planning rate; MOQ per order line; only `approved` suppliers; a hard monthly budget by the month of the order week (November binds); resistor stock in reels; safety stock for critical parts; one supplier on quality hold; dual sourcing of critical parts (company habit) | All-units price breaks per order line; lead times in business days, W5 and W6 have 4 (Christmas, New Year's Day) | Each supplier is one or two weeks late with hidden probabilities (estimate them from the history; 1–7 days after the promised Monday = one week, 8–14 = two); deliveries late independently; open orders on time. Allocation caps per month. Engineering change C04 → C25 from W6: C04 left at the end of W5 is scrapped at standard cost, C25 has no stock, is critical and must be dual-sourced; C04 needs neither. A longer quality hold (to W5), which may fall on the main semiconductor maker S03 |
| **What the requirements put out of scope** | "Plan at list prices", "treat lead times as whole weeks and ignore holidays", "the flash change is not released this round: C04 in all ten weeks, no C25", "do not use the delivery history or the allocations: suppliers deliver on time and confirm everything" | The flash change and the history/allocations, as in easy | Nothing |
| **Rules** | `moq`, `quality_hold` (physical); `approved_vendor`, `budget_cap` (contractual); `dual_source_critical` (business policy, bendable) | Same | + `allocation_cap` (physical) |
| **Quality (lower is better)** | Purchases + 0.5% of standard cost per piece held per week + 5× standard cost per piece-week of backlog + 1.5× standard cost per piece-week below safety stock (critical parts, weeks in use) | Same formula; purchases at the break each line reaches | Holding, backlog, shortfall and C04 scrap become exact expectations over the true lateness distribution; purchases are paid either way |
| **Clarification targets** | 12: BOM explosion, round scope (list prices, no flash change, no lateness/allocation), lead time in weeks, USD rate, MOQ per line, quality hold, budget month, AVL status, reels, safety stock, dual sourcing, cost model | 13: lead time becomes business days, round scope without the pricing part; + price breaks | 16: + supplier lateness, allocation, engineering change, expected-cost scoring (no round-scope target) |
| **What it tests** | MRP netting from a BOM, units traps, cash-constrained timing (defer November orders to faster, dearer suppliers), when to bend a habit, reading which data is in scope | Lot sizing against price breaks under a cash cap, calendar arithmetic | Estimating lateness from small samples, safety lead time vs. cost, splitting volume around allocation, use-up planning for a phased-out part |

## Rule parameters: what a rule seed draws

Each parameter is drawn on its own from its pool in the setting's tier (`params:` in case.yaml). The old rule sets
A, B and C are inside the pools: A = (1,380, 1, 80%, S07 to W3), B = (1,450, 1.5, 70%, S05 to W4), C = (1,320, 0.5,
90%, S01 to W4); a rule seed now combines them freely, so the strictest values no longer come together.

| Parameter | easy | medium | hard | What it changes |
|---|---|---|---|---|
| `usd_krw`: planning rate for S04's USD quotes (KRW per USD) | 1,380 · 1,450 · 1,320 · 1,500 | same | 1,380 | Pacific Parts' prices in the purchases and in the monthly budget; at 1,320 S04 is the cheapest source of the MCU and DRAM, at 1,500 it barely is |
| `safety_weeks`: safety stock = this × average weekly demand of a critical part, rounded up | 1 · 1.5 · 0.5 | same | same | how much stock the plan builds and keeps; the shortfall cost of a plan made for less |
| `max_share`: dual sourcing, the most one supplier may get of a critical part's ordered pieces | 80% · 70% · 90% | same | 80% | how much volume moves to dearer second sources |
| `quality_hold`: supplier on quality hold and the last week whose arrivals from it are rejected | S07 to W3 · S05 to W4 · S01 to W4 | same | S03 to W5 · S05 to W5 · S01 to W5 | *which* parts lose their cheapest early source: S07 cheap passives and mechanics, S05 the main PCB source, S01 the main connector source and a frequent second source for ICs, S03 the main semiconductor maker (also on allocation and a C25 source) |

Derived for the texts (`derive_params`): `hold_supplier` (the supplier's name in each locale) and `hold_until` (the
week). `admissible()` rejects a hold that ends before the supplier's goods could arrive at all (S03 and S05 quote
11–13 business days, so nothing of theirs arrives before W4); every candidate in the pools passes, the hook guards
edits to them.

Why the pools look like this (all measured with the validator's binding test: from the first public seed's
setting, change one parameter; it binds if that setting's reference breaks a rule, its objective moves by 1%, or the
other setting's reference beats it by 1%):

- **The hold week is not a parameter of its own.** In hard, moving the end of an S03 hold from W4 to W5 changed
  nothing (the November budget already pushes S03's orders to W3, arriving W6), so supplier and week are drawn as one
  value. In hard, `quality_hold` S03 to W5 → S01 to W5 makes the reference invalid on world seeds 20261123, 1, 2
  and 3.
- **The planning rate and the share cap are fixed in hard.** With late deliveries, the safety lead time and the
  allocation, S04 carries 4–9% of the hard reference's purchases, so 1,320 → 1,550 moved it 0.6–1.4% depending on the
  world, and a 90% cap left the hard reference valid under 70% on two of four worlds. In medium they bind: from the
  first public seed (1,320), 1,450 and 1,500 break the budget on worlds 20261123, 1 and 3 and move the reference
  +1.31% and +1.82% on world 2 (1,380 moves it only 0.6–0.7%, and breaks the budget on world 3); from 90%, both 80%
  and 70% make the reference invalid on all four worlds. 1,500 (a cautious treasury rate) was added because, with the
  first version's reference, 1,320 → 1,450 moved the medium reference by only 0.85% on the case world.
- **Safety stock** binds everywhere: in hard, 1 → 1.5 weeks moves the reference by +8.3% (world 2) to +11.9% (world
  20261123).
- **A 60% share cap** was tried for hard and left out: the reference's second-source step moves whole lines and
  cannot reach 60% for C02 and C25 in most combinations.
- **No budget parameter.** A finance reserve (0, 5 or 10% of every month's budget kept back) was tried: it moved the
  hard reference by 0–1.3% (the reference defers to fast suppliers at little extra cost), so it was dropped. The
  budget is data; it is calibrated over the pools instead (below), so that November binds in every combination.

### Public panel (`rule_seeds: [42, 3, 78]`)

Chosen so that every candidate shows up at least once in each tier (except one of the four planning rates, as three
seeds can show only three), and so that the first seed (42), on which the validator tests binding, draws values from
which a change binds on every world checked: 1,320 and 90% in medium, S03 to W5 in hard.

| Setting | Drawn values | Reference objective (M KRW) | Purchases / holding / backlog / shortfall / scrap (M KRW) | November spend vs. unconstrained (M KRW, cap 115) | Baseline objective (M KRW, ratio) | Bending `dual_source_critical` |
|---|---|---|---|---|---|---|
| easy/s42 | `{"usd_krw": 1320, "safety_weeks": 1, "max_share": 90, "quality_hold": "S07-W3"}` | 503.68 | 496.6 / 7.1 / 0 / 0 / 0 | 102.0 vs. 137.5 | 551.87 (1.096) | −2.6% |
| easy/s3 | `{"usd_krw": 1450, "safety_weeks": 1.5, "max_share": 80, "quality_hold": "S01-W4"}` | 564.63 | 556.1 / 8.6 / 0 / 0 / 0 | 101.0 vs. 222.8 | 620.81 (1.100) | −1.4% |
| easy/s78 | `{"usd_krw": 1380, "safety_weeks": 0.5, "max_share": 70, "quality_hold": "S05-W4"}` | 480.69 | 474.1 / 6.6 / 0 / 0 / 0 | 113.9 vs. 132.4 | 506.56 (1.054) | −3.6% |
| medium/s42 | `{"usd_krw": 1320, "safety_weeks": 1, "max_share": 90, "quality_hold": "S07-W3"}` | 504.47 | 497.4 / 7.1 / 0 / 0 / 0 | 111.9 vs. 180.7 | 547.25 (1.085) | −0.8% |
| medium/s3 | `{"usd_krw": 1450, "safety_weeks": 1.5, "max_share": 80, "quality_hold": "S01-W4"}` | 556.57 | 548.3 / 8.3 / 0 / 0 / 0 | 98.6 vs. 226.1 | 591.18 (1.062) | −0.2% |
| medium/s78 | `{"usd_krw": 1380, "safety_weeks": 0.5, "max_share": 70, "quality_hold": "S05-W4"}` | 479.39 | 473.0 / 6.4 / 0 / 0 / 0 | 106.5 vs. 137.2 | 504.91 (1.053) | −3.3% |
| hard/s42 | `{"usd_krw": 1380, "safety_weeks": 1, "max_share": 80, "quality_hold": "S03-W5"}` | 557.84 | 530.0 / 8.9 / 7.9 / 11.0 / 0.0 | 110.8 vs. 273.7 | 644.58 (1.156) | −0.2% |
| hard/s3 | `{"usd_krw": 1380, "safety_weeks": 1.5, "max_share": 80, "quality_hold": "S01-W5"}` | 608.79 | 595.5 / 9.1 / 2.4 / 1.8 / 0.0 | 109.9 vs. 349.7 | 716.46 (1.177) | 0% |
| hard/s78 | `{"usd_krw": 1380, "safety_weeks": 0.5, "max_share": 80, "quality_hold": "S05-W5"}` | 514.19 | 495.4 / 7.5 / 6.7 / 4.6 / 0.0 | 106.7 vs. 297.2 | 708.49 (1.378) | −0.3% |

Means per tier: reference 516.3 (easy), 513.5 (medium), 560.3 (hard); baseline 559.7, 547.8, 689.8. "Unconstrained"
is the default planner (second-source step, two-week lots, no trim) without the budget step, the plan the budget is
calibrated on. Bending is the best plan of the netting planner without the second-source step (two- or one-week lots,
each trim option), against the reference: 1.4–3.6% in easy, 0.2–3.3% in medium, at most 0.3% in hard, where
deferrals, allocation and the hold already spread the volume.

### What an agent must ask

The data never states the parameters, so the client has to be asked, in every tier:

- the planning rate for S04's dollar quotes (target `usd_planning_rate`);
- the safety stock rule for critical parts, in weeks of average demand (`safety_stock`);
- the dual-sourcing habit and its cap, which the client lets bend if it saves real money (`dual_source_critical`);
- which supplier is on quality hold and up to which week (`quality_hold`); with S03 on hold (hard), the client adds
  that the hold covers its allocated MCU and DRAM and the new C25 too.

And, independent of the rule seed: the BOM explosion, units (reels), MOQ per line, the budget month, approved status
only, the cost model, and the round's scope (easy and medium) or the lateness, allocation, engineering change and
expected-cost scoring (hard), as listed in the tiers table.

## Reference and baseline numbers (seed 20261123)

The reference is a time-phased MRP per part: it nets stock and open orders against the exploded demand and orders
from the cheapest supplier that still arrives in time, as late as possible, covering two weeks (or one) and rounding
up to a price break when the break costs less in total (medium/hard). Critical parts then move whole lines to a
second source until the share cap holds. Leftover stock is trimmed, latest line first: a line is cut by what the part
holds above its target until its last week, or replaced in the same week by a small-MOQ supplier sized to what is
still missing, when that lowers the part's cost. If a month is over budget, whole lines move to the first week of the
next month with a supplier that still arrives in time, cheapest extra cost per KRW deferred first, each re-sized to
what the part still needs from its new arrival week (so the phased-out C04 deferred to Express Parts Korea (S09) in
hard is 1,400, not the 4,100 of the S03 MOQ it replaced); if no line can move in time, a line moves late (the part
waits for it); January's excess is pulled into W6 where December has room; and if nothing can move, a line is cut
(accepting shortfall or backlog), so that the reference is valid whatever a rule seed draws. In hard it plans one
week of safety lead time for every supplier whose smoothed late rate in the history is above 5% and respects the
allocation. It keeps the cheapest valid plan, by its own cost view, of fifteen variants: the netting planner with
and without the second-source step and with two- or one-week lots, plus a lot-for-lot planner that splits every order
of a critical part with a second source at the share cap (the client's quota habit, which beats whole-line second
sourcing when the second source is dear), each with the trim before and after the budget step, only after it
(trimming first can leave the budget step only dearer deferrals), or not at all. It uses only what the agent can see:
lateness estimates from the history, never the true rates.

The baseline (`baseline_solution`, quality 0 on the normalized scale) is what the client does today without an
engineer: the ERP's plain MRP run and the buyer's fixes. Every part is ordered lot for lot (each order covers the
first week short of stock or safety stock, at least the MOQ) from the cheapest approved supplier that still delivers
in time, as late as its lead time allows, at list prices and on the promised dates (no price breaks, no use of the
delivery history). Critical parts follow a quota arrangement: every order is split with the cheapest other supplier
so that neither gets more than the share cap. A month over budget moves whole lines to the next month as the
reference does, and January's lines are pulled into W6 (cut as the reference cuts when December has no room).

Budget in the data: November 115 M, December 475 M, January 85 M KRW. It is calibrated over every admissible
combination of the candidate pools in every tier (225 combinations), on the unconstrained plans: November is 95% of
the least any combination spends there, rounded down to 5 M, so it binds in every combination a rule seed can draw;
December has 5% headroom over the most any combination spends there plus what it spends in November above the cap;
January 5% over the most any combination spends there. Allocation: C01 6,500, C03 9,000, C06 3,500 per month (60% of
the peak month of the unconstrained hard plan for the calibration values 1,380 / 1 / 80% / S07 to W3, the old rule
set A).

Over all 225 combinations on this world the reference and the baseline are valid, the baseline is worse (ratio
1.045–1.136 in easy, 1.032–1.122 in medium, 1.156–1.410 in hard) and the unconstrained plan overspends November. The
reference sometimes has to move a November line late (the part waits a week) and in a few hard combinations
December binds too. The same holds on world seeds 1, 2 and 3 for all 225 combinations each: the reference and the
baseline are valid and the baseline is worse by at least 3.5% / 2.5% / 12.8% (world 1, easy / medium / hard), 1.2% /
1.0% / 14.9% (world 2) and 1.1% / 1.2% / 16.9% (world 3). The narrowest gaps are combinations with Kowon Passive
(S07) on hold to W3 and 0.5 weeks of safety stock, where the reference's best plan is the quota planner with the trim
after the budget step (see REVIEW.md, Rule seeds). Validation covers the public panel on world seeds 1–3.

The local-search headroom of the first version (a first-improvement search beat the greedy reference by 3–11%, see
REVIEW.md F2) was measured on the old rule sets and the old reference and has not been redone.

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
- Synthetic or unverified. All prices, MOQs, lead times, lateness rates, allocations, budgets and the four
  planning rates are synthetic. The cost weights (0.5% holding per week, about 26% a year, in the usual 20–30%
  range for carrying cost; 5× standard cost per piece-week of backlog; 1.5× for shortfall; scrap at standard
  cost) are design choices, not measured values. The two short weeks assume Christmas and New Year's Day are
  non-working days, as in most countries that use the Gregorian calendar; other plants may differ.
- Lateness is a property of the supplier only (not of the part or the season), at most two weeks, and independent
  across deliveries; real suppliers have correlated delays (a shared shipment, a plant shutdown). The history has
  10–28 deliveries per supplier, so some estimates are far from the truth: S05 (10 deliveries) looks late 32% of the
  time against a true 15%. True late rates at this seed run from 2% (S09, the express broker) to 37% (S04, overseas)
  and 35% (S03, the allocated semiconductor maker).
- `validate-case` checks every public setting: deterministic data in five locales, the same agent view in all nine,
  the reference at quality 1.0, a valid baseline worse than the reference, one deliverable per rule of the setting
  that breaks only that rule, and that every parameter binds (on this world and on world seeds 1–3).

## Relationship to the source assignment

This is a synthetic adaptation of the Apex Manufacturing take-home, not a reproduction of its data or a submission to that assignment. Both use a production schedule, BOM, shared components, stock, existing purchase orders, supplier eligibility, lead times and sourcing rules. Here the output remains the benchmark's eight-week `orders.csv`; the original assignment calls for a general-purpose program that writes purchase orders and alerts to scenario databases. The email is a new fictional commercial event, not a document from the assignment.

The source assignment also includes dated management memos, certification, concentration history, approvals, hazardous handling and expedited freight. Those are not modeled by this extension: the existing quality hold and dual-source rule are only simplified analogues. The simulated client does not receive later emails during a run, issue purchase orders, or request approval. The exercise tests incorporating a dated approved price revision into a static plan and budget, rather than autonomous event handling.
