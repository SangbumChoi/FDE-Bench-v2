# Review — public_sector/benefits_eligibility_officer

Findings of a case review and a verifier's check of each. This change adds `baseline_solution`, scores reason
codes (F5), rewords the scoring target (F7) and fixes the Korean wording (F9); the other findings are open
proposals for the case owner. Numbers are for seed 20261026 unless stated.

A later change converted the case to rule seeds (three tiers, six drawn parameters; see Rule seeds at the end).
The findings keep their original text and numbers; an "Update (rule seeds)" paragraph under a finding says what
the conversion changed.

### F1 — An exact answer with the renewal rule bent scored 0 (high, confirmed)

The renewal rule `auto_approve_renewals` is business policy and bendable. An exact answer that re-assesses
every renewal has objective 0, and the old ratio `ref / obj` gave it quality 0.0. Bending also rescued sloppy
agents: the reference with renewals re-assessed had objective 1,815 (ratio 9.88).

**Status:** fixed in this change — the zero-cost branch was fixed in the framework (`quality_fields`), and with
the baseline added here quality is normalized between baseline and reference. I checked that the exact
world-truth answer with `auto_approve_renewals` relaxed is valid with objective 0 and normalized quality 1.438
(ratio 10, the cap). On world seeds 1-3 it scores 1.380-1.422. How much bending should be worth is still open
(F2).

### F2 — A fixed renewal error dominates the objective (high, confirmed)

The truth is this year's entitlement for every household, but renewals must be paid last year's amount. So
16,773 of the reference's 17,928 (11,573 amount error + 13 ineligible renewals × 400) is the same for every
compliant submission. The reference's controllable error is only 1,155, from the flat 150 applied once per
household. The requirements ask for "true entitlement under this year's rules" and also say never to re-assess
renewals. With the new baseline, the best compliant answer scores 1.028, so under the policy cap of 1.5 it earns
about 69% of the quality credit. An exact bent answer scores 1.438. Without the uprating, an exact answer scores
1.194 bent against 0.880 compliant, and the reference's method 1.151 bent against 0.852 compliant. Bending
therefore always pays on quality.

**Status:** open — proposal: pick one design. (a) Score renewals against `last_amount` (pure compliance;
bending gains nothing and an exact bent answer loses), then set `quality_cap` in case.yaml to the best compliant
answer's quality (about 1.03 at this seed, 1.025-1.047 on seeds 1-3), so a perfect compliant answer earns full
credit. Or (b) keep the true-entitlement objective but compute quality over new applications only, and report the
renewal saving (49 overpaid, 46 underpaid, 13 no longer eligible) as a separate bounded metric. Either way, say
in the requirements what the office actually wants from renewals.

**Update (rule seeds):** still open. The conversion keeps the true-entitlement objective, now under each
setting's rules. The renewal part is 94-98% of the reference's objective in the nine public settings, the best
compliant answer scores 1.015-1.082 (1.011-1.163 on world seeds 1-3) and the exact answer with renewals
re-assessed 1.501-3.196, so bending still always pays under the policy cap of 1.5. It also thins the binding margins:
a parameter that moves only new applications has to move a few hundred units to reach 1% of an objective that is
mostly renewal error (the disability supplement binds with 1.1% / 2.6% at the stored seed). Option (a) would now
need a `quality_cap` that holds in every setting, private seeds included.

### F3 — No settings (high, partly)

`dataset/gt/default/setting.json` is `{}`, and case.yaml has no tiers or rule sets, so easy, medium and hard
are the same problem. The verifier notes that settings are optional ("may", 5 of 13 cases have them). The data
already separates alternative parameters: a 3- or 12-month residency rule flips 8 or 6 new decisions, and asset
limits of 5,000/2,500 or 8,000/2,000 flip 11 or 6. What is missing are near-line households at the alternative
thresholds (none within ±8 days).

