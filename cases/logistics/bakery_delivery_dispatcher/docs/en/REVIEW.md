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

**Ground truth audit:** closed. The reference now polishes every start by local search (relocation, exchanges,
reversals), runs ruin and recreate three times and times each van to the minute; a mixed-integer model gives the
proven optimum of every easy and medium setting it solves within two minutes, and the reference is within 1.2% of it
(most settings within 0.3%). `best_known_solution` and `objective_bound` read the stored results
(`make_bounds.py`, `reference/best_known.json`), and `quality_cap` is the median best known quality (see "Ground
truth audit" below).

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

**Ground truth audit:** closed. The premium cafés now open first (06:00 or 06:30), as the habit's reason says ("so
the premium stores are ready first"), except the East Lake café (C07), whose manager wants to be served before 06:30
and which opens at 07:00 or 07:30. The habit then costs the reference planner 0% to 5.7% of the objective (was about
28% everywhere), and an approved exception pays under both policies in some settings, under the startup policy only
in others, and loses in the rest (GT.md, part 2; "Ground truth audit" below).

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

**Ground truth audit:** closed. The `one_visit` target is gone (the requirement stays as context: the deliverable
cannot express a split delivery, so the fact changes no plan). With a stronger reference no plan worth handing in
comes back after 09:00 in easy and medium, so the shift end there would change nothing: it is fixed at 10:00 in easy
and medium and drawn (09:00, 09:30, 10:00) in hard only, where the rush makes it bind; `build_world` now checks the
tray limit's and the habit's binding in every tier where they vary. The two open binding findings of the shift end
(easy and medium, world seeds 2 and 3) are gone with it.

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

**Ground truth audit:** the weight is fixed at 3 again. The reference is on time, or within a few minutes, in
almost every setting, so another weight hardly changes its plan: the validator's open binding finding in easy, and
over the audit's settings the reference made for 2 or 5 loses at least a tenth of the scale in one easy, two medium
and no hard setting, never as the less harmful guess. The `lateness` target now says only what the client means
(late is allowed and costs 3 van minutes a minute; deliver_by is not a hard deadline) and is in force in medium and
hard: read as a firm deadline (a late minute weighted ten, the literal's reading) it costs a tenth of the scale or
more in 7 of 15 medium and 3 of 15 hard settings, and in none of the 9 easy ones, where it stays context.

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

**Ground truth audit:** unchanged on receiving windows and district names (open). Openings now run to 08:00
(standard cafés), and the premium cafés open first (F3).

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

**Ground truth audit:** replaced. Every van out at 05:00 along a slice of the map was a strawman: it waited at cafés
that were not open and ignored deliver_by, so a plan 20% worse than the reference still scored about 0.9 and soft
facts could not bite. The zero is now the dispatcher's hand plan as the requirements describe it in all five
locales (see "Ground truth audit" below): 1.13 to 1.25 times the reference in the public panel.

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
  `one_visit` target (F4), receiving windows and district names (F7). (Ground truth audit: F2, F3 and F4 are now
  closed; F7 is still open.)

## Ground truth audit

The audit contract (DESIGN.md, Ground truth audit) and the brief's checks were applied together. `audit-case` passes
with two known findings (below); `audited: true`, `quality_cap: 1.0`.

### What was wrong

- **The zero point was a strawman.** The baseline sent every van out at 05:00 along a slice of the map, so vans
  waited at cafés that were not open and reached others late: 1.2 to 3.8 times the reference. On that scale a plan
  20% worse than the reference still scored about 0.9, the soft facts (lateness, the partners this week, the
  pressure café) could not lose a tenth of it, and lazy plans scored well.
- **The literal solution knew what nobody had told it.** It planned with the client's travel times (the 1.3 road
  factor, 25 km/h, four minutes plus 0.2 a tray), which the request and the data never give. With the closed café
  dropped (the "literal plus one rule" near miss) it scored 0.95 to 1.03 in every easy setting with 120 trays.
- **Facts that changed nothing.** `one_visit` (the deliverable cannot split a delivery), the lateness weight in easy
  (2, 3 or 5: the reference is on time) and the shift end in easy and medium (no good plan comes back late there):
  the last two were the validator's three open binding findings.
- **Bending premium-first paid everywhere** (about 28% of the objective).
- **No evidence of headroom:** no best known solution, no bound, no `quality_cap`; the reference was up to 11% above
  plans the search itself found in hard, and changed by up to 10% between runs of a slightly different search.
- **No audit hooks:** no ablations, shortcuts, never-asks solver or diagnostics.

### What changed (scenario, in the client's terms)

| Change | Before | Now | Why |
|---|---|---|---|
| The client's own way | every van out at 05:00 along a slice of the map, premium cafés first even when the habit is suspended | the dispatcher's hand plan, described in requirements.md in all five locales ("How we plan it today"): three ways (by opening time, by deliver_by, four map slices), the cheapest one driven; each café to the van that can be there first, partner cafés to V4, premium cafés first while the habit holds; each round in its best order; each van leaves to reach its first café as it opens | a dispatcher who knows the rules and the travel times; 1.08 to 1.45 times the reference over the audit's settings (public panel 1.13 to 1.25) |
| The literal solution | the reference planner with the client's travel times | the reference planner with the travel times an agent assumes when nobody says: the straight line, 30 km/h and five minutes a stop | the data gives positions only |
| The cafés' opening times | 06:00 to 07:30 for every café | standard cafés 06:00 to 08:00; premium cafés 06:00 or 06:30 (the habit's reason: "so the premium stores are ready first"), except the East Lake café (C07), which opens at 07:00 or 07:30 | bending the habit pays where C07 or a partner café gets in the way and not elsewhere; the manager's "before 06:30" means waiting in every world, not only the public one |
| The lateness cost | drawn: 2, 3 or 5 | 3 in every setting | another weight changed no easy reference; it is a target (`lateness`) in medium and hard, where reading deliver_by as a firm deadline costs |
| The shift end | drawn in every tier: 09:30, 09:00, 10:00 | 10:00 in easy and medium; drawn in hard | no good easy or medium plan comes back after 09:00 |
| Targets (14, one fact each) | `shift` (05:00 and the shift end), `rush_hour` (speeds and start), `lateness` (weight and waiting), `one_visit`, `premium_first` also in easy | `shift_end` (param, hard), `rush_hour` and `rush_start` (param), `lateness` (medium, hard), `premium_first` (param, medium and hard), `closed_cafe` and `tray_limit` marked `param:`; `one_visit` and the 05:00 start are context | one target = one thing the client must tell, and every target bites |
| The reference | greedy insertion, relocation, 300 rounds of ruin and recreate, departures on a 5-minute grid | also exchanges between routes and reversals within one, three ruin-and-recreate runs (one with a cooling threshold), departures to the minute, the dispatcher's plan as a further start | within 1.2% of the proven optimum in easy, 3.4% in medium where solved |
| `build_world` | the shift end, tray limit and habit checked in their highest tier only | checked in every tier where they vary, with a quick construction screening the draw first; a world takes 1 to 5 s | every parameter binds where it is drawn, on every world built |

