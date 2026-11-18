# Review — `retail/grocery_demand_forecaster`

Findings of the case review, each with the verifier's verdict and its status after this change. Quality numbers
below use the new scale (seasonal-naive baseline 0, reference 1) unless they are marked as ratios.

### F1 — No settings: one fixed problem at every difficulty (high, partly)

`case.yaml` declares no tiers, rule sets or `param_labels`; the only ground truth is `gt/default` (the layout before
`dataset/answer/`). So the
difficulty column says nothing about this case, and "which rules apply this time" is never tested. Settings-less
cases are allowed by DESIGN.md (8 of the 13 built cases have none), so this is a coverage gap, not a contract
breach.

**Status:** open — proposal: convert to 3×3 while keeping the visible data byte-identical. Easy = base demand only
(requirements say promotions and the 11 November holiday are handled elsewhere this round); medium adds the
promotion plan, the holiday and the I07 unit change; hard adds the parts that need new scored truth (a dated
revision, a closure, pressure, asymmetric cost on perishables). Rule-set parameters should be ones the data does
not reveal: holiday date (Wed 11 / Fri 13 / Mon 9 Nov), floor (6 on produce + dairy / 4 on dairy only / 8 on
produce only), a future closure (none / S2 on 15 Nov / S5 on the holiday). Do not use store-mean vs.
volume-weighted WAPE as a rule-set pair (same per-cell minimizer, so the references would not differ by 1%), and
do not put informative censoring in hard only (it changes the visible history).

**Status (rule seeds):** resolved — converted to 3 tiers and 5 parameters drawn by rule seeds; see "Rule seeds"
below. The data stays byte-identical. Easy is the base forecast only (the requirements say the category team adds
the promotions and the one-off holiday this round) and is scored against base till sales; medium adds the
promotion plan and the holiday; hard adds what the owner placed there: stockout censoring and returns (hard is
judged against demand, the lower tiers against till sales net of returns), the I07 unit change (I07 is judged in
hard only) and a dated promotion revision. The proposal's store-mean vs. volume-weighted WAPE pair was not used;
the asymmetric cost became the error weight `short_weight` in every tier. The future-closure parameter and a
pressure message are not done (F7).

### F2 — Little headroom above the reference (high, confirmed)

The reference WAPE is 0.1470, the oracle (true generator mean plus the floor) 0.1381, the baseline 0.2790. On
the new scale the oracle reaches quality 1.067 (1.118 / 1.167 / 1.072 on world seeds 1–3), and per-category
promotion and holiday lifts alone give 1.039. Quality is no longer clipped at 1.0, but with the policy cap of 1.5
even a perfect model earns only about 71% of the quality credit, and the gap between a good and an excellent
agent is a few hundredths. The cause is a clean multiplicative generator whose Poisson and day noise dominate.

**Status:** open — proposal: add learnable structure that a plain heuristic misses (informative censoring,
post-promotion dips, within-category cannibalization, a store level shift mid-history, an intermittent slow
mover, a new item with an analog), then strengthen the reference so the oracle sits about 10% above it. Until
then, set `quality_cap` in `case.yaml` near what a strong but achievable model reaches (about 1.05 at this seed),
so full credit does not require beating the oracle. Add a check that keeps the oracle's quality within a band
across world seeds.

**Rule seeds:** the numbers above are for the old single problem. The reference now measures the promotion lift
per category and discount and the holiday lift per category (it pooled both over all categories), and takes the
error weight's quantile of its own residual ratios. Under the new truths the oracle (the true outcome
distribution's quantile per cell) reaches quality 1.05–1.06 in easy and medium and only 1.01–1.03 in hard at the
case seed; in easy and medium a demand fit also beats the till-sales reference by 3–5%. Headroom in hard is
smaller than before, so the `quality_cap` question is more pressing. The expected-loss scoring redesign the owner
is considering for forecasting cases (docs/DIRECTION.md, section 5) is not implemented: scoring is still the
weighted WAPE against one realized horizon. Still open.

**Ground truth audit:** resolved. Scoring is now the plan's expected cost under the demand distribution the world
draws from, so the optimum is known and proven (`objective_bound`, attained by `best_known_solution`): it scores
1.026–1.059 over 45 settings, and `quality_cap` is 1.05, its median (1.040) rounded up. The reference pools the
weekday profile per category and orders a quantile of the demand it predicts; it is 1.2–2.2% above the optimum.
The small headroom is now what full credit means, not a defect: nothing valid can score above the cap by more
than 0.01. (With the first, four-week baseline of the audit the optimum scored 1.018–1.040 and the cap was 1.03;
see "Adversarial check" below.)

