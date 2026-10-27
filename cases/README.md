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
| `finance/loan_underwriting_specialist` ([settings](finance/loan_underwriting_specialist/README.md)) | Underwriting core: one product and its limits, declared salary + documented bonus, policy-bureau cutoff, delinquency, DSR on installment loans, ordered reason codes, protected-attribute twins, tenure referral habit | Credit lines amortized over 5 years in the DSR; stress add-on above 60,000 debt; near-prime quota | Verified income (lowest of declared/documented) with a discrepancy referral; duplicate applications, one loan per person | Policy bureau and cutoff (A ≥ 650 / B on Bureau B ≥ 740 / A ≥ 680); near-prime threshold; DSR cap 40/35/45%; quota 30/25/35%; discrepancy threshold; tenure months 6/3/12 |
| `healthcare/hospital_appointment_scheduler` ([settings](healthcare/hospital_appointment_scheduler/README.md)) | Booking core: 2-slot new visits, urgent window, holiday closure, same-doctor follow-ups (one doctor on leave), interpreters | Referral letters that expire; pre-visit blood test with a daily lab cap | No-show risk by patient and lead time; overbooking of follow-ups; expected idle/collision cost | Clinic closed on the holiday; urgent window; interpreters; lab cap; overbooking cap; "soon" window |
| `manufacturing/procurement_specialist` ([settings](manufacturing/procurement_specialist/README.md)) | MRP core: BOM explosion, whole-week lead times, list prices with USD quotes at a planning rate, MOQ, approved vendors, monthly budget, reels, safety stock, a supplier on quality hold, dual-sourcing habit | All-units price breaks; business-day lead times with holiday weeks | Supplier lateness (exact expected cost from hidden rates); monthly allocation caps; engineering change C04 → C25 with scrap | Supplier on hold (S07 / S05 / S01); USD planning rate; safety-stock weeks; dual-sourcing max share 80/70/90% |
| `finance/stock_trading_strategist` ([settings](finance/stock_trading_strategist/README.md)) | Trading core on 16 stocks: fills at p10 ± half spread or the opening auction, commission, board lots, cash only, no shorts, a restricted list, no trading in the first 10 minutes (bendable) | Sales tax, T+2 settlement; stock and sector limits; order size vs average volume (raw volumes after a consolidation) | Market impact; a max-drawdown mandate through a sell-off | Restricted list (MEDQ+ZENT / NEXO+PYRO / BRAX+DUNE); stock/sector limits 15/40, 10/25, 20/50%; volume cap 10/15/5%; max drawdown 15/10/12% |
| `data_knowledge/multilingual_corpus_curator` ([settings](data_knowledge/multilingual_corpus_curator/README.md)) | 30 well-formed books scored: formats, layout, naming, description extraction, year basis | 66 books: legacy encodings, era and other year notations, full-width/decomposed titles, forbidden characters, romanized author variants, copies to merge, source precedence | All 100 books: recovery from other sources, review with reason codes, unreadable scans, junk files, zip archives, multi-book CSVs, no fabrication; books without an author go to review (bendable) | Layout (year/title/author, year/author/title, author/year_title); year basis; script; co-authors; separator; max length; fallback author |

## Finance & Banking — `finance/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| Loan Underwriting Specialist | ✅ 3×3 settings | ML + rules | Batch decisions | Decide our pending personal-loan applications and their limits (one product) | Income = salary + documented bonus only; policy bureau and its cutoff; DSR cap; limit ≤ annual income; delinquency and reason codes; protected attributes never used (twins); medium: credit lines amortized over 5 years, stress add-on, near-prime quota; hard: verified income with a discrepancy referral, duplicate applications linked by bureau file number | Manual review for applicants recently in their job |
| AML Transaction Monitoring Analyst | ⭐ | ML + rules | Batch alerts | Flag suspicious transactions from last month | Structuring just below the reporting threshold; high-risk corridors; related-account aggregation; whitelisted payroll; daily alert budget | Always alert on a new account's first week |
| KYC Onboarding Reviewer | | Rules + matching | Batch decisions | Review these account applications | Name transliteration across ko/ja/zh romanizations; expired-ID grace period; fuzzy sanctions-list match; PEP rules | Manual review for every foreign national |
| Credit Card Fraud Analyst | | ML | Program `score(txn)` | Score card transactions for fraud | Chargeback labels arrive 45 days late; merchant-category quirks; cost-weighted metric (missed fraud ≫ false alarm) | Block every first international transaction |
| Stock Trading Strategist | ✅ 3×3 settings | Strategy | Program `on_day(day)` | Build a trading strategy for our book that beats holding the index | Fills at p10 plus half spread; commission; board lots; no shorts; a restricted list; medium: sales tax, T+2 settlement, halts, split-adjusted prices but raw volumes, stock / sector limits, a volume cap; hard: market impact, earnings moves at the open, a hidden-period split, max drawdown; synthetic prices only | No trading in the first 10 minutes |
| Collections Strategy Manager | | Optimization | Batch contact plan | Plan who we contact this week and how | Legal contact hours; max contacts per week; hardship flags; cure probability by channel | VIP customers only via their relationship manager |
| Portfolio Rebalancing Advisor | | Optimization | Batch trades | Rebalance client portfolios to target | Drift bands; tax lots and wash-sale window; minimum trade size; contractual ESG exclusions | Keep the home-country bias |
| Treasury Cash Forecaster | | ML | Batch forecast | Forecast daily cash per entity for 4 weeks | Payroll and tax calendars; FX conversion date; intercompany netting; bank holidays per country | Keep a buffer above a fixed floor |
| Insurance Claims Adjuster | | Rules + ML | Batch decisions + payouts | Settle this month's claims | Per-event vs per-year deductible; waiting period; exclusions; fraud signals; documents in mixed languages | Fast-track small claims without documents |
| Insurance Pricing Actuary | | ML + optimization | Batch premiums | Price next year's renewals | Loss-ratio target; regulatory caps on rating factors; gender not allowed; retention elasticity | Round premiums to marketing price points |

## Healthcare — `healthcare/`

| Role | Status | Type | Deliverable | The client asks | Hidden requirements | Bendable rule |
|---|---|---|---|---|---|---|
| Hospital Appointment Scheduler | ✅ 3×3 settings | Optimization | Batch bookings | Schedule two weeks of appointment requests | Day/month/year dates; urgent within 2 working days; in-person interpreters for new patients, paid video for follow-ups; a clinic closed on a holiday; medium: referral expiry, pre-visit blood test and lab capacity; hard: no-show rates, overbooking limits | Follow-ups with the same doctor |
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
