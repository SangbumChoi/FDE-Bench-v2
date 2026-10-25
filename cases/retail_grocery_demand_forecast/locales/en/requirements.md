# Grocery daily demand forecast

## Background

Can you forecast how much of each product each of our five stores will sell every day for the next two weeks, starting Monday 2 November? We place our orders from these numbers. The sales history and our master data are attached, with a couple of other files.

## Deliverable

One CSV file, `forecast.csv`, with the header `store_id,item_id,date,forecast`. One row for every store (S1–S5) × item (I01–I12) × day from 2026-11-02 to 2026-11-15, so 840 rows. Ids exactly as in the data, dates as YYYY-MM-DD, `forecast` is a number (decimals are fine) in the item's current `sales_unit`.

## Data notes

- `sales_history.csv` covers 2024-11-04 to 2026-11-01, one row per store, item and trading day. `stores.csv` and `items.csv` are the store and item lists; `holidays.csv` lists the public holidays in that period; `promo_plan.csv` is the promotion plan for the forecast period.
- We need a forecast of customer demand, not of what the till recorded. On days with `stockout = yes` the shelf ran empty, so `units_sold` is only what was in stock and true demand was higher. Do not treat those days as normal sales.
- Customer returns are logged in `sales_history.csv` as separate rows with a negative `units_sold`, on the day the item was brought back. Returns are not demand: leave those rows out; do not net them against the day's sales.
- The Old Town store (S4) is closed on Sundays, which is why it has no Sunday rows. Its Sunday forecast must be 0.
- `promo_discount_pct` in the history shows the discount on days an item was on promotion in a store (0 = no promotion). The promotions for the forecast period are in `promo_plan.csv`; `start_date` and `end_date` are both inclusive, and they must be taken into account. The sales lift grows with the discount and differs by category; learn it from past promotions.
- Wednesday 11 November 2026 is a one-off regional public holiday (the city's anniversary) and is not in `holidays.csv`. All stores open as usual that day. On past holidays demand went up, more for bakery and beverages than for fresh produce and dairy; expect the same pattern.
- Bread rolls (I07) were sold and recorded per piece until 31 May 2026. Since 1 June 2026 they are sold in packs of 6, the current `sales_unit`. Divide the history before 1 June 2026 by 6 and forecast I07 in packs.
- Our habit: we never forecast less than 6 units of a core item, meaning fresh produce and dairy (I01–I06), on a day the store is open, so the shelves never look empty.

## How the forecast is judged

**Hard constraints** (if any is broken, the forecast does not count):

- Exactly one row for every store × item × date in the period; nothing missing, nothing twice.
- No negative forecast.
- S4 is forecast 0 on Sundays.
- Fresh produce and dairy items are forecast at 6 or more on every day the store is open.

**Quality**: for each store, the WAPE (weighted absolute percentage error) = sum of |forecast − actual demand| over all its items and days ÷ sum of actual demand; then the average over the five stores. Actual demand is what customers wanted to buy, including what they could not buy because of a stockout, in the current sales unit. Lower is better.
