# Energy & Utilities — case specs

AI in energy and utilities is mostly forecasting and operational optimization wired into settlement rules that
put money on accuracy. Korea's power exchange pays renewable plants of 20 MW and up a per-kWh bonus when their
day-ahead forecast error stays under a threshold, which was tightened from 12% to 8% in 2025. Japan's FIP
scheme puts imbalance cost on generators against 30-minute plans. China's provincial "two detailed rules"
penalize solar farms per 15-minute point. Practitioners report the same failure modes again and again:
curtailed or inverter-limited hours left in the training target, holiday and bridge-day effects, meter
multipliers and unit changes, and night-flow artefacts in water networks. Tariff design and storm
restoration are less "ML" and more constrained optimization under regulatory caps and safety sequencing,
which is a good fit for a deterministic evaluator. All five catalog roles are kept. Research showed each is
high-stakes and evaluator-friendly, so no replacement was clearly better. The built role is Battery Dispatch
Operator.

| Role | Task type | Deliverable | Hook |
|---|---|---|---|
| Solar Output Forecaster | ML forecasting | Batch `forecast.csv` | Curtailed history, an inverter outage and a 49-hour "48 h" window across the autumn clock change |
| Grid Load Forecaster | ML forecasting | Batch `load_forecast.csv` | Meter swap from kW to MW, a holiday plus bridge day, a temperature station gap, a new data centre |
| Water Leak Detection Engineer | Anomaly detection + selection | Batch `dispatch.csv` | Night-flow rises caused by flushing, PRV changes, boundary valves and dead loggers, with only 15 crews |
| EV Tariff Designer | Optimization | Batch `tariff.json` | Revenue neutrality on tax-exclusive historical load, ratio caps, bill-impact caps, price response |
| Outage Restoration Planner | Optimization (scheduling) | Batch `restoration_plan.csv` | Hospitals on generator fuel, tree-before-line sequencing, cold-load pickup on tie switches |

---

### Solar Output Forecaster — `energy_utilities/solar_output_forecaster`

- **Why it matters** — Forecast accuracy is paid for directly. KPX settles a bonus of about 3-4 KRW/kWh when
  the day-ahead error is within 8%, Japanese FIP plants pay imbalance against 30-minute plans, and Chinese
  rules score every one of the 96 daily points. Solargis and Fraunhofer ISE both warn that curtailed and
  inverter-fault periods bias models low unless they are excluded or reconstructed.
- **Client & request** — The asset manager of a 6-farm portfolio (an overseas fleet owned by the client in
  ko/ja/zh locales). "Can you forecast our solar farms for the next 48 hours? Weather forecast and history
  attached."
- **Deliverable** — Batch `forecast.csv`, header `farm_id,interval_start,power_mw`. `interval_start` is
  ISO 8601 local time with offset (`2027-10-31T02:00+02:00`), hourly, covering local days 2027-10-30 and
  2027-10-31. That is 49 rows per farm and 294 rows in total. `power_mw` is the average AC output at the
  meter.
- **World & data** — 6 farms, 8-60 MW AC, DC/AC ratios 1.15-1.40. Files: `farms.csv` (farm_id, mwp_dc,
  mw_ac, lat, lon, tilt); `scada_history.csv` (farm_id, timestamp_local, power, curtail_flag, setpoint_pct,
  365 days hourly, about 52k rows); `nwp_forecast.csv` (farm_id, timestamp_utc, ghi_wm2, temp_c,
  cloud_pct, 49 h); `maintenance_log.csv`; `grid_notices.md`. Hidden: the true irradiance path, actual
  output, and the effect of inverter availability.
