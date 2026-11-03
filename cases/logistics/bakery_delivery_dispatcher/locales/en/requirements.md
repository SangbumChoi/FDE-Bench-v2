# Bakery morning delivery routing

## Background

Tomorrow (Monday) morning our central kitchen has to get the bread out to all our cafés with our four vans. Can you plan who drives where, so the cafés get their trays in time and the drivers aren't out longer than they need to be? The café list and the van list are attached.

## Deliverable

One JSON file, `routes.json`: `{"routes": [{"van": "V1", "depart": "05:40", "stops": ["C03", "C07", ...]}, ...]}`. One entry per van used, stops in visiting order, ids exactly as in the data. `depart` is the time the van leaves the kitchen; if it is left out, 05:00 is assumed.

## Data notes

- `x_km` / `y_km` are positions in kilometres relative to the central kitchen at (0, 0). Road distance is 1.3 times the straight-line distance.
<!-- tier: easy medium -->
- Driving speed: count 25 km/h on average, all morning. Monday is a school holiday, so there is no rush hour to plan around this week.
<!-- /tier -->
<!-- tier: hard -->
- Driving speed depends on the time: 30 km/h until {{rush_start}}, and 20 km/h from {{rush_start}} on (morning rush hour). A van that is still on the road at {{rush_start}} slows down from then on.
<!-- /tier -->
- Unloading at a café takes 4 minutes plus 0.2 minutes per tray.
- A van that arrives before `opens` waits until the café opens. `deliver_by` is the latest arrival the café is happy with.
- A late delivery is accepted but not free: every minute a café is reached after its `deliver_by` costs us as much as {{late_cost}} minutes of van time (complaints and credit notes to the café).
- Vans may leave from 05:00 and must be back at the kitchen by {{shift_end}} (end of the drivers' shift).
<!-- when: van_capacity=120 -->
- Each van carries at most `max_trays` trays (120).
<!-- /when -->
<!-- when: van_capacity=100,110 -->
- `max_trays` (120) is what a van's racks hold, but this week we deliver in the new, deeper crates, so a van takes at most {{van_capacity}} trays.
<!-- /when -->
- The {{closed_cafe}} is closed this week for renovation. Do not deliver there.
- Each café gets all of its trays in a single visit from one van.
<!-- tier: easy -->
- `partner_brand = yes` cafés sell our partner's chilled products, but this week the partner brings its chilled range itself. We only bring our bread, so any van may serve them.
<!-- /tier -->
<!-- tier: medium hard -->
- `partner_brand = yes` cafés sell our partner's chilled products. Only the refrigerated van (V4) may serve them.
<!-- /tier -->
<!-- when: premium_first=true -->
- Our habit: on every route, premium cafés are served before standard cafés, so the premium stores are ready first.
<!-- /when -->
<!-- when: premium_first=false -->
- Our habit of serving premium cafés first is suspended this week (the premium managers agreed that being on time matters more), so on a route the cafés can come in whatever order works best.
<!-- /when -->
<!-- tier: easy medium -->
- All four vans are available from 05:00 on Monday (V2's brake check is booked for Tuesday).
<!-- /tier -->
<!-- tier: hard -->
- Monday only: V2 is in the workshop for its brake check until 06:40, so it cannot leave the kitchen before 06:40.
- The manager of the East Lake café (C07) keeps calling me: she insists on being the very first stop of the morning, before 06:30, and says she will take it to head office otherwise. That is not a rule of ours. She gets her trays between `opens` and `deliver_by` like every café, and I don't want the plan built around her calls.
<!-- /tier -->

## How the plan is judged

**Hard constraints** (if any is broken, the plan does not count):

- No van carries more than {{van_capacity}} trays.
- Vans leave at 05:00 or later and are back by {{shift_end}}.
<!-- tier: hard -->
- V2 leaves no earlier than 06:40.
<!-- /tier -->
- Every open café is served exactly once; the {{closed_cafe}} is not served.
<!-- tier: medium hard -->
- Partner-brand cafés are served only by V4.
<!-- when: premium_first=true -->
- On every route, premium cafés come before standard cafés.
<!-- /when -->
<!-- /tier -->

**Quality**: the total time all vans are out (from departure to return), plus {{late_cost}} times every minute a café is reached after its `deliver_by` time. Lower is better.
