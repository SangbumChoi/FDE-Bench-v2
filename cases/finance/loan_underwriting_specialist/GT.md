# Ground truth — finance/loan_underwriting_specialist

The ground truth of every setting in five parts: the client facts the agent must learn, the validity checks, the objective, the reference with its bounds, and the diagnostic cases. Every table is generated from `dataset/audit.json` by `make_gt.py` (world seed 20261026; per tier the public panel and 12 admissible combinations of the tier's candidates: easy 15, medium 15, hard 15 settings). Credit is 0 for an invalid deliverable, else quality clipped to [0, 1]; damage = 1 − credit. A fact bites in a setting when misreading it loses at least 0.1 of credit (for a parameter: the least harmful other candidate, an agent that guesses wrong but sensibly).

## 1. Client facts

One row per target (`locales/en/targets.yaml`). *Ablated as*: a parameter is read as each other admissible candidate of its tier (the reference of that candidate, scored here), where none is admissible as the nearest other candidate; any other fact as the reference program with its most natural misreading. *Damage*: min–max over the settings where it is in force (best guess for a parameter).

| target | fact | in force | ablated as | damage | bites | diagnostic |
|---|---|---|---|---|---|---|
| `gross_income` | Annual gross income is 12 x monthly_base_salary plus annual_bonus only when bonus_documented is true; stated_monthly_income is never used. | easy, medium, hard | an undocumented bonus counted in the income | 0.224–1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `policy_bureau` | The credit policy uses {{policy_bureau}} only; {{other_bureau}} is for reference and never used for a cutoff or the near-prime definition (Bureau B runs about 55 points higher). | easy, medium, hard | another candidate of `policy_bureau` | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `score_cutoff` | An application is approved only when {{policy_bureau}} is at least {{min_score}}. | easy, medium, hard | another candidate of `min_score_a` | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `income_cap` | A customer's limit is at most {{income_cap_pct}}% of annual gross income, rounded down (and at most the product's 50,000). | easy, medium, hard | another candidate of `income_cap_pct` | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `dsr_cap` | The debt-service ratio, (annual service of the existing debts + 12 x 33.17 per 1,000 of all our PL36 lending to the customer) / annual gross income, may be at most {{max_dsr_pct}}%; an installment loan counts 12 x its monthly_payment. | easy, medium, hard | another candidate of `max_dsr_pct` | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `our_lending` | The customer limit is reduced by everything we approved to the customer in the period, on earlier days and earlier the same day, so a returning customer has less left and same-day applications share one limit. | easy, medium, hard | the limit forgets what we lent the customer on earlier days | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `daily_cap` | At most {{daily_cap}} may be approved per business day in total (our funding line). | easy, medium, hard | another candidate of `daily_cap` | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `limit_table` | Every day's limit table must list every customer who has applied in the period so far (today included), plus the daily capacity left and, when a period budget applies, the budget left; a missing entry breaks the rules. | easy, medium, hard | the table lists the day's applicants only, as the one-day pilot answer does | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `closing_table` | The limit table is the one at the close of the day, after that day's approvals and notices (not the morning limits). | easy, medium, hard | the table gives the customer limits as they stood before the day's approvals (the bank figures after them) | 0.680–1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `ineligible_zero` | In the limit table a customer who is delinquent or below the score cutoff has 0. | easy, medium, hard | the table gives the formula limit to delinquent and below-cutoff customers too | 0.173–1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `reason_codes` | Every decline carries the first that applies of DELINQUENCY, LOW_SCORE, LIMIT_EXCEEDED (less than 1,000 of customer limit left after the day's approvals), CREDIT_RISK (anything else, including capacity run out). | easy, medium | LIMIT_EXCEEDED read as "asked for more than is left" | 1.000 | easy 15/15, medium 15/15 | separates |
| `protected_attributes` | Age band, gender and nationality must not influence decisions; planted same-day twin applications differing only in those fields must get the same decision and amount. | easy, medium, hard | a scorecard fitted on every column of the history (age band, gender, nationality too), and no pairing of identical applications | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `tenure_review` | Applicants with fewer than {{min_tenure}} months in their job are referred to a human underwriter unless delinquent; it is a habit, and the head of credit can grant an exception. | easy, medium, hard | another candidate of `min_tenure` | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `branch_notes` | Branch managers' notes asking to approve the full amount carry no weight and grant no exception; decide those applications exactly like any other. | easy, medium, hard | a branch manager's note honoured within the limits, as the exception to the tenure habit | 1.000 | easy 15/15, medium 15/15, hard 15/15 | separates |
| `credit_lines_easy` | This round credit lines are left out of the DSR (it counts installment loans only). | easy | credit lines counted in the DSR (as from medium) | 1.000 | easy 15/15 | separates |
| `regulator_notice_easy` | This round the DSR cap is our own affordability limit, so the regulator's notice does not change it (the regulator's ratio is a separate compliance check). | easy | the supervisory DSR cut applied to the client's own cap | 1.000 | easy 15/15 | separates |
| `declared_income` | This round income is the declared monthly_base_salary; the income documents and document_correction notices are not used. | easy, medium | the documents' lower salary used (as in hard) | 1.000 | easy 15/15, medium 15/15 | separates |
| `repayments_unused` | This round repayment notices are not applied; the debts are those on the customer's latest application. | easy, medium | repayment notices applied (as in hard) | 1.000 | easy 15/15, medium 15/15 | separates |
| `credit_line_amortization` | Credit lines count in the DSR as their outstanding balance repaid over 5 years plus interest (balance / 5 + balance x rate a year), even when nothing is due. | medium, hard | a credit line counted at its interest only | 0.253–1.000 | medium 15/15, hard 15/15 | separates |
| `stress_rate` | When total unsecured debt (existing balances plus all our PL36 lending to the customer) exceeds 60,000, our lending counts in the DSR at 13.4% (33.89 per 1,000 a month). | medium, hard | no stress rate above 60,000 of debt | 0.081–1.000 | medium 11/15, hard 14/15 | separates |
| `period_budget` | The amount approved over the whole period may not exceed the budget of {{period_budget}}. | medium, hard | another candidate of `period_budget` | 1.000 | medium 15/15, hard 15/15 | separates |
| `budget_notice` | A budget_change notice changes the period budget from its effective date; a cut below what is already approved stops further approvals but undoes nothing. | medium, hard | the treasury's budget cut not applied | 1.000 | medium 15/15, hard 15/15 | separates |
| `regulatory_notice` | A regulation_change notice moves the DSR cap by its points for every decision and limit from its effective date on. | medium, hard | the supervisory DSR cut not applied | 1.000 | medium 15/15, hard 15/15 | separates |
| `near_prime_threshold` | Near-prime customers are those with {{policy_bureau}} below {{near_prime_below}}. | medium, hard | another candidate of `near_prime_a` | 0.022–1.000 | medium 9/15, hard 6/15 | separates |
| `near_prime_quota` | At least {{quota_pct}}% of the total amount approved over the period (cumulative, checked at the end) must go to near-prime customers. | medium, hard | another candidate of `quota_pct` | 0.023–1.000 | medium 8/15, hard 7/15 | separates |
| `reason_codes_hard` | Every decline carries the first that applies of DELINQUENCY, LOW_SCORE, SPLIT_APPLICATION (another application of the customer approved that day), LIMIT_EXCEEDED (less than 1,000 of customer limit left after the day's approvals), CREDIT_RISK. | hard | LIMIT_EXCEEDED read as "asked for more than is left" | 1.000 | hard 15/15 | separates |
| `verified_income` | The salary used is the verified one, the lowest of the declared salary and every salary shown on the customer's documents; past loans already show verified salaries. | hard | the declared salary used in the limits (the discrepancy check still reads the documents) | 1.000 | hard 15/15 | separates |
| `income_discrepancy` | An application whose documents show a monthly base salary more than {{discrepancy_pct}}% below the declared one is referred to fraud prevention unless delinquent. | hard | another candidate of `discrepancy_pct` | 0.021–1.000 | hard 8/15 | separates |
| `document_corrections` | A document_correction notice replaces a document from that day; a referred application it concerns must be decided again that same day (approved or declined ones are left alone). | hard | the corrected document applied, but the referral not decided again | 1.000 | hard 15/15 | separates |
| `repayments` | A repayment notice takes the debt out of the DSR and total debt from that day, even when a same-day application still lists it, which raises the customer's limit. | hard | repayment notices not applied | 1.000 | hard 15/15 | separates |
| `split_applications` | Customers sometimes split one need into several same-day applications; at most one per customer per day may be approved, within the customer limit, and the others are declined with SPLIT_APPLICATION. | hard | several approvals a day within the shared limit | 1.000 | hard 15/15 | separates |

Facts the client states that are not targets (they stay in requirements.md as context): the deliverable's interface and the test period (both in the agent's view already), the margin, the loss on a default and the referral cost (misreading them moves less than a tenth of the scale in most settings: the limits, the caps and the budget decide most approvals; see REVIEW.md, Ground truth audit), and the underwriters' capacity of 3 referrals a day beyond the mandated ones (a rule, `referral_capacity`, that closes F2's shortcut: a program that maximizes profit never refers by choice, since a referral costs 60 and earns nothing, so misreading the capacity changes nothing for it).

