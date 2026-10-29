# Resume Screening Specialist — `people_hr/resume_screening_specialist`

A growing payments company in Singapore received 250 applications for three open roles (R1 Backend Engineer,
R2 Data Analyst, R3 Security Analyst) and asks the agent to "shortlist the best candidates for interviews". The
request attaches the job descriptions, the applicant export from the recruiting system and data on 360 people
hired for the same roles before. Everything that decides validity and quality (eight per role, the must-haves,
which experience counts, expired certificates, work authorization, one role per candidate, the adverse-impact
check, the managers' bias in the past scores and the referral habit) is in the hidden requirements and has to be
asked for. The deliverable is `shortlist.csv` (`role_id,candidate_id,rank`, 8 rows per role).

The case has no settings: the same problem is scored at every difficulty. The engagement knobs (full spec vs.
clarify first, client persona, data noise, events) apply on top, as for every case (see
[cases/README.md](../../README.md)).

## Data

| File (en) | Content |
|---|---|
| `candidates.csv` | 250 applicants: `applied_roles` (1 or 2 of R1–R3), `application_date`, `location`, `work_authorization` (citizen, permanent resident, valid work pass, needs visa sponsorship), `highest_education`, `graduation_year`, `total_years_experience` (whole career, a trap), `skills` (tags), `languages`, `referral`, and the protected `gender`, `age_band`, `nationality` |
| `work_history.csv` | One row per job: `job_family` and start/end month (`present` = still in the job) |
| `certifications.csv` | One row per certificate with `issued_on` and `expires_on` |
| `past_hires.csv` | 360 hires 2021–2025 with relevant years and certificates at hire, skills, education, protected attributes, referral and `performance_score_1y` (the noise-free fit formula plus noise with sd 4.5 plus the old managers' bias: +6 men, −5 women, +5 under 30, +3 30s, −6 40s, −10 50 and over, +6 Singaporeans, −2 others) |
| `job_descriptions.md` | The three roles, with the must-have and nice-to-have skills in one list |

Data labels are localized in all five locales; ids and numbers are not. 113 applicants are qualified for at
least one role they applied to (R1 39, R2 57, R3 26; 9 for two roles). 15 applicants are referred, 6 of them
qualified.

## Rules

| Rule | Class | What |
|---|---|---|
| `must_have_skills` | contractual | Both must-have skills, the minimum relevant experience (R1 36 months of software engineering, R2 24 of data analytics, R3 24 of information security; start and end month inclusive, `present` through October 2026) and for R3 a CISSP or Security+ valid on 1 November 2026 |
| `work_authorization` | physical | Nobody who needs visa sponsorship on R1 or R3; R2 is remote through an employer of record and exempt |
| `one_role_per_candidate` | contractual | A candidate is on at most one shortlist |
| `adverse_impact` | physical | Among qualified candidates, a gender, age (under 40 / 40 and over) or nationality (Singapore / other) group of 15 or more fails only if its selection rate is below 0.8× the highest group's **and** a two-sided Fisher exact test against that group gives p < 0.05 |
| `referral_boost` | business_policy (may bend) | Every qualified referred candidate is shortlisted (the company habit) |

Quality is the sum of the 24 shortlisted candidates' true fit for the role they are listed under. True fit is
30 + a weight per year of relevant experience above the minimum (capped) + weighted nice-to-have skills + a valid
bonus certificate + education (R2) + Gaussian noise (sd 3), on the 0–100 scale of the past scores without the
managers' bias. The 9 clarification targets are: shortlist size, must-haves, relevant experience, certificate
expiry, work authorization, one role only, the past-hire bias, adverse impact and the referral habit.

## Situations present

- Hidden facts: every rule above, plus how relevant experience and certificate validity are counted. The world
  generator keeps candidates more than one month away from a minimum and certificates away from the cut-off, so
  the counting conventions never decide a qualification (review F5).
- A biased learning signal: the past hires' scores carry the managers' bias, and in the past hires age is built
  from experience, so a regression on the job columns alone is confounded. The requirements forbid demographic
  columns as inputs to the screening score but allow them to measure and remove that bias.
- People who apply to two roles and are strong for both (3 of them on the reference shortlist).
- A bendable company habit: the six qualified referrals sit low in their roles' fit order, so honouring them
  costs about 5% of the objective.
- No dated events, no pressure from a stakeholder and no rule sets (review F3).

## Adverse-impact check: calibration

With 24 places for 113 qualified candidates in groups of about 56, the four-fifths rule on its own flags gaps
of two or three people. The case used to add a one-person tolerance; protected-blind shortlists still failed it
by chance. The check now adds a significance test (the usual combination of practical and statistical
significance): a group below the four-fifths line is flagged only if a two-sided Fisher exact test on the 2 × 2
table (this group and the highest-rate group, selected against not selected) gives p < 0.05. The one-person
tolerance is dropped; in 800 trial shortlists it never changed a result once the test was applied.

Panel: per world, 400 protected-blind near-optimal shortlists built by the reference's greedy assignment from
noisy scores: 200 from the reference's screening score and 200 from the noise-free fit formula, each with
Gaussian noise per candidate and role (sd 0.5, 1 or 2) or every weight multiplied by a random factor (sd 30%).
Biased learners: 200 shortlists scored with the noise-free formula plus 0.5–1.5× the managers' bias plus noise.
The world and the reference are unchanged: the generator still picks worlds whose reference passes the old,
stricter test.

| World seed | Old test passed (reference-based / formula-based) | New test passed | Biased shortlists flagged (old / new) |
|---|---|---|---|
| 20261103 (public) | 340 of 400, 85.0% (183 / 157) | 400 of 400, 100% | 100% / 100% |
| 1 | 341 of 400, 85.3% (149 / 192) | 399 of 400, 99.8% | 100% / 99.5% |
| 2 | 330 of 400, 82.5% (180 / 150) | 399 of 400, 99.8% | 100% / 99.5% |
| 3 | 298 of 400, 74.5% (139 / 159) | 398 of 400, 99.5% | 100% / 100% |

On the public seed the reference passes at a lowest ratio of 0.727 (other nationalities 10/56 against
Singaporeans 14/57, p = 0.49). A regression on the past hires that keeps the protected effects in the score
fails at a lowest ratio of 0.26 (p = 0.001); the validator's example that passes over women fails at 0.15. The
test has less power than the old rule for mild gaps: ranking by the number of nice-to-have skills (lowest ratio
0.46, p = 0.060) now passes, and a quarter of the managers' bias is not flagged in any of the four worlds.

## Reference and baseline (seed 20261103)

The **reference** puts every qualified referral on the role where it scores best, then assigns (candidate, role)
pairs greedily by a plain screening score: relevant years + 1.5 per nice-to-have skill + 2 for a valid bonus
certificate. The **baseline** is what the client does today without an engineer: the same must-have filter,
referral habit and one-role rule, then the most relevant years of experience first, nothing else.

Normalized quality q = (objective − 1226.29) / (1254.49 − 1226.29); the policies' default cap 1.5 is reached at
objective 1268.59 (1.011 of the reference).

| Shortlist | Objective | Ratio to reference | q | Valid |
|---|---|---|---|---|
| Baseline: relevant years only | 1226.29 | 0.978 | 0 | yes |
| Reference | 1254.49 | 1.000 | 1 | yes |
| Random scores, same greedy assignment (200 valid of 211 drawn) | — | 0.851–0.995, mean 0.934 | below 0 | yes |
| Ranking by total years of experience (must-haves kept) | 1203.18 | 0.959 | below 0 | yes |
| Ranking by nice-to-have count | 1285.52 | 1.025 | 2.10 | yes |
| Regression on past hires, capped years, job columns only | 1314.84 | 1.048 | 3.14 | yes |
| Same with the protected attributes as controls (dropped for scoring) | 1328.65 | 1.059 | 3.63 | yes |
| Regression, linear years, job columns only | 1279.46 | 1.020 | — | no: adverse impact (p = 0.037) |
| Regression keeping the protected terms in the score | 1260.09 | 1.004 | — | no: adverse impact (p = 0.001) |
| Noise-free fit formula | 1315.86 | 1.049 | 3.18 | yes |
| Fit oracle (true fit including noise) | 1343.64 | 1.071 | 4.16 | yes |
| Reference without the referral habit | 1316.22 | 1.049 | 3.19 | only with `referral_boost` bent |

On world seeds 1, 2 and 3 the baseline is 0.951, 0.949 and 0.957 of the reference (objectives 1170.98 against
1231.73, 1116.54 against 1176.82, 1140.42 against 1192.18). Nothing in the baseline looks at the adverse-impact
check, so the generator also requires the baseline to be valid; without that it failed the check on world
seed 23 (p = 0.037). On world seeds 1–40 the baseline is 0.913–0.996 of the reference (median 0.961); where it
is within 1% the normalized scale is very steep. Every competent learner lands above the cap, so the quality
component separates the baseline from a reference-level agent but not a good learner from the oracle (review
F1).

## Notes

- Synthetic. Candidates, careers, skills, certificates, scores and the bias sizes are generated; the fit
  weights are design choices. The four-fifths rule follows US practice (the Uniform Guidelines on Employee
  Selection Procedures, 29 CFR 1607.4D, which also say that differences based on small numbers that are not
  statistically significant may not constitute adverse impact), and so does the 40-and-over age split (the
  US Age Discrimination in Employment Act). The requirements call the check a legal requirement while the case
  is set in Singapore, where no such statistical test is known to be law (review F8).
- All numbers on this page come from `case.py` (`_solve`, `check`, `_fit_value`); the panels and regressions are
  an analysis script, not part of the case.
- `validate-case` checks determinism in five locales, the reference at quality 1, the baseline valid and worse,
  one rule-breaking example per rule and world seeds 1–3.
