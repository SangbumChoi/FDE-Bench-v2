# Logistics & Transportation — case specs

Most AI work in logistics today sits on top of classic operations-research engines instead of replacing them.
Load builders in TMS suites (SAP TM, 3D bin-packing tools) treat axle weights, stacking and drop sequence as
hard rules. Depot and terminal optimizers (INFORM, Kaleris, research systems tested on 100+ bus fleets) put
learned forecasts such as dwell time, energy use or arrival time into a solver. ETA systems such as DoorDash's
DeeprETA correct a routing engine's estimate with a learned residual and are judged on tail error, not on the
mean. Freight-audit vendors now sell "agentic" invoice checking. They say 1-9% of freight spend (some claim
15-25% of invoices) is billed in error, mostly through divisor, surcharge and duplicate mistakes. In every
deployment the hard part is the same: knowing the unwritten local rule (a legal axle cap, a tariff band, a
contract's DIM divisor, a duty table). That makes the field a good fit for a clarify-then-build benchmark.

| Role | Task type | Deliverable | Hook |
|---|---|---|---|
| Bakery Delivery Dispatcher ✅ | Optimization | Batch `routes.json` | (built) |
| Freight Load Planner | Optimization | Batch `loads.json` | Legal axle caps and LIFO-by-stop decide what can share a truck |
| EV Fleet Charging Planner | Optimization | Batch `charging.csv` | The tariff's cheap band is not where you assume, and the grid cap bites |
| Container Yard Planner | Optimization | Batch `yard_plan.csv` | Departure order vs reefer plugs vs IMDG segregation vs weight tiers |
| Airline Crew Scheduler | Optimization | Batch `pairings.json` | FDP depends on report time and sector count, in base-local time |
| Delivery ETA Modeler | ML | Program `eta(order)` | Mixed-timezone timestamps and a window-hit metric that punishes lateness |
| Freight Invoice Auditor (replaces Bike-Share Rebalancing) | Rules + extraction | Batch `audit.csv` | Contract DIM divisor, fuel-index table, duplicate re-bills |

**Replacement.** The catalog's *Bike-Share Rebalancing Planner* is replaced by a *Freight Invoice Auditor*. The
field already has two routing-style optimizers (bakery, load planning) and one ML forecaster (ETA), so
rebalancing would mostly repeat those skills. Freight audit is a large, active commercial AI use case. It tests
a skill missing elsewhere in this field: applying contract terms line by line to documents. It also localizes
naturally, because DIM divisors, VAT/consumption-tax invoices and fuel-revision clauses differ by country.

---

### Freight Load Planner — `logistics/freight_load_planner`
- **Why it matters** — Carriers plan loads in reverse delivery order (LIFO) and treat the drop sequence as a hard
  constraint. Solvers accept lower fill rates rather than block an earlier stop. Axle limits are where planned
  loads become illegal: Korean roadside enforcement finds that roughly two thirds of overload violations are
  axle-weight violations, not gross-weight ones. Research notes that most VRP tools still leave axle limits out.
- **Client & request** — Regional 3PL dispatcher: "Here's tomorrow's freight. Put it into as few trucks as you
  can, and keep the drivers' stop lists sensible."
- **Deliverable** — Batch `loads.json`:
  `{"trucks":[{"truck":"T03","stops":["S12","S04"],"pallets":[{"id":"P0091","slot":5,"tier":1}]}]}`.
  Slots are numbered 1..N from the cab to the doors; tier is 1 (floor) or 2 (stacked).
- **World & data** — 1 depot, 25-35 delivery stops, 180-260 pallets, 10 trucks of two types (13.6 m trailer with
  33 floor slots; 7.2 m rigid with 14). Files: `pallets.csv` (pallet_id, order_id, stop_id, weight_kg, height_cm,
  stackable, fragile, adr_class), `stops.csv` (stop_id, x_km, y_km, window_open/close), `trucks.csv`
  (truck_id, type, slots, tare_front_kg, tare_rear_kg, axle positions), `orders.csv`. Hidden in the world:
  the axle-load model (each slot's weight shared between steer axle and rear group by lever arm).
- **Hidden requirements**
  - `axle_caps` (missing; calculation) — Steer axle ≤ 7.1 t and drive/rear group ≤ 11.5 t (EU style). The Korean
    locale uses 10 t per axle and 40 t gross (Road Act Enforcement Decree), the Japanese locale 10 t axle with a
    general gross limit of 20 t (Vehicle Restriction Order Art. 3), and the US locale 20,000 lb single / 34,000 lb
    tandem / 80,000 lb gross (23 U.S.C. 127). Units follow the locale (kg vs lb).
  - `axle_model` (missing; calculation) — Pallet weight splits between axles by distance from the slot centre to
    each axle (lever rule). The positions are given in `trucks.csv`.
  - `lifo` (ambiguous; business rule) — Within a truck, pallets for a later stop must never sit closer to the
    doors than pallets for an earlier stop.
  - `stacking` (ambiguous; data semantics) — `stackable=N` means nothing goes on top. Fragile pallets are only on
    tier 2. Stacked height ≤ 260 cm.
  - `adr_mix` (missing; business rule) — ADR class 3 pallets never share a truck with class 5.1 (oxidisers),
    based on ADR mixed-loading prohibitions.
  - `one_order_one_truck` (missing; business rule) — An order is never split across trucks (the consignee
    signs one delivery note).
  - `cost` (missing; scoring) — Cost = €180 per truck used + €1.10 per route km. Arriving outside the window
    costs €2 per minute.
  - `rigid_only` (missing; data semantics) — Stops flagged `urban=Y` accept only the 7.2 m rigid truck.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| axle_limits | physical | Computed axle loads ≤ legal caps | Road law; an overweight axle is never acceptable |
| stacking_height | physical | Stack rules and ≤ 260 cm | Load security and door height |
| adr_segregation | physical | No class 3 + 5.1 in the same truck | Dangerous-goods law |
| lifo_order | contractual | Door-to-cab order matches the stop sequence | Agreed handling standard with consignees |
| order_integrity | contractual | Each order delivered whole, exactly once | Delivery-note contract |
| one_customer_per_truck | business_policy | No truck serves two different customers | Sales promised dedicated trucks to key shippers. Keeping it adds 2-3 trucks (about 8-12% cost) |

- **Objective** — Minimize cost. Reference: sweep stops by angle, fill trucks by first-fit decreasing with
  LIFO slotting, repair axle overloads by moving heavy pallets toward the axle centre, then 2-opt each route.
  A coupled load-and-route search leaves about 8% headroom.
- **Hard tier** — Duplicate pallet rows, and a stale `trucks_backup.csv` with an old axle position. Twist: a
  weighbridge correction arrives mid-task and raises six pallets by 200-400 kg, so an axle-legal plan becomes
  illegal.
- **Policy & language angles** — Under `regulated_strict` the agent must ask about axle law rather than assume
  gross weight only. `startup_velocity` rewards accepting the stated EU caps quickly. Localize kg/lb, the axle
  regime by locale, ADR class labels (위험물/危険物/危险品/mercancías peligrosas) and decimal commas in `es`.
- **Authoring risks** — The axle model must be fully specified (axle positions, lever formula), or the rule
  becomes a guessing game. Make sure at least one feasible plan exists under the policy rule.
- **Sources**
  - https://ops.fhwa.dot.gov/Freight/publications/brdg_frm_wghts
  - https://www.c-nexco.co.jp/safety/tokusya/tokusya01.html
  - https://www.ktr.mlit.go.jp/road/sinsei/road_sinsei00000007.html
  - https://www.asiae.co.kr/en/article/2020082410255303655
  - https://www.asiae.co.kr/en/article/2020021810235178784
  - https://learning.sap.com/courses/business-processes-in-sap-s-4hana-transportation-management/planning-loads
  - https://documentserver.uhasselt.be/bitstream/1942/17051/1/orbel28absPollarisetal..pdf
  - https://www.legislation.gov.uk/eudr/2015/719
  - https://www.shipsy.ai/insights/vehicle-capacity-load-planning

---

### EV Fleet Charging Planner — `logistics/ev_fleet_charging_planner`
- **Why it matters** — Depot charging is the main running cost of an electric bus fleet. A 122-bus Shanghai
  study formulated it as a mixed-integer program over time-of-use slots with SoC bounds and station power
  limits. Smart scheduling cuts cost by up to about 10% under dynamic prices. Battery wear, not electricity, can
  dominate total cost, and Fraunhofer IVI found that running about 20 points below a permanent 95-100% SoC
  noticeably slows ageing.
- **Client & request** — Municipal bus operator: "Plan tonight's charging for our electric buses so everyone
  can do their morning block, as cheaply as possible."
- **Deliverable** — Batch `charging.csv` with columns `bus_id, charger_id, slot_start (HH:MM), kw`. Slots are 15
  minutes, from 20:00 to 07:45 the next day.
- **World & data** — 40 buses, 14 chargers (10 × 60 kW, 4 × 150 kW DC), and a 15-minute tariff. Files:
  `buses.csv` (bus_id, battery_kwh, arrival, soc_arrival_pct, first_block_id), `blocks.csv` (block_id,
  departure, km, route_type), `chargers.csv` (charger_id, max_kw, connector), `tariff.csv` (band, start, end,
  price_per_kwh). Hidden in the world: kWh/km per route type and tomorrow's temperature.
- **Hidden requirements**
  - `departure_soc` (missing; calculation) — Departure SoC ≥ block energy + 20% reserve. Energy = km ×
    kWh/km, where kWh/km is 1.1 (urban) or 0.9 (suburban), plus 15% when the forecast is below 0 °C (heater
    load, as seen in winter operations).
  - `site_cap` (missing; physical) — Total depot draw ≤ 900 kW in every slot (transformer).
  - `taper` (missing; calculation) — Above 80% SoC a charger delivers at most 50% of its rated power.
  - `connector` (ambiguous; data semantics) — Buses with `connector=CCS2` cannot use the 4 pantograph DC chargers.
  - `one_bus_per_charger` (missing; physical) — One bus per charger per slot. Moving a bus to another charger
    costs a 30-minute shunt during which it is not charging.
  - `tariff_bands` (ambiguous; data semantics) — Mid-day and evening bands differ from intuition. The Korean
    locale models the April 2026 KEPCO reform (weekday 11-15 h moved to mid-load, 18-21 h raised to peak). The
    Spanish locale uses the 6-period P1-P6 structure. The US locale adds a demand charge on the monthly 15-minute
    peak kW.
  - `demand_charge` (missing; scoring) — Cost = Σ energy × band price + demand price × the night's maximum
    15-minute site kW.
  - `charger_out` (missing; business rule) — Charger C07 is out of service tonight.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| grid_cap | physical | Site kW ≤ 900 in every slot | Transformer protection |
| charger_power | physical | kW ≤ max (and the taper) | Hardware |
| departure_ready | contractual | SoC at departure ≥ requirement | Service contract with the city |
| connector_fit | physical | Compatible charger | Plug mismatch |
| charge_to_full | business_policy | Every bus leaves at 100% | Depot habit "just in case". It forces charging in expensive bands and raises the peak: about 10-14% more cost, plus battery wear |

- **Objective** — Minimize total night cost. Reference: sort buses by deadline slack, fill the cheapest slots
  first under the site cap, then flatten the peak greedily. LP-based scheduling gives 6-10% headroom.
- **Hard tier** — A legacy-encoded tariff file and duplicate bus rows. Twist: the temperature forecast is
  revised to -3 °C mid-task (the late requirement), so the heater uplift applies.
- **Policy & language angles** — `regulated_strict` asks whether the 20% reserve is a contractual minimum.
  `startup_velocity` accepts the tariff as given. Localize the band names (경부하/중간부하/최대부하, 夜間/昼間,
  谷/平/峰, valle/llano/punta), 24 h times and currency.
- **Authoring risks** — Band times must be explicit in the file. The trap is assuming "night = cheapest", not
  hiding the data. Verify that the cap allows a feasible plan.
- **Sources**
  - https://research.polyu.edu.hk/en/publications/an-optimal-charging-scheduling-model-and-algorithm-for-electric-b/
  - https://www.ivi.fraunhofer.de/en/news/13_optimized-battery-strategies-for-public-transport.html
  - https://bus-news.com/running-electric-fleets-in-winter-what-it-takes-to-stay-in-control/
  - https://arena.gov.au/assets/2024/02/Final-ARENA-Submission-VIC-Gov-Zero-Emission-Buses.pdf
  - https://en.fnnews.com/news/202604141134057843
  - https://research.chalmers.se/publication/530347

---

### Container Yard Planner — `logistics/container_yard_planner`
- **Why it matters** — Rehandles (unproductive moves) are the core yard KPI. HHLA CTB in Hamburg uses ML
  dwell-time prediction to cut import rehandling, and vendors such as INFORM and Kaleris slot containers using
  predicted pickup order. Reefers need power plugs, and dangerous goods need separated blocks under IMDG
  segregation.
- **Client & request** — Terminal yard supervisor: "These boxes come off the vessel tonight. Tell us where to
  stack them so we dig less when the trucks come."
- **Deliverable** — Batch `yard_plan.csv` with columns `container_id, block, bay, row, tier`.
- **World & data** — 4 blocks × 10 bays × 6 rows × max 5 tiers (A: dry, B: dry, R: reefer rows with plugs on
  rows 1-2, D: DG block), 300-420 containers. Files: `containers.csv` (container_id ISO 6346, size 20/40,
  gross_kg, reefer Y/N, imdg_class, un_number, carrier, vgm_kg), `pickups.csv` (container_id, appointment
  slot), `yard.csv` (current occupancy). Hidden in the world: actual pickup order (appointments plus 10% no-shows).
- **Hidden requirements**
  - `reefer_plug` (missing; physical) — Reefers only on plug rows, one plug per slot. Reefer stacks ≤ 3 tiers.
  - `imdg_sep` (missing; physical) — Inside block D, class 3 and class 5.1 must be at least one bay apart
    ("separated from"), and class 1 is not accepted at all.
  - `weight_tier` (ambiguous; business rule) — Never place a container > 5 t heavier on top of a lighter one.
    Use VGM when present, otherwise declared gross.
  - `size_mix` (missing; physical) — A 40' takes two bay positions. No 20' on top of a 40'.
  - `stack_height` (missing; physical) — Max 5 tiers, 4 in block A (ground bearing).
  - `rehandle_def` (missing; scoring) — A rehandle is each container sitting above another whose pickup comes
    first, counted in realized pickup order.
  - `no_show` (ambiguous; data semantics) — Appointments with status `tentative` are picked up at the end of the
    day.
  - `existing` (missing; data semantics) — Containers already in the yard stay where they are.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| plug_capacity | physical | Reefers on plug rows, one per plug, ≤ 3 tiers | No power means cargo loss |
| imdg_segregation | physical | Class 3 and 5.1 at least one bay apart; no class 1 | Dangerous-goods safety |
| stack_limits | physical | ≤ 5 tiers (≤ 4 in block A) | Ground bearing and crane reach |
| size_compatibility | physical | No 20' on top of a 40' | Corner castings |
| weight_order | contractual | No container > 5 t heavier above a lighter one | Terminal handling rules agreed with lines |
| carrier_blocks | business_policy | One carrier per block | Liked for reporting, but it breaks departure-order stacking: about 10-15% more rehandles |
- **Objective** — Minimize realized rehandles + 0.2 × crane gantry distance (bays). Reference: sort by
  appointment and fill stacks so the earliest pickup goes on top, with the feasibility filters applied.
  Look-ahead and no-show-aware placement gives about 10% headroom.
- **Hard tier** — Duplicate container rows with check-digit typos, and a stale `vgm_old.csv`. Twist: the
  shipping line moves a vessel's cut-off two hours earlier (deadline change), which reorders 40 export
  pickups.
- **Policy & language angles** — `regulated_strict` demands escalation before any DG change. Localize block
  names, IMDG class labels and date formats. Container IDs stay ISO 6346 and must not be translated.
- **Authoring risks** — State the segregation rule in yard terms, because IMDG chapter 7.2 distances are written
  for ships. Make the no-show behaviour deterministic from the seed.
- **Sources**
  - https://www.identecsolutions.com/yard-planning-and-block-allocation-industry-knowledge-hub
  - https://www.foodlogistics.com/software-technology/press-release/21159899/hamburg-port-consulting-inform-and-hpc-deliver-machine-learning-at-hhla-ctb
  - https://arxiv.org/pdf/2604.06251
  - https://www.dgg.bam.de/dgginfo/detailinfo/imdg/adcjbgwzyldi?lang=en
  - https://jjkellercompliancenetwork.com/institute/segregation-and-stowage-under-the-imdg
  - https://msc-les.org/proceedings/hms/hms2009/hms2009_127.html

---

### Airline Crew Scheduler — `logistics/airline_crew_scheduler`
- **Why it matters** — Crew is an airline's second-largest cost, and pairing optimization is a long-standing OR
  success. Every pairing must satisfy flight-time limits (FAA Part 117, EASA ORO.FTL), and duty limits depend on
  local report time and the number of sectors. A crew-legality failure cancels flights.
- **Client & request** — Regional airline crew planning lead: "Build next month's pairings for our A320 and
  ATR crews, as efficiently as you can."
- **Deliverable** — Batch `pairings.json`:
  `{"pairings":[{"id":"PR001","base":"ICN","fleet":"A320","duties":[["F1203","F1204"],["F1310"]]}]}`.
  Flight IDs come from the schedule.
- **World & data** — 2 bases, 2 fleets, a 7-day repeating schedule (about 220 legs). Files: `flights.csv`
  (flight_id, dep_airport, arr_airport, dep_utc, arr_utc, fleet), `airports.csv` (code, utc_offset,
  dst_rule), `crew_bases.csv`, `hotel_costs.csv`. Hidden: none beyond the rules (deterministic legality).
- **Hidden requirements**
  - `fdp_table` (missing; calculation) — The maximum FDP depends on report time (base-local) and sectors.
    Modeled on EASA Table 2: 13:00 for 1-2 sectors at 06:00-13:29, falling 30 minutes per extra sector to a
    9:00 floor. The FAA variant (Table B) is used in the US locale.
  - `report_debrief` (missing; calculation) — Report 60 minutes before the first departure, release 30 minutes
    after the last arrival.
  - `min_rest` (missing; physical) — Rest between duties ≥ max(10 h, the preceding duty length).
  - `timezones` (ambiguous; data semantics) — Times are UTC. The FDP band uses the base-local time, including
    DST.
  - `return_base` (missing; business rule) — Pairings start and end at the same base and last at most 4 days.
  - `fleet_qual` (missing; physical) — A pairing stays within one fleet type.
  - `min_connect` (missing; physical) — Connection ≥ 35 minutes on the same aircraft, ≥ 60 minutes when changing
    aircraft.
  - `cost` (missing; scoring) — Cost = paid hours (max of block time and 0.5 × duty time per duty) + overnight
    hotel cost + deadhead.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| fdp_limit | physical | Each duty ≤ table FDP | Aviation law; never bends |
| rest | physical | Rest ≥ max(10 h, previous duty) | Aviation law |
| qualification | physical | One fleet per pairing | Type rating |
| min_connection | physical | ≥ 35 / 60 min | Ground operations |
| coverage_base | contractual | Every flight covered exactly once; return to base in ≤ 4 days | Collective agreement and schedule promise |
| seniority_layovers | business_policy | No overnights in the cities senior crew vetoed | Keeps crews happy but costs 5-8% more paid hours |
- **Objective** — Minimize total cost. Reference: greedy chaining by earliest legal connection, then local
  swaps. Set-partitioning column generation beats it by 8-12%.
- **Hard tier** — Duplicate legs and a DST-shifted backup schedule. Twist: a stakeholder from the union says rest
  must be 12 h. The client confirms the CBA says 11 h for the A320 fleet only.
- **Policy & language angles** — Legality never bends. `enterprise_balanced` should justify every deadhead.
  Localize airport display names (codes unchanged) and date formats. The Korean, Japanese and Chinese locales
  carry their own regulator naming (MOLIT, JCAB, CAAC CCAR-121) with the same table so scoring stays identical.
- **Authoring risks** — Give the FDP table explicitly in the requirements, because real tables differ by
  regulator. Keep the schedule small enough that a feasible cover exists without a solver.
- **Sources**
  - https://regulatorylibrary.caa.co.uk/965-2012/Content/Regs/05130_ORO.FTL.205_Flight_duty_period_FDP.htm
  - https://www.easa.europa.eu/en/faq/47591
  - https://www.aviatize.com/glossary/far-part-117
  - https://www.ctsys.com/?p=14959
  - https://far117understanding.com/wp-content/uploads/2021/03/alpa-guide-far-117-2019-5a.pdf
  - https://www.icao.int/Meetings/a40/Documents/WP/wp_445_en.pdf

---

### Delivery ETA Modeler — `logistics/delivery_eta_modeler`
- **Why it matters** — DoorDash moved from tree models to a mixture-of-experts model with probabilistic outputs
  (a reported 20% gain), and its DeeprETA system post-processes routing-engine ETAs with a residual network.
  Practitioners agree that clean, timestamped event logs matter more than model choice. Timezone and DST
  handling is a named pitfall, and the business cares about lateness against the promise, not MSE.
- **Client & request** — Grocery quick-commerce ops lead: "Give us something that predicts delivery time for
  each order."
- **Deliverable** — Program `eta(order: dict) -> {"minutes": float, "window": [lo, hi]}` in `eta.py`, run on
  hidden future orders.
- **World & data** — 3 cities (one across a timezone boundary), 6 months of orders (about 60k). Files:
  `orders.csv` (order_id, store_id, created_at, promised_minutes, items, basket_kg), `deliveries.csv`
  (order_id, picked_at, delivered_at, courier_id), `gps_pings.csv`, `stores.csv` (lat, lon, city, tz),
  `calendar.csv`. Hidden: future delivery durations.
- **Hidden requirements**
  - `tz_mix` (ambiguous; data semantics) — `created_at` is UTC. `delivered_at` is store-local without an offset.
    City C changed DST rules.
  - `gps_noise` (missing; data semantics) — Pings with accuracy > 50 m or speed > 120 km/h are noise.
  - `target_def` (ambiguous; calculation) — Duration runs from `created_at` to the courier's handover scan, not
    to the app's "delivered" tap (which can lag).
  - `holidays` (missing; data semantics) — Local public holidays (Chuseok, Golden Week, Spring Festival, Semana
    Santa by locale) add traffic and order volume.
  - `metric` (missing; scoring) — Score = share of orders delivered inside [lo, hi] − 2 × the share delivered
    after hi. The window width is at most 20 minutes.
  - `leakage` (missing; data semantics) — `picked_at` and courier_id are not known at prediction time.
  - `cancelled` (missing; data semantics) — Cancelled orders have no delivery time. They are excluded, not set to
    zero.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| valid_output | physical | Returns a finite number, lo ≤ minutes ≤ hi, for every hidden order | Program contract |
| window_width | contractual | hi − lo ≤ 20 min | Promise rules in the customer app terms |
| min_promise_30 | business_policy | lo ≥ 30 min | Marketing avoids over-promising, but it costs window-hit in dense zones (about 5-9%) |

Leakage fields are simply absent from the hidden input dict, so leakage cannot be scored by a rule.
- **Objective** — Maximize the score above. Reference: a per-store median duration by hour × weekday, plus a
  holiday uplift and a fixed ±8-minute window. Gradient-boosted quantiles give 8-12% headroom.
- **Hard tier** — Duplicate orders and a CP949/Shift_JIS backup file. Twist: the data team corrects `tz` for
  one store mid-task.
- **Policy & language angles** — `regulated_strict` (consumer-protection advertising rules) needs the agent to
  document the promise logic. Localize holiday names and timestamps. Spanish data uses dd/mm/yyyy.
- **Authoring risks** — The DST trap must be learnable from data plus one answer. Leakage fields should be
  absent from the hidden input dict, so the evaluator does not depend on honesty.
- **Sources**
  - https://arxiv.org/abs/2206.02127
  - https://careersatdoordash.com/?p=12391
  - https://algomaster.io/learn/ml-system-design/design-eta-prediction-system
  - https://www.upperinc.com/blog/eta-accuracy-in-customer-notifications/
  - https://racklify.com/encyclopedia/smarter-shipping-starts-here-unlocking-the-power-of-predictive-eta/

---

### Freight Invoice Auditor — `logistics/freight_invoice_auditor`
- **Why it matters** — Freight invoices are error-prone. Common faults are DIM weight with the wrong divisor,
  fuel surcharge against the wrong index week, unauthorized accessorials (detention, reweigh), and the same
  invoice re-sent under a new reference. AI audit tools match each line against the contract and send
  differences to human review before payment.
- **Client & request** — Shipper's logistics finance manager: "Check last month's carrier invoices before we pay
  them and tell us what's wrong."
- **Deliverable** — Batch `audit.csv` with columns `invoice_id, line_no, status (ok|adjust|reject),
  approved_amount, reason_code (DIM|FUEL|ACC|DUP|RATE|TAX|OK)`.
- **World & data** — 3 carriers, about 900 invoice lines. Files: `invoices.csv` (invoice_id, carrier, ship_date,
  shipment_id, charge_type, amount, currency, tax_id), `shipments.csv` (shipment_id, actual_kg, l/w/h_cm, lane,
  service), `contracts/rates_<carrier>.csv`, `fuel_index.csv` (week, price), `pod_events.csv` (arrival,
  unload times). Hidden: the true overcharge for each line.
- **Hidden requirements**
  - `dim_divisor` (missing; calculation) — Billable kg = max(actual, L×W×H/divisor). The divisor is 5000 for
    carrier A express and 6000 for B. The US locale uses inches and 139 lb.
  - `fuel_table` (missing; calculation) — Surcharge % comes from the index two weeks before the ship date. The
    Spanish locale models the mandatory fuel-revision clause in road haulage contracts.
  - `detention` (missing; business rule) — Detention is payable only beyond 2 free hours, by POD timestamps,
    at €40/h.
  - `duplicate` (ambiguous; data semantics) — The same shipment, charge and amount within 60 days is a duplicate,
    even with a different invoice number.
  - `tax_doc` (missing; business rule) — The Japanese locale needs a qualified-invoice registration number
    (from the October 2023 invoice system). Lines without one get reduced input-tax credit, so status is
    `adjust`.
  - `tolerance` (missing; scoring) — Differences under 1% or ¥/₩/€ equivalent of 2 are `ok`.
  - `currency` (ambiguous; data semantics) — Carrier C bills in USD. Convert at the month-end rate in the file.
  - `scoring` (missing; scoring) — The value is recovered overcharge minus 3 × wrongly rejected amounts.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| tax_compliance | physical | No line approved in full without the required tax document | Tax law; a legal hard limit |
| no_overpay_contract | contractual | approved_amount ≤ contract-correct amount | Carrier contract |
| one_status_per_line | contractual | Every invoice line audited exactly once | AP payment run |
| pay_small_lines | business_policy | Lines < €50 approved as billed | Saves AP time, but lets about 6-10% of recoverable value through |
- **Objective** — Maximize the net recovery. Reference: rule checks for DIM, fuel, detention and exact
  duplicates. Fuzzy duplicate matching and rate-lane inference give about 10% headroom.
- **Hard tier** — Duplicate rows, a stale contract file with last year's rates, and legacy encoding. Twist: the
  carrier sends a credit note mid-task.
- **Policy & language angles** — `regulated_strict` escalates every reject above €1,000. Localize currency, tax
  IDs (T + 13 digits for JP, 사업자등록번호 for KR, 统一社会信用代码 for CN, NIF/RFC for ES), decimal commas and
  units.
- **Authoring risks** — Give every contract parameter in files or in answers. Do not count tax rules from
  memory; state them in the requirements.
- **Sources**
  - https://shipware.com/blog/shipping-surcharge-audit-guide
  - https://dash.fi/blog/shipping-overcharges
  - https://smartdev.com/ai-freight-audit-bill/
  - https://www.stacksync.com/use-case/freight-invoicing-and-audit
  - https://vektortms.com/brokers/billiq
  - https://www.nta.go.jp/taxes/shiraberu/zeimokubetsu/shohi/keigenzeiritsu/invoice_about.htm

---

**Research note.** The shared web-search budget ran out partway through. Some locale facts are from general
knowledge and must be checked against the primary text before a case is authored: Spain's fuel-revision and
waiting-time rules (Ley 15/2009 / RDL 3/2022), CAAC CCAR-121 duty tables, China's 9% transport VAT and Japan's
transitional input-tax credit rates. The cases themselves state every number in their requirements, so scoring
never depends on outside law.
