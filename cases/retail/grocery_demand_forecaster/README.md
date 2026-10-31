# Grocery Demand Forecaster — `retail/grocery_demand_forecaster`

A regional grocery chain with five stores asks the agent to forecast "how much of each product each of our five
stores will sell every day for the next two weeks, starting Monday 2 November", because it places its orders from
these numbers. The deliverable is `forecast.csv` (`store_id,item_id,date,forecast`): one row for every store
(S1–S5) × item (I01–I12) × day from 2026-11-02 to 2026-11-15, 840 rows, in each item's current sales unit. The
forecast is scored against the horizon's actuals, which live only in the world.

The case has **settings**: three tiers × rule seeds (DESIGN.md, Settings). The data and the request are the same
in every setting; only the client's hidden rules, what the forecast is judged against, and so the right forecast
change. The engagement knobs (full spec vs. clarify first, client persona, data noise, events) apply on top, as
for every case (see [cases/README.md](../../README.md)).

## Tiers

| Tier | What the forecast must do | Out of scope (said in the client's words) |
|---|---|---|
| **easy** | The base forecast: a normal day per store × item, judged against **base till sales** (net of returns, stockout days as recorded, no promotion and no holiday effect). S4's Sunday closure, the display floor and the error weight apply | The promotions and the one-off holiday ("our category team adds the effect … so leave both out"); stockout correction ("comes in a later round"); bread rolls I07 ("not judged this round … keep their rows in the file") |
| **medium** | Easy + the promotion plan (inclusive dates, the lift by category and discount learned from past promotions, times the flyer's multiple when one is drawn) and the one-off regional holiday on its drawn date; still judged against **till sales** net of returns | Stockout correction and I07, as in easy |
| **hard** | Medium judged against **customer demand**: stockout days are censored, returns are not demand, I07 is judged (its unit change: pieces until 31 May 2026, packs of 6 since), and a dated revision: on Friday 30 October, after `promo_plan.csv` was exported, the drawn category's promotions were cancelled | — |

The tiers change the truth, not only the rules: the world draws one realization per cell (day noise, a Poisson
quantile, the stockout and return draws) and each setting evaluates it under its own mean (with or without the
promotions, the flyer, the cancellation and the holiday) and as till sales or as demand, so all settings share
the same luck.

## Parameters (what a rule seed draws)

Each parameter is drawn on its own from its pool in the setting's tier (`case.yaml` `params:`).

| Parameter | easy | medium | hard | What it changes |
|---|---|---|---|---|
| `min_display` | 6, 4, 8 | same | same | The display floor of core items (fresh produce and dairy, I01–I06) on open days: the bendable rule `min_display_stock`. It binds on basil (I03) and aged cheese (I06), 136 cells at 6 or 8 |
| `holiday_date` | none | 2026-11-11, 2026-11-13, 2026-11-09 | same | The day of the one-off regional holiday (Wed 11 / Fri 13 / Mon 9 November), not in `holidays.csv`; demand rises by the category's holiday effect that day |
| `promo_uplift` | 1 | 1, 1.5, 2 | same | The printed flyer: a November promotion brings this multiple of a past promotion's extra sales (1 = no flyer, shelf labels as before) |
| `promo_cancelled` | none | none | beverages, dairy, bakery | The category whose promotions the supplier cancelled on 30 October, after the plan was exported |
| `short_weight` | 1, 2, 3 | same | same | In the store's WAPE a unit forecast too low counts this many times a unit too high (1 = plain WAPE). It moves the best forecast from the median to the 2/3 or 3/4 quantile |

The rest is fixed: the 14-day horizon, S4's Sunday closure, the core categories, I07's unit change on 1 June 2026
and that I07 is judged in hard only. `case.py` derives nothing and needs no `admissible()`: every combination is
a sensible week.

## Public panel (rule seeds 3, 25, 58) at the case seed 20261102

Every candidate of every pool appears in the panel. Seed 3 is first: it draws the binding check's setting
(hard/s3: no flyer, plain WAPE, floor 6), where the first other candidate of every parameter already makes the
reference invalid, moves its objective or is beaten by its own reference by at least 3%.

| Setting | Drawn parameters | Reference | Baseline | Baseline / reference |
|---|---|---|---|---|
| easy/s3 | floor 6, weight 1 | 0.1750 | 0.2873 | 1.64 |
| easy/s25 | floor 8, weight 2 | 0.2374 | 0.4090 | 1.72 |
| easy/s58 | floor 4, weight 3 | 0.2548 | 0.5040 | 1.98 |
| medium/s3 | floor 6, holiday Mon 9 Nov, no flyer, weight 1 | 0.1778 | 0.2939 | 1.65 |
| medium/s25 | floor 8, holiday Wed 11 Nov, flyer 1.5, weight 2 | 0.2442 | 0.4701 | 1.93 |
| medium/s58 | floor 4, holiday Fri 13 Nov, flyer 2, weight 3 | 0.2678 | 0.6609 | 2.47 |
| hard/s3 | floor 6, holiday Mon 9 Nov, no flyer, bakery cancelled, weight 1 | 0.1407 | 0.2747 | 1.95 |
| hard/s25 | floor 8, holiday Wed 11 Nov, flyer 1.5, beverages cancelled, weight 2 | 0.1962 | 0.4329 | 2.21 |
| hard/s58 | floor 4, holiday Fri 13 Nov, flyer 2, dairy cancelled, weight 3 | 0.2108 | 0.6753 | 3.20 |

The objective is the mean over the five stores of the weighted WAPE (lower is better). The dicts as stored in
`dataset/gt/<tier>_s<seed>/setting.json`:

```
easy/s3    {min_display: 6, holiday_date: none,         promo_uplift: 1,   promo_cancelled: none,      short_weight: 1}
easy/s25   {min_display: 8, holiday_date: none,         promo_uplift: 1,   promo_cancelled: none,      short_weight: 2}
easy/s58   {min_display: 4, holiday_date: none,         promo_uplift: 1,   promo_cancelled: none,      short_weight: 3}
medium/s3  {min_display: 6, holiday_date: "2026-11-09", promo_uplift: 1,   promo_cancelled: none,      short_weight: 1}
medium/s25 {min_display: 8, holiday_date: "2026-11-11", promo_uplift: 1.5, promo_cancelled: none,      short_weight: 2}
medium/s58 {min_display: 4, holiday_date: "2026-11-13", promo_uplift: 2,   promo_cancelled: none,      short_weight: 3}
hard/s3    {min_display: 6, holiday_date: "2026-11-09", promo_uplift: 1,   promo_cancelled: bakery,    short_weight: 1}
hard/s25   {min_display: 8, holiday_date: "2026-11-11", promo_uplift: 1.5, promo_cancelled: beverages, short_weight: 2}
hard/s58   {min_display: 4, holiday_date: "2026-11-13", promo_uplift: 2,   promo_cancelled: dairy,     short_weight: 3}
```

Every parameter binds (validator, from hard/s3, on the case seed and world seeds 1–3; probed on world seeds 1–20,
where each parameter's strongest alternative makes the reference invalid, or moves or beats it by at least 5%):
- `min_display`: the hard/s3 reference (floor 6) is invalid under 8; under 4 the reference of that setting is
  4.9% better.
- `holiday_date`: the hard/s3 reference's objective moves by +28.4% under Wed 11 Nov and +32.9% under Fri 13 Nov.
- `promo_uplift`: +3.4% under a flyer of 1.5, +11.0% under 2.
- `promo_cancelled`: +17.0% when beverages instead of bakery are cancelled, +5.7% for dairy.
- `short_weight`: +45.3% under weight 2, +90.6% under 3 (and the weighted setting's own reference is 8.4% and
  18.4% better there).

On world seeds 1, 2 and 3 the baseline ÷ reference ratio is 1.34–1.76 (easy), 1.45–2.25 (medium) and 1.68–2.96
(hard).

## What an agent must ask

The clarification targets, by tier (`locales/<lang>/targets.yaml`):

- **Every tier:** S4's Sunday closure (`s4_sunday_closed`), the display floor and its value (`min_display`), the
  metric with its error weight and what the actuals are (`wape_metric`: till sales net of returns in easy and
  medium, demand in hard), the file format (`submission_format`).
- **easy:** that only the base forecast is wanted, without the promotions and the holiday (`base_forecast`).
- **medium and hard:** the promotion plan (`promo_plan`), the flyer's multiple or that there is no flyer
  (`promo_flyer`), the one-off holiday and its date (`one_off_holiday`).
- **hard:** stockout censoring (`stockout_censoring`), returns left out (`returns`), the 30 October cancellation
  and its category (`promo_revision`), I07's unit change (`unit_change_i07`).

So 5 targets in easy, 7 in medium, 11 in hard.

## Data

- `sales_history` (43,718 rows, 2024-11-04 to 2026-11-01, 104 weeks): one sales row per store, item and trading
  day with `units_sold`, `promo_discount_pct` (0 = no promotion) and a `stockout` flag (4,390 stockout rows,
  where recorded sales are 30–85% of demand), plus 1,286 separate customer-return rows with negative units
  (−2,104 units against 2,002,817 sold). S4 has no Sunday rows.
- `promo_plan`: 14 store × item promotions in the horizon (10/20/30% off, start and end inclusive); at the case
  seed 7 beverages, 3 bakery, 2 dairy and 2 produce promotions. On every world seed the plan has at least one
  promotion in each category the 30 October cancellation can draw (beverages, dairy, bakery).
- `holidays`: 12 past public holidays (Christmas, New Year's Day, a spring, summer and autumn holiday, Labour Day,
  each twice). None falls in the horizon, and the one-off holiday (on the drawn date) is not listed.
- `stores` (four supermarkets and the Old Town express store S4) and `items` (12 items in four categories: fresh
  produce I01–I03, dairy I04–I06, bakery I07–I09, beverages I10–I12, with their sales unit). Bread rolls (I07)
  are listed in packs of 6; the history records them per piece until 31 May 2026.

The data is unchanged by the conversion (byte-identical to the case without settings). The world is a
multiplicative model per store × item × day (store scale and trend, category weekday profile and yearly season,
promotion lift by category and discount, holiday lift by category) with lognormal day noise (σ = 0.07) and
Poisson sales. Stockouts happen with an item's base probability, plus 0.20 on promotion days, independently of the
day's demand. In the horizon, the flyer multiplies a promotion's extra demand; till sales are demand cut to 30–85%
on a stockout day (same probabilities) minus a return of 1–2 units on 3% of cells.

## Rules

| Rule | Class | Tiers | What it requires |
|---|---|---|---|
| `complete_grid` | contractual | all | exactly one row per store × item × date of the horizon (I07 too, even where it is not judged) |
| `non_negative` | physical | all | no negative forecast |
| `closed_day_zero` | physical | all | S4 is closed on Sundays: its Sunday forecasts are 0 |
| `min_display_stock` | business_policy (bendable) | all | core items (fresh produce and dairy, I01–I06) are forecast at `min_display` or more on every open day |

**Quality (lower is better):** per store, Σ (`short_weight` × (actual − forecast) where the forecast is low,
forecast − actual where it is high) ÷ Σ actual over its judged items and days, averaged over the five stores.
The actuals are base till sales (easy), till sales net of returns (medium) or customer demand (hard); I07 is
judged in hard only.

## Situations present

- **Hidden facts:** the base-only scope (easy), what the actuals are (till sales or demand), returns, S4's Sunday
  closure, the promotion plan and the flyer, the one-off holiday and its date, the I07 unit change, the display
  floor and the error weight.
- **A dated event (hard):** the cancellation of 30 October, after `promo_plan.csv` was exported, so the file the
  agent has is stale for one category.
- No pressure message; the engagement axis supplies the only other events (REVIEW.md, F7).

## Reference and baseline

The **reference** is a weekday-level model per store × item, from the history only: a weekday profile from the
last 52 weeks of usable days without promotion or holiday, a level from the last 8 weeks of such days, a category
season factor from last year's level around the horizon, a promotion lift per category and discount and a holiday
lift per category, both against the local level, and history before 1 June 2026 divided by 6 for I07. Then the
setting: the promotions this tier forecasts (lift × the flyer's multiple on the extra part, none for the
cancelled category), the holiday lift on the drawn day, and the `short_weight / (1 + short_weight)` quantile of
the store × item's ratio of actual to fitted value over the last 26 weeks (the median at weight 1); S4's Sundays at
0 and the floor on core items. In easy and medium it fits till sales as recorded (stockout days in, returns
netted, as the client describes the actuals); in hard it fits demand (stockout days and return rows out).

The **baseline** is the seasonal naive forecast a store manager would use without an engineer, the same in every
setting: what the till recorded on the same weekday of the last history week (26 October to 1 November), with
S4's Sundays at 0 and the drawn floor on core items. It makes no stockout, promotion, holiday or weight
adjustment.

What each part is worth at the case seed (the reference with one change, quality on the baseline-0 /
reference-1 scale):

| Change to the reference | easy/s25 | medium/s25 | hard/s3 | hard/s25 | hard/s58 |
|---|---|---|---|---|---|
| Oracle: the true outcome distribution's quantile per cell, with the floor | 1.053 | 1.062 | 1.030 | 1.019 | 1.014 |
| Fitted to the other target (demand in easy/medium, till sales in hard) | 1.040 | 1.046 | 0.932 | 0.933 | 0.942 |
| Error weight ignored (the median) | 0.861 | 0.888 | — | 0.926 | 0.894 |
| Promotions and an 11 November holiday added (easy) / promotions ignored | 0.714 | 0.767 | 0.846 | 0.847 | 0.688 |
| Holiday ignored | — | 0.874 | 0.854 | 0.854 | 0.845 |
| Flyer ignored | — | 0.948 | — | 0.965 | 0.905 |
| Cancellation ignored | — | — | 0.975 | 0.856 | 0.976 |
| I07 history not divided by 6 | — | — | 0.999 | 0.996 | 0.997 |
| Returns netted against the day's sales | — | — | 0.999 | 0.999 | 1.000 |
| Display floor dropped (the bendable rule broken) | 1.114 | 1.077 | 1.067 | 1.065 | 1.001 |

So stockout censoring bites in hard only: in easy and medium the client's till-sales actuals make a demand fit
unnecessary, though it still beats the till fit by 3–5% (the censored days only add noise to a till level, and a
till sale's median sits close to demand's). Bending the floor pays 7–11% with a floor of 6 or 8 and nothing with 4
under weight 3, where the quantile forecast already clears it.

## Notes

- Synthetic. All volumes, profiles, elasticities, holiday effects and stockout rates are invented; nothing is
  calibrated to a real chain. The holiday calendar is generic (see REVIEW.md, F8).
- `validate-case` checks deterministic data in five locales, the reference at quality 1.0 in every public setting,
  a valid baseline worse than the reference, one deliverable per rule that breaks only that rule, that every
  parameter binds, and world seeds 1–3.
