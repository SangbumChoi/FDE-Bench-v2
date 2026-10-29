# Bakery Delivery Dispatcher — `logistics/bakery_delivery_dispatcher`

A bakery's central kitchen delivers bread trays to its cafés every morning with four vans. The client asks the
agent to plan tomorrow's (Monday) routes "so the cafés get their trays in time and the drivers aren't out longer
than they need to be". The deliverable is `routes.json`: for each van used, a departure time (`HH:MM`, 05:00 if
left out) and the cafés in visiting order. The evaluator drives the plan through the world's travel model and
scores it against the reference.

The case has no settings: it is one fixed problem at every difficulty (no tiers, no rule sets). The engagement
knobs (full spec vs. clarify first, client persona, data noise, events) apply on top, as for every case (see
[cases/README.md](../../README.md)). It is also the framework's test fixture (`tests/conftest.py`), so its
validation has to stay fast.

## Data

`cafes` (18 cafés C01–C18: `x_km` / `y_km` relative to the kitchen at (0, 0), `trays` 8–30, `tier`
premium/standard, `opens`, `deliver_by`, `partner_brand`) and `vans` (V1–V4, `max_trays` 120, only V4
refrigerated). File names, headers and labels are localized (`매장목록.csv` with `매장등급 = 프리미엄`,
`cafeterias.csv` with `categoria = premium`); IDs and numbers are not. The closed café is an ordinary row: only
the client knows it is closed.

At the case seed (20261025) 17 cafés are open with 356 trays against 480 trays of fleet capacity. The partner
cafés are Harbour café (C05, standard), Clock Tower café (C10, premium) and Stadium café (C16, premium); the
other premium cafés are C01, C04, C07 and C13.

## What the client knows (hidden requirements)

- Road distance is 1.3 times the straight-line distance. Speed depends on when a leg starts: 30 km/h before
  07:00, 20 km/h from 07:00 (rush hour). Unloading takes 4 minutes plus 0.2 minutes per tray.
- A van that arrives before `opens` waits. Arriving after `deliver_by` is accepted, but each late minute costs
  the bakery as much as three minutes of van time (complaints, credit notes).
- Vans leave from 05:00 and are back by 09:30 (end of the drivers' shift); each carries at most `max_trays`.
- South Hill café (C11) is closed this week for renovation.
- `partner_brand` cafés sell the partner's chilled products, so only the refrigerated van V4 may serve them.
- Each café gets all its trays in one visit from one van.
- The company habit: on every route, premium cafés come before standard cafés.

There are 9 clarification targets: road distance, speeds, service time, shift, closed café, cold chain, one
visit, premium first and the lateness cost.

## Rules

| Rule | Class | Meaning |
|---|---|---|
| `van_capacity` | physical | A van carries at most 120 trays. |
| `shift_window` | physical | Vans leave at 05:00 or later and are back at the kitchen by 09:30. |
| `closed_cafe` | physical | No delivery to the closed café (C11). |
| `serve_each_once` | contractual | Every open café is served exactly once. |
| `cold_chain` | contractual | Partner-brand cafés are served only by the refrigerated van. |
| `premium_first` | business policy | On every route, premium cafés come before standard cafés (may bend through the exception process under policies that make business policy soft). |

**Quality (lower is better):** the total time all vans are out, from departure to return (waiting at closed
cafés included), plus 3 × every minute a café is reached after its `deliver_by`.

## Situations present

- **Hidden fact:** C11 is closed this week; nothing in the data says so.
- **Data semantics:** `partner_brand = yes` means chilled goods, so the refrigerated van only.
- **Habit that may bend:** premium first. At this seed it makes V4 serve C16 and C10 before C05, so C05 is
  reached about 10 minutes after its 07:30 `deliver_by` in every compliant plan.
- **Trade-off:** leaving later avoids waiting at cafés that are not open yet, but legs that start from 07:00 are
  slower and late arrivals cost three times as much.
- No dated event and no stakeholder pressure (see REVIEW.md, F8).

## Reference and baseline

The **reference** (`_solve`) builds the routes by cheapest feasible insertion (partner cafés first, then by tier,
biggest first), retrying with V4 seeded by each workable order of the partner cafés and then with shuffled
insertion orders when the greedy construction corners itself. It then relocates single stops while the
objective drops, and gives each route its best departure on a 5-minute grid.

The **baseline** (`baseline_solution`) is the dispatcher's own plan without an engineer: V4 takes the partner
cafés (premium first, in the order that brings it back soonest); the other cafés are taken in bearing order
round the kitchen, starting due west, and loaded onto V1, V2, V3 and then V4 until the next one no longer fits
(capacity, back by 09:30); each van serves its premium cafés first and then the rest in order of opening; every
van leaves at 05:00, when the shift starts, and `deliver_by` is ignored. If a café is left over, the sweep starts
from the next café round (if no start works, the reference routes are driven with every van leaving at 05:00,
which is always valid; no world built so far needs this).

| Seed 20261025 | Objective | Route minutes | Late minutes | Routes |
|---|---|---|---|---|
| Reference | 625.55 | 592.74 | 10.94 | V1 06:20 C01 C04 C15 C08 · V2 06:00 C13 C07 C18 C06 · V3 05:45 C09 C03 C14 C02 C17 · V4 06:10 C16 C10 C05 C12 |
| Baseline | 963.09 | 897.53 | 21.85 | V1 C03 C14 C02 C17 · V2 C07 C13 C09 C18 C06 C12 · V3 C01 C04 C08 C15 · V4 C16 C10 C05, all at 05:00 |

Most of the baseline's extra cost is waiting: leaving at 05:00, the vans reach cafés that open from 06:00 on.

Other world seeds (the `validate-case` panel and two more):

| World seed | Reference | Baseline | Baseline / reference |
|---|---|---|---|
| 1 | 568.06 | 1,292.28 | 2.27 |
| 2 | 779.02 | 1,192.03 | 1.53 |
| 3 | 560.91 | 1,402.46 | 2.50 |
| 7 | 543.02 | 939.29 | 1.73 |
| 42 | 532.93 | 1,415.56 | 2.66 |

Over the case seed and world seeds 1–50 the baseline is valid in all 51 worlds (the fallback is never used) and
costs 1.37 to 4.16 times the reference (median 2.19). `validate-case --world-seeds 1,...,50` passes.

**Headroom** (seed 20261025; "q" is normalized quality, baseline 0 and reference 1). A simulated-annealing
search from the reference (relocate, swap and 2-opt moves, departures to the minute; an analysis script, not part
of the case) reaches 601.51 under all rules, q = 1.07, which earns 0.71 of the quality credit at the policy cap
of 1.5 (the reference earns 0.67). Its loads are 89/85/115/67 trays and its latest return is 09:21, so neither
capacity nor the shift binds there. With `premium_first` relaxed the same search reaches 521.98 with no late
minutes (q = 1.31), bending the habit on three of the four routes.

## Notes

- Synthetic. The positions, tray counts, opening times, speeds, service time and the lateness weight are
  invented; the speed is a step at 07:00 by leg start time, not a time-dependent travel model.
- `build_world` keeps drawing from the seed's random stream until the reference solver finds a plan that keeps
  every rule and every rule has a plan that breaks only it, so any world seed gives a usable world.
- `validate-case` checks the reference at quality 1.0, the baseline valid and worse, one deliverable per rule
  that breaks only that rule, deterministic data in five locales, and world seeds 1, 2 and 3.
