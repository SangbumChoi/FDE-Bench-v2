# Case catalog

Cases live in `cases/<field>/<role>/` and are addressed as `<field>/<role>` (e.g.
`finance/loan_underwriting_specialist`). Each case is titled by the **role** the agent plays for the client;
fields are listed with their names in all five locales in [`fields.yaml`](fields.yaml). Every case is
authored natively in zh / en / ko / ja / es and must pass `fdebench2 validate-case`. Format:
[DESIGN.md §3](../DESIGN.md#3-native-case-format).

**Status:** ✅ built and validated · ⭐ recommended first batch · (blank) planned

**Deliverable:** *Batch* = a file the agent produces (plan, decisions, forecast). *Program* = code the
evaluator runs on hidden inputs (e.g. `decide(application)`, `answer(question)`), isolated from the scorer
(see [DESIGN.md §3](../DESIGN.md#program-deliverables)).

**Data and answers on disk:** every case keeps its generated data and ground truth in `dataset/`
(`visible/<lang>/` as the agent receives it, `hidden/` for inputs it never sees, `gt/<tier>_<ruleset>/`
per setting with the reference deliverable and its score). Regenerate with `fdebench2 export-dataset`;
`validate-case` fails if the stored files drift from the generator.

Detailed, research-grounded specs for every unbuilt role are in [`docs/specs/`](../docs/specs/README.md).

Each row lists the hidden requirements the simulated client knows (examples, not exhaustive) and the
`business_policy` rule a policy may let the agent bend.

## Difficulty: one dataset, nine ground truths

A case with **settings** keeps one dataset and one request, and varies only what the client wants
(hidden requirements) and how the deliverable is scored:

- **Difficulty → content tier** (easy / medium / hard): which rules apply and how strictly they are scored.
  The data does not change; a lower tier's requirements say which parts of it are out of scope this round.
- **Rule set** (A / B / C): the hyperparameters of those rules (caps, thresholds, which item a rule
  targets, scoring weights). Each rule set has its own correct solution: a solution tuned to one is
  invalid or worse under the others.
- **Evaluation:** every difficulty is run under all three rule sets and reported as their mean, so results
  have one column per difficulty.
- **Same view:** the agent's prompt and files are byte-identical in all nine settings (`validate-case`
  checks this), and campaigns run isolated in docker, so the only way to learn this setting's rules is to ask
  the client.

How the work is handed over is a separate axis, **engagement** (`configs/engagement.yaml`), the same for
every difficulty in a comparison:

| | `full_spec` | `standard` (default) | `messy` |
|---|---|---|---|
| What the agent gets | request + full requirements | request only; must ask the client first | request only; must ask the client first |
| Client | cooperative | default | busy: terse, vague answers to vague questions |
| Question rounds | 30 | 30 | 15 |
| Data noise (agent's copy only) | none | none | duplicate rows, a stale backup file, legacy encoding |
| Mid-task events | none | none | conflicting stakeholder, client unavailable, corrected file, late-remembered fact, deadline pulled in |

Each case with settings documents them in its own `README.md`: the tier table, the rule-set table and the
reference numbers for all nine settings. Cases without settings are the same problem at every difficulty.

| Case | easy | medium adds | hard adds | Rule sets vary |
|---|---|---|---|---|
| `finance/loan_underwriting_specialist` ([settings](finance/loan_underwriting_specialist/README.md)) | Daily program `on_day`: decide each day's applications within the customer limit (product max, income cap, DSR headroom minus period lending) and the daily disbursement cap, and report the closing limit table; bureau cutoff, delinquency, reason codes, twins, tenure habit | Credit lines and stress rate in the DSR; period budget; cumulative near-prime quota; dated notices (regulator DSR cut, budget cut) | Verified income and discrepancy referral; document corrections re-decided; repayments; split same-day applications; VIP pressure notes | Policy bureau and cutoff; DSR cap; income cap; daily cap; period budget; quota; discrepancy threshold; tenure months |
| `healthcare/hospital_appointment_scheduler` ([settings](healthcare/hospital_appointment_scheduler/README.md)) | Daily program `on_day`: book each day's requests into the next 10 working days, keep the urgent reserve, refill cancellations from the waitlist in priority order, report the daily status table; 2-slot new visits, holiday closure, interpreters, move notice, same-doctor habit | Referrals that expire; blood tests with a lab cap; doctor absences and an interpreter absence (moves within the notice period) | No-shows (hidden rates) and overbooking; duplicate and multi-department requests; staff notes (keep-free, VIP) scored | Closed clinic; urgent window; interpreters; lab cap; overbooking cap; move notice; waitlist order |
| `manufacturing/procurement_specialist` ([settings](manufacturing/procurement_specialist/README.md)) | MRP core: BOM explosion, whole-week lead times, list prices with USD quotes at a planning rate, MOQ, approved vendors, monthly budget, reels, safety stock, a supplier on quality hold, dual-sourcing habit | All-units price breaks; business-day lead times with holiday weeks | Supplier lateness (exact expected cost from hidden rates); monthly allocation caps; engineering change C04 → C25 with scrap | Supplier on hold (S07 / S05 / S01); USD planning rate; safety-stock weeks; dual-sourcing max share 80/70/90% |
| `finance/stock_trading_strategist` ([settings](finance/stock_trading_strategist/README.md)) | Daily program `on_day`: fills, commission, lots, cash only, no shorts; restricted list and a dated restriction notice with a close-out deadline; large orders need approval (bendable); daily position/limit status table | Sales tax, T+2; stock and sector limits with a dated limit cut; a client cash withdrawal | Market impact; circuit-breaker session; max-drawdown mandate; insider-tip and "make it 10%" notes | Restricted list; large-order threshold; close-out deadline; stock/sector limits; withdrawal basis; drawdown mandate |
| `data_knowledge/multilingual_corpus_curator` ([settings](data_knowledge/multilingual_corpus_curator/README.md)) | 30 well-formed books scored: formats, layout, naming, description extraction, year basis | 66 books: legacy encodings, era and other year notations, full-width/decomposed titles, forbidden characters, romanized author variants, copies to merge, source precedence | All 100 books: recovery from other sources, review with reason codes, unreadable scans, junk files, zip archives, multi-book CSVs, no fabrication; books without an author go to review (bendable) | Layout (year/title/author, year/author/title, author/year_title); year basis; script; co-authors; separator; max length; fallback author |

## Finance & Banking — `finance/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| Loan Underwriting Specialist | ✅ 3×3 settings | Decision program | Program `on_day(day)` | Decide each day's personal-loan applications and keep every approval within the limits | Daily customer and bank limits with a closing limit table (scored); one product; documented income; policy bureau cutoff; DSR cap; delinquency and reason codes; protected attributes never used (twins); dated notices (regulator change, budget cut, repayments, document corrections); split applications and VIP pressure notes | Manual review for applicants recently in their job |
| AML Transaction Monitoring Analyst | ⭐ | ML + rules | Batch alerts | Flag suspicious transactions from last month | Structuring just below the reporting threshold; high-risk corridors; related-account aggregation; whitelisted payroll; daily alert budget | Always alert on a new account's first week |
| KYC Onboarding Reviewer | | Rules + matching | Batch decisions | Review these account applications | Name transliteration across ko/ja/zh romanizations; expired-ID grace period; fuzzy sanctions-list match; PEP rules | Manual review for every foreign national |
| Credit Card Fraud Analyst | | ML | Program `score(txn)` | Score card transactions for fraud | Chargeback labels arrive 45 days late; merchant-category quirks; cost-weighted metric (missed fraud ≫ false alarm) | Block every first international transaction |
| Stock Trading Strategist | ✅ 3×3 settings | Strategy | Program `on_day(day)` | Build a trading strategy for our book that beats holding the index | Follow dated instructions: restricted-list additions with a close-out deadline, a client withdrawal, a limit cut, a circuit breaker; stock/sector limits; drawdown mandate; split-adjusted prices but raw volumes; a daily position/limit status table (scored); ignore an inside tip and return pressure; synthetic prices only | Large orders need the desk head's approval |
| Collections Strategy Manager | | Optimization | Batch contact plan | Plan who we contact this week and how | Legal contact hours; max contacts per week; hardship flags; cure probability by channel | VIP customers only via their relationship manager |
| Portfolio Rebalancing Advisor | | Optimization | Batch trades | Rebalance client portfolios to target | Drift bands; tax lots and wash-sale window; minimum trade size; contractual ESG exclusions | Keep the home-country bias |
| Treasury Cash Forecaster | | ML | Batch forecast | Forecast daily cash per entity for 4 weeks | Payroll and tax calendars; FX conversion date; intercompany netting; bank holidays per country | Keep a buffer above a fixed floor |
| Insurance Claims Adjuster | | Rules + ML | Batch decisions + payouts | Settle this month's claims | Per-event vs per-year deductible; waiting period; exclusions; fraud signals; documents in mixed languages | Fast-track small claims without documents |
| Insurance Pricing Actuary | | ML + optimization | Batch premiums | Price next year's renewals | Loss-ratio target; regulatory caps on rating factors; gender not allowed; retention elasticity | Round premiums to marketing price points |

## Healthcare — `healthcare/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| Hospital Appointment Scheduler | ✅ 3×3 settings | Decision program | Program `on_day(day)` | Book each day's appointment requests and keep the clinics full | Maximize slots used: refill cancellations from the waitlist in priority order, urgent reserve, overbooking against no-shows; urgent window; interpreters; referrals and blood tests; doctor absences moved with notice; a daily status table (scored); keep-free and VIP notes to ignore | Follow-ups with the same doctor |
| Emergency Bed Manager | | Optimization | Batch bed assignments | Assign incoming admissions to wards for 72 h | Isolation needs; single-sex bays; step-down rules; bed cleaning time | Keep surgical beds reserved |
| Nurse Shift Planner | | Optimization | Batch roster | Make next month's nurse roster | Skill mix per ward; night-shift limits; legal rest; approved leave | A senior nurse on every shift |
| Operating Room Scheduler | | Optimization | Batch OR schedule | Schedule next week's surgeries | Surgeon availability; sterilization turnover; equipment conflicts; ICU bed after surgery | Pediatric cases first in the morning |
| Pharmacy Inventory Planner | | Optimization | Batch orders | Plan drug orders for the next 6 weeks | First-expiry-first-out; cold chain; caps on controlled substances; shortage substitutes | Two weeks of safety stock for everything |
| Patient No-Show Predictor | | ML + policy | Batch predictions + overbooking | Predict no-shows and set overbooking | A leaking column (reminder sent after booking); asymmetric cost; clinic-specific patterns | Never overbook pediatrics |
| Medical Claims Coder | | Rules + extraction | Batch codes | Code these visit notes for billing | Payer-specific bundling; modifiers; unit caps; notes in five languages | No unspecified codes: hold for a physician query instead |
| Clinical Trial Site Selector | | Optimization | Batch site plan | Choose sites for our new trial | Enrollment forecast; contractual diversity targets; budget; site start-up lag | Prefer existing partner sites |

## Manufacturing & Supply Chain — `manufacturing/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| Procurement Specialist | ✅ 3×3 settings | Optimization | Batch purchase orders | Plan purchases for the next 8 weeks | Demand from a BOM; MOQ per order line; resistor stock in reels; monthly budget cap; safety stock; supplier on quality hold; USD quotes at a planning rate; medium: price breaks, business-day lead times; hard: supplier lateness from history, allocation caps, an engineering change with obsolete stock | Always dual-source critical parts |
| Production Planner | | Optimization | Batch schedule | Schedule the plant for next week | Sequence-dependent setups; maintenance windows; due dates; shift calendars | Batch the same colors together |
| Quality Inspection Engineer | | ML | Program `classify(unit)` | Detect defective units from sensor data | Sensor drift after a recalibration date; one inspector's noisy labels; cost-weighted metric | Flag every unit from the new line |
| Predictive Maintenance Engineer | | ML + scheduling | Batch maintenance plan | Plan maintenance before machines fail | Censored run-to-failure data; a sensor unit change; crew capacity | Service every 500 h regardless |
| Demand Planner | | ML | Batch forecast | Forecast monthly demand per SKU and region | Promotions; cannibalization; new products with analogs; one region's distributor change | Never forecast below last year minus 20% |
| Warehouse Slotting Manager | | Optimization | Batch slot plan | Re-slot the warehouse | Hazardous-goods segregation; weight per rack level; pick frequency; ergonomic zones | Keep brand blocks together |
| Supplier Risk Analyst | | ML + rules | Batch risk tiers | Rate our suppliers' risk | Financial distress signals; geographic concentration; single-source parts | Strategic suppliers are never "high" |
| Spare Parts Planner | | ML + optimization | Batch stock levels | Set spare-part stock per site | Intermittent demand; criticality classes; obsolescence; transfer between sites | At least one of every critical part per site |
| Pallet Load Planner | | Optimization | Batch pallet builds | Build pallets for tomorrow's shipments | Weight balance; crush limits; customer pallet-height limits | One SKU per layer |

## Retail & E-commerce — `retail/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| Grocery Demand Forecaster | ✅ | ML | Batch forecast | Forecast daily sales per store × item for two weeks | Stockout censoring; returns rows; store closed Sundays; promo plan; unlisted holiday; unit change to 6-packs; WAPE | Minimum display quantity for produce and dairy |
| Markdown Pricing Manager | | Optimization | Batch prices | Set end-of-season markdowns | Price elasticity; margin floor; no below-cost sales; competitor matching | Prices end in a charm digit |
| Promotion Planner | | Optimization | Batch promo calendar | Plan next quarter's promotions | Vendor-funding contracts; cannibalization; max promotions per category | No promotions on hero SKUs |
| Assortment & Shelf Space Planner | | Optimization | Batch planogram | Allocate shelf space for the new season | Shelf capacity; minimum facings; delisting rules | Brand blocking on the shelf |
| E-commerce Search Merchandiser | | Ranking | Program `rank(query, items)` | Improve product search ranking | Hidden relevance judgments; contractual sponsored slots; out-of-stock demotion; queries in five languages | Boost the house brand |
| Returns Fraud Analyst | | ML | Batch flags | Find abusive returns | Wardrobing patterns; return windows by category; serial returners across accounts | Never flag top loyalty tier |
| Store Staffing Planner | | Optimization | Batch roster | Staff the stores from next week's traffic | Labor law; minimum staff at opening; skills per department | A manager on duty at all times |
| Marketing Budget Allocator | | Optimization | Batch budget | Split next quarter's marketing budget | Diminishing returns per channel; minimum contracted spend; attribution lag | Keep a TV spend floor |

## Logistics & Transportation — `logistics/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| Bakery Delivery Dispatcher | ✅ | Optimization | Batch routes | Plan Monday's van routes to the cafés | Road/speed/unloading model; shift window; café closed this week; cold-chain partners; one visit; lateness cost | Premium cafés first |
| Freight Load Planner | | Optimization | Batch truck loads | Consolidate tomorrow's freight into trucks | Axle weights; stacking rules; last-in-first-out by stop | One customer per truck |
| EV Fleet Charging Planner | | Optimization | Batch charging schedule | Plan overnight charging for our electric buses | Charger power limits; departure state of charge; site grid cap; time-of-use tariff | Always charge to 100% |
| Container Yard Planner | | Optimization | Batch stacking plan | Stack incoming containers to minimize rehandling | Departure order; reefer plugs; hazardous segregation; stack weight | Keep each carrier in its own block |
| Airline Crew Scheduler | | Optimization | Batch pairings | Build next month's crew pairings | Duty-time limits; rest; return to base; qualifications per aircraft | Honor seniority preferences |
| Delivery ETA Modeler | | ML | Program `eta(order)` | Predict delivery times | Time-zone mix-ups in timestamps; GPS noise; holiday traffic; metric = share within the promised window | Never promise under 30 minutes |
| Freight Invoice Auditor | | Rules + extraction | Batch audit results | Check our carriers' invoices against the contracts before we pay | Dimensional-weight divisor; fuel surcharge index and lag; accessorial charges; duplicate invoices; tax-invoice requirements per country | Pay small discrepancies without dispute |

## Customer Service & Operations — `customer_service/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| Call-Center Workforce Planner | ✅ | Optimization | Batch roster | Build next week's multilingual support roster | One language per shift; 30-min coverage; holiday at 60%; contract limits; 11 h rest; leave dates (d/m/y, rejected requests); overtime | A new hire never alone on a language |
| Support Ticket Triage Lead | ⭐ | ML + rules | Program `triage(ticket)` | Route and prioritize incoming tickets | Tickets in five languages; SLA tiers; VIP contracts; language queues; duplicate tickets | Every VIP ticket is P1 |
| Customer Churn Analyst | | ML + optimization | Batch offers | Decide who gets a retention offer | A leaking column; offer eligibility; offer budget; uplift vs risk | No offers to customers under 3 months |
| Complaint Escalation Manager | | Rules + ML | Batch classifications | Classify complaints and escalations | Regulator-reportable categories with deadlines; severity rules; repeat complainants | Auto-escalate any mention of the CEO |
| Knowledge Base QA Assistant | | Retrieval QA | Program `answer(question)` | Answer customer questions from our manuals | Manual versions per product model; refuse out-of-scope; cite the section; answer in the question's language | Always suggest premium support |
| Field Service Dispatcher | | Optimization | Batch dispatch plan | Dispatch technicians to tomorrow's jobs | Skills; SLA windows; parts on the van; travel times | Same technician for repeat visits |

## Data & Knowledge Work — `data_knowledge/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| BI Data Analyst | ✅ | Text-to-SQL | Batch answers (built); Program later | Answer our managers' business questions from the database | Fiscal year starts in April; "active" = activity in 90 days; exclude test accounts; currency conversion date; time zone of timestamps | Round reported figures to thousands |
| Multilingual Corpus Curator | ✅ 3×3 settings | Data organization | Program `organize(corpus_dir, out_dir)` | Sort our multilingual book folder into a library by year, title and author | Mixed formats (pdf, docx, epub, html, xml, json, csv, zip) and legacy encodings; era and other year notations; romanized author variants; duplicates across formats; missing or conflicting metadata routed to review with a reason code; scored on a hidden corpus | Books without an author go to review |
| Data Migration Engineer | | Data engineering | Batch merged dataset | Merge our two legacy customer databases | Duplicate detection; encodings; address normalization; which system wins on conflicts | Never merge records across regions |
| Document Extraction Specialist | | Extraction | Batch structured fields | Extract fields from these invoices | Date formats per country; VAT rules; credit notes as negatives; documents in five languages | Reject handwritten invoices |
| Report Automation Analyst | | Data engineering | Program run on hidden future months | Automate the monthly KPI report | Finance's metric definitions; restatements; late-arriving data cutoff | Show last year's figures as originally reported |
| Survey Insights Analyst | | Text classification | Batch coded responses | Code our open-ended survey answers | Taxonomy rules; multi-label rules; responses in five languages; sample weighting | Merge small categories into "other" |
| Research Literature Curator | | Classification | Batch include/exclude | Screen abstracts for our systematic review | Inclusion criteria; study-design rules; duplicate publications | Include every RCT regardless of language |

## Legal & Compliance — `legal_compliance/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| Contract Review Counsel | ✅ | Extraction + rules | Batch issue list | Review these supplier contracts | Company playbook; governing law; auto-renewal; liability caps; contracts in mixed languages | Accept vendor paper under a value threshold |
| Privacy Request Handler | | Rules + search | Batch responses | Handle this month's personal-data requests | Statutory deadlines; legal holds; identity verification; data across systems | Auto-close unverified requests after 7 days |
| Breach Notification Assessor | | Rules | Batch assessments | Tell us which data incidents must be reported, to whom and by when | Notification deadlines (72 h, 4 h, 3 business days, 30 days); risk-of-harm tests; encrypted-data exemptions; affected-count thresholds | Notify every incident regardless of risk |
| Trade Compliance Officer | | Classification + rules | Batch classifications | Classify our products for export control | Dual-use criteria; end-user screening; licence exceptions | Treat every new product as controlled until reviewed |
| Policy Q&A Assistant | | Retrieval QA | Program `answer(question)` | Answer employees' policy questions | Policy versions per country and date; cite the clause; refuse legal advice | Always recommend asking HR |

## People & HR — `people_hr/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| Resume Screening Specialist | ✅ | Ranking + rules | Batch shortlist | Shortlist candidates for these roles | Must-have vs nice-to-have; protected attributes never used; adverse-impact ratio ≥ 0.8; resumes in five languages | Boost employee referrals |
| Payroll Specialist | | Rules | Batch payslips | Run this month's payroll | Overtime rules per country; tax tables; retroactive pay; leave deductions | Round net pay to the nearest 10 |
| Workforce Attrition Analyst | | ML + optimization | Batch interventions | Find who is likely to leave and plan interventions | A leaking column; no health data allowed; intervention budget | Never target employees under probation |
| Interview Scheduler | | Optimization | Batch schedule | Schedule this week's interview panels | Time zones; interviewer load limits; panel diversity; candidate availability | Hiring manager on every panel |
| Compensation Planner | | Optimization | Batch raises | Allocate this year's merit budget | Pay bands; pay-equity gaps; budget per department | No raise above 10% |

## Energy & Utilities — `energy_utilities/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| Battery Dispatch Operator | ✅ | Optimization | Batch dispatch | Schedule our battery against tomorrow's prices | Degradation cost; state-of-charge limits; grid export cap; settlement intervals | Keep a 20% reserve |
| Solar Output Forecaster | | ML | Batch forecast | Forecast our solar farms for the next 48 h | Curtailment flags; inverter outages; daylight-saving clock shift | Never forecast above nameplate × 0.9 |
| Grid Load Forecaster | | ML | Batch forecast | Forecast hourly load for next week | Meter replacement with a unit change; holidays; temperature feed gaps | Add a fixed safety margin |
| Water Leak Detection Engineer | | Anomaly detection | Batch alerts | Find leaks in our district meter data | Night-flow baseline; maintenance flushing; meter faults vs leaks | Alert on every night-flow rise above 10% |
| EV Tariff Designer | | Optimization | Batch tariff | Design a time-of-use tariff for EV owners | Revenue neutrality; regulatory caps; peak-shift elasticity | Keep a flat weekend price |
| Outage Restoration Planner | | Optimization | Batch crew plan | Plan restoration after the storm | Critical customers (hospitals); crew skills; switching sequence | Restore by district order |

## Public Sector — `public_sector/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| Benefits Eligibility Officer | ✅ | Rules | Batch determinations | Decide these benefit applications | Household composition rules; income disregards; applicants in five languages; deadlines | Auto-approve renewals |
| Tax Return Reviewer | | ML + rules | Batch audit selection | Pick returns to audit with our budget | Rule-based red flags; audit capacity; legal limits on selection criteria | Always audit returns above a threshold |
| School Timetabling Coordinator | | Optimization | Batch timetable | Build next term's timetable | Teacher loads; room types; part-time teachers' days | No double periods for the youngest grades |
| Public Transit Planner | | Optimization | Batch frequencies | Set bus frequencies within budget | Equity coverage requirement; driver hours; peak capacity | Keep every route at least hourly |
| Permit Application Processor | | Rules + extraction | Batch decisions | Triage building permit applications | Zoning rules; missing documents; statutory review deadlines | Fast-track applications from frequent filers |

## Recommended first batch

Your five plus three high-demand additions, covering both deliverable types:

1. `finance/loan_underwriting_specialist`
2. `healthcare/hospital_appointment_scheduler`
3. `manufacturing/procurement_specialist`
4. `data_knowledge/multilingual_corpus_curator`
5. `finance/stock_trading_strategist`
6. `data_knowledge/bi_data_analyst`
7. `finance/aml_transaction_monitoring_analyst`
8. `customer_service/support_ticket_triage_lead`
