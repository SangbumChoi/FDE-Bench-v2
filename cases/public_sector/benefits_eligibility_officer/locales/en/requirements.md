# Household Living Support determinations

## Background

We have a backlog of about 300 applications for our Household Living Support benefit. Can you decide who qualifies and how much they get each month? The applications, the household members, the declared assets, last year's amount table, the changes some households reported after applying, the letters we received and the leaflet we give to citizens are attached. The leaflet is written for citizens and deliberately avoids numbers; the exact rules are below. What matters to us is that every household is paid exactly what it is entitled to under this year's rules and, above all, that no household is wrongly approved or wrongly turned down; a refusal must also give the right reason.

<!-- tier: easy -->
## This round

This round is only the basic calculation; some parts are dealt with elsewhere:

- **Assets**: the intake desk has already checked everyone's savings and property this round, so treat every household as meeting the asset condition. `DENY_ASSETS` is not used this round.
- **Disability**: the disability supplement is paid separately by the disability office this year, so it is not part of the amount.
- **Child support**: the council is reviewing how child support is treated, so it is not counted as income this round. Those households will be looked at again later.
- **Cap**: the finance department applies the budget cap afterwards, so give us the amounts without any cap.
- **Reported changes and letters**: the changes in `reported_changes.csv` and the documents in the `correspondence` folder are handled separately. Decide every application as filed.

<!-- /tier -->
<!-- tier: medium -->
## This round

The changes in `reported_changes.csv` and the documents in the `correspondence` folder are handled separately this round. Decide every application as filed.

<!-- /tier -->
## Deliverable

One CSV file, `determinations.csv`, with the ASCII header `household_id,eligible,monthly_amount,reason_code` and one row per application in `applications.csv`:

- `household_id` exactly as in the data (e.g. H001);
- `eligible` = `yes` or `no`;
- `monthly_amount` = this year's monthly benefit in our currency units (0 when not eligible);
- `reason_code` = one of `APPROVED` (new application approved), `RENEWAL` (renewal approved), `DENY_RESIDENCY`, `DENY_ASSETS`, `DENY_INCOME`. `APPROVED` and `RENEWAL` go only with `eligible = yes`, the `DENY_` codes only with `eligible = no`. When several reasons apply, use the first in this order: residency, assets, income.

## Data notes

- **Household size**: only members with `lives_at_address = yes` in `household_members.csv` count. Members living elsewhere (a child studying in another city, a spouse working abroad) do not count towards the household size, and their income, disability and so on are ignored completely.
- **Dates**: all dates in the data are written day/month/year (05/03/2025 is 5 March 2025).
- **Residency**: the household must have lived in the city for at least {{residency_days}} days on the application date, i.e. `resident_since` must be at least {{residency_days}} days before `application_date` (application on 14/09/2026 → resident since {{residency_example}} or earlier). This is a statutory condition. Otherwise: not eligible, `DENY_RESIDENCY`.
<!-- tier: medium hard -->
- **Assets** (`assets.csv`): add up all declared values, except the home the household lives in (`home_owned`) and one car (if there are several cars, the most valuable one is exempt; the others count). If this countable total is above {{asset_base}} for a one-person household, plus {{asset_extra}} for each additional member at the address, the household is not eligible: `DENY_ASSETS`.
<!-- /tier -->
- **This year's amounts**: `amount_table_2025.csv` is last year's table. This year's standard amount and maximum housing allowance are last year's values increased by {{uprating}}%, each rounded down to a multiple of 10 (for one person: 640 → {{std1}} and 380 → {{house1}}). The new table has not been published yet, so it is not in the data.
- **Need**: standard amount for the household size + the monthly rent up to the maximum housing allowance for that size (owners with no rent get nothing for housing)<!-- tier: medium hard --> + {{disability_supplement}} for each member at the address with `disability = yes`<!-- /tier -->.
- **Countable income** (members at the address only, all figures monthly): for earned income, each earner keeps the first {{earned_flat}} untouched<!-- when: earned_disregard=150_30,100_20 --> and {{earned_ignored}}% of the rest is also ignored, so {{earned_counted}}% of (earned income − {{earned_flat}}) counts<!-- /when --><!-- when: earned_disregard=200_0 --> and everything above {{earned_flat}} counts in full<!-- /when -->, per person. Pensions, unemployment benefit<!-- tier: medium hard -->, `child_support`<!-- /tier --> and other income count in full<!-- tier: medium hard --> (child support is income of the household, even though some citizens think it is not)<!-- /tier -->.
- **Amount**: need − countable income, rounded down to a whole unit<!-- tier: medium hard -->, and never more than the budget-law cap for the household size: {{cap}}<!-- /tier -->. If the result is 0 or less, the household is not eligible: `DENY_INCOME`.
- **Renewals** (`application_type = renewal`, with `last_year_monthly_amount`): our practice is that renewals are approved at last year's monthly amount without re-assessment (reason `RENEWAL`), to keep the queue moving. All renewal households already meet the residency and asset conditions.
<!-- tier: hard -->
- **Heating supplement** (the finance circular of 25/09/2026 in the `correspondence` folder): for applications dated on or after 01/10/2026, add the winter heating supplement of 60 to the need, whatever the household size. Applications dated earlier do not get it. The cap still applies.
- **Reported changes** (`reported_changes.csv`): some households told us about a change after they applied (a member's new earned income, or a new rent). We decide on the situation on the application date: a change whose `effective_from` is on or before the `application_date` replaces the declared figure (that member's earned income, or the rent); a change that takes effect after the application date is not taken into account now (it goes to the next review).
- **Letters asking for exceptions** (`correspondence` folder): a councillor asks us to approve a family that has not lived here long enough, and an applicant asks us not to count her child support. Neither changes anything: every household is decided on the rules above. The residency condition is statutory and has no exceptions.
<!-- /tier -->

## How the determinations are judged

**Hard constraints** (if any is broken, the batch does not count):

- No household with less than {{residency_days}} days of residence is approved.
<!-- tier: medium hard -->
- No household above the asset limit is approved.
- No monthly amount exceeds the cap for the household size.
<!-- /tier -->
- Every row has a valid reason code that matches the decision (an approval is `APPROVED` for a new application and `RENEWAL` for a renewal).
- Renewals are approved at exactly last year's monthly amount.

**Quality**: the sum over all households of the absolute difference between the amount you pay (0 if not eligible) and the household's true entitlement under this year's rules, plus 400 for every wrong eligibility decision, plus 100 for every household that is rightly refused but with a reason code other than the first condition it fails (residency, assets, income). Lower is better.