- **Hidden requirements**
  - `window_49h` (ambiguous; data semantics) — "48 h" means the two local delivery days. Clocks fall back on
    31 Oct, so there are 49 hourly rows per farm with offsets +02:00 then +01:00. The repeated 02:00 hour
    appears twice, distinguished by its offset. This mirrors day-ahead submissions in local market time.
  - `ac_limit` (ambiguous; calculation) — "Nameplate" in sales material is MWp DC. Export is clipped at
    `mw_ac`, so clear-sky peaks plateau at AC.
  - `curtail_history` (missing; data semantics) — Rows with `curtail_flag=1` are capped by the operator
    setpoint, not by weather. Exclude them from training. This follows the Solargis and Fraunhofer
    guidance.
  - `inverter_outage` (missing; business rule) — F2 has 2 of 10 inverters out until 2027-10-31 12:00
    local, so its available AC is 80%.
  - `curtail_notice` (missing; business rule) — The TSO instructed F3 to stay at or below 50% of `mw_ac`
    from 11:00 to 14:00 on 30 Oct. The forecast is metered output, so it must reflect the instruction.
  - `kw_logger` (ambiguous; data semantics) — F5's history is in kW. A legacy logger was used, and the
    column header says only "power".
  - `utc_nwp` (missing; data semantics) — NWP timestamps are UTC while SCADA is local, and the offset
    changes inside the history.
  - `night_negative` (ambiguous; data semantics) — Small negative night values are auxiliary consumption.
    The forecast floor is 0.
  - `score_mae` (missing; scoring) — Scoring is the total absolute error in MWh across all farm-hours.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| `capacity` | physical | 0 ≤ power ≤ available AC (mw_ac × inverter availability) | Inverters cannot exceed this |
| `rows` | physical | Exactly 294 rows with valid farm/offset keys | The settlement grid is fixed |
| `tso_cap` | contractual | F3 ≤ 50% mw_ac 11:00-14:00 on 30 Oct | Grid-code instruction; schedules above it are rejected |
| `cap_090` | business_policy | power ≤ 0.9 × mw_ac everywhere | Risk desk preference. On clear hours high-DC/AC farms sit at 100% AC, so the cap adds about 0.1 × AC of error per clear hour |

- **Objective** — Minimize Σ|forecast − actual| MWh. Actual = f(true GHI, temperature, DC/AC clipping,
  availability, curtailment). Reference: per-farm least-squares fit of clean history on NWP GHI and
  temperature, AC-clip, apply derates, zero at night. Headroom of 5-12% comes from per-hour bias
  correction and temperature derating.
- **Hard tier** — Duplicate SCADA rows at the fall-back hour; a stale `farms_backup.csv` with old F4
  capacity; a data correction that moves F2's outage end to 18:00. Twist: an O&M stakeholder claims the
  curtailment notice was cancelled, and only the client can confirm it still stands.
- **Policy & language angles** — Under regulated_strict, keep `cap_090` and document it. Under
  startup_velocity, breaking it with a justification is right. enterprise_balanced escalates. Localize
  column labels, the "curtailment" term (출력제어 / 出力制御 / 限电 / curtailment / limitación), and the
  decimal comma in es data files. Pitfall: Korea, Japan and China have no DST, so localized notes must say
  explicitly that the plants are in a DST region.
- **Authoring risks** — Agents may give the repeated hour two identical keys. The offset makes keys unique,
  and the request must say "with offset". Keep the NWP noise level fixed by seed so the reference headroom
  is stable.
- **Sources**
  - https://kb.solargis.com/docs/evaluating-and-managing-forecast-accuracy
  - https://www.ise.fraunhofer.de/content/dam/ise/de/documents/publications/conference-paper/38th-eupvsec-2021/Holland_5BV42.pdf
  - https://arxiv.org/pdf/1705.04132
  - https://www.metroseoul.co.kr/article/20230921500160
  - https://blog.haezoom.com/news_03
  - https://www.yicai.com/news/100097408.html
  - https://ashurst.com/en/insights/japans-renewable-fip-scheme-and-recent-changes-to-the-regime-for-battery-storage
  - https://proceedings.ises.org/scholar/paper/40032

---

### Grid Load Forecaster — `energy_utilities/grid_load_forecaster`

- **Why it matters** — Week-ahead zonal load drives unit commitment and substation switching. Holidays are
  the classic weak spot: Korean studies call Chuseok errors "very large", and Itron separates fixed-date
  from fixed-weekday holidays. Temperature explains more than 70% of load variance, so weather-feed gaps
  and meter scaling errors directly corrupt models.
- **Client & request** — The head of system planning at a distribution utility. "Please forecast hourly
  load for next week for each zone."
- **Deliverable** — Batch `load_forecast.csv`, header `zone_id,hour_start,load_mw`. Hour-beginning local
  timestamps `YYYY-MM-DD HH:00` for Mon 2027-05-03 00:00 to Sun 2027-05-09 23:00. That is 5 zones × 168 =
  840 rows.
