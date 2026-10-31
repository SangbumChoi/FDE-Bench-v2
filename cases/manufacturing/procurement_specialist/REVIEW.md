# Review: manufacturing/procurement_specialist

What a case review found (F1–F10) and what this change did about each finding. Numbers are for seed 20261123 after
this change unless a finding says otherwise. The supplier price e-mail and its rule are the owner's and were not
changed.

### Rule seeds (conversion from rule sets A/B/C)

The three fixed rule sets became candidate pools that a rule seed draws from, one parameter at a time (README,
"Rule parameters"). The data, the request and the price e-mail (C01 from S03 +20% for orders from W4, scored by order
week) are unchanged apart from the November budget, which the calibration below moves from 125 M to 115 M.

- **Pools.** `usd_krw` 1,380 · 1,450 · 1,320 · 1,500 in easy and medium, 1,380 in hard; `safety_weeks` 1 · 1.5 · 0.5
  in every tier; `max_share` 80 · 70 · 90% in easy and medium, 80% in hard; `quality_hold` (supplier and last week
  as one value) S07 to W3 · S05 to W4 · S01 to W4 in easy and medium, the old A/B/C pairs, and S03 to W5 · S05 to
  W5 · S01 to W5 in hard. Public panel `rule_seeds: [42, 3, 78]`; every candidate appears in it except one planning
  rate (three seeds, four rates).
- **Binding (validator, worlds 20261123, 1, 2, 3).** From the first public seed: in medium, planning rate 1,320 →
  1,500 moves the reference +1.17 / +2.22 / +1.79% and breaks the budget on world 3; share cap 90% → 80% makes it
  invalid on all four; in hard, safety stock 1 → 1.5 weeks moves it +10.3 to +11.9%, and the hold S03 to W5 →
  S01 to W5 makes it invalid on all four.
- **Dropped or merged because they did not bind.** The hold week alone (S03, W4 → W5 changed nothing in hard: the
  November budget already pushes S03's orders to W3), so it is drawn with the supplier. The planning rate and the
  share cap in hard (1,320 → 1,550 moved the hard reference 0.6–1.4% by world; a 90% cap left it valid under 70% on
  two of four worlds), so hard keeps 1,380 and 80%. A finance reserve on the monthly budget (0 / 5 / 10%), tried as
  the budget parameter, moved the hard reference 0–1.3%. A 60% share cap for hard was left out: the reference's
  whole-line second sourcing cannot reach it for C02 and C25.
- **admissible()** rejects a hold that ends before the supplier's goods could arrive at all (S03 and S05 quote 11–13
  business days: nothing arrives before W4, so "S05 to W3" would change nothing and has no violating example). The
  pools hold no such value; the hook guards edits.
- **Budget calibrated over the pools.** November's cap is 95% of the least unconstrained November spend over all 225
  admissible combinations of all tiers, so it binds whatever a rule seed draws (before, easy/C spent 125.1 M against
  125 M). December and January keep headroom over every combination.
- **Reference and baseline valid in every combination.** A private seed may draw any combination, so the budget step
  no longer raises when no line can be deferred in time: it moves a line late, pulls January's excess into W6, or
  cuts a line, cheapest extra cost per KRW first. The baseline uses the same fallback. On this world all 225
  combinations have a valid reference and a valid, worse baseline.
