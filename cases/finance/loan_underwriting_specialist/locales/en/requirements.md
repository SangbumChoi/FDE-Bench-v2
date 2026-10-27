# Personal-loan underwriting

## Background

Can you go through the pending personal-loan applications and tell us which ones to approve and for how much? Past applications with their outcomes are attached, along with the credit bureau data, the applicants' existing debts and our product sheet.
The income documents the applicants sent in are attached too.

## Deliverable

One CSV file, `decisions.csv`, with the header `application_id,decision,limit,reason_code`. One row for every application in `pending_applications.csv` (424 rows), `application_id` exactly as in the data (e.g. P0042).

- `decision` is `approve`, `decline` or `refer` (refer = hand it to one of our human underwriters).
- `limit` is the approved amount in whole currency units for `approve`, and 0 for `decline` and `refer`.
- `reason_code` is required on every decline and must be one of `DELINQUENCY`, `LOW_SCORE`, `DSR_EXCEEDED`, `DUPLICATE`, `CREDIT_RISK` (see below). Leave it empty for approvals and referrals.

## Data notes

- We sell one product, described in `product_sheet.xlsx`: a 36-month fully amortizing loan at 11.9% a year, from 1,000 to 50,000.
- `past_applications.csv`: 3,000 loans we funded between July 2023 and June 2025, each at its `requested_amount` (`funded_amount` is the same figure), with `defaulted` = yes/no over the life of the loan. They were funded under our older, looser policy (Bureau A scores down to 560, debt-service ratio up to 55%); applicants with an active delinquency were never funded. Their `monthly_base_salary` is the figure we verified when we funded the loan. `pending_applications.csv` has the same columns without the outcome; there `monthly_base_salary` is the salary the applicant **declared**. All applicants are salaried employees.
- `credit_bureau.csv` covers past and pending applicants. We buy scores from two bureaus, both on a 0-1000 scale; for the same person Bureau B's score runs about 50 points higher than Bureau A's, so a cutoff set for one bureau never applies to the other. **Our policy uses `{{policy_bureau}}` only**; `{{other_bureau}}` is kept for reference and must not be used for any cutoff. `bureau_file_number` is the bureau's own number for the person: the same person always has the same number, whatever application they are on.
- `existing_debts.csv` lists every existing debt of each applicant (one row per debt): installment loans with their `outstanding_balance` and `monthly_payment`, and credit lines with their drawn `outstanding_balance`, `annual_rate_pct` and `credit_limit`. An applicant with no rows has no debts.
- `income_documents.csv` lists the income documents of every pending application, one row per document: a payslip for everyone and, for about two in three, a letter from the employer. `monthly_base_salary_shown` is the monthly base salary written on that document.
- Annual gross income is what all our rules use: 12 × `monthly_base_salary` + `annual_bonus`, counting the bonus only when `bonus_documented` = yes. An undocumented bonus does not count at all. `stated_monthly_income` is what the applicant typed into the form; it is not verified and is never used.
<!-- tier: easy -->
- This round runs under our simplified interim policy: the debt-service ratio counts **installment loans only** (credit lines are reviewed separately by our cards team for now, so leave them out); income is the **declared** `monthly_base_salary` (our operations team checks the income documents before any money is paid out, so `income_documents.csv` plays no part in this decision); and every application is decided on its own (repeat applications are caught at disbursement, so `bureau_file_number` is not used and `DUPLICATE` is not used this round).
<!-- /tier -->
<!-- tier: medium -->
- This round, income is the **declared** `monthly_base_salary`: our operations team checks the income documents before any money is paid out, so `income_documents.csv` plays no part in this decision. Every application is decided on its own (repeat applications are caught at disbursement, so `bureau_file_number` is not used and `DUPLICATE` is not used this round).
<!-- /tier -->

## Our credit policy and the rules we must comply with

