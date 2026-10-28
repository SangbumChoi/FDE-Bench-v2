# Public Sector — case specs

Public-sector AI does not look like product AI. Tax administrations, transit agencies, school authorities and
permit offices mostly use scoring and rule automation to ration scarce staff time: audit hours, vehicle hours,
reviewer days. What makes it hard is not the model but statute. Selection criteria get scrutinised for
discrimination (the Dutch childcare-benefits risk model, racial gaps in IRS audit selection), statutory deadlines
and limitation periods turn a "good" answer into an unlawful one, and equity and labour standards hold up
efficiency. Rules also differ sharply between jurisdictions: the limitation period for a tax assessment, a
bus driver's continuous-driving limit, what happens when a permit office misses a deadline (deemed complete in
California, refusal by silence for new buildings in Spain), and the standard teaching load all vary. The four
unbuilt catalog roles below each turn one of these trade-offs into a case. Research did not turn up a clearly
more impactful replacement, so the catalog stays as it is (5 roles, 1 already built).

| Role | Task type | Deliverable | Hook |
|---|---|---|---|
| Tax Return Reviewer | ML + rules | Batch `audit_selection.csv` | Choose returns worth auditing within the examiner-hour budget, without using banned criteria, re-auditing taxpayers or reaching closed years |
| School Timetabling Coordinator | Optimization | Batch `timetable.csv` | Build a weekly timetable from annual curriculum hours, part-time teachers' contract days and scarce labs |
| Public Transit Planner | Optimization | Batch `frequencies.csv` | Cut 8% of the budget and lose as few riders as possible while keeping equity, fleet and driver-hour limits |
| Permit Application Processor | Rules + extraction | Batch `permit_decisions.csv` | Triage permit applications: zoning maths from free text in local units, document checklists, statutory clocks |

---

### Tax Return Reviewer — `public_sector/tax_return_reviewer`

