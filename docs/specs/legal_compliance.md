# Legal & Compliance — case specs

Automation in legal and compliance work today means triage and rule application on top of a register, not
legal judgment. Privacy-ops platforms (DataGrail, OneTrust, Transcend and others) route data-subject requests
across hundreds of system connectors. Their research shows request volumes rising five years in a row and
deletion requests up more than 500% since 2021. Vendors cite Gartner estimates of about USD 1,400-1,650 per
manually handled request. Incident-response teams run notification matrices because the clocks now differ
sharply: 72 hours in the EU and Korea, 3-5 days for a preliminary report in Japan, 4 hours for large incidents
in China since November 2025, 3 business days in Brazil, and 30 days in a growing number of US states. Export
compliance tools screen parties against consolidated lists with fuzzy matching and classify products from
their parameters. HR and policy chatbots have shown that a company is bound by what its bot says
(*Moffatt v. Air Canada*, 2024). In every deployment the hard part is the same: a statutory clock, an exemption
or a carve-out that is written in law or a playbook, not in the data. That is why the field suits a
clarify-then-build benchmark.

| Role | Task type | Deliverable | Hook |
|---|---|---|---|
| Contract Review Counsel ✅ | Extraction + rules | Batch `review.json` | (built) |
| Privacy Request Handler | Rules + search | Batch `responses.json` | Six statutory clocks, legal holds and alias e-mails decide each answer |
| Breach Notification Assessor (replaces Regulatory Reporting Analyst) | Rules + calculation | Batch `notifications.csv` | Who must be told, by when, under five regimes, from a deduplicated victim list |
| Trade Compliance Officer | Classification + rules | Batch `classifications.csv` + `order_decisions.csv` | Parameters, not product names, decide the control code; the affiliates rule wakes up on 2026-11-10 |
| Policy Q&A Assistant | Retrieval QA | Program `answer(question)` | The right version, the statutory floor, the clause citation, and knowing when to refuse |

**Replacement.** The catalog's *Regulatory Reporting Analyst* is replaced by a *Breach Notification
Assessor*. As written ("ledger-to-report mapping, thresholds, restated prior periods"), that role is a
financial-close task. It overlaps the finance field and depends on a regulator template that is hard to keep
neutral across countries. Breach notification is a core legal-compliance duty and a very active automation
area. It also has hard, deterministic and very different statutory triggers and deadlines in all five
benchmark locales (GDPR/Spain, Korea PIPA, Japan APPI, China CAC, US states, plus Brazil's LGPD for the
Spanish/LatAm angle). The field stays at 5 roles.

---

