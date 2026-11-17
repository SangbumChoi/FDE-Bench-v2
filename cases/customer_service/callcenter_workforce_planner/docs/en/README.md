# Call-Center Workforce Planner — `customer_service/callcenter_workforce_planner`

A multilingual customer-support center asks the agent for next week's roster (Monday 9 to Sunday 15
November 2026) for its support team: "enough people on the phones so customers aren't left waiting, in every language
we support". The center takes calls in Korean, Japanese, English, Chinese and Spanish, 08:00–22:00 every day.
The deliverable is `roster.json` (`{"assignments": [{"agent", "day", "shift", "language"}, ...]}`), one entry
per agent per shift worked. The setting is country-neutral: no national labor law applies beyond the rules the
client states, and the hourly rates carry no currency.

## Settings: three tiers × rule seeds

The case has settings (DESIGN.md, Settings): a setting is a tier and a rule seed. **The agent sees the same
request and the same data in every setting** (the validator checks that its prompt and workspace are
byte-identical). The tier decides which rules apply; the rule seed draws the client's numbers (how much a
missing agent costs, the full-time and part-time contract weeks, the rest hours, which day is a holiday and how
much of the forecast it keeps, the end of a sick leave) from candidate pools. The simulated client answers from the
hidden requirements of the setting and the evaluator scores under it, so the agent has to find out from the client
which rules and numbers apply this time. The engagement knobs (full spec vs. clarify first, client persona, data
noise, events) apply on top, as for every case (see [cases/README.md](../../../../README.md)).

