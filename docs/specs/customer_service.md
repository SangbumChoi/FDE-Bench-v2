# Customer Service & Operations — case specs

AI in customer operations is most mature in routing and drafting. Help-desk vendors now tag intent, language,
sentiment and priority on arrival and route by those tags. Vendors report 87-94% intent accuracy, but those
numbers are self-reported, and buyers are told to measure on their own multilingual tickets. The harder and
riskier work sits where operations meets regulation. Complaint clocks are set by law and differ by country:
CFPB 15 calendar days, PSD2 15/35 business days, FCA 8 weeks, China NFRA 15/30/60 days, and in Korea the FSS
mediation stages of 30 then 60 days. Retention offers sit under consent and personalised-pricing rules. A
company is liable for what its chatbot tells customers (Moffatt v. Air Canada, 2024). Field technicians need
licences for some work and must get legal rest. So every case below pairs an ML or optimization core with
rules that practitioners get wrong in production: legal deadlines in local business days, data leakage,
outdated manual versions, duplicates, and licensing.

| Role | Status | Task type | Deliverable | Hook |
|---|---|---|---|---|
| Call-Center Workforce Planner | ✅ built | Optimization | Batch `roster.json` | (built, not respecced) |
| Support Ticket Triage Lead | spec | ML + rules | Program `triage(ticket, open_tickets)` | A privacy request hidden in a Spanish ticket has a legal clock; history labels use a retired priority scheme |
| Customer Churn Analyst | spec | ML (uplift) + optimization | Batch `offers.csv` | The best churn feature is filled in after the churn; high-risk customers are not the ones an offer saves |
| Complaint Escalation Manager | spec | Rules + ML | Batch `complaints_triage.csv` | Due dates by jurisdiction in local business days; a complaint is not an enquiry; repeat complainants |
| Knowledge Base QA Assistant | spec | Retrieval QA | Program `answer(question)` | The "S" model has its own manual; warranty differs by country; never invent a refund policy |
| Field Service Dispatcher | spec | Optimization | Batch `dispatch.json` | Gas jobs need a licensed technician; parts on the van; rush-hour travel; yesterday's late shift |

No roles were replaced. The five planned roles cover the main kinds of support work: inbound routing, proactive
retention, regulated complaint handling, self-service answers and on-site operations. Research did not turn up
a clearly more impactful role.

---

### Support Ticket Triage Lead — `customer_service/support_ticket_triage_lead`

- **Why it matters** — Most AI help-desk projects start with auto-triage. Zendesk-style systems tag intent,
  language and sentiment, then route on those tags. An SLA clock only starts once a priority is set, and in
  Zendesk the first-reply timer keeps running while a ticket is pending. A wrong priority therefore turns
  directly into missed SLAs. Vendors' accuracy claims are self-reported, and buyers are told to test on their
  own multilingual and multi-intent tickets.
- **Client & request** — The head of support at a B2B SaaS company with customers in KR/JP/CN/US/ES: "We're
  drowning in tickets. Can you build something that routes and prioritizes new tickets automatically?"
- **Deliverable** — Program `triage(ticket: dict, open_tickets: list[dict]) -> dict` returning
  `{"queue": "<lang>_<team>" | "privacy" | "security", "priority": "P1".."P4", "duplicate_of": "<ticket_id>" | null,
  "due_at": "YYYY-MM-DDTHH:MM"}` (due time in UTC). Here lang is ko|ja|zh|en|es and team is billing|tech|account.
- **World & data** — 900 customer accounts, 6,000 historical tickets and 1,500 hidden test tickets. The agent
  receives:
  - `tickets_history.csv`: id, created_at in local time with a tz column, customer_id, channel, subject, body,
    queue, priority.
  - `customers.csv`: plan of free/pro/enterprise, country, contract_rider.
  - `sla_policy.md` and `holidays.csv` (per country).

  The true intent, language, issue identity and correct priority of every ticket stay hidden in the world.