### F3 — Display floor stated as 2 in `case.yaml`, 6 everywhere else (high, confirmed)

`case.yaml` described `min_display_stock` as "never forecast below 2 units", while `MIN_DISPLAY = 6.0` in
`case.py`, all five requirements and the target say 6. The exception classifier sees the `case.yaml` text next
to the requirements, so the client was shown both numbers at the one moment the bendable rule matters, and the
explainer printed both. A floor of 2 would not bind (reference 0.13948 vs. 0.13947 without a floor). The
validator's number lint missed it because "2" appears in the requirements as a date ("Monday 2 November").

**Status:** fixed in this change — the rule description now says 6, matching `MIN_DISPLAY`, the requirements and
the target. No `{{min_display}}` placeholder: the case has no rule sets to fill it from.

**Rule seeds:** the floor is now the parameter `min_display` (6, 4 or 8). The rule description, the requirements,
the `min_display` target and the explainer's rule texts in all five locales insert `{{min_display}}`, so they
always state the drawn value, which is the one `case.py` checks.

### F4 — Bending the display floor never pays (medium, confirmed)

The floor binds on 136 reference cells (basil I03 and aged cheese I06, 1.3% of horizon demand). Dropping it gives
WAPE 0.1395, quality 1.057 (1.084–1.089 on seeds 1–3). At a quality weight of 0.6 and cap 1.5 that is worth
about 0.6 × 0.057 / 1.5 ≈ 0.023 of composite, below both soft-rule penalties (0.05 startup, 0.10 enterprise). WAPE
against true demand gives no credit for shelf presence, so "never bend" is always the right answer.

**Status:** open — proposal: make bending a real trade-off. Either price shelf presence in the objective (a cost
for open-day core forecasts below the floor on days the item sells, or score order quantities that include the
floor), or make the floor bind on more items and calibrate it so bending gains more than the startup penalty but
less than the enterprise one. Document the expected bend / no-bend answer per policy in the README.

**Rule seeds:** partly. Bending now pays a different amount per setting: dropping the floor gains 6.5–11.4%
quality with a floor of 6 or 8 and 0.1–0.3% with a floor of 4 under error weight 3, where the quantile forecast
already clears it (README). It is never negative, so "never bend" is still not a real trade-off. Still open.

**Ground truth audit:** partly resolved. The minimum is a rule on the order and its pool is 4, 6 or 12. Dropping it
gains the reference 0.35–0.43 of quality where the minimum is 12 and a missed sale costs 5, 0.11–0.23 at 12 with a
dearer missed sale, at most 0.07 at 6 and nothing at 4 (GT.md, part 2). Against the policies' penalties that pays
under both policies in the first case, under the startup policy in the second and loses in the others, so the
answer now depends on the setting. What is left: a plan already at the reference's level cannot gain more than
0.05 from any bend, because `quality_cap` is the best plan that keeps the rule; the bend pays only for plans with
room under the cap.

### F5 — Several data-semantics traps barely bind (medium, partly)

Measured as one change to the reference: netting returns gives quality 1.001 (1,286 return rows, −2,104 units
against 2,002,817 sold), ignoring the I07 unit change 0.986, using stockout days as normal 0.960, missing the
holiday 0.927, ignoring the promotion plan 0.855. Stockouts depend only on the item and promotion status, not on
the day's demand, so dropping flagged days is unbiased. The verifier notes the unit change does bind for
long-window models (a 52-week weekday mean falls from ratio 0.945 to 0.476 without it) and that the stockout
effect, while small, is half the oracle headroom.

**Status:** open — proposal: make censoring informative (cap sales at a shelf or inventory level so stockouts
fall on high-demand days, which makes dropping them bias low). Make returns material (e.g. occasional bulk
returns from a catering account) or drop the returns target. Moving the I07 change into the recent window
(e.g. 2026-10-05) would make it bind for every model; all of these change the visible data and the reference
numbers.

**Rule seeds:** the data is unchanged, so this stands. Censoring, returns and the unit change are now hard-only
targets. In hard, fitting till sales as recorded costs the reference 6–7% quality, while not dividing I07's early
history by 6 (0.991–0.999) and netting returns (0.999–1.001) still barely move it. Still open.

