# Manufacturing & Supply Chain — case specs

AI in manufacturing and supply chain is used mostly for decisions that already have a mature operations-research or statistics core: forecasting (Gartner expects 70% of large organizations to run AI-based supply chain forecasting by 2030), scheduling with sequence-dependent setups, predictive maintenance on sensor data, and visual or sensor-based inspection. What separates a working deployment from a demo is rarely the model. It is the plant facts nobody writes down: asymmetric changeover matrices, a sensor that was recalibrated, censored failure records, sell-in that is really channel fill, labor-law limits on overtime, and hazardous-goods rules that differ by country. Practitioners report the same traps everywhere: units that change mid-history (in/s vs mm/s, pieces vs reels, kgf·cm vs N·m), duplicate records after ERP merges, and evaluation metrics that ignore how lopsided the cost of errors is (a late RUL prediction or an escaped defect costs far more than a false alarm). The eight roles below put those traps in the hidden requirements and keep the objective tied to cost.

| Role | Task type | Deliverable | Hook |
|---|---|---|---|
| Production Planner | Optimization | Batch `schedule.csv` | Asymmetric color-change setups, shift calendar in local time, molds shared across presses |
| Quality Inspection Engineer | ML | Program `classify(unit)` | Recalibration offset, one noisy inspector, mixed torque units, 20:1 escape cost |
| Predictive Maintenance Engineer | ML + scheduling | Batch `maintenance_plan.csv` | Censored failures, vibration unit change, statutory press inspections, crew capacity |
| Demand Planner | ML | Batch `forecast.csv` | 4-4-5 fiscal periods, orders vs constrained shipments, distributor change with channel fill |
| Warehouse Slotting Manager | Optimization | Batch `slots.csv` | Hazmat segregation, beam load limits, move budget, picks counted in lines |
| Supplier Risk Analyst | ML + rules | Batch `supplier_risk.csv` | Forced-labor list with aliases, duplicate vendor codes, stale statements, sole sources |
| Spare Parts Planner | ML + optimization | Batch `stock_levels.csv` | Intermittent demand, planned overhaul kits, decommissioned machines, cross-border transfers |
| Pallet Load Planner | Optimization | Batch `pallets.csv` | Crush limits, customer height limits and pallet types, liquids-below-dry rule |

All eight catalog roles are kept. Research did not turn up a clearly more impactful replacement, and the set covers the field's main kinds of decision: plan, inspect, maintain, forecast, store, source, stock and ship.

---

### Production Planner — `manufacturing/production_planner`

- **Why it matters** — Short-term scheduling with sequence-dependent setups is one of the most studied problems in operations research. A 2025 review mapped more than 2,100 papers on it. Industrial cases such as injection molding and unrelated parallel machines with color-dependent setups still rely on heuristics plus constraint programming. In color-changing processes, the purge material and time lost to dark-to-light changes are a direct cost, and so is weekly tardiness.
- **Client & request** — The plant manager of an injection-molding plant: "Can you schedule the presses for next week? Orders and machine info attached."
- **Deliverable** — Batch `schedule.csv` with the header `job_id,machine_id,start` (`start` = plant local time `YYYY-MM-DD HH:MM`). The evaluator derives each end time from shots × cycle time, and each setup from the previous job on that machine.
- **World & data** — 8 presses (tonnage 100–450 t), 45 jobs, 22 molds, 6 color families. Files: `jobs.csv` (job_id, product, mold_id, color, qty_pcs, due_date, customer, priority), `molds.csv` (mold_id, cavities, cycle_s, min_tonnage), `machines.csv`, `setup_matrix.csv` (45-minute base mold change plus a color term, from-color × to-color: minutes and purge kg), `maintenance.csv` (PM windows), `calendar.csv`. Nothing is hidden except the cost weights. The world holds the true processing times.
- **Hidden requirements**
  1. `setup_direction` (ambiguous; data semantics) — Rows are the *from* color and columns the *to* color. Light→dark takes 15 min / 1 kg purge, dark→light takes 90 min / 8 kg. This models light-to-dark sequencing practice.
  2. `shots_not_pieces` (missing; calculation) — Run time = ceil(qty_pcs / cavities) × cycle_s. A 4-cavity mold quarters the time.
  3. `mold_unique` (missing; business rule) — Each mold exists once. Two jobs on the same mold cannot overlap, even on different presses.
  4. `tonnage_eligibility` (missing; business rule) — A job may only run on a press with tonnage ≥ its mold's min_tonnage.
  5. `maintenance_utc` (ambiguous; data semantics) — The CMMS export is in UTC. The plant runs on local time (KST/JST +9, CST +8, CET +1, US Eastern −5, by locale). A job and its setup may not overlap a PM window, and no job pauses across one.
  6. `shift_calendar` (missing; business rule) — Two shifts Mon–Fri 06:00–22:00. A job may pause overnight with the mold left in. Saturday 06:00–14:00 is overtime, at most 3 presses. This reflects the Korean 52-hour week (LSA Art. 53: ≤12 h extension) and Japan's Art. 36 cap of 45 h/month.
  7. `due_means_pickup` (ambiguous; business rule) — The due date is a 14:00 truck pickup. Parts need 2 h of QC/packing, so a job must end by 12:00 that day.
  8. `cost_model` (missing; scoring) — Tardiness costs 50,000 KRW per hour per job, ×3 for priority A. Purge resin costs 6,000 KRW/kg.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| eligibility_and_mold | physical | tonnage OK; no two jobs on one mold overlap | a mold can't be in two presses |
