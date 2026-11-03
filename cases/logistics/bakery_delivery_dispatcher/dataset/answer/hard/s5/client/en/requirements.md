# Bakery morning delivery routing

## Background

Tomorrow (Monday) morning our central kitchen has to get the bread out to all our cafés with our four vans. Can you plan who drives where, so the cafés get their trays in time and the drivers aren't out longer than they need to be? The café list and the van list are attached.

## Deliverable

One JSON file, `routes.json`: `{"routes": [{"van": "V1", "depart": "05:40", "stops": ["C03", "C07", ...]}, ...]}`. One entry per van used, stops in visiting order, ids exactly as in the data. `depart` is the time the van leaves the kitchen; if it is left out, 05:00 is assumed.

## Data notes

- `x_km` / `y_km` are positions in kilometres relative to the central kitchen at (0, 0). Road distance is 1.3 times the straight-line distance.
- Driving speed depends on the time: 30 km/h until 07:00, and 20 km/h from 07:00 on (morning rush hour). A van that is still on the road at 07:00 slows down from then on.
- Unloading at a café takes 4 minutes plus 0.2 minutes per tray.
- A van that arrives before `opens` waits until the café opens. `deliver_by` is the latest arrival the café is happy with.
- A late delivery is accepted but not free: every minute a café is reached after its `deliver_by` costs us as much as 3 minutes of van time (complaints and credit notes to the café).
- Vans may leave from 05:00 and must be back at the kitchen by 10:00 (end of the drivers' shift).
- `max_trays` (120) is what a van's racks hold, but this week we deliver in the new, deeper crates, so a van takes at most 110 trays.
- The South Hill café (C11) is closed this week for renovation. Do not deliver there.
- Each café gets all of its trays in a single visit from one van.
- `partner_brand = yes` cafés sell our partner's chilled products. Only the refrigerated van (V4) may serve them.
- Our habit: on every route, premium cafés are served before standard cafés, so the premium stores are ready first.
- Monday only: V2 is in the workshop for its brake check until 06:40, so it cannot leave the kitchen before 06:40.
- The manager of the East Lake café (C07) keeps calling me: she insists on being the very first stop of the morning, before 06:30, and says she will take it to head office otherwise. That is not a rule of ours. She gets her trays between `opens` and `deliver_by` like every café, and I don't want the plan built around her calls.

## How the plan is judged

**Hard constraints** (if any is broken, the plan does not count):

- No van carries more than 110 trays.
- Vans leave at 05:00 or later and are back by 10:00.
- V2 leaves no earlier than 06:40.
- Every open café is served exactly once; the South Hill café (C11) is not served.
- Partner-brand cafés are served only by V4.
- On every route, premium cafés come before standard cafés.

**Quality**: the total time all vans are out (from departure to return), plus 3 times every minute a café is reached after its `deliver_by` time. Lower is better.