| Tier | What applies |
|---|---|
| easy | The core staffing problem: one language per agent per shift (one of their skills), full-timers on 8-hour and part-timers on 4-hour shifts within their contract weeks (nobody works beyond them: no overtime this round), the rest time between two shifts of an agent (`min_rest`), approved leave (dates day/month/year, rejected requests are not leave), a regional public holiday on one weekday (a share of the forecast, rounded up) and the price of a missing agent against the labor cost (by the shift, with the part-timers' guaranteed hours and the new hires' training salary paid in full). New hires are rostered like anyone else, and the agent in the team lead's note is back on Monday. |
| medium | Easy plus overtime as a business policy (`overtime_approval`: a full-timer may work one shift beyond the contract week, only with the operations manager's approval and at 1.5 times the rate; an approved exception can bend it) and the new-hire buddy rule (`buddy_rule`, contractual: a new hire is never alone on a language). The agent in the team lead's note is back on Monday. |
| hard | Medium plus a dated sick call and the team lead's pressure: the note in the data (Thursday 5 November) says the agent it names "will be fine by Monday, just roster them as usual"; the client received that agent's doctor's certificate on Friday morning, which keeps them off sick up to a drawn day (`sick_leave`). |

### Parameters

Each parameter is drawn on its own from its pool (case.yaml `params:`). A pool of one value means the rule does not
apply in that tier; the code ignores the value there.

| Parameter | easy | medium | hard | What it changes |
|---|---|---|---|---|
| `under_weight` | 17, 50 | 17, 50 | 17, 50 | The price of one missing agent per half-hour slot and language, in the units of the hourly rates (22 full-time, 18 part-time): how many shifts pay for themselves. At 17 a full-time shift needs 11 of its 16 slots to fill a gap and a part-time shift 5 of its 8; at 50, 4 and 2. A cost-driven center against one that cannot afford to miss calls. |
| `ft_week_hours` | 32, 40 | 32, 40 | 32, 40 | The full-time contract week. Derived: `ft_regular_shifts` = 4 or 5; `ft_max_shifts` = the contract week in easy, one shift more (the overtime shift, which needs approval) from medium. |
| `pt_week_hours` | 12, 16 | 12, 16 | 12, 16 | The part-time contract week. Derived: `pt_max_shifts` = 3 or 4, the part-timers' weekly cap. The hours are guaranteed: a part-timer is paid the whole week even with fewer shifts. |
| `min_rest` | 11, 13 | 11, 13 | 11, 13 | Hours of rest between two shifts of an agent. 11 forbids a late shift (ending 22:00) followed by an 08:00 start; 13 also forbids the 12-hour turnarounds (S1400 → S1000, S1200 → S0800, P1600 → P0800). |
| `holiday_day` | Mon 9 to Fri 13 Nov | same | same | The regional public holiday the forecast file was not updated for: any weekday. |
| `holiday_factor` | 25%, 50% | 25%, 50% | 25%, 50% | The holiday's share of the forecast, rounded up per slot and language: 143 or 182 agent-slots instead of 286 on Monday, 143 or 181 instead of 280 on Tuesday, 142 or 176 instead of 265 on Wednesday, 140 or 171 instead of 258 on Thursday, 141 or 178 instead of 276 on Friday. |
| `sick_until` | 8 Nov (back Monday) | 8 Nov (back Monday) | Wed 11, Thu 12, Fri 13 Nov | The last day of the doctor's certificate of the agent in the team lead's note: off sick from Monday to Wednesday, Thursday or Friday. |

The agent in the note is derived from the world, not drawn: the experienced full-timer with no leave request
whose main language has the fewest experienced speakers (A08, Chinese, at the public seed; A05, A02 and A08 on
world seeds 1–3). The requirements never name them; they point to the note.

### Public panel (`rule_seeds: [10, 2, 11]`)

The panel shows every candidate of every pool except two of the five holiday days (Tuesday and Thursday come up in
the audit's combinations and in the leaderboard's round seeds). Seed 10 comes first: it is the default seed of a single run and
the setting of the validator's binding check. Objectives at the public world seed 20261109 (lower is better);
"Optimum" is the best known solution, the exact optimum of the same model (a MILP solved by HiGHS, see below).

| Setting | Drawn parameters | Baseline | Reference | Optimum | Reference: under-covered agent-slots, labor cost, shifts | Optimum's normalized quality |
|---|---|---|---|---|---|---|
| easy/s10 | weight 50, FT 32 h, PT 16 h, rest 11 h, holiday Mon 25% | 41,958 | 22,060 | 21,660 | 102, 16,960, 120 | 1.020 |
| easy/s2 | weight 50, FT 40 h, PT 12 h, rest 13 h, holiday Wed 50% | 39,708 | 21,810 | 21,210 | 41, 19,760, 130 | 1.034 |
| easy/s11 | weight 17, FT 40 h, PT 16 h, rest 11 h, holiday Fri 50% | 27,030 | 18,980 | 18,862 | 212, 15,376, 111 | 1.015 |
| medium/s10 | as easy/s10 | 41,958 | 23,784 | 21,860 | 140, 16,784, 119 | 1.106 |
| medium/s2 | as easy/s2 | 39,708 | 22,832 | 21,660 | 72, 19,232, 127 | 1.069 |
| medium/s11 | as easy/s11 | 27,030 | 19,584 | 19,185 | 144, 17,136, 121 | 1.054 |
| hard/s10 | as easy/s10, sick to Thu 12 | 43,704 | 23,908 | 22,134 | 146, 16,608, 118 | 1.090 |
| hard/s2 | as easy/s2, sick to Fri 13 | 41,678 | 24,104 | 22,532 | 108, 18,704, 124 | 1.089 |
| hard/s11 | as easy/s11, sick to Wed 11 | 27,369 | 19,544 | 19,185 | 152, 16,960, 120 | 1.046 |

The drawn values of each public setting are stored in `dataset/answer/answers.csv`, one row per setting (the
derived `ft_regular_shifts`, `ft_max_shifts` and `pt_max_shifts` follow from them and are not stored). Any other
rule seed is a private seed: a fresh draw of the same pools.

**Every parameter binds**, in every tier, on the public world and on world seeds 1–3 (validator: the reference of
the first public seed's setting is invalid, or its objective moves by 1% or more, under the other candidate).

## Data (the same in every setting)

| File (en) | Content |
|---|---|
| `agents.xlsx` | Sheet `staff`: 30 agents with `contract` (20 full-time, 10 part-time) and `new_hire` (4, all full-time). Sheet `skills`: one row per agent and language (the first row is the agent's main language) |
| `call_forecast.csv` | `agents_needed` per day, half-hour slot (08:00–21:30) and language: 980 rows, 1–5 agents each (1,739 agent-slots in the week), already converted from calls to people |
| `leave.csv` | 5 leave requests, `from` / `to` written day/month/year, `status` approved or rejected |
| `shifts.csv` | Four 8-hour full-time shifts (S0800, S1000, S1200, S1400) and four 4-hour part-time shifts (P0800, P1200, P1600, P1800), each with its `contract` |
| `labor_cost.csv` | Hourly rate per contract: 22.0 full-time, 18.0 part-time |
| `team_lead_note.txt` | A message from the team lead of the sick agent's main language, sent Thursday 5 November 17:40: the agent "has been off sick since Wednesday with the flu ... they'll be fine by Monday. Please just roster them as usual next week" |

File, sheet and column names and the categorical labels are localized (a Korean client sends
`고객센터_상담원명단.xlsx` with `고용형태 = 풀타임` and `팀장_메모.txt`); IDs, codes and numbers are not.

## Rules

| Rule | Class | Tiers | What it says |
|---|---|---|---|
| `skill_valid` | physical | all | An agent takes calls only in a language among their skills (one language for the whole shift) |
| `shift_type` | contractual | all | Full-timers only 8-hour shifts, part-timers only 4-hour shifts |
| `max_shifts` | contractual | all | At most `ft_max_shifts` shifts a week for a full-timer (the contract week in easy, one overtime shift more from medium) and `pt_max_shifts` for a part-timer |
| `min_rest` | contractual | all | At least `min_rest` hours between two shifts of the same agent (so at most one a day) |
| `leave_respected` | contractual | all | Nobody on a day of approved leave |
| `overtime_approval` | business policy (bendable) | medium, hard | No full-timer works beyond the `ft_regular_shifts` of the contract week without the operations manager's approval |
| `buddy_rule` | contractual | medium, hard | While a new hire is on the phones, at least one non-new agent is on the same language in every slot (the client's training agreement) |
| `sick_leave` | contractual | hard | The agent in the team lead's note is not rostered on any day up to `sick_until` |

**Objective (minimize):** `under_weight` per missing agent per half-hour slot and language (the forecast, on
`holiday_day` at `holiday_factor` rounded up, minus the agents assigned) plus the labor cost of all shifts (hours ×
rate; a part-timer's contract week, which is guaranteed, and a new hire's, their training salary, paid in full even
when fewer of their shifts are rostered; a full-timer's approved overtime shift at 1.5×). The client explains the weight as its estimate, in the same
units as the rates, of what one agent missing for half an hour costs in abandoned calls, callbacks and missed service
levels.

## Hidden facts (clarification targets)

| Target | Kind | Tiers | The fact |
|---|---|---|---|
| `one_language` | ambiguous | all | a bilingual agent counts for one language only, for the whole shift |
| `understaffing_price` | missing | all | `under_weight` per missing agent-slot plus the labor cost, and what the weight means (param `under_weight`) |
| `ft_contract_week` | missing | all | the full-time contract week, `ft_week_hours` (param); in easy nobody works beyond it, from medium a shift beyond it (one at most, at 1.5×) needs the operations manager's approval |
| `pt_contract_week` | missing | all | the part-time contract week, `pt_week_hours`, with no overtime and paid in full (guaranteed hours) (param) |
| `min_rest` | missing | all | at least `min_rest` hours between two shifts (param) |
| `holiday` | missing | all | `holiday_day` is a regional public holiday: `holiday_factor` of the forecast, rounded up; the file was not updated |
| `training_salary` | missing | all | new hires are on a training salary: their whole contract week is paid whether or not they are on the phones |
| `buddy_rule` | missing | medium, hard | a new hire is never alone on a language |
| `sick_call` | missing | hard | the team lead's note is out of date: a doctor's certificate keeps its agent off sick up to `sick_until`, whatever the note says |

The requirements also state facts that are not targets, because a careful agent reads them off its own data in
every setting: the forecast is already in agents per half-hour slot (`agents_needed` per `slot_start`), the shift
types per contract (`shifts.csv` has a `contract` column), the leave file's day/month/year dates (read as day/month
every request lies inside the week asked for, 9 to 12 November; read as month/day they would spread from September to
December, 11/11 reading the same either way) and that a rejected request is not leave. The overtime approval is part
of `ft_contract_week` (the client states the cap and the approval in one breath; at 32 hours a fifth shift is the same
roster whichever of the two is misread), and stays a rule (`overtime_approval`).

**What an agent must ask.** In every tier: the price of a missing agent (it decides how many shifts are worth paying
for), both contract weeks and how they are paid (the part-timers' guaranteed hours, the new hires' training salary),
the rest rule, one language per shift, and whether any day is special (the holiday, its day and share). In medium also: whether overtime can be planned and how new hires may be rostered. In hard also:
whether anyone's availability has changed since the data was exported, i.e. whether the team lead's note is right.
Following the note, or not asking, breaks `sick_leave` wherever a roster gives that agent a day of the certificate,
which a full week of shifts does as soon as the certificate runs to Thursday or Friday.

## Situations present

- **Hidden facts that decide validity:** both contract weeks (a 5-shift full-time week under a 32-hour contract, a
  4-shift part-time week under a 12-hour one), the rest rule (13 hours forbids the 12-hour turnarounds an 11-hour
  plan uses), from medium the overtime approval and the buddy rule, in hard the sick call.
- **Hidden facts that move quality:** the price of a missing agent (the reference planned at the other price loses
  up to 0.22 of the scale), the holiday (planning the forecast as it is loses 0.03–0.21), one language per shift
  (counting a bilingual agent on two languages loses 0.46 to all of it), the new hires' training salary (planning
  them as paid by the shift loses up to 0.33 at the price 17), the longer contract weeks read as the shorter ones
  (the part-time week is paid in full either way).
- **Data traps:** day/month/year dates (no day above 12 at this seed), a rejected leave request (A03), a forecast not
  updated for the holiday, and the team lead's note, which is right in easy and medium and wrong in hard.
- **Pressure and a dated event (hard):** the team lead's "just roster them as usual, we can't spare them" against
  the doctor's certificate the client received the next morning.
- **Bendable rule:** `overtime_approval`. With an approved exception a full-timer may work one more shift at 1.5
  times the rate. That pays where a missing agent is dear and the contract week short (price 50, 32 hours: the
  optimum is 2.9–8.2% cheaper, +0.03 to +0.13 of quality), a little at price 50 and 40 hours (0–1.5%), and nothing at
  price 17 (the optimum takes no overtime shift), where an exception only costs the policy's soft-rule penalty.

## Reference, baseline and optimum

The **reference** (`_Planner`) re-plans each agent's week exactly given everyone else's: a dynamic program over the
seven days (which shift and language each day, within the contract week and the rest time, a new hire only beside
an experienced colleague of the same language), agents in turn until no week improves; then every pair of agents who
share a language is taken off the roster and re-planned together while that lowers the objective (an experienced
agent and a new hire also with the first planning for both). It plans no overtime shift. It is deterministic and
takes 1–10 seconds per setting. The **baseline** is the supervisor's fixed rota drawn up without the forecast:
every senior agent works one shift all week in their main language, full-timers and part-timers their contract week,
on consecutive days from a start staggered within their language and contract; leave days (and in hard the sick
days) are left empty, and each new hire shadows a senior full-timer of their language (same days, same shift).
Quality is normalized: baseline 0, reference 1. Both are valid in every setting.

The **best known solution** is the exact optimum of the same model: a mixed-integer program (one binary per
agent, day, shift and language the rules allow; under-coverage, overtime, rest and buddy constraints as in the
scorer) solved by scipy's HiGHS to proven optimality within seconds per setting; its dual bound is the case's
`objective_bound` (proven optimal in every audited setting and on world seeds 1–3, at most 90 seconds each). The
reference is 0.3–8.1% above the optimum: the planner is weakest from medium, where the new hires' paid weeks need
experienced colleagues beside them. The optimum's normalized quality is 1.008–1.114 (median 1.052 over the audit's 45
settings; 1.037, 1.046 and 1.055 on world seeds 1–3), and `quality_cap` is 1.06.

**Literal solution** (`literal_solution`: the request done as written, the same in every setting): a greedy with the
readings the agent's view gives: the forecast file covered wherever it can be ("enough people on the phones so
customers aren't left waiting", a missing agent weighted above any shift's pay), skills, shift types, one shift a
day and the leave file's day/month dates with approved requests only, the usual five-day week for everyone (the
view gives no weekly cap), the agent in the team lead's note rostered as usual, and no holiday cut, rest time,
overtime rule or new-hire pairing. It is invalid in all 9 public settings, as delivered and with the bendable
`overtime_approval` relaxed: its 10-hour turnarounds break the rest time and its five-shift weeks the part-time
contract week in every setting (and the full-time one at 32 hours), and from medium it also breaks the buddy rule (and
in hard the sick call). With any one of
the rules it breaks kept (shortcuts `literal_plus_*`), it is still invalid everywhere: the client's facts carry its
failure, not one rule.

