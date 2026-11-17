# Ground truth — customer_service/callcenter_workforce_planner

The ground truth of every setting in five parts: the client facts the agent must learn, the validity checks, the objective, the reference with its bounds, and the diagnostic cases. Every table is generated from `dataset/audit.json` by `make_gt.py` (world seed 20261109; per tier the public panel and 12 admissible combinations of the tier's candidates: easy 15, medium 15, hard 15 settings). Credit is 0 for an invalid deliverable, else quality clipped to [0, 1]; damage = 1 − credit. A fact bites in a setting when misreading it loses at least 0.1 of credit (for a parameter: the other candidate's reference, an agent that guesses wrong but sensibly).

## 1. Client facts

One row per target (`locales/en/targets.yaml`). *Ablated as*: a parameter is read as the other candidate of its tier (the reference of that candidate, scored here); any other fact as the reference planner with its most natural misreading (the reference itself where that roster is valid and no worse by the misreading). *Damage*: min–max over the settings where it is in force.

| target | fact | in force | ablated as | damage | bites | diagnostic |
|---|---|---|---|---|---|---|
| `one_language` | An agent takes calls in only one language for the whole shift (one of their skills); a bilingual agent never counts for two languages at once. | easy, medium, hard | a bilingual agent on shift counts on each of their languages at once | 0.463–1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `understaffing_price` | A missing agent costs {{under_weight}} per half-hour slot and language, in the units of the hourly rates (the client's estimate of abandoned calls, callbacks and missed service levels); the roster is judged on that plus the labor cost of all shifts, and lower is better. | easy, medium, hard | the other candidate of `under_weight` | 0.002–0.216 | easy 12/15, medium 11/15, hard 9/15 | separates |
| `ft_contract_week` | A full-timer's contract week is {{ft_week_hours}} hours, that is {{ft_regular_shifts}} shifts<!-- tier: easy -->, and nobody works beyond it this round<!-- /tier --><!-- tier: medium hard -->. Overtime is not planned: one shift beyond it (paid 1.5 times) needs the operations manager's approval<!-- /tier -->. | easy, medium, hard | the other candidate of `ft_week_hours` | 0.041–1.000 | easy 11/15, medium 12/15, hard 11/15 | separates |
| `pt_contract_week` | A part-timer's contract is {{pt_week_hours}} hours a week, at most {{pt_max_shifts}} shifts, with no overtime; those hours are guaranteed (paid in full even if fewer shifts are rostered). | easy, medium, hard | the other candidate of `pt_week_hours` | 0.051–1.000 | easy 14/15, medium 13/15, hard 14/15 | separates |
| `min_rest` | There must be at least {{min_rest}} hours of rest between the end of one shift and the start of the next shift of the same agent. | easy, medium, hard | the other candidate of `min_rest` | 0.000–1.000 | easy 6/15, medium 5/15, hard 7/15 | separates |
| `holiday` | {{holiday_day}} is a regional public holiday in the client's main market; the demand for that day is {{holiday_factor}} of the forecast, rounded up, and the forecast file was not updated for it. | easy, medium, hard | the forecast file as it is: no day cut | 0.032–0.214 | easy 10/15, medium 9/15, hard 9/15 | separates |
| `training_salary` | New hires are on a training salary: their whole contract week ({{ft_regular_shifts}} shifts) is paid whether or not they are on the phones, so leaving a new hire's shift off the roster saves nothing. | easy, medium, hard | a new hire paid by the shift like everyone else in labor_cost.csv | 0.000–0.329 | easy 1/15, medium 5/15, hard 9/15 | separates |
| `buddy_rule` | A new hire must never be alone on a language; in every half-hour slot they work, at least one non-new agent is on the same language. | medium, hard | new hires rostered like everyone else | 1.000 | medium 15/15, hard 15/15 | separates |
| `sick_call` | The team lead's note is out of date; on Friday morning the client received the doctor's certificate of the agent it names, who is off sick up to and including {{sick_until}} and must not be rostered before then, whatever the note says. | hard | the team lead's note followed: the agent rostered as usual | 0.000–1.000 | hard 12/15 | separates |

Facts the client states that are not targets (they stay in requirements.md as context, or are rules the agent can read off its own data): that the forecast is already in agents per half-hour slot (the column is `agents_needed` per `slot_start`), the shift types per contract (`shifts.csv` has a `contract` column), the leave file's day/month/year dates (read as day/month, every request falls inside the week asked for, 9 to 12 November; read as month/day, they would spread from September to December, and the one request that reads the same either way, 11/11, is inside it too) and that a rejected request is not leave (its `status` says `rejected`). A careful agent infers each of these from the data in every setting, so asking for them is not scored (REVIEW.md, Ground truth audit). The old `easy_scope` and `one_shift_a_day` targets went with the rules they described: the rest time now applies in every tier, and overtime is out of easy's scope by the contract week itself. `overtime_approval` is part of `ft_contract_week` from medium (the client states the cap and the approval in one breath, and a roster cannot tell the two misreadings apart); the rule `overtime_approval` stays.

## 2. Validity checks

Every rule of case.yaml is a hard gate (`physical` and `contractual` never bend; `business_policy` bends only through the company policy's exception path).

| rule | class | tiers | why it is a hard gate |
|---|---|---|---|
| `skill_valid` | physical | easy, medium, hard | an agent cannot take calls in a language they do not speak |
| `shift_type` | contractual | easy, medium, hard | the contracts fix the shift length |
| `max_shifts` | contractual | easy, medium, hard | the contract weeks: nobody is paid or scheduled beyond them (from medium, one approved overtime shift more for a full-timer) |
| `min_rest` | contractual | easy, medium, hard | the labor agreement's rest time (11 h is the EU minimum, 13 h a stricter company agreement) |
| `leave_respected` | contractual | easy, medium, hard | approved leave cannot be taken back |
| `overtime_approval` | business_policy | medium, hard | a business policy: the operations manager approves each overtime shift; an approved exception can bend it, and with the 1.5 times premium that pays only where a missing agent is dear |
| `buddy_rule` | contractual | medium, hard | the training agreement: a new hire is never alone on a language (contractual since the audit; it was a bendable habit) |
| `sick_leave` | contractual | hard | a doctor's certificate: the agent is not fit to work |

## 3. Objective

objective = `under_weight` × the under-covered agent-slots + the labor cost (minimize).

- **Under-covered agent-slots**: per day, half-hour slot and language, the forecast's agents needed (on the holiday `holiday_factor` of it, rounded up) minus the agents assigned to that language in that slot, when positive. An agent counts in one language only, in every slot of their shift.
- **Labor cost**: hours × rate (22 full-time, 18 part-time) for every shift worked; a part-timer's contract week (guaranteed hours) and a new hire's (training salary) are paid in full even when fewer of their shifts are rostered; a full-timer's shift beyond the contract week (possible from medium, only with an approved exception) at 1.5 times.
- **Uncertainty**: none in the objective; the forecast is the client's planning figure. The uncertain part of the case is the client's facts, above all in hard the sick call that contradicts the team lead's note.
- The baseline (the client's own way: the supervisor's fixed rota, one shift all week in the main language, every experienced agent their contract week, new hires shadowing a senior) anchors quality 0 and the reference quality 1.

## 4. Reference and bounds

- **Reference** (`reference_solution`, `_Planner`): each agent's week is re-planned exactly given everyone else's, a dynamic program over the seven days (shift and language each day, within the contract week and the rest time, a new hire only beside an experienced colleague of the same language), agents in turn until no week improves; then every pair of agents who share a language is taken off and re-planned together (an experienced agent and a new hire also with the first planning for both) while that lowers the objective. No overtime shift (the policy is not bent). Deterministic, 1–10 s per setting.
- **Best known** (`best_known_solution`): the exact optimum of the same model, a mixed-integer program solved by HiGHS (scipy) to proven optimality (time limit 300 s, never reached in the audit).
- **Bound** (`objective_bound`, proven): the MILP's dual bound. Its scope is every roster that keeps every rule, the overtime approval included: a roster with an approved overtime exception can end below it (section Bending in REVIEW.md).

| setting | reference | baseline | span | best known | best known quality | bound | gap (reference − bound) / reference |
|---|---|---|---|---|---|---|---|
| easy/s10 | 22060 | 41958 | 0.902 | 21660 | 1.020 | 21660 | 0.018 |
| easy/s2 | 21810 | 39708 | 0.821 | 21210 | 1.034 | 21210 | 0.028 |
| easy/s11 | 18980 | 27030 | 0.424 | 18862 | 1.015 | 18862 | 0.006 |
| easy/c1 | 25290 | 42938 | 0.698 | 24840 | 1.025 | 24840 | 0.018 |
| easy/c2 | 19202 | 24949 | 0.299 | 19124 | 1.014 | 19124 | 0.004 |
| easy/c3 | 19249 | 26599 | 0.382 | 19193 | 1.008 | 19193 | 0.003 |
| easy/c4 | 22710 | 40458 | 0.782 | 21960 | 1.042 | 21960 | 0.033 |
| easy/c5 | 20906 | 40758 | 0.950 | 20456 | 1.023 | 20456 | 0.022 |
| easy/c6 | 21250 | 40278 | 0.895 | 20700 | 1.029 | 20700 | 0.026 |
| easy/c7 | 19049 | 27030 | 0.419 | 18862 | 1.023 | 18862 | 0.010 |
| easy/c8 | 25140 | 42538 | 0.692 | 24740 | 1.023 | 24740 | 0.016 |
| easy/c9 | 18549 | 26945 | 0.453 | 18408 | 1.017 | 18408 | 0.008 |
| easy/c10 | 23810 | 42008 | 0.764 | 23210 | 1.033 | 23210 | 0.025 |
| easy/c11 | 18771 | 25000 | 0.332 | 18710 | 1.010 | 18710 | 0.003 |
| easy/c12 | 18772 | 26667 | 0.421 | 18631 | 1.018 | 18631 | 0.008 |
| medium/s10 | 23784 | 41958 | 0.764 | 21860 | 1.106 | 21860 | 0.081 |
| medium/s2 | 22832 | 39708 | 0.739 | 21660 | 1.069 | 21660 | 0.051 |
| medium/s11 | 19584 | 27030 | 0.380 | 19185 | 1.054 | 19185 | 0.020 |
| medium/c1 | 19488 | 26979 | 0.384 | 19151 | 1.045 | 19151 | 0.017 |
| medium/c2 | 22202 | 40728 | 0.834 | 20976 | 1.066 | 20976 | 0.055 |
| medium/c3 | 24990 | 42088 | 0.684 | 23690 | 1.076 | 23690 | 0.052 |
| medium/c4 | 19758 | 24813 | 0.256 | 19419 | 1.067 | 19419 | 0.017 |
| medium/c5 | 23410 | 40458 | 0.728 | 22160 | 1.073 | 22160 | 0.053 |
| medium/c6 | 19610 | 25085 | 0.279 | 19317 | 1.054 | 19317 | 0.015 |
| medium/c7 | 19231 | 27251 | 0.417 | 18992 | 1.030 | 18992 | 0.012 |
| medium/c8 | 22856 | 39708 | 0.737 | 21660 | 1.071 | 21660 | 0.052 |
| medium/c9 | 21700 | 41078 | 0.893 | 20726 | 1.050 | 20726 | 0.045 |
| medium/c10 | 26090 | 41438 | 0.588 | 24340 | 1.114 | 24340 | 0.067 |
| medium/c11 | 24734 | 41208 | 0.666 | 23260 | 1.089 | 23260 | 0.060 |
| medium/c12 | 22982 | 41108 | 0.789 | 21760 | 1.067 | 21760 | 0.053 |
| hard/s10 | 23908 | 43704 | 0.828 | 22134 | 1.090 | 22134 | 0.074 |
| hard/s2 | 24104 | 41678 | 0.729 | 22532 | 1.089 | 22532 | 0.065 |
| hard/s11 | 19544 | 27369 | 0.400 | 19185 | 1.046 | 19185 | 0.018 |
| hard/c1 | 23584 | 42904 | 0.819 | 22434 | 1.060 | 22434 | 0.049 |
| hard/c2 | 19791 | 25350 | 0.281 | 19345 | 1.080 | 19345 | 0.023 |
| hard/c3 | 19594 | 27607 | 0.409 | 19304 | 1.036 | 19304 | 0.015 |
| hard/c4 | 19783 | 26462 | 0.338 | 19624 | 1.024 | 19624 | 0.008 |
| hard/c5 | 19135 | 26995 | 0.411 | 18822 | 1.040 | 18822 | 0.016 |
| hard/c6 | 19059 | 25362 | 0.331 | 18646 | 1.066 | 18646 | 0.022 |
| hard/c7 | 19462 | 25339 | 0.302 | 19060 | 1.068 | 19060 | 0.021 |
| hard/c8 | 19155 | 25186 | 0.315 | 18725 | 1.071 | 18725 | 0.022 |
| hard/c9 | 19662 | 26893 | 0.368 | 19287 | 1.052 | 19287 | 0.019 |
| hard/c10 | 24208 | 44304 | 0.830 | 22908 | 1.065 | 22908 | 0.054 |
| hard/c11 | 19145 | 25101 | 0.311 | 18761 | 1.064 | 18761 | 0.020 |
| hard/c12 | 22776 | 41050 | 0.802 | 21352 | 1.078 | 21352 | 0.063 |

The best known solution reaches 1.008–1.114 on the quality scale (median 1.052); the reference is 0.3%–8.1% above the bound. **quality_cap** = 1.06: the median best known quality over the measured settings, rounded up to the next 0.01 (full credit at the best known; DESIGN.md, Ground truth audit).

**Value of asking** (never asks = `robust_solution`: the strictest candidate of every rule (the shorter contract weeks, the longer rest, from medium the buddy rule, in hard the latest sick day), no overtime, and the exact optimum of the expected objective over every price, holiday day and holiday share of the tier's pools, a stochastic MILP; every shift read as paid by the hour, as the view suggests; never asks (params) = the best single setting's reference or the baseline, which know every fixed fact):

| tier | never asks (credit) | its validity rate | voi | never asks (params) | voi_params |
|---|---|---|---|---|---|
| easy | 0.767 | 1.000 | 0.233 | 0.748 | 0.252 |
| medium | 0.778 | 1.000 | 0.222 | 0.644 | 0.356 |
| hard | 0.749 | 1.000 | 0.251 | 0.550 | 0.450 |

## 5. Diagnostic cases

`diagnose()` returns `enforced` and `evidence` per target from the roster `score()` parsed. A fact that is a rule is read off the rule (a part-timer or full-timer above the contract week, two shifts closer than the rest time, an overtime shift, a new hire alone, the sick agent on a sick day). Every other fact, and a contract week or rest time that is kept, is measured against each other reading (the other candidate of the parameter, or the natural misreading; for the holiday also the cut on each other candidate day): the roster *follows* that reading when it loses at least 5% of the quality scale against the reference, keeps that reading's rules, and is closer to the reference planner's roster under that reading than to the true one's (by at least 5% of the scale and with at most half the distance). A roster at least as good as the reference never follows another reading. *Separates*: the reference is enforced in every measured setting and every ablation that bites is not.

| target | not enforced when | reference enforced | ablations |
|---|---|---|---|
| `one_language` | follows the double-counting reading (see below) | yes | separates |
| `understaffing_price` | follows the other price of a missing agent | yes | separates |
| `ft_contract_week` | a full-timer above the contract week (from medium: beyond it without the approval), or follows the other contract week | yes | separates |
| `pt_contract_week` | a part-timer above the contract week, or follows the other contract week | yes | separates |
| `min_rest` | two shifts closer than the rest time, or follows the other rest time | yes | separates |
| `holiday` | follows the uncut forecast, or the cut on another candidate day | yes | separates |
| `training_salary` | follows the reading where new hires are paid by the shift | yes | separates |
| `buddy_rule` | a new hire alone on a language (none when no new hire is rostered) | yes | separates |
| `sick_call` | the note's agent rostered on a certified sick day (none when that agent is not rostered at all) | yes | separates |

**Reliability on other deliverables** (a run's deliverable is neither the reference nor an ablation). Settings where the diagnostic calls the deliverable not enforced, of those where it gives a True or False: the best known solution (valid, built with full knowledge of its setting, so every one would be a false negative), the ablation of the target that also calls other targets not enforced (of the settings where it bites; facts can interact), and the baseline (each setting's own) and `robust_solution` (its tier's), which are informational: neither is built with full knowledge.

| target | best known | cross flags | baseline | robust_solution |
|---|---|---|---|---|
| `one_language` | 0/45 | 37/45 (`understaffing_price`, `buddy_rule`) | 0/45 | 0/45 |
| `understaffing_price` | 0/45 | 0/32 | 23/45 | 21/45 |
| `ft_contract_week` | 0/45 | 11/34 (`understaffing_price`, `training_salary`) | 0/45 | 8/45 |
| `pt_contract_week` | 0/45 | 6/41 (`understaffing_price`) | 0/45 | 11/45 |
| `min_rest` | 0/45 | 0/18 | 0/45 | 0/45 |
| `holiday` | 0/45 | 9/28 (`understaffing_price`) | 0/45 | 11/45 |
| `training_salary` | 0/45 | 0/15 | 0/45 | 0/45 |
| `buddy_rule` | 0/30 | 0/30 | 0/30 | 0/30 |
| `sick_call` | 0/15 | 0/12 | 0/8 | 0/15 |

`diagnose()` raised in 0 evaluation(s) of the audit.

**Shortcuts** (closed: invalid, or quality at most 0.5):

| shortcut | what it does | closed in | best quality where valid |
|---|---|---|---|
| `one_shift` | The rules kept minimally: a single shift (the first agent, their first shift and language). | 45/45 | 0.000 |
| `fixed_rota` | The client's own fixed rota copied (the baseline). | 45/45 | 0.000 |
| `fixed_rota_no_new_hires` | The fixed rota with one change: new hires stay off the phones. | 45/45 | 0.000 |
| `fixed_rota_peak` | The fixed rota with one change: everyone on the 10:00 (full-time) or 12:00 (part-time) shift. | 45/45 | 0.000 |
| `same_shift_all_week` | Constants: every experienced agent on their contract's first shift and language, from Monday on. | 45/45 | 0.000 |
| `part_timers_only` | The objective's arithmetic: only part-timers, the cheapest per half-hour (the planner, no full-timers). | 45/45 | 0.000 |
| `one_day_only` | A partial roster: the planner's roster for Monday alone, nobody on the other six days. | 45/45 | 0.000 |
| `weekdays_only` | A partial roster: the planner's roster for Monday to Friday, nobody at the weekend. | 32/45 | 0.586 |
| `no_new_hires` | The buddy rule kept vacuously: the planner's roster with the new hires taken off the phones. | 44/45 | 0.515 |
| `one_shift_each` | The rules kept minimally: the planner with one shift a week for every agent. | 45/45 | 0.000 |
| `literal_plus_max_shifts` | The literal solution plus one rule: the request as written, with the weekly caps of both contracts kept. | 45/45 | – |
| `literal_plus_min_rest` | The literal solution plus one rule: the request as written, with the rest time between two shifts kept. | 45/45 | – |
| `literal_plus_buddy_rule` | The literal solution plus one rule: the request as written, with no new hire alone on a language kept. | 30/30 | – |
| `literal_plus_overtime_approval` | The literal solution plus one rule: the request as written, with no shift beyond the full-time contract week kept. | 15/15 | – |
| `literal_plus_sick_leave` | The literal solution plus one rule: the request as written, with the certified sick days kept. | 15/15 | – |

**Findings** (as validate-case reads the stored audit with this quality_cap; OPEN_AUDIT_FINDINGS may waive a problem):

- problem: shortcut (2): weekdays_only, no_new_hires
- warning: few_bites (2): min_rest, training_salary
- warning: the ablation of target one_language also calls other targets not enforced in 37 of the 45 settings where it bites: understaffing_price (13), buddy_rule (24) (e.g. easy/s10)
- warning: voi_low (3): easy, medium, hard
