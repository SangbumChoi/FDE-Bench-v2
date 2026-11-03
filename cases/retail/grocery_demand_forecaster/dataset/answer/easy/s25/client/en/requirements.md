# Grocery daily demand forecast

## Background

Can you forecast how much of each product each of our five stores will sell every day for the next two weeks, starting Monday 2 November? We place our orders from these numbers. The sales history and our master data are attached, with a couple of other files.

**This round** we only need the base forecast: what each store sells on a normal day. Our category team adds the effect of the promotions and of the one-off regional holiday in the period on top of your numbers, so leave both out. Bread rolls (I07) are not judged this round (the bakery orders them itself while the switch to packs settles in); keep their rows in the file all the same.

## Deliverable

One CSV file, `forecast.csv`, with the header `store_id,item_id,date,forecast`. One row for every store (S1–S5) × item (I01–I12) × day from 2026-11-02 to 2026-11-15, so 840 rows. Ids exactly as in the data, dates as YYYY-MM-DD, `forecast` is a number (decimals are fine) in the item's current `sales_unit`.

## Data notes

- `sales_history.csv` covers 2024-11-04 to 2026-11-01, one sales row per store, item and trading day, plus separate return rows (see below). `stores.csv` and `items.csv` are the store and item lists; `holidays.csv` lists the public holidays in that period; `promo_plan.csv` is the promotion plan for the forecast period.
- This round we judge the forecast against what the tills record, the way our weekly sales report shows it: `units_sold` as booked, with customer returns (separate rows with a negative `units_sold`, on the day the item was brought back) netted against the day's sales, and days with `stockout = yes` as they were recorded. Correcting for empty shelves comes in a later round.
- The Old Town store (S4) is closed on Sundays, which is why it has no Sunday rows. Its Sunday forecast must be 0.
- `promo_discount_pct` in the history shows the discount on days an item was on promotion in a store (0 = no promotion); those days sold more than a normal day. The promotions in `promo_plan.csv` are added by the category team this round: forecast those days as normal days, without any promotion lift.
- There is a one-off regional public holiday in the forecast period that is not in `holidays.csv`. The category team adds its effect too, so forecast that day as a normal day of its weekday.
- Our habit: we never forecast less than 8 units of a core item, meaning fresh produce and dairy (I01–I06), on a day the store is open, so the shelves never look empty.

## How the forecast is judged

**Hard constraints** (if any is broken, the forecast does not count):

- Exactly one row for every store × item × date in the period; nothing missing, nothing twice.
- No negative forecast.
- S4 is forecast 0 on Sundays.
- Fresh produce and dairy items are forecast at 8 or more on every day the store is open.

**Quality**: an empty shelf costs us more than a unit left over, so a unit forecast too low counts 2 times as much as a unit forecast too high. For each store: the sum over all its items and days of 2 × (actual − forecast) where the forecast is below the actual and (forecast − actual) where it is above, ÷ the sum of actual; then the average over the five stores.

"Actual" is the base sales: what the tills record on those days, net of returns, with the effects of the promotions and the holiday taken out by the category team. Bread rolls (I07) are left out of the sums this round. Lower is better.
