# Review — data_knowledge/bi_data_analyst

Findings from the case review, checked again against the code at the public seed (20261026) and on world seeds 1–20.
F1, F3, F8 and F9 were fixed when the review was first addressed (the "first change" below). F10 is the case
owner's request: three tiers × three rule sets, and answers that can be right, "don't know" or wrong, with rewards
that differ by rule set. It is done in the second change, which also moves F2, F4 and F5. The rest are open
proposals for the case owner.

### F1 — The rounding rule made Q07 and Q09 unanswerable (high, partly)

Money answers had to be whole thousands of KRW, but they were scored within 0.5% of the unrounded figure. For the
per-order averages this fails: Q07 = 41,618 rounds to 42,000 (+0.92%) and Q09 = 35,780 rounds to 36,000 (+0.62%).
So a sheet that followed the rule could score at most 10/12, and the stored reference scored 9. The rounded exact
answers passed on only 35% (Q07) and 45% (Q09) of seeds 1–20. Bending `report_rounding` raised the score: a UTC-day
sheet scored 7/12 rounded and 9/12 exact.

**Status:** fixed in the first change. A money answer is now correct within 0.5% or 500 KRW of the exact figure,
whichever is wider, so the exact figure rounded to the nearest thousand always counts. The "How the answers are
judged" section and the `report_rounding` target say so in all five locales. `violating_examples` now asserts that
the exact answers, rounded as finance requires, score 12/12 with no violation on every world the validator builds;
they do on seeds 1–20. The reference rises from 9 to 11 (Q07 and Q09 now count), and following the rule no longer
costs a question: the UTC-day sheet scores 9/12 rounded or exact. The verifier's objection stands: no general
"bending never helps" check was added, since bendable rules elsewhere are meant to cost objective. Second change:
the rounding unit is now a rule-set parameter (1,000 / 10,000 / 100 KRW), the money tolerance is 0.5% or half the
unit, and the same assertion (objective 1.0, no violation) runs in all nine settings.

### F2 — No headroom between the reference and the ceiling (high, confirmed)

The reference is `compute()` with the category rename missed. Under the old clipped scale it scored 9, and any sheet
with 9 or more correct got full quality. With the F1 fix and the new scale the problem is reversed. The reference
scores 11 and the baseline 0, so a perfect sheet has normalized quality 12/11 = 1.09. Under the policy cap of 1.5,
a perfect sheet earns only 73% of the quality credit, and the rename (Q06) is the only fact that separates it from
the reference.

**Status:** open, and changed by the second change (F10). The reference still misses only the rename, and Q06 is
scored only in hard. So in easy and medium the reference is right on every scored question and *is* the ceiling: a
perfect sheet has normalized quality 1.000 in all six of those settings. Under the policy cap of 1.5 the best
possible sheet earns 67% of the quality credit there. In hard the perfect sheet scores 1.091 (A), 1.125 (B) and
1.091 (C) at the public seed: the reference leaves Q06 as "don't know" under A and C and gets it wrong under B. Its
objective is 0.958 / 0.917 / 0.979 on every seed checked (1–20), and the baselines move the normalized figure only
slightly. The earlier proposal (`quality_cap: 1.09`) no longer fits. One case-wide cap cannot give full credit to the
perfect sheet in all nine settings: a cap of 1.0 would give a reference-level sheet full credit in hard as well, and
a cap above 1.0 leaves easy and medium short. So the second change sets no `quality_cap`. Proposals:
(a) a per-tier `quality_cap` in the framework (1.0 for easy and medium, 1.10 for hard); (b) give the reference one
deliberate gap in every tier, e.g. a question it cannot settle in easy and in medium, so that it abstains there too;
(c) weight each question by the number of binding targets it exercises, so that every hidden fact costs about the
same.

### F3 — Refunds dated after the reference date, and a hair-trigger Q11 tolerance (high, partly)

`refunds.csv` has 23 refunds dated 2026-10-01 to 2026-10-18 (Korea time), worth 853,041 KRW ex tax. The truth
counts them against their order's period. The requirements already gave the booking rule but not the export date.
Cutting refunds off at the reference date moves Q11 from −2.57% to +0.38%. Q11 was scored within 0.5% of itself,
i.e. ±0.013 percentage points, or about ±3,700 KRW on 29 M KRW of monthly revenue.