| no_overlap_setup | physical | each gap between jobs on a press ≥ setup time; no overlap with PM windows | machine physics |
| working_time | contractual | production only inside shifts; Saturday on ≤3 presses | labor agreement / statutory overtime cap |
| color_blocks | business_policy | each color forms one contiguous block per press | ops habit; it blocks inserting an urgent priority-A job, so tardiness rises 5–15% |

- **Objective** — Minimize tardiness cost + purge cost (KRW). The reference uses ATCS dispatching (apparent tardiness cost with setups) per press, followed by pairwise swap local search, all deterministic.
- **Hard tier** — Duplicate job rows (an order re-keyed), stale `jobs_backup.csv` without 3 rush orders, legacy encoding. Twist: midweek, sales moves one customer's due date forward a day. That collides with the color block on press P5.
- **Policy & language angles** — regulated_strict: no Saturday shift without an approved exception; the color rule is held. startup_velocity: may justify breaking color blocks. Localize color names, dates and time zones (the main pitfall). Spanish data uses `dd/mm/yyyy`, en uses `MM/DD/YYYY` (state this in the data notes).
- **Authoring risks** — Time-zone conversion has to be one unambiguous offset, with no DST inside the week. Keep 24 h of slack so a feasible schedule always exists. Validate that the reference never violates working_time.
- **Sources**
  - https://munin.uit.no/handle/10037/36927
  - https://publica.fraunhofer.de/handle/publica/452187
  - https://repository.li.mahidol.ac.th/handle/123456789/76451
  - https://ifactoryapp.com/article/ai-color-queue-optimization-purge-reduction-paint
  - https://practiceguides.chambers.com/practice-guides/employment-2026/south-korea
  - https://www.tokyodev.com/articles/overtime-in-japan-laws-pay-rates-and-fixed-overtime

---

### Quality Inspection Engineer — `manufacturing/quality_inspection_engineer`

- **Why it matters** — Predicting end-of-line failures from station sensor data is a canonical industrial ML task. Bosch's Kaggle challenge had under 1% failures and was scored with MCC because accuracy and AUC hide imbalance. Studies on industrial data over 36 months show accuracy falling as sensor drift grows. AIAG MSA guidance (cited for IATF 16949 clause 7.1.5.1.1) says gauges and inspectors themselves carry error.
- **Client & request** — The quality manager of an e-axle actuator plant: "We want a model that flags defective units from the test-bench data. Here's last quarter."
- **Deliverable** — Program `classifier.py` exposing `classify(unit: dict) -> int` (1 = reject). It is run on 6,000 hidden units with ≤ 20 ms per unit, standard library + numpy/pandas/scikit-learn only. The `unit` keys match `units_train.csv` columns minus the label columns.
- **World & data** — 4 lines (L1–L4, L4 launched 5 weeks ago), 12 sensors. `units_train.csv` (24,000 rows: unit_id, line_id, test_ts, s01–s12, inspector_id, result ∈ pass/fail/rework, disposition_code), `calibration_log.csv`, `spec_limits.csv`, `reinspection_sample.csv` (800 units re-judged by a lab). Hidden: true defect state of every unit and the 6,000 test units, all dated after the recalibration.
- **Hidden requirements**
  1. `recal_offset` (missing; data semantics) — s04 (housing temperature) read +2.5 °C high before its recalibration on day 41. Test data is post-recal.
  2. `noisy_inspector` (missing; data semantics) — Inspector QI-07's labels flip about 25% of the time (visible in the re-inspection sample). They should be dropped or down-weighted.
  3. `torque_units` (ambiguous; data semantics) — s06 torque is N·m except on L3, which logs kgf·cm (×0.0981).
  4. `rework_is_defect` (ambiguous; data semantics) — `rework` means the unit failed first-pass test, so it counts as a defect.
  5. `retest_duplicates` (missing; data semantics) — Retested units appear twice. The latest test_ts is the record of truth.
  6. `no_disposition` (missing; data semantics) — disposition_code is written after scrap and is absent at prediction time (leakage).
  7. `missing_sensor` (missing; data semantics) — s09 isn't installed on L1 (blank). The program must not crash on NaN.
  8. `cost_weights` (missing; scoring) — An escaped defect costs 20, a false reject 1 (warranty vs scrap), so the right threshold is near p = 1/21.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| interface | physical | returns 0/1 for every unit within time; no exception | a program that crashes can't run on the line |