### Privacy Request Handler — `legal_compliance/privacy_request_handler`
- **Why it matters** — Data-subject request volumes have grown for five straight years. About 87% are deletions,
  while access requests are fewer but much more work. Fewer than a quarter of companies have automated
  fulfilment. Regulators enforce both sides: answering late, and releasing data to someone who is not the data
  subject. Deadlines differ by law (one month under GDPR Art. 12(3), 45 days under 11 CCR 7021, 10 days under
  Korea's PIPA Enforcement Decree Art. 41/44, 15 days for LGPD access requests).
- **Client & request** — Privacy operations lead at a consumer app sold in Spain, California, Korea, Japan,
  China and Brazil: "Here are this month's personal-data requests and our system exports. Work out what we owe
  each person and by when."
- **Deliverable** — Batch `responses.json`:
  `{"R0001": {"action": "fulfill"|"partial"|"deny"|"extend"|"await_verification", "due_date": "YYYY-MM-DD",
  "record_ids": ["CRM-0042", "TKT-9913"]}}`. For access requests `record_ids` lists the records to disclose; for
  deletion requests it lists the records to erase. One entry per request.
- **World & data** — 5,000 customers and 120 requests. Files: `requests.csv` (request_id, received_at_utc,
  jurisdiction, type = access/delete/correct/opt_out, requester_email, stated_name, verification_status,
  verification_requested_at, verification_completed_at), `customers.csv` (customer_id, primary_email,
  alt_emails, name, country), system exports `crm.csv`, `billing.csv` (invoices), `marketing_events.csv` and
  `support_tickets.csv` (about 40k rows; tickets are keyed by e-mail, not customer_id), `legal_holds.csv`
  (hold_id, customer_id, matter, start, released_at), `retention_schedule.csv`. Hidden in the world: the true
  requester-to-customer match (including alias e-mails and 6 impostor requests), and the true record set and
  outcome for each request.
- **Hidden requirements**
  - `deadlines` (missing; calculation) — ES: one calendar month from receipt; if the month has no matching day,
    the last day of that month. US-CA: 45 calendar days. KR: 10 days. BR access: 15 days. JP: client SLA of
    14 days (APPI Art. 33 only says "without delay"). CN: 30 days (the industry reading of PIPL Art. 50 and
    GB/T 35273). Received times are in UTC and must be converted to the jurisdiction's local date first.
  - `verification_clock` (ambiguous; calculation) — Under GDPR the clock pauses from a prompt verification request
    until the person verifies, per EDPB Guidelines 01/2022. Under CCPA it does not pause, and a request still
    unverified on day 45 is denied.
  - `opt_out_no_verify` (missing; business rule) — CCPA opt-out of sale/sharing needs no identity verification and
    is due in 15 business days (11 CCR 7026).
  - `legal_hold` (missing; business rule) — Records under an active hold are not erased (GDPR Art. 17(3)(e), legal
    claims), and the action becomes `partial`. Holds whose `released_at` falls before the due date do not
    count.
  - `tax_retention` (missing; data semantics) — Invoices in `billing.csv` stay for the retention period in the
    schedule (KR 5 years, JP 7, ES 6, BR 5, CN 10, CA 4). They are excluded from erasure but included in access
    disclosures.
  - `identity_match` (ambiguous; data semantics) — Match on primary or alternate e-mail after trimming and
    lowercasing. A name mismatch alone is not grounds to deny. A requester e-mail that matches no customer is
    `deny`.
  - `all_systems` (missing; data semantics) — Access and deletion cover all four exports, including tickets found
    by e-mail.
  - `extension` (missing; business rule) — `extend` is allowed only for ES/CA requests with more than 1,000
    records. The due date then becomes +2 months (ES) or +45 days (CA).
  - `scoring` (missing; scoring) — The score is the mean over requests of 0.4 × action correct + 0.2 × due date
    exact + 0.4 × record-set F1.
- **Rules**

  | id | class | check | why |
  |---|---|---|---|
  | `all_requests_answered` | physical | every request_id present | a request left unanswered is a statutory breach |
  | `no_disclosure_unverified` | physical | no access records released for unverified or impostor requests | that disclosure would itself be a data breach |
  | `no_erasure_under_hold` | physical | no held record listed for erasure | spoliation of evidence |
  | `due_within_law` | contractual | due_date ≤ statutory or SLA date | the JP/CN dates are client SLA readings, so contractual |
  | `auto_close_unverified_7d` | business_policy | access/delete requests unverified 7 days after the verification e-mail are `deny` | closes GDPR requests whose clock was paused and that would have verified on day 8-20, so correct fulfilments are lost |
- **Objective** — Maximize the score above. Reference: deterministic rules with an exact primary-email join and
  the correct deadline table, but no alias e-mails and no ticket lookup by e-mail. Expected headroom about 10%.
- **Hard tier** — Duplicate request rows (the same person on web and e-mail: merge them and use the earlier
  receipt). A stale backup of `legal_holds.csv` that is missing a hold opened last week. CP949/Shift_JIS
  exports. Data correction: a hold is released mid-task. Twist: a California requester has moved to Spain, and
  the jurisdiction is decided by `jurisdiction`, not by `customers.country`.
- **Policy & language angles** — `regulated_strict`: the auto-close policy may not bend without escalation, and
  NOTES must cite the legal basis for every `partial`. `startup_velocity`: bending auto-close is the trap,
  because GDPR losses outweigh the time saved. `enterprise_balanced`: justify it. Localize the request-type
  labels (열람/削除/acceso/acesso), national IDs in CRM notes (RRN, My Number, DNI/NIE, CPF, 身份证号) and date
  formats. Japanese exports may carry Reiwa-era dates.
- **Authoring risks** — The JP/CN deadlines are not statutory numbers: state them in requirements.md as client
  SLA. Month-end arithmetic must be spelled out. Generate impostors from e-mails that do not resolve to any
  customer, so they cannot be told apart by fuzzy logic alone.
- **Sources**
  - https://law.cornell.edu/regulations/california/11-CCR-7021
  - https://gdpr-info.eu/art-17-gdpr/
  - https://www.activemind.legal/guides/edpb-guidelines-right-of-access/
  - https://knowledge.clym.io/en/article/what-are-some-of-the-common-deadlines-for-answering-a-dsar-9jh4ev/
  - https://www.datagrail.io/blog/data-privacy/the-1-5m-dsr-problem-what-datagrails-research-found/
  - https://www.nepla.ai/wiki/it-정보-방송통신/개인정보-위치정보-신용정보/-일문일답-정보주체가-자기-정보에-대한-열람-요청을-하면-반드시-열람시켜줘야-할까-0o4866l5q8el
  - https://secureprivacy.ai/blog/how-do-companies-automate-dsar-workflows

---

### Breach Notification Assessor — `legal_compliance/breach_notification_assessor`
- **Why it matters** — Breach clocks have tightened and diverged.
  - EU and Spain: GDPR Art. 33, 72 hours from awareness.
  - Korea: after the 2023 PIPA amendment, 72 hours both to individuals and to the PIPC/KISA. Regulator reporting
    is required at 1,000 or more subjects, for sensitive or unique identifiers, or for external hacking.
  - Japan (APPI): preliminary report within 3-5 days, final report within 30 days (60 days for malicious
    breaches).
  - China: the CAC measures in force since 2025-11-01 require a 4-hour report above 1 million people.
  - Brazil (ANPD Res. 15/2024): 3 business days.
  - US states: Colorado, Florida and now California give 30 days, with attorney-general notice at 500 or more
    residents.

  Missing a clock brings fines (up to KRW 30 million in Korea for late notice alone). Over-notifying costs money
  and causes notification fatigue.
- **Client & request** — Group DPO of an e-commerce and payments group: "We've had a run of security
  incidents. Tell me which ones we actually have to report, to whom, and by when."
- **Deliverable** — Batch `notifications.csv` with columns incident_id, jurisdiction (ES|KR|JP|CN|BR|US-CA|US-CO|
  US-FL), recipient (REGULATOR|INDIVIDUALS|REGULATOR_FINAL|AG) and deadline_utc (ISO 8601, to the hour). One row
  per required notification. An incident with none gets one row with recipient `NONE`.
- **World & data** — 60 incidents and about 150k victim rows. Files: `incidents.csv` (incident_id, detected_at
  local+tz, personal_data_confirmed_at, cause = ransomware/misdelivery/lost_device/insider/misconfig/
  credential_stuffing, encrypted, key_compromised), `affected_subjects.csv` (incident_id, subject_id,
  residence, data categories, national_id_hash), `holidays.csv` (BR, KR, JP). Hidden in the world: the true
  unique-person count per incident and residence, and the required notification set.
- **Hidden requirements**
  - `clock_start` (ambiguous; calculation) — Clocks run from `personal_data_confirmed_at`, not from detection.
    Convert to UTC from the stated time zone.
  - `unique_persons` (missing; data semantics) — Count people, not rows. The same person appears under several
    subject_ids that share a `national_id_hash`. The KR ≥ 1,000, JP > 1,000 and US ≥ 500 thresholds use the
    deduplicated count per residence.
  - `kr_rules` (missing; business rule) — Individuals within 72 h for any leak. PIPC within 72 h if ≥ 1,000
    people, any RRN/passport/driver's-licence number, or external hacking.
  - `jp_rules` (missing; business rule) — PPC report (preliminary within 5 days by client practice, final within
    30/60 days) if there is sensitive data (要配慮), card data, an improper purpose, or more than 1,000 people. No
    report if the data was strongly encrypted and the key is safe.
  - `eu_rules` (missing; business rule) — Regulator within 72 h unless the breach is unlikely to create risk (the
    data was encrypted and the key not compromised). Individuals too when the risk is high (special categories,
    national ID, card, password).
  - `br_cn_rules` (missing; calculation) — ANPD and individuals within 3 business days, skipping BR holidays. CN:
    provincial CAC within 4 h only above 1,000,000 people. Otherwise PIPL Art. 57 notice within 72 h under the
    client playbook.
  - `us_pi_definition` (ambiguous; data semantics) — US states count only name plus SSN, driver's licence or
    card+code, or (CA only) username+password. E-mail alone does not count. The encryption safe harbour applies.
    CA consumer notice within 30 days; AG notice for 500 or more residents within 15 days after that.
  - `scoring` (missing; scoring) — 0.6 × F1 over (incident, jurisdiction, recipient) + 0.4 × the share of true
    positives whose deadline is exact to the hour.
- **Rules**

  | id | class | check | why |
  |---|---|---|---|
  | `every_incident_decided` | physical | each incident has ≥ 1 row | an undocumented decision breaks the Art. 33(5) record duty |
  | `deadline_not_after_law` | physical | for listed rows, deadline ≤ statutory deadline | statutory clocks never bend |
  | `playbook_readings` | contractual | JP 5-day and CN 72 h rows follow the playbook | these turn vague statutory words into fixed numbers, so the client owns them |
  | `notify_individuals_everywhere` | business_policy | every incident gets an INDIVIDUALS row in each residence jurisdiction | over-notifies low-risk and encrypted incidents, which lowers precision |
- **Objective** — Maximize the score. Reference: the full rule matrix, but it counts rows instead of
  deduplicated persons and ignores BR holidays. Expected headroom 8-12%.
- **Hard tier** — Duplicate victim rows. A stale `incidents.csv` without corrected confirmation times. A
  legacy encoding. Stakeholder conflict: PR asks to hold all notices until a press date (the law wins). Late
  requirement: Florida residents are added. Twist: one lost laptop was encrypted, but a note shows the key was
  taped to it, so the encryption exemption does not apply.
- **Policy & language angles** — `regulated_strict` forbids bending the notify-everyone policy without approval.
  `startup_velocity` rewards precision. Localize regulator names (개인정보보호위원회, 個人情報保護委員会, 网信办, AEPD, ANPD),
  ID types and time-zone labels (KST/JST/CST/CET/BRT). In zh, "CST" means China Standard Time, not US Central.
- **Authoring risks** — The statutes have discretion. requirements.md must fix every judgment ("high risk" =
  the listed categories) so the truth is deterministic. Deadlines are compared in UTC, to the hour.
- **Sources**
  - https://gdpr-info.eu/art-33-gdpr/
  - https://www.privacyworld.blog/2023/05/south-korea-consults-on-draft-decree-to-personal-information-protection-act/
  - https://law.asia/doing-business-in-korea-data-privacy-compliance
  - https://iapp.org/news/a/practical-notes-for-japans-important-updates-of-the-appi-guidelines-and-qas
  - https://www.morganlewis.com/pubs/2025/09/china-issues-new-cybersecurity-incident-reporting-framework
  - https://www.mayerbrown.com/en/insights/publications/2025/12/chinas-cybersecurity-incident-reporting-measures-come-into-effect
  - https://www.trenchrossi.com/en/legal-alerts/brazilian-data-protection-authority-anpd-publishes-regulation-on-notification-of-security-incident/
  - https://www.accountablehq.com/post/which-u-s-states-have-breach-notification-deadlines-stricter-than-hipaa
  - https://privacyrights.org/sites/default/files/2026-01/PrivacyRightsClearinghouse_DataBreachNotificationLaws_2026.pdf

---

### Trade Compliance Officer — `legal_compliance/trade_compliance_officer`
- **Why it matters** — Under the EAR the exporter is responsible for its own classification. The control code
  comes from technical parameters on the Commerce Control List, not from the product name. EAR99 items can
  still need a licence for restricted end users. Entity-List parties get no licence exceptions (15 CFR
  744.11). The 50%-affiliates rule is written into 744.11(a)(1) but stayed until 2026-11-09, so it applies to
  shipments from 2026-11-10. Party screening runs on the Consolidated Screening List, with fuzzy matching for
  transliterated names.
- **Client & request** — Export manager at a Korean/Japanese maker of thermal cameras, network appliances and
  drone parts: "Classify our catalogue and tell us which open orders can ship."
- **Deliverable** — Batch `classifications.csv` (product_id, control_code: a Wassenaar-style code such as
  `6A003.b.4`, `5A992`, or `EAR99`) and `order_decisions.csv` (order_id, decision =
  SHIP_NLR|SHIP_EXCEPTION|HOLD_LICENSE|BLOCK, exception = LVS|ENC|NONE).
- **World & data** — 80 products, 300 open orders, 150 customers, and a restricted list of 400 names. Files:
  `product_specs.csv` (parameters with units: resolution, frame_rate, operating_temp, endurance_min,
  key_length, mass_market_flag), `bom.csv` (component value, origin), `orders.csv` (order_id, customer_id,
  product_id, qty, net_value_usd, ship_date, end_use_note), `customers.csv` (name, romanized and native,
  country, parent_id, ownership_pct), `restricted_parties.csv`, `control_list.csv` (synthetic thresholds),
  `country_groups.csv`. Hidden in the world: the true code per product and the true list matches.
- **Hidden requirements**
  - `parameters_decide` (ambiguous; data semantics) — Thermal cameras with frame rate ≤ 9 Hz drop to the
    decontrolled entry whatever the marketing category. Temperature columns mix °C and °F, and range columns mix
    km and miles.
  - `mass_market` (missing; business rule) — Encryption that meets the mass-market note is 5A992 under ENC
    (b)(1), not 5A002.
  - `de_minimis` (missing; calculation) — Products made outside the US are subject to the EAR only if their
    controlled US-origin content is above 25% of value (10% for E:1 destinations).
  - `screening` (ambiguous; data semantics) — Match on native-script names and normalized romanizations, and drop
    legal suffixes (Co., Ltd., 有限公司, 株式会社, ㈜, S.A. de C.V.). A match means BLOCK.
  - `affiliates_date` (missing; business rule) — For ship_date ≥ 2026-11-10, a customer ≥ 50% owned by a listed
    party (summed through parents) means HOLD_LICENSE.
  - `lvs` (missing; calculation) — LVS only to Country Group B, with net value per order within the entry limit.
    Orders split on the same day for the same consignee are combined (15 CFR 740.3 bans splitting).
  - `catch_all` (missing; business rule) — An end-use note that mentions military or WMD use means HOLD_LICENSE,
    even for EAR99.
  - `country_groups` (missing; business rule) — E:1 means BLOCK. National-security-controlled items to D:1
    mean HOLD_LICENSE.
- **Rules**

  | id | class | check | why |
  |---|---|---|---|
  | `no_ship_to_listed` | physical | no SHIP_* to true list matches | statutory prohibition |
  | `no_ship_without_licence` | physical | no SHIP_* where a licence is required | an unlicensed export is a crime |
  | `all_orders_decided` | physical | every order present | |
  | `new_products_controlled` | business_policy | products launched < 90 days ago are HOLD_LICENSE | blocks lawful revenue on EAR99/5A992 newcomers |
- **Objective** — Maximize 0.4 × classification accuracy + 0.6 × the share of value shipped out of the value
  that can lawfully ship. Reference: correct thresholds, but it assumes °C and screens exact romanized names
  only. Expected headroom 8-12%.
- **Hard tier** — Duplicate orders. A stale restricted list missing last month's additions. A data correction to
  ownership percentages. The deadline is pulled in. Twist: the same customer has orders on both sides of
  2026-11-10.
- **Policy & language angles** — `regulated_strict`: escalate before releasing any held new product.
  `startup_velocity`: may justify releasing EAR99 newcomers. Localize customer names in native script, Korean
  전략물자 and Japanese 該非判定 terms, and decimal commas in es parameter sheets.
- **Authoring risks** — Use synthetic thresholds labelled as such, so the case teaches the reasoning, not today's
  CCL. State that the case decides under US EAR rules only.
- **Sources**
  - https://www.bis.gov/licensing/classify-your-item
  - https://www.law.cornell.edu/cfr/text/15/744.11
  - https://www.law.cornell.edu/cfr/text/15/740.3
  - https://www.law.cornell.edu/cfr/text/15/740.17
  - https://www.trade.gov/consolidated-screening-list
  - https://en.wikipedia.org/wiki/Export_Control_Law_of_the_People%27s_Republic_of_China

---

### Policy Q&A Assistant — `legal_compliance/policy_qa_assistant`
- **Why it matters** — HR policy bots are a common first deployment of generative AI. *Moffatt v. Air Canada*
  held a company liable for negligent misrepresentation by its chatbot, so wrong answers carry real cost. The
  EU AI Act Art. 50 transparency duties apply from 2026-08-02. Leave law sets floors that handbooks cannot go
  below:
  - Korea (LSA Art. 60): 15 days after one year, +1 day per 2 years, up to 25.
  - Japan (LSA Art. 39): 10 days after 6 months with 80% attendance, up to 20.
  - China: 5/10/15 days by cumulative years of work.
  - Spain (Estatuto de los Trabajadores Art. 38): 30 calendar days.
- **Client & request** — HR operations head: "People keep asking HR the same policy questions. Build something
  that answers them from our handbook."
- **Deliverable** — Program `answer(question: dict) -> dict`. The input has keys question_id, employee_id,
  asked_on, text. The output is `{"type": "answer"|"refuse"|"escalate", "value": number|string|null,
  "citation": "POL-LEAVE-KR-v3#4.2", "refer_to_hr": bool}`.
- **World & data** — 6 countries (KR, JP, CN, ES, MX, US), 40 policy files with versions (`policies/*.md`,
  front-matter effective_from and superseded_by), `employees.csv` (employee_id, employing_entity_country,
  work_location, hire_date, prior_service_years, part_time_days, grade), and 60 labelled example questions.
  Hidden: 500 test questions, templated, with exact answers.
- **Hidden requirements**
  - `version_by_event_date` (ambiguous; data semantics) — Use the version in force on the date of the event asked
    about (the trip date, the leave date), not on asked_on.
  - `employing_entity` (ambiguous; business rule) — The employing entity's country decides the policy. Secondees
    stay on home policy for up to 12 months.
  - `statutory_floor` (missing; calculation) — The answer is the larger of the handbook value and the statutory
    floor. In CN, cumulative years include prior_service_years.
  - `part_time_prorata` (missing; calculation) — JP part-timers get the proportional grant table. ES leave is
    stated in calendar days.
  - `currency_units` (missing; data semantics) — Per-diem values are local-currency integers (KRW and JPY have no
    decimals).
  - `citation_format` (missing; scoring) — The citation is policy-id-version#clause. An answer without the right
    citation scores 0.
  - `refuse_scope` (missing; business rule) — Questions on legal claims ("is my dismissal lawful?") or about
    another employee's data get `refuse`.
  - `escalate_harassment` (missing; business rule) — Harassment or whistleblowing questions get `escalate` with
    the hotline policy cited.
- **Rules**

  | id | class | check | why |
  |---|---|---|---|
  | `no_other_employee_data` | physical | never returns another employee's data | privacy law |
  | `no_legal_advice` | contractual | legal-claim questions are refused | the HR service charter sets the bot's scope |
  | `always_refer_hr` | business_policy | `refer_to_hr=true` on every answer | each referral opens a ticket; the deflection KPI counts referred answers at 0.5 |
- **Objective** — Maximize the mean over questions: 1 for a correct value with the correct citation (0.5 if
  referred). Refusals and escalations count when correct. Reference: keyword retrieval, latest version, no
  statutory floor. Expected headroom 10-15%.
- **Hard tier** — A stale handbook export. An encoding issue. A late requirement: an MX policy update
  mid-task. Twist: a KR policy v4 takes effect in the middle of the question window.
- **Policy & language angles** — `regulated_strict` keeps referrals. Questions arrive in the customer locale:
  연차, 年休, 年假, vacaciones.
- **Authoring risks** — The templated questions must have exactly one answer. Freeze the statutory tables in
  requirements.md.
- **Sources**
  - https://www.mccarthy.ca/en/insights/blogs/techlex/moffatt-v-air-canada-misrepresentation-ai-chatbot
  - https://artificialintelligenceact.eu/article/50/
  - https://laws.e-gov.go.jp/law/322AC0000000049
  - https://www.boe.es/buscar/act.php?id=BOE-A-2015-11430
