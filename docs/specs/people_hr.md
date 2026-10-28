# People & HR — case specs

Most HR AI deployed today sits on top of rules engines and HR systems instead of replacing them. Payroll vendors
(ADP, Deel, Papaya) sell anomaly detection that compares each payslip with the employee's own history and with
peers. Scheduling tools (GoodTime, Ashby, Guide) automate panel coordination, which recruiters report takes about
a third of their week. Attrition models (IBM's widely cited "95%" flight-risk program) score risk and suggest
manager actions. Compensation suites now run pay-equity checks inside the merit cycle. Research keeps finding the
same failure point: the hard part is not the model but the unwritten local rule. Examples are which allowances
count toward the overtime base in Japan, how Korea's December 2024 ruling on ordinary wage changed it, US daylight
saving ending a week after Europe's, a label that leaks a resignation, or a pay-gap threshold a works council
agreed to. Regulation is also tightening on exactly these systems. The EU AI Act lists employment AI as high-risk
(Annex III, point 4). The EU Pay Transparency Directive had to be in national law by 7 June 2026, Japan extended
gender pay-gap disclosure to employers with 101+ staff from April 2026, and health data is a special category in
the GDPR, Korea's PIPA, Japan's APPI and China's PIPL. That makes the field a good fit for a clarify-then-build
benchmark with real legal hard limits.

| Role | Task type | Deliverable | Hook |
|---|---|---|---|
| Resume Screening Specialist ✅ | Ranking + rules | Batch `shortlist.csv` | (built) |
| Payroll Specialist | Rules | Program `run_payroll(input_dir, period)` | Three countries, three different overtime bases, and an August raise approved in October |
| Workforce Attrition Analyst | ML + optimization | Batch `interventions.csv` + `risk_scores.csv` | A leaking column, censored snapshots, banned health data and a non-randomized pilot |
| Interview Scheduler | Optimization | Batch `schedule.csv` | US clocks change a week after Europe's, and Tokyo is closed on Tuesday |
| Compensation Planner | Optimization | Batch `raises.csv` | Merit budget vs bands vs a 5% equal-pay line vs people on parental leave |

No catalog roles are replaced: each of the four unbuilt roles covers a different skill (rule application,
leakage-aware ML with uplift, time-zone constraint scheduling, budget allocation under equity constraints).

---

### Payroll Specialist — `people_hr/payroll_specialist`
- **Why it matters** — Payroll errors are common. Deel's 2025 Singapore survey found that a third of employees had
  at least one payroll error in two years, and vendors build their AI around catching anomalies before a run is
  final. Overtime law is where most money goes wrong, and it differs sharply by country. Korea pays a 50% premium on
  "ordinary wage" (LSA Art. 56). Japan pays 25%, rising to 50% above 60 overtime hours a month, plus 25% for
  late-night work (LSA Art. 37). Spain caps overtime at 80 hours a year and lets it be paid or compensated with
  rest (ET Art. 35).
- **Client & request** — HR operations manager of a 110-person software company with entities in Seoul, Tokyo and
  Madrid: "Can you build something that runs our monthly payroll from the timesheet export? October is attached,
  and we want to reuse it every month."
- **Deliverable** — Program `payroll.py` exposing `run_payroll(input_dir: str, period: str) -> list[dict]`. It
  returns one dict per employee paid in `period` ("2026-10"), with the keys `employee_id, period, currency,
  base_pay, overtime_pay, allowances, retro_pay, leave_deduction, gross_pay, social_insurance, income_tax,
  net_pay`. Amounts are numbers in the entity's currency.
- **World & data** — There are 3 entities: KR 48 employees (KRW), JP 35 (JPY) and ES 27 (EUR). The files are
  `employees.csv` (id, entity, contract type, monthly base or hourly rate, FTE, hire/termination date,
  dependents, `paga_extra_prorated` for ES), `allowances.csv` (employee, type, monthly amount),
  `timesheets.csv` (one row per employee per day, with clock-in/out in local time, `day_type`
  workday/rest/statutory_holiday and `comp_rest` y/n; about 3,300 rows), `adjustments.csv` (raises with
  effective dates, unpaid leave days), `statutory_parameters.csv` (minimum wages, divisors, rates, caps),
  `withholding_tables.csv` (synthetic per country: taxable band × dependents → tax) and
  `payslips_2026-09.csv` (the prior run). The hidden inputs are November and December 2026 (December includes
  ES pagas extra and year-end hires/leavers) plus one synthetic edge-case month. The true payslips are computed
  in the world.
- **Hidden requirements**
  - `kr_ordinary_wage` (ambiguous; calculation) — KR hourly ordinary wage = (base + fixed monthly allowances +
    the regular quarterly bonus / 3) / 209 h. The bonus counts even though it requires being employed on the
    payment date. This follows the Supreme Court en banc ruling of 19 Dec 2024, which dropped the "fixedness"
    test. Performance bonuses stay out.
  - `kr_premiums` (missing; calculation) — Overtime (beyond 8 h/day or 40 h/week) +50% and night work
    (22:00-06:00) +50%, and the two add up. Holiday work is +50% for the first 8 h and +100% beyond, and within
    those 8 h it does not also earn the overtime premium (Art. 56(2)-(3)).
  - `jp_premium_base` (ambiguous; calculation) — The JP base excludes family, commuting and housing allowances
    (Art. 37(5), Enforcement Rule 21) but includes the regional allowance. Divisor = average scheduled hours per
    month from the company calendar (160.0 h in 2026).
  - `jp_60h_tier` (missing; calculation) — Overtime hours beyond 60 in the month earn +50%. Late-night work
    (22:00-05:00) adds +25% on top. Statutory-holiday work earns +35% and does not count toward the 60 h.
  - `es_overtime` (missing; business rule) — The collective agreement pays ES overtime at 1.25 × the hourly rate,
    where hourly rate = (12 monthly salaries + 2 pagas extra) / 1,760 agreed annual hours. Hours flagged
    `comp_rest = y` are compensated with rest and are not paid. Pagas extra are paid in June and December unless
    `paga_extra_prorated = y`.
  - `retro_raise` (missing; business rule) — A 4% KR/JP raise approved on 15 Oct is effective 1 Aug. Back pay for
    August and September goes in `retro_pay`, and it includes the overtime premiums recomputed at the new rate
    (from those months' timesheets, provided in the archive). It is taxed in the month it is paid.
  - `leave_deduction` (ambiguous; calculation) — Unpaid leave deducts monthly base / that month's scheduled
    working days per day, not / 30. Mid-month joiners and leavers are prorated the same way.
  - `si_caps` (missing; data semantics) — Social-insurance contributions apply the rate to the contribution base,
    clamped to the minimum and maximum in `statutory_parameters.csv`. The JP base is the employee's standard
    monthly remuneration grade, not this month's gross.
  - `rounding` (ambiguous; calculation) — Each line is rounded before it is summed: KRW tax rounded down to 10 won,
    JPY employee contributions rounded half-down (50 sen goes down), EUR to cents.
- **Rules**

| id | class | evaluator checks | why this class |
|---|---|---|---|
| `minimum_wage` | physical | effective hourly pay for scheduled hours ≥ the entity's statutory minimum; two planted part-timers need a top-up | statutory floor, no contract can waive it |
| `statutory_premiums` | physical | each employee's `overtime_pay` ≥ the legal minimum premium recomputed from the world's timesheets | LSA Art. 56 / Art. 37 are mandatory minimums |
| `payslip_integrity` | contractual | every active or terminated-in-period employee appears exactly once; `gross − social_insurance − income_tax = net` | the payroll service contract defines a complete, reconciled run |
| `round_net_to_10` | business_policy | `net_pay` of KRW/JPY rounded to the nearest 10 units, EUR to the nearest 0.10 (Japan's practice of rounding wages under 100 yen is permitted by notice) | the company's habit; truth is exact, so keeping it costs accuracy on every payslip |

- **Objective** — Maximize the share of (employee, month, line) values that match the world's truth within 1
  currency unit (EUR 0.01), over the three hidden months. The reference implements every requirement but
  recomputes the retro overtime at a flat 25% for JP, ignoring the 60 h tier in August. That gives about 0.88
  accuracy, so there is 5-12% headroom.
- **Hard tier** — Duplicate timesheet rows for one day after a re-export. A stale `statutory_parameters_2025.csv`
  with the old Korean minimum wage (10,030 won instead of 10,320). Timesheets in CP949/Shift_JIS. A data
  correction mid-task (one termination date moves). A late requirement: "Oh, Madrid's agreement changed, overtime
  is 1.30 from November." Twist: one Tokyo employee crosses 60 h exactly on a late-night shift, so the clock-out
  minute decides the tier split.
- **Policy & language angles** — `regulated_strict`: no bending of rounding, and an audit trail in NOTES.md for
  every formula. `startup_velocity`: rounding may be justified away. `enterprise_balanced`: escalate the rounding.
  Localize allowance labels (家族手当, 식대, plus convenio), day types and month names. Number formats (EUR comma
  decimals) are a pitfall when parsing the localized CSV.
- **Authoring risks** — Real tax law is too large: keep the withholding tables synthetic and in-world, and state
  that they are authoritative. Fix every rate in `statutory_parameters.csv` so nothing depends on outside
  knowledge. Make the hidden months exercise every rule so a hard-coded October cannot pass.
- **Sources**
  - https://ombudsman.kotra.or.kr/ik-en/cntnts/i-410/web.do
  - https://www.crowe.com/kr/en-us/news/news20230727_en
  - https://iuslaboris.com/insights/south-korean-supreme-court-redefines-ordinary-wages/
  - https://www.crowe.com/kr/en-us/news/news20250102_en
  - https://wageindicator.org/work/minimum-wage/updates/2026/minimum-wage-updated-in-south-korea-from-01-january-2026-january-01-2026/
  - https://monolith.law/en/general-corporate/wage-overtime-annual-leave-japan
  - https://www.tokyodev.com/articles/overtime-in-japan-laws-pay-rates-and-fixed-overtime
  - https://jsite.mhlw.go.jp/niigata-roudoukyoku/content/contents/syoguukaizen.pdf
  - https://www.cuestioneslaborales.es/estatuto-trabajadores/articulo-35/
  - https://www.dol.gov/whd/opinion/FLSA/2019/2019_07_01_07_FLSA.pdf
  - https://www.deel.com/blog/ai-payroll-error-detection/
  - https://workforcesoftware.com/?p=15771

---

### Workforce Attrition Analyst — `people_hr/workforce_attrition_analyst`
- **Why it matters** — Flight-risk scoring is one of the oldest HR AI products. IBM claimed 95% accuracy and $300M
  saved, but did not show how. The published literature keeps naming the same failures: treating current
  employees as true "stayers" (censoring), and features that only exist once someone has quit (leakage). Turnover
  costs about 20% of salary at the case-study median and up to 0.5-2× on Gallup's broader count. The legal stakes
  are high. Attrition scoring is profiling for employment decisions (EU AI Act Annex III(4)), and sickness data is
  special-category data (GDPR Art. 9, PIPA Art. 23, APPI "special care" data, PIPL Art. 28).
- **Client & request** — Head of People, 2,400-person logistics-tech company: "Find who's likely to leave and tell
  us who to spend the retention budget on."
- **Deliverable** — Batch: `risk_scores.csv` (`employee_id,p_leave_6m`, one row per active employee) and
  `interventions.csv` (`employee_id,intervention` with `stay_interview | retention_bonus | internal_move`,
  targeted employees only).
- **World & data** — 2,400 active employees on 2026-09-30. Each has a latent voluntary-exit hazard and a true
  uplift per intervention, which depends on the cause: pay gap, a stalled promotion, a new manager, or causes
  nothing can fix such as relocation or retirement. The files are `employees.csv`, `snapshots.csv` (quarterly
  2023Q1-2026Q2, about 30k rows, with `left_voluntary_6m`), `exits.csv` (with exit type), `absence.csv` (days by
  `reason_code`: annual/sick/medical/parental), `engagement.csv`, `comp.csv` (compa-ratio), `pilot_2025.csv`
  (who received what and the outcome), `critical_roles.csv` and `costs.csv`. The hidden truth is each employee's
  6-month exit probability with and without each intervention.
- **Hidden requirements**
  - `label_definition` (ambiguous; data semantics) — "Leave" means voluntary exit within 6 months of 2026-10-01.
    Dismissals, retirements and fixed-term contract ends are not events.
  - `leaky_column` (missing; data semantics) — `rehire_eligible` is filled in only during offboarding, and
    `tenure_months` in snapshots was computed at extraction time, so recompute it from the snapshot date. This is
    the point-in-time discipline from churn practice.
  - `censoring` (missing; calculation) — Snapshots after 2026-Q1 have incomplete 6-month windows. Drop them, or
    model them as censored; never label them "stayed".
  - `no_health_data` (missing; business rule) — Sick/medical absence, `disability_flag`, EAP usage and parental
    leave may not be features or targeting criteria. Only `annual` leave days may be used. Basis: GDPR Art. 9 and
    its national equivalents.
  - `budget` (missing; business rule) — The total budget is EUR 180,000. A bonus costs 10% of annual base, a stay
    interview EUR 300, an internal move EUR 2,000. There are 30 internal-move slots, and a move needs a matching
    job family.
  - `value_of_retention` (ambiguous; scoring) — Replacement cost is 0.5 × salary, or 1.0 × for roles in
    `critical_roles.csv`.
  - `pilot_bias` (ambiguous; data semantics) — In the 2025 pilot, managers chose who got a bonus. Only the
    `pilot_group = random` rows (the Busan site) give a valid uplift estimate. Naive comparisons overstate the
    bonus effect about 3×.
  - `already_resigned` (missing; business rule) — Employees with `resignation_submitted = yes` are lost: give them
    no intervention and exclude them from value.
  - `one_intervention` (missing; business rule) — At most one intervention per employee.
- **Rules**

| id | class | evaluator checks | why this class |
|---|---|---|---|
| `health_data` | physical | among 40 planted employees whose only risk signal is long medical absence, ≤ 3 are targeted and ≤ 6 rank in the top risk decile | special-category data law; a verifiable proxy since features cannot be observed |
| `budget_and_slots` | contractual | total cost ≤ EUR 180,000; internal moves ≤ 30 and job family matches | budget approved by the CFO |
| `eligibility` | contractual | no resigned employees targeted, one intervention each, ids valid | scope agreed with the client |
| `no_probation_targeting` | business_policy | nobody hired after 2026-04-01 is targeted | habit; new hires have the highest hazard and cheap stay-interview uplift, so keeping it forgoes value |

- **Objective** — Maximize expected retained value = Σ over targeted employees of (p0 − p_a) × replacement value,
  using the world's true probabilities. The reference trains logistic regression on clean, uncensored features,
  ranks by risk × value / cost, assigns a bonus when compa-ratio < 0.9 and a stay interview otherwise, and fills
  the budget greedily. Headroom of about 10-15% comes from cause-specific uplift (new manager → stay interview;
  stalled promotion → internal move).
- **Hard tier** — Duplicate snapshot rows after an HRIS migration. A stale `employees_backup.csv` missing 60 recent
  hires. Legacy encoding. Stakeholder conflict: a finance VP says "just give bonuses to the top 100 risks". Data
  correction: 12 exits reclassified from voluntary to dismissal. Twist: a site reorganization in 2025-Q3 caused a
  burst of exits that is not predictive. The client knows it, and it should be down-weighted or excluded.
- **Policy & language angles** — `regulated_strict` treats the scoring as high-risk AI: NOTES.md must list the
  features used and confirm that no special-category data was used, and no bending. `startup_velocity` may justify
  dropping the probation rule. Localize reason codes (병가, 傷病休暇, baja médica), job families and site names, and
  watch for fiscal-quarter labels (Japanese FY starts in April).
- **Authoring risks** — Absence totals that mix sick and annual days must not be the only good signal, or the
  health rule becomes impossible. Keep uplift learnable from the random pilot (about 600 rows). Expected-value
  scoring avoids noise from sampled outcomes.
- **Sources**
  - https://www.cnbc.com/2019/04/03/ibm-ai-can-predict-with-95-percent-accuracy-which-employees-will-quit.html
  - https://towardsdatascience.com/cracking-the-employee-attrition-problem-with-machine-learning-6ee751ec4aae/
  - https://humanforce.com/blog/how-to-use-survival-analysis-to-predict-when-employees-will-leave
  - https://pub.towardsai.net/what-healthcare-taught-me-about-churn-hint-classification-is-the-wrong-tool-ea188a2a2883
  - https://reliamag.com/topics/guides/manufacturing-employee-turnover-costs
  - https://larridin.com/blog/eu-ai-act-high-risk-employment-performance-promotion
  - https://secureprivacy.ai/blog/gdpr-article-9-special-categories-lawful-processing-and-compliance-guide-2026
  - https://www.simmons-simmons.com/en/publications/cku2ir2sx1gla0a019ycaji33/impact-of-the-new-personal-information-protection-law-in-the-workplace
  - https://www.linklaters.com/en/insights/data-protected/data-protected---japan

---

### Interview Scheduler — `people_hr/interview_scheduler`
- **Why it matters** — Recruiters report spending about 35% of their time on scheduling. Ashby's data on 5M+ events
  shows panels are much slower to book than single interviews (34% vs 54% booked within a day). Coordination is
  the main thing vendors automate. Cross-border panels break on time zones. Europe leaves daylight saving on the
  last Sunday of October (25 Oct 2026) and the US on the first Sunday of November (1 Nov 2026), while Korea, Japan
  and China have no DST, so offsets change from one week to the next. Research on slates also motivates
  diverse-panel policies.
- **Client & request** — Recruiting coordination lead, a company with offices in Seoul, Tokyo, Madrid and New York:
  "Please schedule next week's final-round panels for these candidates."
- **Deliverable** — Batch `schedule.csv`:
  `candidate_id,start_utc,duration_min,interviewer_ids,mode`. `start_utc` is ISO-8601 with Z, `interviewer_ids`
  are separated by `;`, and `mode` is `onsite:<office>` or `video`.
- **World & data** — The week is Mon 2 Nov - Fri 6 Nov 2026. There are 42 candidates across 6 roles and 55
  interviewers. The files are `candidates.csv` (role, city, `tz_name`, `utc_offset`, `offer_deadline`,
  `referred_by`, availability windows in local time), `interviewers.csv` (office, competencies, `trained` y/n,
  gender, `weekly_cap`), `calendars.csv` (busy blocks in local time, about 1,400 rows), `roles.csv` (panel
  recipe, onsite or video) and `rooms.csv`. Interviewer and candidate availability is fully known in the world.
- **Hidden requirements**
  - `stale_offset` (missing; data semantics) — `utc_offset` was exported on 20 Oct, so the US rows are still on
    EDT (−4). Use `tz_name`: New York is −5 during the target week.
  - `culture_day` (missing; business rule) — 3 Nov is Culture Day, a national holiday in Japan. The Tokyo office
    is closed, and that is not in the calendars.
  - `working_hours` (ambiguous; business rule) — Interviewers 09:00-18:00 local time, excluding lunch (12:00-13:00
    in Seoul and Tokyo, 14:00-15:00 in Madrid). Candidates only inside their windows.
  - `panel_recipe` (ambiguous; business rule) — 3 interviewers: one with the role's competency and `trained = y`
    (untrained interviewers cannot score), and one from a different team.
  - `load_caps` (missing; business rule) — An interviewer does at most 2 panels a day and at most `weekly_cap`
    (default 5) a week, with a 15-minute buffer between panels.
  - `diverse_panel` (missing; business rule) — Every panel includes at least one woman and at least two offices.
  - `conflict` (missing; business rule) — An interviewer never sits on the panel of a candidate they referred.
  - `durations` (ambiguous; data semantics) — Engineering panels last 90 min and the others 60. Onsite roles need a
    room with capacity ≥ 4 in that office.
  - `priority` (ambiguous; scoring) — Candidates whose offer deadline falls before 9 Nov count 3×, and earlier
    days score higher.
- **Rules**

| id | class | evaluator checks | why this class |
|---|---|---|---|
| `no_double_booking` | physical | no person or room in two places at once; every slot inside true availability and outside the holiday | people cannot be in two meetings |
| `panel_validity` | contractual | panel recipe, trained interviewer, durations, conflict of interest | the hiring process agreed with the client |
| `load_and_hours` | contractual | daily/weekly caps, buffers, local working hours | interviewer agreements and working-time rules (Korea LSA 52-hour week) |
| `diverse_panel` | contractual | at least one woman and at least two offices per panel | company hiring standard |
| `hiring_manager_on_panel` | business_policy | the role's hiring manager is on every panel | habit; managers are the bottleneck (5 of them for 42 candidates), so keeping it pushes candidates out of the week |

- **Objective** — Maximize Σ over scheduled candidates of weight × (1 − 0.1 × weekday index), with weight 3 for a
  deadline before 9 Nov and 1 otherwise. The reference assigns greedily: candidates by priority, then the earliest
  feasible slot with the least-loaded qualified interviewers. Local search should improve it by 6-12%.
- **Hard tier** — Duplicate calendar rows. A stale `calendars_last_week.csv`. Legacy encoding. Client unavailable
  mid-task. A late requirement: "the Madrid office closes at 15:00 on Friday". Twist: one candidate in Mexico City
  is listed with a US-style DST offset, but Mexico dropped DST after 2022.
- **Policy & language angles** — `regulated_strict`: candidate data minimization, so NOTES.md must not repeat
  gender and the hiring-manager rule may not bend. `startup_velocity` may justify allowing video panels without the
  hiring manager. Localize city names, weekday names and date formats (2026年11月2日, 2/11/2026 in Spanish), and
  name order (family name first in ko/ja/zh).
- **Authoring risks** — Make sure the instance stays feasible when every rule is kept. Use deterministic tie-breaks
  in the reference. Don't let a 24-hour-clock vs AM/PM confusion be the only signal.
- **Sources**
  - https://www.guide.co/blog/interview-coordination-benchmarks
  - https://stealthagents.com/research/recruiting-interview-scheduling-workload-statistics-2026
  - https://yello.co/blog/interview-scheduling-statistics/
  - https://www.cloudapper.ai/?p=162218
  - https://en.wikipedia.org/wiki/Daylight_saving_time_by_country
  - https://onlabor.org/the-rooney-and-mansfield-rules-diversity-programs-in-structurally-different-industries
  - https://www.visier.com/blog/how-hr-can-tackle-diversity-using-the-rooney-rule
  - https://natlawreview.com/article/new-nyc-law-restricting-artificial-intelligence-driven-employment-tools-reveals-what
  - https://globallawexperts.com/52-hour-rule-korea/

---

### Compensation Planner — `people_hr/compensation_planner`
- **Why it matters** — Merit cycles are moving under pay-transparency law. The EU directive (transposition deadline
  7 June 2026) brings gap reporting for employers with 100+ staff, joint pay assessments when there are signs of
  discrimination, and a ban on asking about salary history. Spain's RD 902/2020 already requires a pay register by
  sex, and a written justification when one sex's average or median pay is ≥ 25% higher. Japan made gender
  pay-gap disclosure mandatory for employers with 101-300 staff from 1 Apr 2026, on top of the existing 301+ rule.
  Compa-ratio against band midpoints is the standard positioning measure.
- **Client & request** — Total Rewards lead, a 1,200-employee company in KR/JP/ES/US: "Allocate this year's merit
  budget. Ratings and the salary export are attached."
- **Deliverable** — Batch `raises.csv`: `employee_id,merit_pct,equity_adj,new_base_salary`.
  `new_base_salary` is the annual FTE-adjusted base in local currency.
- **World & data** — 1,200 employees in 4 departments × 4 countries. The files are `employees.csv` (level, family,
  country, base, currency, FTE, rating 1-5 or blank, hire date, `leave_status`, gender), `pay_bands.csv`
  (country × level min/mid/max), `merit_matrix.csv` (rating × compa-ratio quartile → guideline %),
  `budgets.csv` and `fx_rates.csv` (as of 2026-09-30). The hidden truth is each person's market target compa-ratio
  by rating.
- **Hidden requirements**
  - `budget_scope` (ambiguous; calculation) — Merit = 3.5% of eligible base payroll, per department, converted at
    the given FX. There is a separate company-wide equity pool of 0.5%. Pools may not be mixed.
  - `eligibility` (missing; business rule) — Hired after 2026-10-01: no merit. Hired Jul-Sep: merit prorated by
    months. Rating 1: 0%. Employees who have given notice are excluded.
  - `fte_annualize` (missing; data semantics) — Compute compa-ratio on the FTE-annualized base against the band of
    the employee's own country and level.
  - `band_rules` (missing; business rule) — Anyone below band minimum is raised to the minimum from the equity
    pool. Nobody ends above the maximum.
  - `protected_leave` (missing; business rule) — Employees on maternity or parental leave have a blank rating.
    They receive at least the department's average merit for their last rating. Basis: Korea EEOA Art. 19,
    Japan's Childcare Leave Act Art. 10, and EU law.
  - `equal_pay_line` (missing; scoring) — In every country × level × family group with ≥ 5 of each gender, women's
    mean compa-ratio after raises must be ≥ 0.95 × men's. This mirrors the directive's 5% trigger.
  - `rounding` (ambiguous; calculation) — Round to KRW 10,000, JPY 1,000, EUR/USD 10, rounding up.
  - `effective_date` (missing; data semantics) — Raises take effect 2027-01-01 and apply to the current annual
    base, not to year-to-date pay.
- **Rules**

| id | class | evaluator checks | why this class |
|---|---|---|---|
| `protected_leave` | physical | merit for people on leave ≥ the department average for their last rating | statutory ban on disadvantage for taking leave |
| `budgets` | contractual | per-department merit spend ≤ budget; equity spend ≤ pool | board-approved budget |
| `bands_and_eligibility` | contractual | band min/max respected, eligibility rules followed | compensation policy |
| `equal_pay_line` | contractual | 0.95 gap line in every testable group | works-council agreement; the law requires an assessment, not a fixed number |
| `merit_cap_10` | business_policy | merit_pct ≤ 10 | habit; underpaid top performers need 12-15% to reach target, so the cap leaves shortfall |

- **Objective** — Minimize Σ weight(rating) × max(0, target compa-ratio − new compa-ratio), with weights 5:4:3:1:0
  for ratings 5..1. The reference applies matrix midpoints, scales to each budget, then fixes floors and equity
  gaps greedily. A small LP or knapsack approach should gain 8-15%.
- **Hard tier** — Duplicate employee rows from a merged subsidiary. A stale FX file. Legacy encoding. A data
  correction (12 ratings changed after calibration). Stakeholder conflict: one department head wants to pool
  budgets. Twist: one band table is in monthly KRW while the others are annual.
- **Policy & language angles** — `regulated_strict`: NOTES.md must document the equity check, and the cap may not
  bend. `startup_velocity` may justify exceptions above 10%. Localize rating labels (S/A/B/C/D in Korea and Japan,
  1-5 elsewhere), currency formats and grade names.
- **Authoring risks** — Keep the equity line achievable within the pool. Gender is used only for the check, never
  as an input. Without the hidden ratings for people on leave there must be a single correct value.
- **Sources**
  - https://commission.europa.eu/strategy-and-policy/policies/justice-and-fundamental-rights/gender-equality/equal-pay/eu-action-equal-pay_en
  - https://www.boe.es/buscar/act.php?id=BOE-A-2020-12215
  - https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000091025.html
  - https://en.wikipedia.org/wiki/Compa-ratio
  - https://en.wikipedia.org/wiki/Pay_transparency