**Ground truth audit:** partly resolved. Stockout days now cost: the order has to cover demand in every tier, a
unit short costs 5 to 30 units left over, and the items run out more often (8–30% of days, was 5–20%; the history
was redrawn). Reading stockout days as normal sales loses 0.11–0.48 of the scale and bites in all 45 settings.
Returns still move nothing (under 0.003) and are no longer a target; bread rolls' unit change costs 0.09–0.21 in
hard but the data settles it, so it is context too. Still open: stockouts stay independent of the day's demand,
so leaving flagged days out is unbiased; capping sales at a shelf level would make that biased as well, and needs
a reference that treats flagged days as lower bounds.

### F6 — Targets that the data already settles count fully in Ask-F1 (medium, partly)

`s4_sunday_closed` (S4 has no Sunday rows) and `unit_change_i07` (items list "pack of 6", the history drops about
6× on 1 June 2026) are labelled `missing`, and Ask-F1 recall counts all nine targets equally, while the agent is
told to ask only about what the data does not settle. The verifier rejects the reviewer's 4/9 figure: stockout
censoring and returns are correctly `ambiguous` (capped sales and exclusion vs. netting cannot be read from the
data), and `promo_plan` also covers inclusive end dates and category lift.

**Status:** open — proposal: relabel `s4_sunday_closed` and `unit_change_i07` as a confirm kind and count them as
covered when NOTES.md states the right inference (or give them half weight). Keep `missing` for facts with no
trace in the data (holiday, floor, metric). This needs a framework notion of target kind in `clarify.py`.

**Rule seeds:** unchanged: `s4_sunday_closed` (every tier) and `unit_change_i07` (hard only) are still `missing`.
Still open.

**Ground truth audit:** resolved by removing both from the targets. The closure stays a rule
(`closed_day_zero`) and the unit change a data note the client confirms when asked; neither counts in Ask-F1.
What the data does not settle, that S4's Sundays and bread rolls still need their rows, is in
`submission_format`.

### F7 — No dated events or pressure (medium, confirmed)

Only hidden facts are present: no inbox, no dated notice, no stakeholder pushing for a distorted forecast. The
case cannot test re-planning on a dated change or resisting pressure; the generic engagement events are the only
dynamics.

