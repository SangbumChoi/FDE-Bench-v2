# Healthcare — case specs

Most real hospital AI deployments are on the operations side, not the diagnostic side. Examples are capacity command centers that predict discharges and match patients to beds, case-length models that schedulers check when they post a surgery, no-show models that drive reminders and overbooking, autonomous coding engines that auto-accept codes they are confident about, and feasibility tools that rank trial sites. Published results are mixed. Duke's prospectively deployed case-length model beat schedulers' own estimates by only a few percentage points. Most bed-flow and coding claims come from vendors and have not been independently checked. A widely cited study showed that predictive overbooking can make Black patients wait up to 30% longer. The hard part is therefore rarely the algorithm. It is the rules that sit around it: licensing ratios and rest law, infection control, payer edits, controlled-substance law and sponsor commitments to regulators. These rules differ between the US, the EU/Spain, Korea, Japan and China, and the client seldom states them. The seven unbuilt roles below are all in the catalog, and none was replaced; `hospital_appointment_scheduler` is already built.

| Role | Task type | Deliverable | Hook |
|---|---|---|---|
| Emergency Bed Manager | Optimization | Batch `bed_assignments.csv` | "Pending" discharges never leave; C. diff rooms need a 2-hour terminal clean |
| Nurse Shift Planner | Optimization | Batch `roster.csv` | Fixed ratios with no averaging, an 11-hour rest rule and a 72-night-hour cap |
| Operating Room Scheduler | Optimization | Batch `or_schedule.csv` | Booked minutes leave out anesthesia time; hip trays need 4 h of sterile processing |
| Pharmacy Inventory Planner | Optimization (stochastic) | Batch `orders.csv` | Demand history is in doses while orders are in packs; FEFO waste; controlled-drug order caps |
| Patient No-Show Predictor | ML + policy | Batch `predictions.csv` + `overbook.csv` | The reminder-call column leaks; late cancels count as no-shows |
| Medical Claims Coder | Rules + extraction | Batch `diagnoses.csv` + `claim_lines.csv` | Bundling edits, unit caps, the 8-minute rule, and "suspected" diagnoses are not coded |
| Clinical Trial Site Selector | Optimization (simulation) | Batch `site_plan.csv` | 11% of sites never activate; the enrollment count column mixes screened and randomized patients |

---

### Emergency Bed Manager — `healthcare/emergency_bed_manager`

- **Why it matters** — ED boarding (an admitted patient waiting in the ED for a ward bed) drives crowding and harm. CMS's 2026 outpatient rule finalized an access measure that flags any wait over 4 hours from the decision to admit until the patient leaves the ED. Command centers such as Bradford's in the UK and Humber River in Canada say they freed bed capacity largely by getting bed allocation right. NHS same-sex accommodation guidance makes mixed-sex placements reportable breaches.
- **Client & request** — The patient-flow manager writes: "Can you assign the expected admissions to ward beds for the next 72 hours? We want people out of the ED faster."
- **Deliverable** — Batch `bed_assignments.csv` with columns `admission_id,bed_id,assign_time`. `assign_time` is `YYYY-MM-DD HH:MM` in hospital local time. A patient left out of the file boards until the horizon ends. Each admission appears at most once.
- **World & data** — 6 wards, 148 beds. The wards are Medical A and Medical B (4-bed bays plus single rooms), Surgical, Orthopedics, Step-down (10 monitored beds) and Pediatrics (14 beds). 4 single rooms have negative pressure. The agent receives these files:
  - `beds.csv` (`bed_id, ward, room_id, room_type, negative_pressure`)
  - `current_patients.csv` (148 rows: `bed_id, sex, isolation, discharge_time, discharge_status`)
  - `admissions.csv` (about 210 rows: `admission_id, dta_time, birth_date, sex, service, acuity, isolation_code`)
  - `ward_rules.txt`

  New admissions are stated to stay beyond the horizon. Hidden in the world: which pending discharges actually happen. None do inside the horizon.
- **Hidden requirements**
  - `pending_discharge` (ambiguous; data semantics) — Only `discharge_status = confirmed` frees a bed at `discharge_time`. A `pending` discharge waits on a physician decision and does not happen within 72 h. This is modeled on "expected discharge" lists, which bed managers know are optimistic.
  - `cleaning_time` (missing; calculation) — A bed is ready 60 min after a discharge, or 120 min if the leaving patient was on contact isolation. The longer time reflects sporicidal terminal cleaning, where bleach products need about 10 min of wet contact time and isolation cleans take measurably longer.
  - `airborne` (missing; business rule) — Isolation codes `AIR` (TB, measles, varicella) go only to negative-pressure rooms. This follows the CDC rule on airborne infection isolation rooms.
  - `contact_cohort` (ambiguous; business rule) — `MRSA`, `VRE` and `CDI` patients need a single room. Alternatively, a bay may hold only patients with the same organism code. This is cohorting as practiced under HICPAC.
  - `same_sex_bays` (missing; business rule) — Every occupant of a 4-bed bay must share the same sex at every moment. Single rooms and Step-down are exempt. This follows the NHS rule that mixing is justified only in high-dependency care.
  - `step_down` (missing; business rule) — `acuity = 3` (telemetry or non-invasive ventilation) goes only to Step-down. Step-down beds take only acuity 3.
  - `pediatric_age` (ambiguous; data semantics) — Age is computed from `birth_date` at `dta_time`. Patients under 16 go to Pediatrics only. Patients aged 16 or over never go there.
  - `boarding_metric` (missing; scoring) — Boarding runs from `dta_time` to `assign_time`, and the 4-hour threshold carries an extra penalty (see Objective).
  - `surgical_reserve` (missing; business rule) — The surgical director wants 4 Surgical beds empty at 07:00 every day for elective post-op patients.
