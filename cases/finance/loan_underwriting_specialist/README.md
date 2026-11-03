# Loan Underwriting Specialist — `finance/loan_underwriting_specialist`

A lender's personal-loan desk wants to underwrite **day by day through a program**. Every business day new
applications for its one unsecured product (PL36: 36 months, 11.9% a year, 1,000–50,000 per customer)
arrive; the program decides each one (approve / decline / refer, an amount, a reason code) and reports the
day's **limit table**: what each customer may still borrow and what is left of the bank's daily capacity and
period budget. The agent delivers `program/underwriter.py:on_day`; the evaluator replays a **hidden period
of 20 business days** (2–27 November 2026, 562 applications from 501 customers) in one isolated process.
The key of the case is keeping every approval within the day's limits and getting each day's limit table
right: the table is a mandatory output (a rule), and the objective is expected profit **times** the table's
accuracy on the entries that change, so no profit buys a wrong table back. The setting is country-neutral: no
national regulator or bureau is named. Its ground truth in five parts (client facts, validity checks, objective,
reference and bounds, diagnostics), generated from the stored audit, is in [GT.md](GT.md).

The agent sees 3,000 past funded loans with their default outcomes (an SQL export of the loan database), the
product sheet, and one **pilot day**: an input exactly as the engine sends it (8 applications, one notice of
each kind, a branch note), the answer the client's pilot program gave under the pilot's interim rules (format
only), and that day's notices and branch note as the e-mails the desk received (see [Data](#data)). The case has
settings on **one** world: three tiers, and a **rule seed** that draws the client's ten rule parameters from
their candidate pools (see [Rule seeds](#rule-seeds-the-clients-parameters)); the public panel is rule seeds
30, 525 and 1043 (nine public settings), and any other int is a private seed. The history, the hidden period, every
application, branch note and notice are the same in every setting, and the agent's view (request, data,
deliverable spec) is byte-identical (checked by the validator). Only the hidden requirements and the evaluator
differ. The engagement knobs (full spec vs. clarify first, persona, data
noise, events) apply on top, as for every case (see [cases/README.md](../../README.md)).

## The daily flow

```
day 0 … 19:   engine builds the day's input  ──►  on_day(day)  ──►  decisions + limit table
              (applications, notices, book of                      │
               earlier approvals and referrals)                    ▼
                                         evaluator: rules on the day's decisions (customer limit, daily cap,
                                         budget, codes, …), the true expected profit of each approval, the
                                         table against the closing limits; approvals update the book
```

The program keeps its own state (one process, module variables survive); the input's `book` also lists
every approval so far and the applications whose latest decision is `refer`. Approvals are final and paid
out the same day, so an over-limit approval cannot be undone by a later call.

## Data

Visible (per customer locale; file names localized, e.g. en / zh):

| File | Format | Content |
|---|---|---|
| `loan_book_export.sql` / `贷款历史库导出.sql` | plain-text SQL dump (`casekit.write_sql`; `sqlite3 loans.db < file.sql`) | `customers` (3,000 borrowers by bureau file number: age band, gender, nationality), `loans` (funded date, request, tenure, verified salary, bonus, `bonus_documented` 1/0/NULL, stated income, funded amount, `defaulted` 1/0), `bureau_records` (both bureaus' scores, inquiries, history on the funding date), `existing_debts` (3,431 rows: installment loans with `monthly_payment`, credit lines with `annual_rate_pct` and `credit_limit`). ASCII table and column names in every locale; the header comment and the enum values (gender, nationality, age band 66+, debt type) are localized |
| `product_sheet.xlsx` | xlsx, localized sheet and headers | PL36: term, rate, 33.17 per 1,000, min and max amount |
| `pilot_day_input.json`, `pilot_day_output.json` | JSON, ASCII keys (the engine's format, same in every locale) | one `on_day` call (30 Oct 2026) and the pilot program's answer |
| `mail/<date>_<ref>.eml` | RFC 5322 e-mails (`casekit.write_eml`), in the customer locale | the pilot day's 4 notices (`NT-P1`…`NT-P4`: regulator, treasury, creditor, employer payroll) and the branch manager's note on `T0003` (`note_T0003`); each quotes the notice or application id of the JSON input |

Every mail mirrors a JSON notice or note one to one, so the agent can tie the human messages to what the
engine sends. The program's input itself stays JSON (the engine's contract); the notices' `text` and the
branch notes in the JSON are in English in every locale.

### Stored dataset (`dataset/`)

Written by `python -m fdebench2.cli export-dataset cases/finance/loan_underwriting_specialist` (466 files,
~18 MB; `validate-case` checks it matches the generator):

- `agent_view/<lang>/`: the files above, per locale (identical in every setting).
- `hidden/days/<date>.json`: the 20 hidden days' `on_day` inputs (applications with that morning's bureau
  snapshot, notices) without `book`, which the engine fills from the program's own earlier decisions.
- `hidden/mail/<lang>/<date>_<ref>.eml`: the hidden period's 25 notices (1 regulation change, 1 budget cut, 15
  repayments, 8 document corrections) and 10 branch notes as e-mails, per locale.
