# Bakery morning delivery routing

## Background

Tomorrow (Monday) morning our central kitchen has to get the bread out to all our cafés with our four vans. Can you plan who drives where, so the cafés get their trays in time and the drivers aren't out longer than they need to be? The café list and the van list are attached.

## Deliverable

One JSON file, `routes.json`: `{"routes": [{"van": "V1", "depart": "05:40", "stops": ["C03", "C07", ...]}, ...]}`. One entry per van used, stops in visiting order, ids exactly as in the data. `depart` is the time the van leaves the kitchen; if it is left out, 05:00 is assumed.

## Data notes

- `x_km` / `y_km` are positions in kilometres relative to the central kitchen at (0, 0). Road distance is 1.3 times the straight-line distance.
- Driving speed: count 25 km/h on average, all morning. Monday is a school holiday, so there is no rush hour to plan around this week.
- Unloading at a café takes 4 minutes plus 0.2 minutes per tray.
- A van that arrives before `opens` waits until the café opens. `deliver_by` is the latest arrival the café is happy with.
- A late delivery is accepted but not free: every minute a café is reached after its `deliver_by` costs us as much as 2 minutes of van time (complaints and credit notes to the café).
- Vans may leave from 05:00 and must be back at the kitchen by 09:30 (end of the drivers' shift).
- `max_trays` (120) is what a van's racks hold, but this week we deliver in the new, deeper crates, so a van takes at most 110 trays.
- The North Station café (C03) is closed this week for renovation. Do not deliver there.
- Each café gets all of its trays in a single visit from one van.
- `partner_brand = yes` cafés sell our partner's chilled products, but this week the partner brings its chilled range itself. We only bring our bread, so any van may serve them.
- Our habit of serving premium cafés first is suspended this week (the premium managers agreed that being on time matters more), so on a route the cafés can come in whatever order works best.
- All four vans are available from 05:00 on Monday (V2's brake check is booked for Tuesday).

## How the plan is judged

**Hard constraints** (if any is broken, the plan does not count):

- No van carries more than 110 trays.
- Vans leave at 05:00 or later and are back by 09:30.
- Every open café is served exactly once; the North Station café (C03) is not served.

**Quality**: the total time all vans are out (from departure to return), plus 2 times every minute a café is reached after its `deliver_by` time. Lower is better.