- **Rules**

  | id | class | check | why |
  |---|---|---|---|
  | `one_patient_per_bed` | physical | No overlap with a current patient (pending discharges included) or another admission; cleaning buffer respected; `assign_time` ≥ `dta_time` | A bed holds one body |
  | `airborne_negative_pressure` | physical | Every AIR patient is in a negative-pressure room | Room engineering, not choice |
  | `step_down_acuity` | physical | Acuity 3 ↔ Step-down | Monitoring equipment exists only there |
  | `contact_isolation` | contractual | Single room or same-organism bay | Infection-control policy and accreditation |
  | `same_sex_bays` | contractual | No mixed bay at any minute | National standard; reportable breach |
  | `pediatric_ward` | contractual | Under 16 ↔ Pediatrics | Safeguarding policy |
  | `surgical_reserve` | business_policy | ≥4 empty Surgical beds at each 07:00 | Holding beds empty lengthens ED boarding for surgical and outlier patients |
- **Objective** — Minimize Σ boarding hours + 10 per patient boarding more than 4 h + 2 per medical patient placed on Surgical or Ortho (outlier) + (hours to horizon end + 24) per patient not assigned. Reference: process patients in `dta_time` order, take the earliest-ready feasible bed with the home ward preferred, and keep the reserve. A lookahead that saves single rooms for the isolation patients who arrive later should gain about 8-12%.
- **Hard tier** — Duplicate admission rows (re-registered patients), a stale `beds_backup.csv` that still lists 2 decommissioned beds, and a corrected `current_patients.csv` arriving mid-task in which 3 pending discharges become confirmed. Twist: a stakeholder conflict. The infection-prevention nurse emails that VRE must never cohort. That nurse is not the owner; the client confirms that cohorting is allowed.
- **Policy & language angles** — `regulated_strict`: keep the surgical reserve and document every cohorted bay. `startup_velocity`: relaxing the reserve is a justified gain. `enterprise_balanced`: escalate first. Localize ward names and isolation labels (MRSA, 접촉격리, 接触予防策, 接触隔离, aislamiento de contacto). Use 24-hour times in every locale. Show Japanese birth dates in Western years, never the 和暦 era calendar. Spanish uses dd/mm/yyyy.
- **Authoring risks** — The world must guarantee that a feasible plan exists with the reserve kept. Isolation codes must be unambiguous in every language. Do not let the agent learn the pending-discharge truth from the data itself, for example from a `pending` patient whose discharge time falls before the horizon.
- **Sources** — https://www.england.nhs.uk/long-read/delivering-same-sex-accommodation/ · https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2013/04/MSA-FAQ-v1.1-Final.pdf · https://www.cdc.gov/infection-control/hcp/basics/transmission-based-precautions.html · https://www.beckershospitalreview.com/care-coordination/ed-boarding-patients-often-wait-hours-for-an-inpatient-team-7-study-notes/ · https://ecqi.healthit.gov/ecqm/EH/2023/CMS111v11 · https://www.cambridge.org/core/services/aop-cambridge-core/content/view/E53CD196190EDFEEC29A29A425429F9D/S0899823X20007564a.pdf · https://www.healthcarefacilitiestoday.com/posts/Benchmarks-for-hospital-room-cleaning-times--11631 · https://www.ge.com/news/reports/the-english-patients-this-uk-hospital-is-harnessing-ai-to-deliver-slicker-service

---

### Nurse Shift Planner — `healthcare/nurse_shift_planner`

- **Why it matters** — Nurse rostering is the standard OR benchmark problem (INRC-II separates hard rules from weighted soft ones), and the hard rules are law. California Title 22 §70217 sets per-unit ratios that hold "at all times", with no averaging. The EU Working Time Directive requires 11 h of daily rest, and Spain's 2026 Estatuto Marco draft raises that to 12 h. Japan's fee schedule cuts payment when average night hours exceed 72 per month. Korea ties inpatient nursing fees to grades based on patients per nurse.
- **Client & request** — The director of nursing writes: "Please make next month's roster for our three wards. Fair to everyone, and safe."
- **Deliverable** — Batch `roster.csv` with columns `nurse_id,date,shift,ward_id`. `shift` is one of `D` (07-15), `E` (15-23) or `N` (23-07, counted on its start date). One row per worked shift.
- **World & data** — December 2026 (31 days). Three wards: ICU (12 beds), Med-Surg (30 beds) and Pediatrics (16 beds). 74 nurses, 8 of them floats. Files:
  - `nurses.csv` (`nurse_id, home_ward, fte, hire_date, icu_cert, pals_cert, float`)
  - `census_forecast.csv` (`ward, date, shift, patients`)
  - `leave.xlsx` (`nurse_id, date, status`, where status is approved or requested)
  - `prior_week.csv` (the last 7 days of November)

  Hidden: nothing stochastic. Correctness is about the rules.
