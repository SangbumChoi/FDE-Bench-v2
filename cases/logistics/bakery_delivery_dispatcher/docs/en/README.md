# Bakery Delivery Dispatcher — `logistics/bakery_delivery_dispatcher`

A bakery's central kitchen delivers bread trays to its cafés every morning with four vans. The client asks the
agent to plan tomorrow's (Monday) routes "so the cafés get their trays in time and the drivers aren't out longer
than they need to be". The deliverable is `routes.json`: for each van used, a departure time (`HH:MM`, 05:00 if
left out) and the cafés in visiting order. The evaluator drives the plan through the client's travel times and
scores it between the dispatcher's own hand plan (0) and the reference (1).

The case has **settings**: three tiers × rule seeds (DESIGN.md, Settings). The data and the request are the same
in every setting; only the client's hidden rules, and so the right plan, change. The engagement knobs (full spec
vs. clarify first, client persona, data noise, events) apply on top, as for every case (see
[cases/README.md](../../../../README.md)). It is also the framework's test fixture (`tests/conftest.py`,
`tests/test_validator.py`), so its validation has to stay fast. It is audited (`audited: true`): see "Ground truth
audit" below, [GT.md](../../GT.md) and [CLIENT_REVIEW.md](../../CLIENT_REVIEW.md).

## Tiers

