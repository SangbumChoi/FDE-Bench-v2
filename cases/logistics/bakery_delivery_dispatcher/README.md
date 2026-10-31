# Bakery Delivery Dispatcher — `logistics/bakery_delivery_dispatcher`

A bakery's central kitchen delivers bread trays to its cafés every morning with four vans. The client asks the
agent to plan tomorrow's (Monday) routes "so the cafés get their trays in time and the drivers aren't out longer
than they need to be". The deliverable is `routes.json`: for each van used, a departure time (`HH:MM`, 05:00 if
left out) and the cafés in visiting order. The evaluator drives the plan through the setting's travel model and
scores it against the reference.

The case has **settings**: three tiers × rule seeds (DESIGN.md, Settings). The data and the request are the same
in every setting; only the client's hidden rules, and so the right plan, change. The engagement knobs (full spec
vs. clarify first, client persona, data noise, events) apply on top, as for every case (see
[cases/README.md](../../README.md)). It is also the framework's test fixture (`tests/conftest.py`,
`tests/test_validator.py`), so its validation has to stay fast.

## Tiers

| Tier | Rules in force | Out of scope (said in the client's words) |
|---|---|---|
| **easy** | The routing core: this week's tray limit per van, the drivers' shift (out from 05:00, back by the shift end), one visit per café, the café closed this week, a constant 25 km/h, the lateness cost | The partner cold chain ("this week the partner brings its chilled range itself … any van may serve them"), the premium-first habit ("suspended this week"), the rush hour ("Monday is a school holiday"), V2's brake check ("booked for Tuesday") |
| **medium** | Easy + the partner cold chain (partner-brand cafés by the refrigerated V4 only) + the premium-first habit when the rule seed draws it | The rush hour and V2's brake check, as in easy |
| **hard** | Medium + the morning rush (30 km/h before `rush_start`, 20 km/h from it, also on a leg already under way), a dated event (V2 is in the workshop until 06:40 on Monday) and pressure from the East Lake café (C07) manager, who insists on being the first stop before 06:30 (not a rule) | — |

## Parameters (what a rule seed draws)

Each parameter is drawn on its own from its pool in the setting's tier (`case.yaml` `params:`).

| Parameter | easy | medium | hard | What it changes |
|---|---|---|---|---|
| `closed_cafe` | C11, C03, C14 | same | same | Which café must not be served (South Hill / North Station / Maple Row café, named as in the data in every locale); every other café must be |
| `late_cost` | 3, 2, 5 | same | same | Minutes of van time one late minute costs: the objective's lateness weight |
| `shift_end` | 09:30, 09:00, 10:00 | same | same | When every van must be back at the kitchen |
| `van_capacity` | 100, 110, 120 | same | 110 | This week's trays per van (`max_trays` in the data is 120; the new crates take room). Fixed in hard, so its candidates are compared in medium |
| `rush_start` | none | none | 07:00, 06:30, 07:30 | When vans slow from 30 to 20 km/h (easy and medium: 25 km/h all morning) |
| `premium_first` | false | true, false | true, false | Whether the premium-first habit holds this week |

The vans, the 05:00 start, road distance (1.3 × straight line), unloading (4 + 0.2 per tray min), V2's workshop
until 06:40 (hard) and the pressure café (C07) are fixed. `case.py` derives nothing and needs no `admissible()`:
every combination is feasible in every world `build_world` accepts (below).

## Public panel (rule seeds 5, 13, 58) at the case seed 20261025

Seed 5 draws each tier's **headline**: the latest shift end and the largest tray limit, with the first candidate of
every other pool (`case.py` `_headline`); the validator's binding check starts from it.

| Setting | Drawn parameters | Reference | Baseline | Baseline / reference |
|---|---|---|---|---|
| easy/s5 | C11, late 3, 10:00, 120 trays, no rush, habit off | 435.73 | 1,669.60 | 3.83 |
| easy/s13 | C14, late 5, 09:00, 100 trays, no rush, habit off | 449.79 | 1,285.12 | 2.86 |
| easy/s58 | C03, late 2, 09:30, 110 trays, no rush, habit off | 420.30 | 1,189.64 | 2.83 |
| medium/s5 | C11, late 3, 10:00, 120 trays, no rush, **habit on** | 626.50 | 1,977.71 | 3.16 |
| medium/s13 | C14, late 5, 09:00, 100 trays, no rush, habit off | 463.34 | 1,273.22 | 2.75 |
| medium/s58 | C03, late 2, 09:30, 110 trays, no rush, habit off | 440.61 | 1,141.36 | 2.59 |
| hard/s5 | C11, late 3, 10:00, 110 trays, rush 07:00, **habit on** | 709.27 | 1,870.28 | 2.64 |
| hard/s13 | C14, late 5, 09:00, 110 trays, rush 07:30, habit off | 472.58 | 1,269.31 | 2.69 |
| hard/s58 | C03, late 2, 09:30, 110 trays, rush 06:30, habit off | 537.35 | 1,177.53 | 2.19 |

The dicts as stored in `dataset/gt/<tier>_s<seed>/setting.json` (`rush_start` and `premium_first` as drawn):

```
easy/s5    {closed_cafe: C11, late_cost: 3, shift_end: "10:00", van_capacity: 120, rush_start: none, premium_first: false}
easy/s13   {closed_cafe: C14, late_cost: 5, shift_end: "09:00", van_capacity: 100, rush_start: none, premium_first: false}
easy/s58   {closed_cafe: C03, late_cost: 2, shift_end: "09:30", van_capacity: 110, rush_start: none, premium_first: false}
medium/s5  {closed_cafe: C11, late_cost: 3, shift_end: "10:00", van_capacity: 120, rush_start: none, premium_first: true}
medium/s13 {closed_cafe: C14, late_cost: 5, shift_end: "09:00", van_capacity: 100, rush_start: none, premium_first: false}
medium/s58 {closed_cafe: C03, late_cost: 2, shift_end: "09:30", van_capacity: 110, rush_start: none, premium_first: false}
hard/s5    {closed_cafe: C11, late_cost: 3, shift_end: "10:00", van_capacity: 110, rush_start: "07:00", premium_first: true}
hard/s13   {closed_cafe: C14, late_cost: 5, shift_end: "09:00", van_capacity: 110, rush_start: "07:30", premium_first: false}
hard/s58   {closed_cafe: C03, late_cost: 2, shift_end: "09:30", van_capacity: 110, rush_start: "06:30", premium_first: false}
```

Every candidate of every pool appears in the panel. Every parameter binds (validator, world seeds 1–20 too):
- `closed_cafe`: the hard/s5 reference serves C03 and C14, so it is invalid under either.
- `late_cost`: the hard/s5 reference is 56 minutes late in all; its objective moves by 7.9% (weight 2) and
  15.8% (weight 5).
- `shift_end`: a hard/s5 van is back at 09:03, so the reference is invalid under 09:00.
- `van_capacity` (compared in medium): a medium/s5 van carries 103 trays, invalid under 100.
- `rush_start`: the hard/s5 reference's objective moves by +14.0% under 06:30 and −10.6% under 07:30.
- `premium_first`: without the habit the reference is 27.5% cheaper in hard/s5 (514.28 against 709.27) and
  28.4% in medium/s5 (448.70 against 626.50).

## What an agent must ask

The clarification targets, by tier (`locales/<lang>/targets.yaml`):

- **Every tier:** road distance (1.3 ×), service time, the shift end, the closed café (which one), one visit per
  café, the premium-first habit (on, or suspended this week), the lateness cost (its weight), and the tray limit
  when it is below the racks' 120 (`tray_limit`, drawn 100 or 110; hard always 110).
- **easy and medium:** the constant 25 km/h (`speed`).
- **easy:** that any van may serve the partner cafés this week (`partner_this_week`).
- **medium and hard:** the cold chain (partner cafés by V4 only).
- **hard:** the rush hour and its start (`rush_hour`), V2 in the workshop until 06:40 (`workshop`) and that the C07
  manager's demand is not a rule (`manager_pressure`).

So 9 or 10 targets in easy and medium, 12 in hard.

## Data

`cafes` (18 cafés C01–C18: `x_km` / `y_km` relative to the kitchen at (0, 0), `trays` 8–30, `tier`
premium/standard, `opens`, `deliver_by` 30, 45 or 60 minutes after opening, `partner_brand`) and `vans` (V1–V4,
`max_trays` 120, only V4 refrigerated). File names, headers and labels are localized (`매장목록.csv` with
`매장등급 = 프리미엄`, `cafeterias.csv` with `categoria = premium`); IDs and numbers are not, and a café's name
follows its ID (C11 is always South Hill café). The closed café is an ordinary row: only the client knows it is
closed.

At the case seed the 18 cafés order 332 trays (309 to 318 with the closed café out, against 400 to 480 trays of
fleet capacity). The partner cafés are Harbour café (C05, standard), Clock Tower café (C10, premium) and Stadium
café (C16, premium); the other premium cafés are C01, C04, C07 and C13. C07 opens at 07:00 (deliver by 08:00), so
the manager's "before 06:30" would mean a van waiting half an hour at her door.

**Which worlds are used.** `build_world` keeps drawing from the seed's stream until a world is usable for every
setting a rule seed can draw (public or private):
1. For each tier, the reference solver serves all 18 cafés under the tier's strictest combination (100 trays,
   back by 09:00, in hard the 06:30 rush and V2 from 06:40, the habit and the cold chain where the tier has them).
   That plan is the tier's fallback: with the closed café dropped it keeps every setting's rules (a later shift
   end, more trays, a later rush, no habit and one stop fewer never bring a van back later), so every setting has
   a valid plan.
