# Household Living Support determinations

## Background

We have a backlog of about 300 applications for our Household Living Support benefit. Can you decide who qualifies and how much they get each month? The applications, the household members, the declared assets, last year's amount table and the leaflet we give to citizens are attached. The leaflet is written for citizens and deliberately avoids numbers; the exact rules are below. What matters to us is that every household is paid exactly what it is entitled to under this year's rules and, above all, that no household is wrongly approved or wrongly turned down; a refusal must also give the right reason.

## Deliverable

One CSV file, `determinations.csv`, with the ASCII header `household_id,eligible,monthly_amount,reason_code` and one row per application in `applications.csv`:

- `household_id` exactly as in the data (e.g. H001);
- `eligible` = `yes` or `no`;
- `monthly_amount` = this year's monthly benefit in our currency units (0 when not eligible);
- `reason_code` = one of `APPROVED` (new application approved), `RENEWAL` (renewal approved), `DENY_RESIDENCY`, `DENY_ASSETS`, `DENY_INCOME`. `APPROVED` and `RENEWAL` go only with `eligible = yes`, the `DENY_` codes only with `eligible = no`. When several reasons apply, use the first in this order: residency, assets, income.

## Data notes

- **Household size**: only members with `lives_at_address = yes` in `household_members.csv` count. Members living elsewhere (a child studying in another city, a spouse working abroad) do not count towards the household size, and their income, disability and so on are ignored completely.
- **Dates**: `application_date` and `resident_since` in `applications.csv` are written day/month/year (05/03/2025 is 5 March 2025).
- **Residency**: the household must have lived in the city for at least 6 months on the application date, i.e. `resident_since` must be on or before the same day of the month six months before `application_date` (application on 14/09/2026 → resident since 14/03/2026 or earlier). This is a statutory condition. Otherwise: not eligible, `DENY_RESIDENCY`.
- **Assets** (`assets.csv`): add up all declared values, except the home the household lives in (`home_owned`) and one car (if there are several cars, the most valuable one is exempt; the others count). If this countable total is above 6,000 for a one-person household, plus 3,000 for each additional member at the address, the household is not eligible: `DENY_ASSETS`.
- **This year's amounts**: `amount_table_2025.csv` is last year's table. This year's standard amount and maximum housing allowance are last year's values increased by 3.2%, each rounded down to a multiple of 10 (for one person: 640 → 660 and 380 → 390). The new table has not been published yet, so it is not in the data.
- **Need**: standard amount for the household size + the monthly rent up to the maximum housing allowance for that size (owners with no rent get nothing for housing) + 120 for each member at the address with `disability = yes`.
- **Countable income** (members at the address only, all figures monthly): for earned income, each earner keeps the first 150 untouched and 30% of the rest is also ignored, so 70% of (earned income − 150) counts, per person. Pensions, unemployment benefit, `child_support` and other income count in full (child support is income of the household, even though some citizens think it is not).
- **Amount**: need − countable income, rounded down to a whole unit, and never more than the budget-law cap for the household size: 1,050 (1 person), 1,450 (2), 1,800 (3), 2,100 (4), 2,350 (5), 2,550 (6 or more). If the result is 0 or less, the household is not eligible: `DENY_INCOME`.
- **Renewals** (`application_type = renewal`, with `last_year_monthly_amount`): our practice is that renewals are approved at last year's monthly amount without re-assessment (reason `RENEWAL`), to keep the queue moving. All renewal households already meet the residency and asset conditions.

## How the determinations are judged

**Hard constraints** (if any is broken, the batch does not count):

- No household with less than 6 months of residence is approved.
- No household above the asset limit is approved.
- No monthly amount exceeds the cap for the household size.
- Every row has a valid reason code that matches the decision (an approval is `APPROVED` for a new application and `RENEWAL` for a renewal).
- Renewals are approved at exactly last year's monthly amount.

**Quality**: the sum over all households of the absolute difference between the amount you pay (0 if not eligible) and the household's true entitlement under this year's rules, plus 400 for every wrong eligibility decision, plus 100 for every household that is rightly refused but with a reason code other than the first condition it fails (residency, assets, income). Lower is better.
