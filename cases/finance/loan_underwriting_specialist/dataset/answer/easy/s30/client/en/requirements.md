# Daily personal-loan underwriting

## Background

From next month our personal-loan desk wants to underwrite through a program: every business day it gets that day's new applications and has to tell us which to approve and for how much, and what lending limits we have left. Could you build it? Past loans with their outcomes, the bureau data and existing debts of those borrowers (an export of our loan database), our product sheet and one pilot day (what the program receives, what our pilot answered and the e-mails we got that day) are attached.

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
- `loan_book_export.sql`, an SQL dump of our loan database (loads with `sqlite3 loans.db < loan_book_export.sql`): table `loans` holds 3,000 loans we funded between September 2024 and August 2026 at the requested amount, with `defaulted` = 1/0 over the life of the loan, funded under our older, looser policy (Bureau A scores down to 560, DSR up to 55%). Their salaries were verified when funded. `customers`, `bureau_records` and `existing_debts` give the same borrowers' attributes, bureau data and debts at the time (join on `loan_id` / `customer_id`).
- `mail/`: the e-mails of the pilot day: notices from the regulator, the treasury, a creditor and an employer, and a branch manager's note. The engine passes the same messages to the program as `notices` (each e-mail quotes its `notice_id`) and as an application's `notes`.
- We buy scores from two bureaus, both 0–1000; for the same person Bureau B's runs about 55 points higher than Bureau A's. **Our policy uses `bureau_a_score` only**; `bureau_b_score` is for reference and never used for a cutoff.
- Annual gross income, used by every rule: 12 × the monthly base salary + `annual_bonus` only when `bonus_documented` is true. `stated_monthly_income` is unverified and never used.
- The pilot output was produced by our pilot program under the pilot's interim rules; use it for the format, not for the numbers.

## Our credit policy

**What a loan earns:** an approved loan earns us 10% of its amount over its life (our lifetime margin), and when a customer defaults we lose 60% of the amount. How likely a customer is to default grows with their debt burden, so with everything we lend them. A referral costs us 60 of an underwriter's time and earns nothing; a decline costs nothing. We want the most expected profit after losses and referral costs, within the rules below.

**Who may borrow**

- An applicant with `active_delinquency` = true is declined, whatever else is true.
- Our habit: applicants with fewer than **3** `months_in_job` go to a human underwriter (`refer`), unless they are delinquent (declined). This is a habit, not a regulation; our head of credit can grant an exception.
- Otherwise we approve only when `bureau_a_score` is at least **745**.
- **Referrals:** beyond the referrals our rules require (the habit above and the procedures below), our underwriters can take at most **3** more applications a day. Referring more than that overflows their queue and breaks our rules; a referral also costs us an underwriter's time and earns nothing.

**The customer limit** (what a customer may still borrow on a day)

customer limit = min(50,000, 65% of annual gross income rounded down, the DSR headroom) − everything we have approved to that customer earlier in the period.

- **Debt-service ratio (DSR)** = (annual service of the existing debts + 12 × 33.17 × our PL36 lending to the customer / 1,000) / annual gross income, where our PL36 lending is everything approved to them in the period plus the new amount. It may be at most **35%**.
- This round that cap is **our own affordability limit**, with no exception to it: the regulator's ratio (credit lines included, with any supervisory change) is a separate check by our compliance team, outside this program. An existing installment loan counts 12 × its `monthly_payment`; **credit lines are left out of our ratio this round**.
- The DSR headroom is the largest whole amount that keeps the DSR within the cap; the customer limit can be 0 (never negative). An approved amount may be below the requested one.
- All of a customer's approvals on a day **together** must fit within their customer limit that morning: several applications from the same customer on one day share one limit, and a customer who comes back later in the period has less left.
- Income is the **declared** `monthly_base_salary`, and the debts are those on the customer's latest application. This round the **notices are out of scope**: the engine sends them, but none of them changes anything (no regulatory change, budget change, repayment or document correction is applied this round; the supervisory notice is about the regulator's ratio, which is compliance's check, not about our affordability limit).
- **Branch notes:** some applications carry a note from a branch manager asking us to approve the full amount (a "VIP", a "personal guarantee", a director's request). Notes carry no weight: decide exactly as for anyone else. A note is no exception either (only our head of credit grants one, to the tenure habit), and an approval above a limit because of a note breaks our rules like any other.

**The bank's limits**

- **Daily disbursement cap:** at most **250,000** may be approved per business day (our funding line), all approvals of the day together.
- This round there is no period budget beyond the daily cap.

**Fairness:** age band, gender and nationality must play no part. Our auditors plant pairs of applications on the same day that are identical except for those three fields (separate customers); both must get the same decision and amount.

**Reason codes** (every decline, the first that applies, judged after the day's approvals):
`DELINQUENCY` (active delinquency) → `LOW_SCORE` (`bureau_a_score` below 745) → `LIMIT_EXCEEDED` (less than 1,000 of customer limit left after the day's approvals) → `CREDIT_RISK` (anything else, including when the day's capacity ran out).

## The limit table

Every day, return the limits **at the close of the day**, after that day's approvals and with that day's notices applied. Every day's table must hold every entry below; a table that leaves out a customer or a figure breaks our rules.

- `customers`: every customer who has applied in the period so far (today included) → what they may still borrow: their customer limit as above (after everything approved to them, today included), or 0 for a customer who is delinquent or below the score cutoff.
- `daily_capacity_remaining`: the daily cap minus today's approvals (not below 0).
- `period_budget_remaining`: not used this round (null is fine).

An entry counts as right when it is within 1 + 0.1% of ours. A day's table scores the share of right entries among the customers whose entry changes that day, times the share of right bank figures. The customers whose entry changes are those who applied that day, any other customer whose limit moved since the day before, and any customer whose entry you changed to a wrong amount. The table's accuracy is the mean over the 20 days.

## How the program is judged

**Hard constraints** (if any is broken, the program does not count):

- One well-formed decision for every application of the day (and none for anything else), and a complete limit table; a call that crashes or times out counts as broken.
- Delinquent applicants declined; no approval with `bureau_a_score` below 745; short-tenure applicants referred (our habit; an exception is possible); at most 3 referrals a day beyond those our rules require.
- No customer approved more on a day than their customer limit that morning; no day above the daily cap of 250,000.
- The right reason code on every decline; planted twins treated alike.

**Quality** = (expected profit / the expected profit of our own benchmark program on the same days) × the limit table's accuracy. Our desk quotes customers from the table and treasury funds from it, so lending done on a wrong table is worth that much less to us. Expected profit: what the approvals earn less their expected losses, with the margin and the loss of our credit policy and the true probability that the customer defaults over the loan's life (with everything we have lent them), less the cost of the referrals; a decline counts 0, and a loss stays a loss whatever the table. Higher is better.
