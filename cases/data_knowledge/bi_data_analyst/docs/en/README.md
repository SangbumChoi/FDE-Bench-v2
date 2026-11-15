# BI Data Analyst — `data_knowledge/bi_data_analyst`

A coffee and tea subscription shop that sells boxes and one-off items to customers in Korea, Japan and the US
(head office in Seoul, all reporting in KRW) sends the agent a CSV export of its order database, a short data
dictionary and twelve questions from its managers: "Can you answer them from the database export? ... please
send back one number per question." The deliverable is `answers.json` with every question id
(`{"Q01": ..., ..., "Q12": ...}`), each a number or `null`. `null` means "don't know": the CEO's board pack shows
the figure as "not available yet". The request names none of the definitions that decide the numbers, and it does
not say what a wrong figure costs. Both are in the hidden requirements, and the simulated client gives them only
when asked.

A setting is a tier and a rule seed. The tier decides which questions the board pack needs this round. The rule
seed draws four of the client's rules, each on its own, from a pool of three values: the first month of the
fiscal year, the active-customer window, the unit money is rounded to, and what a "don't know" is worth against a
right and a wrong answer. That makes 81 combinations per tier. The public panel is rule seeds 4, 12 and 23 (nine
settings, stored in `dataset/answer/` and checked by the validator); any other seed is a private draw whose answers
are published nowhere. **The agent sees the same request and the same data in every setting** (the validator
checks that its prompt and workspace are byte-identical). The simulated client answers from the hidden
requirements of the setting, and the evaluator scores under it. So the case measures two things: whether the agent
finds the definitions and gets the answers right, and whether it says "don't know" when it should (calibrated
abstention). The engagement knobs (full spec vs. clarify first, client persona, data noise, events) apply on top,
as for every case (see [cases/README.md](../../../../README.md)).

The case is audited: [GT.md](../../GT.md) has the ground truth in five parts with the audit's numbers, and
[CLIENT_REVIEW.md](../../CLIENT_REVIEW.md) the passage the client answers each fact from, in every language.

## Data (the same in every setting)

Rendered per locale (labels, product names and the two Markdown files are localized; table and column names stay
English so they load into SQL). Row counts at the public world seed (20261026):

| File | Rows | Content |
|---|---|---|
| `customers.csv` | 1,407 | `customer_id`, `signup_at_utc`, `country` (KR / JP / US), `plan` (subscription / one-off) |
| `accounts_meta.csv` | 1,407 | `account_type`: 1,385 regular, 15 staff, 7 test |
| `products.csv` | 24 | category box / coffee / tea / snacks / pantry / accessories, KRW list price |
| `orders.csv` | 11,174 | 2025-01-01 to 2026-09-30; 10,298 completed, 553 cancelled, 323 payment_failed; KRW 7,878, JPY 1,890, USD 1,406 orders; subtotal, tax (KR and JP 10%, US 7%), total in the order currency |
| `order_items.csv` | 18,557 | quantity and unit price per line |
| `payments.csv` | 10,689 | one row per paid order, including 391 cancelled orders that were paid |
| `refunds.csv` | 793 | tax-inclusive amounts, full or per line; 23 of them dated 2026-10-01 to 2026-10-18 (after the reference date) |
| `fx_rates.csv` | 1,338 | KRW per USD and per JPY for every calendar day from 2024-12-01 to 2026-09-30; the won weakens steadily, from 1,333 to 1,498 KRW per dollar and from 8.82 to 9.97 per yen |
| `questions.md`, `data_dictionary.md` | | the twelve questions (reference date 2026-09-30) and the column list |

The settings never change the data. Orders run from 2025-01-01, so FY2025 is covered and over under every fiscal
year of the pool (it starts in September, April or July 2025). The FY2026 periods are not all over on the
reference date: under an April year the first quarter (April to June) and the first half (April to September) are;
under a July year the first half runs to December; under a September year the first quarter runs to November and
the first half to February 2027. A period that is still running has no figure yet (below).

The exchange rates are the one part of the data that changed with the ground truth audit: they now follow a steady
trend with day-to-day swings (two random draws a day, as before, so every customer, order and refund is unchanged).
A walk without a trend ended near its own average on some worlds, and the FX convention then decided no answer
there (REVIEW.md, F4 and Ground truth audit).

## The questions and the hidden facts