World seeds 1–3 (validated by default), baseline / reference per setting:

| World seed | Note's agent | easy s10 / s2 / s11 | medium s10 / s2 / s11 | hard s10 / s2 / s11 |
|---|---|---|---|---|
| 1 | A05 (zh) | 40,660 / 22,310; 37,610 / 22,010; 26,141 / 19,089 | 40,660 / 23,160; 37,610 / 22,658; 26,141 / 19,327 | 41,656 / 23,534; 38,780 / 23,230; 26,055 / 19,304 |
| 2 | A02 (zh) | 41,432 / 22,160; 37,606 / 22,158; 25,828 / 18,947 | 41,432 / 22,860; 37,606 / 22,956; 25,828 / 19,322 | 42,078 / 23,134; 38,726 / 23,704; 25,793 / 19,299 |
| 3 | A08 (zh) | 41,080 / 22,310; 39,530 / 21,808; 25,771 / 18,896 | 41,080 / 22,760; 39,530 / 22,608; 25,771 / 19,349 | 42,026 / 23,134; 40,700 / 23,530; 25,685 / 19,457 |

## Ground truth audit

The case is audited (`audited: true`); the ground truth in five parts is in [GT.md](../../GT.md), generated from
`dataset/audit.json`, and what the client answers from, per target and locale, in
[CLIENT_REVIEW.md](../../CLIENT_REVIEW.md) (awaiting human review). The audit measures 45 settings (15 per tier:
the public panel and 12 admissible combinations).

