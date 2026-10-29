# Call-Center Workforce Planner — `customer_service/callcenter_workforce_planner`

A multilingual customer-support center asks the agent for next week's roster (Monday 9 to Sunday 15 November
2026) for its support team: "enough people on the phones so customers aren't left waiting, in every language
we support". The center takes calls in Korean, Japanese, English, Chinese and Spanish, 08:00–22:00 every day.
The deliverable is `roster.json` (`{"assignments": [{"agent", "day", "shift", "language"}, ...]}`), one entry
per agent per shift worked. The setting is country-neutral: no national labor law applies beyond the rules the
client states, and the hourly rates carry no currency.

The case has **no settings**: the same problem, rules and ground truth at every difficulty. The engagement
knobs (full spec vs. clarify first, client persona, data noise, events) apply on top, as for every case (see
[cases/README.md](../../README.md)).

## Data

| File (en) | Content |
|---|---|
| `agents.xlsx` | Sheet `staff`: 30 agents with `contract` (20 full-time, 10 part-time) and `new_hire` (4, all full-time). Sheet `skills`: one row per agent and language (the first row is the agent's main language) |
| `call_forecast.csv` | `agents_needed` per day, half-hour slot (08:00–21:30) and language: 980 rows, 1–5 agents each, already converted from calls to people |
| `leave.csv` | 5 leave requests, `from` / `to` written day/month/year, `status` approved or rejected |
| `shifts.csv` | Four 8-hour full-time shifts (S0800, S1000, S1200, S1400) and four 4-hour part-time shifts (P0800, P1200, P1600, P1800) |
| `labor_cost.csv` | Hourly rate per contract: 22.0 full-time, 18.0 part-time |

File, sheet and column names and the categorical labels are localized (a Korean client sends
`고객센터_상담원명단.xlsx` with `고용형태 = 풀타임`); IDs, codes and numbers are not.

## Rules

| Rule | Class | What it says |
|---|---|---|
| `skill_valid` | physical | An agent takes calls only in a language among their skills (one language for the whole shift) |
| `min_rest` | physical | At least 11 hours between two shifts of the same agent (so at most one a day) |
| `shift_type` | contractual | Full-timers only 8-hour shifts, part-timers only 4-hour shifts |
| `max_shifts` | contractual | At most 5 shifts a week for a full-timer, 3 for a part-timer |
| `leave_respected` | contractual | Nobody on a day of approved leave |
| `buddy_rule` | business policy (bendable) | While a new hire is on the phones, at least one non-new agent is on the same language in every slot |

**Objective (minimize):** 40 per missing agent per half-hour slot and language (the forecast, with Wednesday
at 60% rounded up, minus the agents assigned) plus the labor cost of all shifts (hours × rate, a full-timer's
5th shift of the week at 1.5×). The client explains the 40 as its estimate, in the same units as the rates, of
what one agent missing for half an hour costs in abandoned calls, callbacks and missed service levels.

## Hidden facts (9 clarification targets)

`one_language` (a bilingual agent counts for one language only), `slot_coverage` (the forecast is already in
people, checked per half-hour slot), `holiday_wednesday` (11 November is a regional public holiday in the
client's main market: 60% of the forecast, rounded up; the file was not updated), `contract_limits`,
`min_rest`, `leave_dates` (day/month/year, both ends included, rejected requests are not leave), `overtime`
(4 regular shifts, the 5th at 1.5×), `buddy_rule`, `understaffing_penalty` (the 40 and the cost model).

## Situations present

- **Hidden facts that decide validity:** the rest rule (an optimizer that does not know it produces 13
  `min_rest` violations at this seed), the contract shift types and caps, one language per shift, and the leave
  file (read as month/day, A20's day off on Monday 9 November becomes 11 September, and the other ranges
  stretch over months).
- **Hidden facts that only move quality:** the holiday (Wednesday demand 265 → 229 agent-slots), the overtime
  premium and the under-staffing weight.
- **Data traps:** day/month/year dates (no day above 12 at this seed), a rejected leave request (A03), a
  forecast not updated for the holiday.
- **Bendable rule:** `buddy_rule`. At the optimum, bending it gains 0.58% of the objective.
- **No pressure note or dated event** in the case itself; only the generic `messy` engagement events.

## Reference, baseline and optimum (seed 20261109)

The **reference** is a greedy: it repeatedly adds the (agent, day, shift, language) with the largest gain,
40 per still-uncovered slot minus the shift's pay (with the overtime premium), honoring every rule and
preferring senior agents so that new hires find buddies later. The **baseline** is the supervisor's fixed rota
drawn up without the forecast: every senior agent works one shift all week in their main language, full-timers
their 4 regular days and part-timers 3, on consecutive days from a start staggered within their language and
contract; leave days are left empty, and each new hire shadows a senior full-timer of their language (same
days, same shift). Quality is normalized: baseline 0, reference 1.

| Roster | Objective | Under-covered agent-slots | Labor cost | Shifts | Ratio to reference | Normalized quality |
|---|---|---|---|---|---|---|
| Baseline (fixed rota) | 37,376 | 554 | 15,216 | 103 | 0.685 | 0 |
| Reference (greedy) | 25,584 | 183 | 18,264 | 116 | 1 | 1 |
| Optimum (MILP) | 23,464 | 75 | 20,464 | 126 | 1.090 | 1.180 |
| Optimum ignoring the holiday | 23,872 | | | | 1.072 | 1.145 |
| Optimum ignoring overtime, or with the weight unknown | 23,560 | | | | 1.086 | 1.172 |
| Optimum without the buddy rule (valid only if bent) | 23,328 | | | | 1.097 | 1.191 |
| One shift only (A01, Monday, S0800, en) | 67,656 | | | 1 | 0.378 | 0 (floored) |

The optimum is the known ceiling: an exact MILP of the same model (about 2,000 binaries) solved with scipy's
HiGHS in about 8 seconds, to proven optimality, and checked with `case.py`'s own evaluator. It is an analysis
script, not part of the case (scipy is not a dependency). Under the default policy cap of 1.5 the reference
earns 0.67 of the quality component and the optimum 0.79; `case.yaml` sets no `quality_cap` (see REVIEW.md,
F1).

World seeds 1–3 (validated by default):

| World seed | Baseline | Reference | Optimum | Optimum's normalized quality |
|---|---|---|---|---|
| 1 | 36,776 | 25,232 | 23,672 | 1.135 |
| 2 | 36,936 | 25,336 | 23,544 | 1.155 |
| 3 | 37,848 | 25,440 | 23,248 | 1.177 |

## Notes

- Synthetic: names, skills, forecast, leave and rates are generated from the seed; the shift pattern and the
  rules are design choices, not one center's practice.
- Simplifications: the forecast is already in agents (no calls, handling time or Erlang C step), shifts count
  in every slot with no breaks, a full-timer's normal week is 4 shifts (32 hours), and 11 hours of rest is the
  EU minimum but below Spain's 12. Names are Latin-script in every locale and are not tied to the agent's
  languages.
- The leave dates are day/month/year in every locale. At this seed no date has a day above 12, but in other
  world seeds approved leave on Friday to Sunday shows 13–15 (seeds 1 and 3).
- `validate-case` checks the case on its seed and world seeds 1–3: deterministic data in five locales, the
  reference valid at quality 1, the baseline valid and worse, and one roster per rule that breaks only that
  rule.