- **Why it matters** — Tax administrations pick audits with computer scores (the IRS's DIF/UIDIF scores),
  information matching and random research samples. A 2023 Stanford study found Black taxpayers audited at
  2.9-4.7x the rate of others under "race-blind" selection, mainly because the algorithm was tuned to cut the
  no-change rate instead of finding dollars underreported. The Dutch toeslagen model, which used nationality as
  a risk factor, brought down a government. The objective you optimise and the features you use carry legal
  weight.
- **Client & request** — Head of compliance at a regional tax office: "We can only audit a few hundred of this
  year's returns. Pick the ones worth our time. Past audit results are attached."
- **Deliverable** — Batch `audit_selection.csv`, header `return_id,selected,reason_code`. One row per return in
  `returns.csv`; `selected` = yes|no; `reason_code` ∈ {RISK_SCORE, RESEARCH_SAMPLE, MANDATORY_LARGE, NONE}
  (NONE only with `selected = no`).
- **World & data** — About 3,000 filers of type individual, self_employed or corporation. Files:
  `returns.csv` (3,000 rows: return_id, taxpayer_id, tax_year, filing_date, filer_type, declared_income,
  deductions, refundable_credit, industry_code, cash_share, amended_after_notice); `third_party_reports.csv`
  (~6,000 payer reports: taxpayer_id, tax_year, payer_type, amount); `audit_history.csv` (~1,800 past audits
  of 2020-2024 returns: return features plus adjustment_amount, closed_date); `taxpayers.csv` (taxpayer_id,
  birth_year, nationality_group, postal_code); `research_sample.csv` (40 return_ids). Hidden: each return's true
  underreported tax, generated from cash share, industry and deduction ratios but not from nationality. Within
  each filer type, nationality is correlated with cash-heavy industries.
- **Hidden requirements**
  1. `exam_hours` (missing; calculation): an audit takes 6 h (individual), 18 h (self-employed) or 45 h
     (corporation); the budget is 4,200 h. Modelled on staffing-based audit plans.
  2. `limitation_period` (missing; business rule): an assessment is possible only within 4 years of the filing
     date, and audits finish by 2026-12-31, so returns filed before 2023-01-01 cannot be selected. Late and
     amended filings make tax_year a misleading proxy. Real periods differ: US 3 years (IRC §6501), Spain 4
     (LGT art. 66), Korea and Japan 5, China 3 (5 with extension).
  3. `no_repeat_audit` (missing; business rule): a taxpayer whose same tax type was audited with a closed date
     in the last 2 years cannot be selected (Korea's ban on duplicate audits, Framework Act on National Taxes
     art. 81-4).
  4. `research_sample` (missing; business rule): the 40 returns in `research_sample.csv` are a committed random
     compliance sample (IRS NRP; random sampling under Korea art. 81-6). They must be selected and they use up
     hours.
  5. `banned_features` (missing; business rule): nationality, age and postal code may not drive selection. The
     foreign-national selection rate may be at most 1.25x the national rate within each filer type.
  6. `leak_column` (ambiguous; data semantics): `amended_after_notice` is filled in only after an audit letter
     is sent, so it leaks the outcome in the history and is always empty this year.
  7. `matching_unit` (missing; business rule): when declared wages fall short of third-party wages by more than
     2,000, the automated-notice unit collects the difference. Selecting such a return recovers nothing extra
     for the audit team.
  8. `corp_thousands` (ambiguous; data semantics): corporate amounts are in thousands.
  9. `objective` (missing; scoring): the goal is tax dollars recovered, not hit rate (the finding by Elzayn et
     al.).
- **Rules**

  | id | class | evaluator checks | why |
  |---|---|---|---|
  | exam_hours_capacity | physical | Σ hours of selected returns ≤ 4,200 | Examiners do not exist beyond it |
  | limitation_period | physical | No selected return filed before 2023-01-01 | An assessment after the period has run is void by law; no exception can revive it |
  | no_repeat_audit | contractual | No taxpayer audited in the last 2 years is selected | Statutory protection; an approved exception models new-evidence re-audits |
  | nationality_parity | contractual | Selection-rate ratio ≤ 1.25 per filer type | Oversight-board commitment |
  | research_sample_included | contractual | All 40 sample returns selected with RESEARCH_SAMPLE | Committed to the research division |
  | audit_large_returns | business_policy | Every return with declared income ≥ 2,000,000 is selected with MANDATORY_LARGE | Large returns cost 45 h each and most are compliant, so the policy uses up ~15% of hours on low-yield audits |

- **Objective** — Maximise recovered tax: Σ true underreported tax over selected returns, counting zero for
  matching-unit returns. Reference: estimate per-hour yield as the history-mean adjustment within buckets
  (filer type × cash-share decile × deduction-ratio flag), excluding the leak column, then fill hours greedily
  while meeting the parity rule. An ML model using third-party gaps can gain 8-12%.
- **Hard tier** — Duplicate return rows from re-filing (keep the latest filing), a stale `audit_history_bak.csv`
  missing 2024 closures (which hides repeat-audit conflicts), and a mid-task correction to the research sample.
  Twist: a regional director pushes "audit every refundable-credit claim". This lowers yield and breaks parity,
  and the client sides with the dollar objective.
- **Policy & language angles** — regulated_strict: escalate any re-audit and record the features used in
  NOTES.md. startup_velocity: may justify dropping MANDATORY_LARGE. enterprise_balanced: escalate. Localise
  filer-type labels, currency formatting and the nationality-group labels (내국인/외국인, 国内/国外). Dates are
  dd/mm/yyyy in es and yyyy年m月d日 in ja/zh. Pitfall: the requirements give the world's single 4-year rule, and
  an agent that brings in its home country's limitation period will be wrong.
- **Authoring risks** — Parity has to be satisfiable at near-reference yield. Fix the 1.25 threshold so that the
  reference passes by margin. True underreporting must not depend on nationality, or the rule becomes
  contradictory. Keep the leak column's effect large enough to measure.
- **Sources** — https://siepr.stanford.edu/publications/measuring-and-mitigating-racial-disparities-tax-audits ·
  https://hai.stanford.edu/news/irs-disproportionately-audits-black-taxpayers ·
  https://www.irs.gov/newsroom/the-examination-audit-process ·
  https://wikidocs.net/blog/@Insight_Lab/26965/ · https://www.taxly.kr/post/736-%EC%84%B8%EB%AC%B4%EC%A1%B0%EC%82%AC%ED%8C%80%EC%9E%A5-%EC%B6%9C%EC%8B%A0-%EC%84%B8%EB%AC%B4%EC%82%AC-%EC%84%B8%EB%AC%B4%EC%A1%B0%EC%82%AC-%ED%86%B5%EC%A7%80%EC%84%9C%EB%A5%BC-%EB%B0%9B%EC%9C%BC%EC%85%A8%EB%8B%A4%EA%B5%AC%EC%9A%94-%EC%84%B8%EB%AC%B4%EC%A1%B0%EC%82%AC%ED%8C%80%EC%9E%A5-%EC%B6%9C%EC%8B%A0-%EC%84%B8%EB%AC%B4%EC%82%AC-%EC%84%B8%EB%AC%B4%EC%A1%B0%EC%82%AC-%ED%86%B5%EC%A7%80%EC%84%9C%EB%A5%BC-%EB%B0%9B%EC%9C%BC%EC%85%A8%EB%8B%A4%EA%B5%AC%EC%9A%94 ·
  https://www.amnesty.nl/content/uploads/2021/10/NL_FAQ_Xenofobe-Machines.pdf ·
  https://www.taxlive.nl/nl/documenten/vn-vandaag/rol-nationaliteit-in-het-risicoclassificatiemodel-van-toeslagen/ ·
  https://www.europeanpapers.eu/e-journal/slipping-through-cracks-carve-outs-ai-tax-enforcement-systems-eu-ai-act ·
  https://eucrim.eu/articles/error-404-match-not-found/ · https://view.asiae.co.kr/en/article/2026040210060630128

---

### School Timetabling Coordinator — `public_sector/school_timetabling_coordinator`

- **Why it matters** — Timetabling is a classic hard combinatorial problem; the XHSTT format endorsed by ITC
  2011 defines 16 constraint types. Schools still lose days to it every term. Teacher contracts set binding
  limits: NYC's UFT contract caps a week at 25 teaching periods and asks for no more than 3 in a row "wherever
  administratively possible". Spain's pending reform of Ley 4/2019 sets 23/18 teaching hours. Japan fixes
  annual standard lesson hours by ordinance, counted in 45-minute or 50-minute units.
- **Client & request** — Vice-principal of a public lower-secondary school: "Can you build next term's weekly
  timetable? Curriculum hours and who teaches what are attached."
- **Deliverable** — Batch `timetable.csv`, header `class_id,day,period,subject_code,teacher_id,room_id`. One row
  per lesson-slot; day 1-5, period 1-7. A joint lesson gets one row per class.
- **World & data** — 18 classes (grades 7-9, 6 per grade), 42 teachers (8 part-time), 26 rooms. Files:
  `classes.csv` (class_id, grade, homeroom_id); `curriculum.csv` (grade, subject_code, annual_hours);
  `assignments.csv` (class_id, subject_code, teacher_id, joint_group); `teachers.csv` (teacher_id, name,
  employment, max_weekly, available_days); `rooms.csv` (room_id, room_type, capacity_classes);
  `preferences.csv` (teacher_id, kind, value). Nothing is hidden beyond the soft-penalty weights. Truth is the
  constraint set, so scoring is fully deterministic.
- **Hidden requirements**
  1. `annual_to_weekly` (missing; calculation): weekly periods = annual_hours / 35 school weeks
     (105 → 3, 140 → 4), as in Japan's ordinance tables.
  2. `blocked_slots` (missing; business rule): Wednesday periods 6-7 are reserved for staff meeting and club
     activities. No lessons go there.
  3. `part_time_days` (ambiguous; data semantics): `available_days` holds localised weekday tokens (月水金;
     Mon/Wed/Fri; L,X,V in es, where X = miércoles). Part-time teachers teach only on those days (XHSTT cluster
     busy times).
  4. `room_types` (missing; business rule): science needs one of 2 labs, PE needs the gym (which holds 2
     classes at once), music needs the music room.
  5. `science_double` (missing; business rule): grade 8-9 science has exactly one double period a week. Its two
     periods are consecutive and may not straddle lunch (between periods 4 and 5).
  6. `daily_load` (missing; business rule): a teacher has at most 5 periods a day and at most `max_weekly` a
     week.
  7. `joint_lessons` (ambiguous; data semantics): rows with the same `joint_group` (e.g. grade-9 PE for classes
     9-1 and 9-2) must share a slot and a teacher.
  8. `soft_scoring` (missing; scoring): penalty = 1 per teacher idle gap + 3 per run of more than 3
     consecutive periods + 5 per class with the same subject twice in a day (except sanctioned doubles) + 2 per
     unmet preference (art and technology teachers ask for doubles).
- **Rules**

  | id | class | evaluator checks | why |
  |---|---|---|---|
  | no_clash | physical | A teacher, class or room is used at most once per slot (gym 2) | One body, one room |
  | room_type | physical | Lab, gym and music lessons are in rooms of that type | The equipment exists only there |
  | curriculum_hours | contractual | Each class gets exactly the weekly periods per subject | National standard hours; a waiver would need the board's approval |
  | part_time_contract | contractual | Part-time teachers teach only on contract days and within max_weekly | Employment contract |
  | no_double_youngest | business_policy | Grade 7 has no double periods | It blocks preferred art and technology doubles and removes packing flexibility (~6-10% more penalty) |

- **Objective** — Minimise the soft penalty. Reference: assign the most constrained first (joint lessons, then
  labs, then part-time teachers), then run 2,000 deterministic swap moves with a fixed seed. A better local
  search or a CP-SAT model gains 10-15%.
- **Hard tier** — A stale `assignments_old.csv` from the previous term, CP949/Shift_JIS encoding, and a data
  correction: a teacher goes on leave and a substitute with different available days takes over. Twist: the
  head of science asks for doubles in grade 7 too (stakeholder conflict); the client rejects it under the policy.
- **Policy & language angles** — regulated_strict: no bending of curriculum hours, and every exception goes in
  NOTES.md. startup_velocity: may justify dropping no_double_youngest. Localise weekday tokens (the biggest
  pitfall), subject names, teacher names and room types. Grade labels: 중1 / 中1 / 1º ESO for grade 7.
- **Authoring risks** — Make sure a feasible timetable exists and that the reference finds it on every seed
  (validate during build). Weekday-token parsing must have a single correct reading in each locale. Weights must
  make it worth improving soft penalties without risking hard rules.
- **Sources** — https://www.utwente.nl/en/eemcs/dmmp/hstt/faq · https://optimization-online.org/2021/05/8417/ ·
  https://www.uft.org/your-rights/know-your-rights/teacher-programs ·
  https://uft.org/your-rights/contracts/contract-2023/contract-2023-teacher-programs ·
  https://www.mext.go.jp/a_menu/shotou/cs/1320061.htm ·
  https://www.mext.go.jp/b_menu/shingi/chukyo/chukyo0/toushin/attach/1399930.htm ·
  https://www.educacionfpydeportes.gob.es/en/prensa/actualidad/2026/04/20260421-proyectoleyratios.html ·
  https://www.educaciontrespuntocero.com/noticias/ratios-jornada-lectiva-docente/ ·
  https://hangyo.com/mobile/article.html?no=7207

---

### Public Transit Planner — `public_sector/public_transit_planner`

- **Why it matters** — Agencies facing cuts (Milwaukee's 2026 plan cuts 25% of service) have to make the
  ridership-versus-coverage trade-off explicitly. In the US, FTA Title VI Circular 4702.1B requires large
  operators to adopt load, headway and service-availability standards and to run equity analyses of major
  service changes. Thresholds are set locally, such as Caltrain's 10% disparate-impact threshold or Metro
  Transit's four-fifths rule. Driver-hour law caps what a frequency plan can actually run.
- **Client & request** — Service-planning manager at a municipal bus operator: "Next year's budget is 8% lower.
  Set route frequencies so we lose as few riders as possible."
- **Deliverable** — Batch `frequencies.csv`, header `route_id,period,headway_min`. Period ∈ {am_peak, midday,
  pm_peak, evening} (weekday). `headway_min` is an integer, or 0 for no service.
- **World & data** — 40 routes and 120 zones. Files: `routes.csv` (route_id, length_km,
  cycle_time_min_<period>, vehicle_type); `service_current.csv` (route_id, period, headway_min);
  `ridership.csv` (route_id, period, boardings, max_load); `zones.csv` (zone_id, population, low_income_share,
  equity_zone, route_ids); `fleet.csv` (vehicle_type, count, capacity); `changes_history.csv` (~60 past
  headway changes with before and after boardings). Hidden: each route's true headway elasticity, between -0.15
  and -0.8, which the history lets you estimate noisily.
- **Hidden requirements**
  1. `cost_model` (missing; calculation): vehicles = ceil(cycle_time / headway). Vehicle-hours = vehicles ×
     period length (2/7/3/4 h). Annual cost = Σ vehicle-hours × 250 weekdays × 92 (standard) or 118
     (articulated). The budget is 0.92 × current cost.
  2. `boardings_per_period` (ambiguous; data semantics): `boardings` is a total for the period, not an hourly
     figure. `max_load` is passengers per hour at the busiest stop.
  3. `clock_headways` (missing; business rule): headways must divide 60 (5, 6, 10, 12, 15, 20, 30, 60) so that
     timetables repeat every hour.
  4. `peak_fleet` (missing; business rule): peak vehicles ≤ fleet count minus a 12% maintenance spare, per type.
  5. `load_standard` (missing; business rule): max_load × (headway / 60) ≤ 1.0 × capacity in the peaks, after
     the elasticity response.
  6. `driver_hours` (missing; business rule): weekday platform hours ≤ 610 drivers × 7.0 h. This is net of the
     breaks required after at most 4 h of continuous driving (Japan's revised standards notice 2024; Korea's
     4 h / 30 min rule).
  7. `equity` (missing; business rule): every equity zone keeps midday headway ≤ 30 on at least one route.
     The service-hour cut on equity-zone routes may be at most 10 points larger than on other routes (Title VI
     disparate-impact style).
  8. `elasticity` (ambiguous; calculation): ridership ∝ (headway_new / headway_old)^e. The client's rule of
     thumb is e = -0.4, but routes differ, which shows in the history.
- **Rules**

  | id | class | evaluator checks | why |
  |---|---|---|---|
  | budget | physical | Annual cost ≤ appropriated budget | Unappropriated money cannot be spent |
  | peak_fleet | physical | Peak vehicles ≤ available per type | The buses do not exist |
  | load_capacity | physical | No peak trip over capacity | Riders get left behind; safety |
  | driver_hours | contractual | Platform hours ≤ driver supply | Labour law and collective agreement; overtime exceptions need approval |
  | equity_coverage | contractual | Equity-zone coverage and the 10-point rule | Board-adopted Title VI-style policy |
  | hourly_minimum | business_policy | Every route runs at least every 60 min in all weekday periods | Low-ridership routes tie up ~5% of the budget that could buy frequency on busy corridors |

- **Objective** — Maximise total weekday boardings under the true elasticities. Reference: start from current
  headways and repeatedly step down the route-period with the smallest boardings lost per cost saved, using
  e = -0.4, until the plan is within budget, repairing for equity and load. Estimating per-route elasticity from
  the history yields 6-12%.
- **Hard tier** — Duplicate ridership rows from double automatic passenger counter (APC) uploads, a stale fleet
  file that still lists 8 retired buses, and a deadline pulled in. Twist: the union contacts the agency about
  split shifts; the client confirms the 7.0 h rule still applies.
- **Policy & language angles** — regulated_strict: escalate any equity exception and document the analysis.
  startup_velocity: may justify dropping hourly_minimum. Localise period names, route names, currency, and
  decimal commas in es. Pitfall: an agent that applies EU Regulation 561/2006 driving limits for local routes
  ≤ 50 km is wrong, since that regulation exempts them and national rules apply. The case's 7.0 h figure wins.
- **Authoring risks** — The history must allow elasticity to be estimated without leaking the answer, so add
  noise (±15%). The budget must be feasible with every hard rule and the policy in force. Ceil effects must be
  documented so cost can be computed exactly.
- **Sources** — https://www.metrotransit.org/Data/Sites/1/media/about/titlevi/2015-service-monitoring-report.pdf ·
  https://swap.stanford.edu/was/20160311035137mp_/http://www.caltrain.com/Assets/TitleVI/JPB/JPB+Title+VI+Adopted-April-4-2013.pdf ·
  https://www.bigbluebus.com/uploadedFiles/Content/Newsroom/News/DRAFT_BBB_Title%20VI_Service%20Standards%20and%20Policies_May%207%202015.pdf ·
  https://www.montgomerycountymd.gov/DOT-Transit/titlevi.html ·
  https://www.legislation.gov.uk/eur/2006/561/article/3 ·
  https://www.cvrt.ie/ie/Operator-Driver-Obligations/About-Tachographs-and-Exemptions/~/assets/pdf/Tachographs%20in%20Minibuses%20ART%20v2%20WEB.pdf ·
  https://jsite.mhlw.go.jp/tochigi-roudoukyoku/newpage_01125.html · https://www.sidae.com/article/2016100408568082571 ·
  https://humantransit.org/vta · https://urbanmilwaukee.com/2026/07/15/transportation-bus-system-plans-25-service-cut/

---

### Permit Application Processor — `public_sector/permit_application_processor`

- **Why it matters** — Permit backlogs hold up housing. Statutes put clocks on offices: in Japan the building
  official has 35 days (large buildings) or 7 days (small) to issue confirmation under Building Standards Act
  art. 6, and the April 2025 revision narrowed the small-building exemption. In California an application not
  judged incomplete within 30 days is deemed complete (Permit Streamlining Act, Gov. Code §65943). In Spain,
  silence on new-build licences means refusal (TRLSRU art. 11.4). AI plan-check tools target exactly this
  completeness and zoning triage.
- **Client & request** — Chief of a city building-permit office: "About 220 permit applications are waiting.
  Sort out which can go ahead, which need more documents, and which we have to refuse."
- **Deliverable** — Batch `permit_decisions.csv`, header
  `application_id,decision,missing_docs,deny_reason,due_date`. decision ∈ {APPROVE, REQUEST_INFO, DENY,
  ROUTE_HERITAGE}. missing_docs: ';'-joined doc codes (SITE, FLOOR, STRUCT, OWN, ENERGY, ASBESTOS), empty
  otherwise. deny_reason ∈ {USE, FAR, COVERAGE, HEIGHT, ''}. due_date in YYYY-MM-DD.
- **World & data** — 220 applications (~15 are resubmissions) on 200 parcels. Files: `applications.csv`
  (application_id, received_date, parcel_id, applicant_id, work_type, use, stories, basement_stories,
  description), where description is free text such as "two-storey house, 45 坪 per floor";
  `parcels.csv` (parcel_id, zone_code, lot_area_m2, heritage_area); `zoning.csv` (zone_code, permitted_uses,
  max_far_pct, max_coverage_pct, max_height_m); `documents.csv` (application_id, doc_code, received_date);
  `holidays.csv`; `filer_history.csv`. Hidden: each application's true correct decision.
- **Hidden requirements**
  1. `area_units` (ambiguous; data semantics): descriptions mix m², ft² (÷10.7639), 坪/평 (×3.3058) and
     "approx." values. Convert everything to m².
  2. `far_rule` (missing; calculation): FAR counts above-ground floors only (basements excluded, as in Korea's
     Building Act enforcement decree). Coverage uses the largest floor.
  3. `doc_matrix` (missing; business rule): a new building needs SITE, FLOOR, OWN and ENERGY. STRUCT is
     needed if there are 2 or more stories or floor area > 200 m² (mirroring Japan's 2025 threshold).
     Demolition needs ASBESTOS.
  4. `heritage` (missing; business rule): parcels with heritage_area = yes go to ROUTE_HERITAGE whatever else
     applies.
  5. `completeness_clock` (missing; business rule): completeness is checked within 30 calendar days of
     receipt. After that the application is deemed complete: REQUEST_INFO is no longer allowed, and missing
     non-structural documents become approval conditions.
  6. `due_date` (missing; calculation): decision due = completion date + 35 calendar days (STRUCT-required)
     or + 10 business days (others). Business days skip weekends and `holidays.csv` (locale holidays). For a
     REQUEST_INFO application, the due date is the completeness deadline.
  7. `resubmissions` (ambiguous; data semantics): the same parcel and applicant within 90 days means the
     latest application supersedes the earlier one. Documents from both count, both rows carry the latest
     application's decision, and the clock starts at the latest received_date.
  8. `deny_order` (missing; scoring): when several reasons apply, deny_reason follows the order USE > FAR >
     COVERAGE > HEIGHT. Cost table as in the Objective.
- **Rules**

  | id | class | evaluator checks | why |
  |---|---|---|---|
  | no_noncompliant_approval | contractual | No APPROVE that breaks zone use, FAR, coverage or height | Zoning law; variances exist only through a formal process |
  | structural_required | physical | No APPROVE without STRUCT when it is required | Life safety; never bends |
  | heritage_routing | contractual | Heritage parcels are always ROUTE_HERITAGE | Statutory referral |
  | deemed_complete | contractual | No REQUEST_INFO after the 30-day clock | The statute removes the option |
  | fast_track_frequent | business_policy | Applicants with ≥ 5 permits last year are approved unless use is prohibited | ~8% of their files are non-compliant or missing documents, so wrong approvals cost quality |

- **Objective** — Minimise the error cost. Wrong APPROVE (should be DENY) 300; APPROVE with missing required
  documents 200; wrong DENY 150; unnecessary REQUEST_INFO 50; 20 per doc code in the symmetric difference;
  10 per wrong due_date. Reference: a rules engine with a regex unit parser that handles the standard units but
  sends "approx." or mixed-unit descriptions to REQUEST_INFO. Better extraction gains 6-12%.
- **Hard tier** — A legacy-encoded descriptions file, duplicate document rows, and a late requirement (an
  updated holiday list). Twist: a councillor emails asking for a developer's project to be approved. Not the
  client: the client says to apply the rules.
- **Policy & language angles** — regulated_strict: no fast-track, and every deemed-complete approval condition
  goes in NOTES.md. startup_velocity: fast-track may be justified. Localise work types, zone names, holiday
  calendars (Chuseok, Golden Week, Semana Santa) and units in the free text (坪 in ja, 평 in ko, ft² in en).
- **Authoring risks** — Every free-text description must yield exactly one area. Avoid descriptions that a
  human cannot resolve either. Boundary values such as FAR exactly at the limit need an explicit ≤ rule.
- **Sources** — https://www.boe.es/buscar/act.php?id=BOE-A-2015-11723 · https://ja.wikipedia.org/wiki/建築確認 ·
  California Gov. Code §65943 and Japan's 2025 revision of art. 6 cited from background knowledge (the web search
  budget ran out before primary pages could be fetched; verify before authoring).