- **Stronger reference.** It now also tries one-week lots and a leftover trim (a line cut to what the part still
  needs, or replaced in the same week by a small-MOQ supplier), eight variants in all. The trim was needed: without
  it the baseline beat the reference in 30 of 162 sampled easy settings of this world, all with 0.5 weeks of safety
  stock (end-of-horizon overbuying at the second source's MOQ). Panel ratios baseline/reference: 1.054–1.091 easy,
  1.046–1.065 medium, 1.156–1.377 hard.
- **Still open.** On other worlds the baseline still matches or beats the reference in a few easy and medium
  combinations, all with Kowon Passive (S07) on hold to W3 and mostly 0.5 weeks of safety stock: none on world 1, 9
  of 108 medium combinations on world 2 (by up to 1.6%), 2 easy and 3 medium on world 3 (by up to 0.2%). The
  reference's two-week lots front-load November, and its deferrals to faster, dearer suppliers cost more than the
  baseline's small lot-for-lot lines. Quality then falls back to the plain ratio. This belongs to F2.
- **Checker's follow-up (resolved).** A check of private rule seeds 4–10 on world seeds 1–3 hit these combinations:
  rule seeds 6 and 8 (S07 to W3, 0.5 weeks) had the baseline 0.1–1.6% below the reference in easy and medium on worlds
  2 and 3. The reference now keeps the cheapest of fifteen variants: the eight above, the same with the trim only
  after the budget step (trimming first can leave the budget step only dearer deferrals), and a lot-for-lot planner
  that splits each order of a critical part at the share cap, with the three trim options. In those combinations the
  quota planner trimmed after the budget step wins, 1.0–1.4% below the baseline (the trim cuts the end-of-horizon
  lots the baseline keeps). All 225 combinations on each of worlds 20261123, 1, 2 and 3 now have a valid reference
  and a valid baseline that is worse by at least 1.0% (min baseline/reference ratio 1.0098, world 2 medium; hard at
  least 1.128). Panel references: easy/s42 505.86 → 503.68, easy/s3 573.41 → 564.63, medium/s42 513.61 → 504.47,
  medium/s3 558.17 → 556.57, medium/s78 482.66 → 479.39, hard/s3 609.07 → 608.79, hard/s78 514.40 → 514.19 M KRW;
  baseline/reference ratios 1.054–1.100 in easy, 1.053–1.085 in medium, 1.156–1.378 in hard. The data and the
  budget calibration are unchanged (the calibration uses the default planner without trim).
- **Tests.** `tests/test_procurement_price_email.py` read the settings from the removed `all_settings()`; it now takes
  them from the case. `tests/test_rule_seeds.py` used this case as its example of the deprecated `rulesets:`; it now
  builds a legacy copy of its own toy case.

### F1 — Bending the dual-sourcing habit is not worth it for a strong plan (high, partly)

The requirements allow an exception to `dual_source_critical` "if it saves real money". Under the old scale bending
never paid: on a local-search plan it saved 0.2–2.1% (0% in hard), quality was clipped at 1.0, and a bent rule
costs 0.05 or 0.1. The new scale pays only weak plans to bend. At reference level, dropping the second-source step
cuts the objective by 2.5–4.8% in easy and medium. That lifts normalized quality from 1.0 to 1.27–3.25, which is
+0.11 to +0.20 of the final score, more than the penalty. On a local-search plan the same step saves only 0.6–2.0%
(0–0.3% in hard). Quality there is already above the 1.5 cap, except in easy/B (+0.02) and hard/B (+0.005). So the
payoff comes from the narrow baseline gap (F2), not from what the habit costs.

**Status:** open — proposal: decide whether bending should pay for strong plans too. If it should, make the second
source structurally dearer or slower for the high-value critical parts (C05 PCB, C06 display), or remove S04 as the
cheap alternative for C01 and C03. Then measure the gain on an optimised plan: it should be at least 3–5% in easy and
medium, and worth more than the penalty after the cap. In hard, give the habit a real cost, for example second sources
only from late-prone suppliers. Recheck after F2's calibration, because where the cap sits decides who gains.

**Status (rule seeds):** open, remeasured on the panel: the best plan without the second-source step saves 2.6–4.0%
in easy and medium (0.2% in medium/s3) and nothing in hard, where the hard reference already is such a plan.
After the fifteen-variant reference (Rule seeds, checker's follow-up): 1.4–3.6% in easy, 0.2–3.3% in medium, at most
0.3% in hard.

### F2 — Weak greedy reference, and a deferred line kept its old MOQ (high, confirmed)

In all three hard settings, `_defer` moved the W1 C04 line (S03, MOQ 4,100) to S09 in W3 and kept all 4,100 pieces,
although only 1,386 were still needed. The other 2,714 were scrapped, costing 3.80 M KRW. The reference is also a
plain greedy: the 5% safety-lead-time threshold never decides anything, because the lowest smoothed late rate is
S09's 8.3%. A first-improvement local search beats the reference by 3.0–11.1% (quality ratio 1.030–1.111). On the
new scale that search scores q 1.25–4.90, which is above the 1.5 cap in 6 of 9 settings. The baseline sits only
2.1–2.8% above the reference in easy and medium under A and C, so small gains look large. On other world seeds the
gap is often narrower: over seeds 1–40 (39 worlds build), 15 of the 234 easy and medium settings have the baseline
within 2% of the reference, down to 0.6% (seed 5 medium/A, seed 17 easy/A), where a plan 1% better than the
reference already scores q above 2.5. In hard the baseline stays 1.08–1.29× the reference.

**Status:** fixed in this change: the `_defer` bug. A moved line is now re-sized by `_resize` to what the part still
lacks from its new planned arrival. It is rounded the way the planner rounds and never grows. Hard now buys 1,400 C04
and scrap falls to 0.02 M. The references change by −3.6% to +0.1%: hard −1.5/−3.6/−2.0%, the B settings about
−3.5%. easy/A gets 0.12% worse, because the ratio-greedy deferral now defers more than November needs. The December
cap is calibrated at 5% over the references, so it drops from 525 M to 490 M in the data. Open — proposal: make the
reference near-optimal, either by shipping a local search or a MILP with a fixed solver, or, in hard, an
expected-cost search on the history estimates. Make the safety-lead-time rule meaningful, for example by weighing a
supplier's estimated late rate against one week of holding. Then set `quality_cap` in case.yaml from the best known
normalized quality, or widen the baseline gap, so that a generic optimiser does not saturate.

**Status (rule seeds):** partly improved. The reference now keeps the cheapest of eight planner variants (second
source or not, two- or one-week lots, with or without a leftover trim that cuts or re-sources the last lines), and
its budget step falls back to late moves, pulls and cuts so that it is valid in every combination. The baseline gap
on the panel is wider: 1.046–1.091 in easy and medium (was 1.021–1.113), 1.156–1.377 in hard. Still open: the
local-search headroom was not re-measured, the safety-lead-time threshold still decides nothing, and on world seeds
2 and 3 the baseline matches or beats the reference in 14 of 432 easy and medium combinations (see "Rule seeds").
That last point is resolved: with the quota planner and the trim after the budget step among its variants, the
reference beats the baseline by at least 1.0% in every combination on worlds 20261123, 1, 2 and 3. The local search
and the safety-lead-time rule stay open.

### F3 — The price e-mail does not change the answer, and the documentation was stale (high, confirmed)

The scorer raises C01 from S03 by ×1.20 from W4. But S04 already quotes C01 at 3,692 KRW against S03's 4,146, so a
planner that ignores the e-mail scored 0.994–0.999 in easy and medium and produced an identical plan in hard (verifier
numbers). As a document, the e-mail has several problems:
- it comes from the buyer's own address
- it uses the internal week code W4
- it is a `.txt` with one English file name in every locale, where DESIGN.md asks for localized `.eml` files
- it has no clarification target
- it says itself that the pending 5% must not be applied

The documentation had also drifted. The README table was labelled "before the price email" and was stale (easy/A
515.25 against 518.87 stored). The requirements' copy of the request had lost its e-mail line. README, case.py and
DESIGN.md disagree on where the case comes from (the ReflectionAI and Apex lineage, "original", "written from
scratch").

**Status:** fixed in this change, documentation only:
- README numbers are regenerated from the current code and include the baseline; explainer.html is regenerated.
- The README lists the e-mail file among the data and in the easy price facts.
- The request's e-mail line is added to the Background of all five requirements files.
- The easy price bullet names the e-mail change in all five locales.
- The e-mail paragraph now sits at the end of the data notes in every locale.

Open — proposal (owner's decision): make the e-mail matter by raising a part or supplier the plan depends on, such as
S08 displays, S05 PCBs or C01 at S04. Give the effective date as a mid-week calendar date, and let the agent infer
approved versus pending from a thread. Deliver it as a localized `.eml` from a supplier domain, with a clarification
target. Resolve the provenance statements: cite or drop the ReflectionAI and Apex lineage after a licensing and
contamination check.

### F4 — Backlog is priced per piece of the part, not per board (high, partly)

Backlog costs 5× the part's standard cost per piece-week, separately for each part, so a shortage of a cheap part
barely counts. hard/A's reference leaves 11,366 piece-weeks of the 6 KRW MLCC C10 waiting, about 384–392
board-weeks, for 0.34 M KRW. One board's material costs 18,210 KRW (B100) or 37,534 KRW (B200). Per board-week, a C10
shortage costs about 890 KRW against 74,000 for the display, roughly 83×; the review's 2,500× is the per-piece ratio.

**Status:** open — proposal: price backlog per board-week. One way is `board_penalty / qty_per_board` per missing
piece, with `board_penalty` set to 5× the board's material cost or a stated margin. This stays separable per part, so
the exact expectation still works. The alternative is to simulate builds as the minimum over parts. Either way,
re-calibrate the budget and the references, and state the per-board stoppage cost in the `cost_model` target.

### F5 — Rule sets are nested, and the budget binds mostly in November and under B (medium, confirmed)

B is the strictest and C the loosest on every numeric parameter: 1,450, 1.5 and 70% against 1,320, 0.5 and 90%. What
keeps the rule sets apart is the supplier on hold. All 18 cross-pairs are invalid, and 16 of them fail on
`quality_hold` (6 also on dual sourcing, 4 on the budget). Before this change, the verifier measured the November cap
costing 0.02–1.55% in easy and medium under A and C; unconstrained November spend in easy/C is 125.1 M against a
125 M cap. December (now 490 M) and January are built with 5% headroom over the references. The local-search
plans spend 269–435 M in December.

**Status:** open — proposal: decorrelate the parameters, for example A: high FX and low safety; B: low FX, high
safety and a loose share; C: mid FX and a strict share. Make at least one more parameter non-nested: which month is
tight, or which parts are critical or on allocation. Calibrate the caps per rule set so that compliance costs at least
2% in every setting, and let December bind in one rule set.

**Status (rule seeds):** mostly fixed. Each parameter is drawn on its own, so the strict values no longer come
together: the panel has, for example, 1,320 with 1 week and a 90% cap, and 1,380 with 0.5 weeks and a 70% cap. The
non-nested hold stays and gains a harder hard pool (S03, S05 or S01 to W5). Every parameter binds on four worlds
(see "Rule seeds" above). November's cap is now calibrated over every combination of the pools, at 95% of the least
unconstrained November spend, so it binds in every combination (115 M; the unconstrained November spend on the panel
is 132–346 M) instead of barely in easy/C. December binds only in a few hard combinations where deferrals pile up;
compliance does not cost 2% everywhere (a budget parameter was tried and did not bind). Open: the month that is tight
is still always November.

### F6 — Lower-tier scope cuts read as switches, and the easy price line was garbled (medium, confirmed)

The easy and medium requirements say to plan as if every supplier confirms everything, although the client forwarded
an allocation notice. Easy also says "plan at list prices" and "ignore holidays" while the production plan visibly
dips in W5 and W6. en:29 read "adjusted for the approved email, whatever its size", where the other locales say
"regardless of line size". The targets `round_scope_easy` and `round_scope_medium` pack three facts and two facts into
one target each.

**Status:** fixed in this change: the garbled sentence. en:29 now reads "every order line is priced at `unit_price`
per piece regardless of its size (with the approved change from the supplier price email)". The other four locales
name the e-mail change in the same place. Open — proposal: give each scope cut a reason inside the story, for
example:
- the allocation takes effect in February;
- the delivery history comes from the old ERP and is unreliable;
- the price breaks need a frame agreement that is not yet signed;
- the ERP plans in weekly buckets.
Also split the round-scope targets into one target per fact.

### F7 — The "country-neutral" scenario is a Korean plant (medium, confirmed)

The README calls the case country-neutral apart from one fact. Yet eight of the nine suppliers are Korean, the ja and
zh sheets list them as 韓国/韩国, the short weeks are Korea's 25 December and 1 January, and the budget is in KRW in
every locale. The budget (125 / 490 / 85 M) is derived from reference spend, which leaves January at about a sixth of
December. Stock left after W10 is worth nothing, so the hard references spend 2.6 M in January and let the
non-critical parts run out.

**Status:** open — proposal: either say in every locale that the client is a Korean plant and correct the README, or
localize the currency, the supplier countries and the holiday calendar per locale. Derive the budget from a business
rule, for example 0.9 × the standard cost of the demand each month's orders cover, and check that it binds. Add a
terminal requirement, such as N weeks of W11–W12 demand on hand at the end of W10, or value ending stock at standard
cost.

### F8 — No dated event and no pressure that works (medium, confirmed)

The e-mail is dated 2026-11-20, before W1, and is a static file. The client receives no later e-mails, and the only
bendable rule is the one in F1, so the only situations the case really has are hidden facts. Lateness modelling does
matter in hard. The verifier's local search that ignores lateness scored 0.922 in hard/A and 0.956 in hard/B; the
same search on the history estimates scored 1.120 and 1.097.

**Status:** open — proposal: build a weekly program variant of hard on `casekit.program_session`. Each week the
program would receive the realised arrivals, and dated events would arrive mid-run: the price revision in W3, a
January allocation cut, the S05 hold lifted early. Add a pressure situation scored through the existing exception
process, for example a plant manager asking to take S05's held lots "just this once", or to buy everything from S09.

### F9 — Data realism slips (low, confirmed)

74 of the 188 history receipts (39%) fall on a Saturday or Sunday, because on-time lots arrive 0–4 days before the
promised Monday. Eight history rows come from supplier-part pairs the AVL marks pending or suspended, for example
PO-3132 (S07/C18, pending) and PO-3250 (S07/C17, suspended). This happens because history parts are drawn from every
quoted pair. S03 also quotes connectors and the antenna, although the README calls it the allocated semiconductor
maker. The allocated MCU and DRAM have 13 business days of lead time at S03.

**Status:** open — proposal: move received dates to business days. Draw history only from approved pairs, or label
the others as qualification samples. Move S03's connector quotes to a distributor. Give the allocated parts longer
lead times, for example 30–60 business days with an S09 premium, so that allocation and lateness interact.

### F10 — Korean wording and where the e-mail rule sits in each locale (low, confirmed)

- ko:59 "…입고 예정이지 않습니다" was ungrammatical.
- ko:80 applied the e-mail change "to the order week".
- ko:42 (and zh:42 必须, ja:42 必ず) turned the bendable habit into a "must".
- The e-mail paragraph sat in the data notes in en but at the end of the scoring section in the other locales.
- zh:80 applied the change only to the price-break prices.
- S09 appears in the texts as "익스프레스파츠" and "Express Parts", but in the data as "익스프레스파츠코리아" and
  "Express Parts Korea".

**Status:** fixed in this change:
- ko:59 now reads "W1~W{{hold_until}}에 입고 예정인 {{hold_supplier}} 물량이 없습니다".
- The e-mail paragraph is reworded in ko and ja and moved to the end of the data notes in ko, zh, ja and es, with the
  same content as en.
- zh now names both the base unit price and the price-break prices.
- 반드시, 必须 and 必ず are removed.

Open — proposal: use the supplier names exactly as they appear in the data, and add a validator check that block
positions and supplier names match across locales.

**Baseline:** what the client does today without an engineer, an ERP-style MRP run. Each part is ordered lot for lot
from the cheapest approved supplier that delivers in time, at list prices and on the promised dates. Critical parts
are split by a quota, and the buyer fixes the budget afterwards. Objectives in M KRW, baseline against reference:

| Tier | A | B | C |
|---|---|---|---|
| easy | 534.17 vs. 519.50 | 644.90 vs. 579.32 | 503.44 vs. 491.90 |
| medium | 532.54 vs. 521.76 | 615.89 vs. 582.57 | 502.76 vs. 492.37 |
| hard | 670.53 vs. 579.75 | 745.39 vs. 612.78 | 647.75 vs. 537.11 |

The baseline is between 1.021× and 1.216× the reference. (These are the rule sets A/B/C of the first version; after the
rule-seed conversion the public panel's baseline is 1.046–1.377× the reference, see the README's "Public panel".)
