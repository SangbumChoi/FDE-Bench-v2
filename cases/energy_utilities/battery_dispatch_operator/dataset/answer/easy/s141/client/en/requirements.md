# Battery dispatch for the week of 22-28 March 2027

## Background

Can you plan when the battery at our site in Spain should charge and discharge next week (Monday 22 to Sunday 28 March) to make the most money? I've attached the price forecast, the solar forecast for the co-located solar farm, the battery spec sheet, our connection agreement and last week's dispatch log.

## Deliverable

One CSV file, `dispatch.csv`, with the ASCII header `timestamp,charge_mw,discharge_mw` and one row per 15-minute interval from `2027-03-22 00:00` to `2027-03-28 23:45`. `timestamp` is the start of the interval in local time as `YYYY-MM-DD HH:MM`. `charge_mw` and `discharge_mw` are the average battery power at the meter over that quarter-hour in MW, both zero or positive.

## Data notes

- We settle in 15-minute intervals, but `price_forecast.csv` is hourly: each hour's `day_ahead_price_eur_mwh` applies to all four quarter-hours of that hour. A quarter at P MW is P × 0.25 MWh.
- All timestamps are local time. The clocks go forward on Sunday 28 March (02:00 becomes 03:00), so that day has only 23 hours and there is no 02:00-02:45 on it. The week therefore has 668 quarter-hours, and the plan must have exactly those 668 rows; do not invent rows for clock times that do not exist.
- `solar_forecast.csv` gives the farm's average output per quarter-hour in MW. Treat it as exact.
- `battery_spec.csv`: 40 MWh, 20 MW charge and 20 MW discharge. The sheet quotes 84.6% round-trip efficiency; we model it per direction: 95% on charge and 89% on discharge. Charging at P MW for a quarter adds 0.25 × P × 0.95 MWh to the stored energy; discharging P MW (as delivered at the meter) removes 0.25 × P / 0.89 MWh.
- The manufacturer allows 5%-95% state of charge, and our warranty allows the same window: stay within 5%-95% (2 to 38 MWh) at every moment.
- The battery starts the week at 50% (20 MWh) at Monday 00:00, and must end the week (after the Sunday 23:45 interval) at 50% (20 MWh) or more.
- In any quarter the battery either charges or discharges (or rests), never both. Each is at most 20 MW.
- `connection_agreement.md` is out of date on one point: because of substation works, our export limit is reduced from 30 MW. In the current phase of the works, from Monday 22 March until they end (planned for 30 June 2027), it is 15 MW. The solar farm and the battery share the connection: whenever the battery discharges, solar + discharge − charge must not exceed 15 MW. When the battery is not discharging and solar is above 15 MW, the controller clips the solar automatically; that is allowed, but the clipped energy is lost unless the battery soaks it up.
- For this first plan, leave out our off-peak import rule: the battery may charge from the solar farm or from the grid at any hour, as long as the site never draws more than 20 MW from the grid.
- Leave battery wear out of this first plan too: no degradation cost is charged this round.
- The evening emergency reserve does not apply to this first plan either: the battery may use its whole warranty window in the evening.
- `dispatch_log_last_week.csv` shows how we ran the battery last week, for reference. It was planned with last week's settings, and not all of them are the same this week.

## How the plan is judged

**Hard constraints** (if any is broken, the plan does not count):

- State of charge stays within 5%-95% throughout (95% efficiency on charge, 89% on discharge).
- Each power value is between 0 and 20 MW; no quarter both charges and discharges; grid import at most 20 MW.
- While discharging, site export (solar + discharge − charge) is at most 15 MW.
- The week starts at 50% and ends at 50% or more.

**Quality**: the battery's profit in EUR, settled at the actual market prices of the week (they will differ from the forecast; plan on the forecast). For every quarter, site net output = solar + discharge − charge. If positive, we earn price × 0.25 × min(net, export limit); if negative, we pay price × 0.25 × the import. From that we subtract what the solar farm alone would have earned (price × 0.25 × min(solar, export limit)). The export limit is 15 MW. Higher is better.