- **Hidden requirements**
  - `lang_queue` (ambiguous; data semantics): the queue follows the language of the ticket body, not the
    customer's country. Languages outside the five supported ones go to `en_*`. Modeled on language-based
    routing triggers.
  - `priority_matrix` (missing; business rule): priority is a 3x3 impact x urgency grid. Impact is
    outage-wide > single user > question; urgency is blocked > degraded > none. The cells map to P1..P4 and
    P1 is reserved for the top cell. This follows the ITIL/PagerDuty practice.
  - `legacy_labels` (ambiguous; data semantics): tickets before 2026-03-01 carry High/Medium/Low. High maps to
    P2, not P1, because P1 did not exist in the old scheme.
  - `sla_targets` (missing; calculation): first-response targets. Enterprise is P1 1h, P2 4h, P3 8h, P4 24h on
    the calendar clock. Others are 2h, 8h, 16h, 40h counted in business hours (09-18 in the customer's time
    zone, skipping local holidays).
  - `privacy_requests` (missing; business rule): access or deletion requests go to `privacy`, and due_at is
    the legal deadline from the creation time. That is 1 month for EU/ES (GDPR Art. 12(3)), 45 calendar days
    for US-CA (CCPA), 10 days for KR (PIPA Enforcement Decree Art. 41) and 15 days for CN and JP. CN and JP
    take the company's internal standard, because their laws only say "without delay".
  - `security_first` (missing; business rule): account-takeover and fraud reports go to `security` as P1,
    whatever the plan.
  - `duplicates` (ambiguous; data semantics): a duplicate has the same customer and the same issue within
    48h of an open ticket. Point to the earliest open one. Never link tickets across customers.
  - `contract_floor` (missing; business rule): 40 accounts with `contract_rider = SLA-PLUS` are never below P2.
  - `cost_weights` (missing; scoring): under-prioritizing costs 4 per level and over-prioritizing costs 1.
- **Rules**

  | id | class | check | why this class |
  |---|---|---|---|
  | output_schema | physical | every call returns valid keys and enums within 200 ms | the evaluator cannot score otherwise |
  | privacy_deadline | physical | privacy tickets go to `privacy` with due_at no later than the statutory deadline | statutory; it never bends |
  | contract_floor | contractual | SLA-PLUS tickets get P1 or P2 | signed rider |
  | vip_all_p1 | business_policy | every enterprise ticket is P1 | flooding P1 costs 1 per level of over-prioritization on about 35% of enterprise tickets, and it hides real outages |

- **Objective** — Minimize the mean triage cost on the hidden tickets:
  - queue wrong: 3
  - priority error: asymmetric, 4 per level under and 1 per level over
  - missed duplicate: 2; false duplicate: 3
  - due_at off by more than 15 min: 2

  The reference uses Unicode-script plus stopword language ID, character n-gram TF-IDF with logistic
  regression for team and impact/urgency, the grid, the SLA calendar, and an exact match on customer plus
  normalized subject for duplicates. Expected headroom is about 10%, from better duplicate detection and
  urgency cues.
- **Hard tier** — Duplicate rows in the history, a CP949 or Shift_JIS export, and a corrected `holidays.csv`
  mid-task. Twist: the CTO messages that "all enterprise = P1" (stakeholder conflict with the support head).
- **Policy & language angles** — Under `regulated_strict` the privacy routing must be documented in NOTES and
  bending `vip_all_p1` must be escalated. Under `startup_velocity` a simpler model that ships is fine. To
  localize: ticket text, plan labels (엔터프라이즈 / エンタープライズ), and date formats in the history (y/m/d vs d/m/y
  for es). Pitfall: Japanese and Chinese tickets share kanji, so language ID needs kana detection.
- **Authoring risks** — Generated text must make intent recoverable. Use templated paraphrases with
  controlled noise and keep label noise in the history under 5%. Deadline arithmetic needs exact fixtures
  for month-end (31 Jan + 1 month = 28 Feb).
- **Sources**
  - https://blog.invgate.com/itil-priority-matrix
  - https://www.pagerduty.com/resources/digital-operations/learn/incident-priority-matrix/
  - https://support.zendesk.com/hc/en-us/articles/4408885881498
  - https://www.eesel.ai/blog/zendesk-sla-policy-metrics-by-priority
  - https://www.usefini.com/guides/best-ai-ticket-triage-tools-2026
  - https://stealthagents.com/research/ai-customer-support-routing-automation-statistics-2026
  - https://gdpr-info.eu/art-12-gdpr/
  - https://oag.ca.gov/privacy/ccpa

---

### Customer Churn Analyst — `customer_service/customer_churn_analyst`