| Tier | Rules in force | Out of scope (said in the client's words) |
|---|---|---|
| **easy** | The routing core: this week's tray limit per van, the café closed this week, the travel times (road distance, a constant 25 km/h, unloading), the cost of a late minute, every café served once, the vans back by 10:00 | The partner cold chain ("this week the partner brings its chilled range itself … any van may serve them"), the premium-first habit ("suspended this week"), the rush hour ("Monday is a school holiday"), V2's brake check ("booked for Tuesday") |
| **medium** | Easy + the partner cold chain (partner-brand cafés by the refrigerated V4 only) + the premium-first habit when the rule seed draws it | The rush hour and V2's brake check, as in easy |
| **hard** | Medium with the tray limit at 110 + the morning rush (30 km/h before `rush_start`, 20 km/h from it, also on a leg already under way), a drawn end of the shift (09:00, 09:30 or 10:00), a dated event (V2 is in the workshop until 06:40 on Monday) and pressure from the East Lake café (C07) manager, who insists on being the first stop before 06:30 (not a rule) | — |

## Parameters (what a rule seed draws)

Each parameter is drawn on its own from its pool in the setting's tier (`case.yaml` `params:`).

| Parameter | easy | medium | hard | What it changes |
|---|---|---|---|---|
| `closed_cafe` | C11, C03, C14 | same | same | Which café must not be served (South Hill / North Station / Maple Row café, named as in the data in every locale) |
| `shift_end` | 10:00 | 10:00 | 09:30, 09:00, 10:00 | When every van must be back. Drawn in hard only: in easy and medium no plan worth handing in comes back after 09:00 |
| `van_capacity` | 100, 110, 120 | same | 110 | This week's trays per van (`max_trays` in the data is 120; the new crates take room) |
| `rush_start` | none | none | 07:00, 06:30, 07:30 | When vans slow from 30 to 20 km/h (easy and medium: 25 km/h all morning) |
| `premium_first` | false | true, false | true, false | Whether the premium-first habit holds this week |

Fixed in every setting: the vans, the 05:00 start, road distance (1.3 × straight line), unloading (4 + 0.2 per tray
min), the cost of a late minute (3 van minutes), V2's workshop until 06:40 (hard) and the pressure café (C07).
`case.py` derives nothing and needs no `admissible()`: every combination is feasible in every world `build_world`
accepts (below). The first version also drew the lateness cost (2, 3 or 5) and the shift end in every tier; neither
changed a reference in easy (the validator's open binding findings), so the lateness cost is now fixed and the
shift end is drawn in hard only.

## Public panel (rule seeds 5, 13, 58) at the case seed 20261025

Seed 5 draws each tier's **headline**: the latest shift end and the largest tray limit, with the first candidate of
every other pool (`case.py` `_headline`); the validator's binding check starts from it.

| Setting | Drawn parameters | Reference | Baseline (dispatcher) | Scale width |
|---|---|---|---|---|
| easy/s5 | C11, 10:00, 120 trays | 451.85 | 534.94 | 18.4% |
| easy/s13 | C14, 10:00, 100 trays | 446.95 | 516.36 | 15.5% |
| easy/s58 | C03, 10:00, 110 trays | 459.96 | 548.78 | 19.3% |
| medium/s5 | C11, 10:00, 120 trays, **habit on** | 491.17 | 590.45 | 20.2% |
| medium/s13 | C14, 10:00, 100 trays, habit off | 475.91 | 537.05 | 12.8% |
| medium/s58 | C03, 10:00, 110 trays, habit off | 483.63 | 555.25 | 14.8% |
| hard/s5 | C11, 10:00, rush 07:00, **habit on** | 508.01 | 619.04 | 21.9% |
| hard/s13 | C14, 09:00, rush 07:30, habit off | 453.30 | 533.79 | 17.8% |
| hard/s58 | C03, 09:30, rush 06:30, habit off | 551.12 | 687.96 | 24.8% |

Every candidate of every pool appears in the panel. Every parameter binds in every tier where it varies
(validator, world seeds 1–3 too): `closed_cafe` (the other candidates' references serve the closed café),
`van_capacity` in easy and medium (the headline reference loads a van above 100), `premium_first` (the habit costs the
headline reference at least 1%), `shift_end` and `rush_start` in hard.

## What an agent must ask

The clarification targets, by tier (`locales/<lang>/targets.yaml`), one fact each:

- **Every tier:** road distance (`road_distance`), unloading time (`service_time`), the closed café
  (`closed_cafe`), and the tray limit when it is below the racks' 120 (`tray_limit`; hard always 110).
- **easy and medium:** the constant 25 km/h (`speed`).
- **easy:** that any van may serve the partner cafés this week (`partner_this_week`).
- **medium and hard:** the cold chain (`cold_chain`), whether the premium-first habit holds (`premium_first`) and
  what a late minute costs (`lateness`: 3 van minutes; deliver_by is not a hard deadline).
- **hard:** that there is a morning rush (`rush_hour`), when it starts (`rush_start`), the end of the shift
  (`shift_end`), V2 in the workshop until 06:40 (`workshop`) and that the C07 manager's demand is not a rule
  (`manager_pressure`).

So 5 or 6 targets in easy, 7 or 8 in medium, 12 in hard. The client also says, when asked, that a late minute costs 3
van minutes (in easy, where no good plan is late), that each café gets its trays in one visit, that vans may leave from 05:00 and wait for a café to
open, and how the dispatcher plans today; those facts change no good plan and are context, not targets.

## Data

`cafes` (18 cafés C01–C18: `x_km` / `y_km` relative to the kitchen at (0, 0), `trays` 8–29, `tier`
premium/standard, `opens` 06:00 to 08:00, `deliver_by` 30, 45 or 60 minutes after opening, `partner_brand`) and
`vans` (V1–V4, `max_trays` 120, only V4 refrigerated). File names, headers and labels are localized
(`매장목록.csv` with `매장등급 = 프리미엄`, `cafeterias.csv` with `categoria = premium`); IDs and numbers are not, and
a café's name follows its ID (C11 is always South Hill café). The closed café is an ordinary row: only the client
knows it is closed. The data gives positions only: no driving speed, road factor or unloading time.

At the case seed the 18 cafés order 356 trays (337 to 348 with the closed café out, against 400 to 480 trays of
fleet capacity). Premium cafés open first (06:00 or 06:30), except the East Lake café (C07, premium), which opens at
07:00 or 07:30 in every world, after the 06:30 its manager demands. The partner cafés are Harbour café (C05,
standard), Clock Tower café (C10, premium) and Stadium café (C16, premium).

**Which worlds are used.** `build_world` keeps drawing from the seed's stream until a world is usable for every
setting a rule seed can draw (public or private):
1. For each tier, a valid plan serves all 18 cafés under the tier's strictest combination (100 trays, back by
   09:00, in hard the 06:30 rush and V2 from 06:40, the habit and the cold chain where the tier has them). That
   plan is the tier's fallback: with the closed café dropped it keeps every setting's rules.
2. Every parameter can change the answer where it varies: under each tier's headline the reference loads a van
   above 100 trays (easy, medium), brings a van back after 09:00 (hard) and costs at least 1% more with the habit
   than without it (medium, hard). A quick construction screens the draw first, the reference confirms it.
3. Every rule has a plan that breaks only it in hard with 110 trays and the 09:00 shift end.

A world takes 1 to 5 seconds to build.

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
are not open yet included), plus 3 × every minute a café is reached after its `deliver_by`.

## Situations present

- **Hidden facts:** the travel times; which café is closed; this week's tray limit below `max_trays`; whether the
  premium-first habit holds; in hard, when the rush starts and when the shift ends.
- **Data semantics:** `partner_brand = yes` means chilled goods, so the refrigerated van only (medium, hard), but
  not this week in easy.
- **Habit that may bend:** premium first, where drawn. It costs the reference planner 0 to 6% of the objective, so
  an exception pays in some settings and not in others (below).
- **Dated event (hard):** V2 in the workshop until 06:40 on Monday.
- **Pressure (hard):** the C07 manager's demand to be the first stop before 06:30. The client says it is not a
  rule; her café opens at 07:00 or later, so following it means a van waiting at her door.
- **Trade-off:** leaving later avoids waiting at cafés that are not open yet, but in hard legs after the rush
  start are slower, and late arrivals cost three times as much as van time.

## Reference and baseline

The **reference** (`_plan`) starts from the greedy cheapest-insertion construction (partner cafés first when the
cold chain applies, then by tier, biggest first, with retries from each workable order of the partner cafés and from
shuffled orders), the tier's fallback without the closed café and the dispatcher's plan; polishes each by local
search (relocation, exchanges between routes, reversals within a route); runs ruin and recreate three times (300
rounds each, one with a cooling threshold) with departures on a 5-minute grid; and polishes the best plan again with
departures to the minute. It is computed once per world and rule values, and is within 1.2% of the proven optimum
in every easy setting, 3.2% in every medium one and 1.6% in every hard one (relative to the reference's objective;
GT.md, part 4).

The **baseline** (`baseline_solution`) is the dispatcher's own hand plan, which the requirements describe: he draws
up the morning three ways and drives the cheapest. Two go through the cafés in the order they open, or in the
order of `deliver_by` (partner cafés first, to V4, when the cold chain applies; premium cafés before standard ones
while the habit holds), giving each café to the van that can be there first, at the end of its round, if that van
keeps the tray limit and is back in time; a café that fits at the end of no round is squeezed in where it adds the
least driving, if need be after moving one café of that round to another, and one that still fits nowhere is given
out first. The third splits the map into four slices round the kitchen. He then puts each round in its best order
and sends each van out to reach its first café as it opens (V2 in hard not before 06:40). He knows every rule and
the travel times. The first version's baseline sent every van out at 05:00 along a slice of the map, 1.2 to 3.8
times the reference: a strawman that left a plan 20% worse than the reference at quality 0.9.

The case-seed routes of the headline settings:

| Setting | Plan | Objective |
|---|---|---|
| medium/s5 reference | V1 06:15 C01 C08 C15 C17 C03 · V2 06:15 C04 C13 C12 · V3 06:50 C07 C02 C14 C06 · V4 05:45 C16 C10 C05 C18 C09 | 491.17 (490.36 route min, 0.27 late) |
| medium/s5 baseline | V1 06:14 C01 C08 C12 C06 · V2 06:13 C04 C18 C15 C17 · V3 06:19 C13 C07 C02 C14 C09 · V4 05:40 C16 C10 C05 C03 | 590.45 (590.45, 0 late) |
| hard/s5 reference | V1 06:49 C07 C02 C14 C06 C03 · V2 06:40 C01 C18 C15 C17 · V3 06:19 C04 C13 C12 · V4 05:44 C16 C10 C08 C05 C09 | 508.01 (498.14, 3.29 late) |
| hard/s5 baseline | V1 06:17 C01 C08 C15 C17 · V2 06:48 C07 C02 C14 C09 · V3 06:21 C13 C04 C18 C06 · V4 05:43 C16 C10 C05 C12 C03 | 619.04 (619.04, 0 late) |

**Literal solution** (`literal_solution`: the request done as written, the same in every setting): the reference
planner with the readings the agent's view gives, every café on the list served ("all our cafés"), any van for any
café up to its racks' 120 trays, out from 05:00 with no shift end, `deliver_by` as the target (a late minute weighted
as ten van minutes), no closed café, habit, cold chain or workshop day. The data has positions but no travel times,
so it assumes what an agent assumes when nobody says: the straight line between the coordinates, 30 km/h and five
minutes at each café. It delivers to the café that is closed this week, so it is invalid in all 9 public settings,
as delivered and with the bendable habit relaxed (also over the week's tray limit, and in hard back after the shift
end and with V2 out before 06:40). Every other reading of the travel times is invalid the same way, since the plan
serves every café; but its near miss with the closed café known depends on the guess: 0.00 with the literal's own,
up to 0.93 with a planner's (1.3 times the straight line, 25 km/h, five minutes a stop) in six of the nine easy
settings, where the closed café is often the only rule it breaks (known and open, Ground truth audit below).