| spec_limit_reject | contractual | every unit with any characteristic outside `spec_limits.csv` is flagged | customer control plan / PPAP |
| escape_cap | contractual | recall on true defects ≥ 0.85 | customer quality agreement (PPM target) |
| flag_new_line | business_policy | every L4 unit is flagged (100% containment) | L4 runs at the plant's defect rate, so about 1,400 good units are scrapped and cost rises about 10% |

- **Objective** — Minimize 20·FN + 1·FP on the hidden set. The reference fixes the offset and the units, drops QI-07 labels, trains L2 logistic regression, applies the cost threshold, and ORs in the spec limits. Gradient boosting gives about 10% headroom.
- **Hard tier** — Duplicate rows, stale calibration log missing the day-41 entry, encoding. Twist: the client "remembers" late that L3 changed torque wrenches, and the units confusion starts there.
- **Policy & language angles** — regulated_strict holds flag_new_line (containment is common for a launch under IATF). enterprise_balanced may escalate an exception after showing L4 yield. Localize sensor labels and result labels (合格/不合格/返工, 양품/불량/재작업, OK/NG/手直し), and use decimal commas in es/de-style formats for es.
- **Authoring risks** — Noise must be learnable but not dominant, so verify the Bayes-optimal cost with true labels. Hidden units must share the feature distribution except for the documented shifts. Pin library versions.
- **Sources**
  - https://arxiv.org/pdf/1701.00705
  - https://arxiv.org/pdf/1612.05740
  - https://sintef.brage.unit.no/sintef-xmlui/handle/11250/3016329
  - https://link.springer.com/article/10.1007/s10845-025-02569-6
  - https://www.spcforexcel.com/Downloads/pdf/Acceptance-Criteria-for-Measurement-Systems-Analysis.pdf
  - https://ifactoryapp.com/industries/automotive-manufacturing/measurement-system-analysis-msa-gage-rr-automotive
  - https://www.chinesestandard.net/PDF.aspx/GBT2828.1-2012?Preview

---

### Predictive Maintenance Engineer — `manufacturing/predictive_maintenance_engineer`

- **Why it matters** — RUL work grew out of NASA's C-MAPSS benchmark, whose score punishes late predictions more than early ones (exponent divisor 10 vs 13), because a missed failure costs more than an early service. Field studies show that censored records hide distinct populations and bias naive estimators. Vibration severity is judged against ISO 10816-3/20816-3 zones.
- **Client & request** — The maintenance manager of a machining plant: "Plan maintenance for the next 12 weeks so machines don't break down on us."
- **Deliverable** — Batch `maintenance_plan.csv` with the header `machine_id,week,action` (week 1–12; action ∈ `service`, `inspection`). At most one service per machine.
- **World & data** — 60 machines (40 CNC spindles, 12 pumps, 8 servo presses). `machines.csv` (type, line, install date, last_service_date, runtime_hours), `sensor_weekly.csv` (104 weeks: vibration, temperature, load), `failure_history.csv` (310 episodes: start, end, end_reason ∈ failure/preventive/still_running), `crew_calendar.csv`, `statutory_inspections.csv`, `parts_leadtime.csv`. Hidden: each machine's degradation and Weibull-PH hazard. Failures are simulated over 300 fixed seeds.
- **Hidden requirements**
  1. `censoring` (missing; calculation) — `preventive` and `still_running` episodes are right-censored, not failures. Dropping them, or counting them as failures, biases the fitted life.
  2. `vibration_unit_change` (missing; data semantics) — Before week −30 the gateway reported in/s peak; after, mm/s RMS. 1 in/s pk ≈ 17.96 mm/s RMS.
  3. `zone_d` (ambiguous; business rule) — A spindle above 7.1 mm/s RMS in the latest week is in zone D (group 1, flexible) and must be serviced in week 1.
  4. `runtime_hours` (ambiguous; data semantics) — Age is counted in runtime hours since the last service. The counter resets at service. Line C runs 24 h/day, the others 16 h/day.
  5. `statutory_presses` (missing; business rule) — Servo presses whose statutory inspection (Korea OSH Act safety inspection, Japan ISH Act Art. 45 annual specific self-inspection) falls due in the horizon get an `inspection` row on or before the due week.
  6. `crew_capacity` (missing; business rule) — 2 crews × 3 jobs/week. Week 7 has 1 crew (holiday leave). An inspection uses one slot.
  7. `part_leadtime` (missing; business rule) — Pump service kits need 2 weeks of lead time, so pumps can be serviced from week 3 on.
  8. `duplicate_log` (missing; data semantics) — CMMS and paper logs duplicate 25 episodes that lie within 2 days of each other.
  9. `cost_model` (missing; scoring) — Unplanned failure costs 12 M KRW (downtime + expedite). A service costs 2.5 M, an inspection 0.4 M.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| capacity | physical | jobs per week ≤ crew slots | people can't be in two places |