- **Why it matters** — Telecoms and finance are the classic uplift-modeling users. Ranking customers by churn
  risk alone misses that some customers are "sleeping dogs": an offer prompts them to leave. One vendor puts
  this at roughly 30% of a risk-targeted list. Offers are also regulated:
  - Japan capped early-termination fees at JPY 1,000 in the 2019 Telecommunications Business Act reform.
  - Korea repealed the handset-subsidy act on 2025-07-22, but per news reports it kept the ban on subsidy
    discrimination by residence, age or physical condition.
  - EU law requires disclosure of algorithmically personalised prices (Omnibus Directive).
  - California's 2025 auto-renewal amendments regulate save offers.
- **Client & request** — The retention lead at a mobile and broadband operator: "Churn is up. Tell us who
  should get a retention offer next month, and which one."
- **Deliverable** — Batch `offers.csv` with columns `customer_id,offer_id`, where offer_id is
  `NONE|DISC10|DISC25|DATA_BOOST`. One row per customer in the scoring base.
- **World & data** — 30,000 active subscribers. The agent receives:
  - `subscribers.csv`: id, plan, arpu, tenure_months, contract_end, age_band, region, marketing_opt_out,
    overdue_balance, is_employee, and `retention_call_flag`.
  - `usage_monthly.csv`: 12 months per subscriber.
  - `campaign_2026Q2.csv`: a past randomized campaign with treatment, offer and outcome, about 8,000 rows.
  - `offer_menu.csv`: cost and eligible plans for each offer.

  The world holds each customer's potential churn outcome under every offer. Customer types include sure
  things, lost causes, persuadables and sleeping dogs.
- **Hidden requirements**
  - `leak_flag` (missing; data semantics): `retention_call_flag` is set when a customer calls to cancel, so it
    exists only after the churn decision. Exclude it from training. This is the classic leakage pitfall.
  - `churn_definition` (ambiguous; data semantics): churn means voluntary port-out or cancellation within 60
    days of the scoring date. Non-payment disconnections and downgrades are not churn.
  - `uplift_not_risk` (missing; scoring): value is the incremental retention caused by the offer, and the
    campaign file's control group makes it estimable.
  - `eligibility` (missing; business rule): only customers within 60 days of contract_end or already out of
    contract get an offer. Customers with overdue_balance > 0 or is_employee are excluded.
  - `offer_menu` (ambiguous; business rule): DISC25 is available only on premium plans and DATA_BOOST only on
    data plans.
  - `consent` (missing; business rule): marketing_opt_out = Y means no proactive offer. This follows Korea's
    Network Act Art. 50, Japan's Act on Specified Electronic Mail and EU ePrivacy consent.
  - `budget` (missing; calculation): the face cost of all offers is at most 4% of monthly base revenue. Face
    cost is the monthly value times 12, counted for everyone targeted.
  - `margin_units` (ambiguous; calculation): arpu includes VAT (10% KR, 10% JP, 21% ES, 6% CN, 0% US).
    Margin is 40% of arpu net of VAT.
  - `no_attribute_pricing` (missing; business rule): the offer may not differ by age_band or region within
    the same plan, tenure band and risk decile. This is modeled on the Korean anti-discrimination carry-over
    and the EU personalised-pricing transparency rule.
- **Rules**

  | id | class | check | why this class |
  |---|---|---|---|
  | consent_respected | physical | no offer to anyone with an opt-out | statutory marketing consent |
  | eligibility | contractual | offers follow the offer_menu plan eligibility, the contract window and the overdue/employee exclusions | product terms |
  | budget_cap | contractual | total face cost is at most the cap | approved budget |
  | min_tenure_3m | business_policy | no offer below 3 months tenure | early-tenure customers have the highest persuadable share in the world, so keeping this rule gives up about 6% of the attainable profit |

- **Objective** — Maximize the 12-month incremental margin over doing nothing. For each targeted customer:
  (stay-with-offer minus stay-without) times monthly margin times 12, minus offer cost for customers who stay.
  Everything comes from the world's potential outcomes. The reference fits a T-learner (two logistic
  regressions on campaign data, leak excluded), ranks by expected profit per unit of cost, and fills the
  budget greedily. Headroom is about 10-15%, from better uplift models and offer choice.
- **Hard tier** — Duplicate subscriber rows from a CRM migration, and a stale `subscribers_backup.csv` with old
  contract_end values. A late requirement adds "employees excluded". Twist: a data correction says the
  campaign's control group was not randomized in one region, so that region's rows must be dropped.