**Status:** fixed in the first change, using the text option, which leaves the data and every truth unchanged. The
requirements in all five locales now say that the export was taken on 2026-10-31 and holds the orders placed up to
the reference date with every refund recorded until then, and that October refunds count against their order's
period. The `net_revenue` target said the same; in the second change that clause is its own target,
`late_refunds` (medium and hard, where Q11 is scored). By construction no refund can fall after 2026-10-29; the latest on
seeds 1–20 is 2026-10-26. Q11 is now scored within ±0.05 percentage points, so a change reported to one decimal
place counts. The October refunds still cost a sheet that drops them: 1–2 questions, Q11 and sometimes Q07. A
tax-inclusive Q11 is off by only 0.015–0.052 points and now usually passes, but that sheet still loses Q01, Q02,
Q07 and Q09.

### F4 — Some target clauses never change an answer (medium, partly)

The verifier reproduced the numbers. Three clauses never change an answer: refunds at the refund-date FX rate (0/12
change), line-matched rather than pro-rata refund allocation (Q06 moves 0.28%), and an 89-day active window. Test
accounts are visible as `account_type = test`. New data point: at world seed 2 the latest-rate FX shortcut costs no
question at all, so `fx_order_date` binds only on some worlds. With the F1 tolerance, the refund cut-off and active
window variants now cost only their own question (Q11, Q03). Before, Q07 and Q09 also failed by the rounding
lottery.

**Status:** open. Proposal: make the sub-clauses bind, or drop them from the target texts. Possible data changes:
an FX move between order and refund dates large enough to move a money answer by more than 0.5%; partial-quantity
refunds that do not equal a line amount; completed orders on 2026-07-02 and 2026-07-03 from customers with no other
order in the window. Then check on seeds 1–3 that each target, and each clause the client is asked about, flips at
least one answer.

Second change (partly addressed). The `net_revenue` target is split by tier. `net_revenue` keeps the tax and
booking clauses, which bind in every tier (tax-inclusive: Q01 in easy, 3–5 questions in medium and hard). The
October-refund clause is `late_refunds` (medium, hard): Q11 in every rule set, plus Q02 under B. The pro-rata clause
moved into `category_rename` (hard). It is still small there (Q06 moves 0.28%), but it now sits in the one tier
where a category figure is scored. Still open: the refund-date FX clause, and `fx_order_date` costing nothing on some
worlds (seed 2 under A and B, seed 1 under B). The 89-day point is now a one-day-short window under each rule set:
it costs Q03 in every setting at the public seed and on seeds 1–3, except A at the public seed and B at seed 1.

### F5 — No settings and no README (medium, confirmed)

case.yaml declares no tiers or rule sets, so all nine difficulty × rule-set cells score the same problem. The
convention parameters are already easy to lift out of `compute()`: FY start and naming flips 6–8 answers, the FX
convention 0–5, and the active window flips Q03. The verifier found that booking refunds in the refund period
flips 2 answers (Q08, Q11), not 4 as the finding said.

**Status:** fixed in the second change (F10). The README was added in the first change. What the proposal said, and
what was built:

- Tiers. Easy scores Q01, Q03, Q04, Q10 and Q12, covering counted orders, test and staff accounts, FY and rounding;
  the other questions are answered with null "this round". Medium adds net revenue, FX and Korea time. Hard adds
  the rename, the October refunds and the F6 situations. *Built:* easy and medium as proposed (medium scores Q02,
  Q05, Q07, Q08, Q09, Q11). Hard adds Q06 (the rename). The October refunds already bind in medium, because Q11 is
  scored there. The F6 situations are still open (F6).
- Rule sets vary the FY start (April / July / January), the active window (90 / 60 / 30 days), the rounding unit
  (1,000 / 10,000 / 100) and the FX convention. Score the rounding unit with the half-unit tolerance from F1.
  *Built:* FY start, window and rounding unit as proposed, with the half-unit tolerance. The fourth parameter is
  the owner's reward scheme, not the FX convention.
- Check that each rule set's sheet loses at least one question under the other two. *Built:* validate-case checks
  that each reference is invalid or at least 1% worse under the other rule sets of its tier. All 18 pairs pass:
  9 are invalid (rounding), and the 9 valid ones score 0.00–0.40 of the other reference.

### F6 — No dated event and no pressure (medium, confirmed)

