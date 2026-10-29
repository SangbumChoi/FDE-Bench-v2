# Interview shortlist for three open roles

## Background

We got too many applications for these three roles. Can you shortlist the best candidates for interviews? The job descriptions and the applicant export from our recruiting system are attached, along with some data on people we hired for the same roles before.

The three roles are R1 Backend Engineer, R2 Data Analyst and R3 Security Analyst (see `job_descriptions.md`). Interviews start on 1 November 2026.

## Deliverable

One CSV file, `shortlist.csv`, with the header `role_id,candidate_id,rank`. Exactly 8 candidates per role (24 rows in total), `rank` 1 to 8 within each role (1 = strongest). Ids exactly as in the data (e.g. `R2`, `C017`). A candidate can only be listed for a role that appears in their `applied_roles`.

## Data notes

- `candidates.csv` has one row per applicant; `applied_roles` lists the roles they applied to, separated by `;`, and `skills` lists their skills the same way. `work_history.csv` has one row per job, `certifications.csv` one row per certificate. `past_hires.csv` covers the 360 people we hired for these three roles from 2021 to 2025.
- **Must-haves** (hard filter; a candidate who misses any of them cannot be shortlisted for that role):
  - R1: the skills Python and SQL, and at least 36 months of relevant experience.
  - R2: the skills SQL and statistics, and at least 24 months of relevant experience.
  - R3: the skills network security and SIEM, at least 24 months of relevant experience, and a valid CISSP or CompTIA Security+ certificate.
  - Every other skill named in the job descriptions is nice-to-have: it makes a candidate stronger but is not required.
- **Relevant experience** only counts jobs in `work_history.csv` whose `job_family` matches the role: `software engineering` for R1, `data analytics` for R2, `information security` for R3. Other jobs do not count. `total_years_experience` in `candidates.csv` adds up every job of the career and must not be used for this. A job's length in months counts both the start and the end month (2021-03 to 2023-02 = 24 months); `end_month = present` means the person still holds the job, counted up to and including October 2026.
- **Certificates** count only if `expires_on` is 1 November 2026 or later. An expired certificate counts for nothing: neither for the R3 must-have nor as a plus.
- **Work authorization**: R1 (hybrid, in our office) and R3 (on site, in client data centres) need people who are already allowed to work in Singapore: `citizen`, `permanent resident` or `valid work pass`. Candidates with `needs visa sponsorship` cannot be shortlisted for R1 or R3. R2 is fully remote through an employer-of-record partner, so work authorization does not matter for R2.
- **One role per candidate**: some people applied to two roles and are strong for both. Each candidate goes on at most one shortlist; put them where they help most.
- **Past hires**: `performance_score_1y` is the performance score each hire received after one year (0-100). It is our best signal of what makes someone strong in these roles; `relevant_years_at_hire` and `certifications_valid_at_hire` were recorded with the same rules as above. Be careful: an internal audit found that these scores were given by managers who systematically rated men, younger staff and Singaporeans higher. The demographic columns must not be inputs to the screening score, but you may use them to measure and remove the managers' bias from the past scores.
- **Protected attributes**: `gender`, `age_band` and `nationality` are in the export only because the system exports everything. They must not be used to score or rank candidates, and neither may obvious stand-ins for them such as `graduation_year`, `languages` or `location`.
- **Referrals (our habit)**: every candidate with `referral = yes` who meets all the must-haves of a role they applied to (including work authorization where needed) gets an interview: put them on that role's shortlist (if they qualify for two roles, either one). Referred candidates who do not meet the must-haves get no special treatment.

## How the shortlist is judged

**The file must have the right shape**: exactly 8 rows per role, ranks 1-8 once each, known ids, and only roles the candidate applied to. Otherwise it cannot be scored at all.

**Hard constraints** (if any is broken, the shortlist does not count):

- Every shortlisted candidate meets the must-haves of the role they are listed for.
- Nobody who needs visa sponsorship is on the R1 or R3 shortlist.
- No candidate appears on two shortlists.
- Adverse-impact check (legal requirement): take all candidates who are qualified (meet all must-haves, including work authorization where required) for at least one role they applied to. A group's selection rate is the share of its qualified candidates who are on any shortlist. The groups compared are: gender as recorded; age under 40 against 40 and over; Singapore nationality against all other nationalities together. Groups with fewer than 15 qualified candidates are not tested. A tested group fails the check only if both of these hold:
  - its rate is below 0.8 times the highest rate for the same attribute (the four-fifths rule);
  - the gap is statistically significant: a two-sided Fisher exact test on the 2 × 2 table of this group and the highest-rate group, selected against not selected, gives p < 0.05. With groups of this size a gap of one or two people can be chance; the test flags only gaps that chance does not explain.
- Every qualified referred candidate is shortlisted.

**Quality**: the sum, over the 24 shortlisted candidates, of each one's true job fit for the role they are listed under, on the same 0-100 scale as `performance_score_1y` but without the managers' bias. The order within a role does not change the score, but we will invite people from the top down. Higher is better.