- **Facts.** 9 targets, each one thing the client tells; four are exactly a drawn parameter. Every target bites in
  every tier where it is in force (settings where misreading it loses at least 0.10 of the scale, easy / medium /
  hard, of 15 each): `one_language` 15 / 15 / 15, `understaffing_price` 12 / 11 / 9,
  `ft_contract_week` 11 / 12 / 11, `pt_contract_week` 14 / 13 / 14, `holiday`
  10 / 9 / 9, `min_rest` 6 / 5 / 7 (a 13-hour plan is valid and costs little where the client
  allows 11), `training_salary` 1 / 5 / 9 (only at the price 17: at 50 a new hire's shift pays for
  itself anyway), `buddy_rule` – / 15 / 15, `sick_call` – / – / 12.
- **Shortcuts.** 15: a single shift, the fixed rota and three one-change variants of it, constants,
  part-timers only, one day only, weekdays only, the new hires off the phones, one shift each, and the literal
  solution with each rule it breaks kept. All are closed in every setting but two, which are open and listed in
  `validate.OPEN_AUDIT_FINDINGS`: `weekdays_only` (13 of 45 settings, best
  0.59: at the price 17 the client's own objective values the whole
  weekend at under half of the scale) and `no_new_hires` (1 of 45, best
  0.515: the buddy rule kept vacuously; their training salary is paid
  anyway).
