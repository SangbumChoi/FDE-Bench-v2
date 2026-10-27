# Battery dispatch for the week of 22-28 March 2027

## Background

Can you plan when our battery should charge and discharge next week (Monday 22 to Sunday 28 March) to make the most money? I've attached the price forecast, the solar forecast for the farm next door, the battery spec sheet, our connection agreement and last week's dispatch log.

## Deliverable

One CSV file, `dispatch.csv`, with the ASCII header `timestamp,charge_mw,discharge_mw` and one row per 15-minute interval from `2027-03-22 00:00` to `2027-03-28 23:45`. `timestamp` is the start of the interval in local time as `YYYY-MM-DD HH:MM`. `charge_mw` and `discharge_mw` are the average battery power at the meter over that quarter-hour in MW, both zero or positive.

## Data notes

- We settle in 15-minute intervals, but `price_forecast.csv` is hourly: each hour's `day_ahead_price_eur_mwh` applies to all four quarter-hours of that hour. A quarter at P MW is P × 0.25 MWh.
- All timestamps are local time. The clocks go forward on Sunday 28 March (02:00 becomes 03:00), so that day has only 23 hours and there is no 02:00-02:45 on it. The week therefore has 668 quarter-hours, and the plan must have exactly those 668 rows; do not invent rows for clock times that do not exist.
- `solar_forecast.csv` gives the farm's average output per quarter-hour in MW. Treat it as exact.
- `battery_spec.csv`: 40 MWh, 20 MW charge and 20 MW discharge. The sheet quotes 84.6% round-trip efficiency; we model it as 92% in each direction. Charging at P MW for a quarter adds 0.25 × P × 0.92 MWh to the stored energy; discharging P MW (as delivered at the meter) removes 0.25 × P / 0.92 MWh.
- The manufacturer allows 5%-95% state of charge, but our warranty requires 10%-90% (4 to 36 MWh) at every moment.
- The battery starts the week at 50% (20 MWh) at Monday 00:00, and must end the week (after the Sunday 23:45 interval) at 50% or more.
- In any quarter the battery either charges or discharges (or rests), never both. Each is at most 20 MW.
- `connection_agreement.md` is out of date on one point: because of substation works, our export limit is reduced from 30 MW to 25 MW from 1 March to 30 June 2027. The solar farm and the battery share the connection: whenever the battery discharges, solar + discharge − charge must not exceed 25 MW. When the battery is not discharging and solar is above 25 MW, the controller clips the solar automatically; that is allowed, but the clipped energy is lost unless the battery soaks it up.
- Charging from the solar farm is allowed at any time (charge no more than the solar output in that quarter). Drawing power from the grid (charging more than the solar output) is only allowed in quarters starting 00:00-05:45 local time, our off-peak import window, and never more than 20 MW.
- Every MWh that goes in or out of the battery (charge MWh plus discharge MWh, at the meter) costs us EUR 5 in degradation.
- Our policy: the battery keeps at least 20% (8 MWh) in reserve for emergencies at every moment between 17:00 and 21:00 local time, every day.
- `dispatch_log_last_week.csv` shows how we ran the battery last week, for reference.

## How the plan is judged

**Hard constraints** (if any is broken, the plan does not count):

- State of charge stays within 10%-90% throughout (with 92% efficiency each way).
- Each power value is between 0 and 20 MW; no quarter both charges and discharges; grid import at most 20 MW.
- While discharging, site export (solar + discharge − charge) is at most 25 MW.
- Grid import only in quarters starting 00:00-05:45.
- The week starts at 50% and ends at 50% or more.
- At least 20% state of charge at every moment between 17:00 and 21:00.

**Quality**: the battery's profit in EUR, settled at the actual market prices of the week (they will differ from the forecast; plan on the forecast). For every quarter, site net output = solar + discharge − charge. If positive, we earn price × 0.25 × min(net, 25); if negative, we pay price × 0.25 × the import. From that we subtract what the solar farm alone would have earned (price × 0.25 × min(solar, 25)) and EUR 5 per MWh of battery throughput. Higher is better.
