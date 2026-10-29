# BI Data Analyst — `data_knowledge/bi_data_analyst`

A coffee and tea subscription shop that sells boxes and one-off items to customers in Korea, Japan and the US
(head office in Seoul, all reporting in KRW) sends the agent a CSV export of its order database, a short data
dictionary and twelve questions from its managers: "Can you answer them from the database export? ... please
send back one number per question." The deliverable is `answers.json`, one JSON number per question id
(`{"Q01": ..., ..., "Q12": ...}`). The request names none of the definitions that decide the numbers; they are
in the hidden requirements, and the simulated client gives them only when asked.

The case has no settings: it is the same problem at every difficulty. The engagement knobs (full spec vs.
clarify first, client persona, data noise, events) apply on top, as for every case (see
[cases/README.md](../../README.md)).

## Data

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

## The questions and the hidden facts

Q01 net revenue FY2025 · Q02 net revenue FY2026 Q1 · Q03 active customers at the reference date · Q04 top
customer by net revenue FY2025 · Q05 orders on the 2026-07-01 sale day · Q06 "pantry" net revenue FY2025 · Q07
average order value FY2026 H1 · Q08 refund rate FY2025 · Q09 average refund per refunded order FY2025 · Q10 new
customers FY2025 · Q11 September vs. August 2026 net revenue change · Q12 units per order FY2025.

Nine clarification targets (`targets.yaml`). The last column is how many questions a sheet loses when it gets
only that fact wrong, answers rounded as finance requires, at the public seed (seeds 1–3 in brackets):

| Target | Kind | The fact | Questions lost |
|---|---|---|---|
| `fiscal_year` | missing | FY starts on April 1 and is named after its start year; Q1 = Apr–Jun, H1 = Apr–Sep | 6 (7, 8, 6) with a calendar FY |
| `local_day` | ambiguous | timestamps are UTC, days are Korea time (UTC+9) | 3 (4, 3, 5): Q02, Q05, Q11, sometimes Q03/Q10 |
| `test_accounts` | missing | account_type test is excluded from every figure; staff stay in | 10 (10, 10, 11) and invalid if tests stay in; 8 (8, 9, 8) if staff are dropped too |
| `counted_orders` | ambiguous | only completed orders count, even when a cancelled order has a payment row | 8 (7, 7, 8) |
| `net_revenue` | ambiguous | subtotal (ex tax) minus refunds ex tax, booked in the order's period, refunds made after the reference date included; pro rata over lines for a category | 4 (5, 4, 4) tax-inclusive; 1 (1, 2, 1) if the October refunds are cut off |
| `fx_order_date` | missing | convert at the order date's rate; refunds use the order's rate | 5 (3, 0, 3) at the latest rate |
| `active_customer` | ambiguous | at least one counted order in the 90 days 2026-07-03 to 2026-09-30 | 1 (Q03) with a 30- or 91-day window |
| `category_rename` | missing | `snacks` was renamed `pantry` on 2025-10-01; "pantry" covers both labels | 1 (Q06) |
| `report_rounding` | missing | money answers rounded to the nearest thousand KRW (and how answers are checked) | 0 (invalid instead) |

## Rules

| Rule | Class | What breaks it |
|---|---|---|
| `answer_format` | physical | a question missing or not a single JSON number |
| `exclude_test_accounts` | contractual | a count or customer-id answer (Q03, Q04, Q05, Q10) equal to the figure with test accounts included (Korea-time days), where that differs from the figure without them |
| `report_rounding` | business policy (bendable) | a money answer (Q01, Q02, Q06, Q07, Q09) that is not a whole multiple of 1,000 KRW |

Quality is the number of questions answered correctly against the exact (unrounded) figures from the world:
Q03, Q04, Q05 and Q10 exactly; money within 0.5% or 500 KRW, whichever is wider (so the exact figure rounded to the
nearest thousand always counts); Q11 within 0.05 percentage points; Q08 and Q12 within 0.5%. A percentage given as
a fraction (0.0610 for 6.10%) is accepted.

## Situations present

- **Hidden facts:** the nine targets above. The data is built so that each one shows up: a QA load test on test
  account 10027 (36 orders of ten hand grinders and five 1 kg blends in FY2025) makes it the top customer when test
  accounts stay in; five test orders land in the first minutes of the 2026-07-01 sale (Korea time), which is still
  2026-06-30 in UTC; paid cancellations have payment rows; four pantry products were launched under the new label
  while the four older ones still say snacks; October refunds of September orders move Q11 by about 3 points (2–4 on seeds 1–3).
- **Dated events, pressure:** none in the case itself (see REVIEW.md F6); the messy engagement adds the framework's
  generic events.

## Reference and baseline numbers (public seed 20261026)

The reference is a careful analyst who gets every definition right except the category rename: it answers the
"pantry" question from the `pantry` label only. The baseline is the export summed at face value with none of the
client's definitions (calendar-year periods on the stored UTC dates, every order whatever its status, revenue =
order `total` less the refunds dated in the period, every currency at the 2026-09-30 rate, active = ordered in the
last 30 days, "pantry" = the `pantry` label), keeping only the two finance policies the client applies anyway (test
accounts out, money rounded to thousands), so the sheet is valid.

| Question | Exact figure | Reference | Baseline |
|---|---|---|---|
| Q01 | 223,734,559 | 223,735,000 | 231,049,000 ✗ |
| Q02 | 75,372,876 | 75,373,000 | 82,939,000 ✗ |
| Q03 | 881 | 881 | 668 ✗ |
| Q04 | 10392 | 10392 | 11182 ✗ |
| Q05 | 183 | 183 | 111 ✗ |
| Q06 | 37,194,179 | 12,444,000 ✗ | 5,612,000 ✗ |
| Q07 | 41,618 | 42,000 | 46,000 ✗ |
| Q08 | 6.097 | 6.097 | 4.991 ✗ |
| Q09 | 35,780 | 36,000 | 39,000 ✗ |
| Q10 | 655 | 655 | 640 ✗ |
| Q11 | −2.568 | −2.568 | −5.443 ✗ |
| Q12 | 2.105 | 2.105 | 2.124 ✗ |
| **Correct** | 12 (rounded as required) | **11** | **0** |

Normalized quality is (correct − baseline) / (reference − baseline): 11/12 scores 1.0 and a perfect sheet
12/11 = 1.09 at the public seed. On world seeds 1–3 the reference scores 11 and the baseline 1, 0 and 0; on seeds
1–20 the baseline scores 0–2 (a naive figure sometimes lands within tolerance, e.g. Q12 or Q04) and the exact
answers rounded to thousands score 12 on every seed. `violating_examples` checks the last point on every world
the validator builds.

## Notes

- Synthetic. Prices, tax rates, FX paths, order rhythms and refund rates are invented; the shop, its customers and
  its accounts are fictional. The fiscal-year, local-day, test-account, net-revenue and rename conventions are the
  common traps of BI work on raw exports, not facts about a real company.
- Known simplifications (REVIEW.md F7): a flat 7% US tax on every order, FX rates on weekends, paid cancellations
  without a reversal row, and sign-ups from 2024-07-01 while the order history starts on 2025-01-01.