- **Hidden requirements**
  - `ratio` (missing; calculation) — Required nurses = ceil(patients / r), with r = 2 for ICU, 5 for Med-Surg and 4 for Pediatrics. This is required per shift with no averaging, modeled on Title 22.
  - `rest_11h` (missing; business rule) — At least 11 h between the end of one shift and the start of the next. After an N shift the next day can only be N or off, and an E shift cannot be followed by a D shift. The rule spans the boundary with `prior_week.csv`. Modeled on the EU WTD Art. 3.
  - `night_cap` (missing; business rule) — At most 9 N shifts (72 h) per nurse per month and at most 3 consecutive. Modeled on Japan's 72-hour rule.
  - `skills` (missing; business rule) — Only `icu_cert` nurses work in the ICU. Every Pediatrics shift has at least one `pals_cert` nurse. Floats may work any ward their certifications allow.
  - `leave_status` (ambiguous; data semantics) — `approved` leave is binding. `requested` days off are preferences that carry a penalty when not met.
  - `fte_shifts` (missing; calculation) — Target shifts = round(fte × 21) ± 1 (8-hour shifts). No more than 5 consecutive working days.
  - `seniority` (ambiguous; data semantics) — Years of experience are counted from `hire_date` to 2026-12-01. In ja and ko the file shows `hire_date` in the local format.
  - `senior_on_shift` (missing; business rule) — The client's own rule: every ward and shift has a nurse with at least 5 years of experience.
  - `scoring` (missing; scoring) — See Objective.
- **Rules**

  | id | class | check | why |
  |---|---|---|---|
  | `one_shift_per_day` | physical | At most 1 row per nurse per date; known nurse and ward | A person is in one place |
  | `staffing_ratio` | contractual | Staff ≥ required on every ward, date and shift | Licensing law, with no averaging |
  | `rest_and_nights` | contractual | 11 h rest, night cap, at most 5 consecutive days | Labor law and fee rules |
  | `approved_leave` | contractual | No shift on approved leave | Labor agreement |
  | `certification` | contractual | ICU and PALS skill rules | Scope of practice |
  | `senior_on_shift` | business_policy | At least one senior per ward and shift | Seniors are scarce, so keeping the rule costs unmet requests and pushes extra nights onto seniors |
- **Objective** — Minimize 3 × requested days off not granted + 2 × FTE target deviations beyond ±1 + 1 × staff above requirement + 4 × each nurse's nights above 6 + 2 × single isolated days off. Reference: day-by-day greedy fill (nights first) using fewest-assigned-first. A local-search swap pass should gain about 10%.
- **Hard tier** — A CP949/Shift_JIS `leave.xlsx` export, duplicated leave rows, and a late requirement: two nurses come back from maternity leave on 12-14 Dec. Twist: deadline pulled in. The roster must be posted 2 weeks ahead, so week 1 is frozen to an attached draft that has to be completed without changes.
- **Policy & language angles** — `regulated_strict`: keep the senior rule and write down every assumption about ratios. `startup_velocity`: relaxing the senior rule is the obvious justified gain. Locale pitfalls: shift labels (日勤/準夜/深夜, 데이/이브닝/나이트, 白班/小夜班/大夜班, mañana/tarde/noche) must map to D/E/N, and the Spanish week starts on Monday.
- **Authoring risks** — The ratio, rest and leave rules must leave a feasible roster under the senior rule. Do not make the 12 h Spanish draft rule apply only in `es`: the world uses 11 h everywhere and the requirements say so.
- **Sources** — https://www.law.cornell.edu/regulations/california/Cal-Code-Regs-Tit-22-SS-70217 · https://www.cdph.ca.gov/Programs/CHCQ/LCP/Pages/AFL-07-26.aspx · https://www.translation-centre.am/pdf/Translat/EU_Direct/Social/Dir_2003_88_en.pdf · https://www.sanidad.gob.es/areas/profesionesSanitarias/PregFrecEstatutoMarco.htm · https://www.kango-roo.com/work/5910/ · https://nursing.jhu.edu/wp-content/uploads/2023/02/Improvement-Plan-of-Nurse-Staffing-Standards-in-Korea.pdf · https://arxiv.org/pdf/1501.04177

---

### Operating Room Scheduler — `healthcare/operating_room_scheduler`

