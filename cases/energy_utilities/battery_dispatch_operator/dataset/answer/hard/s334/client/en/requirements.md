# Battery dispatch for the week of 22-28 March 2027

## Background

Can you plan when the battery at our site in Spain should charge and discharge next week (Monday 22 to Sunday 28 March) to make the most money? I've attached the price forecast, the solar forecast for the co-located solar farm, the battery spec sheet, our connection agreement and last week's dispatch log.

## Deliverable

One CSV file, `dispatch.csv`, with the ASCII header `timestamp,charge_mw,discharge_mw` and one row per 15-minute interval from `2027-03-22 00:00` to `2027-03-28 23:45`. `timestamp` is the start of the interval in local time as `YYYY-MM-DD HH:MM`. `charge_mw` and `discharge_mw` are the average battery power at the meter over that quarter-hour in MW, both zero or positive.

## Data notes

- We settle in 15-minute intervals, but `price_forecast.csv` is hourly: each hour's `day_ahead_price_eur_mwh` applies to all four quarter-hours of that hour. A quarter at P MW is P × 0.25 MWh.
- All timestamps are local time. The clocks go forward on Sunday 28 March (02:00 becomes 03:00), so that day has only 23 hours and there is no 02:00-02:45 on it. The week therefore has 668 quarter-hours, and the plan must have exactly those 668 rows; do not invent rows for clock times that do not exist.
- `solar_forecast.csv` gives the farm's average output per quarter-hour in MW. Treat it as exact.
- `battery_spec.csv`: 40 MWh, 20 MW charge and 20 MW discharge. The sheet quotes 84.6% round-trip efficiency; we model it per direction: 92% on charge and 92% on discharge. Charging at P MW for a quarter adds 0.25 × P × 0.92 MWh to the stored energy; discharging P MW (as delivered at the meter) removes 0.25 × P / 0.92 MWh.
- The manufacturer allows 5%-95% state of charge, but our warranty requires 15%-85% (6 to 34 MWh) at every moment.
- The battery starts the week at 50% (20 MWh) at Monday 00:00, and must end the week (after the Sunday 23:45 interval) at 30% (12 MWh) or more.
- In any quarter the battery either charges or discharges (or rests), never both. Each is at most 20 MW.
- `connection_agreement.md` is out of date on one point: because of substation works, our export limit is reduced from 30 MW. In the current phase of the works, from Monday 22 March until they end (planned for 30 June 2027), it is 18 MW. The solar farm and the battery share the connection: whenever the battery discharges, solar + discharge − charge must not exceed 18 MW. When the battery is not discharging and solar is above 18 MW, the controller clips the solar automatically; that is allowed, but the clipped energy is lost unless the battery soaks it up.
- Charging from the solar farm is allowed at any time (charge no more than the solar output in that quarter). Drawing power from the grid (charging more than the solar output) is only allowed in quarters starting 02:00-07:45 local time, our off-peak import window, and never more than 20 MW.
- Every MWh that goes in or out of the battery (charge MWh plus discharge MWh, at the meter) costs us EUR 25 in degradation.
- Our policy: the battery keeps at least 30% (12 MWh) in reserve for emergencies at every moment between 17:00 and 21:00 local time, every day.
- Three notices came in this week. They override the documents for the hours they name:
  - The substation contractor finishes early: from Saturday 27 March 00:00 the agreement's 30 MW export limit applies again, for the rest of the week.
  - The DSO has planned works on our line: on Saturday 27 March from 18:00 to 21:00 the site may export at most 8 MW. In those quarters solar + discharge − charge must not exceed 8 MW while the battery discharges; solar above it is clipped like above the export limit.
  - Inverter maintenance: on Friday 26 March from 08:00 to 20:00 the battery is offline. It can neither charge nor discharge in those quarters.
- Our trading desk keeps asking for the evening reserve to be sold into the evening peaks as well ("the spike pays for it"). The reserve is company policy: it stays in force unless operations approves an exception.
- `dispatch_log_last_week.csv` shows how we ran the battery last week, for reference. It was planned with last week's settings, and not all of them are the same this week.

## How the plan is judged

**Hard constraints** (if any is broken, the plan does not count):

- State of charge stays within 15%-85% throughout (92% efficiency on charge, 92% on discharge).
- Each power value is between 0 and 20 MW; no quarter both charges and discharges; grid import at most 20 MW.
- While discharging, site export (solar + discharge − charge) is at most 18 MW, or 30 MW from Saturday 27 March 00:00.
- Grid import only in quarters starting 02:00-07:45.
- The week starts at 50% and ends at 30% or more.
- At least 30% state of charge at every moment between 17:00 and 21:00.
- On Saturday 27 March from 18:00 to 21:00, site export while discharging is at most 8 MW.
- No charging or discharging on Friday 26 March from 08:00 to 20:00.

**Quality**: the battery's profit in EUR, settled at the actual market prices of the week (they will differ from the forecast; plan on the forecast). For every quarter, site net output = solar + discharge − charge. If positive, we earn price × 0.25 × min(net, export limit); if negative, we pay price × 0.25 × the import. From that we subtract what the solar farm alone would have earned (price × 0.25 × min(solar, export limit)) and EUR 25 per MWh of battery throughput. The export limit is 18 MW, 30 MW from Saturday 27 March 00:00 and 8 MW during the DSO's hours on Saturday 27 March. Higher is better.