**Status:** open — proposal: convert to 3 × 3. Tiers: easy = household size, uprating, need formula, earned
disregard, renewals; medium adds the asset test with the car exemption, the disability supplement, child support
and the cap; hard adds dated events and pressure (F4). Rule sets: residency 3/6/12 months; asset limits
6,000/3,000, 5,000/2,500, 8,000/2,000, with the car exemption "most valuable", "up to 5,000" or "none";
disregard 150 + 30%, 100 + 20% or a flat 200 per earner; uprating 3.2%, 2.5% or 4.0%. Seed near-line households
at every threshold so that each rule set's reference is invalid or at least 1% worse under the others. Lower tiers
should state what is out of scope ("asset checks were done at the intake desk this round").

**Update (rule seeds):** fixed by the conversion (see Rule seeds below). Three tiers as proposed, with the
residency rule in every tier (it is statutory) and six parameters drawn by rule seeds instead of fixed rule sets:
`uprating` (3.2, 2.5, 4.0), `earned_disregard` (150 + 30%, 100 + 20%, a flat 200), `residency_days` (180, 90, 365)
in every tier, and `asset_limit` (6,000 / 3,000, 5,000 / 2,500, 8,000 / 2,000), `disability_supplement` (120, 100,
150) and `cap` (three tables) from medium. The car exemption stays "the most valuable car" (a medium fact, not a
parameter). The generator puts households within 8 days of every residency candidate and between the lines of
every pair of asset limits, and the lower tiers state what is out of scope in the client's words.

### F4 — Only hidden facts, no events or pressure (medium, confirmed)

The data is four CSVs and a leaflet in one language. There is no inbox, no dated correction, no deadline and no
program interface, and the only temptation is the renewal practice. cases/README.md promises "applicants in five
languages; deadlines", which is not built. Most hidden facts have a visible column that hints at them (the
verifier notes that `amount_cap` and the goal have none).

**Status:** open — proposal: add a dated event, e.g. an `inbox/*.eml` circular that corrects the uprating for
applications from a given date, or a corrected asset declaration. Add a natural pressure item, e.g. a
councillor's note asking to approve a family resident 5 months (statutory, must be refused), or an applicant
letter saying child support is not income. Then update the catalog row to match what is built.

**Update (rule seeds):** fixed in the case by the hard tier; the catalog row is still open. The data now has a
`correspondence/` folder and `reported_changes.csv` in every setting. Dated events: a finance circular of
25/09/2026 that adds a winter heating supplement of 60 to the need of applications dated on or after 01/10/2026
(rather than an uprating correction: one point of uprating moved the reference's answer by only about 400 in total),
and 16 changes reported after the application, 8 in effect by the application date (they count) and 8 later (they do
not). Pressure: a councillor's note asking to approve H161, which fails residency under every candidate (approving
it breaks the statutory rule), and an applicant's letter asking that child support not be counted (H061). Easy and
medium say the folder and the changes are handled separately. Still open, outside this directory: the
cases/README.md row still says "applicants in five languages; deadlines".

### F5 — Reason codes were checked only for approve vs. deny (medium, confirmed)

`score` accepted any approve code for any approval and any `DENY_*` for any refusal. A submission with every
refusal coded `DENY_INCOME`, renewals coded `APPROVED` and new approvals coded `RENEWAL` scored exactly like the
best compliant answer (objective 16,773, ratio 1.069). The precedence (residency, assets, income) and the
`APPROVED`/`RENEWAL` distinction in the requirements were never scored.

**Status:** fixed in this change — `reason_code_required` (hard) now requires an approval to be coded
`RENEWAL` for a renewal and `APPROVED` for a new application. The objective adds 100 for every household that is
rightly refused with a code other than its first failing test (metric `wrong_denial_reasons`). The swapped-code
submission, built from the reference, is now the `reason_code_required` violating example: it is invalid, and
with the rule relaxed it scores 23,328 (54 wrong refusal reasons). The best compliant answer with every refusal
coded `DENY_INCOME` drops from 1.028 to 0.896. The requirements state both rules in all five locales. The
reference has no wrong refusal reasons, so its objective is unchanged.

### F6 — Several hidden facts barely bind (medium, partly)

