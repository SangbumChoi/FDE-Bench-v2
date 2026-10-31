# Purchase plan for the next eight weeks

## Background

We assemble two models of control board and buy about two dozen components from a handful of suppliers. Can you plan what we should order from which supplier over the next two months so production doesn't stop and we don't overspend? I've attached the production plan, the bill of materials, our current stock, open orders, the supplier quotes, the approved-vendor list and the budget.
Supply has been shaky lately, so I've also added our suppliers' delivery history for the last six months and the allocation notice we got. The BOM already includes engineering's planned change to the flash memory on both boards.
Please also use the attached supplier price email when pricing orders.

## Deliverable

One CSV file, `orders.csv`, with the header `order_week,component_id,supplier_id,quantity`. One row per purchase order line. `order_week` is the week the order is placed, as a number from 1 to 8 (1 = W1, the week starting Monday 23 November 2026; 8 = W8, the week of 11 January 2027). `component_id` and `supplier_id` exactly as in the data. `quantity` in pieces (whole units), also for resistors. Rows with the same week, component and supplier are added together into one order line.

## Data notes

- `production_plan.csv` gives the number of boards we build per week (`boards`) for each board model (`product_id` B100 and B200), for W1 to W10. We place orders in W1 to W8 only; W9 and W10 are in the plan so that the last orders are judged on what they cover. Stock still on hand after W10 is worth nothing in this plan.
- `bom.csv` is the bill of materials: `qty_per_board` pieces of each component go into one board of that model. The demand for a component in a week is the boards of each model built that week times its `qty_per_board`, added over both models. B100 has no display and no antenna.
<!-- tier: easy medium -->
- The flash change in `bom.csv` (C04 valid until W5, the new C25 from W6) has not been released for this round: plan as if both boards keep using C04 in all ten weeks, and ignore the C25 rows and the `valid_from_week` / `valid_to_week` columns. C25 is not needed.
<!-- /tier -->
<!-- tier: hard -->
- `valid_from_week` and `valid_to_week` in `bom.csv` say in which weeks a row applies (see the engineering change below).
<!-- /tier -->
- `inventory.csv`: `on_hand` is the stock at the start of W1. It is in pieces for every part except the SMD resistors (C07, C08, C09), which the warehouse counts in reels of 5,000 pieces: `on_hand = 12` for a resistor means 60,000 pieces.
- `open_orders.csv`: orders already placed and paid. They arrive in the `arrival_week` shown and are not part of this plan's spending.
<!-- tier: hard -->
  They have already shipped, so they arrive on time.