2. The parameters can change the answer: under each tier's headline, the reference brings a van back after the
   earliest shift end (hard), loads one above the smallest tray limit (medium), is late for at least 1% of its
   objective, and costs at least 1% more than without the premium-first habit (hard).
3. Every rule has a plan that breaks only it in hard with 110 trays and the 09:00 shift end.

About 9% of draws pass; a world takes 0.8 s on average to build (at most 3.3 s on world seeds 1–30).

## Rules

| Rule | Class | Tiers | Meaning |
|---|---|---|---|
| `van_capacity` | physical | all | A van carries at most `van_capacity` trays this week. |
| `shift_window` | physical | all | Vans leave at 05:00 or later and are back at the kitchen by `shift_end`. |
| `van_ready` | physical | hard | V2 leaves no earlier than 06:40 (in the workshop on Monday). |
| `closed_cafe` | physical | all | No delivery to `closed_cafe`. |
| `serve_each_once` | contractual | all | Every open café is served exactly once. |
| `cold_chain` | contractual | medium, hard | Partner-brand cafés are served only by the refrigerated van. |
| `premium_first` | business policy | medium, hard, when `premium_first` | On every route, premium cafés come before standard cafés (may bend through the exception process under policies that make business policy soft). |

**Quality (lower is better):** the total time all vans are out, from departure to return (waiting at cafés that
are not open yet included), plus `late_cost` × every minute a café is reached after its `deliver_by`.

