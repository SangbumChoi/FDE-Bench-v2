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

### F3 — Display floor stated as 2 in `case.yaml`, 6 everywhere else (high, confirmed)

`case.yaml` described `min_display_stock` as "never forecast below 2 units", while `MIN_DISPLAY = 6.0` in
`case.py`, all five requirements and the target say 6. The exception classifier sees the `case.yaml` text next
to the requirements, so the client was shown both numbers at the one moment the bendable rule matters, and the
explainer printed both. A floor of 2 would not bind (reference 0.13948 vs. 0.13947 without a floor). The
validator's number lint missed it because "2" appears in the requirements as a date ("Monday 2 November").

**Status:** fixed in this change — the rule description now says 6, matching `MIN_DISPLAY`, the requirements and
the target. No `{{min_display}}` placeholder: the case has no rule sets to fill it from.

### F4 — Bending the display floor never pays (medium, confirmed)

The floor binds on 136 reference cells (basil I03 and aged cheese I06, 1.3% of horizon demand). Dropping it gives
WAPE 0.1395, quality 1.057 (1.084–1.089 on seeds 1–3). At a quality weight of 0.6 and cap 1.5 that is worth
about 0.6 × 0.057 / 1.5 ≈ 0.023 of composite, below both soft-rule penalties (0.05 startup, 0.10 enterprise). WAPE
against true demand gives no credit for shelf presence, so "never bend" is always the right answer.

**Status:** open — proposal: make bending a real trade-off. Either price shelf presence in the objective (a cost
for open-day core forecasts below the floor on days the item sells, or score order quantities that include the
floor), or make the floor bind on more items and calibrate it so bending gains more than the startup penalty but
less than the enterprise one. Document the expected bend / no-bend answer per policy in the README.

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

### F6 — Targets that the data already settles count fully in Ask-F1 (medium, partly)

`s4_sunday_closed` (S4 has no Sunday rows) and `unit_change_i07` (items list "pack of 6", the history drops about
6× on 1 June 2026) are labelled `missing`, and Ask-F1 recall counts all nine targets equally, while the agent is
told to ask only about what the data does not settle. The verifier rejects the reviewer's 4/9 figure: stockout
censoring and returns are correctly `ambiguous` (capped sales and exclusion vs. netting cannot be read from the
data), and `promo_plan` also covers inclusive end dates and category lift.

**Status:** open — proposal: relabel `s4_sunday_closed` and `unit_change_i07` as a confirm kind and count them as
covered when NOTES.md states the right inference (or give them half weight). Keep `missing` for facts with no
trace in the data (holiday, floor, metric). This needs a framework notion of target kind in `clarify.py`.

### F7 — No dated events or pressure (medium, confirmed)

Only hidden facts are present: no inbox, no dated notice, no stakeholder pushing for a distorted forecast. The
case cannot test re-planning on a dated change or resisting pressure; the generic engagement events are the only
dynamics.

**Status:** open — proposal: add an inbox e-mail dated 30 October that revises the promotion plan (one promotion
cancelled, one extended to 15 November, one discount raised), or a refit closure of S3 on 13–14 November, both
scored through the world truth. Add a pressure message (a store manager asking to pad every forecast 15% "so we
never run out"), which raises WAPE and which the client confirms is not policy. Add both as targets.

### F8 — Calendar is Western and partly Spanish (medium, partly)

The "Spring Holiday" falls on Good Fridays (2025-04-18, 2026-04-03) and the autumn one on 12 October; Christmas
is in the zh and ja holiday lists, Lunar New Year and Chuseok are absent, and 11 November (Singles' Day in China,
Pepero Day in Korea) is called a city anniversary in zh and ko. Holiday uplift lands on the day itself (S1 I07:
207 on 24 Dec vs. 359 on 25 Dec). kg produce is recorded as integers and bananas are returned by the kg. No
document claims the world is country-neutral, and Christmas Day is not the record day (15 August 2026 is).

**Status:** open — proposal: use a fictional calendar with neutral fixed dates, put eve effects where a holiday
closes stores, and move the one-off holiday off 11/11 (e.g. Thu 12 Nov, which also suits a rule-set parameter).
Record kg items to 0.1 kg and log returns only for packaged items. All of this changes the visible data.

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