- **World & data** — 5 zones (residential, commercial, industrial, mixed, rural), peaks of 40-220 MW.
  Files: `zone_load_history.csv` (zone_id, hour_ending, value, 3 years, about 131k rows);
  `weather_history.csv` and `weather_forecast.csv` (station_id, timestamp, temp_c); `zone_station_map.csv`;
  `calendar.csv` (date, holiday_name); `new_connections.csv`. Hidden: next week's true load, generated from
  temperature response + calendar + noise.
- **Hidden requirements**
  - `hour_ending` (ambiguous; data semantics) — History is hour-ending (HE01-HE24, as at US ISOs). The
    deliverable is hour-beginning, so shift by one hour.
  - `meter_swap` (missing; data semantics) — Z3's meter was replaced on 2026-11-16. Before that date the
    values are kW, after it MW, and the swap day has rows from both meters. This mirrors VEE
    multiplier/scaling checks.
  - `holiday` (missing; business rule) — Wed 5 May is a national holiday. Model it as a Sunday-like day.
  - `bridge_day` (missing; business rule) — Thu 6 May is a bridge day (징검다리 / 飛び石 / 桥 / puente). The
    industrial zone Z3 runs at 70% of a normal weekday, and other zones are unaffected.
  - `temp_gap` (ambiguous; data semantics) — Station W2 has `-999` sentinels and a 4-day gap in the
    forecast. Use backup station W5 with a +0.8 °C offset for zone Z2.
  - `new_load` (missing; business rule) — A data centre in Z4 energizes Tue 4 May 00:00, adding 12 MW flat.
    It appears only in `new_connections.csv`, and its status column says "pending" in the data.
  - `net_load` (ambiguous; data semantics) — The forecast is metered net load including behind-the-meter
    solar, not gross demand.
  - `score_wape` (missing; scoring) — Scoring is WAPE = Σ|e| / Σ actual across all 840 rows.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| `rows_nonneg` | physical | 840 rows, load ≥ 0 | Net load at these substations cannot go negative (no reverse-flow capacity) |
| `firm_rating` | physical | load ≤ zone transformer trip rating | Protection trips above it, so higher load is impossible |
| `submission_grid` | contractual | Hour-beginning keys exactly matching the ISO template | Agreed data-exchange format |
| `margin_3pct` | business_policy | Each zone's daily peak forecast ≥ 1.03 × the mean daily peak of that zone on the same weekday in the last 4 history weeks | Planning keeps a fixed safety margin. On the holiday and the bridge day the true peak is 10-25% lower, so the rule costs about 2-4 points of WAPE |

- **Objective** — Minimize WAPE. Reference: per-zone regression on heating/cooling degree-hours,
  hour × day-type dummies (holiday → Sunday, bridge → Z3 × 0.7), unit-fixed Z3, added 12 MW. Headroom of
  6-12% comes from lagged temperature and recency weighting.
- **Hard tier** — Duplicate rows on the swap day; CP949/Shift_JIS-encoded calendar; a late requirement
  that the data centre slips to Thursday; a deadline pulled in. Twist: the operations manager (not the
  client) insists the holiday should be treated as a Saturday.
- **Policy & language angles** — Under regulated_strict, keep the margin. Under startup_velocity, drop it
  with a note. Localize holiday names, the bridge-day concept and the day-of-week labels. es uses `dd/mm`
  dates, ja uses `年月日` in the calendar file. Pitfall: the holiday is fixed in the world, not taken from
  each country's real calendar.
- **Authoring risks** — The kW/MW jump is easy to spot, so the overlap-day duplicates carry the subtlety.
  The bridge-day factor must be stated as a number by the client, not left to the agent's guess.
- **Sources**
  - https://aunz.itron.com/w/holidays-are-no-vacation-for-the-load-forecaster
  - https://support.sas.com/resources/papers/proceedings16/SAS3080-2016.pdf
  - https://scholarworks.bwise.kr/ssu/handle/2018.sw.ssu/14423
  - https://www.pjm.com/-/media/DotCom/documents/manuals/m19.ashx
  - https://files.cpuc.ca.gov/wkgrp/wk-group/dai/pswg/APDXCVEE.DOC
  - https://blog.drhongtao.com/2017/03/gefcom2014-load-forecasting-data.html

---

### Water Leak Detection Engineer — `energy_utilities/water_leak_detection_engineer`

- **Why it matters** — Minimum night flow (MNF) analysis per district metered area (DMA) is the standard
  way to find leaks. It works by subtracting legitimate night use (UK default 1.7 L/property/h) and
  known non-domestic profiles from the 02:00-04:00 inflow. The EU Drinking Water Directive (2020/2184,
  Art. 4(3)) obliges member states to assess leakage and act above a threshold. Analysts report that
  property counts, boundary errors and night-use variability drive false alarms.