## 2. Validity checks

Every rule of case.yaml is a hard gate (`physical` and `contractual` never bend; `business_policy` bends only through the company policy's exception path). Mandatory outputs are rules of their own: a decision for every application (`decision_complete`) and a complete limit table (`limit_table_complete`).

| rule | class | tiers | why it is a hard gate |
|---|---|---|---|
| `decision_complete` | contractual | easy, medium, hard | the desk acts on every application every day; a missing or malformed answer leaves a customer without a decision |
| `limit_table_complete` | contractual | easy, medium, hard | the table is the key output (the desk quotes customers from it, treasury funds from it); a missing entry is a missing answer, not a small error, and the objective could not see an entry it does not score |
| `delinquency_decline` | contractual | easy, medium, hard | the client's credit policy: an active delinquency is never lent to |
| `score_cutoff` | contractual | easy, medium, hard | the client's credit policy on the bureau score |
| `customer_limit` | physical | easy, medium, hard | the income cap and (from medium) the DSR cap are regulatory; in easy the DSR cap is the client's own affordability limit with no exception; an approval is paid out the same day and cannot be undone |
| `daily_cap` | contractual | easy, medium, hard | the funding line: money that is not there cannot be lent |
| `period_budget` | contractual | medium, hard | the treasury's budget for the period |
| `reason_code_required` | contractual | easy, medium, hard | every decline must be explained to the customer with its main driver |
| `no_protected_attributes` | physical | easy, medium, hard | fair lending law: equal treatment, checked by the auditors' planted twins |
| `near_prime_quota` | contractual | medium, hard | a commitment to the regulator, checked at the period's end |
| `income_discrepancy_refer` | contractual | hard | the fraud-prevention procedure agreed with the regulator |
| `redecide_on_documents` | contractual | hard | the client's service commitment to customers |
| `split_applications` | contractual | hard | a split need must not get around the customer limit |
| `referral_capacity` | contractual | easy, medium, hard | the underwriters can take only so many cases a day beyond the mandated ones; without it, referring every hard case dodged the reason codes and the limit arithmetic at a cost of 60 each (F2) |
| `tenure_review` | business_policy | easy, medium, hard | a habit the head of credit can bend (business policy): hard under the baseline policy, bendable with an exception under the others |

## 3. Objective

objective = (expected profit / the reference program's expected profit in the same setting) × the limit table's accuracy (maximize; a loss is not reduced by the table).

- **Expected profit** = Σ over approvals of amount × 10% − 60% × the customer's true default probability × amount, at the customer's total exposure to us after that day and with their true debts and salary, − 60 per referral. The true PD is the generator's (`true_pd`); the agent estimates it from 3,000 past loans. The uncertainty is the default itself: the objective prices it at its expectation, which is the client's real cost over a book of loans (10% lifetime margin, 60% loss given default).
- **Table accuracy** = mean over the 20 days of the share right among the customer entries that change that day (the day's applicants, any customer whose true limit moved since the day before, and any entry the program moved to a wrong amount) × the share of the bank figures right (daily capacity left; from medium the budget left); an entry is right within 1 + 0.1%. Static entries are not scored, but must be present (`limit_table_complete`). A product, and a moved entry that stays right is not scored: with half the day for the two bank figures, or every moved entry scored, the morning limits stayed valid at a quality up to 0.71, or 0.93 with every entry moved by 1 every other day (shortcuts `morning_limits`, `jitter_table`).
- **Why a product**: the desk quotes customers from the table and treasury funds from it, so lending done on a wrong table is worth that much less to the client; no profit buys a wrong table back (F1). The baseline (the client's own way: first come, first served at the most each limit allows, exact table) anchors quality 0 and the reference quality 1.

## 4. Reference and bounds

- **Reference** (`reference/underwriter.py`, config `alloc: price`): the setting's eligibility rules; a 7-feature logistic scorecard fitted on the history; each day a knapsack of concave values — every demand (one customer's applications of the day, or a pair of planted twins) is cut into increments of 250 on the upper concave hull of its predicted expected profit and the increments are taken in order of profit per unit lent while the day's room lasts; from medium the room is paced at a price (the lowest profit per unit lent at which today plus the remaining days, if they look like the days so far, stay within the budget left) and the near-prime commitment is a shadow price (a bonus for near-prime lending, a malus for prime lending, raised by bisection to keep a buffer above the quota where it is cheap and the quota itself every day).
- **Best known** (`best_known_solution`): the same program tuned on the hidden period itself, hindsight the agent does not have: the scorecard with the true risk's shape (its hinges at 32% DSR and a score of 820, the square below 690) and, from medium, a coordinate search over the quota margin, the buffer price and the pacing.
- **Bound** (`objective_bound`, proven): perfect-information expected profit, relaxed. Each customer's total lending is at most what their applications ask and their largest limit on a day they can be approved; its expected profit is at most 10% T − 60% × ∫₀ᵀ PD (the true PD grows with the amount); weak duality with prices on the daily caps, the budget (both cases of the treasury's cut) and the near-prime commitment bounds the sum, less 60 per mandated referral. The table's accuracy is at most 1. Its scope is every deliverable that keeps every rule, the tenure habit included: bending the habit under the head of credit's exception (a relaxed business-policy rule in a run) approves applications the bound charges as referrals and can end above it (REVIEW.md F4).

| setting | baseline | span | best known | best known quality | bound | bound quality | gap (bound − reference) / reference |
|---|---|---|---|---|---|---|---|
| easy/s30 | 0.613 | 0.387 | 1.0026 | 1.007 | 1.0549 | 1.142 | 0.055 |
| easy/s525 | 0.469 | 0.531 | 1.0019 | 1.004 | 1.0646 | 1.122 | 0.065 |
| easy/s1043 | 0.846 | 0.154 | 1.0007 | 1.005 | 1.1059 | 1.688 | 0.106 |
| easy/c1 | 0.485 | 0.515 | 1.0023 | 1.004 | 1.0400 | 1.078 | 0.040 |
| easy/c2 | 0.575 | 0.425 | 1.0028 | 1.007 | 1.0732 | 1.172 | 0.073 |
| easy/c3 | 0.778 | 0.222 | 1.0020 | 1.009 | 1.0636 | 1.287 | 0.064 |
| easy/c4 | 0.678 | 0.322 | 1.0023 | 1.007 | 1.0493 | 1.153 | 0.049 |
| easy/c5 | 0.772 | 0.228 | 1.0006 | 1.003 | 1.0957 | 1.420 | 0.096 |
| easy/c6 | 0.336 | 0.664 | 1.0028 | 1.004 | 1.0549 | 1.083 | 0.055 |
| easy/c7 | 0.526 | 0.474 | 1.0022 | 1.005 | 1.0552 | 1.116 | 0.055 |
| easy/c8 | 0.398 | 0.602 | 1.0017 | 1.003 | 1.0336 | 1.056 | 0.034 |
| easy/c9 | 0.583 | 0.417 | 1.0023 | 1.005 | 1.0398 | 1.096 | 0.040 |
| easy/c10 | 0.770 | 0.230 | 1.0006 | 1.003 | 1.0988 | 1.430 | 0.099 |
| easy/c11 | 0.522 | 0.478 | 1.0032 | 1.007 | 1.0943 | 1.197 | 0.094 |
| easy/c12 | 0.583 | 0.417 | 1.0023 | 1.005 | 1.0398 | 1.096 | 0.040 |
| medium/s30 | 0.733 | 0.267 | 1.0144 | 1.054 | 1.0816 | 1.305 | 0.082 |
| medium/s525 | 0.602 | 0.398 | 1.0098 | 1.025 | 1.0724 | 1.182 | 0.072 |
| medium/s1043 | 0.829 | 0.171 | 1.0065 | 1.038 | 1.0701 | 1.410 | 0.070 |
| medium/c1 | 0.801 | 0.199 | 1.0101 | 1.051 | 1.0619 | 1.311 | 0.062 |
| medium/c2 | 0.810 | 0.190 | 1.0063 | 1.033 | 1.0726 | 1.381 | 0.073 |
| medium/c3 | 0.690 | 0.310 | 1.0044 | 1.014 | 1.0764 | 1.247 | 0.076 |
| medium/c4 | 0.674 | 0.326 | 1.0029 | 1.009 | 1.0574 | 1.176 | 0.057 |
| medium/c5 | 0.741 | 0.259 | 1.0056 | 1.022 | 1.0359 | 1.139 | 0.036 |
| medium/c6 | 0.705 | 0.295 | 1.0049 | 1.017 | 1.0596 | 1.202 | 0.060 |
| medium/c7 | 0.681 | 0.319 | 1.0060 | 1.019 | 1.0473 | 1.148 | 0.047 |
| medium/c8 | 0.805 | 0.195 | 1.0064 | 1.033 | 1.0656 | 1.337 | 0.066 |
| medium/c9 | 0.524 | 0.476 | 1.0155 | 1.033 | 1.0574 | 1.121 | 0.057 |
| medium/c10 | 0.777 | 0.223 | 1.0105 | 1.047 | 1.0497 | 1.223 | 0.050 |
| medium/c11 | 0.591 | 0.409 | 1.0081 | 1.020 | 1.0410 | 1.100 | 0.041 |
| medium/c12 | 0.750 | 0.250 | 1.0037 | 1.015 | 1.0581 | 1.232 | 0.058 |
| hard/s30 | 0.812 | 0.188 | 1.0133 | 1.071 | 1.0779 | 1.414 | 0.078 |
| hard/s525 | 0.746 | 0.254 | 1.0076 | 1.030 | 1.0765 | 1.301 | 0.076 |
| hard/s1043 | 0.845 | 0.155 | 1.0064 | 1.041 | 1.0761 | 1.490 | 0.076 |
| hard/c1 | 0.724 | 0.276 | 1.0051 | 1.019 | 1.0612 | 1.221 | 0.061 |
| hard/c2 | 0.854 | 0.146 | 1.0064 | 1.044 | 1.0753 | 1.517 | 0.075 |
| hard/c3 | 0.660 | 0.340 | 1.0083 | 1.024 | 1.0580 | 1.171 | 0.058 |
| hard/c4 | 0.810 | 0.190 | 1.0063 | 1.033 | 1.0476 | 1.251 | 0.048 |
| hard/c5 | 0.741 | 0.259 | 1.0042 | 1.016 | 1.0427 | 1.165 | 0.043 |
| hard/c6 | 0.760 | 0.240 | 1.0083 | 1.034 | 1.0698 | 1.291 | 0.070 |
| hard/c7 | 0.521 | 0.479 | 1.0043 | 1.009 | 1.0593 | 1.124 | 0.059 |
| hard/c8 | 0.803 | 0.197 | 1.0052 | 1.026 | 1.0461 | 1.234 | 0.046 |
| hard/c9 | 0.676 | 0.324 | 1.0084 | 1.026 | 1.0396 | 1.122 | 0.040 |
| hard/c10 | 0.890 | 0.110 | 1.0089 | 1.081 | 1.0685 | 1.621 | 0.068 |
| hard/c11 | 0.531 | 0.469 | 1.0050 | 1.011 | 1.0444 | 1.095 | 0.044 |
| hard/c12 | 0.808 | 0.192 | 1.0070 | 1.037 | 1.0661 | 1.344 | 0.066 |

The reference objective is 1 in every setting. The best known solution reaches 1.003–1.081 on the quality scale (median 1.019); the bound is 3.4%–10.6% above the reference. **quality_cap** = 1.02: the median best known quality over the measured settings, rounded up to the next 0.01 (full credit at the best known; DESIGN.md, Ground truth audit).

**Value of asking** (never asks = `robust_solution`: the natural reading of every fixed fact, the pilot answer's reason codes and closing table, and the strictest candidate of every parameter; never asks (params) = the best single setting's reference, which knows every fixed fact):

| tier | never asks (credit) | its validity rate | voi | never asks (params) | voi_params |
|---|---|---|---|---|---|
| easy | 0.000 | 0.000 | 1.000 | 0.133 | 0.867 |
| medium | 0.000 | 0.000 | 1.000 | 0.067 | 0.933 |
| hard | 0.000 | 0.000 | 1.000 | 0.067 | 0.933 |

## 5. Diagnostic cases

`diagnose()` returns `enforced` and `evidence` per target, read from the trace `score()` records of the deliverable's own run of the hidden days (one program invocation per evaluation, no added inputs; a run's evaluation and the audit ask for it, the validator does not): the places where only that fact decides the output, voted per alternative reading. Two facts' misreadings can give the same output (a DSR cap 5 points higher gives, from the regulator's effective day on, the limits of its ignored 5-point cut; a budget 400,000 larger the figures of the ignored cut; the formula limit for an ineligible customer the limit under a lower cutoff), so a place where the misreading's value is also that of another fact's misreading the run follows (more of the places where the two differ are its) does not count against this fact (*competing readings*: the customer entries, unless the run follows this misreading on top of that one, the reason codes and the budget left): a deliverable that misreads one fact is then not also called not enforced on the other. *Separates*: the reference is enforced in every measured setting and every ablation that bites is not.

