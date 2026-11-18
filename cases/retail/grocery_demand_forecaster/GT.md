# Ground truth — retail/grocery_demand_forecaster

The ground truth of every setting in five parts: the client facts the agent must learn, the validity checks, the objective, the reference with its bounds, and the diagnostic cases. Every table is generated from `dataset/audit.json` by `make_gt.py` (world seed 20261102; per tier the public panel and 12 admissible combinations of the tier's candidates: easy 15, medium 15, hard 15 settings). Credit is 0 for an invalid deliverable, else quality clipped to [0, 1]; damage = 1 − credit. A fact bites in a setting when misreading it loses at least 0.1 of credit (for a parameter: the least harmful other candidate, an agent that guesses wrong but sensibly).

This is the benchmark's forecasting case, and its ground truth follows the rules for such cases (docs/DIRECTION.md, section 5): no forecast is "the" answer, so nothing is compared with a reference forecast or with one realized November. The deliverable is the decision the client takes from the forecast, an order per store, item and day; it is scored by its expected cost under the demand distribution the world itself draws from; the client's costs choose the loss; and the rules are rules on the order.

## 1. Client facts

One row per target (`locales/en/targets.yaml`). *Ablated as*: a parameter is read as each other candidate of its tier (the reference of that candidate, scored here); any other fact as the reference with its most natural misreading of the agent's own view. *Damage*: min–max over the settings where it is in force (best guess for a parameter).

| target | fact | in force | ablated as | damage | bites | diagnostic |
|---|---|---|---|---|---|---|
| `order_quantity` | The stores order exactly the number in the file for each day and add nothing of their own, so it must be the quantity to order, not the expected sales. | easy, medium, hard | the number read as a sales forecast to which the stores add their own cushion: the expected demand handed in | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `lost_sale_cost` | A unit a customer wanted and did not find costs about {{lost_sale_cost}} times as much as a unit left over at closing. | easy, medium, hard | another candidate of `lost_sale_cost` | 0.133–0.355 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `stockout_censoring` | On stockout days units_sold is capped by what was in stock and customer demand was higher; the order must cover demand, so those days must not be treated as normal sales. | easy, medium, hard | stockout days read as normal sales and returns netted: the history as the till recorded it | 0.111–0.484 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `base_forecast` | This round the order leaves the promotions in promo_plan.csv out; the category team adds their effect on top afterwards. | easy | the promotion plan read as part of the order (the file is attached), at the historical lift | 0.220–0.534 | easy 15/15 | separates |
| `one_off_holiday` | The one-off regional holiday on {{holiday_date}} is not in holidays.csv; stores are open and demand rises as on past holidays, most for bakery and beverages. | easy, medium, hard | another candidate of `holiday_date` | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `min_display` | Core items (fresh produce and dairy, I01-I06) are never ordered below {{min_display}} units on a day the store is open. | easy, medium, hard | another candidate of `min_display` | 0.003–1.000 | easy 10/15, medium 12/15, hard 9/15 | separates |
| `manager_note` | The Central Plaza (S1) store manager's e-mail asking for 20% on top is his own wish, not company policy; S1 is ordered like every other store. | easy, medium, hard | the store manager's e-mail followed: 20% on top for Central Plaza | 0.150–0.469 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `submission_format` | The ordering system loads the file as it is, so it needs exactly one row for every store, item and day from 2026-11-02 to 2026-11-15 (840 rows), S4's Sundays (order 0) and bread rolls (I07) included. | easy, medium, hard | rows only where the store trades: S4's Sundays left out | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `promo_plan` | The promotions in promo_plan.csv run in the forecast period and must be in the order quantities; nobody adds them afterwards. | medium, hard | the promotions read as somebody else's top-up: the order without them | 0.574–1.000 | medium 15/15, hard 15/15 | separates |
| `promo_flyer` | [1: The November promotions run like past ones (shelf labels only, no flyer), so the lift learned from the history applies as it is.] [2,3: The November promotions are also in the printed flyer and bring about {{promo_uplift}} times the extra sales of a past promotion with the same discount in the same category.] | medium, hard | another candidate of `promo_uplift` | 0.059–1.000 | medium 15/15, hard 13/15 | separates |
| `promo_revision` | On Friday 30 October, after promo_plan.csv was exported, all {{promo_cancelled}} promotions in the plan were cancelled; they do not run, and the rest of the plan stands. | hard | another candidate of `promo_cancelled` | 0.174–1.000 | hard 15/15 | separates |

Facts the client states that are no longer targets (they stay in requirements.md as context, and the client still answers them when asked):

- **Returns** (the rows with negative units are not demand): netting them moves the reference by less than 0.003 of the scale (1,255 return rows, 2,097 units against 1,943,585 sold). The reference leaves them out, and the `stockout_censoring` ablation nets them, as a reader of the till record would.
- **S4's Sunday closure**: the data settles it (the history has no Sunday row for S4), and the natural reading is the right one. It stays a rule (`closed_day_zero`); what the data does not settle, that the closed days still need their rows, is in `submission_format`.
- **Bread rolls' unit change** (hard): the data settles it too (`items.csv` says pack of 6 and the history drops sixfold on 1 June 2026). Taking the history as recorded costs the reference 0.09 to 0.21 in hard, so it is dropped because the data answers it, not for its weight. Bread rolls are still judged in hard only.
- **How the plan is judged**: the first version's `wape_metric` bundled the error weight with what the actuals were. The weight became the business fact `lost_sale_cost`; the actuals are no longer a choice (an order has to cover demand, so `stockout_censoring` is in force in every tier).
- **How the stores order today** (the managers' habit and its cushion): context for the client's own way, which is the zero of the quality scale.

## 2. Validity checks

Every rule of case.yaml is a hard gate (`physical` and `contractual` never bend; `business_policy` bends only through the company policy's exception path). All four are rules on the order quantity, the decision the client takes from the forecast: a forecast is never invalid for being low, since the file is the order and a low order is only costly. A file that cannot be read (no `forecast.csv`, no quantity column, an unknown store or item, a date outside the horizon, a quantity that is not a number) is fatal. The header decides nothing, because the request names no format and the stores order the number they are given: the quantity is read from `order_qty`, else from a `forecast` column, else from the file's one other column of numbers, and the key columns may carry the names the client's own data gives them in any of the five languages.

| rule | class | tiers | why it is a hard gate |
|---|---|---|---|
| `complete_grid` | contractual | easy, medium, hard | the ordering system loads one number per store, item and day: a missing row is a product nobody orders. The mandatory output: S4's Sundays and bread rolls have rows too, also where they are not judged |
| `non_negative` | physical | easy, medium, hard | an order cannot be negative |
| `closed_day_zero` | physical | easy, medium, hard | nobody takes a delivery at a closed store |
| `min_display_stock` | business_policy | easy, medium, hard | the client's habit for its core shelves (business policy): a hard gate under the baseline policy, bendable with an approved exception under the others. It is a rule on the order, the decision; no forecast is invalid for being low |

**Bending the display minimum.** What an approved exception is worth: the reference with the minimum dropped (every core item at its own cost-minimizing order), scored with the rule relaxed, against the reference that keeps it; and the quality of the best plan without the minimum. Over the audit's settings, by drawn minimum and cost ratio:

| display minimum | a missed sale costs | settings | gain of the reference when it bends | best plan without the minimum (quality) |
|---|---|---|---|---|
| 4 | 5 | 2 | 0.00 | 1.05 |
| 4 | 12 | 5 | 0.00 | 1.04–1.05 |
| 4 | 30 | 5 | 0.00 | 1.03–1.05 |
| 6 | 5 | 4 | 0.04–0.07 | 1.08–1.12 |
| 6 | 12 | 5 | 0.02 | 1.05–1.08 |
| 6 | 30 | 9 | 0.00–0.01 | 1.03–1.06 |
| 12 | 5 | 8 | 0.35–0.43 | 1.40–1.48 |
| 12 | 12 | 3 | 0.14–0.23 | 1.18–1.29 |
| 12 | 30 | 4 | 0.11–0.17 | 1.14–1.21 |

A bent rule costs a policy's penalty (0.05 under the startup policy, 0.10 under the enterprise one) and quality weighs 0.6 there, so a gain g pays when 0.6 × g / quality_cap exceeds the penalty: g above 0.09 and 0.18. The bend therefore pays under both policies where the minimum is 12 and a missed sale costs 5 (the minimum forces eight or nine units a day of items that sell three), under the startup policy where it is 12 and a missed sale costs 12 or 30 (under the enterprise policy only in the settings at the top of the range at 12), and loses with a minimum of 4 or 6, where the cost-minimizing order is already at or near the minimum. This holds for a plan with room under `quality_cap` 1.05: a plan at the reference's level can gain at most 0.05 of quality credit from any bend, less than either penalty, because the cap is the best plan that keeps the rule.

## 3. Objective

objective = the mean over the five stores of (Σ over the store's judged items and days of the expected units left over + `lost_sale_cost` × the expected units short) ÷ (Σ of the expected demand); minimize.

- **The decision picks the loss.** The stores order exactly the number in the file, so a unit too many is a unit left over at closing (written off or cleared at a loss: one unit's worth) and a unit too few is a missed sale, which costs the client `lost_sale_cost` times as much (5, 12 or 30: the margin, and customers who go elsewhere). The same forecast is a good order under one ratio and a poor one under another, for a reason the client can explain.
- **Expected loss, not one draw.** A day's demand in a cell is the cell's mean times lognormal day noise (sd 0.07), counted as a Poisson number (a rounded normal from 30 on), exactly as the history was drawn. `score()` integrates the day noise with 16 Gauss-Hermite nodes and sums the counts, so the expected units left over and short of any order are exact and the same on every machine: no realized future, no luck. The first version scored the weighted WAPE against one drawn horizon.
- **Whose demand.** The cell's mean is the world's own: the store's scale and trend, the category's weekday profile and season, the holiday's effect on the drawn date, and in medium and hard the promotions that run (the plan minus the cancelled category, times the flyer's multiple). In easy the promotions are the category team's, so demand is the demand without them. Bread rolls are judged in hard only; a closed day has no demand, so anything ordered there is left over (and breaks `closed_day_zero`).
- **The zero and the one.** Quality 0 is the store managers' habit (`baseline_solution`): the average of the last eight weeks' sales of that weekday, days the store ran out left aside, plus a cushion of 10, 20 or 30% at a cost ratio of 5, 12 or 30, 2% more per point of discount times the flyer's multiple on promotion days, the holiday ordered like a Saturday, the display minimum and S4's Sundays at 0. The managers know their business, not statistics. The habit is taken at its fairest: over the measured settings of the public world and world seeds 1 and 2 these cushions cost it at most 0.002 more than the flat cushion that costs it least at each ratio, and no other window or cushion lifts it by half the scale (shortcuts `habit_last_year`, `habit_more_cushion`). Quality 1 is the reference (part 4).

## 4. Reference and bounds

- **Reference** (`reference_solution`): a model of expected demand per cell from the history only: stockout days and return rows left out, bread rolls' early history divided by 6; a weekday profile per category pooled over its items, stores and both years; a level per store and item over the last twelve weeks, carried into November by last year's change of the category's level; a promotion lift per category and discount and a holiday lift per category against the local level; and the day noise left once Poisson counting is taken out. The order is the `lost_sale_cost / (1 + lost_sale_cost)` quantile of the demand the model predicts for the cell, with S4's Sundays at 0 and the display minimum on core items.
- **Best known** (`best_known_solution`): every cell's cost-minimizing order under the true demand distribution (hindsight no agent has: the true mean of every cell), raised to the display minimum.
- **Bound** (`objective_bound`, proven, and attained): the objective is a sum over cells of a cost that depends on that cell's order alone, divided by constants, and every rule bounds one cell's order. A cell's expected cost is convex in the order with its minimum at the `k / (1 + k)` quantile, so no valid plan costs less in a cell than that quantile, or the display minimum where it is higher. The best known solution is that plan, so the gap between the two is zero and the gap below is the reference's distance from the optimum.

| setting | reference | baseline | span | best known | best known quality | bound | bound quality | gap (reference − bound) / reference |
|---|---|---|---|---|---|---|---|---|
| easy/s3 | 0.3932 | 0.5366 | 0.365 | 0.3876 | 1.039 | 0.3876 | 1.039 | 0.014 |
| easy/s25 | 0.2883 | 0.3618 | 0.255 | 0.2849 | 1.047 | 0.2849 | 1.047 | 0.012 |
| easy/s58 | 0.3239 | 0.4589 | 0.417 | 0.3191 | 1.035 | 0.3191 | 1.035 | 0.015 |
| easy/c1 | 0.4150 | 0.6159 | 0.484 | 0.4093 | 1.028 | 0.4093 | 1.028 | 0.014 |
| easy/c2 | 0.3933 | 0.5384 | 0.369 | 0.3876 | 1.039 | 0.3876 | 1.039 | 0.014 |
| easy/c3 | 0.3926 | 0.5475 | 0.395 | 0.3865 | 1.039 | 0.3865 | 1.039 | 0.016 |
| easy/c4 | 0.4163 | 0.5571 | 0.338 | 0.4107 | 1.040 | 0.4107 | 1.040 | 0.013 |
| easy/c5 | 0.3264 | 0.4581 | 0.404 | 0.3218 | 1.035 | 0.3218 | 1.035 | 0.014 |
| easy/c6 | 0.3273 | 0.4316 | 0.319 | 0.3228 | 1.043 | 0.3228 | 1.043 | 0.014 |
| easy/c7 | 0.2872 | 0.3736 | 0.301 | 0.2838 | 1.040 | 0.2838 | 1.040 | 0.012 |
| easy/c8 | 0.2558 | 0.3431 | 0.341 | 0.2524 | 1.040 | 0.2524 | 1.040 | 0.013 |
| easy/c9 | 0.3925 | 0.5462 | 0.392 | 0.3864 | 1.039 | 0.3864 | 1.039 | 0.015 |
| easy/c10 | 0.3921 | 0.5959 | 0.520 | 0.3864 | 1.028 | 0.3864 | 1.028 | 0.015 |
| easy/c11 | 0.2566 | 0.3296 | 0.285 | 0.2532 | 1.046 | 0.2532 | 1.046 | 0.013 |
| easy/c12 | 0.2612 | 0.3347 | 0.282 | 0.2577 | 1.047 | 0.2577 | 1.047 | 0.013 |
| medium/s3 | 0.3873 | 0.5289 | 0.365 | 0.3811 | 1.044 | 0.3811 | 1.044 | 0.016 |
| medium/s25 | 0.2780 | 0.3516 | 0.265 | 0.2736 | 1.059 | 0.2736 | 1.059 | 0.016 |
| medium/s58 | 0.3093 | 0.4789 | 0.549 | 0.3028 | 1.038 | 0.3028 | 1.038 | 0.021 |
| medium/c1 | 0.3332 | 0.4992 | 0.498 | 0.3271 | 1.037 | 0.3271 | 1.037 | 0.019 |
| medium/c2 | 0.3201 | 0.4241 | 0.325 | 0.3148 | 1.051 | 0.3148 | 1.051 | 0.017 |
| medium/c3 | 0.3810 | 0.5336 | 0.401 | 0.3734 | 1.050 | 0.3734 | 1.050 | 0.020 |
| medium/c4 | 0.2530 | 0.3267 | 0.291 | 0.2487 | 1.059 | 0.2487 | 1.059 | 0.017 |
| medium/c5 | 0.2570 | 0.3276 | 0.275 | 0.2532 | 1.053 | 0.2532 | 1.053 | 0.015 |
| medium/c6 | 0.3222 | 0.4243 | 0.317 | 0.3172 | 1.049 | 0.3172 | 1.049 | 0.015 |
| medium/c7 | 0.3211 | 0.4579 | 0.426 | 0.3161 | 1.037 | 0.3161 | 1.037 | 0.016 |
| medium/c8 | 0.2481 | 0.3601 | 0.451 | 0.2433 | 1.043 | 0.2433 | 1.043 | 0.019 |
| medium/c9 | 0.2831 | 0.3548 | 0.253 | 0.2792 | 1.054 | 0.2792 | 1.054 | 0.014 |
| medium/c10 | 0.3818 | 0.5231 | 0.370 | 0.3745 | 1.051 | 0.3745 | 1.051 | 0.019 |
| medium/c11 | 0.3350 | 0.4408 | 0.316 | 0.3288 | 1.059 | 0.3288 | 1.059 | 0.019 |
| medium/c12 | 0.4076 | 0.6120 | 0.502 | 0.4014 | 1.030 | 0.4014 | 1.030 | 0.015 |
| hard/s3 | 0.3932 | 0.5415 | 0.377 | 0.3868 | 1.043 | 0.3868 | 1.043 | 0.016 |
| hard/s25 | 0.2860 | 0.3681 | 0.287 | 0.2821 | 1.047 | 0.2821 | 1.047 | 0.014 |
| hard/s58 | 0.3155 | 0.5006 | 0.587 | 0.3088 | 1.036 | 0.3088 | 1.036 | 0.021 |
| hard/c1 | 0.3148 | 0.4903 | 0.558 | 0.3085 | 1.036 | 0.3085 | 1.036 | 0.020 |
| hard/c2 | 0.3233 | 0.4306 | 0.332 | 0.3173 | 1.056 | 0.3173 | 1.056 | 0.018 |
| hard/c3 | 0.3965 | 0.5532 | 0.395 | 0.3904 | 1.039 | 0.3904 | 1.039 | 0.015 |
| hard/c4 | 0.2805 | 0.3538 | 0.261 | 0.2762 | 1.057 | 0.2762 | 1.057 | 0.015 |
| hard/c5 | 0.3861 | 0.6459 | 0.673 | 0.3783 | 1.030 | 0.3783 | 1.030 | 0.020 |
| hard/c6 | 0.3926 | 0.5506 | 0.402 | 0.3858 | 1.043 | 0.3858 | 1.043 | 0.017 |
| hard/c7 | 0.3953 | 0.6288 | 0.591 | 0.3892 | 1.026 | 0.3892 | 1.026 | 0.016 |
| hard/c8 | 0.3486 | 0.4994 | 0.432 | 0.3434 | 1.035 | 0.3434 | 1.035 | 0.015 |
| hard/c9 | 0.2852 | 0.3582 | 0.256 | 0.2813 | 1.053 | 0.2813 | 1.053 | 0.014 |
| hard/c10 | 0.4127 | 0.5788 | 0.403 | 0.4060 | 1.040 | 0.4060 | 1.040 | 0.016 |
| hard/c11 | 0.2851 | 0.3578 | 0.255 | 0.2812 | 1.053 | 0.2812 | 1.053 | 0.014 |
| hard/c12 | 0.3819 | 0.6549 | 0.715 | 0.3736 | 1.030 | 0.3736 | 1.030 | 0.022 |

The quality scale is 25% to 72% of the reference's cost wide. The best plan reaches 1.026–1.059 on it (median 1.040); the reference is 1.2%–2.2% above the optimum. **quality_cap** = 1.05: the median quality of the best plan over the measured settings, rounded up to the next 0.01 (full credit at the optimum; DESIGN.md, Ground truth audit).

**Value of asking** (never asks = `robust_solution`: the agent's view at its natural reading, with stockout days left out, the promotion plan in the order and bread rolls in packs; every candidate date of the holiday, flyer multiple and cancelled category taken as an equally likely scenario; one cost ratio for the whole pool; the strictest display minimum. It is granted two facts it could not know, that the number is ordered as it is and that the manager's e-mail is not followed. never asks (params) = the best single setting's reference, which knows every fixed fact):

| tier | never asks (credit) | its validity rate | voi | never asks (params) | voi_params |
|---|---|---|---|---|---|
| easy | 0.105 | 1.000 | 0.895 | 0.230 | 0.770 |
| medium | 0.180 | 1.000 | 0.820 | 0.207 | 0.793 |
| hard | 0.139 | 1.000 | 0.861 | 0.200 | 0.800 |

## 5. Diagnostic cases

`score()` returns `enforced` and `evidence` per target in force, for valid and invalid plans alike, from the plan itself: each check reads the orders where only that fact decides them and compares them with the demand distribution, which the scorer knows. *Ordinary* store × item days are open, judged, without a promotion in `promo_plan.csv`, not on a date the holiday can fall on and not a slow core item; a promotion day and the holiday are compared with the same weekday of the other week, itself an ordinary day. The yardstick is the best plan (part 4), so it is enforced by construction; for a plan that hands in the expected demand it is the expected demand, since a cushion grows more slowly than the demand it covers. Central Plaza is left out of the cost-ratio check and has its own store effect in the stockout check, so that following the note flags the note alone; the stockout check also takes out what an item's category shares, so that a model that misses a category's season is not read as one that misreads stockouts. *Separates*: the reference is enforced in every measured setting and every ablation that bites is not.

| target | what tells a plan that implements the fact from one that misreads it | reference enforced | ablations |
|---|---|---|---|
| `order_quantity` | the share of ordinary store × item days whose demand the order covers: clearly above what the expected demand, ordered as it is, covers | yes | separates |
| `lost_sale_cost` | the same share, against the share the best plan covers at each candidate ratio: not enforced when it sits at another candidate's, within a quarter of the way from there to the client's (not told for a plan that hands in the expected demand: no cushion to read). It reads the cushion the plan ends up with, not the ratio its author had in mind | yes | separates |
| `stockout_censoring` | store by store and item by item, how far the orders stand above expected demand, set against the item's stockout rate once its category, the store and the cell's variability are accounted for: reading stockout days as sales lowers the orders most for the items that run out most (enforced under half of that pattern) | yes | separates |
| `base_forecast` | promotion days against the same weekday of the other week (slow core items left out: a display minimum flattens them): under half of what the best plan adds for a promotion at the historical lift | yes | separates |
| `promo_plan` | the same comparison: at least one category of the promotions in force carries half the historical lift or more | yes | separates |
| `promo_flyer` | the lift the promotion days carry, as a multiple of the historical lift: nearest to the flyer's multiple among the candidates' and not past the largest one by more than half a step (not told when stockout days are read as sales, which understates the lift itself) | yes | separates |
| `promo_revision` | the cancelled category's promotion days carry under a quarter of the historical lift, and no category that still runs was dropped in its place (not told for a plan without any promotion) | yes | separates |
| `one_off_holiday` | the holiday against the same weekday of the other week: half the best plan's holiday lift or more, overall and in bakery and in beverages, the categories the client names | yes | separates |
| `min_display` | no core order under the minimum on an open day, and the slow core items (basil, aged cheese) not held flat at a higher candidate | yes | separates |
| `manager_note` | Central Plaza's orders against the other stores', each against its best plan: under half of the 20% the note asks for | yes | separates |
| `submission_format` | every store × item × date exactly once | yes | separates |

**Reliability on other deliverables** (a run's deliverable is neither the reference nor an ablation). Settings where the diagnostic calls the deliverable not enforced, of those where it gives a True or False: the best known solution (valid, built with full knowledge of its setting, so every one would be a false negative), the ablation of the target that also calls other targets not enforced (of the settings where it bites; facts can interact), and the baseline (each setting's own) and `robust_solution` (its tier's), which are informational: neither is built with full knowledge.

| target | best known | cross flags | baseline | robust_solution |
|---|---|---|---|---|
| `order_quantity` | 0/45 | 0/45 | 0/45 | 0/45 |
| `lost_sale_cost` | 0/45 | 0/45 | 0/45 | 32/45 |
| `stockout_censoring` | 0/45 | 0/45 | 0/45 | 0/45 |
| `base_forecast` | 0/15 | 0/15 | 0/15 | 15/15 |
| `promo_plan` | 0/30 | 0/30 | 0/30 | 0/30 |
| `promo_flyer` | 0/30 | 0/30 | 1/30 | 21/30 |
| `promo_revision` | 0/15 | 0/15 | 0/15 | 15/15 |
| `one_off_holiday` | 0/45 | 0/45 | 17/45 | 0/45 |
| `min_display` | 0/45 | 0/44 | 0/45 | 30/45 |
| `manager_note` | 0/45 | 0/45 | 0/45 | 0/45 |
| `submission_format` | 0/45 | 0/45 | 0/45 | 0/45 |

The baseline leaves out the days the store ran out, and the stockout check passes it; it orders the holiday like a Saturday, which misses bakery's lift where the holiday is a Friday, and the holiday check says so. `robust_solution` plans for one cost ratio, the strictest minimum and every scenario of the flyer and the cancellation, and keeps the promotions in easy: it is called not enforced where the client's value is another one, which is the diagnostic working as meant.

**Shortcuts** (closed: invalid, or quality at most 0.5):

| shortcut | what it does | closed in | best quality where valid |
|---|---|---|---|
| `literal_plus_floor` | The literal solution with the one rule it breaks kept: the display minimum on core items. | 45/45 | 0.000 |
| `forecast_as_order` | Ignore the uncertainty: every other fact right, the expected demand handed in as the order. | 45/45 | 0.000 |
| `blanket_cushion` | Pad everything: the literal forecast with the store manager's 20% on top for every store. | 45/45 | 0.000 |
| `copy_last_week` | Copy the data through: last week's sales of the same weekday, for both weeks. | 45/45 | 0.000 |
| `flat_average` | Output constants: one number per store and item, its average day of the last eight weeks, every day. | 45/45 | 0.000 |
| `never_run_out` | Never run out: every day the most the store sold of the item on any day of the last eight weeks. | 45/45 | 0.000 |
| `display_only` | Order nothing but the display minimum of the core items. | 45/45 | 0.000 |
| `judged_rows_only` | Leave out the rows that are not judged or always 0: bread rolls (I07) and S4's Sundays. | 45/45 | – |
| `habit_last_year` | Copy the client's own way and change one thing: the managers' habit averaged over the last 52 weeks. | 45/45 | 0.328 |
| `habit_more_cushion` | Copy the client's own way and pad it: the managers' habit with ten points more cushion. | 45/45 | 0.159 |
| `literal_sized_cushion` | Ask one thing only, the cost of a missed sale: the literal forecast with a flat cushion sized for it. | 45/45 | 0.000 |
| `weekday_quantile` | No model: per store, item and weekday, the cost ratio's quantile of the last 26 weeks' sales. | 45/45 | 0.000 |

**Findings** (as validate-case reads the stored audit with this quality_cap; OPEN_AUDIT_FINDINGS may waive a problem):

- none
