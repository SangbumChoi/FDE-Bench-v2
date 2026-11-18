# Grocery daily demand forecast

## Background

Can you forecast how much of each product each of our five stores will sell every day for the next two weeks, starting Monday 2 November? We place our orders from these numbers. The sales history and our master data are attached, with a couple of other files.

**What the numbers are for.** Each store orders exactly the number in your file for each product and day; it arrives that morning and nobody adds a safety margin on top. So what we need is the quantity to order, not the expected sales.

**What a wrong number costs us.** A unit still on the shelf at closing costs us about one unit's worth: it is written off or cleared at a loss. A unit a customer wanted and did not find costs us about {{lost_sale_cost}} times as much: the margin, and the customers who shop elsewhere next time. This holds for every product and every store.

**How the stores order today.** Each store manager orders by habit: for every product, the average of what the store sold on that weekday in the last eight weeks, leaving out days it ran out, plus about {{habit_cushion}}% to be safe; about 2% more for every point of discount when the product is on promotion; a public holiday like a Saturday. We want something better than that.
<!-- tier: easy -->

**This round** we need the order without the promotions: our category team adds the effect of the promotions on top of your numbers afterwards, so leave them out. Bread rolls (I07) are not judged this round (the bakery orders them itself while the switch to packs settles in); keep their rows in the file all the same.
<!-- /tier -->
<!-- tier: medium -->

**This round** we need the full order, promotions included: nobody adds them afterwards. Bread rolls (I07) are not judged this round (the bakery orders them itself while the switch to packs settles in); keep their rows in the file all the same.
<!-- /tier -->
<!-- tier: hard -->

**This round** we need the full order, promotions included: nobody adds them afterwards. Bread rolls (I07) are part of it.
<!-- /tier -->

## Deliverable

One CSV file, `forecast.csv`, with the header `store_id,item_id,date,order_qty`. One row for every store (S1–S5) × item (I01–I12) × day from 2026-11-02 to 2026-11-15, so 840 rows, the Old Town store's Sundays and the bread rolls included. Our ordering system loads the file as it is, so every one of these rows has to be there. Ids exactly as in the data, dates as YYYY-MM-DD, `order_qty` is the quantity the store orders for that day, a number (decimals are fine) in the item's current `sales_unit`.

## Data notes

- `sales_history.csv` covers 2024-11-04 to 2026-11-01, one sales row per store, item and trading day, plus separate return rows (see below). `stores.csv` and `items.csv` are the store and item lists; `holidays.csv` lists the public holidays in that period; `promo_plan.csv` is the promotion plan for the forecast period; `mail/` holds an e-mail from one of our store managers (see below).
- The order has to cover customer demand, not what the till recorded. On days with `stockout = yes` the shelf ran empty, so `units_sold` is only what was in stock and true demand was higher. Do not treat those days as normal sales.
- Customer returns are logged in `sales_history.csv` as separate rows with a negative `units_sold`, on the day the item was brought back. Returns are not demand: leave those rows out; do not net them against the day's sales.
- The Old Town store (S4) is closed on Sundays, which is why it has no Sunday rows. Its Sunday order must be 0.
<!-- tier: easy -->
- `promo_discount_pct` in the history shows the discount on days an item was on promotion in a store (0 = no promotion); those days sold more than a normal day. The promotions in `promo_plan.csv` are added by the category team this round: order for those days as for normal days, without any promotion lift.
<!-- /tier -->
<!-- tier: medium hard -->
- `promo_discount_pct` in the history shows the discount on days an item was on promotion in a store (0 = no promotion). The promotions for the forecast period are in `promo_plan.csv`; `start_date` and `end_date` are both inclusive, and they must be in the order. The sales lift grows with the discount and differs by category; learn it from past promotions.
<!-- when: promo_uplift=1 -->
- The November promotions run like the past ones (shelf labels only, no flyer), so the lift you learn from the history applies as it is.
<!-- /when -->
<!-- when: promo_uplift=2,3 -->
- The November promotions are also in our printed flyer, which the promotions in the history never were. Our category team expects each of them to bring about {{promo_uplift}} times the extra sales of a past promotion with the same discount in the same category, and the store managers plan for the same.
<!-- /when -->
<!-- /tier -->
<!-- tier: hard -->
- On Friday 30 October, after `promo_plan.csv` was exported, the supplier withdrew its funding and all {{promo_cancelled}} promotions in the plan were cancelled: they will not run. The rest of the plan stands.
<!-- /tier -->
- {{holiday_date}} is a one-off regional public holiday (the city's anniversary) and is not in `holidays.csv`. All stores open as usual that day. On past holidays demand went up, more for bakery and beverages than for fresh produce and dairy; expect the same pattern.
<!-- tier: hard -->
- Bread rolls (I07) were sold and recorded per piece until 31 May 2026. Since 1 June 2026 they are sold in packs of 6, the current `sales_unit`. Divide the history before 1 June 2026 by 6 and order I07 in packs.
<!-- /tier -->
- The e-mail in `mail/` is from the manager of our Central Plaza store (S1), who asks for 20% on top of the numbers for his store. That is his own wish, not company policy: Central Plaza is ordered like every other store. Do not add the 20%.
- Our habit: we never order fewer than {{min_display}} units of a core item, meaning fresh produce and dairy (I01–I06), for a day the store is open, so the shelves never look empty.

## How the order is judged

**Hard constraints** (if any is broken, the file does not count):

- Exactly one row for every store × item × date in the period; nothing missing, nothing twice.
- No negative order quantity.
- S4 is ordered 0 on Sundays.
- Fresh produce and dairy items are ordered at {{min_display}} or more for every day the store is open.

**Quality**: we do not wait for November to see how the numbers did; we judge the plan by what it costs us on average, given how much demand varies from day to day. For each store: over all its items and days, the units we expect to be left over plus {{lost_sale_cost}} times the units we expect to be short, divided by the store's expected demand; then the average over the five stores. Lower is better.
<!-- tier: easy -->

"Demand" here is the demand without the effect of the promotions, which the category team adds. Bread rolls (I07) are left out of the sums this round.
<!-- /tier -->
<!-- tier: medium -->

Bread rolls (I07) are left out of the sums this round.
<!-- /tier -->
<!-- tier: hard -->

Bread rolls (I07) count, in packs.
<!-- /tier -->