**The agent's view** changed the same way in every setting: `cafes.csv` (five locales) is a new draw (the opening
rule above, and the world at the case seed was redrawn by the new filter: 356 trays, was 332); `vans.csv` and
`request.md` are unchanged. The hidden texts changed in all five locales: requirements.md (the late cost is 3, the
dispatcher's habit), targets.yaml, summary.yaml, and explainer.yaml (tiers, shortcuts).

### What the audit shows (39 settings, public world)

**Shortcuts** (each given every rule of its setting it can keep and the client's travel times):

| Shortcut | Before the audit | Now | How closed |
|---|---|---|---|
| `literal_plus_closed_cafe` | 0.95–1.03 in the easy settings with 120 trays | 0.00 (invalid in 34 of 39) | the travel times the request never gives |
| `literal_plus_van_capacity`, `_shift_window`, `_cold_chain`, `_premium_first`, `_van_ready` | not measured | invalid in all 39 | the closed café |
| `id_order` | not measured | 0.00 (valid in 12) | the delivery windows |
| `opening_order` | not measured | 0.00 | the map |
| `nearest_neighbour` | not measured | 0.00 | the delivery windows |
| `map_slices` | the zero point itself | at most 0.41 | the dispatcher's slices are one of his three ways |
| `habit_best_departures` | not measured | at most 0.43, except 0.66 in hard/c12 | known and open (below) |
| `habit_one_move` | not measured | at most 0.43, except 0.53 in hard/c1 | known and open (below) |

- **The literal solution**: invalid in all 9 public settings as delivered and with the habit relaxed (the closed
  café; also over the week's tray limit in the 100- and 110-tray settings, and in hard back after the shift end
  and with V2 out before 06:40). Its near misses depend on the travel guess, which is the client's fact carrying the
  score: over the 39 settings the literal with the closed café known is valid in 4 to 7 and scores 0.00 with the
  literal's own guess (30 km/h, five minutes) or 25 or 40 km/h, up to 0.58 with ten minutes a stop and up to 0.81 at
  20 km/h, and 0.94 with the client's travel times granted (in the easy settings with 120 trays, where the travel
  times and the closed café are the whole problem).
- **Facts**: all 14 bite in every tier where they are in force (README, Ground truth audit; GT.md, part 1).
  `shift_end` bites in one of 15 hard settings and `tray_limit` in 13 of 31: a stricter guess of an ordered pool
  costs little, so they bite where the client's value is the strict end.
- **Value of asking**: 0.90 / 0.67 / 0.85 in easy / medium / hard. `robust_solution` is granted the travel times;
  with the luckiest guess about a fact nothing on hand settles (the partner cafés free in easy, V2 on its latest
  round in hard) it keeps 0.33 / 0.33 / 0.16, so asking is still worth 0.67 / 0.67 / 0.84.
- **Reference and bounds**: `make_bounds.py` stores, for the 39 settings and the round's, the better of a long search
  and the optimal plan of a mixed-integer model where it applies (`reference/best_known.json`), and the model's dual
  bound. Best known quality 1.000–1.234, median 1.000, so `quality_cap` is 1.0. The hard bound drives every leg at
  30 km/h and is loose (11–28%).
- **Diagnostics**: one per target; the reference is enforced and every biting ablation is not, the best known plan
  is never called not enforced; the travel facts flag each other (warnings).
- **Bending**: pays under both policies in 3 of 13 habit settings, under the startup policy only in 4, in neither in 6
  (GT.md, part 2).

### Checks against the lessons of the earlier audits

- **A strong never-asks deliverable.** The solver reads every fact the data settles, keeps the partner cafés on V4
  (valid under both readings), plans for the smallest tray limit and earliest shift end, and chooses the café to
  leave out, the habit and the rush start by its own estimate of credit over every combination of the pools; it is
  granted the travel times. Its luckiest variants are reported beside it (above).
- **Copying the baseline and changing one thing.** Measured on the public world and world seeds 1–3 (39 settings
  each): the four map slices with the best departures never reach 0.5; the dispatcher's rounds with each van at its
  best minute reach 0.5 in 1 / 3 / 5 / 13 settings (at most 0.71); his plan with its most useful café move in
  1 / 2 / 0 / 0 (at most 0.73). They open where his plan is within 8–10% of the reference. A dispatcher who also
  times to the minute, or moves one café, narrows other settings' scales below 5% (measured: down to 3.6% on these
  worlds), so both are waived in `validate.OPEN_AUDIT_FINDINGS` with that reason.
