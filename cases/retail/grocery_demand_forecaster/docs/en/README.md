# Grocery Demand Forecaster — `retail/grocery_demand_forecaster`

A regional grocery chain with five stores asks the agent to forecast "how much of each product each of our five
stores will sell every day for the next two weeks, starting Monday 2 November", because it places its orders from
these numbers. What the request does not say is that the stores order exactly the number they are given. So the
deliverable, `forecast.csv` (`store_id,item_id,date,order_qty`: one row for every store S1–S5 × item I01–I12 × day
from 2026-11-02 to 2026-11-15, 840 rows, in each item's current sales unit), is an **order plan**, and it is scored
as one: by what it is expected to cost the client, not against one November that happened.

This is the benchmark's forecasting case, and it follows the rules for such cases (docs/DIRECTION.md, section 5):

- **Expected loss, not one draw.** The world knows the demand distribution it draws from, so the scorer computes the
  plan's expected cost under it, exactly. No realized future, no luck, and the best possible plan is known.
- **The client's decision picks the loss.** A unit left over costs one unit's worth; a unit a customer wanted and
  did not find costs `lost_sale_cost` times as much. That ratio is a client fact, and it changes the best number.
- **Rules constrain decisions, not forecasts.** The display minimum, the closed store and the complete file are
  rules on the order. No forecast is "invalid" for being low: the model family is the agent's own business.
- **Elicitation is about the target.** What the number is used for, demand or recorded sales, the calendar
  (holiday, promotions, the flyer, a cancellation), and whose word counts (the store manager's e-mail).

The case has **settings**: three tiers × rule seeds (DESIGN.md, Settings). The data and the request are the same
in every setting; only the client's hidden facts, and so the right plan, change. The engagement knobs (full spec
vs. clarify first, client persona, data noise, events) apply on top, as for every case (see
[cases/README.md](../../../../README.md)).

## Tiers

| Tier | What the plan must do | Out of scope (said in the client's words) |
|---|---|---|
| **easy** | The order without the promotions, judged against demand without them. The stores order the number as it is; a missed sale costs `lost_sale_cost` leftover units; stockout days understate demand; the one-off holiday on its drawn date; S4's Sunday closure and the display minimum; the store manager's e-mail is not policy | The promotions ("our category team adds the effect … on top of your numbers afterwards, so leave them out"); bread rolls I07 ("not judged this round … keep their rows in the file") |
| **medium** | Easy + the promotion plan (inclusive dates, the lift by category and discount learned from past promotions, times the flyer's multiple when one is drawn) | I07, as in easy |
| **hard** | Medium + bread rolls (I07 is judged, so its unit change matters: pieces until 31 May 2026, packs of 6 since) and a dated revision: on Friday 30 October, after `promo_plan.csv` was exported, the drawn category's promotions were cancelled | — |

## Parameters (what a rule seed draws)

Each parameter is drawn on its own from its pool in the setting's tier (`case.yaml` `params:`).

| Parameter | easy | medium | hard | What it changes |
|---|---|---|---|---|
| `lost_sale_cost` | 5, 12, 30 | same | same | What a unit short costs, in units left over. The best order covers demand on 5/6, 12/13 or 30/31 of days: the 83%, 92% or 97% quantile of the day's demand |
| `min_display` | 6, 4, 12 | same | same | The display minimum of core items (fresh produce and dairy, I01–I06) on open days: the bendable rule `min_display_stock`, a rule on the order. It holds up basil (I03) and aged cheese (I06), which sell a few units a day |
| `holiday_date` | 2026-11-11, 2026-11-13, 2026-11-09 | same | same | The day of the one-off regional holiday (Wed 11 / Fri 13 / Mon 9 November), not in `holidays.csv`; demand rises by the category's holiday effect that day |
| `promo_uplift` | 1 | 1, 2, 3 | same | The printed flyer: a November promotion brings this multiple of a past promotion's extra sales (1 = no flyer, shelf labels as before) |
| `promo_cancelled` | none | none | beverages, dairy, bakery | The category whose promotions the supplier cancelled on 30 October, after the plan was exported |

`derive_params` adds `habit_cushion` (10, 20 or 30% for a cost ratio of 5, 12 or 30): the cushion the store
managers add today, which the requirements quote and the baseline uses. The rest is fixed: the 14-day horizon,
S4's Sunday closure, the core categories, I07's unit change on 1 June 2026, that I07 is judged in hard only, and
the store manager's e-mail. No `admissible()`: every combination is a sensible fortnight.

## Public panel (rule seeds 3, 25, 58) at the case seed 20261102

Every candidate of every pool appears in the panel.

| Setting | Drawn parameters | Reference | Baseline | Baseline / reference |
|---|---|---|---|---|
| easy/s3 | missed sale 30, minimum 6, holiday Mon 9 Nov | 0.3932 | 0.5366 | 1.36 |
| easy/s25 | missed sale 5, minimum 12, holiday Wed 11 Nov | 0.2883 | 0.3618 | 1.25 |
| easy/s58 | missed sale 12, minimum 4, holiday Fri 13 Nov | 0.3239 | 0.4589 | 1.42 |
| medium/s3 | missed sale 30, minimum 6, holiday Mon 9 Nov, no flyer | 0.3873 | 0.5289 | 1.37 |
| medium/s25 | missed sale 5, minimum 12, holiday Wed 11 Nov, flyer 2 | 0.2780 | 0.3516 | 1.26 |
| medium/s58 | missed sale 12, minimum 4, holiday Fri 13 Nov, flyer 3 | 0.3093 | 0.4789 | 1.55 |
| hard/s3 | missed sale 30, minimum 6, holiday Mon 9 Nov, no flyer, bakery cancelled | 0.3932 | 0.5415 | 1.38 |
| hard/s25 | missed sale 5, minimum 12, holiday Wed 11 Nov, flyer 2, beverages cancelled | 0.2860 | 0.3681 | 1.29 |
| hard/s58 | missed sale 12, minimum 4, holiday Fri 13 Nov, flyer 3, dairy cancelled | 0.3155 | 0.5006 | 1.59 |

The objective is the expected cost of the plan as a share of expected demand (lower is better): 0.39 means that the
units expected to be left over, plus 30 times the units expected to be short, come to 39% of the units customers
are expected to want. The drawn values as stored in `dataset/answer/answers.csv`, one row per setting:

```
easy/s3    {lost_sale_cost: 30, min_display: 6,  holiday_date: "2026-11-09", promo_uplift: 1, promo_cancelled: none}
easy/s25   {lost_sale_cost: 5,  min_display: 12, holiday_date: "2026-11-11", promo_uplift: 1, promo_cancelled: none}
easy/s58   {lost_sale_cost: 12, min_display: 4,  holiday_date: "2026-11-13", promo_uplift: 1, promo_cancelled: none}
medium/s3  {lost_sale_cost: 30, min_display: 6,  holiday_date: "2026-11-09", promo_uplift: 1, promo_cancelled: none}
medium/s25 {lost_sale_cost: 5,  min_display: 12, holiday_date: "2026-11-11", promo_uplift: 2, promo_cancelled: none}
medium/s58 {lost_sale_cost: 12, min_display: 4,  holiday_date: "2026-11-13", promo_uplift: 3, promo_cancelled: none}
hard/s3    {lost_sale_cost: 30, min_display: 6,  holiday_date: "2026-11-09", promo_uplift: 1, promo_cancelled: bakery}
hard/s25   {lost_sale_cost: 5,  min_display: 12, holiday_date: "2026-11-11", promo_uplift: 2, promo_cancelled: beverages}
hard/s58   {lost_sale_cost: 12, min_display: 4,  holiday_date: "2026-11-13", promo_uplift: 3, promo_cancelled: dairy}
```

Every parameter binds in every tier where it varies (validator, from each tier's s3 setting, on the case seed and
world seeds 1–3). What the s3 reference does under another value:

- `lost_sale_cost`: its objective moves by 10% (12) and 14% (5), and the reference of that setting is 7% and 23%
  better there.
- `min_display`: invalid under 12 (the s3 reference keeps a minimum of 6).
- `holiday_date`: +76% to +116% under another date.
- `promo_uplift` (medium, hard): +66% to +77% under a flyer of 2, +253% to +295% under 3.
- `promo_cancelled` (hard): +18% when beverages instead of bakery are cancelled, +12% for dairy.

On world seeds 1, 2 and 3 the baseline ÷ reference ratio is 1.22–1.44 (easy), 1.26–1.59 (medium) and 1.28–1.62
(hard).

## What an agent must ask

The clarification targets, by tier (`locales/<lang>/targets.yaml`), one fact each:

- **Every tier:** the stores order the number as it is, so it must be the quantity to order (`order_quantity`);
  what a missed sale costs against a leftover unit (`lost_sale_cost`); stockout days understate demand
  (`stockout_censoring`); the one-off holiday and its date (`one_off_holiday`); the display minimum and its value
  (`min_display`); the store manager's e-mail is not policy (`manager_note`); the rows the ordering system needs:
  one for every store, item and day, closed days and bread rolls included (`submission_format`; the header is not
  part of the fact, see Rules).
- **easy:** the promotions are left out (`base_forecast`).
- **medium and hard:** the promotions are in the order (`promo_plan`); the flyer's multiple, or that there is no
  flyer (`promo_flyer`).
- **hard:** the 30 October cancellation and its category (`promo_revision`).

So 8 targets in easy, 9 in medium, 10 in hard. Three facts of the first version are no longer targets and stay in
the requirements as context: returns (misreading them moves nothing), S4's Sunday closure and bread rolls' unit
change (the data settles both). GT.md, part 1, has the reason for each.

## Data

- `sales_history` (43,687 rows, 2024-11-04 to 2026-11-01, 104 weeks): one sales row per store, item and trading
  day with `units_sold`, `promo_discount_pct` (0 = no promotion) and a `stockout` flag (7,175 stockout rows, 17% of
  the sales rows and 10% to 31% by item, where recorded sales are 30–85% of demand), plus 1,255 separate
  customer-return rows with negative units (−2,097 units against 1,943,585 sold). S4 has no Sunday rows.
- `promo_plan`: 14 store × item promotions in the horizon (10/20/30% off, start and end inclusive); at the case
  seed 7 beverages, 3 bakery, 2 dairy and 2 produce promotions. On every world seed the plan has at least one
  promotion in each category the 30 October cancellation can draw (beverages, dairy, bakery).
- `holidays`: 12 past public holidays (Christmas, New Year's Day, a spring, summer and autumn holiday, Labour Day,
  each twice). None falls in the horizon, and the one-off holiday (on the drawn date) is not listed.
- `stores` (four supermarkets and the Old Town express store S4) and `items` (12 items in four categories: fresh
  produce I01–I03, dairy I04–I06, bakery I07–I09, beverages I10–I12, with their sales unit). Bread rolls (I07)
  are listed in packs of 6; the history records them per piece until 31 May 2026.
- `mail/2026-10-28_central_plaza_orders.eml`: an e-mail from the manager of Central Plaza (S1) to the ordering
  desk, in the client's language: "We keep running out of one line or another on Saturdays … Whatever numbers you
  get for November, please add 20% on top for Central Plaza." It is his wish, not policy; the client says so when
  asked.

The world is a multiplicative model per store × item × day (store scale and trend, category weekday profile and
yearly season, promotion lift by category and discount, holiday lift by category) with lognormal day noise
(σ = 0.07) and Poisson counts. Stockouts happen with an item's own probability (8% to 30%), plus 20 points on
promotion days, independently of the day's demand; on a stockout day the till records 30–85% of demand. The
horizon has no realized future: a day's demand in a cell is that same law around the cell's mean, with the
holiday on the drawn date and, in medium and hard, the promotions that run (the flyer multiplies their extra
demand).

## Rules

All four are rules on the order quantity.

| Rule | Class | Tiers | What it requires |
|---|---|---|---|
| `complete_grid` | contractual | all | exactly one row per store × item × date of the horizon (S4's Sundays and I07 too, even where they are not judged): the mandatory output |
| `non_negative` | physical | all | no negative order quantity |
| `closed_day_zero` | physical | all | S4 is closed on Sundays: its Sunday orders are 0 |
| `min_display_stock` | business_policy (bendable) | all | core items (fresh produce and dairy, I01–I06) are ordered at `min_display` or more for every open day |

The request names no file format, and the agent is told to infer one, so the header decides nothing: the quantity
is read from `order_qty`, else from a `forecast` column, else from the file's one other column of numbers, and the
key columns may carry the names the client's data gives them in any of the five languages (`store_id` or `점포코드`).
The stores order that number as it is. Anything else that cannot be read is fatal.

**Quality (lower is better):** per store, Σ (expected units left over + `lost_sale_cost` × expected units short)
÷ Σ expected demand over its judged items and days, averaged over the five stores. The expectation is exact: the
scorer integrates the day noise (16 Gauss-Hermite nodes) and sums the counts of the demand law above. Demand is
without the promotions in easy; I07 is judged in hard only.

## Situations present

- **Hidden facts:** what the number is used for, the cost of a missed sale, stockout days, the scope of the
  promotions, the flyer, the one-off holiday and its date, the display minimum, the file's rows.
- **A dated event (hard):** the cancellation of 30 October, after `promo_plan.csv` was exported, so the file the
  agent has is stale for one category.
- **Pressure (every tier):** the Central Plaza manager's e-mail asking for 20% on top. Following it over-orders
  the largest store.

## Reference and baseline

The **reference** is a model of expected demand per cell, from the history only: stockout days and return rows
left out, I07's history before 1 June 2026 divided by 6; a weekday profile per category, pooled over its items,
stores and both years; a level per store × item from the last twelve weeks of usable days without promotion or
holiday, carried into November by last year's change of the category's level; a promotion lift per category and
discount and a holiday lift per category, both against the local level; and an estimate of the day noise. Then
the setting: the promotions this tier has (lift × the flyer's multiple on the extra part, none for the cancelled
category), the holiday lift on the drawn day, and the order: the `lost_sale_cost / (1 + lost_sale_cost)` quantile
of the demand the model predicts for the cell; S4's Sundays at 0 and the display minimum on core items.

The **baseline** is the store managers' habit, what the client does without an engineer: for every item the
average of what the till recorded on that weekday in the last eight weeks, days the store ran out left aside, plus
a cushion of 10, 20 or 30% at a cost ratio of 5, 12 or 30; 2% more per point of discount, times the flyer's
multiple, on a promotion day; the holiday ordered like a Saturday; S4's Sundays at 0 and the display minimum. The
managers know their business (what is on promotion, the flyer, the holiday, the cancellation), not statistics.
The habit is taken at its fairest, so that the scale's zero is not a strawman: over the measured settings of the
public world and world seeds 1 and 2 these cushions cost it at most 0.002 more than the flat cushion that costs
it least at each ratio, and no other window or cushion lifts it by half the scale (a year's window at most 0.33, ten
points more cushion at most 0.16). With a four-week window, as the audit first had it, the average rested on two
to four days: the scale was up to 120% wide and a year's window alone scored up to 0.59. The first baseline
repeated last week's sales and knew none of the client's facts; an engineer who ignored them could beat it by
modelling alone.

The **best plan** (`best_known_solution` = `objective_bound`, a proven optimum) orders every cell's
cost-minimizing quantity under the true demand distribution. It scores 1.03 to 1.06 (median 1.040), so
`quality_cap` is 1.05 (the median rounded up to the next 0.01) and the reference is 1.2% to 2.2% above the
optimum.

### Literal solution

`literal_solution` is the request done as written: the reference's model fitted to sales as the till recorded them
(stockout days in, returns netted), with the promotion plan at the lift past promotions show and the holidays on
file (none in the horizon), I07's history as recorded, the store manager's 20% for Central Plaza, and the forecast
itself handed in as the number (a `forecast` column, which the stores order as it is): no cushion and no display
minimum. It is the same file in every setting and is invalid in all 9 public settings: 118 to 136 core-item orders
fall below the client's display minimum. With that rule relaxed it is valid and costs 0.61 to 3.62, against 0.35
to 0.54 for the store managers' habit: quality 0.00 in every setting, because it covers demand on half the days
where the client needs five days in six or more, and misses the holiday. The column name is not what fails it: a
`forecast` column is read as the order. The next most natural literal readings fail the same way, in all 45
audited settings and the nine of round 2026-11: the e-mail not followed, stockout days left out, bread rolls in
packs, the numbers rounded to whole units (each invalid as delivered and 0.00 with the rule relaxed).

## Ground truth audit

`fdebench2 audit-case` measures the case on 45 settings (15 per tier: the public panel and 12 other combinations).
[GT.md](../../GT.md) has the five parts with every table; [CLIENT_REVIEW.md](../../CLIENT_REVIEW.md) the passages
the client answers from, awaiting human review. In short:

| Part | Result |
|---|---|
| Client facts | 11 targets, one fact each. Every one bites (invalid, or at least 0.10 of the scale lost) in every tier where it is in force: `order_quantity` 1.00, `one_off_holiday` 1.00, `promo_plan` 0.57–1.00, `promo_revision` 0.17–1.00, `base_forecast` 0.22–0.53, `manager_note` 0.15–0.47, `stockout_censoring` 0.11–0.48, `lost_sale_cost` 0.13–0.36 (least harmful wrong candidate; in all 45 settings), `promo_flyer` 0.06–1.00 (28 of 30), `min_display` 0.00–1.00 (31 of 45 settings), `submission_format` invalid |
| Shortcuts | 12, closed in all 45 settings: the literal with the display minimum kept (0.00), the expected demand as the order (0.00), a blanket 20% on the literal forecast (0.00), last week copied (0.00), one average per item (0.00), never run out (0.00), the display minimum only (0.00), unjudged rows left out (invalid), the managers' habit over a year's window (at most 0.33) or with ten points more cushion (at most 0.16), the literal forecast with a cushion sized for the cost ratio (0.00), the weekday's own sales quantile (0.00) |
| Value of asking | A plan that never asks keeps 0.10 / 0.18 / 0.14 of the credit in easy / medium / hard, so asking is worth 0.90 / 0.82 / 0.86; the best single reference of another setting keeps 0.20–0.23 |
| Reference and bounds | Best plan = proven optimum, quality 1.026–1.059; reference 1.2–2.2% above it; scale 25% to 72% of the reference's cost wide |
| Diagnostics | Every target has one, read from the plan against the demand law. It separates the reference from every ablation that bites, never calls the best plan not enforced, and no ablation flags another target, on the public world and on world seeds 1–10 |

**Bending the display minimum** pays in some settings and loses in others. Dropping it gains the reference 0.35 to
0.43 of quality where the minimum is 12 and a missed sale costs 5, 0.11 to 0.23 at 12 with a dearer missed sale,
0.00 to 0.07 at 6 and nothing at 4. Against the policies' penalties (0.05 and 0.10 of the final score, quality
weighing 0.6: a gain above 0.09 and 0.18) that pays under both policies in the first case, under the startup
policy in the second and loses elsewhere. A plan already at the reference's level gains at most 0.05 of credit,
because full credit is the best plan that keeps the rule.

## Notes

- Synthetic. All volumes, profiles, elasticities, holiday effects, cost ratios and stockout rates are invented;
  nothing is calibrated to a real chain. The holiday calendar is generic (see REVIEW.md, F8).
- One cost ratio for every product is a simplification: fresh produce that is thrown away and bottled water that
  keeps do not cost the same when left over (REVIEW.md, Ground truth audit, open items).
- `validate-case` checks deterministic data in five locales, the reference at quality 1.0 in every public setting,
  a valid baseline worse than the reference, one deliverable per rule that breaks only that rule, that every
  parameter binds, the literal solution, the stored audit and world seeds 1–3.