- **Client & request** — The NRW (non-revenue water) manager. "Find the leaks in our district meter data
  so we can send crews out."
- **Deliverable** — Batch `dispatch.csv`, header `dma_id,est_leak_m3_per_day`. At most 15 rows, one per
  DMA. `est_leak_m3_per_day` > 0.
- **World & data** — 48 DMAs and 90 days of 15-minute data. Files: `dma_inflow.csv` (dma_id, timestamp,
  flow, about 415k rows); `dma_pressure.csv` (dma_id, timestamp, avg_zone_pressure_m); `dma_info.csv`
  (dma_id, properties, mains_km, flow_unit); `night_users.csv` (dma_id, user, night_m3h);
  `work_orders.csv` (flushing, PRV changes, valve operations). Hidden: true leak start date and rate for
  9 DMAs, and the true night use.
- **Hidden requirements**
  - `mnf_window` (ambiguous; calculation) — MNF is the lowest 1-hour rolling mean between 02:00 and 04:00
    local. The baseline is the median of nights 31-60 back, and the current value is the median of the last
    7 nights.
  - `legit_night` (missing; calculation) — Subtract 1.7 L/property/h plus `night_users`. A hospital and a
    bakery are listed.
  - `flushing` (missing; business rule) — Nights with mains-flushing work orders are excluded.
  - `prv_change` (missing; calculation) — The DMA 17 PRV setpoint was raised 12% on day 70. Normalize
    leakage with exponent N1 = 1.0 (leak ∝ pressure^N1), because a rise that pressure explains is not a
    new leak.
  - `boundary_valve` (missing; data semantics) — The boundary valve between DMA 08 and 09 was opened on
    day 75. Flow moved from one to the other while their sum stayed flat.
  - `meter_fault` (ambiguous; data semantics) — Flat-lines of 6 h or more, zeros, and single-sample
    spikes are logger faults, not leaks. DMA 31's logger froze at a high value.
  - `units` (ambiguous; data semantics) — `flow_unit` is L/s for 6 DMAs and m³/h for the rest.
  - `crew_cap` (missing; business rule) — 15 crew-days are available this cycle. Each dispatch uses one.
  - `score_value` (missing; scoring) — Value is the true leak m³/day found in dispatched DMAs, minus 3 m³/day
    per dispatch to a DMA with no leak.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| `valid_ids` | physical | Known DMA ids, no duplicates, estimate > 0 | Malformed dispatch |
| `crew_limit` | contractual | ≤ 15 rows | Contracted crew capacity |
| `night_rise_10` | business_policy | Every DMA whose raw MNF (no corrections) rose > 10% is dispatched | Ops habit. 4-5 of the about 12 such DMAs are artefacts (flushing, PRV, valve, frozen logger), and dispatching them displaces real small leaks |

- **Objective** — Maximize value. Reference: unit-fix, fault filter, exclude flushing nights,
  pressure-normalized MNF excess over baseline, threshold 2 m³/h, top 15. It misses the boundary pair,
  which leaves 6-12% headroom.
- **Hard tier** — Duplicate timestamps from logger re-uploads; a stale `dma_info_2025.csv` with old
  property counts; a correction adding a missed flushing night. Twist: the field supervisor asks to
  "always include DMA 31" (the frozen logger).
- **Policy & language angles** — Under regulated_strict, honour `night_rise_10` even at the cost of value.
  startup_velocity drops it with justification. enterprise_balanced escalates. Localize DMA terms (블록 /
  配水ブロック / 计量分区 / sector hidráulico) and pressure units (all in metres head; avoid kgf/cm² in ko/ja
  unless converted).
- **Authoring risks** — Guarantee at most 12 raw-rise DMAs so that the policy plus the cap stays feasible.
  Leak sizes must exceed the noise in night use (about ±50% night-to-night per field reports), so give
  leaks ≥ 1.5 m³/h.
- **Sources**
  - https://help2.innovyze.com/infoworkswspro/Content/HTML/Papers_WS/paper_demand_area_analysis.htm
  - https://www.preprints.org/manuscript/202411.1010
  - https://ita.upv.es/idi/descargaarticulo.php?id=160
  - https://www.edie.net/determining-nightline-leakage-and-usage/
  - https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32020L2184

