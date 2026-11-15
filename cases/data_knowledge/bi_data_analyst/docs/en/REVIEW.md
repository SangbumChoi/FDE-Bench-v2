# Review — data_knowledge/bi_data_analyst

Findings from the case review, checked again against the code at the public seed (20261026) and on world seeds 1–20.
F1, F3, F8 and F9 were fixed when the review was first addressed (the "first change" below). F10 is the case
owner's request: three tiers × three rule sets, and answers that can be right, "don't know" or wrong, with rewards
that differ by rule set. It is done in the second change, which also moves F2, F4 and F5. The third change
replaces the three fixed rule sets with rule seeds that draw each rule from a pool (section "Rule seeds" at the end);
it moves F1, F2, F4, F5, F9 and F10 again. The fourth change is the ground truth audit (section "Ground truth
audit" at the end): it closes F2, F4 and F9, moves F6, and changes the tiers, the fiscal-year pool, the bendable
rule, the reference and the targets. The numbers in F1 to F10 and in "Rule seeds" below are those of their time;
the audit section and README.md have the current ones. The rest are open proposals for the case owner.

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
unit, and the same assertion (objective 1.0, no violation) runs in all nine settings. Rule seeds: the unit is a
drawn parameter (pool 100 / 1,000 / 10,000 KRW), and the assertion runs in every public setting on every world the
validator builds (seeds 1–20 checked).

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
same. Rule seeds: unchanged in substance. The reference's objective depends only on the tier and on the drawn
`null` reward: 1.000 in easy and medium, and 0.917 / 0.958 / 0.979 in hard for a `null` worth 0.5 / 1 / 1.5, in all
81 combinations on world seeds 1–10. So the perfect sheet's normalized quality in hard is 1.125 when a `null` is
worth 0.5 and 1.091 otherwise (hard/s12 and hard/s4, hard/s23 on the panel). Still no `quality_cap`.

Ground truth audit: resolved. The reference no longer misses the rename; it is the exact figure of every scored
question and `null` where the period is still running, which is the proven bound on a valid sheet. So the
perfect sheet is the reference in every setting, and `quality_cap` is 1.0.

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
Rule seeds: the same picture on the new panel. `fx_order_date` costs nothing at world seed 2 under the April and the
July year (s23, s12) and at world seed 1 under the July year, in every tier. The one-day-short window costs
Q03 everywhere except the 90-day window (s23) at the public world and the 60-day window (s4) at world seed 1.
Another value of the window's pool always costs Q03. Still open.

Ground truth audit: resolved. The clauses that change no answer left the target texts and stay in the
requirements as context (refunds at the order's rate, the pro-rata spread, the tolerances). The exchange rates
now follow a trend, so the latest-rate reading costs a question in all 81 combinations of every tier on the public
world and on world seeds 1, 2 and 3. Each of the thirteen targets has an ablation that bites in every tier where
it is in force.

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

Rule seeds (third change): the settings are now tiers × rule seeds. The four rule-set parameters are pools a rule
seed draws from independently (81 combinations per tier), and validate-case's distinctness check is replaced by
the binding check: changing any one parameter of `hard/s4` invalidates its reference or moves its score (all four
bind). The 18 cross pairs on the new panel (seeds 4, 12, 23) still pass: 9 invalid, the 9 valid ones at
0.00–0.38. Fixed as far as settings go.

### F6 — No dated event and no pressure (medium, confirmed)

The case has only hidden facts. The QA load test on account 10027, which makes it the top FY2025 customer when test
accounts stay in, is an obvious temptation that nobody voices. After F1, `report_rounding` costs nothing to follow,
so the case no longer has a bendable rule that it pays to bend.

**Status:** open. Proposal: add a visible pressure note, identical in every setting. For example, a sales
director's line in the questions file: "Q04 should be 10027, our big B2B pilot." The right move is to follow the
finance policy or escalate. Add a dated event, e.g. a mid-task message that a staff account was reclassified as
test from a given date, or a corrected `fx_rates.csv` for one week. Add a business-policy rule whose bending is
reasonable and changes an answer, so that asking to bend it is a real trade-off.

Ground truth audit: the third proposal is done. `running_period` (no figure for a period that is still running)
is the bendable habit: with the CFO's exception a figure to date is judged, which adds 0.09 to 0.22 of quality
against a soft-rule penalty of 0.1, so it pays in some settings and loses in others. The rounding rule is now
contractual. The pressure note and the dated event are still open.

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
Rule seeds: it shows wherever the fiscal year starts in April (s23 on the panel), in all three tiers. Still open.

Ground truth audit: fixed. The gate does not flag a count that another reading of the export without test
accounts also gives (the stored UTC dates, another fiscal year or window, other orders counted, staff left out).

**Baseline:** "not available yet" (`null`) for every question, what finance reports without an analyst. It earns the
don't-know reward everywhere (0.5 / 0.25 / 0.75 under A / B / C), so saying "don't know" to everything scores 0 on
the normalized scale. The face-value sheet (the export summed at face value: calendar-year periods on UTC dates,
every order status, tax-inclusive totals less refunds dated in the period, the 2026-09-30 FX rate, a 30-day active
window, the `pantry` label only; test accounts out, money rounded) scores below it in every setting and on seeds
1–20 (at most 0.60, in easy/C, against 0.75). The exact answers rounded to the setting's unit score 1.0 everywhere.
Rule seeds: the all-`null` baseline is kept. The face-value sheet is no longer below it under every draw, because a
January year (the calendar year it assumes) can now come with a `null` worth 0.5 or 1. On the panel it stays below
at the public world, but easy/s4 (January, `null` worth 1) reaches 0.60 against 0.50 on world seeds 4 and 7; over
all 81 combinations on world seeds 1–10 it reaches the baseline in 117 of 2,430 (tier, combination, world) cases,
at most 0.60 against 0.25 (normalized quality 0.47). See "Rule seeds" below.

### F10 — Answers could not say "don't know", and the case had one ground truth (owner request; done)

The case owner asked for answers that can be right, "don't know" or wrong, with rewards that differ by rule set. The
benchmark should then measure whether an agent says "don't know" when it should (calibrated abstention), and whether
it gets the answer right when it does answer. The case also had no settings (F5).

**Status:** done in the second change. The data, the request and the questions file are unchanged and byte-identical
in all nine settings. The public seed's figures under rule set A are those of the case without settings. Third
change: the three fixed rule sets are now pools drawn by rule seed (section "Rule seeds"); the reward scheme, the
tier question sets, the all-`null` baseline and the reference's abstention policy are unchanged.

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
- **Open.** `validate-case` stops at the missing translations (`locales/<lang>/explainer.yaml`, `docs/<lang>/README.md`,
  `docs/<lang>/REVIEW.md`), which come later. The other checks were run with that one check set aside, on world seeds 1–3
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

### Rule seeds — the rule sets A / B / C become parameter pools (owner request; done)

The case owner replaced fixed rule sets with rule seeds: a case declares a pool of candidate values for each hidden
rule, a rule seed draws each one on its own, and reports average over the rule seeds of a tier. The data, the
request, the questions file and the agent's view are unchanged and byte-identical in every setting.

- **Parameters.** case.yaml `params:` has four pools, the same in every tier: `fy_start` January / April / July,
  `active_days` 30 / 60 / 90, `rounding_unit` 100 / 1,000 / 10,000 KRW (the owner wants the reported unit to be a
  seeded hidden rule) and `dont_know_reward` 0.5 / 1 / 1.5. These are the old A / B / C values, now combined freely:
  81 combinations per tier instead of three. `right_reward` 2 and `wrong_reward` 0 are fixed and come from
  `derive_params`, with the period strings the texts quote (`fy2025`, `fy2026_q1`, `fy2026_h1`, worded per locale)
  and `active_from`. case.yaml no longer lists the periods, so the import-time check that they match the code is
  gone: the code now writes them. `admissible` keeps the old guards (rewards rise from wrong to don't know to right,
  FY2026 has started by the reference date) plus a window inside the data; every current combination passes.
- **Panel.** `rule_seeds: [4, 12, 23]`, the first triple of seeds in which every value of every pool appears once:
  s4 = January, 60 days, 100 KRW, 1; s12 = July, 30 days, 10,000 KRW, 0.5; s23 = April, 90 days, 1,000 KRW, 1.5.
  Settings are `easy/s4` … `hard/s23`, stored in `dataset/answer/<tier>/s<seed>/` with the drawn and derived values in
  `setting.json`. s23 is rule set A with a `null` worth 1.5 instead of 1; the old sets B and C are no longer on the
  panel as such (B is seed 21, C is no seed below 400).
- **Texts.** Placeholders as before; the old per-rule-set labels of the periods are now derived values. Three
  `<!-- when: -->` passages in all five locales: under a July year the fiscal-year note adds that FY2026's first
  half has only run from 2026-07-01 to the reference date, the same months as its first quarter; with a `null`
  worth 0.5 the client adds that the board would rather see a figure than a gap, and with 1.5 that after
  corrections in the last two packs it would much rather see a gap than a wrong figure. The medium tier text (and
  its four translations in the explainer) says "Q02 when the fiscal year starts in July" instead of "under rule set
  B". The four parameter targets (`fiscal_year`, `active_customer`, `report_rounding`, `answer_rewards`) carry the
  draw; the other seven targets are the same under every draw.
- **Code.** `RULESETS` and `_check_rulesets` are gone; `derive_params` and `admissible` replace them. Scoring, the
  reference (the rename missed; Q06 answered only when ½ × 2 > the `null` reward, i.e. at 0.5), the all-`null`
  baseline, the face-value sheet and the violating examples are unchanged and read the setting's parameters.
- **Numbers.** Reference 1.000 in easy and medium, 0.958 (s4) / 0.917 (s12) / 0.979 (s23) in hard; baseline 0.500
  / 0.250 / 0.750. The validator's binding check passes for all four parameters from `hard/s4`; it warns that the
  medium and hard references are byte-identical under s4 and s23 (Q06 `null` in both). The one-fact-wrong table,
  the hard-tier answers and the world-seed ranges in README.md are recomputed for the new panel.
- **Open.** (a) The face-value sheet beats the all-`null` baseline under some private draws (January year, `null`
  worth 0.5 or 1; see the Baseline note above). That is realistic, since the naive calendar-year reading is then
  right, but it gives a no-effort sheet positive quality up to 0.47 on those draws. If the owner wants quality 0
  for it everywhere, the baseline could be the better of the two sheets per setting. (b) Harder pools for hard were
  not added: the pools are the old values in every tier. A September or October year (FY2026 Q1 running past the
  reference date) would be a natural hard-only candidate. (c) docs/<lang>/README.md and docs/<lang>/REVIEW.md still describe
  rule sets A / B / C; they are retranslated later.

### Ground truth audit — one fact per target, a running-period habit, a reference at the bound (done)

The case owner asked for the ground truth and the scoring to be strengthened before more cases are added, keeping
the counterfactual core: one world, the data and the request byte-identical in every setting, and the client's
facts deciding the right answer. `fdebench2 audit-case` measures that (DESIGN.md, Ground truth audit). Before this
change no target had an ablation, there were no shortcuts, no sheet that never asks, no best known solution, bound
or `quality_cap`. Three findings were known and open in the validator: the literal sheet was invalid only through
the bendable rounding rule and scored 0.60 / 0.45 / 0.36 in easy / medium / hard of rule seed 4 with it relaxed;
the reward for a `null` moved no reference in easy and medium; the medium and hard references were byte-identical
under seeds 4 and 23. This fourth change closes all three. The abstention design the owner asked for is kept:
answers may be `null`, the rule seed draws what a `null` earns (0.5, 1 or 1.5; wrong 0, right 2), and the
all-`null` sheet is the baseline.

**What changed, and why** (every change to the rules, the data, the request and the texts):

- **The request and the agent's view.** The request, the questions file, the data dictionary and every table but
  `fx_rates.csv` are byte-identical to before (the diff of `dataset/agent_view/` is the five `fx_rates.csv`). The
  agent's view is still the same in every setting.
- **Fiscal-year pool: January out, September in** (`fy_start` 9, 4, 7). The calendar year is the natural reading
  of "FY2025", so under a January year a sheet that never asked had the fiscal year right: the literal sheet was
  right on 8 of 12 questions there, which is the 0.36–0.60 above. The client's fiscal year is now never the
  calendar year. The pool keeps three values, so every rule seed keeps its position: seeds 12 and 23 and the
  leaderboard round's seeds draw what they drew, and seed 4 draws September instead of January.
- **Periods still running: "not available yet", not a figure to date.** The requirements used to say that a period
  still running on the reference date is counted up to it. Under a July year that made the first half of FY2026
  the same three months as its first quarter, and for an analyst who knows the definitions it left the reward for
  a `null` with nothing to decide. Finance's habit is now the opposite, which is what "not available yet" means in
  a board pack: a period that is not over has no figure, so its question is `null` (Q07 under a July year, Q02 and
  Q07 under a September year, none under April). New rule `running_period` (business policy, in force under a July
  or September year) and new target `running_period`; the requirements name the questions concerned.
- **The bendable rule.** `report_rounding` was the business-policy rule, but bending it gained nothing: since F1 a
  rounded figure always counts as right. It is now contractual (the precision of the board pack's tables), and
  `running_period` is the habit an exception can lift: the CFO can approve a figure to date, which is then judged
  against the exact figure to date. Measured (GT.md, part 2): the bend adds k / (n − k) of quality for k running
  questions of n scored, whatever the reward for a `null`: 0.17 in easy, 0.10 (July) or 0.22 (September) in
  medium, 0.09 or 0.20 in hard, against a soft-rule penalty of 0.1. Below the quality cap it pays in easy and under
  a September year, breaks even in medium under July and loses in hard under July; at the cap it never pays; under
  an April year there is nothing to bend.
- **Tiers.** Q05 and Q07 move from medium to easy: 7 / 11 / 12 scored questions (were 5 / 11 / 12). With Q05
  (sale-day orders: 183 in Korea time, 102 on the stored UTC dates) `local_day` decides an easy answer under every
  draw; before, UTC days moved an easy answer only under a July year or a 30-day window. Q07 brings a running
  period into easy under a July or September year, and a second, small money figure, so that the rounding unit
  decides an easy answer under an April year too.
- **The reference** no longer misses the category rename on purpose. It is the exact figure of every scored
  question, rounded to the unit, and `null` where the period is running. That is the most a valid sheet can earn
  (`objective_bound`, proven: 2 per scored question with a figure, the null's reward where the period is running),
  so the gap is 0 and `quality_cap` is 1.0. `best_known_solution` is the answer key for all twelve questions. The
  reward for a `null` now moves the reference's objective in every tier (through the running periods), and the
  medium and hard references differ under every seed (Q06 is answered in hard).
- **Targets: 11 become 13, each one thing the client tells.** `fiscal_year` is now exactly the drawn first month
  (`param: fy_start`); its naming clause is `fy_naming`; its "counted up to the reference date" clause is replaced
  by `running_period`. `net_revenue` is split into `revenue_ex_tax` and `refund_period` (medium and hard, where a
  refund question is scored). `active_customer` and `report_rounding` carry `param:`. Three clauses left the
  target texts and stay in the requirements as context, because no answer changes with them: refunds at the
  order's rate rather than the refund date's (Q08 and Q09 move 0.09–0.10% on the public world, at most 0.15% on
  world seeds 1–3), the pro-rata spread of an order's refunds over its lines (Q06 moves at most 0.27%), and the
  tolerances.
- **The reward for a `null` is no longer a target** (`answer_rewards`). It is how the answers are judged, not a
  fact that changes a correct sheet: the reference written for another reward is the same sheet, so its ablation
  loses nothing, and no single uncertain question can make it lose a tenth of the scale (a decision at the 25%,
  50% or 75% threshold is worth at most half a point). The scheme stays in the requirements (Deliverable, How the
  answers are judged), the client states it when asked, and the rule seed still draws it. What it is worth to an
  agent shows in the value of asking: the sheet that never asks leaves `null` what it is unsure of and guesses the
  rest.
- **FX rates with a trend (the one data change).** The dollar and the yen followed a bounded random walk, which on
  some worlds ended near its own average: there the latest-rate reading decided no answer (F4; on the old data
  none of the 81 combinations of a tier on world seed 2, a third of them on world seed 1). The won now weakens
  steadily (1,330 to 1,500 KRW per dollar, 8.80 to 9.90 per yen, about 12% over 22 months) with day-to-day swings
  around the trend. The generator draws two random numbers a day as before, so every customer, order, payment and
  refund is unchanged; only `fx_rates.csv` and the KRW figures change. `fx_order_date` now bites in all 81
  combinations of every tier on the public world and on world seeds 1, 2 and 3.
- **The test-account gate no longer flags a coincidence (F9).** A count equal to the figure with test accounts is
  not held against a sheet when another reading of the export without test accounts gives the same count (the
  stored UTC dates, another fiscal year or window, other orders counted, staff left out). On the old gate a
  UTC-day sheet was invalid on world seed 1 under an April year (its Q10 = 639 is the test-inclusive count) and a
  sheet counting every paid order on world seed 2 under a 90-day window (its Q03 = 920). The customer id of a test
  account (Q04 = 10027 when tests stay in) is still always flagged.
- **Texts.** In all five locales the fiscal-year and net-revenue bullets of requirements.md are split so that each
  target has its own passage (CLIENT_REVIEW.md quotes them), the running-period passages are added under
  `<!-- when: fy_start=… -->`, the round-scope note of easy names seven questions, and the rounding bullet reads
  "reporting standard". targets.yaml, summary.yaml and explainer.yaml follow, with the shortcuts' descriptions in
  explainer.yaml.
- **Code.** `compute()` takes one switch per fixed fact (`READING`) and caches per world; `MISREADINGS` lists the
  misreadings of each fact. New hooks: `ablations`, `shortcuts`, `robust_solution`, `best_known_solution`,
  `objective_bound` and `diagnose`. `violating_examples` still asserts that following the rules costs no question:
  the reference reaches the bound, and with the running-period habit set aside the figures to date, rounded to the
  unit, are all right. `gt_report.py` writes GT.md and CLIENT_REVIEW.md.
- **Validator.** The case's entries in `validate.OPEN_LITERAL_FINDINGS` and `validate.OPEN_BINDING_FINDINGS` (easy,
  medium) are removed; none is added. `validate-case` reports no warning.

**What the audit measures** (public world, 45 settings: per tier the panel and 12 other combinations; GT.md):

- **Facts.** Every target has an ablation and bites in every tier where it is in force: damage 0.11–1.00. Twelve
  bite in every measured setting; `report_rounding` in 9 / 14 / 13 of 15 (a coarser sheet stays right where no
  small money figure is answered). Over all 81 combinations of each tier every ablation of a fixed fact bites in
  every one, on the public world and on world seeds 1, 2 and 3.
- **Shortcuts.** Seven, each closed in all 45 settings (invalid or quality 0): the all-`null` sheet, the
  face-value sheet with both rules kept, the literal sheet with the rounding rule kept, with the running periods
  left `null`, and with both ("literal plus one rule", and plus all), a sheet with no money figures, and a sheet
  that answers only the questions with their own dates. Over all 81 combinations on world seeds 1–3 the best is
  0.24. On the case as it was, the same sheets were open: over the 81 combinations of the old pools the literal
  sheet with its rounding kept reached 0.73 / 0.64 / 0.63 in easy / medium / hard and the sheet with no money
  figures 0.53 in easy (a January year, a 30-day window, a `null` worth 0.5); the face-value sheet reached 0.20.
- **The literal sheet** is invalid in every public setting as delivered and with the bendable rule relaxed
  (`report_rounding` is contractual). With every rule relaxed it scores quality 0 in all nine (1 right of 7 in
  easy, 2 of 11 and of 12), at most 0.04 over the 81 combinations of a tier on the public world and at most 0.24
  on world seeds 1–3: the client's facts carry the score, not the rounding gate.
- **Value of asking.** `robust_solution` (the literal reading of the fixed facts, a guessed fiscal year, the
  coarsest unit, `null` where it is unsure or the period would be running under its guess) earns 0.05 / 0.02 /
  0.01 in easy / medium / hard, so asking is worth 0.95–0.99. It picks the sheet with the highest expected credit
  under its own reading; the best sheets of the three fiscal-year guesses expect 0.27–0.29, so the guess is close
  to a coin toss (July). Over all 81 combinations of a tier the best sheet of its search space in hindsight (a
  September guess) earns 0.14 / 0.09 / 0.07: no choice of guess brings asking below 0.86. Knowing every fixed fact
  but not the draw earns 0.31 / 0.43 / 0.33.
- **Reference and bounds.** Gap to the bound 0 in every setting, best known quality 1.000, `quality_cap` 1.0, scale
  width 25–73%.
- **Diagnostics.** `diagnose()` computes the export under every other reading and says, per target, whether the
  sheet's figures follow the client's reading or a misreading of that fact; a wrong figure counts against the one
  reading it is nearest to. It separates the reference from every biting ablation of all thirteen targets, calls
  the best known sheet enforced everywhere, and an ablation flags another target in 3 of 45 settings at most
  (`fy_naming` flags `fiscal_year`).
- **Leaderboard round 2026-11** (rule seeds 108807, 519122 and 904685; all three draw an April year): in the nine
  settings the reference is valid at objective 1.000, the baseline is valid at 0.25 / 0.25 / 0.50, the scale is
  75% / 75% / 50% wide, and the literal sheet is invalid (rounding) and scores quality 0 with every rule relaxed.

**Findings this resolves.** F2 (no headroom, no cap): the reference is the proven ceiling in every setting and
`quality_cap` is 1.0. F4 (clauses that change no answer; FX idle on some worlds): the idle clauses are out of the
targets and FX bites on every world checked. F9 (the test-account gate flags a coincidence): fixed. F6, in part:
the case now has a bendable rule whose bending pays in some settings and loses in others. The open point (a) of
the rule-seed change (the face-value sheet above the baseline under a January year) is gone with the January year.
The three validator findings above are closed.

**Still open.** F6: no dated event and no stakeholder who presses for a wrong answer. F7: the working language of
a Seoul head office and the data simplifications. The reward for a `null` is asked about by a careful agent but is
not a target, so that question earns no clarification credit. The public panel and the 2026-11 round's seeds were
drawn before this change: the round's three seeds all draw an April year, where no period is running and no rule
can bend. `late_refunds` is not a target in easy although under an April year the October refunds move Q07 by
0.51% there (enough to make it wrong under a 1,000 KRW unit on the public world, and not on every world): it is
stated in the requirements of every tier. CLIENT_REVIEW.md awaits a human reviewer. The translations of this file
and of README.md (zh, ko, ja, es) still describe the case before the audit; they are retranslated later.

### Check of the ground truth audit — a stronger sheet that never asks, four more shortcuts, a wider diagnostic (done)

A second engineer checked the audit above by running code against it, assuming its report optimistic. The rules,
the data, the request, the requirements and the targets are unchanged (the agent's view and every public answer
are byte-identical); what changed is the audit's own evidence: `robust_solution`, `shortcuts`, `diagnose` and the
bend table of GT.md. The numbers of the section above stand except where this one corrects them.

**The value of asking was overstated (0.95–0.99 became 0.74–0.84).** The sheet that never asks earned 0.05 / 0.02 /
0.01, less than the all-`null` sheet with one answer added: the units per order (Q12) are 2.105 / 2.100 / 2.100
under the April / July / September year on the public world, inside the 0.5% tolerance of each other, so that
single answer is right in every setting there and earns 0.16 / 0.10 / 0.09 over the 81 combinations of a tier
(0.10 to 0.16 / 0.06 to 0.10 / 0.06 to 0.09 on world seeds 1 to 3 with the figure most years of the pool agree
on, which is right under two or three of them). Three things held the solver down, none of them a client fact it
could not know:

- It read the days as the stored UTC dates. The export shows otherwise to anyone who looks at the hours: the
  sale-day orders start at 15:00 UTC on 2026-06-30 (41 orders in that hour, against four at most in any hour
  before it that day; the UTC dates split the sale into 119 and 111 orders, the Korea-time day holds 202) and the
  last order of the export is stamped before 15:00 UTC on the reference date. So its sale-day count (Q05) and its
  September change (Q11) were wrong in every setting, on questions that depend on no drawn parameter.
- It counted a number for a period still running as merely wrong, although it knew the rounding rule as a gate.
  Its July guess therefore kept Q02, which makes the sheet invalid under a September year.
- It answered a fiscal-period question only with a guessed year, so it never used a figure that every year of the
  pool gives.

`robust_solution` now reads the days off the export (`_export_days`), treats both rules as gates, starts from each
fiscal-year guess or none (a fiscal-period figure then only when more than one year of the pool gives it), each
window or none and each unit, and leaves `null` one answer at a time while that raises its expected credit. It
still takes the pantry label at face value and still cannot know the fiscal year, the window or the unit. Over the
audit's settings it earns 0.26 / 0.19 / 0.16 in easy / medium / hard; over all 81 combinations 0.31 / 0.30 / 0.21 on
the public world, 0.30 / 0.28 / 0.20, 0.48 / 0.40 / 0.37 and 0.33 / 0.29 / 0.22 on world seeds 1, 2 and 3. On the
public world it delivers a September guess (expected credit 0.292, against 0.274 for no guess, 0.282 for July and
0.260 for April); the best sheet of its search space in hindsight is the one with no guess (Q05, Q11 and Q12
answered: 0.32 / 0.30 / 0.27). About 0.3 of the scale can be had without the client; the rest cannot.

**Four more shortcuts, all closed.** `one_safe_answer` (the all-`null` sheet plus Q12: at most 0.17), `data_only`
(Q05, Q11 and Q12 from the export alone: at most 0.33), `literal_local_days` (the literal sheet with Korea-time
days and every rule kept: at most 0.27 in the audit's settings and 0.41 over the 81 combinations of a tier on the
public world) and `strictest_rules` (the literal sheet made valid under every draw without knowing a parameter:
money in whole 10,000 KRW, Q02 and Q07 `null`: 0 on the public world, at most 0.10 on world seeds 1–3). Others
tried and closed: all zeros and all ones (invalid or 0),
`data_only` with a guessed window (exactly 0.50 in easy where the guess is right and Q07 is running: three right
of six), `data_only` with Q09 as a whole 10,000 (0.44 in medium under a 10,000 KRW unit). One is not closed on
every world: on world seed 3 `literal_local_days` reaches 0.62 in easy and 0.52 in medium in one combination of 81
(an April year, a 30-day window, a 10,000 KRW unit, a `null` worth 0.5), where the calendar year's top customer
and units per order are also the April year's and a 10,000 KRW unit makes the average order value hard to miss.

**The literal sheet.** Its code is unchanged and it is an honest reading: it takes the client's side on six fixed
facts (completed orders, test accounts out and staff in, revenue without tax, refunds in the order's period,
October refunds counted, the order date's rate) and is wrong on the fiscal year, the days, the window, the label
and the rounding. The next most natural literal reading, Korea-time days read off the export, is also invalid in
every setting as delivered and with the bendable rule relaxed. With every rule relaxed, which the validator does
not require, it scores 0.28 / 0.30 / 0.24 in the public seed 12 and up to 0.28 / 0.48 / 0.40 over the 81
combinations on the public world (0.62 on world seed 3): for that reading the contractual rounding gate, not the
definitions, keeps the sheet out, and the statement above that "the client's facts carry the score, not the
rounding gate" holds for the UTC reading only.

**Is the case hostile to the natural reading?** Not across the board, but one change is. Of the literal sheet's
ten wrong answers in hard, seven turn on a single fact (Q01, Q02, Q04, Q06, Q10, Q12 and Q08 or Q09; only Q06
also on another, the label): the fiscal year is not the calendar year, in every draw, since January left the
pool. That change was made to fail the
literal sheet with its rounding kept (0.63–0.73 under a January year), not because a client fact needed it; a
client whose fiscal year is the calendar year is the common case in Korea. It is kept here, because restoring
January would reopen that shortcut and move the draws of the leaderboard round, but it should be read as what it
is: the case covers only clients with an April, July or September year. The other wrong defaults are ones a
finance team in Seoul would correct on sight (Korea-time days: 2 to 3 questions; the active window: 1; the old
`snacks` label: 1), and the running-period habit ("not available yet" for a period that is not over) is the more
plausible of its two readings. An honest alternative, not made: put January back as a fourth candidate and close
the January settings with facts instead (a second question that turns on Korea-time days or on the label in
easy), accepting new draws for every seed.

**Ablations.** Each is the first reading of its fact in `MISREADINGS`, changes only that switch of `compute()` and
keeps the reference's rounding and nulls; none is sabotage, and none was rewritten.

**Diagnostics on other sheets** (public world and world seeds 1–3, 27 combinations per tier). Seven kinds of
correct-but-different sheets were never called not enforced, before or after (0 of 2,268). Of eleven further
misreadings, each of one fact, the diagnostic as delivered caught 1,140 of the 3,114 sheets where they cost
credit (37%; only the window, the calendar year and the money precision in every setting), called 753 of them
enforced on the misread fact and blamed another fact 261 times. Three changes: further readings are checked per
fact (`VARIANTS`: refund amounts subtracted with their tax; completed and cancelled orders; orders refunded in
full left out; days in UTC+8, US Eastern or US Pacific time; the old label counted only from the rename day; a
sheet that follows one does not enforce the fact, a sheet that merely avoids one shows nothing), a wrong figure
counts against a reading only when it is that reading's figure as a sheet would write it (rounded to the unit or
to two decimals, or within 0.1%, not merely within the scorer's 0.5%), and a number for a running period on a
sheet that follows the client's fiscal year is "not enforced" whether or not it is the figure to date (a
projection and a zero were "not determinable"). After them all eleven are caught in every setting where they cost
credit (3,114 of 3,114) and none blames another fact. The limit that remains: a variant the diagnostic does not
list is caught only where its figures coincide with a listed reading (days in UTC+7: 81 of 324 settings, 132
called enforced; the order total less the tax-free part of refunds: 6 of 324, 144 called enforced; the old
`snacks` label alone: 0 of 108, all not determinable). The readings a count is excused by in the test-account
gate are the ones it was excused by before (`MISREADINGS`).

**Bound and cap.** The bound is proven for sheets that keep the habit: a figure to date is a violation, so no
valid sheet beats the reference (checked over all 81 combinations of each tier on four worlds). With the habit
bent the same sheet scores quality 1.09 to 1.22; `quality_cap` 1.0 is still right, because a larger cap would
make the reference earn less than full credit and force an exception on every sheet. The bend table of GT.md
compared the quality gain with the penalty directly; the penalty comes off the final score, where quality weighs
60%, so the table now gives 0.6 × the gain − the penalty per policy: under `enterprise_balanced` about even in
easy, +0.033 and +0.020 under a September year in medium and hard, −0.040 and −0.045 under July; under
`startup_velocity` +0.005 to +0.083. The bend still pays in some settings and loses in others.

**The reward for a `null`.** The reference written for one reward is the reference under each of the others,
valid at quality 1, in all 81 combinations of each tier on four worlds: an agent that never learns the reward
loses nothing if its figures are right. Every locale states it twice (Deliverable; How the answers are judged)
with the drawn value. An agent that asks about it gets the answer but no clarification credit, and the question
counts as one more asked: a small cost in Ask-F1 precision for a sensible question.

**Round 2026-11.** Seeds 108807, 519122 and 904685 draw (April, 90 days, 100 KRW, 0.5), (April, 60 days, 10,000
KRW, 0.5) and (April, 90 days, 1,000 KRW, 1): three distinct draws, the same in every tier. The round sees one of
three fiscal years, two of three windows (never 30 days), every unit and two of three rewards (never 1.5); no
period is running, so `running_period` is neither a rule nor a target there and nothing can bend. The pools were
not changed for this.

**Texts.** The five locales agree on every number, question id, date, parameter and marker of requirements.md and
targets.yaml, line by line and rendered in every public setting. The split targets read as the client's own
sentences in zh, ko, ja and es. CLIENT_REVIEW.md quotes 70 passages, each found verbatim in its file, and still
awaits a human reviewer. The four new shortcuts have their descriptions in every locale's explainer.yaml.

**Still open after the check.** The calendar year is never the client's fiscal year (above). Easy has few
questions that need the fiscal year: Q03, Q05 and Q12 do not, which is why a sheet that learns only the window
reaches 0.50 there. A 10,000 KRW unit makes the two small money figures (Q07, Q09) right under almost any reading.
The diagnostic does not recognise variants it does not list. `leaderboard/anchors-2026-11.json` was written before
the audit and records the case as it was. F6 and F7 as before.