- **The baseline is the client's way, not a strawman.** It knows every rule and the travel times and plans by three
  hand methods; the first habit tried (by opening time only) left one-change shortcuts at up to 0.94.
- **Cheapest insertion is a part of the work.** With every fact right (`insertion_plan`), it reaches 0.42 / 0.39 /
  0.49 at most on the public world but up to 0.79 / 1.01 / 0.77 on world seeds 1–3 (above 0.5 in 13 / 22 / 9 of 39);
  it needs the rules and the travel times, so it is reported in GT.md, not as a shortcut.
- **Names are not a trap.** The request names no file or format; the deliverable's spec goes to the converter, and
  the requirements state `routes.json`, its keys and the 05:00 default.
- **Diagnostics off the public world.** On world seed 1 every diagnostic separates and the best known plan (there
  the reference) is never called not enforced. Every target bites in every tier there but `lateness`, which bites in
  no medium setting and in one hard one: whether reading deliver_by as a firm deadline costs depends on how tight
  the world's windows are.
- **Round 2026-11** (rule seeds 108807, 519122, 904685): before, the nine settings drew C03 or C11, late cost 2,
  shift 09:00, 100 or 110 trays, rush 06:30, habit on in medium and hard; reference and baseline valid, scale 72%
  to 171% wide, literal invalid. Now they draw C03 or C11, 10:00 in easy and medium and 09:00 in hard, 100 or 110
  trays (110 in hard), rush 06:30 and the habit on in medium and hard (108807 and 519122 draw the same hard
  setting). On the public world and world seeds 1–3: reference and baseline valid in all 36, scale 6.5% (public
  hard/s108807) to 56% wide, literal invalid as delivered and with the habit relaxed in all 36.