## Ground truth audit

`fdebench2 audit-case` measures the case on 39 settings (the public panel and up to 12 other combinations per tier:
easy has only 9). [GT.md](../../GT.md) has the five parts with every table; [CLIENT_REVIEW.md](../../CLIENT_REVIEW.md)
the passages the client answers from, awaiting human review. In short:

| Part | Result |
|---|---|
| Client facts | 14 targets, one fact each. Every one bites (invalid, or at least 0.10 of the scale lost) in every tier where it is in force: `closed_cafe`, `cold_chain` 1.00 everywhere; `road_distance` 0.23–1.00, `speed` 0.17–1.00, `rush_hour` 0.11–1.00, `manager_pressure` 0.28–1.00 and `partner_this_week` 0.16–0.70 in every setting; `service_time` (read as five minutes a stop) in 32 of 39, `rush_start` in 13 of 15, `premium_first` in 22 of 30, `workshop` in 9 of 15, `lateness` in 10 of 30 (medium and hard; in no medium setting of world seeds 1–3), `tray_limit` in 13 of 31 (where the limit is the strict end of its pool) and `shift_end` in 1 of 15 (least harmful wrong candidate). The travel facts are guessable together: with every other fact known, a planner's guess of the travel times reaches above 0.5 in 7 of 9 easy, 11 of 15 medium and 9 of 15 hard settings (GT.md, part 5) |
| Shortcuts | 15. Closed in all 39 settings: café-id order, opening order, nearest neighbour without the windows, the deadline order balanced by trays (0.00), cheapest insertion with the departures left out (0.00), four map slices (at most 0.41) and the literal solution with any one client fact known (closed café 0.00; the others invalid). Known and open (`validate.OPEN_AUDIT_FINDINGS`): the dispatcher's plan with its timing done right reaches 0.67 (hard/c12) and 0.53 (medium/s13) and with its one most useful café move 0.53 (hard/c1); the literal solution with the closed café known and a planner's guess of the travel times (1.3 times the straight line, 25 km/h, five minutes a stop) reaches 0.77–0.93 in 6 of the 9 easy settings |
| Value of asking | A plan that never asks keeps 0.22 / 0.31 / 0.16 of the credit in easy / medium / hard (0.33 / 0.31 / 0.16 with the luckiest guess about a fact nothing on hand settles), so asking is worth 0.78 / 0.69 / 0.85 |
| Reference and bounds | Proven optimum (a mixed-integer model with the rush priced exactly) in all 39 settings: the reference is 0.0–1.2% above it in easy, 0.0–3.2% in medium and 0.1–1.6% in hard; best known quality 1.000–1.234 (median 1.000), `quality_cap` 1.0 |
| Diagnostics | Every target has one. It separates the reference from every ablation that bites and never calls the best known plan not enforced. A plan misread in a way no ablation plans (slower, longer roads, heavier unloading, deliver_by ignored, another rush start) is told by a small grid of misreadings round the client's value; the travel facts flag each other, since all of them change how long the vans take |

