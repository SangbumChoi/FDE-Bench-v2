# Battery dispatch for the week of 22-28 March 2027

## Background

Can you plan when the battery at our site in Spain should charge and discharge next week (Monday 22 to Sunday 28 March) to make the most money? I've attached the price forecast, the solar forecast for the co-located solar farm, the battery spec sheet, our connection agreement and last week's dispatch log.

## Deliverable

One CSV file, `dispatch.csv`, with the ASCII header `timestamp,charge_mw,discharge_mw` and one row per 15-minute interval from `2027-03-22 00:00` to `2027-03-28 23:45`. `timestamp` is the start of the interval in local time as `YYYY-MM-DD HH:MM`. `charge_mw` and `discharge_mw` are the average battery power at the meter over that quarter-hour in MW, both zero or positive.

## Data notes

- We settle in 15-minute intervals, but `price_forecast.csv` is hourly: each hour's `day_ahead_price_eur_mwh` applies to all four quarter-hours of that hour. A quarter at P MW is P × 0.25 MWh.
- All timestamps are local time. The clocks go forward on Sunday 28 March (02:00 becomes 03:00), so that day has only 23 hours and there is no 02:00-02:45 on it. The week therefore has 668 quarter-hours, and the plan must have exactly those 668 rows; do not invent rows for clock times that do not exist.
- `solar_forecast.csv` gives the farm's average output per quarter-hour in MW. Treat it as exact.
- `battery_spec.csv`: 40 MWh, 20 MW charge and 20 MW discharge. The sheet quotes 84.6% round-trip efficiency; we model it per direction: {{eta_charge_pct}}% on charge and {{eta_discharge_pct}}% on discharge. Charging at P MW for a quarter adds 0.25 × P × {{eta_charge}} MWh to the stored energy; discharging P MW (as delivered at the meter) removes 0.25 × P / {{eta_discharge}} MWh.
<!-- when: soc_window=10-90,15-85 -->
- The manufacturer allows 5%-95% state of charge, but our warranty requires {{soc_min}}%-{{soc_max}}% ({{soc_min_mwh}} to {{soc_max_mwh}} MWh) at every moment.
<!-- /when -->
<!-- when: soc_window=5-95 -->
- The manufacturer allows 5%-95% state of charge, and our warranty allows the same window: stay within {{soc_min}}%-{{soc_max}}% ({{soc_min_mwh}} to {{soc_max_mwh}} MWh) at every moment.
<!-- /when -->
- The battery starts the week at 50% (20 MWh) at Monday 00:00, and must end the week (after the Sunday 23:45 interval) at {{end_soc}}% ({{end_soc_mwh}} MWh) or more.
- In any quarter the battery either charges or discharges (or rests), never both. Each is at most 20 MW.
- `connection_agreement.md` is out of date on one point: because of substation works, our export limit is reduced from 30 MW. In the current phase of the works, from Monday 22 March until they end (planned for 30 June 2027), it is {{export_cap}} MW. The solar farm and the battery share the connection: whenever the battery discharges, solar + discharge − charge must not exceed {{export_cap}} MW. When the battery is not discharging and solar is above {{export_cap}} MW, the controller clips the solar automatically; that is allowed, but the clipped energy is lost unless the battery soaks it up.
<!-- tier: easy -->
- For this first plan, leave out our off-peak import rule: the battery may charge from the solar farm or from the grid at any hour, as long as the site never draws more than 20 MW from the grid.
- Leave battery wear out of this first plan too: no degradation cost is charged this round.
- The evening emergency reserve does not apply to this first plan either: the battery may use its whole warranty window in the evening.
<!-- /tier -->
<!-- tier: medium hard -->
- Charging from the solar farm is allowed at any time (charge no more than the solar output in that quarter). Drawing power from the grid (charging more than the solar output) is only allowed in quarters starting {{import_from}}-{{import_last}} local time, our off-peak import window, and never more than 20 MW.
- Every MWh that goes in or out of the battery (charge MWh plus discharge MWh, at the meter) costs us EUR {{degradation}} in degradation.
- Our policy: the battery keeps at least {{reserve_pct}}% ({{reserve_mwh}} MWh) in reserve for emergencies at every moment between {{reserve_from}} and {{reserve_to}} local time, every day.
<!-- /tier -->
<!-- tier: hard -->
- Three notices came in this week. They override the documents for the hours they name:
  - The substation contractor finishes early: from {{works_end}} 00:00 the agreement's 30 MW export limit applies again, for the rest of the week.
  - The DSO has planned works on our line: on {{dso_day}} from 18:00 to 21:00 the site may export at most {{dso_mw}} MW. In those quarters solar + discharge − charge must not exceed {{dso_mw}} MW while the battery discharges; solar above it is clipped like above the export limit.
  - Inverter maintenance: on {{outage_day}} from 08:00 to 20:00 the battery is offline. It can neither charge nor discharge in those quarters.
- Our trading desk keeps asking for the evening reserve to be sold into the evening peaks as well ("the spike pays for it"). The reserve is company policy: it stays in force unless operations approves an exception.
<!-- /tier -->
- `dispatch_log_last_week.csv` shows how we ran the battery last week, for reference. It was planned with last week's settings, and not all of them are the same this week.

## How the plan is judged

**Hard constraints** (if any is broken, the plan does not count):

- State of charge stays within {{soc_min}}%-{{soc_max}}% throughout ({{eta_charge_pct}}% efficiency on charge, {{eta_discharge_pct}}% on discharge).
- Each power value is between 0 and 20 MW; no quarter both charges and discharges; grid import at most 20 MW.
- While discharging, site export (solar + discharge − charge) is at most {{export_cap}} MW<!-- tier: hard -->, or 30 MW from {{works_end}} 00:00<!-- /tier -->.
<!-- tier: medium hard -->
- Grid import only in quarters starting {{import_from}}-{{import_last}}.
<!-- /tier -->
- The week starts at 50% and ends at {{end_soc}}% or more.
<!-- tier: medium hard -->
- At least {{reserve_pct}}% state of charge at every moment between {{reserve_from}} and {{reserve_to}}.
<!-- /tier -->
<!-- tier: hard -->
- On {{dso_day}} from 18:00 to 21:00, site export while discharging is at most {{dso_mw}} MW.
- No charging or discharging on {{outage_day}} from 08:00 to 20:00.
<!-- /tier -->

**Quality**: the battery's profit in EUR, settled at the actual market prices of the week (they will differ from the forecast; plan on the forecast). For every quarter, site net output = solar + discharge − charge. If positive, we earn price × 0.25 × min(net, export limit); if negative, we pay price × 0.25 × the import. From that we subtract what the solar farm alone would have earned (price × 0.25 × min(solar, export limit))<!-- tier: medium hard --> and EUR {{degradation}} per MWh of battery throughput<!-- /tier -->. The export limit is {{export_cap}} MW<!-- tier: hard -->, 30 MW from {{works_end}} 00:00 and {{dso_mw}} MW during the DSO's hours on {{dso_day}}<!-- /tier -->. Higher is better.