- **Why it matters** — OR time is the most expensive capacity a hospital has. Benchmarks are an 80% block utilization target and about 30-minute turnovers. Duke deployed a gradient-boosting case-length model at case posting, and it improved on schedulers' estimates by about 3-11 points. Elective cancellations are often caused by a missing ICU bed or a missing instrument tray: SPD conflict checks are frequently ignored, and loaner sets arrive late.
- **Client & request** — The perioperative director writes: "Schedule next week's surgeries from the waiting list. Use the rooms well and avoid overtime."
- **Deliverable** — Batch `or_schedule.csv` with columns `case_id,room_id,date,start`, where `start` is `HH:MM`, the time the patient enters the room. Unscheduled cases are left out.
- **World & data** — 6 ORs, Mon-Fri 2026-11-30 to 12-04, 08:00-17:00. 150 waiting cases. Files:
  - `cases.csv` (`case_id, surgeon_id, procedure, booked_minutes, anesthesia, priority, target_date, patient_age, icu_required, isolation, latex_allergy`)
  - `surgeons.csv` (availability by day)
  - `equipment.csv` (robot ×1, C-arm ×2, laser ×1)
  - `trays.csv` (set types and counts, for example `HIP-01` ×2)
  - `icu_slots.csv` (elective ICU beds per day: 2, 2, 1, 2, 1)
- **Hidden requirements**
  - `room_time` (ambiguous; data semantics) — `booked_minutes` is incision to closure. Room occupancy adds 30 min for `GA` and 15 for `regional/sedation`.
  - `turnover` (missing; calculation) — 30 min between cases in a room. A contact-isolation case needs 60 min after it, which in practice means scheduling it last.
  - `tray_reprocessing` (missing; business rule) — A tray set can be reused only 240 min after its case ends (the SPD cycle). Concurrent cases cannot exceed the set count.
  - `equipment_conflict` (missing; business rule) — Robot, C-arm and laser cases cannot overlap beyond the unit counts.
  - `icu_bed` (missing; business rule) — The number of `icu_required` cases per day cannot exceed that day's ICU slots.
  - `priority_deadline` (missing; business rule) — `P2` cases (for example cancer) must happen on or before `target_date`.
  - `overtime_cap` (missing; business rule) — A room may run to 18:00 at the latest. Minutes after 17:00 are overtime.
  - `latex_first` (missing; business rule) — A latex-allergy patient is the first case of the day in their room, as is common practice after a room has stood clean overnight.
  - `peds_first` (missing; business rule) — The client's habit: patients under 12 start before 10:00 because of fasting.
- **Rules**

  | id | class | check | why |
  |---|---|---|---|
  | `room_no_overlap` | physical | Room time plus turnover do not overlap; inside 08:00-18:00 | A room is physically busy |
  | `surgeon_no_overlap` | physical | Surgeon is available and in one room at a time | One person |
  | `equipment_and_trays` | physical | Unit and tray counts, 240 min reprocessing | Sterile-processing physics |
  | `icu_capacity` | physical | ICU slots per day | No post-op bed means no surgery |
  | `priority_deadline` | contractual | All P2 cases scheduled by target date | Waiting-time standard |
  | `latex_first` | contractual | First case of the day | Patient-safety protocol |
  | `peds_first` | business_policy | Patients under 12 start before 10:00 | Takes prime first-case slots and clashes with latex-first and with equipment, so total value drops |
- **Objective** — Maximize Σ booked minutes of scheduled cases (P2 weight 2, P3 weight 1) − 2 × overtime minutes. Reference: by priority then target date, longest-processing-time first-fit into rooms, with the surgeon's cases kept in one room. Bin-packing improvement should add about 6-10%.
- **Hard tier** — A stale `trays_backup.csv` that shows 3 hip sets instead of 2, duplicate case rows after re-posting, and a data correction: ICU slots on Thursday drop to 0. Twist: the client is unavailable for a day, and a surgeon emails asking for a whole Tuesday room. The surgeon is not the owner, and the request conflicts with a P2 deadline.
- **Policy & language angles** — `regulated_strict`: keep pediatrics first. `startup_velocity`: break it where it buys a P2 case. Localize procedure names, but keep the IDs. Durations stay in minutes everywhere. The Japanese and Korean data use 午前/오전 labels in a display column only.
- **Authoring risks** — Latex-first and peds-first must never be jointly infeasible for the reference. The anesthesia add-on must be inferable only by asking.
- **Sources** — https://pmc.ncbi.nlm.nih.gov/articles/PMC10631498 · https://scholars.duke.edu/publication/1582437 · https://www.beckershospitalreview.com/uncategorized/5-key-indices-for-a-high-performing-or/ · https://impact-advisors.com/article/surgical-block-utilization · https://leantaas.com/?p=1331 · https://infectioncontroltoday.com/view/conflict-schedule-checker-tool-spd-instrument-management · https://www.casechek.com/how-sterile-processing-teams-navigate-vendor-tray-chaos/ · https://www.cirrelt.ca/DocumentsTravail/CIRRELT-2020-10.pdf · https://www.frontiersin.org/articles/10.3389/frhs.2021.787358

---

### Pharmacy Inventory Planner — `healthcare/pharmacy_inventory_planner`

