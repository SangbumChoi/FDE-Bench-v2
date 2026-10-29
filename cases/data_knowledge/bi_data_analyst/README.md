# BI Data Analyst — `data_knowledge/bi_data_analyst`

A coffee and tea subscription shop that sells boxes and one-off items to customers in Korea, Japan and the US
(head office in Seoul, all reporting in KRW) sends the agent a CSV export of its order database, a short data
dictionary and twelve questions from its managers: "Can you answer them from the database export? ... please
send back one number per question." The deliverable is `answers.json` with every question id
(`{"Q01": ..., ..., "Q12": ...}`), each a number or `null`. `null` means "don't know": the CEO's board pack shows
the figure as "not available yet". The request names none of the definitions that decide the numbers, and it does
not say what a wrong figure costs. Both are in the hidden requirements, and the simulated client gives them only
when asked.

The case has nine ground truths: three tiers × three rule sets. **The agent sees the same request and the same
data in all nine** (the validator checks that its prompt and workspace are byte-identical). What changes is which
questions the board pack needs this round, the client's conventions (fiscal year, active window, rounding unit)
and what a right, a "don't know" and a wrong answer are worth. The simulated client answers from the hidden
requirements of the setting, and the evaluator scores under it. So the case measures two things: whether the
agent finds the definitions and gets the answers right, and whether it says "don't know" when it should
(calibrated abstention). The engagement knobs (full spec vs. clarify first, client persona, data noise, events)
apply on top, as for every case (see [cases/README.md](../../README.md)).

## Data (the same in every setting)

Rendered per locale (labels, product names and the two Markdown files are localized; table and column names stay
English so they load into SQL). Row counts at the public seed (20261026):

| File | Rows | Content |
|---|---|---|
| `customers.csv` | 1,407 | `customer_id`, `signup_at_utc`, `country` (KR / JP / US), `plan` (subscription / one-off) |
| `accounts_meta.csv` | 1,407 | `account_type`: 1,385 regular, 15 staff, 7 test |
| `products.csv` | 24 | category box / coffee / tea / snacks / pantry / accessories, KRW list price |
| `orders.csv` | 11,174 | 2025-01-01 to 2026-09-30; 10,298 completed, 553 cancelled, 323 payment_failed; KRW 7,878, JPY 1,890, USD 1,406 orders; subtotal, tax (KR and JP 10%, US 7%), total in the order currency |
| `order_items.csv` | 18,557 | quantity and unit price per line |
| `payments.csv` | 10,689 | one row per paid order, including 391 cancelled orders that were paid |
| `refunds.csv` | 793 | tax-inclusive amounts, full or per line; 23 of them dated 2026-10-01 to 2026-10-18 (after the reference date) |
| `fx_rates.csv` | 1,338 | KRW per USD and per JPY for every calendar day from 2024-12-01 to 2026-09-30 |
| `questions.md`, `data_dictionary.md` | | the twelve questions (reference date 2026-09-30) and the column list |

The data is unchanged by the settings: the files are byte-identical to the case without settings. Orders run from
2025-01-01, so every fiscal year the rule sets need is covered (FY2025 from January, April or July 2025). The one
period that does not fit is the first half of FY2026 under a July year (July–December 2026). The requirements say,
in every rule set, that a period still running on the reference date is counted up to the reference date, so that
half is July–September 2026 under B. Under A it ends on the reference date, and under C it is over.

## The questions and the hidden facts

Q01 net revenue FY2025 · Q02 net revenue FY2026 Q1 · Q03 active customers at the reference date · Q04 top customer
by net revenue FY2025 · Q05 orders on the 2026-07-01 sale day · Q06 "pantry" net revenue FY2025 · Q07 average order
value FY2026 H1 · Q08 refund rate FY2025 · Q09 average refund per refunded order FY2025 · Q10 new customers FY2025 ·
Q11 September vs. August 2026 net revenue change · Q12 units per order FY2025.