## Situations present

- **Hidden facts:** which café is closed; this week's tray limit below `max_trays`; the shift end; the lateness
  weight; whether the premium-first habit holds; in hard, when the rush starts.
- **Data semantics:** `partner_brand = yes` means chilled goods, so the refrigerated van only (medium, hard), but
  not this week in easy.
- **Habit that may bend:** premium first, where drawn. It costs 27–28% of the objective at the headline settings,
  so bending it through the exception process pays where business policy is soft (REVIEW.md, F3).
- **Dated event (hard):** V2 in the workshop until 06:40 on Monday.
- **Pressure (hard):** the C07 manager's demand to be the first stop before 06:30. The client says it is not a
  rule; following it means waiting at a café that opens at 07:00 (case seed) and reshuffling a route.
- **Trade-off:** leaving later avoids waiting at cafés that are not open yet, but in hard legs after the rush
  start are slower, and late arrivals cost `late_cost` times as much as van time.

## Reference and baseline

The **reference** (`_plan`) builds the routes by cheapest feasible insertion (partner cafés first when the cold
chain applies, then by tier, biggest first), retrying with V4 seeded by each workable order of the partner cafés
and then with shuffled insertion orders when the greedy construction corners itself; it also starts from the
tier's fallback without the closed café. Each start is improved by relocating single stops, the cheaper one by 300
rounds of ruin and recreate (2–4 neighbouring or random cafés taken out and put back by cheapest insertion), and
each route gets its best departure on a 5-minute grid. It is computed once per world and rule values.