| statutory_inspection | physical | every due press inspected by its due week | legal ban on operating; no exception process exists |
| zone_d_week1 | contractual | zone-D spindles serviced in week 1 | OEM warranty / insurer condition |
| service_500h | business_policy | every machine reaching 500 runtime h in the horizon is serviced before 500 h | uses slots on healthy machines and starves the at-risk ones, so expected cost rises about 12% |

- **Objective** — Minimize expected cost over the 300 failure draws. The reference fits a censored Weibull per type with a fixed vibration coefficient, takes the conditional 12-week failure probability, schedules a service when it exceeds 2.5/12, and fills slots greedily by risk.
- **Hard tier** — Duplicate rows, stale sensor backup before the unit change, encoding. Twist: in a data correction, two machines' end_reason changes from failure to preventive.
- **Policy & language angles** — regulated_strict: service_500h held and the statutory dates verified. startup_velocity: justify dropping the 500 h rule. Localize units (mm/s), fiscal week numbering (ISO week vs a Sunday-start US week), and inspection names (안전검사, 特定自主検査).
- **Authoring risks** — Expected-cost scoring over many draws avoids lucky plans. The unit change must be detectable as a level shift. Zone D must not contradict capacity in week 1 (≤4 such spindles).
- **Sources**
  - https://www.papers.phmsociety.org/index.php/ijphm/article/download/4724/2824
  - https://arxiv.org/pdf/2202.10916
  - https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9123218/
  - https://metricgate.com/blogs/weibull-analysis-failure-prediction/
  - https://www.fabrico.io/blog/iso-10816-3-vibration-severity/
  - https://acoem.us/blog/other-topics/understanding-the-iso-10816-3-vibration-severity-chart/
  - https://kosha.or.kr/english/business/safetyInspection.do

---

### Demand Planner — `manufacturing/demand_planner`

- **Why it matters** — Gartner expects most large firms to run AI forecasting by 2030. Practitioner research finds that planner overrides often hurt accuracy on most items, which is why forecast value added is measured against naive baselines. Sell-in amplifies sell-out, with FMCG sell-in about twice as variable, so distributor changes and channel fill mislead models.
- **Client & request** — An S&OP lead at a small-appliance maker: "Forecast monthly demand per SKU and region for the first half of next fiscal year."
- **Deliverable** — Batch `forecast.csv` with the header `sku_id,region_id,period,forecast_qty` (period `FY27-P01`…`FY27-P06`; whole units).
- **World & data** — 110 active SKUs + 8 launches, 6 regions, 36 fiscal periods. `orders.csv` (sku, region, period, ordered_qty, shipped_qty), `products.csv` (family, analog_sku, launch_period, eol_period, unit_price), `promo_plan.xlsx` (history + future), `regions.csv`, `fiscal_calendar.csv`. Hidden: true orders for P01–P06.
- **Hidden requirements**
  1. `fiscal_445` (missing; data semantics) — Periods follow a 4-4-5 week calendar. P03/P06/P09/P12 have 5 weeks, so a raw period series shows a false quarterly spike.
  2. `orders_not_shipments` (ambiguous; data semantics) — Demand is ordered_qty. During the FY25-P08–P10 plant fire, shipments were capped at 60%.
  3. `promo_uplift` (missing; calculation) — Future promotions add about 35% and pull about 10% from the next period.
  4. `cannibalization` (missing; calculation) — A promotion on one size variant takes about 15% from siblings in the same family.
  5. `analog_launch` (missing; business rule) — New SKUs follow their analog's first three periods at 60/90/100% of the analog's steady level.
  6. `region_recode` (ambiguous; data semantics) — R4 became R7 at the distributor change (FY26-P04). The new distributor's first two periods include about 1.5 periods of channel fill that is not demand. Forecast R7 only.
  7. `returns_rows` (missing; data semantics) — Negative ordered_qty rows are returns and are excluded from demand.
  8. `eol` (missing; business rule) — SKUs past eol_period are delisted, so their forecast is 0.
  9. `metric` (missing; scoring) — Value-weighted WAPE (unit_price) + 0.5 × |value bias|.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| complete_grid | physical | every active sku × region × period once, integer ≥ 0 | an ERP import rejects anything else |
