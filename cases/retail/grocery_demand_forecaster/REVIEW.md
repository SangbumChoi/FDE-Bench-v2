# Review — `retail/grocery_demand_forecaster`

Findings of the case review, each with the verifier's verdict and its status after this change. Quality numbers
below use the new scale (seasonal-naive baseline 0, reference 1) unless they are marked as ratios.

### F1 — No settings: one fixed problem at every difficulty (high, partly)

`case.yaml` declares no tiers, rule sets or `param_labels`; the only ground truth is `gt/default`. So the
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
  floor rule with `{{min_display}}`. README.<lang>.md and REVIEW.<lang>.md still describe the case without settings
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