Eleven clarification targets (`targets.yaml`; values in braces come from the rule set):

| Target | Kind | Tiers | The fact |
|---|---|---|---|
| `fiscal_year` | missing | all | the FY starts on the 1st of {fy_start} and is named after its start year; FY2025, FY2026 Q1 and H1 as dated; a period still running on the reference date counts up to it |
| `local_day` | ambiguous | all | timestamps are UTC, days are Korea time (UTC+9) |
| `test_accounts` | missing | all | account_type test is excluded from every figure; staff stay in |
| `counted_orders` | ambiguous | all | only completed orders count, even when a cancelled order has a payment row |
| `net_revenue` | ambiguous | all | subtotal (ex tax) minus refunds ex tax, booked in the order's period, not the refund's |
| `late_refunds` | ambiguous | medium, hard | the export runs to 2026-10-31; refunds made after the reference date count, against their order's period |
| `fx_order_date` | missing | all | convert at the order date's rate; refunds use the order's rate |
| `active_customer` | ambiguous | all | at least one counted order in the {active_days} days ending on the reference date |
| `category_rename` | missing | hard | `snacks` was renamed `pantry` on 2025-10-01; "pantry" covers both labels, an order's refunds pro rata over its lines |
| `report_rounding` | missing | all | money answers rounded to the nearest {rounding_unit} KRW (and how answers are checked) |
| `answer_rewards` | missing | all | `null` ("not available yet") is accepted; finance values a right figure at 2, a `null` at {dont_know_reward}, a wrong figure at 0 |

## Answers and score

Every key Q01..Q12 must be present, with a finite number or `null`. A missing key, or a value that is neither,
breaks `answer_format` (physical). Each question the tier scores earns a reward:

| | wrong | don't know (`null`) | right |
|---|---|---|---|
| A | 0 | 1 | 2 |
| B | 0 | 0.5 | 2 |
| C | 0 | 1.5 | 2 |

The objective (maximize) is the total reward divided by 2 × the number of scored questions, a number in [0, 1]. A
sheet that is right everywhere scores 1. A sheet that says "don't know" everywhere scores 0.5, 0.25 or 0.75. An
answer or a `null` to a question the tier does not score has no effect. The metrics are `scored`, `answered`,
`right`, `wrong`, `dont_know`, `accuracy_on_answered` (right / answered), `coverage` (answered / scored), the total
`reward`, and the lists of wrong and "don't know" questions.

**Abstention thresholds.** A sheet that knows the scheme should answer a question only when its chance p of being
right beats "don't know": p × 2 > dont_know_reward, i.e. p > 50% under A, p > 25% under B and p > 75% under C. The
client states the scheme as a business fact, and it is a clarification target (`answer_rewards`, kind missing):
"a wrong figure that reaches the board has to be corrected at the next meeting and costs us credibility, while 'not
available yet' only leaves a gap", followed by the three values.

Correctness is unchanged from the case without settings, except for the money tolerance. Q03, Q04, Q05 and Q10 must
match exactly. Money must be within 0.5% or half the rounding unit, whichever is wider (500, 5,000 or 50 KRW), so the
exact figure rounded as the rule set requires always counts. Q11 must be within 0.05 percentage points, and Q08 and
Q12 within 0.5%. A percentage given as a fraction is accepted. `violating_examples` asserts that the exact answers,
rounded to the setting's unit, score 1.0 with no violation, in every setting and on every world the validator builds.

## Tiers: which questions the board pack needs this round

| | easy | medium | hard |
|---|---|---|---|
| **Scored questions** | Q01, Q03, Q04, Q10, Q12 (5) | + Q02, Q05, Q07, Q08, Q09, Q11 (11) | all 12 (+ Q06) |
| **What they test** | Which orders count, test accounts out and staff in, the fiscal year, the active window, rounding (Q01 is the one money question) | Net revenue (tax, refund booking), FX at the order date, Korea-time days at month, quarter and sale-day edges, and the October refunds of September orders | The snacks → pantry rename (Q06) |
| **What the requirements put out of scope** | "the board pack only needs Q01, Q03, Q04, Q10 and Q12 this time … if you answer them we will not use the figures" | "every question except Q06 (the pantry figure)" | Nothing |
| **Clarification targets** | 9: fiscal year, local day, test accounts, counted orders, net revenue, FX, active customer, rounding, answer rewards | 10: + late refunds | 11: + category rename |