| eol_zero | contractual | delisted SKUs are 0 after EOL | distributor delisting agreement |
| floor_ly_minus_20 | business_policy | forecast ≥ 0.8 × same period last year (SKUs with LY history) | forces overforecasts on cannibalized SKUs and on R7 (inflated by channel fill), so WAPE rises 6–10% |

- **Objective** — Minimize the metric against the hidden orders. The reference uses per-week-normalized seasonal ETS on corrected orders, then applies promo and cannibalization multipliers, analog curves for launches, and zero for EOL SKUs.
- **Hard tier** — Duplicate rows, stale promo plan, encoding. Twist: stakeholder conflict. Sales says the R7 fill was "real growth"; the client confirms it is fill.
- **Policy & language angles** — enterprise_balanced: the floor can be escalated with evidence. regulated_strict: held. Localize period labels (第1期/1분기/P01), region names, and promo type labels. Japan's fiscal year usually starts in April, Korea/China in January: state the FY start explicitly per locale (world fixed).
- **Authoring risks** — Not to be confused with the retail grocery forecaster (that case covers daily data, stockout censoring and pack units). Keep noise moderate so the reference has 5–15% headroom.
- **Sources**
  - https://www.gartner.com/en/newsroom/press-releases/2025-09-16-gartner-predicts-70-percent-of-large-orgs-will-adopt-ai-based-supply-chain-forecasting-to-predict-future-demand-by-2030
  - https://www.imd.org/ibyimd/strategy/how-a-new-approach-to-demand-planning-can-redefine-success/
  - https://ideas.repec.org/a/eee/proeco/v143y2013i2p489-498.html
  - https://omp.com/blog/sell-in-and-sell-out-data-analysis-for-a-more-responsive-supply-chain
  - https://blog.massistcrm.com/sell-in-vs-sell-through-data
  - https://us.nttdata.com/en/blog/2022/march/measuring-forecast-accuracy-keeping-score-on-keeping-score

---

### Warehouse Slotting Manager — `manufacturing/warehouse_slotting_manager`

- **Why it matters** — Travel is the largest part of manual pick time. Simulation shows popularity- and cube-per-order-index (COI) slotting in the golden zone shortens fulfillment. Hazardous goods add hard segregation law: Germany's TRGS 510 storage classes, Japan's Fire Service Act designated quantities, Korea's Hazardous Materials Safety Act.
- **Client & request** — The DC manager of an industrial-supplies distributor: "Re-slot the pick area this weekend so pickers walk less."
- **Deliverable** — Batch `slots.csv` with the header `sku_id,location_id`. One row per active SKU.
- **World & data** — 1,150 SKUs, 1,500 locations (10 aisles × 30 bays × 5 levels). `skus.csv` (case dims mm, case_kg, slot_cases, hazard_class, brand, status, seasonal), `locations.csv` (aisle, bay, level, height_mm, max_kg, zone), `order_lines.csv` (13 weeks), `current_slots.csv`. Hidden: the next 4 weeks of order lines.
- **Hidden requirements**
  1. `lines_not_units` (ambiguous; calculation) — Pick frequency = order lines (visits), not units.
  2. `hazmat_zone` (missing; business rule) — Class 3 flammables only in zone H. Class 5.1 oxidizers never in the same or an adjacent bay as class 3.
  3. `beam_load` (missing; business rule) — case_kg × slot_cases ≤ location max_kg.
  4. `heavy_low` (missing; business rule) — Cases > 15 kg only on levels 1–2 (lifting-equation vertical multiplier).
  5. `golden_zone` (missing; scoring) — Levels 2–3 are golden. Levels 1, 4 and 5 add a 4 m-equivalent ergonomic penalty per pick.
  6. `travel_model` (missing; scoring) — Distance per pick = 2 × (bay index × 1.4 m) + |aisle − 1| × 3 m from the depot.
  7. `move_budget` (missing; business rule) — At most 280 SKU moves (2 crews, one weekend). Each move costs 20 m-equivalent.
  8. `inactive_skus` (ambiguous; data semantics) — status = inactive SKUs are not slotted.
  9. `seasonal_lift` (missing; data semantics) — Seasonal SKUs triple in the coming weeks (winter goods).