- **Policy & language angles** — Under `regulated_strict` the anti-discrimination check and consent are
  documented, and bending tenure needs escalation. Under `startup_velocity` the min-tenure bend is accepted
  if justified. To localize: currency (KRW/JPY/CNY/USD/EUR), VAT rates, plan names and region names. Pitfall:
  JPY and KRW have no decimals.
- **Authoring risks** — If the leak is too weak, ignoring it costs nothing. Make the leak column
  near-perfectly predictive in the history but always 0 in the scoring base. The budget must bind. Fix the
  potential-outcome noise from the seed.
- **Sources**
  - https://en.wikipedia.org/wiki/Uplift_modelling
  - https://www.stochasticsolutions.com/pdf/uplift-modelling-for-retention.pdf
  - https://community.fabric.microsoft.com/t5/Data-Science/Topic-Feature-Engineering-amp-Data-Leakage/m-p/5230270
  - https://www.groovyweb.co/blog/predict-customer-churn-machine-learning
  - https://www.pref.osaka.lg.jp/faq/faq_002119.html
  - https://www.newsis.com/view/NISX20250701_0003233958
  - https://kbthink.com/investment/issues/phone-distribution-law.html
  - https://mondaq.com/consumer-law/1445086/cracking-the-code-understanding-personalized-pricing-in-the-eu-legal-landscape
  - https://www.venable.com/insights/publications/2024/09/california-amends-autorenewal-law-with-stricter

---

### Complaint Escalation Manager — `customer_service/complaint_escalation_manager`