---

### EV Tariff Designer — `energy_utilities/ev_tariff_designer`

- **Why it matters** — EV time-of-use (TOU) rates are being deployed in many countries.
  - PG&E's EV2-A and EV-B put the peak at 4-9 pm and 2-9 pm on weekdays.
  - Spain's regulated 2.0TD (CNMC Circular 3/2020, art. 7.3) makes every weekend and national-holiday hour
    off-peak.
  - China's NDRC notice 1093/2021 requires a peak/valley spread of at least 4:1 (3:1 elsewhere), and
    critical peak prices at least 20% above peak.
  - Brattle's Arcturus meta-analysis shows peak reduction growing with the price ratio at a diminishing
    rate.
- **Client & request** — The pricing lead at a retail utility. "Design a time-of-use tariff for our EV
  owners."
- **Deliverable** — Batch `tariff.json`:
  `{"weekday": [24 period codes], "weekend": [24], "prices_eur_kwh": {"off_peak": x, "mid": y, "peak": z}}`.
  Period codes are `off_peak|mid|peak`, and prices exclude tax with 4 decimals.
- **World & data** — 3,000 EV customers in 3 segments (home, multi-unit, fleet). Files: `ev_load_2026.csv`
  (customer_id, segment, month, daytype, hour, kwh, 216 rows per customer, about 648k rows);
  `system_costs.csv` (month, daytype, hour, energy_cost_eur_kwh); `network_cost.md` (EUR per kW of
  coincident peak); `revenue_2026.csv`; `pilot_results.md`. Hidden: the segment elasticities, used by a
  deterministic response model.
- **Hidden requirements**
  - `rev_neutral` (missing; calculation) — Revenue at 2026 loads (no response) must equal the class revenue
    requirement within ±1%.
  - `tax_excl` (ambiguous; data semantics) — `revenue_2026.csv` includes 21% VAT and 5.11% electricity tax,
    so strip both. Deliverable prices exclude tax.
  - `ratio_band` (missing; business rule) — The regulator guideline sets peak/off-peak between 2.0 and 4.0.
  - `bill_cap` (missing; business rule) — No segment's average bill at 2026 load may rise more than 8%.
  - `peak_block` (ambiguous; business rule) — The peak must be one contiguous block of at most 5 hours, and
    at most 3 periods are allowed (rate filing template).
  - `holidays_weekend` (missing; data semantics) — National holidays are billed on the weekend profile.
    Spain treats them this way.
  - `elasticity` (missing; calculation) — Pilot results give own-price elasticity −0.10 and inter-period
    substitution elasticity 0.20 for home, and half those values for fleet.
  - `score_cost` (missing; scoring) — Cost = energy cost of the responded load + network cost × the class
    peak in the 17:00-21:00 weekday window.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| `schema` | physical | 24-entry arrays, valid codes, prices > 0 | Unbillable otherwise |
| `revenue_neutral` | contractual | ±1% at 2026 load, ex-tax | Rate-case condition |
| `ratio_bill_caps` | contractual | Ratio in [2, 4], segment bill increase ≤ 8%, single peak block ≤ 5 h | Regulator approval conditions |
| `flat_weekend` | business_policy | All weekend hours share one period | Marketing simplicity. The fleet segment has a Sunday-evening peak that then cannot be shifted, costing about 4-8% |

- **Objective** — Minimize system cost under the response model (log-ratio shift between periods, then
  own-price scaling). Reference: peak 17-21, mid 7-17 and 21-23, off-peak otherwise, ratio 3.0, prices
  solved for neutrality. Headroom of 5-10% comes from moving the block and the ratio.
- **Hard tier** — Duplicate customer rows; a stale tax rate in a backup file (VAT 10%); a late requirement
  lowering the bill cap to 5%. Twist: marketing and finance disagree on ratio 4 versus 2.5.
- **Policy & language angles** — regulated_strict keeps the flat weekend. startup_velocity may split it if
  the gain is documented. Keep a single world currency (EUR) across locales, because localized currencies
  would rescale prices. Localize the period names (경부하/중간부하/최대부하, オフピーク, 峰/平/谷, valle/llano/punta)
  and the tax names (부가세 / 消費税 / 增值税 / IVA).
- **Authoring risks** — The response model must be fully stated by the client on request. Otherwise
  optimizing against it is guesswork. Check that the reference satisfies every cap.