- **Rules**

| id | class | check | why |
|---|---|---|---|
| fit | physical | case height ≤ location height; beam load | physics |
| hazmat_segregation | physical | zone H + 5.1/3 separation | law (TRGS 510, 消防法, 위험물안전관리법); never bend |
| moves_and_heavy | contractual | ≤280 moves; >15 kg only on levels 1–2 | crew agreement / works-council safety rule |
| brand_blocks | business_policy | each brand's SKUs in contiguous bays of one aisle | fast movers stay spread out, so travel rises about 8% |

- **Objective** — Minimize forecast-week travel + ergonomic penalty + move cost (metres). The reference ranks SKUs by COI with the seasonal ×3, assigns them greedily to the best feasible location, and keeps the current slot when the gain is < 20 m.
- **Hard tier** — Duplicate SKU rows, stale location file missing the new zone-H bays, encoding. Twist: a late requirement adds a class 8 corrosive that must not sit above other goods.
- **Policy & language angles** — regulated_strict: hazard checks documented in NOTES.md. startup_velocity: may justify dropping brand blocks. Localize hazard labels (UN class vs 第4類 引火性液体 vs 제4류), dimensions (in/lb for en), and location codes.
- **Authoring risks** — Verify that the move budget allows the reference to reach its objective. Make the hazard classes unambiguous per locale with a single mapping table.
- **Sources**
  - https://www.proquest.com/docview/232354916
  - https://umbrex.com/?p=245082
  - https://racklify.com/encyclopedia/golden-zone-in-warehouse-picking-optimizing-slotting-and-ergonomics/
  - https://www.leuze-verlag.de/en/pre-and-post-treatment/store-hazardous-substances-correctly
  - https://www.kaigai-shobo.jp/files/fireserviceinjapan/3Overview_of_Hazardous_eng.pdf
  - https://www.city.inagi.tokyo.jp/en/kurashi/iza/1011974/1012005/1012028.html
  - https://ergo-plus.com/wp-content/uploads/NIOSH-guide-v-5.5.pdf

---

### Supplier Risk Analyst — `manufacturing/supplier_risk_analyst`

