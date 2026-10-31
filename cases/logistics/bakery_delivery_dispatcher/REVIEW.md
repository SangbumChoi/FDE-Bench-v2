# Review of `logistics/bakery_delivery_dispatcher`

Findings of the case review (F1–F9), with the verifier's verdicts and what this change did about each. The
numbers are for the case seed 20261025 unless they say otherwise; "q" is normalized quality (baseline 0,
reference 1). The headroom numbers come from a simulated-annealing search from the reference (relocate, swap
and 2-opt moves, departures to the minute), which reproduced the review's 601.51 and 521.98.

### F1 — The closed café was called by another café's name (high, confirmed)

All five locales said "Clock Tower café (C11)" is closed. In the data Clock Tower is C10, a premium partner
café, and C11 is South Hill (남산점, 南山店, Cafetería Colina Sur). An agent that followed the name, serving
C11 and skipping C10, handed in an invalid plan: the reference edited that way breaks `closed_cafe`,
`serve_each_once` (C10 not served) and `shift_window` (V4 back at 10:08). Validity depended on trusting IDs
over names, not on asking the right question.

**Status:** fixed in this change — requirements.md and targets.yaml in all five locales now name the café as
the data does: South Hill café (C11), 남산점(C11), 南山店（C11） (ja, zh), Cafetería Colina Sur (C11). C10 stays
open. The validator's `name (ID)` lint, which flagged the mismatch in all five locales, is now silent.

**Rule seeds:** the closed café is now a parameter (C11, C03 or C14). Each candidate's wording in every locale
comes from `params.closed_cafe.labels` in case.yaml and is the name the data gives that ID (a café's name follows
its ID in every world), so the fix holds for every drawn café; the pressure café of the hard tier, C07, is named as
in the data too. The `name (ID)` lint is silent in every public setting.

### F2 — Little headroom above the reference (high, confirmed)

The search reaches 601.51 under all rules, 3.8% below the reference's 625.55. Quality is no longer clipped at
1.0: against the new baseline (963.09) that plan scores q = 1.07 and earns 0.71 of the quality credit at the
policy cap of 1.5, against 0.67 for the reference. The review's naive angle-sweep plan with tuned departures
(686.39) scores q = 0.82. So naive and expert plans now separate (0, 0.82, 1.0, 1.07), but no known compliant
plan gets near the cap.

**Status:** open — proposal: either strengthen the reference (swap and 2-opt moves, departures to the minute:
about 601.5 on this world) or keep it and set `quality_cap: 1.1` in case.yaml, so that a plan at the best known
level earns full credit. Tightening the instance (F3, F4) would spread plans further.

**Rule seeds:** the reference now also starts from the tier's fallback plan and adds 300 rounds of ruin and
recreate after relocation. The numbers above are for the old single problem; headroom under the new rules has not
been measured. Still open.

### F3 — Bending premium-first pays only marginally, and not where the habit hurts (high, partly)

With `premium_first` relaxed the search reaches 521.98 with no late minutes (q = 1.31), 13.2% below the best
compliant plan. Every compliant plan reaches C05 about 10 minutes late, because V4 has to serve C16 and C10
first (reference V4: C16 06:19, C10 07:00, C05 07:40). The old "clipped at 1.0" argument is gone with the new
scale. With all four score components counted (quality weight 0.6), bending gains 0.094 of the final score
before the penalty against the best compliant plan. That nets −0.006 under `enterprise_balanced` (penalty 0.1)
and +0.044 under `startup_velocity` (0.05). Against the reference it nets +0.023 under `enterprise_balanced`. The best bent plan bends three of the four routes, not
only V4.

**Status:** open — proposal: decide whether a well-argued exception should pay here. If yes, make the habit's
cost concrete and local: for example a partner SLA ("partner cafés charge us for every late minute"), so the
compliant V4 route costs clearly more than a bent one and the business reason is the one the agent should give.
Keep the README's with-and-without numbers (601.51 against 521.98) up to date. If no, remove the conflict
(for example a later `deliver_by` for C05) or make the habit contractual, so that bending never nets a gain.

**Rule seeds:** the habit is now a parameter: medium and hard draw it on or off, easy has it off. Where it holds it
costs much more than before, 27.5% (hard/s5) and 28.4% (medium/s5) of the reference's objective at the case seed,
because the delivery windows are now tighter; bending it with an approved exception pays clearly where business
policy is soft. `build_world` requires at least 1% at the hard headline so that the parameter binds. Whether a bend
should pay this much is still open.

### F4 — Capacity, the shift and the one-visit target do not decide the best plan (medium, partly)

In the best compliant plan the loads are 89/85/115/67 trays against 120, and the latest return is 09:21 against
09:30. Open demand is 356 trays against 480 of fleet capacity. The deliverable has no per-stop quantity, so the
`one_visit` target cannot change a plan (a café listed twice is already a `serve_each_once` violation). Both
rules do bind on weaker plans: the baseline's sweep moves to the next van exactly when capacity or the shift
cuts it off. `van_capacity` has no clarification target (`max_trays` is in the data).

