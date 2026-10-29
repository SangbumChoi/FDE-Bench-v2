# Bakery morning delivery routing

## Background

Tomorrow (Monday) morning our central kitchen has to get the bread out to all our cafés with our four vans. Can you plan who drives where, so the cafés get their trays in time and the drivers aren't out longer than they need to be? The café list and the van list are attached.

## Deliverable

One JSON file, `routes.json`: `{"routes": [{"van": "V1", "depart": "05:40", "stops": ["C03", "C07", ...]}, ...]}`. One entry per van used, stops in visiting order, ids exactly as in the data. `depart` is the time the van leaves the kitchen; if it is left out, 05:00 is assumed.

## Data notes

- `x_km` / `y_km` are positions in kilometres relative to the central kitchen at (0, 0). Road distance is 1.3 times the straight-line distance.
- Driving speed depends on when a leg starts: 30 km/h for legs starting before 07:00, 20 km/h for legs starting at 07:00 or later (morning rush hour).
- Unloading at a café takes 4 minutes plus 0.2 minutes per tray.
- A van that arrives before `opens` waits until the café opens. `deliver_by` is the latest arrival the café is happy with.
- A late delivery is accepted but not free: every minute a café is reached after its `deliver_by` costs us as much as three minutes of van time (complaints and credit notes to the café).
- Vans may leave from 05:00 and must be back at the kitchen by 09:30 (end of the drivers' shift). Each van carries at most `max_trays` trays.
- The South Hill café (C11) is closed this week for renovation. Do not deliver there.
- `partner_brand = yes` cafés sell our partner's chilled products. Only the refrigerated van (V4) may serve them.
- Each café gets all of its trays in a single visit from one van.
- Our habit: on every route, premium cafés are served before standard cafés, so the premium stores are ready first.

## How the plan is judged

**Hard constraints** (if any is broken, the plan does not count):

- No van carries more than its `max_trays`.
- Vans leave at 05:00 or later and are back by 09:30.
- Every open café is served exactly once; C11 is not served.
- Partner-brand cafés are served only by V4.
- On every route, premium cafés come before standard cafés.

**Quality**: the total time all vans are out (from departure to return), plus three times every minute a café is reached after its `deliver_by` time. Lower is better.