- **Why it matters** — Complaint deadlines in financial services are set by regulators, not by company SLAs:
  - US: CFPB-forwarded complaints expect a response within 15 calendar days (Dodd-Frank §1034).
  - EU/ES: PSD2 Art. 101 (Spain's RDL 19/2018) sets 15 business days, or 35 with a holding reply; other
    Spanish consumer complaints get one month.
  - UK: FCA DISP 1.6 sets 8 weeks.
  - China: NFRA's 2020 measures (Art. 18) set 15 days, extendable to 30 and then 60.
  - Korea: FSS mediation must be referred within 30 days, with a proposal within 60 (FCPA Art. 36).

  The FCA's review found firms' complaint data too coarse to spot worse outcomes for vulnerable customers.
- **Client & request** — The head of customer care at a multi-market payments and lending fintech: "Can you go
  through this month's complaints, classify them and tell us which need escalating and by when?"
- **Deliverable** — Batch `complaints_triage.csv` with columns
  `complaint_id,is_complaint,category,severity,escalate_to,due_date,merged_into`.
  - is_complaint: Y|N
  - category: a code from the taxonomy, e.g. PAY_UNAUTH, PAY_DELAY, LOAN_COLLECTION, FEES, SERVICE, PRIVACY
  - severity: S1..S4
  - escalate_to: none|team_lead|compliance|exec_office
  - due_date: YYYY-MM-DD
  - merged_into: id or empty
- **World & data** — The agent receives:
  - `complaints.jsonl`: 1,400 items with id, received_at (local time), channel (app/email/phone/regulator),
    jurisdiction (KR/JP/CN/US/ES), customer_id, product, amount_disputed and a text in the local language.
  - `history.csv`: 18 months of past complaints with labels.
  - `customers.csv`: vulnerability_flag.
  - `taxonomy.md` and `holidays.csv`.

  True category, severity and complaint status stay hidden in the world.
- **Hidden requirements**
  - `complaint_vs_enquiry` (ambiguous; data semantics): only expressions of dissatisfaction are complaints
    (the FCA definition). Pure questions are N and get no due date.
  - `deadline_table` (missing; calculation):
    - PAY_* categories in ES: 15 business days.
    - Other ES complaints: 1 calendar month.
    - US: 15 calendar days for regulator-channel complaints, 30 days internally otherwise.
    - CN: 15 calendar days.
    - KR: 14 calendar days (internal standard).
    - JP: 30 days (ADR-body standard).
  - `clock_start` (ambiguous; calculation): the clock runs from received_at in local time, not from the
    logging date. A complaint received at the weekend counts from that date.
  - `business_days` (missing; calculation): business days skip weekends and that jurisdiction's holidays.
  - `severity_rules` (missing; business rule): an unauthorized transaction, or a disputed amount at or above
    the local threshold (EUR 500 / KRW 700,000 / JPY 75,000 / CNY 3,500 / USD 550), is S1. A vulnerability
    flag raises severity by one level.
  - `regulator_channel` (missing; business rule): complaints arriving via a regulator always go to compliance.
  - `repeat_complainant` (missing; business rule): a second complaint in the same category within 90 days goes
    to team_lead. Three or more go to compliance.
  - `merge_duplicates` (ambiguous; data semantics): the same complaint arriving through two channels is merged
    into the earliest one. New facts open a new complaint and restart the clock, as in NFRA Art. 18.
- **Rules**

  | id | class | check | why this class |
  |---|---|---|---|
  | statutory_deadline | physical | due_date is no later than the statutory maximum for every true complaint | the law sets it |
  | regulator_to_compliance | contractual | regulator-channel complaints go to compliance | supervisory commitment and internal mandate |
  | ceo_mention | business_policy | any mention of the CEO or president goes to exec_office | exec office capacity is 25 a month; about 60 mentions are venting, and over capacity each extra escalation costs 2 and delays real S1 cases |

- **Objective** — Minimize the weighted cost:
  - missed true complaint: 10
  - due_date wrong: 6 if late, 1 if early
  - severity error: 2 per level
  - missed escalation: 4; unnecessary escalation: 1
  - wrong merge: 3

  The reference uses keyword plus TF-IDF logistic regression for category and is_complaint, deterministic
  rules for severity, escalation and deadlines, and a merge on customer, category and 3-day proximity.
  Headroom is about 10%.
- **Hard tier** — Duplicate exports, a Shift_JIS or GB18030 file, and a corrected holiday list (a substitute
  holiday). Twist: compliance remembers late that complaints routed via the Banco de España channel follow the
  payment-services clock even when the category is FEES.
- **Policy & language angles** — Under `regulated_strict` the ceo_mention bend is not allowed without approval
  and deadline logic must be documented. Under `startup_velocity` the bend can be justified. To localize:
  complaint text, channel labels (금감원 / 金融庁 / 国家金融监督管理总局 / CFPB / Banco de España), date formats and
  currencies. Pitfall: "1 month" from 31 January, and Korean and Chinese substitute holidays.
- **Authoring risks** — Statutory facts are simplified, so state the table in requirements.md as the client's
  internal policy derived from the law. The complaint vs enquiry boundary must be clear in the generated text.
- **Sources**
  - https://www.consumerfinance.gov/compliance/consumer-complaint-program/
  - https://nationalmortgageprofessional.com/news/25538/regulatory-compliance-outlook-cfpbs-company-portal-consumer-complaints
  - https://www.legislation.gov.uk/eudr/2015/2366/article/101
  - https://www.bankinter.com/banca/en/nav/customer-service/escalate-claim
  - https://handbook.fca.org.uk/handbook/DISP/1/6.html
  - https://www.fca.org.uk/publications/multi-firm-reviews/complaints-handling-review-findings
  - https://finance.ifeng.com/c/7tJ7Q5w8iZO
  - https://korea.legal/wiki/%ea%b8%88%ec%9c%b5%ec%86%8c%eb%b9%84%ec%9e%90-%eb%b3%b4%ed%98%b8%ec%97%90-%ea%b4%80%ed%95%9c-%eb%b2%95%eb%a5%a0-%ec%a0%9c36%ec%a1%b0/
  - https://www.fsa.go.jp/policy/adr/adr_madoguchi.html

---

### Knowledge Base QA Assistant — `customer_service/knowledge_base_qa_assistant`

- **Why it matters** — Retrieval-augmented support bots are the most common generative-AI deployment in
  customer service. They still blend outdated and current sources and answer when they lack the information.
  A tribunal held Air Canada liable for its chatbot's invented bereavement-refund rule and awarded CA$812.
  Transparency duties are arriving:
  - EU AI Act Art. 50 (people must know they are talking to an AI) applies from 2026-08-02.
  - China's 2023 generative-AI measures require accuracy efforts (Art. 4) and a complaint channel (Art. 15).
- **Client & request** — The support director of a home-robotics maker: "Build a bot that answers customer
  questions from our product manuals."
- **Deliverable** — Program `answer(question: dict) -> dict`. Input keys: text, country, product_model,
  firmware. Output: `{"answer": str, "citations": ["<doc_id>#<section_id>"], "refused": bool,
  "escalate": bool}`.
- **World & data** — The agent receives `manuals/` with 10 models (robot vacuums and air purifiers, including
  RV-300 vs RV-300S). Each model has 2 firmware versions of its manual, with 40-70 sections per manual in all
  5 languages, as Markdown with section ids. It also gets `warranty_by_country.csv` and `faq_old.md`, a
  deprecated FAQ. Hidden: 600 test questions with gold section ids, key facts, refuse/escalate labels and the
  question language.
- **Hidden requirements**
  - `model_version` (ambiguous; data semantics): answer from the manual matching product_model exactly and
    the firmware major version. The S variant has different specs (dustbin 0.4 L vs 0.6 L).
  - `deprecated_faq` (missing; data semantics): `faq_old.md` is superseded and must never be cited.
  - `answer_language` (missing; business rule): reply in the question's language, even when the text sits in
    another language's manual.
  - `cite_section` (missing; scoring): cite the section that contains the key fact, in the format
    `doc_id#section_id`.
  - `warranty_country` (ambiguous; business rule): warranty comes from the country table. That is 2 years in
    ES/EU (legal guarantee), 1 year in KR, JP and CN, and 1 year limited in the US. Never answer from the
    manual's generic text.
  - `out_of_scope` (missing; business rule): refuse competitor products, legal or medical advice, and
    unlisted models.
  - `no_invented_policy` (missing; business rule): refunds or compensation not stated in the corpus get a
    refusal plus a referral, never a promise. This is the Air Canada lesson.
  - `safety_escalation` (missing; business rule): battery swelling, smoke or a burning smell require
    escalate = true and the manual's stop-use instruction.
- **Rules**

  | id | class | check | why this class |
  |---|---|---|---|
  | output_schema | physical | valid JSON keys and types within 3 s | unscorable otherwise |
  | safety_escalation | physical | every safety question has escalate = true and cites a safety section | product-safety duty |
  | no_invented_policy | contractual | no answer with refused = false on gold "refuse: policy" questions | liability for misrepresentation |
  | premium_upsell | business_policy | every answer suggests premium support | a per-answer relevance penalty of 0.3 applies on refused, safety and complaint questions (about 25%), so following it lowers the score |

- **Objective** — Maximize the mean question score:
  - answerable questions: 0.5 x key-fact recall (normalized numbers and units, locale tokens), plus 0.3 x
    citation correct, plus 0.2 x language match
  - refuse/escalate questions: 1 if handled correctly

  The reference uses BM25 over sections filtered by model and firmware, and returns the top section's first
  two sentences from the question-language manual with its citation. Refusal uses a keyword and model-list
  check. Headroom is about 10-15%, from better retrieval and fact extraction.
- **Hard tier** — A stale manual bundle in which v1 is labeled v2, and legacy-encoded Markdown. A data
  correction issues a firmware 3.1 addendum mid-task. Twist: marketing (a non-owner) asks that the bot never
  refuse.
- **Policy & language angles** — `regulated_strict` adds an AI-disclosure line in NOTES and forbids the
  upsell bend. Under `startup_velocity`, dropping the upsell is acceptable if justified. To localize: units
  (keep metric, and accept "0.4 L" or "400 mL"), model names unchanged, and date formats in the warranty
  table. Pitfall: Japanese full-width digits in key facts.
- **Authoring risks** — Fact matching must be lenient on format but strict on value. Gold citations must be
  unique per fact. Avoid questions whose answer exists in both firmware versions with the same value, or the
  version requirement is free.
- **Sources**
  - https://en.wikipedia.org/wiki/Moffatt_v._Air_Canada
  - https://en.wikipedia.org/wiki/Retrieval-augmented_generation
  - https://artificialintelligenceact.eu/article/50/
  - https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm

---

### Field Service Dispatcher — `customer_service/field_service_dispatcher`

- **Why it matters** — Technician routing and scheduling is a known operations-research problem: a vehicle
  routing problem with time windows plus skills and parts. First-time-fix rate is the headline field-service
  KPI. Legal constraints bind:
  - UK: gas work only by an HSE-approved class of person (Gas Safety (Installation and Use) Regs 1998,
    reg. 3).
  - Japan: wiring work requires a licensed electrician (Electrician Act Art. 3).
  - EU: 11 h daily rest and a 20-minute break per 6 h (Working Time Directive).
  - Korea: a 40 + 12 h weekly cap.
- **Client & request** — The service operations manager of a boiler and heat-pump maintenance company:
  "Please dispatch our technicians to tomorrow's jobs."
- **Deliverable** — Batch `dispatch.json`:
  `{"routes": [{"technician": "T03", "stops": [{"job": "J017", "arrive": "HH:MM"}, ...]}], "unassigned": ["J088", ...]}`.
- **World & data** — The agent receives:
  - `technicians.csv`: 18 technicians with skills, gas_licensed, home_base, shift_start, shift_end and
    last_shift_end_yesterday.
  - `jobs.csv`: 130 jobs with type, window (AM 08-12 / PM 13-17 / exact), contract_tier, duration in minutes,
    required_part, repeat_of and vulnerable_household.
  - `van_stock.csv`, `travel_minutes.csv` (a free-flow matrix) and `depot.csv`.

  Hidden truth: none. The deliverable is fully scored from world data.
- **Hidden requirements**
  - `gas_license` (missing; business rule): gas appliance jobs need gas_licensed = Y.
  - `skills` (ambiguous; data semantics): heat-pump jobs need skill HP. "Boiler" covers both gas and oil
    boilers, and only gas ones need the licence.
  - `windows` (missing; business rule): arrival must fall inside the window. Gold contracts allow no lateness.
    Standard contracts pay a penalty per late minute.
  - `parts` (missing; calculation): a job needing a part not on the van requires a depot detour, adding 25
    minutes plus travel.
  - `rush_hour` (missing; calculation): travel starting between 07:30 and 09:30 or 16:30 and 18:30 takes 1.3
    times the matrix time.
  - `rest_and_break` (missing; business rule): an 11 h rest after last_shift_end_yesterday delays the start.
    After 6 h of work a 30-minute break is required (company rule above the EU minimum).
  - `duration_units` (ambiguous; data semantics): rows tagged `src = legacy` give duration in hours.
  - `vulnerable_same_day` (missing; business rule): no-heat jobs for vulnerable households must not be left
    unassigned.
  - `cost_model` (missing; scoring): travel costs 1 per minute. Late standard minutes cost 5 each, an
    unassigned job 300, and overtime minutes 1.5 each up to 60.
- **Rules**

  | id | class | check | why this class |
  |---|---|---|---|
  | licensed_gas | physical | gas jobs only go to licensed technicians | statutory |
  | rest_11h | physical | first start at least 11 h after the previous end | labor law |
  | gold_window | contractual | Gold jobs arrive inside the window | SLA contract |
  | max_overtime | contractual | shift end plus at most 60 minutes | union agreement |
  | same_tech_repeat | business_policy | a repeat visit goes to the original technician | locks about 15 jobs to one technician each, adding about 7% travel and lateness cost |

- **Objective** — Minimize total cost (travel + lateness + unassigned + overtime) under rush-hour travel
  times and depot detours. The reference uses priority-ordered cheapest insertion (vulnerable first, then
  Gold) followed by intra-route 2-opt. Headroom is about 8-12%, from inter-route moves.
- **Hard tier** — Duplicate job rows, and a stale `van_stock_backup.csv`. Client unavailable for an hour. A
  deadline pulled in. Twist: a technician calls in sick mid-task (a data correction removes T07).
- **Policy & language angles** — Under `regulated_strict` the repeat-visit bend needs approval. Under
  `startup_velocity` it can be justified. To localize: addresses, names, job-type labels (보일러 / ボイラー /
  caldera), and 24-hour time throughout. Pitfall: es data in d/m/y and Korean AM/PM (오전/오후) labels in raw
  windows.
- **Authoring risks** — Instances must be feasible for the licensed-gas rule under tight windows. Make sure
  the reference beats the trivial solution, and that the policy rule actually binds.
- **Sources**
  - https://en.wikipedia.org/wiki/Field_service_management
  - https://en.wikipedia.org/wiki/Vehicle_routing_problem
  - https://www.legislation.gov.uk/uksi/1998/2451/regulation/3
  - https://en.wikipedia.org/wiki/Working_Time_Directive_2003
  - https://en.wikipedia.org/wiki/Working_hours_in_South_Korea

---

**Research note.** The shared web-search budget ran out partway through research, so the Knowledge Base QA
and Field Service roles rest on direct fetches of primary pages instead of searches. The following facts are
cited from domain knowledge and were not re-verified here:
- Korea PIPA Enforcement Decree Art. 41 (10 days)
- Korea Network Act Art. 50
- Japan Electrician Act Art. 3
- the EU legal-guarantee period

Verify them before authoring.
