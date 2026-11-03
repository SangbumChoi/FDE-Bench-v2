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
persona, data noise, events) apply on top, as for every case (see [cases/README.md](../../../../README.md)).

## Data (the same in every setting)

`components` (24 parts plus the new flash C25, `critical` flag, standard cost), `production_plan` (boards per
model, W1–W10), `bom` (with `valid_from_week` / `valid_to_week`: C04 in W1–W5, C25 in W6–W10), `inventory`
(resistors in reels of 5,000), `open_orders`, `supplier_quotes.xlsx` (`currency`, `unit_price`, `moq`, two
all-units price breaks, `lead_time_days` in business days; a `suppliers` sheet), `approved_vendors`, `budget`
(monthly caps), `delivery_history` (188 past deliveries, promised vs. received date), `allocations` (monthly caps
for S03/C01, S03/C03, S08/C06) and `mail/` (three `.eml` files: the e-mail thread with Nara Display, below). The
request mentions the history, the allocation notice, the planned flash change and the e-mail thread, so every tier
sees them.

## Supplier e-mail thread (Nara Display)

`mail/` holds a thread of three localized e-mails (`2026-11-18_nara_display_price_notice.eml` and two replies),
written in the client's language, from the supplier's own domain (`naradisplay.example`) and the client's purchasing
(`boardassembly.example`):

1. Nara Display (S08), the main source of the display module C06, the costliest part (14,800 KRW, about a third of the
   purchases), raises every C06 unit price on its quotation, the list price and both break prices, by **12% for
   purchase orders it receives on or after Wednesday 9 December 2026**, and proposes a further 8% from 4 January
   2027.
2. The client's purchasing accepts the 12% and declines the 8% for now (the director decides after the December
   budget review).
3. Nara Display confirms: 12% from 9 December, the 8% stays open.

So the data shows which change is approved and which is pending. What only the client knows is when orders reach the
supplier: every order is sent on the Monday of its order week, so W3's orders (Monday 7 December) still get the old
price and the increase applies from order week W4 (target `price_rise_week`). Scoring prices C06 from S08 at 1.12×
from W4, in purchases and in the monthly budget, in every tier; open orders are unaffected; the 8% is never applied.
The rise matters because the plan depends on S08: the reference brings S08's later C06 orders forward into one W3
line (December has budget room; in medium the larger line also reaches the second price break). A planner that reads
the effective date as the whole week of 9 December (W3) can only bring them forward into November, which the budget
does not allow, and loses 10–23% of the quality scale in 9 of 15 measured easy settings and 3 of 15 medium ones (in
the others the reference's best plan does not depend on it). In hard the allocation (3,500 displays a month from
S08) leaves no room to bring orders forward, so the week is not a hard target; the rise is still scored in hard. The
thread adapts the owner's earlier approved-versus-pending price notice (C01 from S03 +20% from W4, adapted from the
ReflectionAI procurement scenarios), which changed no plan: S04 was already the cheaper MCU source.

## Tiers: which rules apply