**Status:** open — proposal: add an inbox e-mail dated 30 October that revises the promotion plan (one promotion
cancelled, one extended to 15 November, one discount raised), or a refit closure of S3 on 13–14 November, both
scored through the world truth. Add a pressure message (a store manager asking to pad every forecast 15% "so we
never run out"), which raises WAPE and which the client confirms is not policy. Add both as targets.

**Rule seeds:** partly. Hard now has a dated event scored through the world truth: on Friday 30 October, after
`promo_plan.csv` was exported, the promotions of the drawn category (beverages, dairy or bakery) were cancelled;
target `promo_revision`. The visible plan is stale for that category, so an agent that does not ask forecasts lifts
that will not happen (quality 0.86–0.98 at the case seed). The pressure message and a closure are not done. Still
open for pressure.

**Ground truth audit:** resolved for pressure. The data has an e-mail from the Central Plaza (S1) store manager
to the ordering desk: "Whatever numbers you get for November, please add 20% on top for Central Plaza." The client
says it is his wish, not policy (target `manager_note`, every tier); following it loses 0.15–0.47. A future
closure is not done.

### F8 — Calendar is Western and partly Spanish (medium, partly)

The "Spring Holiday" falls on Good Fridays (2025-04-18, 2026-04-03) and the autumn one on 12 October; Christmas
is in the zh and ja holiday lists, Lunar New Year and Chuseok are absent, and 11 November (Singles' Day in China,
Pepero Day in Korea) is called a city anniversary in zh and ko. Holiday uplift lands on the day itself (S1 I07:
207 on 24 Dec vs. 359 on 25 Dec). kg produce is recorded as integers and bananas are returned by the kg. No
document claims the world is country-neutral, and Christmas Day is not the record day (15 August 2026 is).

**Status:** open — proposal: use a fictional calendar with neutral fixed dates, put eve effects where a holiday
closes stores, and move the one-off holiday off 11/11 (e.g. Thu 12 Nov, which also suits a rule-set parameter).
Record kg items to 0.1 kg and log returns only for packaged items. All of this changes the visible data.

**Rule seeds:** partly. The one-off holiday's date is drawn (Mon 9, Wed 11 or Fri 13 November), so 11/11 is one of
three candidates; easy has no holiday in scope. The calendar file, the kg records and the zh/ko holiday names are
unchanged. Still open.

### F9 — Korean phrasing (low, partly)

Numbers and parameters match across all five locales. A few Korean phrases were calques or awkward: "6개 미만"
uses the piece counter for items sold by the kg, "CSV 파일 하나, `forecast.csv`이며" follows the English word
order, "빼 주세요 … 차감하지도 않습니다" mixes a request and a statement, and the store names 북역점 / 호숫가점 are
literal. The verifier notes 개 is the generic counter and 개청 기념일 is attested, so these are polish.

**Status:** fixed in this change — ko requirements and target: "6(판매단위 기준) 미만", "산출물은 CSV 파일
`forecast.csv` 하나이며, 헤더는 …", "차감하지도 마세요", "일회성 지역 공휴일인 시민의 날(시 승격 기념일)"; ko
store names 북부역점 (S3) and 호수공원점 (S5). The same request/statement mix in ja ("相殺もしません") now reads
"相殺もしないでください". A native reviewer should still sign off.

### F10 — Documentation details that mislead reviewers (low, confirmed)

The requirements said "one row per store, item and trading day" but then describe separate negative return rows
on the same key (1,286 such rows). The explainer labelled the deliverable spec "agent-visible" although only the
extractor sees it, and the case had no README with its reference and baseline numbers.

**Status:** fixed in this change — the data note now reads "one sales row per store, item and trading day, plus
separate return rows" in all five locales, and README.md gives the reference, baseline, oracle and ablation
numbers. The explainer label is generated by the framework and already reads "shown to the extractor … not to
the agent" at this commit.

**Baseline:** seasonal naive (same weekday of the last history week, S4 Sundays 0, floor of 6 on core items):
mean WAPE 0.2790 vs. the reference 0.1470 at the case seed (ratio 1.90); 0.2534 / 0.2521 / 0.2533 vs. 0.1474 /
0.1592 / 0.1417 on world seeds 1–3 (ratios 1.58–1.79).

## Rule seeds

The case moved from one fixed problem to the rule-seed contract (DESIGN.md, Settings): three tiers in case.yaml and
five parameters that a rule seed draws, each on its own, from a pool per tier. The data and `request.md` are
byte-identical in every setting and to the case before the conversion; the requirements, targets, rules and the
truth the forecast is scored against follow the tier and the drawn values.

- **Tiers.** Easy: the base forecast, scored against base till sales (net of returns, stockout days as recorded,
  without the promotion and holiday effects); the requirements say in the client's words that the category team
  adds the promotions and the holiday itself, that stockout correction comes in a later round and that bread rolls
  (I07) are not judged this round (their rows stay in the file). Medium adds the promotion plan (with the flyer's
  multiple where drawn) and the one-off holiday on its drawn date, still against till sales and without I07. Hard
  is scored against customer demand (stockout days censored, returns not demand), judges I07 (its unit change) and
  adds the dated cancellation of 30 October.
- **Parameters.** `min_display` (6, 4, 8: the display floor, rule `min_display_stock`), `holiday_date` (none in
  easy; 2026-11-11, 2026-11-13, 2026-11-09), `promo_uplift` (1 in easy; 1, 1.5, 2: the flyer's multiple of a past
  promotion's extra sales), `promo_cancelled` (none in easy and medium; beverages, dairy, bakery in hard) and
  `short_weight` (1, 2, 3: a unit forecast too low counts that many times a unit too high in the store's WAPE).
  Labels word the dates, multiples and categories in each locale. Public panel: rule seeds 3, 25 and 58, which show
  every candidate of every pool; seed 3 draws the binding check's start (hard/s3).
- **Truth.** `build_world` keeps the history and the plan exactly as before and then draws, per horizon cell, the
  day noise, a Poisson quantile, the stockout draw, the share sold on a stockout day and a return draw (common
  random numbers). `truth(world, rules)` turns them into the setting's actuals: demand (hard) or till sales net of
  returns (easy, medium) under that setting's mean (promotions with the flyer and the cancellation, the holiday on
  its date). Scoring stays the store-mean WAPE against that one realization, with the error weight.
- **Reference and baseline.** The reference keeps its weekday-level model, now with promotion lifts per category
  and discount and holiday lifts per category, fitted to till sales in easy and medium and to demand in hard, and
  forecasts the weight's quantile of its residual ratios before the floor. The baseline stays the seasonal naive
  forecast with the drawn floor. Baseline ÷ reference at the case seed: 1.64–1.98 (easy), 1.65–2.47 (medium),
  1.95–3.20 (hard).
- **Binding.** From hard/s3 every parameter changes the answer: the floor of 8 makes the reference invalid (and a
  floor of 4 lets the reference improve by 4.9%), another holiday date moves its objective by 28–33%, a flyer by
  3–11%, another cancelled category by 6–17%, another error weight by 45–91%. On world seeds 1–20 the strongest
  alternative of each parameter makes the reference invalid, or moves or beats it by at least 5%.
- **Targets.** 5 in easy (`base_forecast` is new), 7 in medium (`promo_flyer` new; the holiday target is now
  `one_off_holiday` with the drawn date), 11 in hard (`promo_revision` new; `stockout_censoring`, `returns` and
  `unit_change_i07` are hard only). `wape_metric` states the weight and what the actuals are per tier.
- **Explainer and translations.** `locales/<lang>/explainer.yaml` (zh, ko, ja, es) has the three tiers and the
  floor rule with `{{min_display}}`. docs/<lang>/README.md and docs/<lang>/REVIEW.md still describe the case without settings
  and are to be retranslated.
- No test hard-codes this case; `python -m pytest -q` passes unchanged.
- **Check of the conversion (fixed).** The plan's 14 promotions are a random sample of store × item pairs, and on
  some world seeds a category the cancellation can draw has none (no dairy promotion on world seed 6, no beverages
  on 8). A hard setting that draws that category then cancels nothing: the client's 30 October message is about
  promotions that do not exist, and the parameter changes nothing there (the validator's binding check still
  passes, since another category binds). `build_world` now makes sure every category of the `promo_cancelled`
  pool has a promotion in the plan: a plan that lacks one moves one promotion of its most promoted category (same
  store, dates and discount) to an item of the missing category, with its own random stream. The stored world and
  world seeds 1–5 already cover every category, so their data and answers are unchanged.

## Ground truth audit

The case owner's principles for forecasting cases (docs/DIRECTION.md, section 5) and the audit contract (DESIGN.md,
Ground truth audit) were applied together. `audit-case` now passes with no finding and no waiver; `audited: true`.

### What was wrong

- **The literal forecast was one exception away from a good score.** It broke only the display floor, a
  bendable rule; with the floor relaxed it scored 0.42–0.95 in every public setting, and with the floor kept
  (the "literal plus one rule" near miss) 0.42–0.86.
- **Open shortcuts.** The median forecast with every other fact right scored 0.74–1.00; the literal forecast with
  a blanket 20% on top 0.00–0.78.
- **A rule on a forecast.** The display floor made a forecast invalid for being low, although forecasting models
  differ and none is "the" answer.
- **One draw.** Quality was the weighted WAPE against one realized horizon, so skill and luck were mixed and the
  best achievable score was unknown (the true generator mean reached 1.07).
- **Facts that changed nothing.** Returns (under 0.002), bread rolls' unit change (0.001–0.009), stockout days
  (0.06–0.07, hard only); `wape_metric` bundled the error weight with what the actuals were.
- **A baseline that knew nothing.** Last week's sales repeated, so a competent model beat it by modelling alone
  and the client's facts carried little of the scale.

### What changed (scenario, in the client's terms)

| Change | Before | Now | Why |
|---|---|---|---|
| What is scored | a forecast, against one realized horizon (weighted WAPE) | an order plan, by its expected cost under the demand distribution: units left over + `lost_sale_cost` × units short, as a share of expected demand, exact | "we place our orders from these numbers": the stores order the number as it is. Expected loss has no luck and a known optimum |
| The loss | `short_weight` 1, 2 or 3, described under "how the forecast is judged" | `lost_sale_cost` 5, 12 or 30, a business cost stated in the background | the client's decision picks the loss; with a weight of 1 the plain forecast was the answer |
| The deliverable | `forecast` column | `order_qty` column (a `forecast` column alone is read as the order) | rules belong on the decision |
| Display floor | on the forecast; 4, 6 or 8 | on the order; 4, 6 or 12 | a forecast is never invalid for being low; at 12 the habit is costly enough to be worth bending |
| What demand is | till sales in easy and medium, demand in hard | demand in every tier | an order has to cover demand; "till sales" has no meaning for an order |
| The holiday | out of scope in easy | in every tier | without it easy had too few facts: a literal forecast with a lucky blanket cushion reached 0.58–0.70 |
| The flyer | 1, 1.5 or 2 | 1, 2 or 3 | 1.5 against 1 moved the plan by under 0.10 |
| Stockout rates in the history | 5–20% per item | 8–30%, one item per category well above the others | reading stockout days as sales now costs 0.09–0.30 and can be told from the plan |
| The store manager's e-mail | none | `mail/2026-10-28_central_plaza_orders.eml`, five locales | the pressure item of F7 |
| The client's own way | last week's sales of the same weekday | the store managers' habit: eight-week average without stockout days (four weeks in the audit's first version; see "Adversarial check"), a cushion of 10, 20 or 30% by cost ratio, 2% per discount point times the flyer, the holiday like a Saturday | the managers know their business; an engineer who ignores the client's facts must not beat them |

