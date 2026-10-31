# Call-Center Workforce Planner — `customer_service/callcenter_workforce_planner`

A multilingual customer-support center asks the agent for next week's roster (Monday 9 to Sunday 15 November
2026) for its support team: "enough people on the phones so customers aren't left waiting, in every language
we support". The center takes calls in Korean, Japanese, English, Chinese and Spanish, 08:00–22:00 every day.
The deliverable is `roster.json` (`{"assignments": [{"agent", "day", "shift", "language"}, ...]}`), one entry
per agent per shift worked. The setting is country-neutral: no national labor law applies beyond the rules the
client states, and the hourly rates carry no currency.

## Settings: three tiers × rule seeds

The case has settings (DESIGN.md, Settings): a setting is a tier and a rule seed. **The agent sees the same
request and the same data in every setting** (the validator checks that its prompt and workspace are
byte-identical). The tier decides which rules apply; the rule seed draws the client's numbers (how much a
missing agent costs, the contract week, the holiday's share, the rest hours, the end of a sick leave) from
candidate pools. The simulated client answers from the hidden requirements of the setting and the evaluator
scores under it, so the agent has to find out from the client which rules and numbers apply this time. The
engagement knobs (full spec vs. clarify first, client persona, data noise, events) apply on top, as for every
case (see [cases/README.md](../../README.md)).

| Tier | What applies |
|---|---|
| easy | The core staffing problem: one language per agent per shift (one of their skills), full-timers on 8-hour and part-timers on 4-hour shifts within their weekly caps, at most one shift a day, approved leave (dates day/month/year, rejected requests are not leave), and the under-staffing weight. The client says what is out of scope this round: the forecast is used as it is every day, every shift is costed at the plain rate, rest times are checked on the floor, new hires are rostered like anyone else, and the agent in the team lead's note is back on Monday. |
| medium | Easy plus the rest time between two shifts (`min_rest`), the regional holiday on Wednesday 11 November (a share of the forecast, rounded up), overtime beyond the full-time contract week (1.5 times the rate), and the new-hire buddy habit (`buddy_rule`). The agent in the team lead's note is back on Monday. |
| hard | Medium plus a dated sick call and the team lead's pressure: the note in the data (Thursday 5 November) says the agent it names "will be fine by Monday, just roster them as usual"; the client received that agent's doctor's certificate on Friday morning, which keeps them off sick up to a drawn day (`sick_leave`). |

### Parameters

Each parameter is drawn on its own from its pool in the tier (case.yaml `params:`). A pool of one value means
the rule does not apply in that tier; the code ignores the value there.

| Parameter | easy | medium | hard | What it changes |
|---|---|---|---|---|
| `under_weight` | 15, 25, 40 | 15, 25, 40 | 15, 25, 40 | The cost of one missing agent per half-hour slot and language, in the units of the hourly rates (22 full-time, 18 part-time): how many shifts pay for themselves. At 15 a full-time shift needs 12 of its 16 slots to fill a gap, at 40 five. |
| `ft_week_hours` | 32, 40 | 32, 40 | 32, 40 | The full-time contract week. Derived: `ft_regular_shifts` = 4 or 5 and `ft_max_shifts` = 5 or 6 (one shift more, as overtime, is the weekly cap). Easy uses the cap; medium and hard also pay the shift beyond the contract week at 1.5×. |
| `holiday_factor` | 1.0 (no cut) | 0.5, 0.6, 0.75 | 0.5, 0.6, 0.75 | Wednesday's demand is this share of the forecast, rounded up: 176, 229 or 255 agent-slots instead of 265. |
| `min_rest` | 0 (one shift a day only) | 11, 13 | 11, 13 | Hours of rest between two shifts of an agent. 11 forbids a late shift (ending 22:00) followed by an 08:00 start; 13 also forbids the 12-hour turnarounds (S1400 → S1000, S1200 → S0800, P1600 → P0800). 12 h would forbid the same pairs as 11 h, so it is not a candidate. |
| `sick_until` | 2026-11-08 (back Monday) | 2026-11-08 (back Monday) | 2026-11-10, 2026-11-11, 2026-11-12 | The last day of the doctor's certificate of the agent in the team lead's note: off sick from Monday to Tuesday, Wednesday or Thursday. |

The agent in the note is derived from the world, not drawn: the experienced full-timer with no leave request
whose main language has the fewest experienced speakers (A08, Chinese, at the public seed; A05, A02 and A08 on
world seeds 1–3). The requirements never name them; they point to the note.