**Bending the premium-first habit** pays in some settings and loses in others. Where it holds it costs the
reference planner 0% to 5.7% of the objective; dropping it under an approved exception gains 0.00 to 0.64 of quality.
Against the policies' penalties (0.05 and 0.10 of the final score, quality weighing 0.6: a gain above 0.083 and
0.167) that pays under both policies in 3 of the 13 measured settings, under the startup policy only in 4 and in
neither in 6. A plan already at the reference's level gains nothing, since `quality_cap` is 1.0.

**Round 2026-11** (rule seeds 108807, 519122 and 904685 in every tier): reference and baseline valid in all nine
settings on the public world and world seeds 1–3, scale 6.5% to 56% wide, literal solution invalid as delivered and
with the habit relaxed. The open near miss with a planner's guess of the travel times reaches 0.84 and 0.77 in
easy/s108807 and easy/s519122 on the public world, and the dispatcher's plan with one café moved 0.56 in hard/s904685
(a combination the audit's 39 settings do not hold).

## Notes

- Synthetic. The positions, tray counts, opening times, speeds, service time and the lateness weight are
  invented. In hard the speed changes at `rush_start` also on a leg already under way (the time a leg takes is
  never shorter when it starts later).
- `validate-case` checks every public setting: the reference at quality 1.0, the baseline valid and worse, one
  deliverable per rule in force that breaks only that rule, deterministic data in five locales, every parameter
  binding, the same agent view in every setting, the literal solution, the stored audit and world seeds 1, 2 and 3.
