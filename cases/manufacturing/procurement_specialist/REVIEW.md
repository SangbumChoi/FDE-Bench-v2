# Review: manufacturing/procurement_specialist

What a case review found (F1–F10) and what this change did about each finding. Numbers are for seed 20261123 after
this change unless a finding says otherwise. The supplier price e-mail and its rule are the owner's and were not
changed.

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

The baseline is between 1.021× and 1.216× the reference.