The **baseline** (`baseline_solution`) is the dispatcher's own plan without an engineer: when the cold chain
applies, V4 takes the partner cafés (premium first, in the order that brings it back soonest); the other cafés are
taken in bearing order round the kitchen, starting due west, and loaded onto V1, V2, V3 and then V4 until the next
one no longer fits (this week's tray limit, back by the shift end); each van serves its premium cafés first and
then the rest in order of opening; every van leaves at 05:00 (in hard V2 at 06:40), when the shift starts, and
`deliver_by` is ignored. If a café is left over, the sweep starts from the next café round; if no start works, the
tier's fallback routes are driven with every van leaving as early as it may (always valid; not needed so far).

The case-seed routes of the headline settings:

| Setting | Plan | Objective |
|---|---|---|
| medium/s5 reference | V1 05:50 C01 C07 C09 · V2 06:05 C08 C12 C15 C02 · V3 06:05 C13 C14 C17 C03 C18 C06 · V4 06:00 C10 C04 C16 C05 | 626.50 (557.97 route min, 22.84 late) |
| medium/s5 baseline | V1 C01 C03 C09 C17 C06 C18 · V2 C13 C04 C07 C14 C12 C15 C02 · V3 C08 · V4 C10 C16 C05, all at 05:00 | 1,977.71 (859.59, 372.71 late) |
| hard/s5 reference | V1 06:10 C04 C12 C15 C02 · V2 06:40 C08 C03 C18 C06 · V3 06:10 C13 C14 C09 C17 · V4 05:50 C10 C01 C07 C16 C05 | 709.27 (541.10, 56.06 late) |
| hard/s5 baseline | V1 C01 C03 C09 C17 C06 C18 · V2 06:40 C13 C07 C14 C15 C02 · V3 C04 C08 C12 · V4 C10 C16 C05, the others at 05:00 | 1,870.28 (841.89, 342.80 late) |

Most of the baseline's extra cost is waiting (vans at cafés before they open) and lateness at the cafés it reaches
last.

Reference objectives on the validator's other world seeds:

| World seed | easy s5 / s13 / s58 | medium s5 / s13 / s58 | hard s5 / s13 / s58 |
|---|---|---|---|
| 1 | 469.31 / 510.62 / 468.93 | 632.60 / 557.98 / 470.66 | 671.59 / 537.13 / 540.77 |
| 2 | 448.89 / 418.55 / 452.80 | 805.19 / 452.96 / 473.96 | 1,104.65 / 431.50 / 544.96 |
| 3 | 492.71 / 496.33 / 499.92 | 634.03 / 607.11 / 601.92 | 751.63 / 597.80 / 708.56 |

Over the case seed and world seeds 1–30, in every tier and in rule seeds 5, 13, 58 and the private 101–105 (744
settings), the reference is valid, the baseline is valid and costs 1.17 to 9.76 times the reference (median 3.04),
and every rule in force has a plan that breaks only it. `validate-case --world-seeds 1,...,20` passes.

## Notes

- Synthetic. The positions, tray counts, opening times, speeds, service time and the lateness weights are
  invented. In hard the speed changes at `rush_start` also on a leg already under way (the time a leg takes is
  never shorter when it starts later).
- Headroom above the reference has not been measured again since the rule seeds (REVIEW.md, F2).
- `validate-case` checks every public setting: the reference at quality 1.0, the baseline valid and worse, one
  deliverable per rule in force that breaks only that rule, deterministic data in five locales, every parameter
  binding, the same agent view in every setting, and world seeds 1, 2 and 3.