**Status:** open — proposal: if the physical rules should matter for strong plans, make one bind at the
optimum: a shift end of 09:00, or demand near 90% of the fleet. A smaller V4 would not do it, since the compliant
V4 route carries 67 trays. Either drop the `one_visit` target or allow split deliveries with per-stop tray
counts, so that the fact changes the deliverable.

**Rule seeds:** partly resolved. The shift end (09:00, 09:30, 10:00) and this week's tray limit (100, 110, 120; a
hidden fact below the visible `max_trays` of 120, framed as new, deeper crates) are parameters, and `build_world`
keeps only worlds in which they can change the answer: the hard headline reference has a van back after 09:00 and
the medium headline one carries more than 100 trays (case seed: 09:03 and 103 trays), so both bind there.
`van_capacity` now has a target (`tray_limit`) whenever it is below 120. The `one_visit` target is unchanged
(open).

### F5 — The lateness cost was stated only as a scoring rule (medium, confirmed)

The 3× weight on late minutes appeared only under "How the plan is judged". The client prompt forbids
describing weights, and the data notes only said `deliver_by` is "the latest arrival the café is happy with".
Whether the agent learned the trade-off, and whether the `lateness` target could be covered, depended on the
simulated client breaking its own instructions.

**Status:** fixed in this change — the data notes in all five locales now state the cost as a business fact,
right after the `deliver_by` line: "A late delivery is accepted but not free: every minute a café is reached
after its `deliver_by` costs us as much as three minutes of van time (complaints and credit notes to the café)."
The "How the plan is judged" section is unchanged; reducing it to the manager's voice is left to the owner.

**Rule seeds:** the weight is the parameter `late_cost` (2, 3 or 5), stated the same way in the data notes, the
judging section and the `lateness` target.

### F6 — Some world seeds crashed the generator (medium, confirmed)

At review time the reference solver raised on 5 of world seeds 1–30, and 3 of those worlds had no valid plan,
because partner and tier roles are fixed by index.

**Status:** not reproduced — the earlier commit "Bakery dispatcher: work on any world seed" (adb576f) makes
`build_world` keep drawing from the seed's stream until the reference finds a valid plan and every rule has a
plan that breaks only it, and the construction now retries from each workable partner order and from shuffled
orders. World seeds 1–50 all build, and `validate-case --world-seeds 1,...,50` passes: reference, violating
examples and the new baseline. The roles are still fixed by index; the redraw does the work.

**Rule seeds:** `build_world` now also needs a valid plan under each tier's strictest combination (the tier's
fallback) and worlds in which every parameter can matter (see "Rule seeds" below). About 9% of draws pass, 0.8 s
per world on average. The case seed and world seeds 1–30 build; `validate-case --world-seeds 1,...,20` passes. The
data at the case seed changed with it.

### F7 — Delivery during opening hours, the speed step and district names (medium, partly)

Vans wait until a café opens, and `deliver_by` is 45–90 minutes after opening, whereas real bakery drops
usually land before opening. Speed depends only on when a leg starts: a leg starting at 06:59 runs entirely at
30 km/h, one starting at 07:00 takes 50% longer. District names ignore the coordinates (North Station café is
at y = −10.27, South Hill café at y = +6.05), though the data never says +y is north. The verifier finds these
to be realism judgments rather than defects: the rules are stated and apply to every agent alike.

**Status:** open — proposal: if the case is reworked (F8), turn `opens` into a receiving window ("staff on site
from") with `deliver_by` at or before opening, use a speed that changes mid-leg (or ramps over 06:45–07:15), and
assign district names from the coordinates. Each of these changes the data and the reference, so they belong
with the F8 redesign rather than in a patch.

**Rule seeds:** partly done. In hard the speed now changes at `rush_start` also on a leg already under way (a leg
starting later never takes less time); easy and medium use a constant 25 km/h. `deliver_by` is now 30, 45 or 60
minutes after opening (was 45, 60 or 90), so lateness is a live trade-off. `opens` as a receiving window and
district names from the coordinates are not done (open).

### F8 — No settings, and only hidden facts (medium, confirmed)

The case has no tiers or rule sets, so every difficulty column scores the same problem. Of the three situation
kinds it has only hidden facts (C11 closed, the cold-chain meaning, the premium-first habit): no dated event and
no stakeholder pressure. It is also the framework's test fixture (`tests/conftest.py`), which makes changes to it
costly.

**Status:** open — proposal: first move the fixture tests to a small dedicated case. Then convert to 3 tiers ×
3 rule sets with byte-identical data. Easy: the travel model, shift, closed café and lateness cost, with the
cold chain and premium-first stated as out of scope this week. Medium: adds the cold chain, rush-hour speeds and
premium-first (bendable). Hard: adds a dated event (V2 in the workshop until 06:40, or a doubled order that makes
capacity bind) and a pressure message (a premium manager demanding to be first). Rule sets could vary which café
is closed, the shift end, the lateness weight and the rush start. A hidden V4 capacity would contradict the
visible `max_trays`, so it should be framed as a hidden fact ("V4's chiller shelf is broken this week").

**Status (rule seeds):** resolved — converted to 3 tiers and 6 parameters drawn by rule seeds, with V2 in the
workshop until 06:40 as the dated event and the East Lake café (C07) manager's demand as pressure, both in hard;
see "Rule seeds" below. The tray limit is framed as a hidden fact for every van (new crates), not V4 only. The
fixture tests stay on this case, updated minimally.

### F9 — Korean wording of the 07:00 boundary and one column label (low, confirmed)

`07:00 이전` / `07:00 이후` both include 07:00 in standard Korean usage, so a leg starting exactly at 07:00 fell
in both speed bands; minute-level departures make that case reachable. The column label `최종도착` reads as
"final arrival" rather than a deadline. Numbers agree across the five locales.

**Status:** fixed in this change — ko/requirements.md and ko/targets.yaml now say "07:00 전에 출발하는 구간은 시속
30km, 07:00부터 출발하는 구간은 시속 20km". The Korean column is renamed `납품마감` in the data (case.py) and in
every Korean text that names it.

**Rule seeds:** the speed sentences were rewritten for the new model (easy and medium: a constant 25 km/h; hard:
`{{rush_start}} 전까지는 시속 30km, {{rush_start}}부터는 시속 20km`), keeping an unambiguous boundary. `납품마감` is unchanged.

**Baseline:** the dispatcher's own plan (V4 takes the partner cafés; the rest are split by bearing round the
kitchen and loaded onto V1, V2, V3, then V4; premium first, then by opening; every van leaves at 05:00): 963.09
against the reference's 625.55 at seed 20261025 (×1.54). On world seeds 1, 2 and 3: 1,292.28 against 568.06,
1,192.03 against 779.02 and 1,402.46 against 560.91. Over seeds 1–50 it is valid in every world, at ×1.37 to
×4.16 the reference (median ×2.19).