The case has only hidden facts. The QA load test on account 10027, which makes it the top FY2025 customer when test
accounts stay in, is an obvious temptation that nobody voices. After F1, `report_rounding` costs nothing to follow,
so the case no longer has a bendable rule that it pays to bend.

**Status:** open. Proposal: add a visible pressure note, identical in every setting. For example, a sales
director's line in the questions file: "Q04 should be 10027, our big B2B pilot." The right move is to follow the
finance policy or escalate. Add a dated event, e.g. a mid-task message that a staff account was reclassified as
test from a given date, or a corrected `fx_rates.csv` for one week. Add a business-policy rule whose bending is
reasonable and changes an answer, so that asking to bend it is a real trade-off.

### F7 — Seoul head office with a non-Korean working language; implausible data details (low, confirmed)

Every locale describes a Seoul company that reports in KRW. Its labels are nevertheless "in our working language"
(Spanish, Japanese, Chinese). The data also has a flat 7% US tax, FX rates on weekends, 391 paid cancellations with
no reversal row, and sign-ups from 2024-07-01 while orders start on 2025-01-01.

**Status:** open. Proposal: make the client the Madrid, Tokyo or Shanghai sales office of a Seoul group that
reports group figures in KRW. That keeps one world and one truth. Add reversal rows for paid cancellations, which
keeps the trap. Use business-day FX with a "last available rate" rule (a new hidden fact). State in the data
dictionary that the order history starts on 2025-01-01.

### F8 — Korean wording: two half-years and an ambiguous Q12 (low, confirmed)

The Korean Q05 called the 2026-07-01 sale "상반기 결산 세일" (calendar first half), while Q07 uses "FY2026 상반기"
for April–September. That nudges toward a calendar fiscal year. Q12 "몇 개의 상품" admits a distinct-products
reading: 1.66 lines per order against the true 2.105 units.

**Status:** fixed in the first change. The Korean questions file now reads "Q05: 여름 세일 당일(2026-07-01)…" and
"Q12: FY2025 주문 1건당 평균 상품 수량(낱개 기준)은 얼마인가요?". The ja (中間セール, 点数) and zh (年中大促, 件)
wording has no such collision, so it is unchanged. The category label 팬트리 is kept; that point is a matter of
taste and was not in the fix list.

### F9 — The test-account gate is narrower than its rule text (low, partly)

The gate only checks Q03, Q04, Q05 and Q10 for exact equality with the Korea-time figure that includes test
accounts. Money answers that include test accounts pass validity (8/12, no violation), and so does a sheet that
excludes only account 10027 (4/12). The requirements already described the gate correctly; case.yaml did not.

**Status:** fixed in the first change. The case.yaml rule now says "a count or customer-id answer (Q03, Q04, Q05, Q10)
that equals the figure with test accounts included, where that differs from the figure without them". One point is
left for the owner. The comparison always uses Korea-time days, so a sheet that excludes test accounts but uses UTC
days can match by coincidence: at world seed 1, its Q10 = 639 equals the test-inclusive figure and is flagged.
Proposal: do not flag an answer that equals the test-free figure under either day convention. Second change: the
gate checks only the questions the tier scores, under the setting's periods, and a `null` never trips it. The seed-1
coincidence now shows in easy/A, medium/A and hard/A, because Q10 is scored in every tier. It is still open.

**Baseline:** "not available yet" (`null`) for every question, what finance reports without an analyst. It earns the
don't-know reward everywhere (0.5 / 0.25 / 0.75 under A / B / C), so saying "don't know" to everything scores 0 on
the normalized scale. The face-value sheet (the export summed at face value: calendar-year periods on UTC dates,
every order status, tax-inclusive totals less refunds dated in the period, the 2026-09-30 FX rate, a 30-day active
window, the `pantry` label only; test accounts out, money rounded) scores below it in every setting and on seeds
1–20 (at most 0.60, in easy/C, against 0.75). The exact answers rounded to the setting's unit score 1.0 everywhere.

### F10 — Answers could not say "don't know", and the case had one ground truth (owner request; done)

The case owner asked for answers that can be right, "don't know" or wrong, with rewards that differ by rule set. The
benchmark should then measure whether an agent says "don't know" when it should (calibrated abstention), and whether
it gets the answer right when it does answer. The case also had no settings (F5).

**Status:** done in the second change. The data, the request and the questions file are unchanged and byte-identical
in all nine settings. The public seed's figures under rule set A are those of the case without settings.

