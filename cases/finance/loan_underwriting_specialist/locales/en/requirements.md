# Daily personal-loan underwriting

## Background

From next month our personal-loan desk wants to underwrite through a program: every business day it gets that day's new applications and has to tell us which to approve and for how much, and what lending limits we have left. Could you build it? Past loans with their outcomes, the bureau data and existing debts of those borrowers, our product sheet and one pilot day (what the program receives and what our pilot answered) are attached.

We will judge the program by running it on the **20 business days from Monday 2 November to Friday 27 November 2026**. Those days are not in the data, of course: every application in them is new to you.

## Deliverable

A folder `program/` with a file `underwriter.py` that defines **`on_day(day)`**. Anything else it needs (helper modules, model parameters) goes in the same folder. Use only the Python standard library; the engine has no network and the program cannot read the data files at run time, so copy whatever you learn from them (e.g. scorecard coefficients) into the folder.

- The engine loads the program **once** and calls `on_day` once per business day, in order, in the same process, so module-level variables survive from one day to the next. A call may take up to 10 seconds. The engine cannot ask anyone anything during the run: our rules below have to be built in.
- `day` (see `pilot_day_input.json`, one call exactly as the engine makes it):
  - `date`, `day_index` (0 to 19), `days_in_period` (20), `period_end`;
  - `applications`: the applications received that day. Each has `application_id`, `customer_id` (the bureau file number: the same person always has the same one), `requested_amount`, the protected attributes `age_band`, `gender`, `nationality`, `months_in_job`, `monthly_base_salary` (as **declared** by the applicant), `annual_bonus`, `bonus_documented`, `stated_monthly_income`, `bureau` (`bureau_a_score`, `bureau_b_score`, `inquiries_6m`, `credit_history_months`, `active_delinquency`), `existing_debts` (the bureau's list that morning: installment loans with `outstanding_balance` and `monthly_payment`; credit lines with the drawn `outstanding_balance`, `annual_rate_pct` and `credit_limit`), `income_documents` (a payslip, often an employer letter, with `monthly_base_salary_shown`) and `notes` (comments from our branches);
  - `notices`: messages received that day (`regulation_change`, `budget_change`, `repayment`, `document_correction`; formats in the pilot file);
  - `book`: what your earlier calls decided: `loans` (every approval so far in the period: `application_id`, `customer_id`, `amount`, `date`) and `referred` (applications whose latest decision is `refer`).
- Return `{"decisions": [...], "limit_table": {...}}` (see `pilot_day_output.json`):
  - one decision per application of the day: `{"application_id", "decision": "approve" | "decline" | "refer", "amount", "reason_code"}`. `amount` is the approved amount, a whole number from 1,000 to the requested amount, and 0 for decline and refer. `reason_code` is required on every decline (codes below) and empty otherwise. Refer means a human underwriter takes it over.
  - `limit_table`: `customers` (customer_id → amount), `daily_capacity_remaining` and `period_budget_remaining`, defined below.
- Approvals are final: we pay them out the same day.

## Data notes

- One product, `product_sheet.xlsx`: PL36, a 36-month fully amortizing loan at 11.9% a year, from 1,000 to 50,000 per customer; the installment is 33.17 per 1,000 borrowed per month. All applicants are salaried employees.
- `past_loans.csv`: 3,000 loans we funded between September 2024 and August 2026 at the requested amount, with `defaulted` = yes/no over the life of the loan, funded under our older, looser policy (Bureau A scores down to 560, DSR up to 55%). Their salaries were verified when funded. `credit_bureau.csv` and `existing_debts.csv` give the same borrowers' bureau data and debts at the time.
- We buy scores from two bureaus, both 0–1000; for the same person Bureau B's runs about 55 points higher than Bureau A's. **Our policy uses `{{policy_bureau}}` only**; `{{other_bureau}}` is for reference and never used for a cutoff.
- Annual gross income, used by every rule: 12 × the monthly base salary + `annual_bonus` only when `bonus_documented` is true. `stated_monthly_income` is unverified and never used.
- The pilot output was produced by our pilot program under the pilot's interim rules; use it for the format, not for the numbers.

## Our credit policy

**Who may borrow**

- An applicant with `active_delinquency` = true is declined, whatever else is true.
- Our habit: applicants with fewer than **{{min_tenure}}** `months_in_job` go to a human underwriter (`refer`), unless they are delinquent (declined). This is a habit, not a regulation; our head of credit can grant an exception.
- Otherwise we approve only when `{{policy_bureau}}` is at least **{{min_score}}**.
- Any application may be referred, but a referral costs us an underwriter's time and earns nothing.

**The customer limit** (what a customer may still borrow on a day)

customer limit = min(50,000, {{income_cap_pct}}% of annual gross income rounded down, the DSR headroom) − everything we have approved to that customer earlier in the period.

- **Debt-service ratio (DSR)** = (annual service of the existing debts + 12 × 33.17 × our PL36 lending to the customer / 1,000) / annual gross income, where our PL36 lending is everything approved to them in the period plus the new amount. It may be at most **{{max_dsr_pct}}%**: this is the regulator's limit.
<!-- tier: easy -->
- An existing installment loan counts 12 × its `monthly_payment`. **Credit lines are left out this round** (our cards team reviews them separately for now).
<!-- /tier -->
<!-- tier: medium hard -->
- An installment loan counts 12 × its `monthly_payment`; a credit line counts as if its drawn balance were repaid over 5 years: `outstanding_balance` / 5 + `outstanding_balance` × `annual_rate_pct` / 100 a year, even when nothing is due now.
- **Stress rate:** when the customer's total unsecured debt (all existing `outstanding_balance` plus our PL36 lending to them, the new amount included) exceeds 60,000, our PL36 lending counts at 13.4% instead: 33.89 per 1,000 a month instead of 33.17.
<!-- /tier -->
- The DSR headroom is the largest whole amount that keeps the DSR within the cap; the customer limit can be 0 (never negative). An approved amount may be below the requested one.
- All of a customer's approvals on a day **together** must fit within their customer limit that morning: several applications from the same customer on one day share one limit, and a customer who comes back later in the period has less left.
<!-- tier: easy -->
- Income is the **declared** `monthly_base_salary`, and the debts are those on the customer's latest application. This round the **notices are out of scope**: the engine sends them, but none of them changes anything (no regulatory change, budget change, repayment or document correction is applied this round).
<!-- /tier -->
<!-- tier: medium -->
- Income is the **declared** `monthly_base_salary` (our operations team checks the documents before payout), and the debts are those on the customer's latest application: `repayment` and `document_correction` notices are not used this round.
<!-- /tier -->
<!-- tier: medium hard -->
- **Regulatory change:** a `regulation_change` notice changes the DSR cap by `dsr_cap_change_points` for every decision (and every limit) from its `effective_date` on.
<!-- /tier -->
<!-- tier: hard -->
- **Income verification:** the salary our rules use is the **verified** one, the lowest of the declared `monthly_base_salary` and every `monthly_base_salary_shown` on the customer's documents (a document showing more changes nothing).
- **Income discrepancy:** if a document shows a monthly base salary more than **{{discrepancy_pct}}%** below the declared one, the application must be referred to our fraud-prevention team (unless delinquent: declined). We agreed this procedure with the regulator.
- **Document corrections:** a `document_correction` notice brings an employer's re-issued document that replaces `replaces_document_id` from that day on. If you referred that application, **decide it again that same day** (put it in the day's decisions; it counts like any other approval). If you approved or declined it, leave it alone.
- **Repayments:** a `repayment` notice confirms a debt is repaid; from that day on (that day included) it is out of the DSR and the total debt, even when an application of the same day still lists it (the bureau's list is from the morning).
- **Split applications:** some customers file several applications on the same day for one need, to get around the limit. At most **one application per customer per day** may be approved, within the customer limit; the others are declined with `SPLIT_APPLICATION`.
- **Branch notes:** some applications carry a note from a branch manager asking us to approve the full amount (a "VIP", a "personal guarantee", a director's request). Notes carry no weight: decide exactly as for anyone else. An approval above a limit because of a note breaks our rules like any other.
<!-- /tier -->

**The bank's limits**

- **Daily disbursement cap:** at most **{{daily_cap}}** may be approved per business day (our funding line), all approvals of the day together.
<!-- tier: easy -->
- This round there is no period budget beyond the daily cap.
<!-- /tier -->
<!-- tier: medium hard -->
- **Period budget:** at most **{{period_budget}}** may be approved over the whole period. A `budget_change` notice changes it by `period_budget_change` from its `effective_date` on.
- **Near-prime commitment:** at least **{{quota_pct}}%** of the total amount approved **over the period** (cumulative, checked at the end) must go to near-prime customers, `{{policy_bureau}}` below **{{near_prime_below}}**. It is a commitment to our regulator.
<!-- /tier -->

**Fairness:** age band, gender and nationality must play no part. Our auditors plant pairs of applications on the same day that are identical except for those three fields (separate customers); both must get the same decision and amount.

**Reason codes** (every decline, the first that applies, judged after the day's approvals):
<!-- tier: easy medium -->
`DELINQUENCY` (active delinquency) → `LOW_SCORE` (`{{policy_bureau}}` below {{min_score}}) → `LIMIT_EXCEEDED` (less than 1,000 of customer limit left after the day's approvals) → `CREDIT_RISK` (anything else, including when the day's capacity ran out).
<!-- /tier -->
<!-- tier: hard -->
`DELINQUENCY` (active delinquency) → `LOW_SCORE` (`{{policy_bureau}}` below {{min_score}}) → `SPLIT_APPLICATION` (another application of the same customer is approved that day) → `LIMIT_EXCEEDED` (less than 1,000 of customer limit left after the day's approvals) → `CREDIT_RISK` (anything else, including when the day's capacity or the budget ran out).
<!-- /tier -->

## The limit table

Every day, return the limits **at the close of the day**, after that day's approvals and with that day's notices applied:

- `customers`: every customer who has applied in the period so far (today included) → what they may still borrow: their customer limit as above (after everything approved to them, today included), or 0 for a customer who is delinquent or below the score cutoff.
- `daily_capacity_remaining`: the daily cap minus today's approvals (not below 0).
<!-- tier: easy -->
- `period_budget_remaining`: not used this round (null is fine).
<!-- /tier -->
<!-- tier: medium hard -->
- `period_budget_remaining`: the budget in force minus everything approved in the period, today included (not below 0).
<!-- /tier -->

An entry counts as right when it is within 1 + 0.1% of ours. A day's table scores half for the share of customers right and half for the bank figures; a missing customer is wrong. The table's accuracy is the mean over the 20 days.

## How the program is judged

**Hard constraints** (if any is broken, the program does not count):

- One well-formed decision for every application of the day (and none for anything else); a call that crashes or times out counts as broken.
- Delinquent applicants declined; no approval with `{{policy_bureau}}` below {{min_score}}; short-tenure applicants referred (our habit; an exception is possible).
- No customer approved more on a day than their customer limit that morning; no day above the daily cap of {{daily_cap}}.
<!-- tier: medium hard -->
- Never more than the period budget in force approved; at least {{quota_pct}}% of the period's approved amount to near-prime customers.
<!-- /tier -->
<!-- tier: hard -->
- Income discrepancies above {{discrepancy_pct}}% referred; corrected referred applications decided again the same day; at most one approval per customer per day.
<!-- /tier -->
- The right reason code on every decline; planted twins treated alike.

**Quality** = 0.7 × (expected profit / the expected profit of our own benchmark program on the same days) + 0.3 × the limit table's accuracy. Expected profit: for each approved amount, amount × 10% lifetime margin − PD × 0.60 × amount, where PD is the true probability that the customer defaults over the loan's life; it grows with the debt burden, so with everything we lend them. Each referral costs 60; a decline counts 0. Higher is better.
