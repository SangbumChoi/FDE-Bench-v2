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

**Update (ground truth audit):** fixed (see Ground truth audit below). The renewals stay measured against this year's
entitlement, which the requirements now say in the client's words ("the price of our practice, the same for every
batch that keeps it"); that cost is the proven floor of a valid objective. The reference is now the answer key, so
a perfect compliant batch is the reference (1.0) and `quality_cap` is 1.0; the scale is carried by the new
applications, from the client's own worksheet to the answer key. Bending is priced: an exception covers the whole
renewal queue at 200 a renewal household, so re-assessing every renewal pays in 37 and loses in 8 of the 45 audited
settings, and loses in most settings of world seeds 1 and 2.

### F3 — No settings (high, partly)

`dataset/gt/default/setting.json` (the layout before `dataset/answer/`) is `{}`, and case.yaml has no tiers or
rule sets, so easy, medium and hard
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
in every tier, and `asset_limit` (6,000 / 3,000, 5,000 / 2,500, 8,000 / 2,000), `disability_supplement` (120,
100, 150) and `cap` (three tables) from medium. The car exemption stays "the most valuable car" (a medium fact, not a
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

**Update (ground truth audit):** the binding is now measured per fact by the audit's ablations: every target bites
in every tier where it is in force. More members have a disability (63 among the new applications, 28 before),
which makes the supplement facts bite; the cap binds for 19-20, 15-16 and 5 new households under the 980, 1,050 and
1,150 tables. The date format is no longer a target (the dates give it away), as F7 proposed.

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

**Update (ground truth audit):** fixed. The `residency` target is now the residency period alone (`param:
residency_days`); the date format stays in the requirements as context. The `scoring` target is gone: the goal
changes no exact answer and reading the refusal order the other way costs less than a tenth of the scale, so both
stay in the requirements and in the objective.

### F8 — Rule classes do not match the client's wording (low, partly)

`residency_requirement` is called a statutory condition in the requirements but is classed contractual, so a
policy that made contractual rules soft could bend a statute. No shipped policy does that today. Classing the
budget cap as physical matches the repo's convention for legal limits.

**Status:** open — proposal: move `residency_requirement` to `physical` (or a never-relaxable statutory class),
and keep `amount_cap` physical. Its violating example stays as it is, since physical rules are not re-checked
when relaxed.

**Update (ground truth audit):** fixed. `residency_requirement` is physical, like the budget cap.

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

## Ground truth audit

The deep audit of the ground truth (DESIGN.md, Ground truth audit). The case is now `audited: true`; the measured
evidence is in [GT.md](../../GT.md) and `dataset/audit.json`, what the client answers each fact from in
[CLIENT_REVIEW.md](../../CLIENT_REVIEW.md) (awaiting human review). Numbers are on the public world unless stated.

### What the audit found

- **Nothing was measured.** `audit-case` at the start: 19 targets with no ablation, no shortcuts, no never-asks
  solver, no best known solution or bound, no `quality_cap`.
- **A fixed renewal error made the scale and the bend (F2).** Renewals must be rolled over at last year's amount but
  were measured against this year's entitlement: 94-98% of the reference's objective was this one cost, the same for
  every compliant answer. The reference's own error (the flat part of the disregard once per household) was the other
  2-6%, so a perfect compliant batch scored 1.015-1.082 and, under the policy cap of 1.5,
  earned about 69% of the quality credit, while re-assessing the renewals scored 1.501-3.196: bending always paid.
- **The zero point was a strawman.** The baseline ("the counter's worksheet") took every income column in full, so
  it ignored the office's own earnings disregard, and the requirements never described it. Copying it and adding
  the disregard alone recovered 0.47-0.80 of the scale.
- **Several targets were natural readings or did not bite.** `household_size` and `need_formula` are what the
  literal solution already does; reading the refusal order the other way (`scoring`) cost at most 0.08 of the
  answer key's scale; the parameter ablations of `uprating` (candidates 0.7-0.8 points apart) and of the disability
  supplement cost a few hundredths; applying easy's cap cost 0.03-0.05. Four targets bundled facts:
  `residency` (the period and the date format), `asset_test` (the limit and the car exemption), `scoring` (the goal
  and the order), `changes_and_letters_out_of_round` (the changes, the circular and the letters).

### What changed

All in the client's own terms; the request and the agent's view are the same in every setting.

- **Renewals and their exception.** The requirements say what the renewal practice costs: renewals are measured
  against their entitlement this year too, "the price of our practice, the same for every batch that keeps it", the
  proven floor of a valid objective (`objective_bound`, `practice_cost`). Only the director can approve an exception;
  it covers the whole renewal queue (every renewal household is treated alike) and each re-assessment is half a day
  of a caseworker, counted at 200 a renewal household (`REASSESSMENT_COST`), charged once any renewal is not rolled
  over. Re-assessing every renewal now pays in some settings and loses in others; cherry-picking one always loses.
- **Reference: the answer key.** Every rule of the setting applied exactly; it is also the best known solution, its
  objective is the bound (gap 0), and `quality_cap` is 1.0.
- **Baseline: the client's own way, described.** requirements.md has a new section, "How the counter does it today"
  (all five locales): last year's paper worksheet. It has last year's figures on it (table, disregard of 150 and 30%,
  from medium last year's 980 cap table), its disregard box takes the applicant's earnings only (the other members'
  earnings count in full, with those of a partner, parent or other relative on the form who lives elsewhere), it
  counts every income column (child support too), has no supplement line, counts residency in calendar months and
  decides as filed. It keeps the statutory period, the asset limit and the round's arrangements, so it is valid. No
  one of its differences carries the scale: the worksheet with any one thing changed reaches at most 0.396 (0.436 on
  world seeds 1-3).
- **Uprating.** The candidates are 3.5, 2.0 and 5.0 (3.2, 2.5 and 4.0 before), 1.5 points apart, so a wrong guess
  costs a tenth of the scale in most settings. Pools of the same size keep every public draw's position.
- **Data** (the same in every setting): a member has a disability with probability 0.14 (0.08 before; 108 members,
  63 at the address of a new application, against 28), which changes the disability column and the renewals' last
  amounts; the generator checks its situations against fixed rules (`PROBE`), so the uprating pool no longer moves the
  world. The household, asset, change and correspondence situations are as before (H161, H061, 16 changes).
- **Rule class.** `residency_requirement` is physical (statutory), like the budget cap (F8).
- **Reading the file.** Household ids and reason codes are read in any letter case (`h001`, `approved`), so a
  correct batch never loses for a spelling the request leaves open.
- **Texts in five locales.** requirements.md (the easy and medium rounds now say separately that the changes are
  decided as filed and that the correspondence, the circular included, is handled elsewhere; the renewal exception;
  the counter's worksheet; the quality paragraph), targets.yaml, summary.yaml and explainer.yaml (the shortcuts).
- **Targets: 19 → 15.** Removed and kept as context: `household_size`, `need_formula` (natural readings),
  `scoring` (no exact answer changes; the order costs below a tenth), `cap_out_of_round` (no cap is the natural
  reading; applying one costs 0.04-0.06) and `heating_supplement` (an official circular, applied by the natural
  reading; its fact is easy's and medium's `circular_out_of_round`). Split: `changes_and_letters_out_of_round` into
  `changes_out_of_round` and `circular_out_of_round` (the letters change nothing in any tier). Renamed and narrowed:
  `asset_test` to `asset_limit` (`param: asset_limit`; the car exemption is context). `earned_disregard`,
  `residency` (without the date format) and `uprating` are `param:` targets; `disability_supplement` and
  `amount_cap` are misread as "none" (the agent sees no figure for either).
- **Hooks.** `ablations` (the answer key under one misreading, `misreadings`), `shortcuts` (19), `robust_solution`
  (with `never_asks`, the variants that try to beat it), `best_known_solution`, `objective_bound`, `diagnose`
  (`diagnostic`, `alternatives`); `bent_deliverables` and `diagnostic_cases` for GT.md. `gt_report.py` writes GT.md
  and `client_review.py` CLIENT_REVIEW.md.

### Results

- **Literal solution**: invalid in all nine public settings and all 45 measured ones, as delivered and with
  `auto_approve_renewals` relaxed (approving recent arrivals breaks the statutory residency rule). Its next readings
  (a residency wait of 90, 180 or 365 days guessed with the renewals rolled over; every rule it breaks kept) are
  invalid or score 0.000-0.056.
- **Facts**: every target bites in all 15 settings of every tier where it is in force, but `uprating` (13 / 10 / 4
  of 15 per tier; 6-15 of 15 on world seeds 1-3); damage 0.068-1.000. Every diagnostic separates; no false
  "not enforced" on the best known solution; no ablation flags another target.
- **Shortcuts**: 19, closed in all 45 settings (best valid quality 0.396), and on world seeds 1-3 (0.436).
- **Value of asking**: 1.000 / 0.962 / 0.746 (easy / medium / hard); 1.000 / 0.957-0.981 / 0.769-0.872 on world
  seeds 1-3.
- **Bending**: re-assessing every renewal pays in 15 / 11 / 11 and loses in 0 / 4 / 4 of 15 settings per tier
  (−0.181 to +0.434 of quality); on world seeds 1, 2 and 3 it pays in 12, 16 and 24 of 45 and loses in the rest.
- **Leaderboard round 2026-11** (rule seeds 108807, 519122, 904685, every tier, public world and world seeds 1-3):
  the reference valid at quality 1.0, the baseline valid, the scale 0.802 wide or wider, the literal solution invalid
  as delivered and relaxed, in all 36 settings (before: also all passing, scale 0.602 or wider, the literal invalid).

### Findings resolved

- **Resolved:** F2 (the renewal cost is the stated price of the practice and the bound; the reference is the
  answer key and earns full credit; bending is priced and two-sided), F7 (the date clause dropped from `residency`,
  the `scoring` target removed), F8 (`residency_requirement` physical).
- **Mostly:** F6 (every target now bites in every tier where it is in force; the date format stays context).
- **Still open:** F10 (renewal residency is at least 400 days, and last year's award keeps its random floor of
  60-300), and outside this directory the catalog row of F4. docs/zh, ko, ja and es README and REVIEW still describe
  the case before the audit until they are retranslated.

### Checks of the audit's own claims

- **The never-asks solver is a strong attempt.** It reads every fixed fact the natural way, hedges the reported
  changes (the one fixed fact the data leaves open) and plans for the strictest candidate of each rule. Attempts to
  beat it (GT.md, part 4): reading the reported changes as in effect only, 0.287 in hard against 0.254; gambling on
  the middle asset limit (invalid wherever the drawn limit is stricter), 0.148 in medium and 0.296 in hard, which
  takes knowing the zero point an agent does not have; the answer key of one guessed combination, 0.000 / 0.079 /
  0.151 on average; a solver that guessed every fixed fact of the tier right, 0.426 / 0.094 / 0.287. Against the
  best never-asks attempt asking is still worth 1.000 / 0.852 / 0.704, and against the lucky guess (not a strategy
  an agent can choose) 0.574 / 0.906 / 0.713.
- **The diagnostic holds on other deliverables.** Four batches with every fact right (amounts in cents, ids and
  codes in lower case with Yes/NO and two decimals, two slips, every refusal coded `DENY_INCOME`) are called
  enforced on every fact in every setting; seven misreadings no
  ablation makes (residency in calendar months, the disregard once per household, last year's table, every car
  exempt, another cap table, another supplement, the changes ignored) are each caught in every setting where they
  change the batch, with no other target flagged.
- **The zero point is the client's way, and no single change carries it.** Copying the worksheet and changing one
  thing, every one of its ten differences in turn and a guessed uprating, stays at or below 0.396 (0.436 on world
  seeds 1-3).

## Ground truth check

A second engineer checked the audit adversarially (the same house rules). Numbers are on the public world unless
stated; "before" is the audit above.

### What the check found

- **The bound was not proven.** A renewal counted as rolled over within half a unit of last year's amount but was
  paid what the batch wrote, so writing each renewal half a unit towards its entitlement stayed valid and beat the
  bound by 0.5 a renewal (55 on the public world, quality 1.002-1.003 in every setting tried).
- **The diagnostic hid a second misread fact.** A fact was called not enforced only when the batch otherwise agreed
  with the client's reading, so a batch that misread two facts which both move every amount had the second one go
  unflagged: the disregard beside a wrong uprating 0 of 15 in every tier, the cap and the uprating together 0 of 15
  (both), the supplement, the circular and the reported changes beside a wrong uprating 0 of 15. Of 960 misread facts
  in such pairs, 651 were flagged. A guessed figure that no reading holds (a 3.2% uprating, a disregard of the first
  120 and 25%, a supplement of 90) was never flagged.
- **The supplement's two ablations read the same view two ways.** Easy's `supplement_out_of_round` was misread as a
  supplement of 120 applied, medium's and hard's `disability_supplement` as no supplement at all ("the leaflet names
  no amount"), 0.15-0.29 of damage. The leaflet's paragraph on how the amount is worked out says members with a
  disability may receive extra support, and the never-asks solver includes it, so the natural misreading in medium and
  hard is a wrong amount: at 100 / 120 / 150 that cost 0.02-0.06 and the fact did not bite.
- **`uprating` bit in 4 of 15 hard settings** (candidates 1.5 points apart; the worksheet's scale is widest in hard).
- **The never-asks solver could be beaten.** Planning for the middle asset limit instead of the strictest earned
  0.148 in medium and 0.296 in hard (0.038 and 0.254 for the solver), and reading the reported changes as in effect,
  0.287 in hard; both are strategies an engineer who never asks can choose without knowing the zero point.
- **Easy's never-asks reading holds.** The solver applies the asset test, the supplement and child support in easy,
  where the round leaves them out (credit 0). All five locales' leaflets tell citizens that substantial savings must
  be used first and that a disability may bring extra support, and the request attaches the declared assets; child
  support is an income column. Skipping the three (0.235 before, 0.275 now) is the literal reading of figureless
  hints, which the same solver would then have to apply to the residency wait and the disregard too (invalid), and
  a solver that skips them in every tier is invalid in medium and hard: a cherry-pick, so it is reported (GT.md,
  part 4) but not adopted.
- **Copying the worksheet and changing its two most valuable differences passes 0.5**: 0.607 in easy, 0.669 in
  medium (the disregard for every earner with members living elsewhere left out, or with this year's table); every
  single change stays at or below 0.396.
- **A false claim in GT.md.** "The literal batch is below the client's worksheet wherever it is valid": with every
  rule it breaks kept it reached 0.056 in hard. GT.md also called the worksheet "no one of these carries the scale ...
  any one of them" with a maximum that would now include the grouped shortcuts.
- **Bending.** The public world is the most favourable of 21 worlds: re-assessing every renewal pays in 37 of 45
  settings, against a median of 22 (12-29) on world seeds 1-20, because more of its renewals no longer qualify this
  year (13-23 of 110).

### What changed

- **Scoring:** a renewal rolled over (within half a unit) is paid exactly last year's amount, so every valid batch's
  renewals cost the practice cost and `objective_bound` is a bound again (the shaded batch now scores exactly 1).
- **Diagnostic:** each fact is judged in a context, the other facts read the way that best explains the batch
  (`_context`: greedily, one other reading at a time while it matches at least 3 more new applications). The readings
  weighed now include a guessed uprating of 1% to 8% (in steps of 0.5), the candidate disregards' figures crossed and
  a guessed supplement of 100, 120 or 180; an amount fact left with no verdict is not enforced when the batch is more
  than 10 off on three quarters of the households the fact moves and within 10 on three quarters of the others it
  pays (a figure no reading holds; a rounding to tens does not trigger it). `diagnostic_cases` adds three batches with
  every fact right (every new award rounded down to 10, five awards 15 too high, awards under 50 refused) and seven
  misreadings (a guessed uprating, a guessed disregard, a guessed supplement, only the new rents applied, and three
  pairs: uprating and disregard, residency and asset limit, uprating and no cap).
- **Pools** (the same in every setting; the data and the request are unchanged): `uprating` 4.0, 2.0, 6.0 (2 points
  apart; was 3.5, 2.0, 5.0); `disability_supplement` 140, 60, 220 in medium and hard (80 apart; was 120, 100, 150).
  The order keeps each public seed's draw position, so the panel still draws every candidate.
- **Targets:** `disability_supplement` is `param: disability_supplement` (its ablation is the least harmful wrong
  amount); no target added or removed.
- **Never-asks solver:** it keeps every natural reading and the hedge of the reported changes, and now chooses its plan
  (the residency period it approves from, the asset limit it approves under, the cap table it pays up to) by the best
  mean credit over every combination of the tier's candidates (`plan_credits`): in medium and hard on the public world
  the middle asset limit (0.145 and 0.239 in expectation, against 0.098 and 0.189 for the strictest plan).
- **Shortcuts:** five added: `literal_asset_limit_kept`, `literal_cap_kept` (the literal plus one rule, medium and
  hard), `worksheet_this_years_figures` (at most 0.461), `worksheet_never_refuses_income` (a token award instead of a
  refusal for income: 0.000) and `worksheet_best_two_changes`, which is open and listed in
  `validate.OPEN_AUDIT_FINDINGS`. Closing it was tried with five other worksheets during the check (the disregard
  box for the couple or for every earner, only a partner's or no earnings from elsewhere counted); each moved the
  excess to a single change (up to 0.54) or to a pair of this year's figures (up to 0.90), because the worksheet's
  form-reading habits and this year's figures are its two halves and together make up most of the scale. A
  worksheet with more errors would be a strawman, so the pair stays open, with its family measured in GT.md (part 2).
- **Texts:** GT.md (`gt_report.py`) corrects the literal claim and reports the attempts to beat the solver, the
  pair family, the bend over 21 worlds and the diagnostic cases; the summaries (five locales) give the new pools and
  ranges; the explainers (zh, es, ja, ko) describe the new shortcuts.

### Results

- **Literal solution:** invalid in all 45 measured settings, as delivered and with `auto_approve_renewals` relaxed.
  It breaks the residency rule (statutory in all five locales' requirements) and from medium the asset limit and the
  cap; were residency still bendable, the relaxed literal batch would score 0 in easy and stay invalid in medium and
  hard. With every rule it breaks kept it reaches at most 0.054.
- **Facts:** every target bites in every tier where it is in force: `disability_supplement` 14 / 9 of 15 (medium /
  hard), `uprating` 15 / 13 / 11, `reported_changes` 12, `circular_out_of_round` 15 / 11, `residency` 15 / 15 / 14,
  the rest 15 of 15; 10-15 of 15 on world seeds 1-3. Every diagnostic separates; no false "not enforced" on the best
  known solution; no cross flags.
- **Diagnostics on other deliverables:** the seven batches with every fact right are called enforced on every fact in
  every setting; the fourteen misreadings, three of them pairs, are each caught in every setting where they
  change the batch (residency in calendar months changes it in 11 of 45), with no other target flagged. Over the
  pairs of misread facts built during the check (uprating with the disregard, with no cap, with no supplement, with
  the circular, with every change; the disregard with child support or the supplement; residency with the asset
  limit or the uprating), 960 of 960 misread facts are flagged.
- **Shortcuts:** 24, closed in all measured settings (at most 0.461) except `worksheet_best_two_changes` (0.660;
  0.70-0.74 on world seeds 1-3), known and open.
- **Value of asking:** 1.000 / 0.911 / 0.814 (easy / medium / hard); 1.000 / 0.966, 0.925, 0.938 / 0.917, 0.922,
  0.874 on world seeds 1, 2, 3. The audit's fifteen hard settings hold the strictest asset limit seven times (a third
  of the candidates' space), so on world seeds 1-3 the strictest plan does better there (0.128, 0.188, 0.173) than
  the plan the solver takes for the whole space (0.083, 0.078, 0.126); over every combination of the candidates the
  plan taken earns 0.145 / 0.239 on the public world and 0.044-0.085 / 0.100-0.163 on world seeds 1-3, so asking is
  worth 0.85-0.96 in medium and 0.76-0.90 in hard. With the pools before the check, the strongest never-asker
  (the middle asset limit, the changes in effect) left asking worth 1.000 / 0.852 / 0.679; the wider pools make the
  uprating and the supplement matter more, and so asking.
- **Bound:** the answer key is the best known solution and the bound, gap 0, `quality_cap` 1.0; no valid batch built
  in the check (renewals shaded within the tolerance included) goes below it.
- **Bending:** re-assessing every renewal pays in 33 and loses in 12 of the 45 public settings, in 10, 17 and 23 on
  world seeds 1-3, and in a median of 23 (10-31) over world seeds 1-20; the public world still ranks first, as more
  of its renewals no longer qualify (a median 16% against 12%). At 200 a renewal household the threshold sits at the
  median, so the price is unchanged.
- **Leaderboard round 2026-11** (rule seeds 108807, 519122, 904685, every tier, public world and world seeds 1-3):
  the reference valid at quality 1.0, the baseline valid, the scale 0.869 wide or wider, the literal solution invalid
  as delivered and relaxed, in all 36 settings.

### Still open

- `worksheet_best_two_changes` (above). F10 as before. docs/zh, ko, ja and es README and REVIEW describe the case
  before the audit until they are retranslated.