### Tests

Two tests hard-coded this case's old state and were updated minimally.
`tests/test_validator.py::test_baseline_must_be_valid_and_worse[worse]` plants a baseline in this case's case.py,
which makes the stored audit stale; it now ignores that one problem.
`tests/test_end_to_end.py::test_native_korean_run_scores_reference_as_one` expected no per-target diagnostic
(`enforced` None) and the policy's quality cap of 1.5; the reference is now enforced on every target and the case's
`quality_cap` (1.0) sets its credit.

### Still open

- **The two one-change shortcuts** above (known and open).
- **`lateness` is weak on some worlds**: it bites in 7 of 15 medium and 3 of 15 hard settings here, but in none of
  the medium ones on world seed 1.
- **The hard bound is loose** (11–28%): the model drives every leg at the speed before the rush. An exact model of the
  rush needs a binary per leg.
- **The reference in hard** is the best plan known in all but one hard setting; nothing proves how far it is from
  the optimum there.
- **The scale narrows to 6.5–9.1%** in a few hard settings (hard/s108807 of the round, hard/c1, hard/c12), where the
  dispatcher's plan happens to be good; above the 5% floor, but small differences weigh more there.
- **Receiving windows and district names** (F7), and a native review of the new texts in zh, ko, ja and es
  (requirements, targets, summaries, explainer texts) and of every verdict in CLIENT_REVIEW.md. docs/<lang>/README.md
  and REVIEW.md in those four languages still describe the case before the audit.
- **`leaderboard/anchors-2026-11.json`** holds this case's anchor rows from before the audit; it is outside the case
  directory and has to be regenerated (`fdebench2 anchors`).

### Ground truth audit, second pass (adversarial check)

A second engineer checked the audit above by running code against it: other natural guesses for the literal solution,
the public world against world seeds 1-3, the two waivers, the hard bound, the weak facts, a better never-asks plan, the
baseline and diagnostics on deliverables that are neither reference nor ablation.

