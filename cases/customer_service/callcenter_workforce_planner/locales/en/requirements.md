# Multilingual support center weekly roster

## Background

Could you put together next week's roster (Monday 9 to Sunday 15 November) for our support team? We need enough people on the phones so customers aren't left waiting, in every language we support. The staff list and the expected call volume are attached.

## Deliverable

One JSON file, `roster.json`: `{"assignments": [{"agent": "A01", "day": "2026-11-09", "shift": "S0800", "language": "ko"}, ...]}`. One entry per agent per shift worked. `agent` and `shift` exactly as in the data, `day` as YYYY-MM-DD, `language` as the code `ko` (Korean), `ja` (Japanese), `en` (English), `zh` (Chinese) or `es` (Spanish).

## Data notes

- `agents.xlsx`, sheet `staff`: every agent with `contract` (full-time / part-time) and `new_hire`. Sheet `skills`: one row per agent and language they can take calls in. Only these 30 agents are available.
- `call_forecast.csv` already gives people, not calls: `agents_needed` is the number of agents needed on each language in the half-hour slot starting at `slot_start` (08:00 to 21:30; the phones are open 08:00-22:00). Coverage is checked per half-hour slot: an agent counts in every slot inside their shift (S0800 covers the slots 08:00 to 15:30).
- An agent takes calls in exactly one language for the whole shift, the one written in `language`, and it must be one of their skills. A bilingual agent counts for one language only, never for two at once.
- {{holiday_day}} is a regional public holiday in our main market. We stay open but expect far fewer calls: for that day plan {{holiday_factor}} of the forecast, rounded up to whole agents. The forecast file was not updated for this.
- `shifts.csv`: full-timers work only the 8-hour shifts (S...), part-timers only the 4-hour shifts (P...).
- A full-timer's contract week is {{ft_week_hours}} hours, that is {{ft_regular_shifts}} shifts.
<!-- tier: easy -->
- Nobody works beyond the contract week this round: a full-timer works at most {{ft_max_shifts}} shifts in the week.
<!-- /tier -->
<!-- tier: medium hard -->
- We do not plan overtime. By contract a full-timer may work one extra shift ({{ft_max_shifts}} in the week at most), but only with the operations manager's approval, and that shift is paid 1.5 times. Without that approval a full-timer works at most {{ft_regular_shifts}} shifts.
<!-- /tier -->
- A part-timer's contract is {{pt_week_hours}} hours a week: at most {{pt_max_shifts}} shifts, and no overtime. Those hours are guaranteed: we pay a part-timer's whole contract week even if we roster fewer shifts.
- Between the end of one shift and the start of the agent's next shift there must be at least {{min_rest}} hours of rest (so also at most one shift a day; for example, S1400 ends at 22:00 and cannot be followed by an 08:00 shift the next morning<!-- when: min_rest=13 -->, nor by a 10:00 one<!-- /when -->).
- `leave.csv` writes dates as day/month/year (10/11/2026 is 10 November); `from` and `to` are both included. Only `status = approved` counts as leave; a `rejected` request means the agent works normally.
- `labor_cost.csv` gives the hourly rate per contract. New hires are on a training salary: we pay a new hire's whole contract week ({{ft_regular_shifts}} shifts) whether or not they are on the phones.
<!-- tier: medium hard -->
- A new hire is never alone on a language: it is part of our training agreement. In every half-hour slot a new hire is on the phones, at least one agent who is not a new hire must be assigned to the same language.
<!-- /tier -->
<!-- tier: easy medium -->
- `team_lead_note.txt`: yes, the agent in that note is back on Monday; plan them like everyone else.
<!-- /tier -->
<!-- tier: hard -->
- `team_lead_note.txt` is out of date. On Friday morning (6 November) HR received that agent's doctor's certificate: they are off sick up to and including {{sick_until}}. Do not roster them on any day up to then, whatever the note says; after that they work normally.
<!-- /tier -->
<!-- tier: easy -->

**This round's scope**

- No overtime this round: the contract week is the limit for everyone.
- New hires can be rostered like everyone else; the floor manager pairs them with an experienced colleague on the day.
<!-- /tier -->

## How the roster is judged

**Hard constraints** (if any is broken, the roster does not count):

- Each agent only takes calls in one of their languages.
- Full-timers only on 8-hour shifts, part-timers only on 4-hour shifts.
- At most {{ft_max_shifts}} shifts a week for full-timers and {{pt_max_shifts}} for part-timers.
- At least {{min_rest}} hours of rest between two shifts of the same agent.
- Nobody is scheduled during approved leave.
<!-- tier: medium hard -->
- No full-timer works beyond the {{ft_regular_shifts}} shifts of the contract week without the operations manager's approval.
- New hires always have a non-new colleague on the same language at the same time.
<!-- /tier -->
<!-- tier: hard -->
- The agent in the team lead's note is not scheduled while off sick (up to and including {{sick_until}}).
<!-- /tier -->

**Quality**: {{under_weight}} for every missing agent in every half-hour slot and language (`agents_needed`, with the holiday adjustment on {{holiday_day}}, minus the agents assigned to that language in that slot, when positive), plus the labor cost of all shifts (hours times hourly rate; a part-timer's and a new hire's whole contract week even if fewer of their shifts are rostered<!-- tier: medium hard -->; an approved overtime shift at 1.5 times<!-- /tier -->). The {{under_weight}} is in the same units as the hourly rates: it is our estimate of what one missing agent for half an hour costs us in abandoned calls, callbacks and missed service levels. Extra agents beyond the need are not penalized except through their cost. Lower is better.