- **Answers.** `answers.json` maps every id Q01..Q12 to a number or `null` ("don't know"). A missing key, or a value
  that is neither a finite number nor `null`, breaks `answer_format` for any question, scored or not. The
  deliverable spec, the rule texts and the requirements in all five locales say so. The extractor is told to write
  `null` where the engineer gave no figure.
- **Score.** Each scored question earns 2 if right, `dont_know_reward` if `null` and 0 if wrong. The objective is
  total / (2 × scored questions), in [0, 1]. Metrics: `scored`, `answered`, `right`, `wrong`, `dont_know`,
  `accuracy_on_answered`, `coverage`, `reward`, and the wrong and "don't know" question lists. An answer or a `null`
  to an unscored question has no effect. The rounding and test-account gates check only scored questions.
- **Rule sets.** A = (0, 1, 2), B = (0, 0.5, 2), C = (0, 1.5, 2), so an agent that knows the scheme answers only
  when P(right) is above 50%, 25% or 75%. The other parameters change the correct answers: FY start April / July /
  January, active window 90 / 60 / 30 days, rounding unit 1,000 / 10,000 / 100 KRW. The client states the scheme in
  business terms: a wrong figure in the board pack must be corrected at the next meeting and costs credibility,
  while "not available yet" only leaves a gap. The three values follow. It is a target (`answer_rewards`, kind
  missing).
- **A period that runs past the data.** Under a July year, H1 FY2026 is July–December 2026, past the reference date.
  The requirements say, in every rule set, that a period still running on the reference date is counted up to it,
  so B's H1 is July–September 2026. The generator's date range did not have to change: orders from 2025-01-01 cover
  FY2025 under all three starts.
- **Tiers.** easy Q01, Q03, Q04, Q10, Q12; medium + Q02, Q05, Q07, Q08, Q09, Q11; hard + Q06. The client's
  requirements say, in its own words, which questions the board pack needs this round. Easy is not free of net
  revenue and FX, because Q01 needs both, and Korea time decides Q01 under B. The October refunds bind from medium
  on. README.md has the table of which fact costs which question in each setting.
- **Reference.** The current logic under the setting's conventions. It misses the rename, and leaves unscored
  questions `null`. For Q06 it believes its pantry-label figure is right with even odds and keeps it only when
  ½ × 2 > `dont_know_reward`. So it answers (wrongly) under B and says "don't know" under A (tie) and C.
  **Baseline:** the all-`null` sheet ("not available yet" everywhere), so pure abstention scores 0; the face-value
  sheet scores below it in every setting.
- **Numbers.** See README.md: reference 1.000 in easy and medium and 0.958 / 0.917 / 0.979 in hard. The perfect
  sheet's normalized quality is 1.000 in easy and medium and 1.091 / 1.125 / 1.091 in hard. It differs across
  settings, so no `quality_cap` is set (F2).
- **Validator.** The run warns that the medium and hard references are byte-identical under A and C: both leave Q06
  `null` (not needed in medium, "don't know" in hard). They score 1.000 against 0.958 and 0.979, so the tier still
  adds signal.
- **Open.** `validate-case` stops at the missing translations (`locales/<lang>/explainer.yaml`, `README.<lang>.md`,
  `REVIEW.<lang>.md`), which come later. The other checks were run with that one check set aside, on world seeds 1–3
  (and seeds 1–20 for the world-seed checks), and pass.
- **Checked again.** A second review recomputed the rewards on hand-made sheets (all right, all `null`, one `null`
  and one wrong, unscored answers of every kind), the format rule (missing key, string, boolean, list, NaN,
  Infinity), the abstention trade-off on Q06, the cross-rule-set scores, the README tables (objectives, the
  one-fact-wrong table and the hard-tier answers) and the seed 1–20 ranges; all reproduce. Fixed: a JSON integer too
  large for a float (e.g. 400 digits) made scoring raise instead of breaking `answer_format`; the README's list of
  the questions another rule set moves was incomplete (Q04, Q07, Q09); the Spanish texts read "FY2025 = del …".
  The check "under B, abstaining scores lower than answering wrongly" cannot hold as worded: under every scheme a
  `null` earns more than a wrong answer. What holds is the expectation at the reference's even odds: answering
  beats abstaining under B (1 against 0.5 per question), ties under A and loses under C.