- **Why it matters** — Procurement teams screen suppliers with Altman Z-scores (with variants for private firms) and add delivery signals because balance sheets lag. Legal screening is now compulsory: under UFLPA, goods from listed entities are presumed to involve forced labor (43 entities were added in Aug 2026), and Germany's LkSG requires an annual risk analysis of direct suppliers.
- **Client & request** — The CPO of an electronics maker: "Rate our suppliers' risk so we know where to focus next year."
- **Deliverable** — Batch `supplier_risk.csv` with the header `supplier_id,tier,score` (tier ∈ low/medium/high, score 0–1).
- **World & data** — 420 vendor codes (≈400 real suppliers). `suppliers.csv` (country, region, category, strategic), `financials.csv` (fiscal_year_end, currency, scale, statement lines), `delivery.csv` (24 months OTD/PPM), `sourcing.csv` (part, supplier, annual_spend), `events.csv`, `entity_list.csv`. Hidden: which suppliers suffer a disruption in the next 12 months, and its loss.
- **Hidden requirements**
  1. `merged_vendors` (missing; data semantics) — 20 suppliers have two codes after an ERP merge (`merge_map` provided on request). Spend and history are combined.
  2. `z_double_prime` (ambiguous; calculation) — Use Z″ (private) with zones < 1.1 distress and 1.1–2.6 grey. Scale differs (thousands vs millions) but ratios are unaffected. Japanese suppliers have March year-ends.
  3. `stale_statements` (missing; business rule) — Statements > 18 months old are a risk signal, not "no data".
  4. `entity_aliases` (missing; business rule) — List matches include aliases and alternate romanizations (e.g., Xinjiang/Sinkiang spellings). A match makes the supplier high.
  5. `sole_source_impact` (missing; calculation) — Impact = spend of parts where the supplier holds 100% share × 3, plus other spend.
  6. `region_cluster` (missing; data semantics) — Suppliers in one quake/flood region share an event draw.
  7. `otd_definition` (ambiguous; data semantics) — OTD is measured against the confirmed date. A downward 6-month trend is the leading signal.
  8. `early_payment_requests` (missing; data semantics) — An event "requested advance/shortened payment" (beyond normal 60-day terms, cf. Japan's 2026 取適法) signals distress.
  9. `cost_model` (missing; scoring) — High mitigation costs 3 M and averts 90% of loss. Medium costs 0.8 M and averts 50%.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| entity_list_high | physical | every listed (incl. alias) supplier is high | statutory import ban; can't be waived |
| high_capacity | contractual | high ≤ 12% of suppliers | audit firm contract capacity |
| strategic_never_high | business_policy | strategic suppliers never high | hides 3–4 genuinely distressed strategic suppliers, so expected loss rises about 10% |

`strategic_never_high` conflicts with `entity_list_high` for one strategic supplier on the list. The physical rule wins, and the requirements say so. That supplier is excluded from the policy's check.

- **Objective** — Minimize mitigation cost + unaverted expected loss (KRW). The reference uses logistic regression on Z″, stale flag, OTD trend and events, then expected loss = p × impact, tiers by quantile under the capacity cap, plus the legal overrides.
- **Hard tier** — Duplicate rows, stale entity list (missing the August additions), encoding. Twist: the client is unavailable in the last third of the session.
- **Policy & language angles** — regulated_strict: document the sanctions screening. enterprise_balanced: escalate the strategic exception. Localize company names (CJK names with romanized aliases), currencies, and fiscal year ends.
- **Authoring risks** — Fuzzy-match ground truth must be deterministic, so give an explicit alias table on request. Avoid real company names.
- **Sources**
  - https://beancount.io/blog/2026/05/18/altman-z-score-five-ratio-bankruptcy-prediction-model-small-business-financial-distress-screen-customers-suppliers-credit-guide
  - https://www.mdpi.com/2674-1032/5/1/17
  - https://www.industryweek.com/software-amp-systems/360-degree-view-risk
  - https://www.thomsonreuters.com/en-us/help/onesource-global-trade/regulatory-insights/2026/august-4th/dhs-updates-uflpa-entity-list-43-new-entities
  - https://ofwlaw.com/expansion-of-the-uflpa-entity-list-implications-for-importers/
  - https://www.taylorwessing.com/en/insights-and-events/insights/2026/01/lksg
  - https://www.dlapiper.com/insights/publications/2025/12/major-amendments-to-japan-subcontract-act

---

### Spare Parts Planner — `manufacturing/spare_parts_planner`

- **Why it matters** — MRO spares have intermittent demand, and plain smoothing mis-forecasts it. Croston's method is biased upward, and SBA's (1 − α/2) correction is standard. Capital spares are rarely used but a stockout means a long shutdown, while obsolete parts become write-offs once the last-time-buy window passes.
- **Client & request** — The maintenance director of a 3-site packaging group: "Set spare-part stock levels for each site."
- **Deliverable** — Batch `stock_levels.csv` with the header `site_id,part_id,min_qty,max_qty` (reorder at ≤ min, order up to max).
- **World & data** — 3 sites (S1, S2 in one country, S3 abroad), 480 parts. `parts.csv` (criticality V/E/D, unit_cost, issue_unit, pack_size, lead_time, eol_date), `issues.csv` (36 months, work_order_type), `installed_base.csv`, `overhaul_plan.csv`, `site_capacity.csv`, `on_hand.csv`. Hidden: 52 weeks of demand simulated over 200 draws.
- **Hidden requirements**
  1. `intermittent` (missing; calculation) — Most parts have zero demand in more than 70% of months. Use Croston/SBA-type rates and Poisson-type quantiles.
  2. `planned_overhaul` (ambiguous; data semantics) — Issues on `PM_OVERHAUL` work orders are planned kits. The future plan is known, so they are excluded from random demand and added in their month.
  3. `decommission` (missing; business rule) — Line 3 at S2 is decommissioned in week 10, so its parts need no stock at S2 after that.
  4. `pack_units` (ambiguous; data semantics) — Issues are in packs for parts with pack_size > 1. Levels are in each.
  5. `lead_time_days` (ambiguous; data semantics) — lead_time is calendar days, not weeks.
  6. `transfers` (missing; business rule) — S1↔S2 transfer takes 1 day and costs 80,000 KRW. S3 is cross-border (customs, about 15 days) and is not used for emergencies.
  7. `eol_ltb` (missing; business rule) — Parts with eol_date in the horizon can't be reordered afterward. Max covers the remainder.
  8. `rotables` (missing; data semantics) — Negative issues are repaired returns.
  9. `cost_model` (missing; scoring) — Stockout-day cost: V 5 M, E 0.5 M, D 0. Holding 20%/year. Order cost 30,000.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| levels_valid | physical | integers, 0 ≤ min ≤ max | system constraint |
| site_capacity | physical | Σ max × part volume ≤ site storage | shelf space |
| inventory_cap | contractual | Σ max × cost ≤ site budget | finance covenant |
| critical_min_one | business_policy | min ≥ 1 for every V part at every site | stocks S2 parts for the decommissioned line and duplicates S1/S2 parts one day apart, so cost rises 6–9% |

- **Objective** — Minimize simulated expected cost. The reference uses SBA rates, a Poisson quantile at the newsvendor ratio by criticality, S1/S2 pooling for E parts, and EOL truncation.
- **Hard tier** — Duplicate issue rows, stale part master without EOL dates, encoding. Twist: a deadline pulled forward. Finance needs the file a day early.
- **Policy & language angles** — regulated_strict: holds critical_min_one (safety-related spares). Localize criticality labels and part descriptions (Japanese 部品名), and keep currencies per site consistent (S3 in its local currency at a stated rate).
- **Authoring risks** — Make the simulation fully specified (review timing, lead time, transfer trigger) in the requirements. Avoid parts whose optimal level hinges on one rare event.
- **Sources**
  - https://nixtlaverse.nixtla.io/statsforecast/docs/models/crostonsba.html
  - https://en.wikipedia.org/wiki/Spare_part
  - https://en.wikipedia.org/wiki/Obsolescence
  - https://duravent.digit-software.com/analytics/forecast-accuracy

---

### Pallet Load Planner — `manufacturing/pallet_load_planner`

- **Why it matters** — Mixed-case pallet building decides freight cost and damage. Corrugated cases are rated from box-compression tests with safety factors of about 4–5, and pallet footprints differ by market (EUR 1200×800, GMA 48×40 in, 1100×1100 in Asia). Road weight limits (e.g., the US 80,000 lb gross / 34,000 lb tandem) cap what goes on a truck.
- **Client & request** — The shipping supervisor of a home-care products plant: "Build the pallets for tomorrow's shipments, please."
- **Deliverable** — Batch `pallets.csv` with the header `pallet_id,order_id,layer,sku_id,cases` (layer 1 = bottom).
- **World & data** — 36 orders, 14 customers, 160 SKUs. `orders.csv`, `skus.csv` (case L/W/H, weight, crush_kg, liquid, cases_per_layer for each pallet type), `customers.csv` (pallet_type, max_height_mm, rate per pallet), `pallet_types.csv`. Hidden: none beyond the rules. Scoring is deterministic geometry.
- **Hidden requirements**
  1. `customer_pallet_type` (missing; business rule) — Each customer has a fixed pallet type (EUR, GMA, T11). cases_per_layer depends on it.
  2. `height_includes_pallet` (ambiguous; calculation) — max_height_mm includes the pallet deck (144 mm EUR/T11, 150 mm GMA).
  3. `crush` (missing; calculation) — Weight above any layer ≤ that layer's SKU crush_kg per case × cases (a mixed layer uses its weakest SKU).
  4. `gross_weight` (missing; business rule) — ≤ 1,000 kg including the pallet (25 kg).
  5. `one_order_per_pallet` (missing; business rule) — No mixing of orders on a pallet.
  6. `liquids_low` (missing; business rule) — Liquid SKUs are never above dry SKUs (customer routing guide).
  7. `weight_units` (ambiguous; data semantics) — Case weights are grams, except the US-sourced SKUs, which are in lb.
  8. `mixed_layer_area` (ambiguous; calculation) — A mixed layer is feasible if Σ cases × footprint ≤ 90% of the deck area. Its height is that of the tallest case.
  9. `cost_model` (missing; scoring) — A pallet is charged a full rate whatever its fill.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| exact_quantities | physical | every order line's cases shipped exactly | the shipment must match the order |
| crush_weight | physical | crush and gross weight | cases collapse |
| height_liquids | contractual | customer height; liquids below dry | retailer routing guide (chargebacks) |
| one_sku_per_layer | business_policy | each layer holds one SKU | forces partial layers, so pallets rise about 8% |

- **Objective** — Minimize Σ pallets × customer rate. The reference sorts by strength/weight descending, fills full layers first, then first-fit mixed layers, and opens a new pallet when a limit binds.
- **Hard tier** — Duplicate order lines, stale customer file with an old height limit, encoding. Twist: in a data correction, a retailer lowers its height limit to 1,500 mm overnight.
- **Policy & language angles** — startup_velocity: may justify mixed layers. regulated_strict: holds the layer rule. Localize dimensions (mm vs in), weights (kg vs lb), and pallet names (パレット T11, 표준 파렛트 1100).
- **Authoring risks** — State the stacking model exactly (layers, no overhang) so the geometry is unambiguous. Ensure feasibility for every order.
- **Sources**
  - https://en.wikipedia.org/wiki/Box_compression_test
  - https://en.wikipedia.org/wiki/Pallet
  - https://en.wikipedia.org/wiki/Palletizing
  - https://en.wikipedia.org/wiki/Federal_Bridge_Gross_Weight_Formula