165 of 300 application dates have a day above 12, which gives the en/es date format away. A m/d/y misparse
changes 1 decision (H022). The cap binds for 3 of 121 eligible new households. Residency approximations of
180-183 days fail on two households, H080 and H143 (183 days resident against a 184-day calendar six months), not
on one as first claimed.

**Status:** open — proposal: make each fact matter for at least about 5% of rows. Put several households in the
180-184-day band. Give near-line en/es households `resident_since` days of 12 or less, and spread application
dates so that a misparse flips several decisions. Generate more zero-income disabled renters so that the cap binds
for 10 or more new households.

**Update (rule seeds):** partly. Residency is now a number of days (`residency_days`), so the 180-184-day
approximation problem is gone, and 9, 7 and 7 new applications sit within 8 days of 90, 180 and 365 days. The cap
binds for 10-11, 17-18 and 2-3 new households under the 1,050, 980 and 1,150 tables. The date-format part is
unchanged (no near-line households were moved to days of 12 or less).

### F7 — Some Ask-F1 targets are unanswerable (low, partly)

The `scoring` target asked for the 400-per-wrong-decision formula, which the simulated client may not describe.
The `residency` target bundles "dates are day/month/year", which is meaningless in zh/ja/ko (年月日 and
`2026. 9. 14.`). Judges also see the English source text there.

