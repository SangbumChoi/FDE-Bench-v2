# Grocery Demand Forecaster — `retail/grocery_demand_forecaster`

A regional grocery chain with five stores asks the agent to forecast "how much of each product each of our five
stores will sell every day for the next two weeks, starting Monday 2 November", because it places its orders from
these numbers. The deliverable is `forecast.csv` (`store_id,item_id,date,forecast`): one row for every store
(S1–S5) × item (I01–I12) × day from 2026-11-02 to 2026-11-15, 840 rows, in each item's current sales unit. The
forecast is scored against the true customer demand of the horizon, which lives only in the world.

The case has no settings: the same request, data, hidden requirements and evaluator at every difficulty. The
engagement knobs (full spec vs. clarify first, client persona, data noise, events) apply on top, as for every case
(see [cases/README.md](../../README.md)).

## Data

- `sales_history` (43,718 rows, 2024-11-04 to 2026-11-01, 104 weeks): one sales row per store, item and trading
  day with `units_sold`, `promo_discount_pct` (0 = no promotion) and a `stockout` flag (4,390 stockout rows,
  where recorded sales are 30–85% of demand), plus 1,286 separate customer-return rows with negative units
  (−2,104 units against 2,002,817 sold). S4 has no Sunday rows.
- `promo_plan`: 14 store × item promotions in the horizon (10/20/30% off, start and end inclusive).
- `holidays`: 12 past public holidays (Christmas, New Year's Day, a spring, summer and autumn holiday, Labour Day,
  each twice). None falls in the horizon, and the one-off holiday on Wednesday 11 November is not listed.
- `stores` (four supermarkets and the Old Town express store S4) and `items` (12 items in four categories: fresh
  produce I01–I03, dairy I04–I06, bakery I07–I09, beverages I10–I12, with their sales unit). Bread rolls (I07)
  are listed in packs of 6; the history records them per piece until 31 May 2026.

The world is a multiplicative model per store × item × day (store scale and trend, category weekday profile and
yearly season, promotion lift by category and discount, holiday lift by category) with lognormal day noise
(σ = 0.07) and Poisson sales. Stockouts happen with an item's base probability, plus 0.20 on promotion days,
independently of the day's demand.

## Rules

| Rule | Class | What it requires |
|---|---|---|
| `complete_grid` | contractual | exactly one row per store × item × date of the horizon |
| `non_negative` | physical | no negative forecast |
| `closed_day_zero` | physical | S4 is closed on Sundays: its Sunday forecasts are 0 |
| `min_display_stock` | business_policy (bendable) | core items (fresh produce and dairy, I01–I06) are forecast at 6 or more on every open day |

Quality is the WAPE per store (Σ |forecast − demand| ÷ Σ demand over its items and days), averaged over the five
stores; lower is better. Demand includes what customers could not buy because of a stockout.

## Situations present

Only hidden facts. The request says only "forecast what each store will sell"; the nine clarification targets
are stockout censoring (forecast demand, not recorded sales), returns (leave out, do not net), S4's Sunday
closure, the promotion plan (inclusive dates, lift by category and discount), the 11 November holiday, the I07
unit change, the display floor of 6, the WAPE metric and the file format. There are no case-specific dated events
or pressure messages; the engagement axis supplies the only events.

## Reference and baseline numbers (seed 20261102)

The **reference** is a censoring-aware weekday-level model per store × item, from the history only: a weekday
profile from the last 52 weeks of clean days (no stockout, promotion or holiday), a level from the last 8 weeks of
clean days, a category season factor from last year's level around the horizon, a promotion lift per discount
level and one holiday lift, both pooled over all categories, history before 1 June 2026 divided by 6 for I07,
returns left out, S4's Sundays at 0 and the floor of 6 on core items.

The **baseline** is the seasonal naive forecast a store manager would use without an engineer: what the till
recorded on the same weekday of the last history week (26 October to 1 November), with S4's Sundays at 0 and the
floor of 6 on core items. It makes no stockout, promotion or holiday adjustment.

| Forecast | Mean WAPE | S1 | S2 | S3 | S4 | S5 | Quality (baseline 0, reference 1) |
|---|---|---|---|---|---|---|---|
| Baseline (same weekday last week + floor) | 0.2790 | 0.3106 | 0.2026 | 0.3084 | 0.3325 | 0.2409 | 0 |
| Reference | 0.1470 | 0.1346 | 0.1196 | 0.1604 | 0.1763 | 0.1442 | 1 |
| Oracle (true generator mean, floor of 6) | 0.1381 | | | | | | 1.067 |

What each part of the reference is worth (the reference with one change; quality on the same scale):

| Change to the reference | Mean WAPE | Quality |
|---|---|---|
| Promotion and holiday lifts per category instead of pooled | 0.1418 | 1.039 |
| Display floor dropped (the bendable rule broken) | 0.1395 | 1.057 |
| Returns netted against the day's sales | 0.1469 | 1.001 |
| I07 history before June not divided by 6 | 0.1489 | 0.986 |
| Stockout days used as normal sales | 0.1523 | 0.960 |
| 11 November holiday unknown (9.1% of horizon demand) | 0.1566 | 0.927 |
| Promotion plan ignored | 0.1662 | 0.855 |

On world seeds 1, 2 and 3 the reference scores 0.1474 / 0.1592 / 0.1417, the baseline 0.2534 / 0.2521 / 0.2533
(baseline ÷ reference 1.72 / 1.58 / 1.79), and the oracle reaches quality 1.118 / 1.167 / 1.072. The floor binds
on 136 reference cells, all basil (I03) and aged cheese (I06), which together are 1.3% of horizon demand.

## Notes

- Synthetic. All volumes, profiles, elasticities, holiday effects and stockout rates are invented; nothing is
  calibrated to a real chain. The holiday calendar is generic (see REVIEW.md, F8).
- `validate-case` checks deterministic data in five locales, the reference at quality 1.0, a valid baseline worse
  than the reference, one deliverable per rule that breaks only that rule, and world seeds 1–3.
