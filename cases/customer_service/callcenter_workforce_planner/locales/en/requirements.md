# Multilingual support center weekly roster

## Background

Could you put together next week's roster (Monday 9 to Sunday 15 November) for our support team? We need enough people on the phones so customers aren't left waiting, in every language we support. The staff list and the expected call volume are attached.

## Deliverable

One JSON file, `roster.json`: `{"assignments": [{"agent": "A01", "day": "2026-11-09", "shift": "S0800", "language": "ko"}, ...]}`. One entry per agent per shift worked. `agent` and `shift` exactly as in the data, `day` as YYYY-MM-DD, `language` as the code `ko` (Korean), `ja` (Japanese), `en` (English), `zh` (Chinese) or `es` (Spanish).

## Data notes

- `agents.xlsx`, sheet `staff`: every agent with `contract` (full-time / part-time) and `new_hire`. Sheet `skills`: one row per agent and language they can take calls in. Only these 30 agents are available.
- `call_forecast.csv` already gives people, not calls: `agents_needed` is the number of agents needed on each language in the half-hour slot starting at `slot_start` (08:00 to 21:30; the phones are open 08:00-22:00). Coverage is checked per half-hour slot: an agent counts in every slot inside their shift (S0800 covers the slots 08:00 to 15:30).
- An agent takes calls in exactly one language for the whole shift, the one written in `language`, and it must be one of their skills. A bilingual agent counts for one language only, never for two at once.
- Wednesday 11 November is a regional public holiday in our main market. We stay open but expect fewer calls: for that day use 60% of the forecast, rounded up to whole agents. The forecast file was not updated for this.
- `shifts.csv`: full-timers work only the 8-hour shifts (S...), part-timers only the 4-hour shifts (P...).
- A full-timer works at most 5 shifts a week, a part-timer at most 3.
- Between the end of one shift and the start of the agent's next shift there must be at least 11 hours of rest (so also at most one shift a day; for example, S1400 ends at 22:00 and cannot be followed by an 08:00 shift the next morning).
- `leave.csv` writes dates as day/month/year (10/11/2026 is 10 November); `from` and `to` are both included. Only `status = approved` counts as leave; a `rejected` request means the agent works normally.
- `labor_cost.csv` gives the hourly rate per contract. A full-timer's normal week is 4 shifts: the 5th shift of the week is overtime and paid 1.5 times.
- Our habit: a new hire is never alone on a language. In every half-hour slot a new hire is on the phones, at least one agent who is not a new hire must be assigned to the same language.

## How the roster is judged

**Hard constraints** (if any is broken, the roster does not count):

- Each agent only takes calls in one of their languages.
- Full-timers only on 8-hour shifts, part-timers only on 4-hour shifts.
- At most 5 shifts a week for full-timers and 3 for part-timers.
- At least 11 hours of rest between two shifts of the same agent.
- Nobody is scheduled during approved leave.
- New hires always have a non-new colleague on the same language at the same time.

**Quality**: 40 for every missing agent in every half-hour slot and language (`agents_needed`, with the holiday adjustment on Wednesday, minus the agents assigned to that language in that slot, when positive), plus the labor cost of all shifts (hours times hourly rate, 5th full-time shift at 1.5 times). The 40 is in the same units as the hourly rates: it is our estimate of what one missing agent for half an hour costs us in abandoned calls, callbacks and missed service levels. Extra agents beyond the need are not penalized except through their cost. Lower is better.