- **Sources**
  - https://www.boe.es/diario_boe/txt.php?id=BOE-A-2020-1066
  - https://www.pge.com/en/account/rate-plans/find-your-best-rate-plan/electric-vehicles.html
  - https://www.gov.cn/zhengce/zhengceku/2021-07/29/content_5628297.htm
  - https://www.brattle.com/insights-events/publications/arcturus-2-0-a-meta-analysis-of-time-varying-rates-for-electricity/

---

### Outage Restoration Planner — `energy_utilities/outage_restoration_planner`

- **Why it matters** — Major events drive the duration index (SAIDI), raising US average interruption
  from about 2 hours to 5.6 hours per year (EIA). Restoration order depends on load criticality and
  resource availability. Utilities are judged on SAIDI and CAIDI, and in Spain on TIEPI.
- **Client & request** — The distribution emergency manager after a storm. "Plan the restoration. We have
  the damage reports and our crews."
- **Deliverable** — Batch `restoration_plan.csv`, header `crew_id,seq,job_id,start_min`. `start_min` is
  minutes from t0 = 2027-09-14 06:00. Each job is assigned exactly once.
- **World & data** — 14 feeders, 70 sections, 62 damage jobs, 12 crews. Files: `damage_jobs.csv` (job_id,
  section_id, type: pole|span|transformer|tree|switching, duration_min, vegetation_flag); `network.csv`
  (section parent, normally-open ties, tie_capacity_mw); `customers.csv` (section_id, customers,
  load_mw, critical_type); `crews.csv` (crew_id, skills, available_from_min, home_depot);
  `travel_min.csv`. Hidden: none beyond the deterministic simulation, which energizes a section when it
  and every section upstream are repaired (or when it is back-fed through a tie).
- **Hidden requirements**
  - `critical_deadline` (missing; business rule) — Two hospitals have about 8 h of generator fuel and must
    be energized by minute 480. Water pumping stations must be energized by minute 720.
  - `tree_first` (missing; business rule) — At vegetation-flagged sites a tree job must finish before line
    work starts.
  - `skills` (ambiguous; data semantics) — Mutual-aid crews (arriving at minute 360) have the line skill
    but no switching authorization.
  - `cold_load` (missing; calculation) — A back-feed through a tie must carry 1.5 × pre-storm load after an
    outage of more than 4 h, and stay within `tie_capacity_mw`.
  - `shift` (missing; business rule) — A crew may work at most 16 h, including travel, before an 8 h rest.
  - `isolation` (missing; business rule) — Back-feeding needs a switching job first, which isolates the
    faulted section.
  - `road_closure` (ambiguous; data semantics) — Travel `-1` means a flooded road, impassable until minute
    600.
  - `score_cmi` (missing; scoring) — Customer-minutes interrupted are counted over 72 h. Restorations under
    5 min are ignored, as in IEEE 1366 momentary interruptions.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| `skills_precedence` | physical | Skill match, tree-before-line, travel feasible, no overlap | Work physically cannot happen otherwise |
| `isolation_tie` | physical | Back-feed only after isolation and within cold-load tie capacity | Safety and thermal limits |
| `critical_shift` | contractual | Hospital deadline 480, pumps 720, 16 h shift limit | Emergency plan filed with the regulator, plus labour agreement |
| `district_order` | business_policy | Districts restored in published order A→D (by first job start) | Public-communication promise. It forces long drives and costs about 8-12% CMI |

- **Objective** — Minimize CMI. Reference: greedy by customers-restored per crew-hour, with critical
  sections first and ties used when they fit. Headroom of 6-12% comes from look-ahead.
- **Hard tier** — Duplicate damage reports; a stale crew roster; a correction with a new pole job; the
  client unavailable for 2 rounds. Twist: the mayor's office demands a school shelter before the pumps.
- **Policy & language angles** — Policies differ mainly on `district_order`. Localize section names, crew
  labels and critical types (병원 / 病院 / 医院 / hospital). Times stay as integer minutes.
- **Authoring risks** — Make sure a feasible plan meets every critical deadline under the policy. Publish
  the simulation rules in full on request.
- **Sources**
  - https://www.eia.gov/todayinenergy/detail.php?id=61303
  - https://en.wikipedia.org/wiki/SAIDI
  - https://en.wikipedia.org/wiki/Power_outage
  - https://www.cpuc.ca.gov/consumer-support/psps/utility-company-psps-reports-post-event-and-post-season
