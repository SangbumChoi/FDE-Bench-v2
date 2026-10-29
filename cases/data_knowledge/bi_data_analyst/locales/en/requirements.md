# Managers' questions from the order database

## Background

Our managers sent these questions. Can you answer them from the database export? The tables, a short data dictionary and the list of questions are attached — please send back one number per question.

We sell coffee and tea subscription boxes and one-off shop items to customers in Korea, Japan and the US. Our head office is in Seoul and all reporting is in KRW.

## Deliverable

One JSON file, `answers.json`: `{"Q01": 123456000, "Q02": ..., ..., "Q12": 1.5}`. One number per question id from the questions file (Q01 to Q12). Money in KRW, percentages in percent (4.25 means 4.25 %), and for the customer question the numeric `customer_id`.

## Data notes

- The export is a set of CSV tables (`customers.csv`, `accounts_meta.csv`, `products.csv`, `orders.csv`, `order_items.csv`, `payments.csv`, `refunds.csv`, `fx_rates.csv`). Table and column names are in English so they can be loaded into SQL as they are; status, category and other labels are in our working language.
- **Fiscal year**: our fiscal year starts on April 1 and is named after the calendar year it starts in. FY2025 = 2025-04-01 to 2026-03-31; FY2026 = 2026-04-01 to 2027-03-31. The first quarter is April–June, the first half is April–September.
- **Days are Korea time**: all timestamps (`ordered_at_utc`, `signup_at_utc`, ...) are stored in UTC, but a "day" for us is a calendar day in Korea time (UTC+9). Add 9 hours before taking the date; every day, month, quarter and fiscal year is decided that way. For example an order at 2026-06-30 16:30 UTC was placed on 2026-07-01. The reference date of the questions is 2026-09-30 (Korea time).
- **Which orders count**: only orders with status `completed`. `cancelled` and `payment_failed` orders never count, even when `payments.csv` has a payment row for them. An order belongs to the period of its order date.
- **Test accounts**: customers whose `account_type` in `accounts_meta.csv` is `test` are our QA accounts. Finance policy: they are excluded from every figure (orders, revenue, customer counts, sign-ups). `staff` accounts are real customers and stay in.
- **Net revenue** excludes tax and is net of refunds: take the order `subtotal` (before tax) and subtract the refunds of that order without their tax. Refund amounts in `refunds.csv` include tax; the tax-free part is `amount × subtotal / total` of the order. A refund reduces the revenue of the period in which the order was placed, not the period of the refund. The export was taken on 2026-10-31: it holds the orders placed up to the reference date with every refund recorded until the export, so `refunds.csv` also has refunds made in October 2026; they count too, against their order's period. For a category, an order's refunds are spread over its lines in proportion to the line amounts (`quantity × unit_price`).
- **Currencies**: amounts are stored in the order's currency (`currency`). Convert to KRW with `krw_per_unit` from `fx_rates.csv` for the order's date (Korea time); the refunds of an order use the same rate. KRW orders need no conversion.
- **Active customer**: a customer with at least one counted order whose date falls in the 90 days ending on the reference date, i.e. 2026-07-03 to 2026-09-30 inclusive.
- **Renamed category**: on 2025-10-01 the category `snacks` was renamed `pantry`. Products launched since then carry `pantry`, but older products still carry `snacks` in `products.csv` (the catalogue was never migrated). It is one category: a question about `pantry` covers both labels for the whole period.
- **Definitions per question**: average order value = net revenue / number of counted orders. Refund rate = refunds without tax / revenue before refunds (subtotals), for orders of the period, in percent. Average refund per refunded order = refunds without tax (KRW) / number of counted orders of the period with at least one refund. New customers = customers whose sign-up date is in the period. Month-on-month change = (September / August − 1) × 100. Units per order = total `quantity` / number of counted orders.
- **Rounding (finance policy)**: every money figure we report (Q01, Q02, Q06, Q07, Q09) is rounded to the nearest thousand KRW, e.g. 38,412 becomes 38,000. Counts, ids, percentages and units are not rounded.

## How the answers are judged

**Hard constraints** (if any is broken, the answer sheet does not count):

- Every question Q01–Q12 is answered with a single number.
- Test accounts are excluded; a count or customer answer that matches the figure with test accounts included is a breach of the finance policy.
- Every money figure (Q01, Q02, Q06, Q07, Q09) is a whole multiple of 1,000 KRW.

**Quality**: the number of questions answered correctly. Each answer is compared with the exact (unrounded) figure under the definitions above: the customer id and the counts (Q03, Q04, Q05, Q10) must match exactly; a money figure must be within 0.5 % or within 500 KRW of the exact figure, whichever is wider (so the exact figure rounded to the nearest thousand always counts); the month-on-month change (Q11) must be within 0.05 percentage points; every other answer must be within 0.5 % of the exact figure. Higher is better.