Q01 net revenue FY2025 · Q02 net revenue FY2026 Q1 · Q03 active customers at the reference date · Q04 top customer
by net revenue FY2025 · Q05 orders on the 2026-07-01 sale day · Q06 "pantry" net revenue FY2025 · Q07 average order
value FY2026 H1 · Q08 refund rate FY2025 · Q09 average refund per refunded order FY2025 · Q10 new customers FY2025 ·
Q11 September vs. August 2026 net revenue change · Q12 units per order FY2025.

Thirteen clarification targets (`targets.yaml`), each one thing the client must tell; values in braces are the rule
seed's draw, or derived from it. A target marked *parameter* is exactly one drawn parameter.

| Target | Kind | In force | The fact |
|---|---|---|---|
| `fiscal_year` | missing, parameter `fy_start` | all tiers | the fiscal year starts on the 1st of {fy_start} |
| `fy_naming` | ambiguous | all tiers | a fiscal year is named after the calendar year it starts in: FY2025 = {fy2025}, FY2026 Q1 and H1 as dated |
| `running_period` | missing | all tiers, under a July or September year | a period still running on the reference date has no figure yet: `null`, not the figure to date (finance's habit; the CFO can approve a figure to date) |
| `local_day` | ambiguous | all tiers | timestamps are UTC, days are Korea time (UTC+9) |
| `test_accounts` | missing | all tiers | account_type test is excluded from every figure; staff accounts are real customers and stay in |
| `counted_orders` | ambiguous | all tiers | only completed orders count, even when a cancelled order has a payment row |
| `revenue_ex_tax` | ambiguous | all tiers | net revenue excludes tax: subtotal minus the tax-free part of refunds |
| `refund_period` | ambiguous | medium, hard | a refund is booked in the period of its order, not of the refund |
| `late_refunds` | ambiguous | medium, hard | the export runs to 2026-10-31; refunds made after the reference date count, against their order's period |
| `fx_order_date` | missing | all tiers | convert at the rate of the order's date (Korea time) |
| `active_customer` | ambiguous, parameter `active_days` | all tiers | at least one counted order in the {active_days} days ending on the reference date (from {active_from}) |
| `category_rename` | missing | hard | `snacks` was renamed `pantry` on 2025-10-01; "pantry" covers both labels |
| `report_rounding` | missing, parameter `rounding_unit` | all tiers | money answers rounded to the nearest {rounding_unit} KRW |

What a `null` is worth (0.5, 1 or 1.5 against 2 for a right figure and 0 for a wrong one) is drawn too, and the
client says it when asked, but it is not a target: it is how the answers are judged. It changes no figure of an
analyst who knows the definitions; it decides what an analyst who does not know them should leave `null`.

## Answers and score

Every key Q01..Q12 must be present, with a finite number or `null`. A missing key, or a value that is neither,
breaks `answer_format` (physical). Each question the tier scores earns a reward: 2 if right, 0 if wrong, and
`dont_know_reward` if `null`, which the rule seed draws:

| `dont_know_reward` | wrong | don't know (`null`) | right | all-`null` sheet scores | answer only if P(right) is above | a wrong figure costs, in right figures |
|---|---|---|---|---|---|---|
| 0.5 | 0 | 0.5 | 2 | 0.25 | 25% | 1/3 |
| 1 | 0 | 1 | 2 | 0.50 | 50% | 1 |
| 1.5 | 0 | 1.5 | 2 | 0.75 | 75% | 3 |

The objective (maximize) is the total reward divided by 2 × the number of scored questions, a number in [0, 1].
An answer or a `null` to a question the tier does not score has no effect. The metrics are `scored`, `running`
(the scored questions whose period is still running), `answered`, `right`, `wrong`, `dont_know`,
`accuracy_on_answered` (right / answered), `coverage` (answered / scored), the total `reward`, and the lists of
wrong and "don't know" questions.

**Abstention thresholds.** A sheet that knows the scheme should answer a question only when its chance p of being
right beats "don't know": p × 2 > dont_know_reward. On the normalized scale the all-`null` sheet is 0, so with k
right and w wrong answers a sheet scores about (k − λw) / (scored questions with a figure), λ = dont_know_reward /
(2 − dont_know_reward): a wrong figure costs a third of a right one, one, or three. The client states the scheme as
a business fact: "a wrong figure that reaches the board has to be corrected at the next meeting and costs us
credibility, while 'not available yet' only leaves a gap", followed by the three values. When a `null` is worth
0.5 the client adds that "this time the board would rather see a figure than a gap"; when it is worth 1.5, that
after corrections in the last two packs "the board would much rather see a gap than a wrong figure this time".

**Periods still running.** One kind of question has no figure at all. Under a July year the first half of FY2026
(Q07) is still running on the reference date, under a September year its first quarter (Q02) too. Finance's habit
is to show "not available yet" until a period is over, so the right answer is `null` and the most a valid sheet
earns there is the null's reward. A number for such a question breaks `running_period`, the one bendable rule: the
CFO can approve a figure to date, and with that exception the figure is judged against the exact figure to date.
Under an April year every period is over and the rule is not in force.

Correctness does not depend on the draw except for the money tolerance. Q03, Q04, Q05 and Q10 must match exactly.
Money must be within 0.5% or half the rounding unit, whichever is wider (50, 500 or 5,000 KRW), so the exact
figure rounded as the draw requires always counts. Q11 must be within 0.05 percentage points, and Q08 and Q12
within 0.5%. A percentage given as a fraction is accepted. `violating_examples` asserts, in every setting and on
every world the validator builds, that the exact answers rounded to the setting's unit reach the bound with no
violation (`null` where the period is running), and that with the running-period habit set aside the figures to
date, rounded the same way, are right for every scored question: following a rule never costs a question.

## Tiers: which questions the board pack needs this round

| | easy | medium | hard |
|---|---|---|---|
| **Scored questions** | Q01, Q03, Q04, Q05, Q07, Q10, Q12 (7) | + Q02, Q08, Q09, Q11 (11) | all 12 (+ Q06) |
| **What they test** | Which orders count, test accounts out and staff in, the fiscal year and its naming, Korea-time days (the sale day), net revenue without tax, FX at the order date, the active window, rounding (Q01 and Q07 are the money questions), and the half-year still running under a July or September year | Where a refund is booked (Q08, Q09, Q11), the October refunds of September orders (Q11), and the quarter still running under a September year (Q02) | The snacks → pantry rename (Q06) |
| **What the requirements put out of scope** | "the board pack only needs Q01, Q03, Q04, Q05, Q07, Q10 and Q12 this time … if you answer them we will not use the figures" | "every question except Q06 (the pantry figure)" | Nothing |
| **Clarification targets** | 10 (9 under an April year, where no period is running) | 12 (11) | 13 (12) |
| **Questions with no figure yet** | Q07 under a July or September year | Q07 under July; Q02 and Q07 under September | as medium |

Every tier draws from the same pools, so the rule seed gives the same parameters in all three tiers (s4 is a
September year with a 60-day window in easy, medium and hard alike). What the tier changes is how many questions
depend on them. The ground truth audit moved two questions into easy: Q05 (sale-day orders), so that Korea-time
days decide an easy answer under every draw (on the stored UTC dates the sale day has 102 orders, not 183), and
Q07 (average order value in the first half of FY2026), which brings a running period and a second, small money
figure into easy (rounded to 10,000 KRW it reads 40,000 for 42,416: wrong under a finer unit).

The refund-booking and October-refund facts are stated in every tier but are targets from medium on, where a
refund question is scored: in easy, booking refunds in the refund's period moves no answer on the panel, and the
October refunds only reach Q07 under an April year. The round-scope notes are not targets: an answer to a question
that is not scored has no effect either way, so knowing the scope changes no score.

Questions a sheet gets wrong when it misreads only one fact (the reference otherwise: exact answers rounded to the
setting's unit, `null` where the period is running), at the public world seed (* = the sheet is also invalid):

| Fact: misreading | easy/s4 | easy/s12 | easy/s23 | medium/s4 | medium/s12 | medium/s23 | hard/s4 | hard/s12 | hard/s23 |
|---|---|---|---|---|---|---|---|---|---|
| `fiscal_year`: the next month of the pool | 3* | 3 | 3 | 6* | 4 | 5 | 7* | 5 | 6 |
| `fy_naming`: named after the year it ends in | 4 | 4 | 4 | 6 | 7 | 7 | 7 | 8 | 8 |
| `running_period`: the figure to date | 0* | 0* | – | 0* | 0* | – | 0* | 0* | – |
| `local_day`: the stored UTC dates | 1 | 3 | 1 | 2 | 6 | 3 | 2 | 7 | 3 |
| `test_accounts`: staff left out too | 4 | 4 | 4 | 6 | 7 | 7 | 7 | 8 | 8 |
| `test_accounts`: test accounts kept in | 6* | 6* | 6* | 9* | 9* | 9* | 10* | 10* | 10* |
| `counted_orders`: every order with a payment row | 4 | 4 | 4 | 6 | 7 | 7 | 7 | 8 | 8 |
| `counted_orders`: every order row | 4 | 4 | 5 | 6 | 7 | 8 | 7 | 8 | 9 |
| `revenue_ex_tax`: tax included | 1 | 1 | 2 | 2 | 2 | 4 | 3 | 3 | 5 |
| `refund_period`: booked in the refund's period | (0) | (0) | (0) | 3 | 2 | 2 | 3 | 2 | 2 |
| `late_refunds`: October refunds cut off | (0) | (0) | (1) | 1 | 2 | 2 | 1 | 2 | 2 |
| `fx_order_date`: the reference date's rate | 2 | 1 | 2 | 4 | 2 | 5 | 5 | 3 | 6 |
| `active_customer`: the next window of the pool | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| `category_rename`: `pantry` label only | – | – | – | – | – | – | 1 | 1 | 1 |
| `report_rounding`: another unit of the pool | invalid, or Q07 and Q09 wrong where answered | | | | | | | | |

Figures in brackets are in tiers where the fact is not a target. The first misreading of each fact is its ablation
in the audit; over the audit's 45 settings every one of them is invalid or loses at least 0.11 of the scale in
every tier where the fact is in force (GT.md, part 1), and so they do in all 81 combinations of each tier on world
seeds 1, 2 and 3. A 10,000 KRW unit (s12) is coarse: a money answer within 5,000 KRW counts, so Q09 is hard to miss
there.

## Parameters and rule seeds

Each parameter has one pool, the same in every tier. A rule seed s draws position
`Random("data_knowledge/bi_data_analyst|<name>|s").randrange(3)` of each pool, independently of the others and of
the tier.

| Parameter | Pool (easy, medium, hard) | What it changes | Target |
|---|---|---|---|
| `fy_start`: the fiscal year starts on the 1st of this month, named after the year it starts in | September, April, July (9, 4, 7) | the FY2025, FY2026 Q1 and H1 periods, so the exact Q01, Q02, Q06, Q07, Q08, Q09, Q10 and Q12 and the top customer Q04 (11333 / 10392 / 10247); which periods are still running (Q02 and Q07 / none / Q07); Q03, Q05 and Q11 stay | `fiscal_year` |
| `active_days`: active = a counted order in the last N days | 30, 60, 90 | Q03 (623 / 801 / 881 at the public world) | `active_customer` |
| `rounding_unit`: money reported to the nearest | 100, 1,000, 10,000 KRW | which money answers are valid (a sheet rounded to a finer unit breaks a coarser unit's rule) and the money tolerance (half a unit): a coarser sheet scored under a finer unit misses Q07 or Q09 | `report_rounding` |
| `dont_know_reward`: what a `null` earns (wrong 0, right 2) | 0.5, 1, 1.5 | every `null`'s reward, so the abstention threshold (25%, 50%, 75%), the all-`null` baseline (0.25, 0.50, 0.75) and the reference's objective wherever a period is running | none (how the answers are judged) |

January is not in the fiscal-year pool. The calendar year is what a sheet that never asks assumes, and under a
January year the literal sheet was right on 8 of the 12 questions (quality 0.36 to 0.60 once its rounding was
excused): the client's fiscal year is now never the calendar year, and when it starts is the drawn fact.

`derive_params` adds what the texts quote: `fy2025`, `fy2026_q1` and `fy2026_h1` (date ranges worded per locale,
e.g. "2025-07-01 to 2026-06-30" / "del 2025-07-01 al 2026-06-30", each period whole), `active_from` (the window's
first day) and the fixed ends of the scheme, `right_reward` 2 and `wrong_reward` 0. `admissible` requires rewards
that rise from wrong to don't know to right, a FY2025 inside the data and over by the reference date, a FY2026 that
has started by then and a window inside the data. Every one of the 81 combinations of the current pools passes; the
hook guards pools added later. The requirements carry six `<!-- when: -->` passages: the client's remark for a
`null` worth 0.5 or 1.5, the note on running periods under an April, a July and a September year, and the
running-period line of the hard constraints under a July or September year.

**Public panel.** Seeds 4, 12 and 23 show every value of every pool once:

| Rule seed | `fy_start` | `active_days` | `rounding_unit` | `dont_know_reward` | Derived periods (FY2025 / FY2026 Q1 / FY2026 H1) and window | No figure yet |
|---|---|---|---|---|---|---|
| 4 | 9 (September) | 60 | 100 | 1 | 2025-09-01–2026-08-31 / 2026-09-01–11-30 / 2026-09-01–2027-02-28; active from 2026-08-02 | Q02, Q07 |
| 12 | 7 (July) | 30 | 10,000 | 0.5 | 2025-07-01–2026-06-30 / 2026-07-01–09-30 / 2026-07-01–12-31; active from 2026-09-01 | Q07 |
| 23 | 4 (April) | 90 | 1,000 | 1.5 | 2025-04-01–2026-03-31 / 2026-04-01–06-30 / 2026-04-01–09-30; active from 2026-07-03 | none |

The draw is the same in every tier, so each row is the drawn dict of `easy/sN`, `medium/sN` and `hard/sN`
(their rows in `dataset/answer/answers.csv`). Seeds 12 and 23 draw what they drew before the audit; seed 4, which
drew the January year, now draws September (the pool keeps its size, so every seed keeps its position). Private
seeds draw any of the 81 combinations.

**Parameter binding** (validate-case, from each tier's `s4`): every parameter changes the right answer or the score
with the first other value it tries, in every tier. In easy the reference of s4 scores 0.929; scored under an
April or a July year it falls to the all-`null` level (0.500, quality 0); under a 30- or 90-day window to 0.786
(Q03); under a 1,000 or 10,000 KRW unit it is invalid; and a `null` worth 0.5 or 1.5 moves its objective to 0.893
or 0.964, because Q07 is `null` under the September year. Medium (0.909) and hard (0.917) read the same way. Before
the audit the reward for a `null` moved no reference in easy and medium (the reference answered every scored
question); that finding is closed. Scoring each public seed's reference under the other two seeds of its tier (18
pairs), 14 are invalid (rounding: a 100 KRW sheet under 1,000 or 10,000, a 1,000 KRW sheet under 10,000; running
periods: a figure where the other year has none yet) and the 4 valid ones score 0.

## What an agent must ask

All thirteen targets in hard (ten in easy, twelve in medium; one fewer under an April year). Three of them carry
the rule seed's draw and cannot be carried over from another run or guessed from the data: the fiscal year's first
month (`fiscal_year`), the active window (`active_customer`) and the rounding unit (`report_rounding`); the fiscal
year also decides whether `running_period` is in force. The other nine are the same under every draw. What a "not
available yet" is worth is drawn too and worth asking, although no target: without it an agent cannot know whether
a 60% answer should be given (yes at 0.5 and 1, no at 1.5).

## Rules

| Rule | Class | What breaks it |
|---|---|---|
| `answer_format` | physical | a question id missing, or a value that is neither a finite number nor `null` (checked for all twelve, scored or not) |
| `exclude_test_accounts` | contractual | a scored count or customer-id answer (Q03, Q04, Q05, Q10) equal to the figure with test accounts included (Korea-time days, the setting's periods), where that differs from the figure without them and no reading of the export without test accounts gives the same figure |
| `report_rounding` | contractual | a scored money answer (Q01, Q02, Q06, Q07, Q09) that is not a whole multiple of the setting's unit (100 / 1,000 / 10,000 KRW) |
| `running_period` | business policy (bendable), under a July or September year | a number for a scored question whose period is still running on the reference date (Q07; under September also Q02) |

`report_rounding` was the bendable rule before the audit. Bending it gained nothing (a rounded figure always
counts as right), so it is now the board pack's reporting standard, and the bendable habit is `running_period`:
with the CFO's approved exception a figure to date is judged like any other answer. It adds k / (n − k) of quality
for k running questions of n scored, the same for every null reward: 0.17 in easy, 0.10 (July) or 0.22
(September) in medium, 0.09 or 0.20 in hard. The policy takes its soft-rule penalty off the final score (0.1
under `enterprise_balanced`, 0.05 under `startup_velocity`), in which quality weighs 60%, so the bend nets 0.6 ×
the gain − the penalty: under `enterprise_balanced` about even in easy (0.000), +0.033 and +0.020 under a
September year in medium and hard, −0.040 and −0.045 under July; under `startup_velocity` between +0.005 (hard,
July) and +0.083. So for a sheet below the quality cap the bend pays in some settings and loses in others; a sheet already at
the cap gains nothing and loses the penalty (GT.md, part 2). The bound is for sheets that keep the habit: a bent
sheet is judged with the rule off and reaches quality 1.09 to 1.22, which the cap of 1.0 cuts back to the
reference's credit.

## Situations present

- **Hidden facts:** the thirteen targets above. The data is built so that each one shows up. A QA load test on test
  account 10027 (36 orders of ten hand grinders and five 1 kg blends, April 2025 to March 2026) makes it the top
  customer under every fiscal year when test accounts stay in. Five test orders land in the first minutes of the
  2026-07-01 sale (Korea time), which is still 2026-06-30 in UTC; the sale day has 183 counted orders in Korea
  time, 188 with the test accounts and 102 on the stored UTC dates. Paid cancellations have payment rows. Four pantry products were launched under the new label, while the four older
  ones still say snacks. October refunds of September orders move Q11 from −3.14 to −0.17. The won weakens through
  the period, so the latest rate is never the rate of an order's date.
- **Calibrated abstention:** the reward scheme is hidden too. An agent that has not found a definition, or cannot
  settle a figure, should weigh its chance of being right against the draw's threshold. Saying "don't know"
  everywhere is the baseline (quality 0); answering everything at face value scores below it in every public
  setting. Where the period is still running, "don't know" is the right answer.
- **A bendable habit:** `running_period` (above).
- **Dated events, pressure:** none in the case itself (see REVIEW.md F6). The messy engagement adds the framework's
  generic events.

## Reference and baseline numbers (public world seed 20261026)

The **reference** is a careful analyst who knows every one of the setting's conventions: the exact figure of each
question the tier scores, money rounded to the setting's unit; `null` for the questions the tier does not score
and for a period still running. It reaches the proven bound: a scored question earns at most 2, and one whose
period is still running at most the null's reward. So `quality_cap` is 1.0.

The **baseline** is what finance reports without an analyst: "not available yet" (`null`) for every question. It
earns the draw's don't-know reward on every scored question (0.25 / 0.50 / 0.75 of the maximum), so saying "don't
know" to everything scores 0 on the normalized scale. The **face-value sheet** is the export summed with none of
the client's definitions: calendar-year periods on the stored UTC dates, every order whatever its status, revenue
= order `total` less the refunds dated in the period, every currency at the 2026-09-30 rate, active = ordered in
the last 30 days, "pantry" = the `pantry` label. Here it keeps both rules (test accounts out, money rounded to the
setting's unit, `null` where the period is running) and still scores below the baseline in every public setting.

| Setting | Drawn (fy_start, active_days, rounding_unit, dont_know_reward) | Reference objective = bound | Baseline (all `null`) | Scale width | Face-value sheet | Literal sheet, every rule relaxed |
|---|---|---|---|---|---|---|
| easy/s4 | 9, 60, 100, 1 | 0.929 (6 right, Q07 null) | 0.500 | 0.462 | 0.071 (none right) | 1 right of 7 |
| easy/s12 | 7, 30, 10000, 0.5 | 0.893 (6 right, Q07 null) | 0.250 | 0.720 | 0.036 (none right) | 1 of 7 |
| easy/s23 | 4, 90, 1000, 1.5 | 1.000 (7 right) | 0.750 | 0.250 | 0.000 (none right) | 1 of 7 |
| medium/s4 | 9, 60, 100, 1 | 0.909 (9 right, Q02 and Q07 null) | 0.500 | 0.450 | 0.091 (none right) | 2 of 11 |
| medium/s12 | 7, 30, 10000, 0.5 | 0.932 (10 right, Q07 null) | 0.250 | 0.732 | 0.114 (1 right) | 2 of 11 |
| medium/s23 | 4, 90, 1000, 1.5 | 1.000 (11 right) | 0.750 | 0.250 | 0.000 (none right) | 2 of 11 |
| hard/s4 | 9, 60, 100, 1 | 0.917 (10 right, Q02 and Q07 null) | 0.500 | 0.455 | 0.083 (none right) | 2 of 12 |
| hard/s12 | 7, 30, 10000, 0.5 | 0.938 (11 right, Q07 null) | 0.250 | 0.733 | 0.104 (1 right) | 2 of 12 |
| hard/s23 | 4, 90, 1000, 1.5 | 1.000 (12 right) | 0.750 | 0.250 | 0.000 (none right) | 2 of 12 |

Normalized quality is (objective − baseline) / (reference − baseline); the face-value sheet's and the literal
sheet's are 0 in every row (below the baseline). The scale is 25% to 73% wide, on the public world and on world
seeds 1, 2 and 3 alike (it depends only on the tier, the reward for a `null` and the number of running periods).

The hard-tier answers (exact figure, reference, literal sheet; the literal sheet is the same in every setting):

| Question | s4 exact | s4 reference | s12 exact | s12 reference | s23 exact | s23 reference | Literal sheet |
|---|---|---|---|---|---|---|---|
| Q01 | 292,350,292 | 292,350,300 | 260,862,020 | 260,860,000 | 224,897,826 | 224,898,000 | 190,677,419 |
| Q02 | to date 28,721,364 | null | 94,386,386 | 94,390,000 | 76,593,753 | 76,594,000 | 70,354,473 |
| Q03 | 801 | 801 | 623 | 623 | 881 | 881 | 620 |
| Q04 | 11333 | 11333 | 10247 | 10247 | 10392 | 10392 | 10145 |
| Q05 | 183 | 183 | 183 | 183 | 183 | 183 | 102 |
| Q06 | 53,353,657 | 53,353,700 | 45,450,520 | 45,450,000 | 37,401,000 | 37,401,000 | 4,856,839 |
| Q07 | to date 42,487 | null | to date 42,786 | null | 42,416 | 42,000 | 42,336 |
| Q08 | 5.911 | 5.911 | 6.175 | 6.175 | 6.090 | 6.090 | 5.909 |
| Q09 | 35,119 | 35,100 | 35,621 | 40,000 | 35,923 | 36,000 | 35,856 |
| Q10 | 715 | 715 | 690 | 690 | 655 | 655 | 640 |
| Q11 | −3.140 | −3.140 | −3.140 | −3.140 | −3.140 | −3.140 | −4.186 |
| Q12 | 2.100 | 2.100 | 2.100 | 2.100 | 2.105 | 2.105 | 2.128 |

Q03, Q05 and Q11 do not depend on the fiscal year. "To date" marks a period still running: the exact figure
counted up to the reference date, which is judged only when the habit is bent.

### Literal solution

`literal_solution` answers every question with a number, as the request asks: completed orders only, test accounts
out, net revenue = subtotal less refunds at the order date's rate (as `compute()` does), with the natural reading of
what the client did not say: the calendar year as the fiscal year, the stored UTC dates as days, "active" as ordered
in the last 30 days, "pantry" as the products labelled pantry, money to the whole won and a period still running
counted to date. It is the same sheet in every setting and is invalid in all 9 public settings (quality 0): no
money figure is rounded to the client's unit (`report_rounding`, contractual), and under a July or September year
it gives a number for a period still running (`running_period`). With every rule relaxed, not only the bendable
one, it is right on 1 of 7 questions in easy and 2 of 11 or 12 in medium and hard, below the all-`null` baseline:
quality 0 in every public setting, at most 0.04 over all 81 combinations of a tier on the public world, and at
most 0.24 on world seeds 1 to 3. Its near misses (rounding kept, the running periods left `null`, or both) are
shortcuts of the audit and score the same.

The next most natural literal sheet reads the days off the export instead of the column names: the sale-day orders
start at 15:00 UTC on 2026-06-30 and the export's last order is stamped before 15:00 UTC on the reference date, so
an analyst who looks at the hours counts Korea-time days. That sheet (otherwise the literal one) is also invalid in
every setting as delivered and with the bendable rule relaxed, because its money is not rounded, so it passes the
validator's check. With every rule relaxed it is right on the sale-day count, the September change and, under a
30-day draw, the active customers, and it is no longer below the baseline everywhere: 0.28 / 0.30 / 0.24 in easy /
medium / hard of the public seed 12 (0 under seeds 4 and 23), up to 0.28 / 0.48 / 0.40 over the 81 combinations of
a tier on the public world, and up to 0.62 / 0.52 / 0.44 on world seed 3 (an April year, a 30-day window and a
`null` worth 0.5, where the top customer and the units per order of the calendar year are also the April year's).
For this reading the rounding gate, not the client's definitions, is what keeps the sheet out. With its rules kept
it is the shortcut `literal_local_days`.

## Ground truth audit

`fdebench2 audit-case` measures the case on the public world over 45 settings (per tier the public panel and 12
other combinations); `dataset/audit.json` stores it, GT.md reports it in full.

- **Facts.** All thirteen targets bite in every tier where they are in force: misreading one alone makes the sheet
  invalid or loses 0.11 to 1.00 of the scale. Twelve bite in every measured setting; `report_rounding` in 9 of 15
  easy settings, 14 of 15 medium and 13 of 15 hard (a sheet rounded to a coarser unit stays right where no small
  money figure is answered).
- **Shortcuts.** Eleven sheets a lazy or gaming analyst would send are closed in all 45 settings. Seven are
  invalid or score 0: all `null`, face value, the literal sheet's three near misses, no money figures, only the
  questions with their own dates. Four were added by the check of the audit and score above 0: the all-`null`
  sheet with one safe answer (the units per order, which hardly move with the fiscal year: at most 0.17), only the
  answers that need no client fact (the sale-day orders and the September change on the Korea-time days the
  export shows, and the units per order: at most 0.33), the literal sheet with Korea-time days and every rule kept
  (at most 0.27 in the audit's settings, 0.41 over all 81 combinations of a tier, 0.62 in one combination on world
  seed 3) and the literal sheet made valid under every draw without knowing a parameter (0).
- **Value of asking.** The sheet that never asks (`robust_solution`) earns 0.26 / 0.19 / 0.16 of the credit in
  easy / medium / hard over the audit's settings, so asking is worth 0.74 / 0.81 / 0.84; over all 81 combinations
  of a tier it earns 0.31 / 0.30 / 0.21. It reads the fixed facts as the literal sheet does, except for the days,
  which it reads off the export (Korea time); it knows that money off the client's unit and a number for a period
  still running make a sheet unusable, takes every draw of the pools as equally likely, and delivers the sheet
  with the highest expected credit: on the public world a September guess, with Q02, Q03, Q07 and Q09 left
  `null`. Its credit comes from the three answers that need no client fact (Q05, Q11, Q12) and from its guess in
  the third of the settings where that is right; the sheet with only those three answers earns 0.32 / 0.30 /
  0.27. Before the check of the audit the solver read the days as UTC dates and earned 0.05 / 0.02 / 0.01, less
  than the all-`null` sheet with Q12 alone (0.16 / 0.10 / 0.09 over the 81 combinations), which overstated the
  value of asking as 0.95 to 0.99. A sheet that knows every fixed fact but not the draw (another setting's
  reference) earns 0.30 / 0.43 / 0.33.
- **Reference and bounds.** The reference reaches the proven bound in every setting (gap 0), the best known sheet
  (the answer key for all twelve questions) scores 1.000, `quality_cap` is 1.0, and the scale is 25% to 73% wide.
- **Diagnostics.** `diagnose()` says for each target whether the sheet's figures follow the client's reading or a
  misreading of that fact. It separates the reference from every ablation that bites, never calls the best known
  sheet not enforced, and an ablation flags another target in 3 of 45 settings at most. On sheets that are
  neither (the check of the audit, public world and world seeds 1 to 3, 27 combinations per tier): seven kinds of
  correct-but-different sheets (percentages as fractions, large money to 100,000 KRW or rounded down, ratios to
  two decimals, figures 0.3% off, wrong figures on unscored questions, one more `null`) are never called not
  enforced (0 of 2,268); eleven further misreadings (refunds subtracted with their tax, cancelled orders counted,
  orders refunded in full left out, days in UTC+8 or US Eastern time, the old label only from the rename day, a
  window a day longer, a projection or a zero for a running period, the calendar year, money to a tenth of the
  unit) are caught in every setting where they cost credit (3,114 of 3,114 sheets; 1,140 before the check, which
  added the `VARIANTS` readings, a tighter match of a wrong figure to a reading and the running-period verdict).
  It knows the readings listed in `MISREADINGS` and `VARIANTS`: a variant it does not list is caught only where it
  gives a listed reading's figures (days in UTC+7: 81 of 324 settings; the order total less the tax-free part of
  refunds: 6 of 324; the old snacks label alone: 0 of 108) and is otherwise called not determinable or, from the
  questions the variant leaves right, enforced (132 and 144 of 324).
- **Bending.** See Rules.

## Notes

- Synthetic. Prices, tax rates, FX paths, order rhythms and refund rates are invented; the shop, its customers and
  its accounts are fictional. The fiscal-year, local-day, test-account, net-revenue and rename conventions are the
  common traps of BI work on raw exports, not facts about a real company. The three `null` rewards are design
  choices that set the abstention threshold at 25%, 50% and 75%, not measured costs.
- Known simplifications (REVIEW.md F7): a flat 7% US tax on every order, FX rates on weekends, paid cancellations
  without a reversal row, and sign-ups from 2024-07-01 while the order history starts on 2025-01-01. The QA test
  account 10027 has load-test orders from April 2025 although it signed up in December 2025.
- `validate-case` checks every public setting: deterministic data in five locales, the same agent view in all
  nine, the reference at quality 1.0, a valid baseline worse than the reference, one deliverable per rule that
  breaks only that rule, the parameter pools and the panel, `derive_params` on every combination, that every
  parameter binds in every tier, the literal sheet (invalid or at most 0.2, also with the bendable rule relaxed)
  and the stored audit. It reports no warning for this case.