The easy questions are not free of net revenue, FX and Korea time. Q01 is the only money question easy can use for
the rounding rule, and it needs the net-revenue definition (a tax-inclusive Q01 is about 10% high) and, on three of
the four worlds checked, the order-date FX rate. Q04 (top customer by net revenue) also moves with FX on some seeds.
Korea-time days decide Q01 under B: the sale opens at midnight on 2026-07-01, the first day of a July fiscal year,
and in UTC its first hours fall on 2026-06-30, inside FY2025. They also decide Q03 or Q10 at the window and year edges on some seeds. The medium
questions are the ones built around these definitions. The October refunds (`late_refunds`) already bind in
medium: they move Q11 by about 3 points in every rule set, and under B they also move Q02, whose quarter is July to
September 2026. So hard adds only the rename. The round-scope notes are not targets: an answer to a question that is
not scored has no effect either way, so knowing the scope changes no score.

Questions a sheet loses when it gets only one fact wrong (exact answers otherwise, rounded to the setting's unit),
at the public seed (seeds 1, 2, 3 in brackets; * = the sheet is also invalid):

| Fact wrong | easy/A | easy/B | easy/C | medium/A | medium/B | medium/C | hard/A | hard/B | hard/C |
|---|---|---|---|---|---|---|---|---|---|
| `fiscal_year`: calendar FY (A, B) or an April FY (C) | 3 (3,4,3) | 4 (4,4,4) | 3 (3,4,3) | 5 (6,7,5) | 6 (7,7,7) | 6 (7,8,7) | 6 (7,8,6) | 7 (8,8,8) | 7 (8,9,8) |
| `local_day`: UTC days | 0 (1*,0,2) | 1 (1,3,1) | 1 (2,2,1) | 3 (4*,3,5) | 5 (4,6,4) | 3 (4,4,4) | 3 (4*,3,5) | 6 (5,7,5) | 3 (4,4,4) |
| `test_accounts`: tests kept in | 5* | 5* | 5* | 9* (9*,9*,10*) | 9* (10*,9*,10*) | 11* | 10* (10*,10*,11*) | 10* (11*,10*,11*) | 12* |
| `test_accounts`: staff dropped too | 3 (3,3,3) | 3 (3,3,3) | 3 (3,3,3) | 7 (7,8,7) | 7 (7,6,6) | 7 (7,6,6) | 8 (8,9,8) | 8 (8,7,7) | 8 (8,7,7) |
| `counted_orders`: every status | 3 (2,2,3) | 3 (2,2,3) | 3 (2,3,3) | 7 (6,6,7) | 7 (6,6,7) | 8 (7,7,7) | 8 (7,7,8) | 8 (7,7,8) | 9 (8,8,8) |
| `net_revenue`: tax included | 1 (1,1,1) | 1 (1,1,1) | 1 (1,1,2) | 4 (5,4,4) | 3 (4,3,4) | 4 (5,4,5) | 4 (5,4,4) | 3 (4,3,4) | 4 (5,4,5) |
| `net_revenue`: refunds in the refund's period | 0 (0,0,0) | 0 (0,0,0) | 1 (0,0,0) | 3 (3,4,3) | 3 (1,3,2) | 4 (3,3,3) | 3 (3,4,3) | 3 (1,3,2) | 4 (3,3,3) |
| `late_refunds`: October refunds cut off | 0 | 0 | 0 | 1 (1,2,1) | 2 (2,2,2) | 1 (1,1,1) | 1 (1,2,1) | 2 (2,2,2) | 1 (1,1,1) |
| `fx_order_date`: latest rate | 2 (1,0,1) | 1 (0,0,1) | 2 (1,1,2) | 4 (2,0,2) | 3 (0,0,3) | 5 (2,1,5) | 5 (3,0,3) | 4 (0,0,3) | 6 (3,1,6) |
| `active_customer`: one day too long | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| `category_rename`: `pantry` label only | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 |
| `report_rounding` | invalid instead | | | | | | | | |

A UTC-day sheet is flagged under `exclude_test_accounts` at world seed 1 (A): its Q10 happens to equal the
test-inclusive figure (REVIEW.md, F9). Under C the calendar year, the face-value guess, is the right fiscal year,
so `fiscal_year` binds there only against a sheet that assumes some other year. B's 10,000 KRW unit is coarse: a
money answer within 5,000 KRW counts, so Q07 and Q09 are hard to miss under B (a tax-inclusive Q09 still rounds to
the right 40,000).

## Rule sets: the client's conventions and what an answer is worth

| Parameter | A | B | C |
|---|---|---|---|
| `fy_start`: the fiscal year starts on the 1st of this month, named after the year it starts in | April | July | January |
| `fy2025` / `fy2026_q1` / `fy2026_h1`: the periods this gives (as the texts state them) | 2025-04-01–2026-03-31 / 2026-04-01–06-30 / 2026-04-01–09-30 | 2025-07-01–2026-06-30 / 2026-07-01–09-30 / 2026-07-01–12-31, counted to 09-30 | 2025-01-01–12-31 / 2026-01-01–03-31 / 2026-01-01–06-30 |
| `active_days` / `active_from`: active = a counted order in the last N days | 90, from 2026-07-03 | 60, from 2026-08-02 | 30, from 2026-09-01 |
| `rounding_unit`: money reported to the nearest | 1,000 KRW | 10,000 KRW | 100 KRW |
| `wrong_reward` / `dont_know_reward` / `right_reward` | 0 / 1 / 2 | 0 / 0.5 / 2 | 0 / 1.5 / 2 |
| Answer only if P(right) is above | 50% | 25% | 75% |

`case.py` derives every period from `fy_start` and `active_days`, and it checks at import that the period strings in
case.yaml, which the texts quote, are the ones it scores. Each rule set's reference is invalid or far worse under
both other rule sets of its tier (18 of 18 pairs): a reference rounded to 1,000 or 100 KRW breaks B's 10,000 KRW
rule, the 100 KRW sheet also breaks A's, and the valid crossings score 0.00–0.40 of the other reference. In every
pair another fiscal year moves Q01, Q02, Q08 and Q10 and another window moves Q03; Q04 also moves between B and
the others, Q12 between C and the others, and a coarser unit scored under a finer one misses Q07 or Q09 (B's
40,000 KRW figures under A and C, A's Q09 under C).

## Rules

| Rule | Class | What breaks it |
|---|---|---|
| `answer_format` | physical | a question id missing, or a value that is neither a finite number nor `null` (checked for all twelve, scored or not) |
| `exclude_test_accounts` | contractual | a scored count or customer-id answer (Q03, Q04, Q05, Q10) equal to the figure with test accounts included (Korea-time days, the setting's periods), where that differs from the figure without them |
| `report_rounding` | business policy (bendable) | a scored money answer (Q01, Q02, Q06, Q07, Q09) that is not a whole multiple of the setting's unit (1,000 / 10,000 / 100 KRW) |

## Situations present

- **Hidden facts:** the eleven targets above. The data is built so that each one shows up. A QA load test on test
  account 10027 (36 orders of ten hand grinders and five 1 kg blends, April 2025 to March 2026) makes it the top
  customer under every fiscal year when test accounts stay in. Five test orders land in the first minutes of the
  2026-07-01 sale (Korea time), which is still 2026-06-30 in UTC. Paid cancellations have payment rows. Four pantry
  products were launched under the new label, while the four older ones still say snacks. October refunds of
  September orders move Q11 by about 3 points (2–4 on seeds 1–3).
- **Calibrated abstention:** the reward scheme is a hidden fact too. An agent that has not found a definition, or
  cannot settle a figure, should weigh its chance of being right against the rule set's threshold. Saying "don't
  know" everywhere earns 0.25–0.75, which is the baseline (quality 0); answering everything at face value earns
  0–0.4 at the public seed, less than that.
- **Dated events, pressure:** none in the case itself (see REVIEW.md F6). The messy engagement adds the framework's
  generic events.

## Reference and baseline numbers (public seed 20261026)

The **reference** is a careful analyst who uses the setting's conventions and gets every definition right except
the category rename: it answers the "pantry" question from the `pantry` label alone. It leaves the questions the
tier does not score as `null`. Its abstention policy is principled and deterministic: its pantry figure covers only
the products launched since 2025-10, so it gives that answer even odds of being right and keeps it only when
½ × right_reward > dont_know_reward. That holds under B (1 > 0.5), so it answers and is wrong. Under A (1 = 1, a tie
abstains) and C (1 < 1.5) it says "don't know". In easy and medium Q06 is not scored, so there the reference is
right on every scored question.

The **baseline** is what finance reports without an analyst: "not available yet" (`null`) for every question. It
earns the rule set's don't-know reward on every scored question (0.5 / 0.25 / 0.75 under A / B / C), so saying
"don't know" to everything scores 0 on the normalized scale. The **face-value sheet** is the export summed with
none of the client's definitions: calendar-year periods on the stored UTC dates, every order whatever its status,
revenue = order `total` less the refunds dated in the period, every currency at the 2026-09-30 rate, active =
ordered in the last 30 days, "pantry" = the `pantry` label. It answers every question, keeps the two finance
policies the client applies anyway (test accounts out, money rounded to the setting's unit), and scores below the
baseline in every setting: its wrong figures earn nothing.

| Setting | Reference objective | Baseline (all `null`) | Face-value sheet (normalized quality) | Perfect sheet | Perfect, normalized quality |
|---|---|---|---|---|---|
| easy/A | 1.000 (5 right) | 0.500 | 0.000 (0.000) | 1.000 | 1.000 |
| easy/B | 1.000 | 0.250 | 0.000 (0.000) | 1.000 | 1.000 |
| easy/C | 1.000 | 0.750 | 0.400 (0.000) | 1.000 | 1.000 |
| medium/A | 1.000 (11 right) | 0.500 | 0.000 (0.000) | 1.000 | 1.000 |
| medium/B | 1.000 | 0.250 | 0.091 (0.000) | 1.000 | 1.000 |
| medium/C | 1.000 | 0.750 | 0.182 (0.000) | 1.000 | 1.000 |
| hard/A | 0.958 (11 right, Q06 null) | 0.500 | 0.000 (0.000) | 1.000 | 1.091 |
| hard/B | 0.917 (11 right, Q06 wrong) | 0.250 | 0.083 (0.000) | 1.000 | 1.125 |
| hard/C | 0.979 (11 right, Q06 null) | 0.750 | 0.167 (0.000) | 1.000 | 1.091 |

Normalized quality is (objective − baseline) / (reference − baseline). The perfect sheet's normalized quality is
1.0 in easy and medium and 1.09–1.13 in hard, so the case sets no `quality_cap` (one number per case cannot give
full credit to the perfect sheet in all nine settings; REVIEW.md, F2). On world seeds 1–20 the reference objectives
are the same in every setting (Q06 is the only question it misses). The face-value sheet scores 0.00–0.40
(easy/A), 0.00–0.20 (easy/B), 0.20–0.60 (easy/C), 0.00–0.18 (medium/A, medium/B), 0.09–0.36 (medium/C), 0.00–0.17
(hard/A, hard/B) and 0.08–0.33 (hard/C), always below the all-`null` baseline. It is higher under C because C's
fiscal year and active window are the calendar year and the 30 days it assumes. Seeds 1–20 build valid worlds,
references, baselines, violating examples and distinct rule sets in all nine settings.

The hard-tier answers (exact figure, reference, face-value sheet; ✓/✗ = the face-value answer right or wrong):

| Question | A exact | A reference | A face value | B exact | B reference | B face value | C exact | C reference | C face value |
|---|---|---|---|---|---|---|---|---|---|
| Q01 | 223,734,559 | 223,735,000 | 231,049,000 ✗ | 258,620,880 | 258,620,000 | 231,050,000 ✗ | 190,723,915 | 190,723,900 | 231,048,900 ✗ |
| Q02 | 75,372,876 | 75,373,000 | 82,939,000 ✗ | 92,389,874 | 92,390,000 | 82,940,000 ✗ | 69,454,940 | 69,454,900 | 82,939,200 ✗ |
| Q03 | 881 | 881 | 668 ✗ | 801 | 801 | 668 ✗ | 623 | 623 | 668 ✗ |
| Q04 | 10392 | 10392 | 11182 ✗ | 10247 | 10247 | 11182 ✗ | 10392 | 10392 | 11182 ✗ |
| Q05 | 183 | 183 | 111 ✗ | 183 | 183 | 111 ✗ | 183 | 183 | 111 ✗ |
| Q06 | 37,194,179 | null | 5,612,000 ✗ | 45,050,055 | 20,050,000 ✗ | 5,610,000 ✗ | 28,990,095 | null | 5,611,900 ✗ |
| Q07 | 41,618 | 42,000 | 46,000 ✗ | 41,881 | 40,000 | 50,000 ✗ | 41,846 | 41,800 | 46,200 ✗ |
| Q08 | 6.097 | 6.097 | 4.991 ✗ | 6.178 | 6.178 | 4.991 ✗ | 5.903 | 5.903 | 4.991 ✗ |
| Q09 | 35,780 | 36,000 | 39,000 ✗ | 35,330 | 40,000 | 40,000 ✓ | 35,820 | 35,800 | 38,800 ✗ |
| Q10 | 655 | 655 | 640 ✗ | 690 | 690 | 640 ✗ | 640 | 640 | 640 ✓ |
| Q11 | −2.568 | −2.568 | −5.443 ✗ | −2.568 | −2.568 | −5.443 ✗ | −2.568 | −2.568 | −5.443 ✗ |
| Q12 | 2.105 | 2.105 | 2.124 ✗ | 2.100 | 2.100 | 2.124 ✗ | 2.128 | 2.128 | 2.124 ✓ |

Under A the figures are those of the case without settings. Q05 and Q11 do not depend on the fiscal year; Q04 is
the same customer under the April and the January year.

## Notes

- Synthetic. Prices, tax rates, FX paths, order rhythms and refund rates are invented; the shop, its customers and
  its accounts are fictional. The fiscal-year, local-day, test-account, net-revenue and rename conventions are the
  common traps of BI work on raw exports, not facts about a real company. The three reward schemes are design
  choices that set the abstention threshold at 25%, 50% and 75%, not measured costs.
- Known simplifications (REVIEW.md F7): a flat 7% US tax on every order, FX rates on weekends, paid cancellations
  without a reversal row, and sign-ups from 2024-07-01 while the order history starts on 2025-01-01. The QA test
  account 10027 has load-test orders from April 2025 although it signed up in December 2025.
- `validate-case` checks every setting: deterministic data in five locales, the same agent view in all nine, the
  reference at quality 1.0, a valid baseline worse than the reference, one deliverable per rule that breaks only
  that rule, and distinct references across rule sets. It warns that the medium and hard references are
  byte-identical under A and C: both leave Q06 `null`, because it is not needed in medium and "don't know" in hard.
  They score differently (1.0 against 0.958 and 0.979), so the tier still adds signal.