- **Why it matters** — Hospital pharmacies balance stockouts, which delay critical therapy, against expired-drug waste. Vendor case studies report inventory turns rising from about 6.3 to 8.4 and waste falling by a third with min/max reordering. ASHP's shortage guidelines require formally approved therapeutic alternatives. Controlled drugs carry legal ordering rules: DEA Form 222/CSOS under 21 CFR 1305 in the US, and Korea's NIMS reporting with lot and expiry for each transaction. Research prototypes now turn probabilistic demand forecasts into replenishment rules.
- **Client & request** — The pharmacy director writes: "Plan our drug orders for the next six weeks. No stockouts, and less waste please."
- **Deliverable** — Batch `orders.csv` with columns `order_date,item_id,supplier_id,packs`. `order_date` must be a Monday or Thursday in the horizon, and `packs` is an integer.
- **World & data** — 60 SKUs: 8 cold-chain items, 5 Schedule II items and 4 on shortage, each with an approved substitute. Files:
  - `items.csv` (`item_id, pack_size, unit, pack_cost, pack_volume_l, storage, controlled, critical`)
  - `lots.csv` (on hand: `item_id, lot, qty_units, expiry`)
  - `dispensing_history.csv` (52 weeks of daily units)
  - `suppliers.csv` (`lead_time_bd, moq_packs, shelf_life_days_on_arrival, allocation_cap`)
  - `substitutes.csv`
  - `holidays.txt`

  Hidden: 42 days of actual daily demand, drawn from the seeded process behind the history. It includes a known flu-season uplift on 6 items.
- **Hidden requirements**
  - `units_vs_packs` (ambiguous; data semantics) — History counts doses or vials. Orders are in packs of `pack_size`.
  - `fefo` (missing; calculation) — The simulation uses the earliest-expiring stock first. Units past expiry are wasted, and incoming lots expire `shelf_life_days_on_arrival` after receipt.
  - `lead_time_bd` (ambiguous; calculation) — Lead time counts business days and skips the dates in `holidays.txt`. Stock arrives at the start of the arrival day.
  - `cold_chain` (missing; business rule) — Refrigerated stock on hand must stay within 900 L at every end of day. This mirrors dedicated 2-8 °C units.
  - `controlled_cap` (missing; business rule) — Schedule II orders cannot exceed 1.5 × the item's average monthly dispensing over the last 3 months, per 28 days. This is the wholesaler's suspicious-order threshold.
  - `shortage_sub` (missing; business rule) — Allocated items cap at `allocation_cap` packs per order. Demand may be met by the substitute at the conversion factor (for example 1 A = 2 B).
  - `moq_budget` (missing; business rule) — Respect MOQ. Total spend must be at or under the stated budget.
  - `safety_two_weeks` (missing; business rule) — The client's habit: on hand plus on order covers 14 days of average demand after every order.
  - `scoring` (missing; scoring) — See Objective.
- **Rules**

  | id | class | check | why |
  |---|---|---|---|
  | `valid_order_days` | physical | Order day, integer packs, known supplier | Ordering system |
  | `fridge_capacity` | physical | 900 L cold-chain limit | Refrigerator volume |
  | `controlled_cap` | contractual | Schedule II cap per 28 days | Diversion-control law and wholesaler agreement |
  | `allocation_and_moq` | contractual | Allocation caps, MOQ | Supplier contracts |
  | `budget` | contractual | Spend ≤ budget | Finance mandate |
  | `safety_two_weeks` | business_policy | 14-day cover for every SKU | Forces extra stock of slow and short-dated items, which costs expiry waste and fridge space |
- **Objective** — Minimize purchase cost + 0.5% of stock value per week (holding) + value of expired units + stockout penalty. The penalty is 5 × unit cost for each unit short, or 20 × for items flagged `critical`. It is computed by FEFO simulation against the hidden demand. Reference: periodic review with order-up-to = (lead time + review period) × 8-week moving average + 1.65σ, rounded to packs. Seasonality and short-dated handling should gain about 8-12%.
- **Hard tier** — A legacy-encoded `items.csv`, duplicated lot rows, and a data correction: supplier S3's lead time doubles in week 3. Twist: a late requirement. A new shortage notice puts a fifth item on allocation mid-task.
- **Policy & language angles** — `regulated_strict`: never bend the 14-day cover, and document the substitute mappings. `startup_velocity`: drop the cover on slow movers. Localize item names (generic INN), storage labels and currency symbols, but keep costs as plain numbers. Holidays are given in the data so that locale calendars (설날, 正月, 春节) are never assumed.
- **Authoring risks** — The demand process must be learnable from the history, with the uplift visible in last year's data. Make the scoring penalty for a stockout greater than the cost of holding.
- **Sources** — https://www.completerx.com/significant-savings-and-profitability-achieved-by-streamlining-pharmacy-inventory/ · https://www.cleverence.com/articles/for-business/hospital-pharmacy-inventory-management-best-practices-4821/ · https://beckersasc.com/asc-supply-chain-materials-management/ashp-releases-revised-drug-shortage-guidelines-4-important-details-to-know.html · https://files.asprtracie.hhs.gov/documents/csc-considerations-supply-shortages.pdf · https://www.federalregister.gov/documents/2023/02/02/2023-01804/controlled-substances-ordering-system-csos-modernization · https://www.dailyvet.co.kr/tag/nims · https://www.cdc.gov/vaccines/hcp/downloads/vaccine-storage-troubleshooting-worksheet.pdf · https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10009839/ · https://neurips.cc/virtual/2026/177311