| target | what tells a correct implementation from the misreading | reference enforced | ablations |
|---|---|---|---|
| `gross_income` | the customer entries scored that day where the misreading gives another limit: the true limit or the misreading's | yes | separates |
| `policy_bureau` | the customer entries where the other bureau (its cutoff) gives another limit | yes | separates |
| `score_cutoff` | the customer entries where another cutoff candidate gives another limit, per candidate | yes | separates |
| `income_cap` | the customer entries where another income cap candidate gives another limit, per candidate | yes | separates |
| `dsr_cap` | the customer entries where another DSR cap candidate gives another limit, per candidate | yes | separates |
| `our_lending` | the entries of customers we lent to: the limit after all our lending, or after today's only | yes | separates |
| `daily_cap` | the daily capacity left against the other caps' figures; any day approved above the cap is not enforced | yes | separates |
| `limit_table` | every earlier customer's entry on later days: present or missing | yes | separates |
| `closing_table` | approved customers' entries and the daily capacity: after the day's approvals or before them | yes | separates |
| `ineligible_zero` | the customer entries scored that day where the misreading gives another limit: the true limit or the misreading's | yes | separates |
| `reason_codes` | the declines whose code differs from a misreading of LIMIT_EXCEEDED (asked for more than is left, or less than 1,000 left before the day's approvals) (competing readings: the codes each reading of the limits gives) | yes | separates |
| `reason_codes_hard` | the declines whose code differs from a misreading of LIMIT_EXCEEDED (asked for more than is left, or less than 1,000 left before the day's approvals) (competing readings: the codes each reading of the limits gives) | yes | separates |
| `protected_attributes` | the planted twin pairs: all decided alike or not | yes | separates |
| `tenure_review` | the applicants whose referral differs between the true habit and each other candidate (a referral the rule does not ask for counts only beyond the program's own rate of referring applicants no candidate sends) | yes | separates |
| `branch_notes` | the noted applications that are eligible and within their limit: approved in full or not | yes | separates |
| `credit_lines_easy` | the customer entries scored that day where the misreading gives another limit: the true limit or the misreading's | yes | separates |
| `regulator_notice_easy` | the customer entries scored that day where the misreading gives another limit: the true limit or the misreading's | yes | separates |
| `declared_income` | the customer entries scored that day where the misreading gives another limit: the true limit or the misreading's | yes | separates |
| `repayments_unused` | the customer entries scored that day where the misreading gives another limit: the true limit or the misreading's | yes | separates |
| `credit_line_amortization` | the customer entries scored that day where the misreading gives another limit: the true limit or the misreading's | yes | separates |
| `stress_rate` | the customer entries scored that day where the misreading gives another limit: the true limit or the misreading's | yes | separates |
| `period_budget` | the budget left against the other budgets' figures (competing reading: the uncut budget); approvals over the budget in force are not enforced, unless only the cut was ignored | yes | separates |
| `budget_notice` | the budget left from the cut's day: with the cut or without it (competing readings: the other budgets); approvals over the cut budget, within the uncut one and with its figures, are not enforced | yes | separates |
| `regulatory_notice` | the customer entries where ignoring the regulator's cut, or applying it from the day its notice arrives, gives another limit: the true limit or that reading's | yes | separates |
| `near_prime_threshold` | the period's near-prime share: under the quota (not told when the other bureau's share is held at the quota, or when the share is held at a lower quota candidate and every higher threshold's share closed some day under the quota), or the share under a stricter threshold held at the quota (*held at a level*: ending at most 4.5 points above it, never under it at a day's close, and closing the first day of lending at most 7 points above it; the first day is not counted under the quota) | yes | separates |
| `near_prime_quota` | the period's near-prime share: under the quota (not told when the other bureau's share is held at the quota, or when a higher threshold's share is held at it and this one closed some day under every lower candidate), or held at a stricter candidate | yes | separates |
| `verified_income` | the customer entries scored that day where the misreading gives another limit: the true limit or the misreading's | yes | separates |
| `income_discrepancy` | the applicants whose discrepancy referral differs between the true threshold and each other candidate (as for the tenure habit) | yes | separates |
| `document_corrections` | each referral whose corrected document arrived: decided again that day or not | yes | separates |
| `repayments` | the customer entries scored that day where the misreading gives another limit: the true limit or the misreading's | yes | separates |
| `split_applications` | each customer-day with several applications and an approval: one approval or more | yes | separates |

**Reliability on other deliverables** (a run's deliverable is neither the reference nor an ablation). Settings where the diagnostic calls the deliverable not enforced, of those where it gives a True or False: the best known solution (valid, built with full knowledge of its setting, so every one would be a false negative), the ablation of the target that also calls other targets not enforced (of the settings where it bites; facts can interact), and the baseline (each setting's own) and `robust_solution` (its tier's), which are informational: neither is built with full knowledge.

| target | best known | cross flags | baseline | robust_solution |
|---|---|---|---|---|
| `gross_income` | 0/45 | 0/45 | 0/45 | 0/45 |
| `policy_bureau` | 0/45 | 0/45 | 0/45 | 26/45 |
| `score_cutoff` | 0/45 | 0/45 | 0/45 | 35/45 |
| `income_cap` | 0/45 | 0/45 | 0/45 | 29/45 |
| `dsr_cap` | 0/45 | 0/45 | 0/45 | 29/45 |
| `our_lending` | 0/45 | 0/45 | 0/45 | 0/39 |
| `daily_cap` | 0/45 | 0/45 | 0/45 | 26/45 |
| `limit_table` | 0/45 | 0/45 | 0/45 | 0/45 |
| `closing_table` | 0/45 | 0/45 | 0/45 | 0/45 |
| `ineligible_zero` | 0/45 | 0/45 | 0/45 | 0/45 |
| `reason_codes` | 0/30 | 0/30 | 0/30 | 6/30 |
| `reason_codes_hard` | 0/15 | 0/15 | 0/15 | 0/15 |
| `protected_attributes` | 0/45 | 0/45 | 0/45 | 45/45 |
| `tenure_review` | 0/45 | 0/45 | 0/45 | 31/45 |
| `branch_notes` | 0/45 | 0/45 | 0/45 | 0/45 |
| `credit_lines_easy` | 0/15 | 0/15 | 0/15 | 15/15 |
| `regulator_notice_easy` | 0/15 | 0/15 | 0/15 | 15/15 |
| `declared_income` | 0/30 | 0/30 | 0/30 | 30/30 |
| `repayments_unused` | 0/30 | 0/30 | 0/30 | 16/30 |
| `credit_line_amortization` | 0/30 | 0/30 | 0/30 | 12/30 |
| `stress_rate` | 0/30 | 0/25 | 0/30 | 12/12 |
| `period_budget` | 0/30 | 0/30 | 0/30 | 19/30 |
| `budget_notice` | 0/30 | 0/30 | 0/30 | 0/11 |
| `regulatory_notice` | 0/30 | 0/30 | 0/30 | 15/30 |
| `near_prime_threshold` | 0/29 | 2/23 (`near_prime_quota`) | 0/4 | 1/6 |
| `near_prime_quota` | 0/29 | 3/21 (`near_prime_threshold`) | 0/4 | 7/12 |
| `verified_income` | 0/15 | 0/15 | 0/15 | 0/15 |
| `income_discrepancy` | 0/15 | 0/15 | 0/15 | 11/15 |
| `document_corrections` | 0/15 | 0/15 | 0/15 | 15/15 |
| `repayments` | 0/15 | 0/15 | 0/15 | 0/9 |
| `split_applications` | 0/15 | 0/15 | 0/15 | 15/15 |

`diagnose()` raised in 0 evaluation(s) of the audit.

**Shortcuts** (closed: invalid, or quality at most 0.5):

| shortcut | what it does | closed in | best quality where valid |
|---|---|---|---|
| `refer_declines` | Refer every application it would decline (bar delinquent ones), so no decline needs a reason code | 45/45 | – |
| `refer_everything` | Refer every application to an underwriter (delinquent ones declined) | 45/45 | – |
| `empty_table` | Decide like the reference but return an empty limit table | 45/45 | – |
| `todays_table` | Decide like the reference but list only the day's applicants in the limit table | 45/45 | – |
| `morning_table` | Decide like the reference but report the limits as they stood before the day's approvals | 45/45 | 0.000 |
| `morning_limits` | Decide like the reference; customer limits as they stood before the day's approvals, bank figures after | 45/45 | 0.320 |
| `jitter_table` | As morning_limits, and every entry moved by 1 every other day, to get static entries scored | 45/45 | 0.320 |
| `zero_table` | Decide like the reference; every customer 0 in the table, the bank figures right | 45/45 | 0.000 |
| `approved_zero` | Decide like the reference; the exact table, except 0 for every customer approved that day | 45/45 | 0.350 |
| `approve_nothing` | Approve nothing: decline with the right codes and report an exact limit table | 45/45 | 0.000 |

**Findings** (as validate-case reads the stored audit with this quality_cap; OPEN_AUDIT_FINDINGS may waive a problem):

- none