### Public panel (`rule_seeds: [10, 2, 3]`)

The panel shows every candidate of every pool. Seed 10 comes first: it is the default seed of a single run and
the setting of the validator's binding check. Objectives at the public world seed 20261109 (lower is better);
"Optimum" is an exact MILP of the same model (see below).

| Setting | Drawn parameters | Baseline | Reference | Optimum | Reference: under-covered agent-slots, labor cost, shifts | Optimum's normalized quality |
|---|---|---|---|---|---|---|
| easy/s10 | weight 40, 32 h (cap 5) | 38,176 | 23,488 | 22,360 | 102, 19,408, 128 | 1.077 |
| easy/s2 | weight 25, 40 h (cap 6) | 30,061 | 22,075 | 21,330 | 163, 18,000, 120 | 1.093 |
| easy/s3 | weight 15, 32 h (cap 5) | 23,826 | 20,047 | 19,952 | 289, 15,712, 107 | 1.025 |
| medium/s10 | weight 40, 32 h, holiday 50%, rest 11 h | 36,216 | 24,288 | 22,472 | 155, 18,088, 115 | 1.152 |
| medium/s2 | weight 25, 40 h, holiday 60%, rest 13 h | 29,611 | 22,197 | 20,928 | 189, 17,472, 116 | 1.171 |
| medium/s3 | weight 15, 32 h, holiday 75%, rest 11 h | 23,766 | 20,443 | 19,919 | 421, 14,128, 98 | 1.158 |
| hard/s10 | weight 40, 32 h, holiday 50%, rest 11 h, sick to Wed 11 | 37,240 | 24,280 | 22,552 | 157, 18,000, 115 | 1.133 |
| hard/s2 | weight 25, 40 h, holiday 60%, rest 13 h, sick to Thu 12 | 29,678 | 22,297 | 21,066 | 193, 17,472, 116 | 1.167 |
| hard/s3 | weight 15, 32 h, holiday 75%, rest 11 h, sick to Tue 10 | 23,722 | 20,458 | 19,919 | 422, 14,128, 98 | 1.165 |

The drawn values of each public setting are stored in `dataset/gt/<tier>_s<seed>/setting.json` (with the
derived `ft_regular_shifts` and `ft_max_shifts`). Any other rule seed is a private seed: a fresh draw of the
same pools.