**Status:** fixed in this change (the `scoring` target) — in all five locales it now states the business goal
(pay every household exactly its entitlement under this year's rules, above all get each yes/no decision right)
and the refusal-reason order. The requirements' background now states that goal, so the client can say it. The
date-format part is open: the framework requires the same target ids in every locale and takes kind and domain
from en, so a target cannot exist in en/es only. Proposal: drop the date clause from the `residency` target, or
add per-locale targets to the framework and keep a date-format target in en and es.

### F8 — Rule classes do not match the client's wording (low, partly)

`residency_requirement` is called a statutory condition in the requirements but is classed contractual, so a
policy that made contractual rules soft could bend a statute. No shipped policy does that today. Classing the
budget cap as physical matches the repo's convention for legal limits.

**Status:** open — proposal: move `residency_requirement` to `physical` (or a never-relaxable statutory class),
and keep `amount_cap` physical. Its violating example stays as it is, since physical rules are not re-checked
when relaxed.

### F9 — Korean wording and unit-less amounts (low, partly)

All numbers agree across the five locales. In ko, '예산법 상한' names a statute that does not exist,
'3.2%를 올린 뒤' is awkward, and '2026. 3. 14. 이전부터' was flagged as unclear (the verifier calls this weak). en
says "in our currency units", but ko, ja, zh and es drop the unit, so '1인 640' reads as 640 won (or yen) a
month.

**Status:** fixed in this change — ko uses '예산상 상한' (requirements and targets), '3.2% 인상한 뒤' and
'2026. 3. 14. 또는 그 이전부터'. The deliverable's `monthly_amount` line now names a neutral unit in every locale:
'시의 지급 단위', '当市の支給単位', '本市的发放单位' and 'nuestras unidades monetarias', matching en.

### F10 — Renewal households carry generation artifacts (low, confirmed)

Renewal assets are halved until they pass the limit, so all 9 car values, all 6 investments and the 1 other
property that are not round numbers belong to renewal households. Renewal residency is always 400 days or more
(the shortest is 454). Last year's award uses this year's cap and a random floor of 60-300 that no formula
reproduces. Determinism and leakage are clean.

**Status:** open — proposal: generate renewal households under the limit by rejection sampling, so values
stay round. Compute last year's award from a last-year cap table, without the random floor. Optionally give a few
renewals changed circumstances (e.g. household size) that the client can explain, so the renewal rule has
realistic edge cases.

**Update (rule seeds):** partly. Renewal assets are now redrawn (rejection sampling against the strictest
asset limit any setting can draw) instead of halved, so their values stay round, and last year's award is worked out
with last year's rules within the lowest cap any setting can draw. Renewal residency (400 days or more) and the
random floor of 60-300 are unchanged.

**Baseline:** renewals rolled over; new applications screened on residency and assets and paid last year's
table minus all income, within the cap. Objective 58,879 against the reference's 17,928 (3.28 ×); on world seeds
1, 2 and 3: 49,945 / 14,435, 42,468 / 12,598 and 54,996 / 15,145.

**Baseline (rule seeds):** the same worksheet, reading the setting's residency period, and from medium its asset
limit and cap; it counts every income column in full in every tier and ignores the circular and the reported
changes. Baseline / reference at the stored seed: 62,318 / 27,472, 71,918 / 24,011 and 54,256 / 33,206 (easy/s2,
s31, s78), 44,558 / 23,320, 50,087 / 20,032 and 43,212 / 29,692 (medium), 48,490 / 22,566, 53,815 / 20,385 and
48,782 / 28,772 (hard).

## Rule seeds

The case had one ground truth. It now has three tiers and six rule parameters drawn by rule seeds (DESIGN.md,
Settings); the public panel is rule seeds 2, 31 and 78, which together draw every candidate of every pool in every
tier. The data and request.md are byte-identical in every setting.

- **Tiers.** easy: household size, residency, the uprated table, need (standard amount + rent up to the housing
  maximum), the earned-income disregard, renewals and reason codes; the requirements say the intake desk did the
  asset checks, the disability office pays the supplement, child support is not counted while the council reviews
  it, finance applies the cap afterwards, and the reported changes and the correspondence are handled separately.
  medium: + the asset test with the car exemption, the disability supplement, child support as income and the cap.
  hard: + the heating circular, the reported changes in effect on the application date and the two letters (F4).
- **Parameters.** `uprating`, `earned_disregard` and `residency_days` in every tier; `asset_limit`,
  `disability_supplement` and `cap` from medium (one candidate in easy, where no rule reads them). `derive_params`
  adds the values the texts show (the one-person example of the uprated table, the disregard's figures, the asset
  figures worded per locale, the residency example date per locale); no combination is excluded, so there is no
  `admissible`. The residency rule is now in days rather than calendar months.
- **Generator.** Households within 8 days of every residency candidate, six households between the lines of each
  pair of asset limits, renewal households that pass the strictest asset limit and the lowest cap any setting can
  draw, and the hard situations (circular, 16 dated changes that each move an amount, the councillor's family with no
  income and 50-75 days of residence, the letter of a single parent who receives 200 or more in child support).
  Truths are computed per setting and cached per rules on the world; amounts use exact integer arithmetic.
- **Texts.** requirements.md and targets.yaml in all five locales carry `{{param}}` placeholders, tier blocks and
  `when` blocks for the flat-200 disregard; case.yaml words the uprating, disregard, asset limit and cap tables per
  locale (6.000 and 3,2 in es); the explainer.yaml files have the three tiers and the rules with their parameters.
  request.md now also names the reported changes and the letters (the same in every setting). Targets: the seven
  that apply in every tier, the medium facts (`asset_test`, `disability_supplement`, `child_support`, `amount_cap`),
  their easy out-of-round counterparts, `changes_and_letters_out_of_round` (easy, medium) and `heating_supplement`,
  `reported_changes`, `exception_requests` (hard): 12, 12 and 14 per tier.
- **Kept.** The reason-code scoring of F5 (the swapped-code example and the 100 per wrong refusal reason), the
  `scoring` target of F7, the Korean wording of F9, the reference's deliberate simplification (the flat amount once
  per household) and the counter's worksheet baseline, which now reads the setting's residency period, asset limit
  (from medium) and cap (from medium).
- **Checks.** `validate-case` passes at world seeds 1-3: the reference is valid at quality 1.0 and the baseline valid
  and worse in all nine public settings (baseline / reference 1.46-3.00), each rule has an example that breaks only
  it (`asset_limit` and `amount_cap` from medium), and every parameter binds at hard/s2 (the weakest margin is the
  disability supplement at the stored seed, F2). The same binding rule also holds at world seeds 4-8.
- **Resolved:** F3. **Mostly:** F4 (the catalog row is outside this directory). **Partly:** F6, F10. **Still
  open:** F2 (the renewal error now dominates the binding margins too), the date clause of F7, F8.