## Rule seeds

The case moved from one fixed problem to the rule-seed contract (DESIGN.md, Settings): three tiers in case.yaml
and six parameters that a rule seed draws, each on its own, from a pool per tier. The data and `request.md` are the
same in every setting; the requirements, targets, rules and scoring follow the drawn values.

- **Tiers.** Easy: this week's tray limit, the shift, one visit, the closed café, a constant 25 km/h and the
  lateness cost; the requirements say in the client's words that the partner brings its chilled range itself this
  week, that the premium-first habit is suspended, that Monday has no rush hour (school holiday) and that V2's brake
  check is on Tuesday. Medium adds the cold chain and the habit where drawn. Hard adds the rush (30 km/h before
  `rush_start`, 20 km/h from it, also mid-leg), V2 in the workshop until 06:40 (new rule `van_ready`) and the C07
  manager's pressure (not a rule; target `manager_pressure`).
- **Parameters.** `closed_cafe` (C11, C03, C14, worded per locale by labels), `late_cost` (3, 2, 5), `shift_end`
  (09:30, 09:00, 10:00), `van_capacity` (100, 110, 120 in easy and medium; 110 in hard, so it is compared in
  medium), `rush_start` (none in easy and medium; 07:00, 06:30, 07:30 in hard) and `premium_first` (false in easy;
  true or false in medium and hard). No derived values; every combination is admissible.
- **Public panel.** Rule seeds 5, 13 and 58: every candidate appears, and seed 5 draws the medium and hard
  headline (latest shift end, largest tray limit, first candidate of the rest).
- **Every setting has a valid plan.** `build_world` solves each tier's strictest combination with all 18 cafés
  open and keeps the plan as the tier's fallback; dropping the closed café keeps it valid under any draw of the
  tier, private seeds included. The reference starts from it as well as from the greedy construction.
- **Every parameter binds**, in every world `build_world` accepts: the closed café and the rush start always; the
  shift end, tray limit, lateness weight and habit because `build_world` keeps only worlds in which they change the
  headline reference (a van back after 09:00 in hard, one above 100 trays in medium, lateness of at least 1% of
  the objective and a habit that costs at least 1% in hard). The world filter is calibrated over the pools only.
- **Data change.** `deliver_by` is 30, 45 or 60 minutes after opening (was 45, 60 or 90) and the accepted world at
  every seed changed with the new filter, so the case-seed data and all numbers differ from the findings above.
- **Baseline.** Still the dispatcher's sweep (V4 takes the partner cafés when the cold chain applies; every van out
  at 05:00, V2 at 06:40 in hard), valid in every setting checked (case seed and world seeds 1–30, rule seeds 5, 13,
  58 and 101–105) at 1.17 to 9.76 times the reference.
- **Tests.** `tests/test_validator.py` keeps this case as its fast fixture: its planted baselines and example
  override take the setting argument, and two assertions match the per-setting messages. `tests/test_end_to_end.py`
  and `tests/test_isolation.py` write the reference through `NativeCase.write_reference` and resolve the spec's rule
  seed before looking up a run folder. `tests/test_rule_seeds.py` used this case as "a case without settings"; it
  now writes a minimal settings-less case.yaml for that.
- **Open:** headroom above the new reference (F2), whether bending the habit should pay this much (F3), the
  `one_visit` target (F4), receiving windows and district names (F7).