<!-- /tier -->
- `supplier_quotes.xlsx`, sheet `quotes`: one row per component and supplier, with the price per piece `unit_price` in `currency`. Pacific Parts (S04) quotes in US dollars, everyone else in KRW. Our budget is in KRW and we convert at a fixed planning rate of **{{usd_krw}} KRW per USD**, not at the market rate.
<!-- tier: easy -->
- This round we plan at list prices: every order line is priced at `unit_price` per piece regardless of its size (with the approved change from the supplier price email); ignore the `break1_*` and `break2_*` columns.
- This round we also treat lead times as whole weeks: divide `lead_time_days` by 5 and round up to get L weeks, and ignore holidays. An order is placed on the Monday of its order week, and an order placed in week w with a lead time of L weeks can be used from week w+L on (ordered in W1 with 12 days = 3 weeks → usable in W4). Goods are available for the whole arrival week's demand.
- `moq` is the minimum quantity per order line, i.e. per supplier, component and order week. Below it the supplier will not ship. Quantities ordered in different weeks are never added up for the MOQ.
<!-- /tier -->
<!-- tier: medium hard -->
- `lead_time_days` is in **business days** (Monday to Friday), not calendar days. Two weeks are short: W5 (21-25 December, Christmas) and W6 (28 December - 1 January, New Year's Day) have only 4 business days each; every other week has 5.
- Timing: an order is placed on the Monday of its order week. The lead time is counted in business days from that Monday, and the goods can be used from the first week that starts after they arrive. Concretely, the arrival week is the first week k for which the business days from the start of the order week to the end of week k-1 add up to at least the lead time. Examples: 5 days ordered in W1 → usable in W2; 12 days ordered in W1 → W4; 10 days ordered in W4 → W7 (W4 has 5 days, W5 and W6 only 4 each). Goods are available for the whole arrival week's demand.
- `moq` is the minimum quantity per order line, i.e. per supplier, component and order week. Below it the supplier will not ship. Price breaks also apply per order line: if one line reaches `break1_qty` the whole line is priced at `break1_price`, from `break2_qty` at `break2_price`. Quantities ordered in different weeks are never added up for the MOQ or the price breaks.
<!-- /tier -->
- `approved_vendors.csv`: a component may only be bought from a supplier whose `status` for that component is `approved`. `pending` (still in qualification) and `suspended` do not count, even if the supplier sent a quote.
- {{hold_supplier}} is on quality hold: their lots due to arrive in W1 to W{{hold_until}} are rejected at incoming inspection and never reach the line. Goods from them may arrive only after W{{hold_until}}.
<!-- when: quality_hold=S03-W5 -->
  The hold covers everything Mirae Semicon ships, the allocated MCU (C01) and DRAM (C03) and the new flash C25 included; orders placed with them still count against their monthly allocation.
<!-- /when -->
- `budget.csv` is a hard monthly cap from our parent company, not a target. An order counts against the month of the Monday of its order week: W1-W2 are November 2026, W3-W6 December 2026, W7-W8 January 2027. USD orders count at {{usd_krw}} KRW per USD.
- Critical components are those with `critical = yes` in `components.csv`. For each of them we want a safety stock of **{{safety_weeks}} times its average weekly demand**: its total demand over the weeks it is used divided by the number of those weeks, times {{safety_weeks}}, rounded up. It should be on hand at the end of every week in which the part is used.
- Our policy: every critical component in use is ordered from at least two different suppliers over the eight weeks, and no single supplier gets more than **{{max_share}}%** of that component's total ordered quantity (counting only the orders in this plan, in pieces), so that we stay qualified with a second source.
<!-- tier: easy medium -->
- This round does not use `delivery_history.csv` or `allocations.csv`: plan as if every supplier delivers in the promised week and confirms everything we order.
<!-- /tier -->
<!-- tier: hard -->
- Engineering change: from W6 on, every board (both models) is built with the new flash **C25** (a new die revision) instead of **C04**; `bom.csv` shows C04 valid in W1-W5 and C25 in W6-W10. C04 is used only in W1-W5. Any C04 still in stock at the end of W5 is scrapped at its standard cost (the supplier does not take it back), and C04 that arrives after W5 is useless. C25 is a new part: no stock and no open orders; it is quoted by Mirae Semicon (S03), Hanbit Electronics (S01) and Express Parts (S09), all approved. C25 is critical: its safety stock is based on its W6-W10 demand and counts from the end of W6. C04, which is being phased out, needs no safety stock and does not have to be dual-sourced any more; C25 does.
- Late deliveries: suppliers do not always deliver on the promised week. `delivery_history.csv` lists our deliveries of the last six months with the promised date (a Monday) and the date we received the goods. Received on or before the promised date counts as on time; 1 to 7 days after it as one week late; 8 to 14 days after it as two weeks late. Nothing was ever later than that. We expect each supplier to behave in the coming weeks as it has in its history. A late delivery can be used one or two weeks later than planned (still never after W10). One delivery is everything a supplier ships of one component for the same arrival week; each delivery is on time or late independently of the others.
- Allocation: Mirae Semicon (S03) has the MCU (C01) and the DRAM (C03) on allocation, and Nara Display (S08) the display (C06). `allocations.csv` gives the most each of them will confirm per calendar month, counting all our orders for that part placed in that month (by the Monday of the order week, as for the budget). Anything above it will not be confirmed.
<!-- /tier -->

The supplier price email revises the quoted prices: apply the approved change by order week, including to any applicable price break. Ignore the pending proposal.

## How the plan is judged

**Hard constraints** (if any is broken, the plan does not count):

- Only approved suppliers for each component.
- Every order line is at least the supplier's MOQ.
- Monthly purchases stay within the budget in `budget.csv`.
- Nothing from {{hold_supplier}} is due to arrive in W1-W{{hold_until}}.
<!-- tier: hard -->
- Monthly orders with S03 for C01 and C03, and with S08 for C06, stay within `allocations.csv`.
<!-- /tier -->
- Every critical component in use is ordered from at least two suppliers, none of them with more than {{max_share}}% of its quantity (our habit; we can make an exception if it saves real money).

**Quality** (lower is better), simulated week by week from W1 to W10 for every component: the stock at the start of a week plus that week's arrivals (open orders and this plan) covers the week's demand; boards that cannot be built for lack of a part wait for it and are built as soon as it arrives. The total is
- the purchase cost of all order lines in KRW (USD at {{usd_krw}} KRW per USD), plus
- holding cost: 0.5% of `standard_cost_krw` per piece in stock at the end of each week, plus
- backlog cost: 5 times `standard_cost_krw` per piece of demand still waiting at the end of each week (a piece missing for two weeks counts twice), plus
- safety-stock shortfall for critical components: 1.5 times `standard_cost_krw` per piece below the safety stock at the end of each week in which the part is used.
<!-- tier: medium hard -->

Purchase costs use the price break each line reaches.
<!-- /tier -->
<!-- tier: hard -->

On top of that, C04 still in stock at the end of W5 costs its `standard_cost_krw` per piece (scrap), and C04 is not simulated after W5. Because deliveries may be late, holding, backlog, shortfall and scrap are counted as expected values over the suppliers' real chances of being one or two weeks late (the history is a sample of them). Purchases are paid in full whether a delivery is late or not.
<!-- /tier -->