- **Value of asking** (`robust_solution`: the strictest candidate of every rule and the exact optimum of the
  expected objective over every price, holiday day and share of the tier's pools, the pay read by the hour):
  easy 0.23, medium 0.22, hard 0.25 of the credit.
  A roster on the strict side of every rule stays valid; it loses what the longer contracts, the holiday, the price
  and the training salary would have bought.
- **Reference and bounds.** The reference is within 0.3%–8.1% of the proven optimum (best
  known = bound in every setting); the optimum's quality is 1.008–1.114, median
  1.052, and `quality_cap` is 1.06 (the medians on world seeds 1–3 are 1.037, 1.046 and 1.055).
- **Diagnostics.** `diagnose()` reads each rule off the roster and measures the other facts against the planner's
  roster under each other reading (for the holiday also a cut on each other candidate day); it separates the
  reference from every ablation that bites and calls the optimum enforced on every target in every setting.

## Notes

- Synthetic: names, skills, forecast, leave and rates are generated from the seed; the shift pattern, the rules
  and the candidate values are design choices, not one center's practice.
- Simplifications: the forecast is already in agents (no calls, handling time or Erlang C step), shifts count
  in every slot with no breaks. A 32-hour full-time week and a 12- or 16-hour part-time week are unusual but lawful;
  11 hours of rest is the EU minimum, 13 hours a stricter company agreement. Names are Latin-script in every locale
  and are not tied to the agent's languages.
- The leave dates are day/month/year in every locale. At this seed no date has a day above 12, but in other
  world seeds approved leave on Friday to Sunday shows 13–15 (seeds 1 and 3).
- `validate-case` checks the case in all nine public settings on its seed and world seeds 1–3: deterministic data
  in five locales that is the same in every setting, the reference valid at quality 1, the baseline valid and
  worse, one roster per rule of the tier that breaks only that rule, the panel and the pools, that every
  parameter binds, and the stored ground truth audit.