| | easy | medium | hard |
|---|---|---|---|
| **What is in force** | The MRP core | + commercial and calendar terms | + supply uncertainty and the engineering change |
| **Domain facts** | Demand = boards × `qty_per_board`, needed in the build week (no assembly offset); `lead_time_days` are business days, here / 5 rounded up = whole weeks, no holidays; list prices (`unit_price`, with Nara Display's C06 rise from W4), S04 in USD at the planning rate; MOQ per order line; only `approved` suppliers; a hard monthly budget by the month of the order week's Monday (W2 is November; November binds); resistor stock in reels; safety stock for critical parts; one supplier on quality hold; dual sourcing of critical parts with a share cap (company habit) | All-units price breaks per order line; lead times in business days counted from the order Monday, W5 and W6 have 4 (Christmas, New Year's Day) | Each supplier is one or two weeks late with hidden probabilities (estimate them from the history; 1–7 days after the promised Monday = one week, 8–14 = two); deliveries late independently; open orders on time. Allocation caps per month. Engineering change C04 → C25 from W6: C04 left at the end of W5 is scrapped at standard cost, C25 has no stock, is critical and must be dual-sourced; C04 needs neither. A longer quality hold (to W5), which may fall on the main semiconductor maker S03 |
| **What the requirements put out of scope, and why** | List prices (the breaks need a frame agreement not signed yet); whole-week lead times, no holidays; no flash change (engineering is still qualifying C25: C04 in all ten weeks, no C25); no delivery history or allocation (management wants a plan on the confirmed dates first) | The flash change and the history/allocations, as in easy | Nothing |
| **Rules** | `moq`, `quality_hold` (physical); `approved_vendor`, `budget_cap` (contractual); `dual_source_critical` (business policy, bendable) | Same | + `allocation_cap` (physical) |
| **Quality (lower is better)** | Purchases + 0.5% of standard cost per piece held per week + 10,000 KRW per board waiting a week for a part (a missing piece costs 10,000 / the part's pieces per board, counted per part) + 1.5× standard cost per piece-week below safety stock (critical parts, weeks in use) | Same formula; purchases at the break each line reaches | Holding, backlog, shortfall and C04 scrap become exact expectations over the true lateness distribution; purchases are paid either way |
| **Clarification targets** | 16: `bom_explosion`, `lead_time_business_days`, `scope_whole_weeks`, `moq_per_line`, `scope_list_prices`, `price_rise_week`, `quality_hold`, `budget_hard_cap`, `budget_month`, `approved_status_only`, `safety_stock`, `dual_source_two`, `max_share`, `scope_no_flash_change`, `scope_on_time`, `scope_no_allocation` | 17: easy without `scope_whole_weeks` and `scope_list_prices`, + `holiday_weeks`, `usd_planning_rate`, `price_breaks` | 18: `bom_explosion`, `lead_time_business_days`, `holiday_weeks`, `moq_per_line`, `price_breaks`, `quality_hold`, the two budget targets, `approved_status_only`, `safety_stock`, `shortfall_cost`, `dual_source_two`, `max_share`, `backlog_cost`, `supplier_lateness`, `allocation_caps`, `eco_switch`, `eco_c04_exempt` |
| **What it tests** | MRP netting from a BOM, units traps, cash-constrained timing (defer November orders to faster, dearer suppliers; buy displays before the price rise), when to bend a habit, reading which data is in scope | Lot sizing against price breaks under a cash cap, calendar arithmetic | Estimating lateness from small samples, safety lead time vs. cost, splitting volume around allocation, use-up planning for a phased-out part |

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

Why the pools look like this (measured when the rule seeds were introduced, on the reference of that time; the
validator repeats the binding test on every change and passes on world seeds 20261123, 1, 2 and 3; all measured with the validator's binding test: from the first public seed's
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
| easy/s42 | `{"usd_krw": 1320, "safety_weeks": 1, "max_share": 90, "quality_hold": "S07-W3"}` | 491.86 | 483.9 / 7.3 / 0.2 / 0.4 / 0.0 | 114.4 vs. 137.5 | 548.58 (1.115) | −0.8% |
| easy/s3 | `{"usd_krw": 1450, "safety_weeks": 1.5, "max_share": 80, "quality_hold": "S01-W4"}` | 552.85 | 542.8 / 8.2 / 0.0 / 1.9 / 0.0 | 114.8 vs. 222.8 | 629.24 (1.138) | 0% |
| easy/s78 | `{"usd_krw": 1380, "safety_weeks": 0.5, "max_share": 70, "quality_hold": "S05-W4"}` | 469.16 | 462.4 / 5.9 / 0.0 / 0.9 / 0.0 | 114.2 vs. 132.4 | 510.09 (1.087) | −1.6% |
| medium/s42 | `{"usd_krw": 1320, "safety_weeks": 1, "max_share": 90, "quality_hold": "S07-W3"}` | 491.95 | 483.7 / 7.8 / 0.0 / 0.4 / 0.0 | 114.6 vs. 180.7 | 543.09 (1.104) | −2.7% |
| medium/s3 | `{"usd_krw": 1450, "safety_weeks": 1.5, "max_share": 80, "quality_hold": "S01-W4"}` | 541.20 | 530.1 / 9.3 / 0.0 / 1.8 / 0.0 | 112.5 vs. 226.1 | 599.47 (1.108) | 0% |
| medium/s78 | `{"usd_krw": 1380, "safety_weeks": 0.5, "max_share": 70, "quality_hold": "S05-W4"}` | 461.63 | 454.8 / 6.5 / 0.0 / 0.3 / 0.0 | 114.9 vs. 137.2 | 508.46 (1.101) | −2.3% |
| hard/s42 | `{"usd_krw": 1380, "safety_weeks": 1, "max_share": 80, "quality_hold": "S03-W5"}` | 542.83 | 516.2 / 9.5 / 6.6 / 10.5 / 0.0 | 114.4 vs. 273.7 | 646.85 (1.192) | 0% |
| hard/s3 | `{"usd_krw": 1380, "safety_weeks": 1.5, "max_share": 80, "quality_hold": "S01-W5"}` | 602.58 | 585.0 / 10.2 / 4.2 / 3.2 / 0.0 | 114.8 vs. 349.7 | 654.26 (1.086) | −0.2% |
| hard/s78 | `{"usd_krw": 1380, "safety_weeks": 0.5, "max_share": 80, "quality_hold": "S05-W5"}` | 508.14 | 484.7 / 8.0 / 9.8 / 5.6 / 0.0 | 115.0 vs. 297.2 | 604.85 (1.190) | −0.2% |

Means per tier: reference 504.6 (easy), 498.3 (medium), 551.2 (hard); baseline 562.6, 550.3, 635.3. "Unconstrained"
is the default planner (second-source step, two-week lots, no trim) without the budget step, the plan the budget is
calibrated on. Bending is the best plan without the second-source step (the planner with the rule switched off, or
the reference where that is cheaper), against the reference: 0.8–2.7% cheaper in the easy and medium settings with a
70% or 90% cap, nothing where the cap is 80% (the plan without it is no cheaper), at most 0.2% in hard, where
deferrals, allocation and the hold already spread the volume. Whether a bend pays after the policy's penalty is in
REVIEW.md (F1).

### What an agent must ask

The data never states the client's rules, so the client has to be asked. Each target is one fact (the full list per
tier is in the tiers table, the wording in `locales/<lang>/targets.yaml`, and what the client answers from in
CLIENT_REVIEW.md):

- drawn per rule seed: the safety stock in weeks of average demand (`safety_stock`), the share cap (`max_share`), the
  supplier on quality hold and the week it ends (`quality_hold`; with S03 on hold the client adds that the hold covers
  its allocated MCU and DRAM and the new C25 too), and in medium the planning rate for S04's dollars
  (`usd_planning_rate`);
- fixed: that parts are needed in the build week, that `lead_time_days` are business days (and the short Christmas and
  New Year weeks in medium and hard), the MOQ per line, the all-units breaks per line, the week the Nara Display rise
  starts (easy and medium), that the budget is a hard cap and how a week is assigned to a month, approved status only,
  that critical parts need two suppliers, and the round's scope (easy and medium) or the lateness, the allocation, the
  engineering change, the backlog cost and the cost of a safety-stock shortfall (hard).

Facts that are in the requirements but are no longer targets, because misreading them costs less than a tenth of
the quality scale (GT.md, part 1): the resistor reels, the holding cost, the planning rate in easy, the week of
the Nara Display rise in hard, the shortfall cost in easy and medium (an agent that keeps the safety stock as a
floor loses at most 0.09 of the scale there) and the expected-cost scoring in hard (its only misreading is the one
`supplier_lateness` already covers).

## Ground truth audit

`fdebench2 audit-case` (stored in `dataset/audit.json`; GT.md is generated from it by `gt_report.py`) measures, on
the public world, each tier's panel plus 12 admissible parameter combinations (39 settings):

- **Every target bites.** For each of the 25 targets (16 in easy, 17 in medium, 18 in hard) the reference planned
  with that one fact misread (its natural misreading, e.g. lead times in calendar days, W2 in December, the price
  rise from W3, no flash change in hard, the safety stock kept as a floor in hard) loses at least a tenth of the
  quality scale, or is invalid, in at least one measured setting of every tier where it is in force; most bite in
  most settings. A drawn parameter's misreading is the reference of another candidate, the least harmful one
  counted. The misreading planner also weighs the reference's own plan and keeps whichever is valid and cheaper by
  its reading, so a fact that does not change the best plan in a setting costs nothing there.
- **Diagnostics.** `diagnose()` reports `enforced` per target, computed only when the audit or a run's scoring asks
  for it (validate-case never does). A plan is not enforced on a target when it breaks a rule only the client's
  reading has, or when it is materially worse than the best plan known for the fact (regret above 0.05 of the
  scale) and the misreading explains at least half of that, by regret against the reference planner's own plan for
  each misreading (the ablation plans, planned once per setting and cached); another candidate's quality hold that
  the plan keeps must also cost it something, a plan that keeps a misreading's restriction more cheaply than the
  planner's own plan for it is not drawn to it, and where the misreading costs the planner nothing a plan it
  explains only in part is not determinable (None). The quality hold, approved status only and the MOQ per line are
  not enforced whenever the plan breaks their rule. The reference is enforced everywhere and every ablation that
  bites is not. The best known solution and the client's own MRP, which know every fact, are called not enforced in 0 of 657
  target-settings each (the earlier diagnostic, which compared with the reference under the misreading: 125 and
  228), the planner's 386 unpolished variants in 29 of 6,556 (earlier 2,189). Ablations of facts that share a rule
  with others (the monthly budget, the dual-sourcing rule) also flag those others (GT.md, part 5; REVIEW.md,
  diagnostics).
- **Shortcuts are closed.** An empty plan, Express Parts for everything, ignoring the budget, buying everything in
  W1, no buffers at all, ordering only the critical parts, copying the gross demand through, the same order every
  week and the client's own MRP rounded up to price breaks are each invalid or score at most 0.5 in every setting.
- **Asking is necessary.** The best plan that never asks (`robust_solution`: the request's natural reading, i.e. the
  flash change applied and the history and the allocation used as the request asks, the rise from W4, planned for
  the middle safety stock, the tightest share cap, the dearest dollar and every candidate hold) is invalid in every
  easy and medium setting (C04 runs out from W6 and has one supplier) and earns 0.66 in hard: value of asking 1.00
  (easy), 1.00 (medium), 0.34 (hard). No never-asks reading tried, the same in every tier, does better than 0.32 in
  easy (ignoring the flash change, against the request), 0.13 in medium or 0.66 in hard (REVIEW.md, second pass).
- **Bounds.** A wider local search (`best_known_solution`) beats the reference by 0.3–3.2% (quality 1.03–1.31,
  median 1.106); a linear relaxation (`objective_bound`) is 4–7% below the reference in easy, 9–12% in medium and
  18–20% in hard (MOQs and price tiers relaxed; orders due after a part's last week are columns too, since a valid
  plan may place them for the share rule). `quality_cap: 1.11`, the median best-known quality, so the best plan
  known earns full quality credit and the reference 0.90.

## Reference and baseline numbers (seed 20261123)

The reference is a time-phased MRP per part: it nets stock and open orders against the exploded demand and orders
from the cheapest supplier that still arrives in time, as late as possible, covering two weeks (or one) and rounding
up to a price break when the break costs less in total (medium/hard). Critical parts then move whole lines to a
second source until the share cap holds. Leftover stock is trimmed, latest line first. If a month is over budget,
whole lines move to the first week of the next month with a supplier that still arrives in time, cheapest extra cost
per KRW deferred first, each re-sized to what the part still needs from its new arrival week; if no line can move in
time, a line moves late; January's excess is pulled into W6 where December has room; and if nothing can move, a line
is cut, so that the reference is valid whatever a rule seed draws. In hard it plans one week of safety lead time for
every supplier whose smoothed late rate in the history is above 5% and respects the allocation. It keeps the
cheapest valid plan, by its own cost view, of fifteen variants (the netting planner with and without the
second-source step and with two- or one-week lots, plus a lot-for-lot planner that splits every critical order at
the share cap, each with the trim before and after the budget step, only after it, or not at all) and then improves
it with a first-improvement local search under a fixed evaluation budget (6,000 plans; deterministic): lines moved
to another week or supplier, resized to a price break or by hundreds, or dropped, every rule kept. That search is
what buys S08's displays in W3 before the price rise. It uses only what the agent can see: lateness estimates from
the history, never the true rates.

The baseline (`baseline_solution`, quality 0 on the normalized scale) is what the client does today without an
engineer: the ERP's plain MRP run and the buyer's fixes. Every part is ordered lot for lot (each order covers the
first week short of stock or safety stock, at least the MOQ) from the cheapest approved supplier that still delivers
in time, as late as its lead time allows, without rounding up to price breaks. Critical parts follow a quota
arrangement: every order is split with the cheapest other supplier so that neither gets more than the share cap. A
month over budget moves whole lines to the next month as the reference does, and January's lines are pulled into W6.
In easy and medium it plans on the promised dates, as the round says; in hard, where deliveries are late, the buyer
adds one week to every supplier's lead time (a blanket buffer, where the reference buffers only the suppliers the
history shows to be late).

Budget in the data: November 115 M, December 480 M, January 85 M KRW. It is calibrated over every admissible
combination of the candidate pools in every tier (225 combinations), on the unconstrained plans: November is 95% of
the least any combination spends there, rounded down to 5 M, so it binds in every combination a rule seed can draw;
December has 5% headroom over the most any combination spends there plus what it spends in November above the cap;
January 5% over the most any combination spends there. Allocation: C01 6,500, C03 9,000, C06 3,500 per month (60% of
the peak month of the unconstrained hard plan for the calibration values 1,380 / 1 / 80% / S07 to W3).

Over all 225 combinations on this world the reference and the baseline are valid and the baseline is worse (ratio
1.060–1.194 in easy, 1.078–1.229 in medium, 1.086–1.233 in hard); the unconstrained plan overspends November. The
same holds on world seeds 1, 2 and 3 for all 225 combinations each, with the baseline worse by at least 7.6% / 7.3% /
6.3% (world 1, easy / medium / hard), 5.3% / 5.1% / 13.1% (world 2) and 5.5% / 5.9% / 5.0% (world 3; the lowest,
5.02%, is hard with 1.5 weeks and Hanbit Electronics on hold). The validator checks the public panel on world seeds
1–3; the audit measures 12 more combinations per tier (GT.md).

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
  range for carrying cost; 10,000 KRW per board-week of backlog, counted per part, about a quarter to a half of a
  board's material cost for a week's late-delivery penalty and overtime; 1.5× for shortfall; scrap at standard
  cost) are design choices, not measured values. Counting the backlog per part overstates a week in which several
  parts are short at once (the line stops once); it keeps every part's cost separable, so the expectation in hard
  stays exact. The two short weeks assume Christmas and New Year's Day are
  non-working days, as in most countries that use the Gregorian calendar; other plants may differ.
- Lateness is a property of the supplier only (not of the part or the season), at most two weeks, and independent
  across deliveries; real suppliers have correlated delays (a shared shipment, a plant shutdown). The history has
  10–28 deliveries per supplier, so some estimates are far from the truth: S05 (10 deliveries) looks late 32% of the
  time against a true 15%. True late rates at this seed run from 2% (S09, the express broker) to 37% (S04, overseas)
  and 35% (S03, the allocated semiconductor maker).
- `validate-case` checks every public setting: deterministic data in five locales, the same agent view in all nine,
  the reference at quality 1.0, a valid baseline worse than the reference by at least 5% (on this world and on world
  seeds 1–3), one deliverable per rule of the setting that breaks only that rule, that every parameter binds, and,
  since the case is `audited: true`, a fresh ground truth audit whose findings pass.

## Relationship to the source assignment

This is a synthetic adaptation of the Apex Manufacturing take-home, not a reproduction of its data or a submission to that assignment. Both use a production schedule, BOM, shared components, stock, existing purchase orders, supplier eligibility, lead times and sourcing rules. Here the output remains the benchmark's eight-week `orders.csv`; the original assignment calls for a general-purpose program that writes purchase orders and alerts to scenario databases. The e-mail thread with Nara Display is a new fictional commercial event, not a document from the assignment.

The source assignment also includes dated management memos, certification, concentration history, approvals, hazardous handling and expedited freight. Those are not modeled by this extension: the existing quality hold and dual-source rule are only simplified analogues. The simulated client does not receive later emails during a run, issue purchase orders, or request approval. The exercise tests incorporating a dated, approved price revision (and ignoring a pending one) into a static plan and budget, rather than autonomous event handling.