**The agent's view.** The request is unchanged. The data changed in two ways, the same in every setting:
`sales_history` was redrawn with the higher stockout rates (43,687 rows, 7,175 stockout rows; was 43,718 and
4,390), and `mail/` is new (its first sentence was reworded in the adversarial check, below). `promo_plan`,
`holidays`, `stores` and `items` are byte-identical to before.

**Targets** (12 → 11, one fact each): new `order_quantity`, `lost_sale_cost` (param) and `manager_note`;
`stockout_censoring` and `one_off_holiday` in every tier; `base_forecast` and `promo_plan` are the promotions'
scope only; `promo_flyer`, `one_off_holiday`, `promo_revision` and `min_display` carry `param:`. Removed and kept
as context: `returns`, `s4_sunday_closed`, `unit_change_i07`, `wape_metric`.

### What the audit shows (45 settings, public world)

Numbers as they stand after the adversarial check (next section), which changed the baseline's window, the
diagnostics and the shortcuts.

**Shortcuts**, all closed in every setting:

| Shortcut | Before the audit | Now | How closed |
|---|---|---|---|
| `literal_plus_floor` | 0.42–0.86 | 0.00 | the cost of a missed sale and the holiday: the literal covers half the days |
| `forecast_as_order` | 0.74–1.00 | 0.00 | `lost_sale_cost` is 5 or more in every setting |
| `blanket_cushion` | 0.00–0.78 | 0.00 | the holiday in every tier, the promotions' scope, stockout days |
| `copy_last_week` | 0.00 (it was the baseline) | 0.00 | — |
| `flat_average` | 0.19–0.43 | 0.00 | — |
| `never_run_out` | 0.00 | 0.00 | — |
| `display_only` | 0.00 | 0.00 | — |
| `judged_rows_only` | invalid | invalid | `complete_grid`: the mandatory output |
| `habit_last_year` (new in the check) | up to 0.59 against the four-week habit | at most 0.33 | the habit averages eight weeks |
| `habit_more_cushion` (new) | up to 0.24 | at most 0.16 | the same |
| `literal_sized_cushion` (new) | 0.00 | 0.00 | the holiday, the promotions' scope, stockout days |
| `weekday_quantile` (new) | 0.00 | 0.00 | the same |