**Every parameter binds** (validator, hard/s10, the first change of each parameter that binds): `under_weight`
40 → 15 moves the reference's objective by −16.2%; `ft_week_hours` 32 → 40 by −3.6% (the 5th shift is no
longer overtime); `holiday_factor` 0.5 → 0.6 by +7.1%; `min_rest` 11 → 13 makes the reference invalid; and
`sick_until` Wednesday → Thursday makes it invalid (Tuesday leaves it valid and the objective unchanged). The
same holds on world seeds 1–3. A rule seed's reference is invalid or worse under the other public seeds of its
tier: invalid in 11 of the 18 cross pairs (a 6-shift week under a 5-shift cap, 12-hour turnarounds under 13 h of
rest, the sick agent on a sick day), quality ratio 0.82–0.96 (normalized 0.56–0.89) in six, and in one pair
(easy, seed 10's reference under seed 2) 0.5% better than seed 2's own greedy.

## Data (the same in every setting)

| File (en) | Content |
|---|---|
| `agents.xlsx` | Sheet `staff`: 30 agents with `contract` (20 full-time, 10 part-time) and `new_hire` (4, all full-time). Sheet `skills`: one row per agent and language (the first row is the agent's main language) |
| `call_forecast.csv` | `agents_needed` per day, half-hour slot (08:00–21:30) and language: 980 rows, 1–5 agents each, already converted from calls to people |
| `leave.csv` | 5 leave requests, `from` / `to` written day/month/year, `status` approved or rejected |
| `shifts.csv` | Four 8-hour full-time shifts (S0800, S1000, S1200, S1400) and four 4-hour part-time shifts (P0800, P1200, P1600, P1800) |
| `labor_cost.csv` | Hourly rate per contract: 22.0 full-time, 18.0 part-time |
| `team_lead_note.txt` | A message from the team lead of the sick agent's main language, sent Thursday 5 November 17:40: the agent "has been off sick since Wednesday with the flu ... they'll be fine by Monday. Please just roster them as usual next week" |

File, sheet and column names and the categorical labels are localized (a Korean client sends
`고객센터_상담원명단.xlsx` with `고용형태 = 풀타임` and `팀장_메모.txt`); IDs, codes and numbers are not.

## Rules

| Rule | Class | Tiers | What it says |
|---|---|---|---|
| `skill_valid` | physical | all | An agent takes calls only in a language among their skills (one language for the whole shift) |
| `one_shift_a_day` | contractual | easy | At most one shift a day per agent |
| `min_rest` | contractual | medium, hard | At least `min_rest` hours between two shifts of the same agent (so at most one a day) |
| `shift_type` | contractual | all | Full-timers only 8-hour shifts, part-timers only 4-hour shifts |
| `max_shifts` | contractual | all | At most `ft_max_shifts` (5 or 6) shifts a week for a full-timer, 3 for a part-timer |
| `leave_respected` | contractual | all | Nobody on a day of approved leave |
| `sick_leave` | contractual | hard | The agent in the team lead's note is not rostered on any day up to `sick_until` |
| `buddy_rule` | business policy (bendable) | medium, hard | While a new hire is on the phones, at least one non-new agent is on the same language in every slot |

**Objective (minimize):** `under_weight` per missing agent per half-hour slot and language (the forecast, from
medium with Wednesday at `holiday_factor` rounded up, minus the agents assigned) plus the labor cost of all
shifts (hours × rate; from medium a full-timer's shift beyond the `ft_regular_shifts` of the contract week at
1.5×). The client explains the weight as its estimate, in the same units as the rates, of what one agent
missing for half an hour costs in abandoned calls, callbacks and missed service levels.

## Hidden facts (clarification targets)

| Target | Kind | Tiers | The fact |
|---|---|---|---|
| `one_language` | ambiguous | all | a bilingual agent counts for one language only, for the whole shift |
| `slot_coverage` | ambiguous | all | the forecast is already in people, checked per half-hour slot |
| `holiday_wednesday` | missing | medium, hard | 11 November is a regional public holiday in the client's main market: `holiday_factor` of the forecast, rounded up; the file was not updated |
| `contract_limits` | missing | all | 8-hour shifts and at most `ft_max_shifts` a week for full-timers, 4-hour shifts and at most 3 for part-timers |
| `one_shift_a_day` | missing | easy | at most one shift a day |
| `min_rest` | missing | medium, hard | at least `min_rest` hours between two shifts |
| `leave_dates` | ambiguous | all | day/month/year, both ends included, rejected requests are not leave |
| `overtime` | missing | medium, hard | the contract week is `ft_week_hours` (`ft_regular_shifts` shifts); the next shift is overtime at 1.5× |
| `buddy_rule` | missing | medium, hard | a new hire is never alone on a language |
| `understaffing_penalty` | missing | all | `under_weight` per missing agent-slot plus the labor cost, and what the weight means |
| `sick_call` | missing | hard | the team lead's note is out of date: a doctor's certificate keeps its agent off sick up to `sick_until`, whatever the note says |
| `easy_scope` | missing | easy | this round: the forecast as it is, plain rates, rest checked on the floor (one shift a day), new hires like anyone else |

**What an agent must ask.** In every tier: the weight of a missing agent (it decides how many shifts are worth
paying for), the weekly caps and shift types, one language per shift, how the leave file's dates read. In
medium also: whether any day is special (the holiday and its share), the rest rule, how overtime is paid and
from which shift, and how new hires may be rostered. In hard also: whether anyone's availability has changed
since the leave export, i.e. whether the team lead's note is right. Following the note, or not asking, breaks
`sick_leave` in every hard setting.

## Situations present

- **Hidden facts that decide validity:** the weekly cap (a 6-shift plan is invalid under a 5-shift cap: 16 and
  11 `max_shifts` violations in easy/s10 and easy/s3 for the greedy planned with the other cap), the rest rule
  (the greedy planned without it breaks `min_rest` 1–7 times; planned with 11 h under 13 h, 8 times), the buddy
  rule (6–11 violations when ignored), the sick call (2 `sick_leave` violations in every hard setting when the
  note is followed), one language per shift, and the leave file (read as month/day, A20's day off on Monday 9
  November becomes 11 September, and the other ranges stretch over months).
- **Hidden facts that only move quality** (normalized quality of the greedy planned with the wrong value):
  the weight (planned at 40 when it is 15: 0.59–0.76; at 15 when it is 40: 0.68–0.74; at 15 when it is 25:
  0.87–0.91; at 40 when it is 25 the greedy loses nothing, 1.00–1.02), the holiday (ignored: 0.87–0.88 at 50%, 0.97 at 60%, about 1.0 at 75%), overtime (ignored:
  0.79–0.93 where it binds; at seed 10 the greedy happens to do 1–3% better without it), and a 40-hour week read
  as 32 (0.985–0.991).
- **Data traps:** day/month/year dates (no day above 12 at this seed), a rejected leave request (A03), a forecast
  not updated for the holiday, and the team lead's note, which is right in easy and medium and wrong in hard.
- **Pressure and a dated event (hard):** the team lead's "just roster them as usual, we can't spare them" against
  the doctor's certificate the client received the next morning.
- **Bendable rule:** `buddy_rule`. At the old single setting the optimum gained 0.58% by bending it (REVIEW F4).

## Reference, baseline and optimum

The **reference** is a greedy: it repeatedly adds the (agent, day, shift, language) with the largest gain,
`under_weight` per still-uncovered slot minus the shift's pay (with the overtime premium from medium), honoring
every rule of the setting and preferring senior agents so that new hires find buddies later. The **baseline** is
the supervisor's fixed rota drawn up without the forecast: every senior agent works one shift all week in their
main language, full-timers their contract week (`ft_regular_shifts` days) and part-timers 3, on consecutive
days from a start staggered within their language and contract; leave days (and in hard the sick days) are
left empty, and each new hire shadows a senior full-timer of their language (same days, same shift). Quality is
normalized: baseline 0, reference 1. Both are valid in every setting.

The **optimum** column is an exact MILP of the same model (1,316–1,364 binaries) solved with scipy's HiGHS in
under 10 seconds per setting, to proven optimality, and checked with `case.py`'s own evaluator. It is an analysis
script, not part of the case (scipy is not a dependency). At the old single setting (weight 40, 32 h, holiday
60%, rest 11 h, no sick call) it gives 23,464 against the greedy's 25,584, as before. The greedy is 0.5–8.1%
above the optimum; the optimum's normalized quality is 1.03–1.17 (table above). `case.yaml` sets no
`quality_cap` (see REVIEW.md, F1).

World seeds 1–3 (validated by default), baseline / reference per setting:

| World seed | Note's agent | easy s10 / s2 / s3 | medium s10 / s2 / s3 | hard s10 / s2 / s3 |
|---|---|---|---|---|
| 1 | A05 (zh) | 37,416 / 23,744; 28,881 / 21,878; 23,866 / 20,215 | 36,296 / 24,224; 28,481 / 22,286; 23,836 / 20,465 | 36,280 / 24,224; 27,948 / 22,462; 23,522 / 20,465 |
| 2 | A02 (zh) | 37,176 / 23,368; 28,830 / 21,974; 23,651 / 20,035 | 36,096 / 24,248; 28,680 / 22,134; 23,651 / 20,341 | 37,008 / 24,456; 28,901 / 22,308; 23,719 / 20,368 |
| 3 | A08 (zh) | 38,528 / 23,512; 29,313 / 22,100; 23,803 / 19,968 | 37,448 / 24,320; 29,063 / 22,135; 23,683 / 20,229 | 37,472 / 24,072; 28,530 / 21,959; 23,384 / 20,184 |

## Notes

- Synthetic: names, skills, forecast, leave and rates are generated from the seed; the shift pattern, the rules
  and the candidate values are design choices, not one center's practice.
- Simplifications: the forecast is already in agents (no calls, handling time or Erlang C step), shifts count
  in every slot with no breaks. A 32-hour contract week is unusual but lawful; 11 hours of rest is the EU
  minimum, 13 hours a stricter company agreement. Names are Latin-script in every locale and are not tied to the
  agent's languages.
- The leave dates are day/month/year in every locale. At this seed no date has a day above 12, but in other
  world seeds approved leave on Friday to Sunday shows 13–15 (seeds 1 and 3).
- `validate-case` checks the case in all nine public settings on its seed and world seeds 1–3: deterministic data
  in five locales that is the same in every setting, the reference valid at quality 1, the baseline valid and
  worse, one roster per rule of the tier that breaks only that rule, the panel and the pools, and that every
  parameter binds.