**The travel times are guessable (open, waived).** The literal solution guesses the travel times the request never gives
(the straight line, 30 km/h, five minutes a stop), and with that guess its near miss with the closed café known scores
0.00. Other guesses an agent makes as readily do not: over the 39 settings, with the closed café known, the straight
line at 25 km/h and ten minutes a stop reaches 0.86, at 20 km/h and five minutes 0.81, and a planner's textbook guess
(1.3 times the straight line, 25 km/h, five minutes a stop) 0.93, all in easy, where the closed café is the only rule
the literal solution breaks once the tray limit is the racks' 120 (and in some 100- and 110-tray settings whose loads
happen to fit). The cause is general: with every other fact the client states, a planner's uniform guess of the travel
times reaches above 0.5 in most settings of every tier (GT.md, part 5), because the time windows fix most of a plan and
a guess that errs on the slow side only costs some waiting. Each travel fact still bites against its own misreading, so
the five travel targets are kept, but jointly they are guessable. Tried and rejected: a tray limit below the racks in
every setting (the planner's guess still fits 100 or 110 trays in some settings, up to 0.84), the partner cafés read as
V4-only (the same near miss then opens in medium, up to 0.94) and a lower lateness cost (it narrows world seed 3 to
3.1%). What closes it is a travel fact no uniform guess approximates: a prototype in which a river along y = 0 is
crossed only on the bridge by the kitchen held the near miss at 0.48, but `build_world` then drew a new world and the
dispatcher's plan with one café moved reached 0.96 (open in 19 of 39 settings). That is a redesign of the scenario, not
a fix, and is left open: the near miss is now a measured shortcut (`literal_plus_closed_cafe_planner_guess`, open in 6
of 39 settings, at most 0.93; on the round's rule seeds 0.84 and 0.77 in easy) and waived in
`validate.OPEN_AUDIT_FINDINGS`.

**The public world against world seeds 1-3.** The case seed's world is the first usable draw of the generic filter
(nothing in `build_world` looks at shortcuts), but the baseline and the shortcuts were tuned on it, and it is the most
favourable of the four worlds measured:

| | public | world 1 | world 2 | world 3 |
|---|---|---|---|---|
| `habit_best_departures` open (the dispatcher's rounds, timed best) | 2 of 39 (at most 0.67) | 4 (0.75) | 6 (0.64) | 18 (0.70) |
| `habit_one_move` open | 1 (0.53) | 2 (0.73) | 0 (0.50) | 0 (0.45) |
| `literal_plus_closed_cafe_planner_guess` open | 6 (0.93) | 4 (0.72) | 3 (0.69) | 5 (0.99) |
| cheapest insertion with every fact above 0.5 | 0 (0.49) | 13 (0.79) | 22 (1.01) | 9 (0.77) |
| `lateness` bites (medium, hard) | 7/15, 3/15 | 0/15, 1/15 | 0/15, 1/15 | 0/15, 2/15 |
| `tray_limit` bites (easy, medium, hard) | 2/6, 7/10, 4/15 | 2/6, 3/10, 14/15 | 3/6, 0/10, 6/15 | 4/6, 7/10, 7/15 |
| `shift_end` bites (hard) | 1/15 | 5/15 | 3/15 | 5/15 |
| value of asking (easy / medium / hard) | 0.78 / 0.69 / 0.85 | 0.74 / 0.67 / 1.00 | 0.92 / 0.76 / 1.00 | 0.88 / 0.72 / 1.00 |

On world seed 2 the reference is 0.0-2.0% above the proven optimum of the settings checked (easy/c3, medium/c6,
hard/s5), so cheapest insertion's 0.7-0.9 there is not a weak reference: the dispatcher's plan is 31-56% above the
reference in easy on that world and a construction heuristic that knows every fact closes most of the gap. It needs
every fact, so it stays "a part of the work" (GT.md, part 5).

**The hard bound and gap (resolved).** `make_bounds.py` now prices the morning rush exactly: every leg costs its drive
at the speed before the rush plus the extra minutes the rush adds to it, a binary per leg start saying on which side of
the rush it starts (piecewise-linear on each side), with free departures, waiting allowed anywhere and V2's workshop
morning relaxed to "at most three routes leave before 06:40" (proof sketch in its docstring). HiGHS solves every hard
setting to optimality in 10-180 s. The hard bound rises from 11-28% below the reference to 0.1-1.6% below it (easy
0.0-1.2%, medium 0.0-3.2%; every one of the 41 stored settings, the round's included, is now solved to optimality, the
two medium ones the old model left open among them); the model's routes, given to the vans and timed to the minute, beat
the reference in six hard settings (best known quality up to 1.10, hard/c12). `quality_cap` stays 1.0 (median best known
quality 1.000). A reference with more starts (each partner order on V4, cheapest insertion) and more ruin-and-recreate
runs reached the optimum in some of those settings and lost ground in others (the search is path-dependent), so the
reference is unchanged and the stronger plans are stored as best known.

**The two waivers (kept, with a measured reason).** `habit_best_departures` now also re-orders each round for its best
departure (the stronger form of the same one change): it reaches 0.67 in hard/c12 and 0.53 in medium/s13 (the first
form: 0.66 in hard/c12 only), where the reference is within 1.1% and 0.0% of the proven optimum; scored against the best
known plan, hard/c12 would still give it 0.61. `habit_one_move` reaches 0.53 in hard/c1, where the reference is within
0.2% of the proven optimum. Neither can be closed by a stronger reference, and closing them through the baseline narrows
other scales below 5% (the first pass's measurement). On the round's rule seeds `habit_one_move` also reaches 0.56 in
public hard/s904685, a combination the 39 audit settings do not hold, and the habit timing opens on world seeds 1-3
there too (up to 0.75).

**Weak facts.** `shift_end` bites in 1 of 15 public hard settings (5, 3 and 5 of 15 on world seeds 1-3) and `tray_limit`
in 13 of 31 (0 of 10 medium on world seed 2): both are ordered pools, and a stricter guess costs little, so they bite
only where the client's value is the strict end; a later guess is invalid (worst damage 1.00), so both stay targets.
`lateness` bites in 7 of 15 medium and 3 of 15 hard settings on the public world but in no medium setting on any of
world seeds 1-3 (hard: 1, 1 and 2 of 15), and reading `deliver_by` as a hard deadline (a late minute worth a thousand)
bites no more. It stays a target where it bites on the public world; off it, it is close to decorative, and pricing a
late minute at one van minute instead of three (it then bites in 2, 10 and 8 of 15 medium settings on world seeds 1-3)
narrows world seed 3's scale to 3.1%. Open. The binding check passes without the three removed `OPEN_BINDING_FINDINGS`
entries on the public world and world seeds 1-3 (validate-case below); it is weaker than a bite (any other candidate
that changes the reference by 1%, against the least harmful one losing a tenth of the scale), which is why a parameter
can bind and still bite rarely.

**Ablation rewritten.** `service_time` was ablated as "no time at the café", which loses the whole scale everywhere:
sabotage more than a misreading. It is now five minutes at every café whatever its trays (the literal solution's own
guess), which still bites in every tier (easy 8 of 9, medium 14 of 15, hard 10 of 15; damage up to 1.00).

**A better never-asks plan.** `robust_solution` read `deliver_by` as a firm deadline (a late minute ten van minutes).
Reading it as a target but not a wall (five) scores 0.12 better in easy (0.22 against 0.10), 0.02 worse in medium (0.31
against 0.33: another café left out) and the same in hard (0.16), so the solver now reads it that way. Other never-asks
plans do better in a tier by luck the solver cannot see: in hard, a soft reading with C03 left out, the habit kept and
the rush planned at 07:00 reaches 0.31, because V2's round happens to leave at 06:49 (after its workshop morning) and
C03 is the closed café in more of the measured settings. The value of asking is 0.78 / 0.69 / 0.85 (was 0.90 / 0.67 /
0.85); with the luckiest guesses at least 0.67 in every tier.

**Diagnostics on other deliverables.** Correct but different plans on the 39 settings (the reference with V1 and V3
swapped, a longer search from it with other seeds, the stored best plans, cheapest insertion with every fact; 131
plans): none called not enforced, before and after. Misreadings no ablation plans, the reference planner with one fact
read so: (a) the other way round from the ablation (vans at 20 km/h, roads 1.6 times the straight line, ten minutes at
every café, `deliver_by` ignored, the rush from 08:00): before, 7 of the 150 that bite were called not enforced on their
fact (5%), since the regret test compared a plan with its ablation's one misreading only, so a plan misread the other
way looked enforced; (b) misread mildly, in ways no reading lists (23 km/h, 1.4 times the straight line, three minutes
plus 0.3 a tray, a late minute worth 1.5, the rush from 06:15 or 07:45, C07 first by 07:00): 18 of 97 (19%).
`_other_way` now adds, for the diagnostic only, a small grid round the client's value in both directions (road 1.15,
1.45 and 1.6 times the straight line; 20, 22 and 28 km/h; 20 and 25 km/h all morning in hard; no, ten minutes or two
plus 0.4 a tray at a café; `deliver_by` ignored or a late minute worth one; the rush from 06:00 or 08:00), each of which
must explain 60% of a plan's loss (`DIAG_SHARE_OTHER`; at 50% cheapest insertion, late at many cafés in hard/c7, was
half explained by `deliver_by` ignored). After: (a) 150 of 150, (b) 64 of 97 (66%); the C07 demand followed only by
07:00 is still called enforced (its check is the demand itself: first stop, reached by 06:30). A reading under which no
plan keeps the rules is skipped (on world seed 2 it raised). The cost is more cross flags among the travel facts
(warnings).

**Baseline.** The dispatcher's plan is computed as requirements.md says in all five locales: three ways, the cheapest
driven; on the four worlds the opening-order way or the map slices win, never the `deliver_by` way. The one step
requirements.md leaves out (squeezing a café in after moving one café of that round to another) is a fallback, and the
restart the code allows never happens. 1.08 to 1.45 times the reference on the public world, 1.09 to 1.74 on world seeds
1-3: not a strawman.

**Round 2026-11 and the hard pool.** On the public world and world seeds 1-3 the nine round settings keep a valid
reference and baseline, scales 6.5-56% wide and an invalid literal solution, as delivered and with the habit relaxed.
Rule seeds 108807 and 519122 draw the same hard setting by chance (four independent draws, 1 in 54); the hard pool is
not narrow. Any two-value tray limit in hard would separate them (for [100, 110]: 110 and 100), but the hard headline
reference loads at most 100 trays on the public world and 94 on world seed 1, so the tray limit could not bind there and
`build_world` would draw other worlds; widening the rush pool changes the public panel's hard settings. Left as is.

**Also checked.** The agent's view is byte-identical in every setting (validate-case); every number, time and café or
van code in requirements.md, targets.yaml, summary.yaml and explainer.yaml agrees line by line across the five locales
(counted words aside). The two outside tests changed minimally: `test_validator`'s planted baseline makes the stored
audit stale and only that problem is filtered; the Korean end-to-end run expects the case's diagnostic and
`quality_cap`.

**Changes in this pass**: `make_bounds.py` (the exact-rush model, best plans from it), `reference/best_known.json`,
case.py (`_misread` for `service_time`, `_other_way` and `_readings`, `ROBUST_LATE` 5, three shortcuts and the stronger
`habit_best_departures`, `PLANNER_GUESS`, docstrings), `make_gt.py` (the texts above and the guessed-travel table),
`explainer.yaml` shortcut texts in zh, ko, ja and es, `validate.OPEN_AUDIT_FINDINGS` (the new waiver and the two
reasons), and the regenerated GT.md, audit.json, dataset and pages.

**Open after this pass.** Resolved from the first pass's list: the loose hard bound and the unproven hard gap. Still
open: the guessable travel times (waived: a travel fact no uniform guess approximates, with a new world and a re-tuned
dispatcher, would close it); the two habit shortcuts (waived; they open in more settings on world seeds 1-3);
`lateness`, close to decorative off the public world; the never-asks credit, which rests on luck the solver cannot see
(which café the measured settings leave out, when V2's round happens to leave); a native review of the new shortcut
texts in zh, ko, ja and es; `leaderboard/anchors-2026-11.json`, still from before the audit.