---

### Patient No-Show Predictor — `healthcare/patient_no_show_predictor`

- **Why it matters** — A Penn State model trained on more than 1 million appointments reached an AUROC of 0.85, with booking lead time the strongest predictor. Huang and Hanauer cut overtime by 27% with predictive overbooking. Samorani et al. showed that overbooking individual high-risk patients made Black patients wait up to 30% longer, so how overbooking is done matters as much as how accurate the model is.
- **Client & request** — The outpatient operations lead writes: "Predict who won't show up next month and tell us how much to overbook each clinic session."
- **Deliverable** — Batch `predictions.csv` (`appointment_id,p_no_show`, every future appointment once, p in [0,1]) plus `overbook.csv` (`session_id,extra`, with `extra` an integer from 0 to 2).
- **World & data** — 8 clinics. `history.csv` holds 24 months, about 60k rows: `appointment_id, patient_id, clinic, session_id, booked_at, slot_time, status, reminder_call_result, prior_visits, distance_km, age, insurance`. `future.csv` holds 4 weeks, about 5,800 rows. `sessions.csv` gives `session_id, clinic, capacity`. Hidden: the true future outcomes.
- **Hidden requirements**
  - `leak_reminder` (ambiguous; data semantics) — `reminder_call_result` is filled 48 h before the visit, and "no answer" correlates strongly with no-shows. In `future.csv` it is blank for 85% of rows, so a model that relies on it collapses.
  - `outcome_def` (ambiguous; data semantics) — No-show means `DNA` or a cancellation less than 24 h ahead. Cancellations 24 h or more ahead are excluded because the slot is refilled.
  - `censored_rows` (missing; data semantics) — History rows with status `booked` are not outcomes and must be dropped.
  - `reschedule_dupes` (missing; data semantics) — A rescheduled visit keeps its `appointment_id` with a new `slot_time`. Only the last row counts.
  - `cost` (missing; scoring) — Each idle slot costs 100 and each patient over capacity costs 150. The ratio implies overbooking only when the expected no-shows are high enough.
  - `clinic_patterns` (missing; data semantics) — Dermatology and Monday-morning sessions have markedly higher rates. The pattern appears in the history, so pooled models underfit.
  - `cap_two` (missing; business rule) — No more than 2 extra bookings per session (the physicians' agreement).
  - `session_level` (missing; business rule) — Overbooking is decided per session, never per patient. This is the equity safeguard modeled on Samorani.
  - `no_peds_overbook` (missing; business rule) — The client's rule: Pediatrics sessions get `extra = 0`.
- **Rules**

  | id | class | check | why |
  |---|---|---|---|
  | `predictions_complete` | physical | All future IDs once, valid p | Scoring needs them |
  | `cap_two` | contractual | 0 ≤ extra ≤ 2, known session | Physician agreement |
  | `no_peds_overbook` | business_policy | extra = 0 for Pediatrics | Pediatrics has a high no-show rate, so the rule leaves idle slots |
- **Objective** — Minimize Σ over sessions of (100 × max(0, capacity − shows) + 150 × max(0, shows − capacity)), using the true outcomes. Extra patients show at their true outcome rate. Brier score is reported as a diagnostic. Reference: logistic regression on lead time, prior no-show rate (computed only from earlier visits), clinic and age, with extra = floor(expected no-shows) capped. Calibrated gradient boosting with clinic interactions should gain about 8%.
- **Hard tier** — Duplicate exports, a stale `history_backup.csv` that is missing the last 2 months, and Shift_JIS/CP1252 encodings. Twist: a stakeholder conflict. The finance lead wants extra = 3; the client confirms that the cap is 2.
- **Policy & language angles** — `regulated_strict`: no overbooking in Pediatrics, and document the leakage check and that ethnicity was not used. `startup_velocity`: may justify overbooking Pediatrics. Status labels (DNA, 노쇼, 無断キャンセル, 爽约, inasistencia) and reminder labels must be localized, and dates follow local order.
- **Authoring risks** — The leaky column must be clearly suspicious once asked about, and fair. Generate outcomes from features that exist in the future file so the score is learnable. Do not include race, to avoid unfair proxies.
- **Sources** — https://www.annfammed.org/page/press-release/machine-learning-model-predicts-no-shows-and-cancellations · https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9021231/ · https://papers.ssrn.com/abstract=3467047 · https://www.healthcareitnews.com/news/study-scheduling-systems-lead-longer-wait-times-black-patients · https://pmc.ncbi.nlm.nih.gov/articles/PMC4187098 · https://thieme-connect.com/products/all/doi/10.4338/ACI-2014-04-RA-0026 · https://www.featuretools.com/?p=3625

---

### Medical Claims Coder — `healthcare/medical_claims_coder`

- **Why it matters** — Autonomous coding engines auto-accept codes they are confident about and route the rest to coders. Accuracy is unverified beyond vendor claims, and upcoding brings False Claims Act exposure. US payers apply CMS NCCI procedure-to-procedure edits (PTP: code pairs that may not be billed together), Medically Unlikely Edits (MUE: unit caps) and X{EPSU} modifiers. Japan's DPC and Korea's HIRA review use ICD-10 based coding but with their own approval criteria, and HIRA denials arrive 9-18 months later.
- **Client & request** — The revenue-cycle manager writes: "Code these outpatient visit notes for billing, please. Diagnoses and procedures."
- **Deliverable** — Batch `diagnoses.csv` (`encounter_id,seq,icd10`, where seq 1 is primary) plus `claim_lines.csv` (`encounter_id,proc_code,modifiers,units`, with modifiers separated by `;`). Encounters that are not billed are left out of both files.
- **World & data** — 420 encounters at 3 payers. The agent receives:
  - `notes/` with one text note per encounter in the customer locale, generated from structured truth
  - `encounters.csv` (`encounter_id, payer, minutes, signed_at, visit_date`)
  - `proc_codes.csv` (a synthetic fee schedule of about 80 codes with prices)
  - `icd10_subset.csv` (about 300 WHO ICD-10 codes)
  - `edits_ptp.csv` (column1/column2 pairs, modifier-allowed flag)
  - `mue.csv`
  - `payers.csv`

  Hidden: the gold codes for each encounter.
- **Hidden requirements**
  - `uncertain_dx` (missing; business rule) — "Suspected" or "rule out" diagnoses are not coded in outpatient care. The documented symptom is coded instead (ICD-10-CM outpatient guideline IV.H). Inpatient conventions in Korea and Japan differ.
  - `ptp_bundling` (missing; business rule) — A column-2 code is dropped unless the pair allows a modifier and the note documents a separate site. In that case append `XS`.
  - `payer_specific` (ambiguous; business rule) — Payer `P2`, a commercial payer, does not apply the PTP table.
  - `em_level` (missing; calculation) — E/M level by total minutes: E1 10-19, E2 20-29, E3 30-39, E4 40 or more. Add modifier `25` when a procedure is done on the same day.
  - `time_units` (missing; calculation) — Timed therapy codes use 15-minute units with the 8-minute rule: 8-22 min = 1, 23-37 = 2, and so on.
  - `mue_cap` (missing; business rule) — Units per code per day are no more than the MUE. A bilateral procedure is one line with `50`.
  - `unsigned` (missing; business rule) — Notes unsigned more than 72 h after the visit are not billed.
  - `no_unspecified` (missing; business rule) — The client's rule: no `.9` "unspecified" codes are submitted. Such encounters are held for a physician query instead.
  - `scoring` (missing; scoring) — See Objective.
- **Rules**

  | id | class | check | why |
  |---|---|---|---|
  | `valid_codes` | physical | Codes exist in the given sets; units ≥ 1 | The claim system rejects anything else |
  | `ptp_edits` | contractual | No unmodified bundled pairs for P1/P3 | Payer edit |
  | `mue_units` | contractual | Units ≤ MUE | Payer edit |
  | `signed_documentation` | contractual | No claim for late-unsigned notes | Payer documentation requirement |
  | `no_unspecified` | business_policy | No `.9` codes | Holding these encounters defers payable revenue |
- **Objective** — Maximize Σ fee of lines that match gold (code, modifiers and units) − 2 × fee of over-coded lines − 0.5 × fee of missed gold lines. Each encounter's line set is compared against gold. Reference: keyword and dictionary mapping plus table edits. Its blind spot is the 8-minute rule on combined minutes, which should leave about 10% headroom.
- **Hard tier** — Duplicate notes (an addendum re-export), notes in a legacy encoding, and a quarterly update of the edit table arriving mid-task. Twist: a late requirement. P3 becomes subject to bundling from this quarter.
- **Policy & language angles** — `regulated_strict`: hold all `.9` encounters and document every bundling decision. `startup_velocity`: bill unspecified codes with a justification. Notes are fully localized (Korean 의증, Japanese 疑い, Chinese 疑似, Spanish "sospecha de"). Codes stay ASCII.
- **Authoring risks** — Notes must be unambiguous in all 5 languages and use templated phrasing, with the gold codes produced from the same templates. Avoid real CPT text, which is copyrighted: the procedure codes are synthetic.
- **Sources** — https://med.noridianmedicare.com/web/jfb/topics/claim-submission/ncci · https://acep.org/administration/reimbursement/reimbursement-faqs/ncci-cci-faq · https://oklahoma.gov/ohca/providers/national-correct-coding-initiative.html · https://mdaudit.com/blog/auditing-autonomous-medical-coding-systems/ · https://blog.nym.health/medical-coding-compliance · https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7738645/ · https://preprints.jmir.org/preprint/108989

---

### Clinical Trial Site Selector — `healthcare/clinical_trial_site_selector`

- **Why it matters** — Tufts CSDD finds that about 11% of initiated sites never activate and about half under-enroll. Start-up takes 17.5 weeks for repeat sites and 22 weeks for new ones. AI feasibility tools from Medidata and IQVIA now predict which sites will not enroll. Sponsors also face per-country rules: FDORA §3601 diversity action plans (draft guidance pulled and contested in 2025), China's NMPA list of filed trial institutions, and Japan's 2023 notice that relaxes the requirement for a separate Japanese Phase 1 study before joining a multiregional trial.
- **Client & request** — The clinical operations VP writes: "Choose the sites for our new Phase 3 study. We need 420 patients as fast as possible within budget."
- **Deliverable** — Batch `site_plan.csv` with columns `site_id,cap`. `cap` is the maximum number of patients the site may randomize, an integer from 1 to 25.
- **World & data** — 180 candidate sites in 9 countries (US, KR, JP, CN, ES, MX, BR, DE, PL). Files:
  - `sites.csv` (`site_id, country, partner, repeat_site, nmpa_filed, underrepresented_catchment`)
  - `history.csv` (`site_id, trial, patients, count_type, months_active`)
  - `costs.csv` (start-up and per-patient cost in local currency)
  - `fx.csv`
  - `country_lag.csv` (regulatory weeks)

  Hidden: each site's true monthly randomization rate, and which sites never activate (about 11%).
- **Hidden requirements**
  - `count_type` (ambiguous; data semantics) — `patients` means randomized patients when `count_type = R` and screened patients when it is `S`. Randomized = screened × 0.6.
  - `rate_norm` (missing; calculation) — The rate is patients / months_active, and `months_active` already excludes start-up.
  - `startup_lag` (missing; calculation) — Activation week = country regulatory lag + 17.5 weeks for a repeat site or 22 weeks for a new one.
  - `fx_budget` (ambiguous; calculation) — The budget is USD 9.0M, converted with `fx.csv`. Cost = start-up cost for every selected site (paid even if it never activates) + per-patient cost.
  - `china_filed` (missing; business rule) — CN sites must have `nmpa_filed = yes`.
  - `country_mix` (missing; business rule) — No country has more than 35% of total cap. JP has at least 8% and CN at least 10%, which the regional filings need.
  - `diversity` (missing; business rule) — At least 25% of US cap is at underrepresented-catchment sites, the sponsor's diversity-plan commitment.
  - `partner_pref` (missing; business rule) — The VP's habit: at least 60% of selected sites are partners.
  - `scoring` (missing; scoring) — See Objective.
- **Rules**

  | id | class | check | why |
  |---|---|---|---|
  | `valid_plan` | physical | Known sites, 1 ≤ cap ≤ 25, Σ cap ≥ 420 | Plan must be able to reach the target |
  | `china_filed` | physical | CN sites filed | Unfiled sites legally cannot run registration trials |
  | `budget` | contractual | Expected cost ≤ USD 9.0M | Approved budget |
  | `country_mix` | contractual | Country shares | Regulatory submission strategy |
  | `diversity` | contractual | US underrepresented share | Commitment to the regulator |
  | `partner_pref` | business_policy | At least 60% partner sites | Some partners are slow, so the rule delays enrollment |
- **Objective** — Minimize the week in which the 420th patient is randomized. This is a deterministic fluid simulation: each site enrolls at its true rate from activation until it reaches its cap, competition is allocated in site_id order, and sites that never activate enroll nobody. If a plan never reaches 420 patients, the week is set to 200. Reference: rank by normalized historical rate per USD, fill the constraints greedily, then add 15% buffer sites. Accounting for new-versus-repeat lag and screened counts should gain about 10%.
- **Hard tier** — A duplicated history export, a stale `fx_backup.csv`, and a data correction: 4 sites lose their NMPA filing. Twist: the deadline is pulled in. The sponsor needs last patient in by week 60, and the lead time this adds makes buffer sites matter.
- **Policy & language angles** — `regulated_strict`: keep partner preference and document every rate assumption. `startup_velocity`: drop slow partners with justification. Localize country names and currency formats (₩, ¥, 元, € with comma decimals in `es`/`de` display columns only).
- **Authoring risks** — The non-activation draw must be unguessable but fair, so that the reference and a careful agent face the same risk. Use expected-value simulation, not random runs. Make sure a plan exists that satisfies all the shares within budget.
- **Sources** — https://www.raps.org/resource/tufts-survey-trial-site-initiation-process-increa.html · https://www.appliedclinicaltrialsonline.com/view/molasses-study-startup-efficiencies · https://www.medidata.com/en/clinical-trial-products/medidata-ai/clinical-trial-analytics/ · https://www.iqvia.com/solutions/research-and-development/precision-site-targeting · https://www.kslaw.com/insights/articles/finally-fda-issues-updated-draft-guidance-on-diversity-action-plans-mandated-by-fdora · https://www.ajmc.com/view/fda-quietly-removes-draft-guidance-on-diversity-in-clinical-trials-following-executive-order-on-dei · https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10019591/ · https://iconplc.com/insights/blog/2026/06/05/japans-clinical-trial-transformation-building-global-future
