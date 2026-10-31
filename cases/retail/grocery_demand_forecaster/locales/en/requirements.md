# Grocery daily demand forecast

## Background

Can you forecast how much of each product each of our five stores will sell every day for the next two weeks, starting Monday 2 November? We place our orders from these numbers. The sales history and our master data are attached, with a couple of other files.
<!-- tier: easy -->

**This round** we only need the base forecast: what each store sells on a normal day. Our category team adds the effect of the promotions and of the one-off regional holiday in the period on top of your numbers, so leave both out. Bread rolls (I07) are not judged this round (the bakery orders them itself while the switch to packs settles in); keep their rows in the file all the same.
<!-- /tier -->
<!-- tier: medium -->

**This round** we need the full forecast, with the promotions and the one-off regional holiday. Bread rolls (I07) are not judged this round (the bakery orders them itself while the switch to packs settles in); keep their rows in the file all the same.
<!-- /tier -->

## Deliverable

One CSV file, `forecast.csv`, with the header `store_id,item_id,date,forecast`. One row for every store (S1–S5) × item (I01–I12) × day from 2026-11-02 to 2026-11-15, so 840 rows. Ids exactly as in the data, dates as YYYY-MM-DD, `forecast` is a number (decimals are fine) in the item's current `sales_unit`.

## Data notes

- `sales_history.csv` covers 2024-11-04 to 2026-11-01, one sales row per store, item and trading day, plus separate return rows (see below). `stores.csv` and `items.csv` are the store and item lists; `holidays.csv` lists the public holidays in that period; `promo_plan.csv` is the promotion plan for the forecast period.
<!-- tier: easy medium -->
- This round we judge the forecast against what the tills record, the way our weekly sales report shows it: `units_sold` as booked, with customer returns (separate rows with a negative `units_sold`, on the day the item was brought back) netted against the day's sales, and days with `stockout = yes` as they were recorded. Correcting for empty shelves comes in a later round.
<!-- /tier -->
<!-- tier: hard -->
- We need a forecast of customer demand, not of what the till recorded. On days with `stockout = yes` the shelf ran empty, so `units_sold` is only what was in stock and true demand was higher. Do not treat those days as normal sales.
- Customer returns are logged in `sales_history.csv` as separate rows with a negative `units_sold`, on the day the item was brought back. Returns are not demand: leave those rows out; do not net them against the day's sales.
<!-- /tier -->
- The Old Town store (S4) is closed on Sundays, which is why it has no Sunday rows. Its Sunday forecast must be 0.
<!-- tier: easy -->
- `promo_discount_pct` in the history shows the discount on days an item was on promotion in a store (0 = no promotion); those days sold more than a normal day. The promotions in `promo_plan.csv` are added by the category team this round: forecast those days as normal days, without any promotion lift.
- There is a one-off regional public holiday in the forecast period that is not in `holidays.csv`. The category team adds its effect too, so forecast that day as a normal day of its weekday.
<!-- /tier -->
<!-- tier: medium hard -->
- `promo_discount_pct` in the history shows the discount on days an item was on promotion in a store (0 = no promotion). The promotions for the forecast period are in `promo_plan.csv`; `start_date` and `end_date` are both inclusive, and they must be taken into account. The sales lift grows with the discount and differs by category; learn it from past promotions.
<!-- when: promo_uplift=1 -->
- The November promotions run like the past ones (shelf labels only, no flyer), so the lift you learn from the history applies as it is.
<!-- /when -->
<!-- when: promo_uplift=1.5,2 -->
- The November promotions are also in our printed flyer, which the promotions in the history never were. Our category team expects each of them to bring about {{promo_uplift}} times the extra sales of a past promotion with the same discount in the same category.
<!-- /when -->
<!-- /tier -->
<!-- tier: hard -->
- On Friday 30 October, after `promo_plan.csv` was exported, the supplier withdrew its funding and all {{promo_cancelled}} promotions in the plan were cancelled: they will not run. The rest of the plan stands.
<!-- /tier -->
<!-- tier: medium hard -->
- {{holiday_date}} is a one-off regional public holiday (the city's anniversary) and is not in `holidays.csv`. All stores open as usual that day. On past holidays demand went up, more for bakery and beverages than for fresh produce and dairy; expect the same pattern.
<!-- /tier -->
<!-- tier: hard -->
- Bread rolls (I07) were sold and recorded per piece until 31 May 2026. Since 1 June 2026 they are sold in packs of 6, the current `sales_unit`. Divide the history before 1 June 2026 by 6 and forecast I07 in packs.
<!-- /tier -->
- Our habit: we never forecast less than {{min_display}} units of a core item, meaning fresh produce and dairy (I01–I06), on a day the store is open, so the shelves never look empty.

## How the forecast is judged

**Hard constraints** (if any is broken, the forecast does not count):

- Exactly one row for every store × item × date in the period; nothing missing, nothing twice.
- No negative forecast.
- S4 is forecast 0 on Sundays.
- Fresh produce and dairy items are forecast at {{min_display}} or more on every day the store is open.

<!-- when: short_weight=1 -->
**Quality**: for each store, the WAPE (weighted absolute percentage error) = sum of |forecast − actual| over all its items and days ÷ sum of actual; then the average over the five stores. A unit too many and a unit too few count the same.
<!-- /when -->
<!-- when: short_weight=2,3 -->
**Quality**: an empty shelf costs us more than a unit left over, so a unit forecast too low counts {{short_weight}} times as much as a unit forecast too high. For each store: the sum over all its items and days of {{short_weight}} × (actual − forecast) where the forecast is below the actual and (forecast − actual) where it is above, ÷ the sum of actual; then the average over the five stores.
<!-- /when -->
<!-- tier: easy -->

"Actual" is the base sales: what the tills record on those days, net of returns, with the effects of the promotions and the holiday taken out by the category team. Bread rolls (I07) are left out of the sums this round. Lower is better.
<!-- /tier -->
<!-- tier: medium -->

"Actual" is what the tills record on those days, net of returns. Bread rolls (I07) are left out of the sums this round. Lower is better.
<!-- /tier -->
<!-- tier: hard -->

"Actual" is customer demand: what customers wanted to buy, including what they could not buy because of a stockout, in the current sales unit. Lower is better.
<!-- /tier -->