- **The literal solution**: invalid as delivered in all 9 public settings (118–136 core orders under the minimum);
  with the bendable rule relaxed, quality 0.00 in all 9 (cost 0.61–3.62 against the habit's 0.35–0.54).
- **Facts**: all 11 bite in every tier where they are in force (README, Ground truth audit; GT.md, part 1).
- **Value of asking**: 0.90 / 0.82 / 0.86 in easy / medium / hard. `robust_solution` is granted two facts it could
  not know (the number is ordered as it is; the e-mail is not followed).
- **Reference and bounds**: the optimum is proven and attained; `quality_cap` 1.05.
- **Diagnostics**: one per target, read from the plan; they separate the reference from every biting ablation,
  with no false "not enforced" on the best plan and no cross flag, on the public world and on world seeds 1–10.
- **Round 2026-11** (rule seeds 108807, 519122, 904685, all nine settings): reference and baseline valid, scale
  25% to 59% wide, literal invalid as delivered and 0.00 with the bendable rule relaxed, and every fact bites in
  at least one of the three seeds in every tier (`min_display` in one or two of three, every other fact in all
  three).

### Adversarial check

A second engineer checked the audit by running code against it. What held, what did not, and what changed.

**Held.**

- **The score is exact.** The expected cost of six plans (reference, baseline, literal, best plan, the reference
  jittered by ±15%, a flat 40 units) in easy/s3, medium/s58 and hard/s25 was recomputed with independent code: the
  cell means re-derived from the world's constants, the day noise integrated on a 4,001-point grid, and a Monte
  Carlo of 200,000 draws per cell with the generator's own recipe. `score()` agrees with the quadrature to
  1.4 × 10⁻⁵ or better (the 16 Gauss-Hermite nodes) and with the Monte Carlo within 1.2 standard errors in all 18
  comparisons. The 35,257 history rows without a stockout have mean −0.01 and standard deviation 1.00 when
  standardized by the scoring law, so the law that scores is the law the data was drawn from.
- **The bound is the optimum.** Per cell, no order on a 0.25 grid costs less than the bound's (45 settings, the
  scorer's cost and an independent one on sampled cells), and 900 random valid perturbations of the best plan all
  cost more.
- **The agent's view** is byte-identical over 78 settings (public, round and 20 other rule seeds) in each of the
  five locales; the five locales' data hold the same numbers, dates and ids; and the data is built before any
  setting is drawn, so no file can show a drawn value. The days the holiday can fall on look like any other in
  past years.
- **The never-asks solver is a genuine attempt.** Without the first grant (it hands in the expected demand) it
  earns 0.00 in every tier; without the second (it follows the e-mail) 0.03 / 0.08 / 0.07 (0.19 / 0.24 / 0.26 on
  the first baseline). Other compromise ratios, display minimums and holiday hedges were tried: over all 27 / 81 /
  243 combinations of a tier's candidates the best of them (a ratio of 20 instead of 14) earns 0.113 / 0.181 /
  0.117 against its 0.099 / 0.167 / 0.099, and a planner that scores every candidate plan against its own model,
  by the ratio of the best cost to the plan's cost over all combinations, picks the solver's own ratio and
  minimum. A plan found with hindsight (the true demand and the true scale of every combination) earned 0.01 to
  0.04 more on the first baseline. It was left as it is.
- **The literal solution is not bent to fail.** Following the e-mail helps it (Central Plaza gets a cushion);
  without the e-mail, with stockout days left out, with bread rolls in packs or rounded to whole units it is
  invalid as delivered and 0.00 with the rule relaxed in all 54 settings tried. Its `forecast` header is read as
  the order.
- **The locales** agree on every placeholder, marker, code, date and number of two digits or more, line by line;
  the differences are single digits one language writes as words.

**Did not hold, and what changed.**

| Finding | Evidence | Change |
|---|---|---|
| The baseline's four-week window made the zero a matter of luck and left a shortcut open | Averaging two to four days per weekday, the habit lost 0.21–0.45 of the scale to the same habit over eight weeks; over 52 weeks it scored up to 0.59 (above 0.5 in 18 of 54 settings), a copy of the client's own way with one number changed. On world seeds 1 and 2 the same shortcut reached 0.49 and 0.41: the public draw was an unlucky one for the habit, and its scale (up to 120% wide) was the widest | The habit averages eight weeks (requirements, five locales). Scale 25–72% wide (21–103% on world seeds 1–10); the same shortcut at most 0.33 (0.44, 0.36, 0.33 on world seeds 1–3). New shortcuts `habit_last_year`, `habit_more_cushion` |
| The cushions were said to be the flat cushions that serve the habit best | With four weeks the best flat cushions were 15, 25 and 35% on average (10–15, 20–35, 35–50 by setting); 10, 20 and 30% left 0.00–0.28 of the scale to a larger cushion | With eight weeks 10, 20 and 30% cost the habit 0.000, 0.000 and 0.001 more than the cheapest flat cushion at a ratio of 5, 12 and 30 (objective units, pooled over the public world and world seeds 1 and 2), so the statement is now true. A fixed 20% for every ratio would be worse still: quality −0.26 to +0.08 at a ratio of 5 and −0.63 to −0.38 at 30 on the first scale, so following the ratio narrows the scale, not widens it |
| A file named `forecast.csv` with any header but `order_qty` or `forecast` was fatal | The request names no format and the prompt says to infer one; `forecast_units`, or the client's own `점포코드`, could not be read | The quantity is read from `order_qty`, else `forecast`, else the one other column of numbers; key columns may carry the data's names in any locale. `submission_format` no longer names the header: its fact is the rows the ordering system needs |
| Diagnostics off the public world: 15 cross flags on world seeds 1–5, all on seeds 3 and 4 (3 more on seed 6 once seeds 6–10 were run) | A plan that reads stockout days as sales, or holds a slow item at a higher minimum, understates a promotion's lift (0.37–0.48 of it, 0.06 for aged cheese) and was called "dropped the wrong category"; a plan that hands in expected demand carries more promotion lift than a cushioned one and was read as a larger flyer | `promo_revision`: "no lift" is under a quarter of the historical one, not told for a plan without promotions; promotions of slow core items are not read; the lift yardstick of a plan without a cushion is expected demand. World seeds 1–10: reference 0 / 4,050 false calls, best plan 0 / 4,050, biting ablation deliverables missed 0 / 5,660, cross flags 0 |
| The cost-ratio check called a correct plan from a cruder model a misreading | An independent forecaster sized for the client's ratio sat at 0.32 of the way from another candidate to the client's (threshold one third) on world seed 5 | The threshold is a quarter (the reference sized for another candidate sits at −0.18 to 0.22 where it bites) |
| Misreadings the ablations never tried were missed | The flyer's multiple applied to the whole day's demand read as "nearest to 3"; the holiday ordered like a Saturday on a Friday sat at 0.51 of the lift; one lift for every category at 0.90 | `promo_flyer` rejects a lift past the largest multiple by more than half a step; `one_off_holiday` also asks for half of bakery's and of beverages' own lift, the categories the client names |
| The e-mail said "we ran out of several lines again last Saturday" | On Saturday 24 October Central Plaza ran out of one line on the public world and of none on world seed 3 | "We keep running out of one line or another on Saturdays" (five locales; the agent's view changes by that sentence, the same in every setting) |

**Probes of the diagnostics** (the nine public settings on the public world and world seeds 1–5, 54 settings).

- *Correct plans built another way*: an independent cruder forecaster (plain weekday means of eight weeks, a
  straight-line promotion lift), a normal approximation with decimals, each store's level off by 2–5%, no
  seasonal carry, the best plan plus or minus one unit everywhere. 324 plans, 2,916 target checks, no false
  "not enforced" (before the changes: 1).
- *Plans with every fact right whose cushion is the neighbouring ratio's*: one flat percentage for every product
  (z × 15%) at a ratio of 30 covers 93–95% of days where the best plan covers 97%, and the reference's model with
  twice its day noise at a ratio of 12 covers 97% where the best plan covers 93%. The cost-ratio check calls 29
  of these 108 plans not enforced; the 108 lose 0.04–0.45 of the scale. The check reads the cushion a plan ends up
  with, not the ratio its author had in mind, and cannot tell these from a misread ratio.
- *New misreadings* (13 kinds, among them a 95% service level whatever the ratio, the ratio inverted, the
  holiday like a Saturday, one holiday lift for every category, the flyer on the whole day's demand, the note
  followed on Fridays and Saturdays only, stockout days at half weight or scaled back by one flat factor, the
  whole plan read as cancelled): 328 of the 462 that bite are called not enforced on their own target (71%;
  245 of 436, 56%, before the changes). Missed by design: a flat 20% at a ratio of 5 (between two candidates),
  stockout days at half weight (under half the pattern), the note's 20% given to every store (Central Plaza
  is not above the others; the cost-ratio check flags it instead), and the whole plan cancelled (told by
  `promo_plan`; `promo_revision` says it cannot tell).

**Reported, not changed.**

- `min_display` bites in 31 of 45 settings (25 before): a guess above the client's minimum is cheap unless the
  guess is 12. An agent that does not know there is a minimum is invalid everywhere.
- `quality_cap` 1.05 is the public world's median best plan, rounded up; on world seeds 1–10 that median is
  1.033–1.062.
- The scale reaches 103% on world seed 7 (a missed sale of 30, the holiday on a Friday, a flyer of 3).

### Still open

- **Stockouts are independent of the day's demand**, so leaving flagged days out is unbiased (F5). The history's
  stockout rates (10% to 31% by item) are also the same whatever cushion the client says the managers add.
- **One cost ratio for every product.** Fresh produce that is thrown away and water that keeps do not cost the
  same when left over. With per-category costs a flat cushion would fail; today a flat cushion of the right size
  on an otherwise right forecast reaches 0.69–0.96.
- **The managers' cushion follows the cost ratio** (`habit_cushion`) and the requirements quote it, so a client
  asked how the stores order today hints at the cushion's size.
- **Bending never pays for a plan at the cap** (F4).
- **The cost-ratio diagnostic reads the cushion, not the ratio**: a plan sized for the right ratio with one flat
  percentage, or with twice the day noise, is called not enforced where it lands on the neighbouring candidate.
- **The complete grid is a hard gate**: a plan that leaves out S4's Sunday rows is invalid, although the order
  there would be 0. The request asks for every store and every day, and the client says the ordering system needs
  the rows; it stays as it was before the audit.
- **Native review** of the rewritten texts in zh, ko, ja and es (requirements, targets, summaries, explainer
  texts, the e-mail), and every verdict in CLIENT_REVIEW.md. docs/<lang>/README.md and REVIEW.md in those four
  languages still describe the case before the audit.
- **`leaderboard/anchors-2026-11.json`** holds this case's anchor rows and fingerprint from before the audit; it
  is outside the case directory and has to be regenerated (`fdebench2 anchors`).
- F8 (the calendar) is unchanged.
