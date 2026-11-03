# Purchase plan for the next eight weeks

## Background

We assemble two models of control board and buy about two dozen components from a handful of suppliers. Can you plan what we should order from which supplier over the next two months so production doesn't stop and we don't overspend? I've attached the production plan, the bill of materials, our current stock, open orders, the supplier quotes, the approved-vendor list and the budget.
Supply has been shaky lately, so I've also added our suppliers' delivery history for the last six months and the allocation notice we got. The BOM already includes engineering's planned change to the flash memory on both boards.
I've also forwarded our e-mail thread with Nara Display about their new display price; please price the orders with it.

## Deliverable

One CSV file, `orders.csv`, with the header `order_week,component_id,supplier_id,quantity`. One row per purchase order line. `order_week` is the week the order is placed, as a number from 1 to 8 (1 = W1, the week starting Monday 23 November 2026; 8 = W8, the week of 11 January 2027). `component_id` and `supplier_id` exactly as in the data. `quantity` in pieces (whole units), also for resistors. Rows with the same week, component and supplier are added together into one order line.

## Data notes

- `production_plan.csv` gives the number of boards we build per week (`boards`) for each board model (`product_id` B100 and B200), for W1 to W10. We place orders in W1 to W8 only; W9 and W10 are in the plan so that the last orders are judged on what they cover. Stock still on hand after W10 is worth nothing in this plan.
- `bom.csv` is the bill of materials: `qty_per_board` pieces of each component go into one board of that model. The demand for a component in a week is the boards of each model built that week times its `qty_per_board`, added over both models. B100 has no display and no antenna. The parts are needed in the week the boards are built, not earlier: goods that arrive in a week can be used for that whole week's builds (there is no assembly offset).
- The flash change in `bom.csv` (C04 valid until W5, the new C25 from W6) has not been released for this round (engineering is still qualifying C25): plan as if both boards keep using C04 in all ten weeks, and ignore the C25 rows and the `valid_from_week` / `valid_to_week` columns. C25 is not needed.
- `inventory.csv`: `on_hand` is the stock at the start of W1. It is in pieces for every part except the SMD resistors (C07, C08, C09), which the warehouse counts in reels of 5,000 pieces: `on_hand = 12` for a resistor means 60,000 pieces.
- `open_orders.csv`: orders already placed and paid. They arrive in the `arrival_week` shown and are not part of this plan's spending.
- `supplier_quotes.xlsx`, sheet `quotes`: one row per component and supplier, with the price per piece `unit_price` in `currency`. Pacific Parts (S04) quotes in US dollars, everyone else in KRW. Our budget is in KRW and we convert at a fixed planning rate of **1,380 KRW per USD**, not at the market rate.
- Nara Display price change (the e-mail thread in `mail/`): we have agreed to their 12% increase on the display module C06 for orders they receive on or after Wednesday 9 December 2026. It applies to every C06 unit price from them, the list price and both break prices. We send every order on the Monday of its order week, so W3's orders (Monday 7 December) still get the old price and the increase applies to their C06 orders from W4 on. The further 8% they proposed from January has not been accepted: plan without it. Open orders are not affected.
- `lead_time_days` is in **business days** (Monday to Friday), not calendar days. Two weeks are short: W5 (21-25 December, Christmas) and W6 (28 December - 1 January, New Year's Day) have only 4 business days each; every other week has 5.
- Timing: an order is placed on the Monday of its order week. The lead time is counted in business days from that Monday, and the goods can be used from the first week that starts after they arrive. Concretely, the arrival week is the first week k for which the business days from the start of the order week to the end of week k-1 add up to at least the lead time. Examples: 5 days ordered in W1 → usable in W2; 12 days ordered in W1 → W4; 10 days ordered in W4 → W7 (W4 has 5 days, W5 and W6 only 4 each). Goods are available for the whole arrival week's demand.
- `moq` is the minimum quantity per order line, i.e. per supplier, component and order week. Below it the supplier will not ship. Price breaks also apply per order line: if one line reaches `break1_qty` the whole line is priced at `break1_price`, from `break2_qty` at `break2_price`. Quantities ordered in different weeks are never added up for the MOQ or the price breaks.
- `approved_vendors.csv`: a component may only be bought from a supplier whose `status` for that component is `approved`. `pending` (still in qualification) and `suspended` do not count, even if the supplier sent a quote.
- Seoul PCB Tech (S05) is on quality hold: their lots due to arrive in W1 to W4 are rejected at incoming inspection and never reach the line. Goods from them may arrive only after W4.
- `budget.csv` is a hard monthly cap from our parent company, not a target: no month may go over it. An order counts against the month of the Monday of its order week: W1-W2 are November 2026 (W2 starts on Monday 30 November, so it counts in November although most of its days are in December), W3-W6 December 2026, W7-W8 January 2027. USD orders count at 1,380 KRW per USD.
- Critical components are those with `critical = yes` in `components.csv`. For each of them we want a safety stock of **0.5 times its average weekly demand**: its total demand over the weeks it is used divided by the number of those weeks, times 0.5, rounded up. It should be on hand at the end of every week in which the part is used.
- Our policy: every critical component in use is ordered from at least two different suppliers over the eight weeks, and no single supplier gets more than **70%** of that component's total ordered quantity (counting only the orders in this plan, in pieces), so that we stay qualified with a second source.
- This round does not use `delivery_history.csv` or `allocations.csv` (management wants a plan on the suppliers' confirmed dates first): plan as if every supplier delivers in the promised week and confirms everything we order.

## How the plan is judged

**Hard constraints** (if any is broken, the plan does not count):

- Only approved suppliers for each component.
- Every order line is at least the supplier's MOQ.
- Monthly purchases stay within the budget in `budget.csv`.
- Nothing from Seoul PCB Tech (S05) is due to arrive in W1-W4.
- Every critical component in use is ordered from at least two suppliers, none of them with more than 70% of its quantity (our habit; we can make an exception if it saves real money).

**Quality** (lower is better), simulated week by week from W1 to W10 for every component: the stock at the start of a week plus that week's arrivals (open orders and this plan) covers the week's demand; boards that cannot be built for lack of a part wait for it and are built as soon as it arrives. The total is
- the purchase cost of all order lines in KRW (USD at 1,380 KRW per USD), plus
- holding cost: 0.5% of `standard_cost_krw` per piece in stock at the end of each week, plus
- backlog cost: every board that waits a week for a missing part costs us 10,000 KRW (late-delivery penalties and overtime to catch up). It is counted per part: a piece of demand still waiting at the end of a week costs 10,000 KRW divided by that part's pieces per board (its demand divided by the boards built of the models that use it), and a piece missing for two weeks counts twice, plus
- safety-stock shortfall for critical components: 1.5 times `standard_cost_krw` per piece below the safety stock at the end of each week in which the part is used.

Purchase costs use the price break each line reaches.
