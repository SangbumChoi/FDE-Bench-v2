# Grocery daily demand forecast

## Background

Can you forecast how much of each product each of our five stores will sell every day for the next two weeks, starting Monday 2 November? We place our orders from these numbers. The sales history and our master data are attached, with a couple of other files.

**This round** we need the full forecast, with the promotions and the one-off regional holiday. Bread rolls (I07) are not judged this round (the bakery orders them itself while the switch to packs settles in); keep their rows in the file all the same.

## Deliverable

One CSV file, `forecast.csv`, with the header `store_id,item_id,date,forecast`. One row for every store (S1–S5) × item (I01–I12) × day from 2026-11-02 to 2026-11-15, so 840 rows. Ids exactly as in the data, dates as YYYY-MM-DD, `forecast` is a number (decimals are fine) in the item's current `sales_unit`.

## Data notes

- `sales_history.csv` covers 2024-11-04 to 2026-11-01, one sales row per store, item and trading day, plus separate return rows (see below). `stores.csv` and `items.csv` are the store and item lists; `holidays.csv` lists the public holidays in that period; `promo_plan.csv` is the promotion plan for the forecast period.
- This round we judge the forecast against what the tills record, the way our weekly sales report shows it: `units_sold` as booked, with customer returns (separate rows with a negative `units_sold`, on the day the item was brought back) netted against the day's sales, and days with `stockout = yes` as they were recorded. Correcting for empty shelves comes in a later round.
- The Old Town store (S4) is closed on Sundays, which is why it has no Sunday rows. Its Sunday forecast must be 0.
- `promo_discount_pct` in the history shows the discount on days an item was on promotion in a store (0 = no promotion). The promotions for the forecast period are in `promo_plan.csv`; `start_date` and `end_date` are both inclusive, and they must be taken into account. The sales lift grows with the discount and differs by category; learn it from past promotions.
- The November promotions run like the past ones (shelf labels only, no flyer), so the lift you learn from the history applies as it is.
- Monday 9 November 2026 is a one-off regional public holiday (the city's anniversary) and is not in `holidays.csv`. All stores open as usual that day. On past holidays demand went up, more for bakery and beverages than for fresh produce and dairy; expect the same pattern.
- Our habit: we never forecast less than 6 units of a core item, meaning fresh produce and dairy (I01–I06), on a day the store is open, so the shelves never look empty.

## How the forecast is judged

**Hard constraints** (if any is broken, the forecast does not count):

- Exactly one row for every store × item × date in the period; nothing missing, nothing twice.
- No negative forecast.
- S4 is forecast 0 on Sundays.
- Fresh produce and dairy items are forecast at 6 or more on every day the store is open.

**Quality**: for each store, the WAPE (weighted absolute percentage error) = sum of |forecast − actual| over all its items and days ÷ sum of actual; then the average over the five stores. A unit too many and a unit too few count the same.

"Actual" is what the tills record on those days, net of returns. Bread rolls (I07) are left out of the sums this round. Lower is better.