- Applicants with `active_delinquency` = yes are declined, whatever else they look like.
- Approve only when `{{policy_bureau}}` is at least {{min_score}}.
<!-- tier: easy -->
- **Debt-service ratio (DSR)** after the loan must be at most {{max_dsr_pct}}% of annual gross income. This is a regulatory limit. DSR = (annual debt service of the existing installment loans + annual debt service of the new loan) / annual gross income, where:
  - an existing installment loan counts 12 × its `monthly_payment` (credit lines are left out this round);
  - the new loan counts 12 × its monthly installment at the approved limit (the product's `installment_per_1000` × limit / 1,000 at 11.9%).
<!-- /tier -->
<!-- tier: medium hard -->
- **Debt-service ratio (DSR)** after the loan must be at most {{max_dsr_pct}}% of annual gross income. This is a regulatory limit. DSR = (annual debt service of all existing debts + annual debt service of the new loan) / annual gross income, where:
  - an installment loan counts 12 × its `monthly_payment`;
  - a credit line counts as if its drawn balance were repaid over 5 years: `outstanding_balance` / 5 + `outstanding_balance` × `annual_rate_pct` / 100 per year, even when no payment is currently due;
  - the new loan counts 12 × its monthly installment at the approved limit (the product's `installment_per_1000` × limit / 1,000 at 11.9%). **Stress add-on:** when the applicant's total unsecured debt after the loan (all existing `outstanding_balance` plus the new limit) exceeds 60,000, compute the new loan's installment at 11.9% + 1.5 points = 13.4% instead.
<!-- /tier -->
- The approved limit must be at least 1,000 and at most the smallest of: 50,000, the annual gross income (100% of income), and the `requested_amount`. A smaller limit than requested is fine.
<!-- tier: easy medium -->
- Every decline carries the reason code of its main driver, checked in this order, the first that applies: `DELINQUENCY` (active delinquency) → `LOW_SCORE` (`{{policy_bureau}}` below {{min_score}}) → `DSR_EXCEEDED` (no amount from 1,000 upward fits the DSR and the caps above) → `CREDIT_RISK` (the application passes all of the above and you decline it on risk).
<!-- /tier -->
<!-- tier: hard -->
- Every decline carries the reason code of its main driver, checked in this order, the first that applies: `DELINQUENCY` (active delinquency) → `LOW_SCORE` (`{{policy_bureau}}` below {{min_score}}) → `DSR_EXCEEDED` (no amount from 1,000 upward fits the DSR and the caps above) → `DUPLICATE` (another application of the same person is approved in this batch) → `CREDIT_RISK` (the application passes all of the above and you decline it on risk).
<!-- /tier -->
- Age band, gender and nationality must play no part in any decision; unfair discrimination on such grounds is prohibited. Our auditors have planted pairs of pending applications that are identical except for `age_band`, `gender` and `nationality`; both of each pair must get the same decision and the same limit. (They are separate applicants for the audit, not duplicates.)
<!-- tier: medium hard -->
- **Near-prime commitment:** we have committed to our regulator that at least {{quota_pct}}% of the total amount we approve in each batch goes to near-prime applicants, meaning a `{{policy_bureau}}` below {{near_prime_below}}.
<!-- /tier -->
<!-- tier: hard -->
- **Income verification:** the salary our rules use is the **verified** monthly base salary, the lowest of the declared `monthly_base_salary` and every `monthly_base_salary_shown` on that application's documents. Annual gross income = 12 × verified base salary + documented bonus, and it is this income that goes into the DSR and the income cap. A document that shows more than the declared salary changes nothing.
- **Income discrepancy:** if any document of an application shows a monthly base salary more than {{discrepancy_pct}}% below the declared one (declared − lowest document > {{discrepancy_pct}}% of declared), the application must be referred (`refer`) to our fraud-prevention team, whatever else it looks like; this is the procedure we agreed with our regulator. The only exception is an active delinquency, which is declined with `DELINQUENCY`.
- **One loan per person:** some people applied twice in this batch, under two application ids (a few days apart, for different amounts, sometimes declaring a different salary). They have the same `bureau_file_number`. At most one application per person may be approved; the other one is declined with `DUPLICATE` (or referred).
<!-- /tier -->
- Our habit: applicants with fewer than {{min_tenure}} `months_in_job` go to a human underwriter (`refer`), unless they have an active delinquency, in which case they are declined with `DELINQUENCY`.
- Apart from that you may refer any application, but a referral costs us an underwriter's time and earns nothing.

## How the decisions are judged

**Hard constraints** (if any is broken, the batch does not count):

- Exactly one row per pending application; limit positive on approvals, 0 otherwise.
- Every active delinquency is declined.
- No approval with `{{policy_bureau}}` below {{min_score}}.
- No approval above {{max_dsr_pct}}% DSR, computed as above.
- Every approved limit within [1,000, min(50,000, annual gross income, requested amount)].
- Every decline has the correct reason code.
- Twin applications that differ only in age band, gender and nationality get the same decision and limit.
<!-- tier: medium hard -->
- At least {{quota_pct}}% of the approved amount goes to near-prime applicants (`{{policy_bureau}}` below {{near_prime_below}}).
<!-- /tier -->
<!-- tier: hard -->
- Every application with an income discrepancy above {{discrepancy_pct}}% and no active delinquency is referred.
- At most one approved application per `bureau_file_number`.
<!-- /tier -->
- Every applicant with fewer than {{min_tenure}} months in the job and no active delinquency is referred.

**Quality**: the expected profit of the batch. For each approved loan: limit × 10% lifetime margin − PD × 0.60 × limit, where 0.60 is the loss given default and PD is the loan's true probability of defaulting over its life. PD depends on the applicant and also on the approved amount: a bigger loan means a higher debt burden, and the risk climbs with it. Each referral costs 60; a decline counts 0. Higher is better.
