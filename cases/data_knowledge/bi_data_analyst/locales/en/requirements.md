# Managers' questions from the order database

## Background

Our managers sent these questions. Can you answer them from the database export? The tables, a short data dictionary and the list of questions are attached — please send back one number per question.

We sell coffee and tea subscription boxes and one-off shop items to customers in Korea, Japan and the US. Our head office is in Seoul and all reporting is in KRW. The answers go into the CEO's pack for the next board meeting.

## Deliverable

One JSON file, `answers.json`: `{"Q01": 123456000, "Q02": null, ..., "Q12": 1.5}`. Every question id from the questions file (Q01 to Q12) is in the file, each with one number, or with `null` when you cannot stand behind a figure; the board pack then shows "not available yet" for it. Money in KRW, percentages in percent (4.25 means 4.25 %), and for the customer question the numeric `customer_id`.

- **Not available vs. wrong**: a wrong figure that reaches the board has to be corrected at the next meeting and costs us credibility, while "not available yet" only leaves a gap. Our finance team values each figure in the pack like this: a correct figure {{right_reward}}, a figure marked "not available yet" (`null`) {{dont_know_reward}}, a wrong figure {{wrong_reward}}.
<!-- when: dont_know_reward=0.5 -->
  This time the board would rather see a figure than a gap.
<!-- /when -->
<!-- when: dont_know_reward=1.5 -->
  After corrections in the last two packs, the board would much rather see a gap than a wrong figure this time.
<!-- /when -->
<!-- tier: easy -->
- **This round**: the board pack only needs Q01, Q03, Q04, Q10 and Q12 this time. We do not need the other seven questions this round; you can leave them as `null`, and if you answer them we will not use the figures.
<!-- /tier -->
<!-- tier: medium -->
- **This round**: the board pack needs every question except Q06 (the pantry figure) this time. You can leave Q06 as `null`; if you answer it we will not use the figure.
<!-- /tier -->

## Data notes

- The export is a set of CSV tables (`customers.csv`, `accounts_meta.csv`, `products.csv`, `orders.csv`, `order_items.csv`, `payments.csv`, `refunds.csv`, `fx_rates.csv`). Table and column names are in English so they can be loaded into SQL as they are; status, category and other labels are in our working language.
- **Fiscal year**: our fiscal year starts on {{fy_start}} 1 and is named after the calendar year it starts in: FY2025 = {{fy2025}}. The first quarter of FY2026 is {{fy2026_q1}} and its first half {{fy2026_h1}}. A period that is still running on the reference date is counted up to the reference date.
<!-- when: fy_start=7 -->
  With our July year, the first half of FY2026 has only run from 2026-07-01 to the reference date, the same three months as its first quarter.
<!-- /when -->
- **Days are Korea time**: all timestamps (`ordered_at_utc`, `signup_at_utc`, ...) are stored in UTC, but a "day" for us is a calendar day in Korea time (UTC+9). Add 9 hours before taking the date; every day, month, quarter and fiscal year is decided that way. For example an order at 2026-06-30 16:30 UTC was placed on 2026-07-01. The reference date of the questions is 2026-09-30 (Korea time).
- **Which orders count**: only orders with status `completed`. `cancelled` and `payment_failed` orders never count, even when `payments.csv` has a payment row for them. An order belongs to the period of its order date.
- **Test accounts**: customers whose `account_type` in `accounts_meta.csv` is `test` are our QA accounts. Finance policy: they are excluded from every figure (orders, revenue, customer counts, sign-ups). `staff` accounts are real customers and stay in.
- **Net revenue** excludes tax and is net of refunds: take the order `subtotal` (before tax) and subtract the refunds of that order without their tax. Refund amounts in `refunds.csv` include tax; the tax-free part is `amount × subtotal / total` of the order. A refund reduces the revenue of the period in which the order was placed, not the period of the refund. The export was taken on 2026-10-31: it holds the orders placed up to the reference date with every refund recorded until the export, so `refunds.csv` also has refunds made in October 2026; they count too, against their order's period. For a category, an order's refunds are spread over its lines in proportion to the line amounts (`quantity × unit_price`).
- **Currencies**: amounts are stored in the order's currency (`currency`). Convert to KRW with `krw_per_unit` from `fx_rates.csv` for the order's date (Korea time); the refunds of an order use the same rate. KRW orders need no conversion.
- **Active customer**: a customer with at least one counted order whose date falls in the {{active_days}} days ending on the reference date, i.e. {{active_from}} to 2026-09-30 inclusive.
- **Renamed category**: on 2025-10-01 the category `snacks` was renamed `pantry`. Products launched since then carry `pantry`, but older products still carry `snacks` in `products.csv` (the catalogue was never migrated). It is one category: a question about `pantry` covers both labels for the whole period.
- **Definitions per question**: average order value = net revenue / number of counted orders. Refund rate = refunds without tax / revenue before refunds (subtotals), for orders of the period, in percent. Average refund per refunded order = refunds without tax (KRW) / number of counted orders of the period with at least one refund. New customers = customers whose sign-up date is in the period. Month-on-month change = (September / August − 1) × 100. Units per order = total `quantity` / number of counted orders.
- **Rounding (finance policy)**: every money figure we report (Q01, Q02, Q06, Q07, Q09) is rounded to the nearest {{rounding_unit}} KRW. Counts, ids, percentages and units are not rounded.

## How the answers are judged

**Hard constraints** (if any is broken, the answer sheet does not count):

- Every question id Q01–Q12 is in the file, with a single number or `null`.
- Test accounts are excluded; a count or customer answer we use this round that matches the figure with test accounts included is a breach of the finance policy.
- Every money figure we use this round (Q01, Q02, Q06, Q07, Q09) is a whole multiple of {{rounding_unit}} KRW.

**Quality**: every question we use this round earns {{right_reward}} if its figure is correct, {{dont_know_reward}} if it is `null` and {{wrong_reward}} if it is wrong; the total is divided by {{right_reward}} times the number of questions we use, so a sheet that is entirely correct scores 1. Each answer is compared with the exact (unrounded) figure under the definitions above: the customer id and the counts (Q03, Q04, Q05, Q10) must match exactly; a money figure must be within 0.5 % or within half the rounding unit of the exact figure, whichever is wider (so the exact figure rounded to the nearest {{rounding_unit}} KRW always counts); the month-on-month change (Q11) must be within 0.05 percentage points; every other answer must be within 0.5 % of the exact figure. A question we do not use this round counts neither way. Higher is better.
