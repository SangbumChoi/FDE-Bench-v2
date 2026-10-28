# Case specs

Research-grounded specs for the catalog's unbuilt cases, one file per field. Each spec gives the client's
request, the deliverable, the world and data, 7-9 hidden requirements, rules with classes, the objective and
reference approach, hard-tier hooks, policy and language angles, authoring risks and sources. The catalog
itself is [`cases/README.md`](../cases/README.md).

## Before authoring a case from a spec

1. **One rule set per case, for every locale.** Scoring is language-independent (DESIGN.md §3): a case's
   hidden requirements, thresholds and rules are the same whichever customer locale it runs in. Where a spec
   describes country-specific law (axle limits, reference-price windows, notification deadlines, tax-document
   rules), pick one rule set for the case and state it in every locale's `requirements.md`; mention the other
   countries' variants only as background. A few spec sections (notably in `logistics.md`) sketch per-locale
   limits; collapse them this way when authoring.
2. **Verify flagged facts.** The research ran into a shared web-search quota, so some regulatory details come
   from secondary sources or the researcher's background knowledge. Each file ends with, or marks inline,
   the facts to check against the primary text. The case itself states its numbers, so scoring never depends
   on them, but realism does.
3. **Legal limits are `physical` or `contractual`**, never `business_policy`, so no policy can bend them.

## Coverage

| Field | Roles specced | Notes |
|---|---|---|
| [Finance](finance.md) | 9 | Card fraud and trading are Programs; portfolio, treasury and insurance details partly from industry practice (flagged) |
| [Healthcare](healthcare.md) | 7 | Medical Claims Coder's bendable rule changed from "highest specificity" (upcoding) to "no unspecified codes, query the physician" |
| [Manufacturing](manufacturing.md) | 8 | Spare parts and pallet load thinly sourced; supplier-risk rule collision resolved in favor of the legal rule |
| [Retail](retail.md) | 7 | |
| [Logistics](logistics.md) | 6 | Bike-Share Rebalancing replaced by Freight Invoice Auditor; per-locale limits to collapse (see 1.) |
| [Customer Service](customer_service.md) | 5 | |
| [Data & Knowledge](data_knowledge.md) | 6 | Book QA researched in depth (now replaced by the built `multilingual_corpus_curator` program case); Report Automation becomes a Program on hidden future months |
| [Legal & Compliance](legal_compliance.md) | 4 | Regulatory Reporting Analyst replaced by Breach Notification Assessor |
| [People & HR](people_hr.md) | 4 | Thinner sourcing; several legal points to verify |
| [Energy & Utilities](energy_utilities.md) | 5 | EV tariff and outage restoration thinly sourced |
| [Public Sector](public_sector.md) | 4 | Permit processing thinly sourced |