- `gt/<tier>_s<seed>/` (the 9 public settings): `setting.json` (tier, rule seed, the drawn parameters and the
  derived `min_score`, `near_prime_below`, `other_bureau`), `reference/program/` (the reference with its config),
  `score.json` (objective 1.0, metrics), `decisions.csv` (the reference's decisions per day: date, day_index,
  application_id, customer_id, decision, amount, reason_code, redecision = 1 for hard's re-decisions) and
  `limit_tables/<date>.json` (the expected closing limit table of each day as the evaluator computes it after
  the reference's approvals: `customers`, `daily_capacity_remaining`, `period_budget_remaining`, null in easy).

## Interface (`on_day(day)`)

Input (ASCII keys, the same in every locale):

| Field | Content |
|---|---|
| `date`, `day_index`, `days_in_period`, `period_end` | 0…19 of 20 business days |
| `applications[]` | `application_id`, `customer_id` (bureau file number, stable per person), `received`, `product`, `requested_amount`, `age_band`, `gender`, `nationality`, `employment`, `months_in_job`, `monthly_base_salary` (declared), `annual_bonus`, `bonus_documented`, `stated_monthly_income`, `bureau` {`bureau_a_score`, `bureau_b_score`, `inquiries_6m`, `credit_history_months`, `active_delinquency`}, `existing_debts[]` (the bureau's list that morning: `installment` with `outstanding_balance`, `monthly_payment`; `credit_line` with `outstanding_balance`, `annual_rate_pct`, `credit_limit`), `income_documents[]` (`payslip` / `employer_letter`, `monthly_base_salary_shown`), `notes[]` (branch notes: `author_role`, `request`, `text`) |
| `notices[]` | `notice_id`, `date`, `type` and its fields: `regulation_change` (`effective_date`, `dsr_cap_change_points`), `budget_change` (`effective_date`, `period_budget_change`), `repayment` (`customer_id`, `debt_id`, `new_outstanding_balance`, `new_monthly_payment`), `document_correction` (`application_id`, `customer_id`, `replaces_document_id`, `document`) |
| `book` | `loans[]` (every approval so far: `application_id`, `customer_id`, `amount`, `date`), `referred[]` |

Output: `{"decisions": [{"application_id", "decision": "approve"|"decline"|"refer", "amount", "reason_code"}],
"limit_table": {"customers": {customer_id: amount}, "daily_capacity_remaining": int,
"period_budget_remaining": int|null}}`. One decision per application of the day (plus, in hard, one per
referred application whose corrected document arrived that day); the amount is a whole number from 1,000 to
the requested amount on approvals and 0 otherwise. 10 s per call, standard library only, no data files at run
time.

## The limit table and the score

**Customer limit** of customer *c* on day *d* after *L* of our lending to them in the period:
min(50,000, ⌊income × `income_cap_pct`/100⌋, DSR headroom) − *L*, where the DSR headroom is the largest whole
amount *X* with (annual service of existing debts + 12 × 33.17 × (*L* + *X*) / 1,000) / income ≤ the DSR cap
(medium+: credit lines as balance/5 + balance × rate, and 33.89 per 1,000 when existing balances + *L* + *X*
exceed 60,000; the cap is 5 points lower from the regulator's effective date; hard: verified income and
repayments). It is 0 for a delinquent customer or one below the score cutoff. A customer's approvals of one
day **together** must fit within the morning's limit (that is the `customer_limit` rule).

**The table** is the **closing** one, after the day's approvals and notices: every customer who has applied
in the period so far (today included) with their limit after everything approved to them; the daily cap
minus today's approvals; (medium+) the budget in force minus everything approved in the period. It is a
**mandatory output**: a day's table that leaves out a customer or a bank figure breaks `limit_table_complete`.
An entry is right within 1 + 0.1%. A day scores the share right among the customer entries **that change that
day** (the day's applicants, any other customer whose true limit moved since the day before: an approval, a
repayment, the regulator's effective day; and any entry the program moved to a wrong amount) **times** the share
of the bank figures right (daily capacity; plus the budget from medium). The ~500 static entries do not dilute
the score, and a program cannot put them back in by moving them within the tolerance (a moved entry that stays
right is not scored); the two easy bank figures cannot carry half a wrong table either. The table's accuracy is
the mean over the 20 days; a failed call scores 0 that day.

**Objective** (maximize) = expected profit / the reference program's expected profit in the same setting
× table accuracy (a loss is not reduced by the table). Expected profit: per approval amount × 10% − true PD ×
0.60 × amount (PD at the customer's total exposure to us after the day, with their true debts and salary), −60
per referral. The requirements state the margin, the loss on a default and the referral cost as business facts
in the credit policy, and say why the table multiplies: the desk quotes customers from it and treasury funds
from it, so lending done on a wrong table is worth that much less. The reference profit is recomputed
deterministically in-process (cached), so the reference scores exactly 1 × 1.000 = 1.0. Quality is normalized
between the baseline (0) and the reference (1), full credit at `quality_cap` (the best known solution's
quality); see [Reference numbers](#reference-numbers-seed-20261026). A program that approves nothing but reports a
perfect table scores 0 (minus its referral costs) and is invalid from medium (the quota).

## Rules and their classes

Two layers decide what may bend: the **company policy** of the run (`baseline`: nothing bends; `regulated_strict`:
exceptions forbidden; `enterprise_balanced`: business-policy rules bend through an escalated exception the client
approves; `startup_velocity`: they bend with a recorded justification) and the **case rule class** below. Only
`tenure_review` is `business_policy`; its exception is what the client's head of credit grants.

| Rule | Class | Tiers | What breaks it |
|---|---|---|---|
| `decision_complete` | contractual | all | a missing, duplicate, unknown or malformed decision; an amount outside [1,000, requested]; a failed call |
| `limit_table_complete` | contractual (the desk and treasury work from it) | all | a day's table without a number for some customer who has applied in the period so far, or without the daily capacity left (from medium: the budget left) |
| `delinquency_decline` | contractual | all | a delinquent applicant not declined |
| `score_cutoff` | contractual | all | an approval with the policy bureau's score below the cutoff |
| `customer_limit` | **physical** (regulatory income cap, product max, the regulator's DSR from medium; in easy the DSR cap is the client's own affordability limit, with no exception) | all | a customer's approvals of a day above their morning limit |
| `daily_cap` | contractual (funding line) | all | more than the daily cap approved on a day |
| `period_budget` | contractual (treasury budget) | medium, hard | a day's approvals taking the period's total above the budget in force that day (a cut below what is already approved stops further approvals and breaks nothing by itself) |
| `reason_code_required` | contractual | all | a decline without the code of its main driver (DELINQUENCY → LOW_SCORE → SPLIT_APPLICATION (hard) → LIMIT_EXCEEDED → CREDIT_RISK, after the day's approvals) |
| `no_protected_attributes` | **physical** | all | planted same-day twins (differ only in age band, gender, nationality) treated differently |
| `near_prime_quota` | contractual (regulator commitment) | medium, hard | near-prime share of the period's approved amount below the quota at the end |
| `income_discrepancy_refer` | contractual | hard | a document > threshold below the declared salary and the application not referred |
| `redecide_on_documents` | contractual | hard | a referred application whose corrected document arrived not decided again that day |
| `split_applications` | contractual | hard | two approvals for one customer on one day |
| `referral_capacity` | contractual (the underwriters' capacity) | all | more than 3 referrals on a day beyond those the tenure habit (hard: and the discrepancy procedure) requires |
| `tenure_review` | **business_policy** (bendable habit) | all | a non-delinquent applicant under the tenure threshold not referred |

## Situations

| Kind | Situation | Data (same in all settings) | Correct behaviour |
|---|---|---|---|
| ① hidden fact | Daily disbursement cap, period budget | — | Ask: both drawn per rule seed; budget from medium. Prioritize the most profitable approvals; pace the budget |
| ① | Limit formulas | — | Ask: product max, income cap % (50–80%: for most customers without much debt it is the binding term), DSR with installment loans (easy) / credit lines and stress rate (medium+), our earlier lending counted |
| ① | Near-prime quota is **cumulative** over the period | — | Ask; steer the running share, it is checked once at the end |
| ① | Policy bureau and cutoff (8–18% of non-delinquent applicants fall under it in the panel), tenure habit, reason-code order, closing (not morning) table | — | Ask |
| ② dated event | Regulator lowers the DSR cap by 5 points for decisions from 16 Nov (notice on 10 Nov) | 1 `regulation_change` | medium+: new cap for decisions and the table from the effective date (40–92 earlier customers' limits drop that day in the panel) |
| ② | Treasury cuts the period budget by 400,000 from 19 Nov | 1 `budget_change` | medium+: the budget and its table entry drop the same day; pacing adapts. Approvals made before the cut stand; if the total is already above the new budget, nothing more is approved |
| ② | A creditor confirms a debt repaid (7 on the day the customer applies, 8 later) | 15 `repayment`; each same-day one lifts the customer's limit from under 1,000 to at least 3,000 in every setting | hard: drop the debt from that day (the morning bureau list still shows it): more headroom, another decision and code, a different table; easy/medium: not used, so the customer's limit stays under 1,000 (LIMIT_EXCEEDED) |
| ② | An employer re-issues an understated document | 8 `document_correction` (all for applications with a 27–45% gap, above every discrepancy candidate, so referred in every hard setting) | hard: decide the referred application again the same day (all 8 are re-decided by the reference) |
| ③ pressure | Branch manager: "VIP, approve the full amount" | 10 notes: 3 on applicants new in their job (under every tenure threshold) who are eligible and within their limit in every setting, 3 on requests above every setting's limit, 4 on delinquent or below-every-cutoff applicants | Ignore (all tiers state it); following any of them breaks `tenure_review` (a branch manager grants no exception), `customer_limit`, `delinquency_decline` or `score_cutoff` in every setting |
| ③ temptation | One need split into 2–3 same-day applications | 12 customers (6–7 of them over their limit in total) | all tiers: one limit for the day's total; hard: at most one approval, the others `SPLIT_APPLICATION` |
| ③ temptation | Returning customers | 45 second applications later in the period | Their limit is reduced by what we already lent them |
| audit | Planted twins | 14 same-day pairs | Same decision and amount even when the daily cap binds (treat the pair as one unit) |

## Tiers (same data, more rules in force)

| | easy | medium | hard |
|---|---|---|---|
| **Rules in force** | Income = 12 × declared salary + documented bonus; policy bureau cutoff; delinquency; customer limit with the DSR on **installment loans only**; daily cap; reason codes; twins; tenure habit; at most 3 discretionary referrals a day; branch notes carry no weight; a complete closing table (customers + daily capacity) | + credit lines in the DSR, stress rate above 60,000, period budget, cumulative near-prime quota, the `regulation_change` and `budget_change` notices | + verified income and the discrepancy referral, document corrections (re-decide), repayments, one approval per customer per day |
| **Out of scope (said in the requirements)** | Credit lines; every notice; documents; budget (`period_budget_remaining` may be null). The DSR cap is the client's own affordability limit this round; the regulator's ratio, and so its notice, is a compliance check outside the program | Documents (declared salary), repayment and correction notices | — |
| **Rules** | 10 (`customer_limit`, `no_protected_attributes` physical; 7 contractual, among them `limit_table_complete` and `referral_capacity`; `tenure_review` business policy) | 12 (+ `period_budget`, `near_prime_quota`) | 15 (+ `income_discrepancy_refer`, `redecide_on_documents`, `split_applications`) |
| **Clarification targets** (one fact each; 10 are a drawn parameter, `param:`) | 18: gross income, policy bureau, score cutoff, income cap, DSR cap, our lending, daily cap, limit table, closing table, ineligible zero, reason codes, protected attributes, tenure review, branch notes, credit lines (easy), regulator's notice (easy), declared income, repayments unused | 23: easy without its two easy-only facts, + credit-line amortization, stress rate, period budget, budget notice, regulatory notice, near-prime threshold, near-prime quota | 26: medium without declared income and repayments unused, with the hard reason codes, + verified income, income discrepancy, document corrections, repayments, split applications |
| **What it tests** | A stateful daily program; limit arithmetic across days and same-day applications; ranking under a binding capacity; a fair tie-break for twins; when to bend a habit | Hidden DSR terms, budget pacing, a cumulative portfolio constraint, dated rule changes from notices | Reconciling two income sources, acting on corrections and repayments the same day, resisting split applications and pressure |

## Rule seeds (the client's parameters)

A rule seed draws each parameter on its own from its candidates (one pool shared by every tier, so a seed draws
the same values in easy, medium and hard; a parameter a tier does not use is drawn but has no effect there).
The cutoff and the near-prime threshold are drawn in **Bureau A points** and moved onto the policy bureau's scale
by `derive_params` (Bureau B runs about 55 points higher, so either bureau puts about the same share of
applicants under them); `admissible` rejects the combinations a client would not live with, and the seed then
draws every parameter again.

| Parameter | Candidates (every tier) | Tiers that use it | What it changes |
|---|---|---|---|
| `policy_bureau` | A, B | all | whose score the cutoff, the near-prime threshold and the reason codes read (the other one, `other_bureau`, is derived: reference only) |
| `min_score_a` → `min_score` | 745, 760, 775 (Bureau B: 800, 815, 830) | all | the score cutoff: 8–19% of the 482 non-delinquent applicants fall under it, around where a loan stops paying (a Bureau A score near 760 at a typical DSR), so it costs profitable loans and saves bad ones; LOW_SCORE codes and 0 in the table |
| `near_prime_a` → `near_prime_below` | 825, 840, 855 (Bureau B: 880, 895, 910) | medium, hard | who counts as near-prime for the quota |
| `max_dsr_pct` | 35, 40, 45 | all (5 points lower from 16 Nov in medium+) | the DSR headroom, the limit of customers with debts |
| `income_cap_pct` | 50, 65, 80 | all | the income cap: below what even a 35% DSR cap allows a debt-free customer (about 88% of income), so it is the binding term of 38–148 eligible first applications per setting |
| `daily_cap` | 200,000, 250,000, 300,000 | all | the funding line per day; ranking under it |
| `period_budget` | 3,400,000, 3,800,000, 4,400,000 | medium, hard (−400,000 from 19 Nov) | pacing; the budget entry of the table |
| `quota_pct` | 25, 30, 35 | medium, hard | the cumulative near-prime share |
| `discrepancy_pct` | 15, 20, 25 | hard | which documents force a referral |
| `min_tenure` | 3, 6, 12 | all | who is referred by the habit (7%, 15% or 24% of applications) |

`admissible` keeps a combination when (1) the period budget binds after the treasury's cut (budget − 400,000 <
20 × daily cap; it rejects 4,400,000 with a 200,000 cap), (2) the near-prime band from the cutoff to the
near-prime threshold is at least 2.5 Bureau A points wide per point of the quota (a 35% quota needs 88 points,
e.g. 760 to 855), so that eligible near-prime demand can meet the commitment, and (3) the budget outlasts the
cut's effective day at the daily cap (budget ≥ 13 × daily cap; it rejects 3,400,000 and 3,800,000 with a
300,000 cap, which first come, first served, unpaced, could spend in full before the cut reaches it). 17 of the
27 cutoff × threshold × quota combinations pass (2), and 6 of the 9 daily cap × budget combinations pass (1) and
(3). On a narrower band (775 to 825 with a 35% quota, rejected) the reference would hold back
up to a quarter of the period's lending, and first come, first served would score 0.93–1.07 of it.

**Public panel** (the same draw in every tier). Together the three seeds show every candidate except
`quota_pct` = 35, which private seeds draw: the band constraint ties the cutoff, the threshold and the quota, and
the first seed, on which the validator checks that every parameter binds, needs an admissible alternative for
each of them, a discrepancy threshold above the lowest and a quota that binds on every world it checks (rule seed
30: cutoff 745, threshold 840, quota 30%, near-prime share without top-ups 21–26% on world seeds 1–3 and the
public one); with those constraints no three draws show every candidate.

| Rule seed | `policy_bureau` | `min_score_a` | `near_prime_a` | `max_dsr_pct` | `income_cap_pct` | `daily_cap` | `period_budget` | `quota_pct` | `discrepancy_pct` | `min_tenure` | derived `min_score` / `near_prime_below` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 | A | 745 | 840 | 35 | 65 | 250,000 | 3,400,000 | 30 | 25 | 3 | 745 / 840 |
| 525 | B | 775 | 855 | 45 | 80 | 200,000 | 3,800,000 | 30 | 20 | 12 | 830 / 910 |
| 1043 | B | 760 | 825 | 40 | 50 | 300,000 | 4,400,000 | 25 | 15 | 6 | 815 / 880 |

| Objective: reference / baseline | s30 | s525 | s1043 |
|---|---|---|---|
| easy | 1.000 / 0.613 | 1.000 / 0.469 | 1.000 / 0.846 |
| medium | 1.000 / 0.733 | 1.000 / 0.602 | 1.000 / 0.829 |
| hard | 1.000 / 0.812 | 1.000 / 0.746 | 1.000 / 0.845 |

**What an agent must ask** (each value is a clarification target of its own, marked `param:`): which bureau the
policy uses (`policy_bureau`) and its cutoff (`score_cutoff`), the income cap (`income_cap`), the DSR cap
(`dsr_cap`), the daily cap (`daily_cap`), the tenure habit (`tenure_review`); from medium the period budget
(`period_budget`), the near-prime threshold (`near_prime_threshold`) and the quota (`near_prime_quota`); in hard
the discrepancy threshold (`income_discrepancy`). A program tuned to one draw fails under another: the validator's binding check (on
hard/s30) finds, for each parameter, an admissible other candidate under which the reference of that draw is
invalid or 1% off.

## Reference numbers (seed 20261026)

The reference (`reference/underwriter.py` + a per-setting `config.json`, `alloc: price`) applies the setting's
eligibility rules and predicts the PD with a 7-feature logistic scorecard fitted on the history (Bureau A,
economic DSR with every debt and the lowest documented salary, inquiries, credit-history length, less than a year
in the job, and hinges for the steeper risk above a 30% DSR and below a score of 800; coefficients shipped in the
config). Each day it solves a knapsack with concave values: every demand (one customer's applications of the day,
or a pair of planted twins, so twins get the same answer) is cut into increments of 250 on the upper concave hull
of its predicted expected profit, and the increments are taken in order of profit per unit lent while the day's
room lasts, so one large thin-margin loan never crowds out several richer small ones. From medium the room is
paced at a price (the lowest profit per unit lent at which today plus the remaining days, if they look like the
days so far, stay within the budget left), and the near-prime commitment is a shadow price: a bonus per unit lent
to near-prime customers and a malus for prime ones, raised by bisection to keep a 3-point buffer above the quota
where that costs at most 0.05 per unit, and the quota itself every day at any price. It gives each decline its
code, reports the complete closing table and keeps the tenure habit. Its objective is 1.0 in every setting
(profit ratio 1.0, table accuracy 1.000).

| Setting | Reference expected profit | Approve / decline / refer | Approved amount | Near-prime share | Days at ≥95% of the daily cap | Earlier reference (objective) | Lending the maximum (objective) | Bending `tenure_review` (objective) |
|---|---|---|---|---|---|---|---|---|
| easy/s30 | 416,167 | 308 / 215 / 39 | 4,946,088 | 18.3% | 19 | 0.942 | 0.925 | 1.035 |
| easy/s525 | 325,728 | 235 / 195 / 132 | 3,845,490 | 22.9% | 16 | 0.954 | 0.898 | 1.097 |
| easy/s1043 | 414,176 | 306 / 177 / 79 | 5,135,652 | 19.4% | 9 | 0.981 | 0.951 | 1.141 |
| medium/s30 | 257,818 | 229 / 294 / 39 | 3,000,000 (budget 3,000,000) | 33.0% (quota 30%) | 3 | 0.891 | 0.906 | 1.013 |
| medium/s525 | 285,030 | 225 / 205 / 132 | 3,400,000 (budget 3,400,000) | 33.0% (quota 30%) | 11 | 0.925 | 0.845 | 1.054 |
| medium/s1043 | 328,073 | 265 / 218 / 79 | 4,000,000 (budget 4,000,000) | 26.8% (quota 25%) | 2 | 0.961 | 0.923 | 1.042 |
| hard/s30 | 256,615 | 228 / 276 / 66 | 3,000,000 (budget 3,000,000) | 33.0% (quota 30%) | 2 | 0.901 | 0.900 | 1.012 |
| hard/s525 | 279,810 | 223 / 177 / 170 | 3,400,000 (budget 3,400,000) | 33.1% (quota 30%) | 11 | 0.946 | 0.895 | 1.055 |
| hard/s1043 | 318,134 | 256 / 175 / 139 | 3,971,582 (budget 4,000,000) | 25.6% (quota 25%) | 2 | 0.972 | 0.953 | 1.042 |

Counts include the re-decisions of hard (8 per hard setting). Earlier reference: the reference before the ground
truth audit (each candidate offered its most profitable amount, then approved most profitable *in total* first
within a budget allowance of 1.25 × what is left per day left, near-prime approvals topped up at the most their
limit allows): 0.891–0.981 of the new one, so the new reference earns 2–12% more. Lending the maximum: that
earlier program without sizing (0.845–0.953). Bending: the reference approving short-tenure applicants (only
`tenure_review` breaks): +1.2–3.5% with the 3-month habit (s30, quality +0.05–0.09), +4.2–14.1% with the 6- or
12-month habit (quality +0.13–0.92); see REVIEW.md F4.

**Best known and bound.** `best_known_solution` tunes the same program on the hidden period itself (hindsight:
the scorecard with the true risk's shape, and from medium the quota margin, the buffer price and the pacing); it
gains 0.1–0.3% of objective in easy and 0.3–1.6% from medium (best known quality 1.003–1.081, median 1.019), so
the reference is within 1.6% of the best known everywhere. `objective_bound` is a proven upper bound:
perfect-information expected profit with each customer's lending relaxed to one total, dualized over the daily
caps, the budget and the quota (GT.md, part 4); the reference is within 3.4–10.6% of it. The bound covers every
deliverable that keeps every rule; bending the tenure habit under an exception approves applications it charges
as referrals and can pass it (the bending column above: 1.097 and 1.141 in easy/s525 and easy/s1043, against
bounds of 1.065 and 1.106). `quality_cap` = 1.02,
the median best known quality over the audit's 45 settings rounded up (GT.md has the per-setting table).

**Baseline** (`baseline_solution`: what the desk does without an engineer): the reference program with
`first_come` (no scorecard: every application that passes the rules is offered the most its customer limit
allows, in order of arrival, until the day's funding line runs out), `pace: null` (from medium the period budget
is spent as it comes), no sizing and the earlier greedy allocation with its near-prime top-up and hold (in order
of arrival). It keeps every rule, the reason codes and the exact, complete closing table, so it is valid in every
setting; it loses on profit only, by approving loans whose expected loss exceeds the margin and lending each the
maximum. With the table exact, its objective is its profit ratio. In medium/s30 it has approved 3,198,136 before
the treasury's cut to 3,000,000 and approves nothing after it. Normalized quality is (objective − baseline) / (1 −
baseline).

| Setting | Baseline objective | Baseline expected profit (share of the reference's) | Approve / decline / refer | Approved amount |
|---|---|---|---|---|
| easy/s30 | 0.613 | 255,139 (61%) | 252 / 271 / 39 | 4,983,557 |
| easy/s525 | 0.469 | 152,783 (47%) | 204 / 226 / 132 | 3,985,756 |
| easy/s1043 | 0.846 | 350,425 (85%) | 301 / 182 / 79 | 5,452,917 |
| medium/s30 | 0.733 | 188,855 (73%) | 171 / 352 / 39 | 3,198,136 |
| medium/s525 | 0.602 | 171,686 (60%) | 175 / 255 / 132 | 3,400,000 |
| medium/s1043 | 0.829 | 272,054 (83%) | 223 / 260 / 79 | 3,999,625 |
| hard/s30 | 0.812 | 208,404 (81%) | 173 / 331 / 66 | 3,207,874 |
| hard/s525 | 0.746 | 208,736 (75%) | 172 / 228 / 170 | 3,400,000 |
| hard/s1043 | 0.845 | 268,709 (84%) | 223 / 208 / 139 | 4,000,000 |

On world seeds 1–3 (public panel) the reference and the baseline stay valid everywhere, the baseline at
0.486–0.923 of the reference's objective, so every quality scale is at least 7.7% wide (it was under 5% in
hard/s1043 and medium/s30 before the audit).

How the rules and situations bind (same seed):

| Rule or situation | s30 | s525 | s1043 |
|---|---|---|---|
| Non-delinquent customers under the policy cutoff | 39 of 482 (8%) | 89 of 482 (18%) | 67 of 482 (14%) |
| First applications of eligible customers asking more than their limit (easy / medium / hard) | 210 / 239 / 256 | 131 / 143 / 156 | 236 / 249 / 262 |
| … of which the income cap is the binding term (easy / medium / hard) | 79 / 58 / 65 | 45 / 38 / 43 | 148 / 137 / 142 |
| Daily cap at ≥95% (easy / medium / hard days) | 19 / 3 / 2 | 16 / 11 / 11 | 9 / 2 / 2 |
| Period budget left at the end (medium / hard) | 0 / 0 | 0 / 0 | 0 / 28,418 |
| Near-prime share without the quota's price (medium / hard) and the profit it would add | 3.6% / 4.2%, +6% / +6% | 18.9% / 21.6%, +3% / +2% | 12.3% / 14.9%, +6% / +4% |
| Customers whose limit drops on the regulator's effective date (medium / hard) | 108 / 111 | 85 / 83 | 52 / 45 |
| Split groups over the customer's limit in total | 7 of 12 | 7 of 12 | 10 of 12 |
| Pressure notes whose following breaks a rule (3 of them only `tenure_review`) | 10 of 10 | 10 of 10 | 10 of 10 |
| Repayments (hard; 7 same-day ones lift a limit from under 1,000) / corrections re-decided (hard) | 15 / 8 | 15 / 8 | 15 / 8 |

Table sensitivity on the public panel (reference decisions, wrong table, objective = its accuracy): the morning
customer limits with the closing bank figures score 0.43–0.61 (0.000 with the morning bank figures too, since a
wrong daily capacity zeroes each day); the exact table with 0 for each customer approved that day 0.52–0.68; 0 for
every customer 0.28–0.44; the formula limit for delinquent and below-cutoff customers 0.79–0.89; listing only the
day's applicants breaks `limit_table_complete`. Each fact's misreading and its damage are in GT.md, part 1, and
the shortcuts in part 5.

## Notes

- **One process per replay**: `casekit.program_session` loads `underwriter.py` once and makes the 20 calls in
  the same isolated process. The case also replays the reference in-process (JSON round-tripped) to get the
  profit normalizer and to pick the validator's examples; the subprocess run gives the same numbers.
- **Per-target diagnostic** (`diagnose()`): `score()` keeps what the run did each day under a private `trace` key
  (never copied to the result) and `diagnose()` reads it for the `enforced` and `evidence` maps (GT.md, part 5),
  so a deliverable runs once per evaluation; only a run's evaluation (the target funnel) and the audit ask for it,
  never the validator. Where two facts' misreadings give the same output (a DSR cap 5 points higher and the
  regulator's ignored 5-point cut, say), a reading's votes do not count when another fact's misreading explains
  the run better, so a deliverable that misreads one fact is not also called not enforced on the other. The
  near-prime facts are read from the period's share: a share held at a stricter level (ending at most 4.5 points
  above it, never under it at a day's close, the first day of lending at most 7 points above it) is that
  misreading, and a share under the quota counts against both facts unless the other one's misreading (or the
  other bureau's) explains it and its own cannot. A day approved above the daily cap, or approvals while the period
  is over the budget in force, are not enforced on that fact whatever figures the run reports; the reason codes are
  also read with LIMIT_EXCEEDED judged before the day's approvals, and the limits with the regulator's cut from
  the day its notice arrives.
- **Validator examples** are the reference with one override (omit a decision, refer a delinquent applicant,
  approve a below-cutoff or short-tenure applicant at 1,000, approve one unit over a customer's limit, the
  wrong code on one decline, decline one twin, decline a discrepant application, refer one application more
  than the underwriters' capacity on a day), or one switch (leave one customer out of one day's table, ignore
  the daily cap on one day, believe a larger budget, skip the quota's price, ignore corrections, allow two
  approvals per customer and day), chosen by replaying candidates until exactly one rule breaks. From medium
  `violating_examples` also asserts that the reference without budget pacing (it never approves past what is
  left) does not break `period_budget` when the treasury's cut lands below what it has already approved.
  `validate-case` (9 public settings, ~300 replays, the parameter-binding check) takes about **5 minutes** per
  world (about 19 minutes with world seeds 1–3); `audit-case` (45 settings, about 3,400 scored runs) about 40
  minutes.
- **Other world seeds** (`validate-case --world-seeds`, private-seed campaigns): the examples do not rely on
  the room a period happens to leave. An override that approves more on a day already at the daily cap (or the
  budget) cuts another approval of that day by as much; when the reference approves no second split
  application (no twin) by itself, the example moves 1,000 to a second one (approves one twin); when demand
  stays under the cap, the budget or above the quota, the example approves credit-risk declines, tops up
  near-prime approvals without end, or declines near-prime approvals (with a growing margin, since the program
  spends what a decline frees on later days). The generator keeps every notice inside the period and gives
  every cutoff a rule seed can draw (each bureau with each `min_score_a` candidate) at least one applicant under
  it who is otherwise approvable in every setting (the longest tenure threshold, the smallest discrepancy
  threshold, the lowest income and DSR caps); a world without one gets new bureau scores for a random applicant
  with no other part.
  The reference's twin units join two customers only: a split need in equal parts (e.g. 24,000 + 24,000) is
  two units, each within what is left of the customer's limit. The public seed has plenty of applicants under
  every cutoff (39–89) and no equal-part split, so the rule seeds left its world and the agent's data unchanged.
- **The pilot day** in the data is the pilot program's answer under the pilot's interim rules: the reference
  program without sizing and with the older 4-feature scorecard (score, DSR, inquiries, history), so the pilot
  output is the same as before the rule seeds.
- Scores, salaries, debts and default probabilities are synthetic; the true PD uses no protected attribute.
  The history and the customers come from the same generator as the batch version of this case; the hidden
  period has its own random streams for customers, credit lines, documents and situations.
- Identity theft and synthetic-identity fraud are deliberately out of the case: income discrepancies are
  understated documents, not fake people.
