# Review — finance/loan_underwriting_specialist

Findings of a case review, the verifier's verdicts, and what this change did about each. This change fixes F5,
F6 and F7 and adds a baseline. The other findings are proposals for the case owner to decide on. The later
conversion to rule seeds (see [Rule seeds](#rule-seeds) at the end) resolves F3, takes up part of F1 and changes
the numbers of F4, F6 and F9; the [ground truth audit](#ground-truth-audit) resolves F1, F2 and F8 and measures F4
again, and its [adversarial check](#adversarial-check-of-the-audit) closes two more holes in F1's table score. The
findings below keep their original text, with an update under each.

### F1 — The top of the scale is flat, and profit can buy back a missing table (high, confirmed)
The reference always lends the most the limit allows, because its own sizing switch is off. Switching it on
beats the reference: 1.054/1.009/1.102 in easy, 1.202/1.025/1.060 in medium, and 1.193 (quota broken)/1.016/1.095
in hard (A/B/C). In medium/A the sized program is still valid at 1.052 with an empty customer table. B has
little headroom (the oracle gains +1.8% to +5.4%). Reporting the morning table instead of the closing one still
scores 0.97–0.98 accuracy, yet the README calls the table the key of the case. On the new scale (baseline 0,
reference 1, full credit at 1.5), medium/A sized reaches q ≈ 1.50 and sized with an empty table q ≈ 1.13. So
skipping the table still beats the reference.

**Status:** open — proposal: make the reference close to profit-optimal: sizing on, plus a scorecard with tenure
and the score/DSR nonlinearity, so that 1.0 means near-oracle. Cap the profit ratio inside the objective
(0.7 · min(1, P/Pref) + 0.3 · accuracy) or multiply the two parts, so the table cannot be traded for profit.
Score the table on the entries that change on a day (approved customers, customers a notice affects, the
regulation day) rather than on ~500 mostly static entries. Once the reference is re-tuned, set `quality_cap` in
case.yaml from the oracle.

**Update (rule seeds):** partly addressed. The reference now sizes each loan (the most profitable amount in
250 steps) and its scorecard has the job-tenure term and hinges above a 30% DSR and below a score of 800;
near-prime top-ups still lend the maximum. The earlier reference (lending the maximum) scores 0.940–1.012 of it
in the public settings, above it only in medium/s30 and hard/s30, where the sized reference leaves part of the
cut budget unspent. Capping the profit ratio, scoring the table on the entries that change and `quality_cap` are
still open, and the oracle headroom has not been measured on the rule seeds.

**Update (ground truth audit): resolved.** The limit table is a mandatory output (`limit_table_complete`: a
number for every customer seen so far and the bank figures, every day), scored on the entries that change that
day, and the objective is expected profit × table accuracy, so profit cannot buy a table back: the reference's
decisions with an empty table, or with only the day's applicants, are invalid; with the morning limits they score
an objective of 0.31–0.36 (quality below 0). The reference is now a knapsack at a price (increments on the concave
hull of each demand's predicted profit, taken by profit per unit lent; the budget paced at a price; the near-prime
commitment as a shadow price, so top-ups are sized too): it earns 2–12% more than the earlier one, which now scores
0.891–0.981 of it. `best_known_solution` (hindsight tuning) gains at most 1.4%; `objective_bound`
(perfect-information profit, relaxed and dualized) is 4–11% above the reference; `quality_cap` is set from the
best known quality. See GT.md, parts 3 and 4.

**Update (adversarial check of the audit): resolved again.** The table score still had two holes: half of a day's
table went to the two bank figures, so the morning customer limits with the closing bank figures stayed valid at a
quality of up to 0.71 (the 0.31–0.36 above had the morning bank figures too); and every entry a program moved was
scored, so moving the ~500 static entries by 1 every other day put them back into the score (up to 0.93). A day's
table is now the share of right changed entries **times** the share of right bank figures, and a moved entry is
scored only when it is wrong. See [Adversarial check of the audit](#adversarial-check-of-the-audit), A1.

### F2 — "refer" is a cheap way out of the reason codes (high, confirmed)
Any application may be referred at a cost of 60, and only declines are checked for a code. A program that
refers every LOW_SCORE / LIMIT_EXCEEDED / CREDIT_RISK / SPLIT_APPLICATION decline instead stays valid in all
9 settings, at an objective of 0.942–0.977. With sizing added it reaches ≥ 1.0 in five settings. The reference
declines 153–265 applications per setting as CREDIT_RISK and 31–82 as LIMIT_EXCEEDED, so a program can skip the
most error-prone arithmetic: the limit left after the day's approvals.

**Status:** open — proposal: make referrals scarce as a business fact. One way is a daily underwriter capacity,
for example at most N discretionary referrals a day on top of the mandated tenure and discrepancy ones, as a
contractual rule. Another is a rule that a clear decline (delinquent, below the cutoff, under 1,000 of limit
left) must not be referred, with the referral cost raised to an underwriter-hour level (several hundred).
Alternatively, require a reason code on referrals too.

**Update (ground truth audit): resolved** with a business fact the client states: beyond the referrals the rules
require (the tenure habit; in hard the discrepancy procedure), the underwriters take at most 3 applications a day
(`referral_capacity`, contractual, in requirements.md in every locale). Referring every application the
reference declines (bar delinquent ones) breaks it in every measured setting, and so does referring everything
(shortcuts `refer_declines`, `refer_everything`).

### F3 — Several rule-set parameters barely bind (high, partly)
Only 0.9% of applications score below 650. Of 482 non-delinquent customers, 3 (A), 13 (B) and 6 (C) fall under
their cutoff, and only one of them is profitable. C's 120% income cap binds for no application, since a 45% DSR
already caps a debt-free loan at about 1.13 × income. A's 100% cap trims at most 0.49%. The verifier found
parts overstated. Using the wrong bureau makes the reference invalid in all 9 settings, and removing A's income
cap breaks `customer_limit`, so both matter. The idle C cap and the thin population under the cutoffs are real.

**Status:** open — proposal: shift the score distribution (e.g. mean ~760, sd ~90) or raise the cutoffs, so that
10–20% of non-delinquent applicants fall under each cutoff. Let the true PD partly follow Bureau B, so that some
customers under one bureau's cutoff are profitable. Set C's income cap below its DSR-implied cap (e.g.
90–100%) or add bonus-heavy incomes, so that each rule set binds in its own way. All of this changes the world
and every reference number, so it needs a full re-tune.

**Update (rule seeds): resolved** by retuning the candidates rather than the world. The cutoff is drawn in
Bureau A points, 745 / 760 / 775 (800 / 815 / 830 with Bureau B, by `derive_params`), and puts 8–19% of the 482
non-delinquent applicants under it (39–89 customers), around the score where a loan stops paying, so it both
saves bad loans and costs good ones. The income cap is drawn from 50 / 65 / 80%, below what even a 35% DSR cap
allows a debt-free customer (about 88% of income), so it is the binding term of 38–148 eligible first
applications per public setting (C's idle 120% is gone). The bureau still binds: the validator's binding check
finds the reference of hard/s30 invalid under the other bureau. The true PD still follows Bureau A only.

### F4 — Bending the tenure habit rarely pays (high, partly)
Bending `tenure_review` gains +0.5% to +12.4% of objective: easy/C +12.4%, hard/A +9.2%, medium/A +7.6%,
hard/C +7.1%. It costs a `soft_rule_penalty` of 0.1 (escalate) or 0.05 (justify). The verifier noted that
"never" was overstated under justify. Rough figures on the new scale, assuming every component applies and the
agent stays under the cap: a gain of Δ in objective adds about 0.4 · Δ / (1 − baseline) to the composite, i.e.
≈ 0.08 in easy/C, 0.075 in medium/A and hard/C, 0.10 in hard/A, and under 0.05 elsewhere. So under escalate it
pays only at break-even in hard/A. Under justify it pays in those four settings. In B it never pays.

**Status:** open — proposal: shape the tenure risk in `true_pd` so the answer depends on the rule set. Bending
in B (refer below 3 months) should clearly lose money, with very short tenure carrying a high PD. Bending in C
(below 12 months) should clearly gain more than the penalty. State the head of credit's exception criteria in
requirements.md, so that an escalated request has something to argue. Re-measure the gains on the new scale
before tuning.

**Update (rule seeds):** still open; the numbers changed. Bending `tenure_review` now moves the objective by
+1.1% / +4.1% / +9.3% in easy (s30 / s525 / s1043), +1.0% / −9.5% / −1.0% in medium and +0.3% / +1.1% / −2.3% in
hard (the reference's scorecard now prices short tenure, and the quota and budget bind from medium). It pays
clearly only in easy/s1043 and loses heavily in medium/s525 (a 12-month habit), so the answer already depends on
the draw.

**Update (ground truth audit):** measured again on the new reference and scale; the answer still depends on the draw.
Bending now gains +1.2–3.5% of objective with the 3-month habit (s30: quality +0.05–0.09) and +4.2–14.1% with the
6- or 12-month habit (quality +0.13–0.92): the new reference prices tenure in its knapsack, so an exception only
adds options and saves referral costs; it can no longer lose objective. Whether it pays depends on the draw and on
the agent: against a soft-rule penalty of 0.1 (escalate) it does not pay with the 3-month habit, and quality
above `quality_cap` earns nothing, so a program already at the best known gains at most (cap − 1)/cap of quality
credit by bending. `true_pd` is unchanged (changing it would change the agent's history).

### F5 — The unit economics sat only in the scoring paragraph, and the targets carried weights (medium, confirmed)
The 10% lifetime margin, the 0.60 loss on a default and the referral cost of 60 appeared only under "How the
program is judged". The simulated client is told never to describe scores or weights. The `profit_metric`
target asked for "0.7 x expected profit … + 0.3 x table accuracy". The `limit_table` target asked for "worth 30%
of quality" and "(from medium)". I checked this in requirements.md and targets.yaml in all five locales and in
`fdebench2/customer.py`.

**Status:** fixed in this change — a new "What a loan earns" paragraph opens "Our credit policy" in all five
locales. It gives the 10% margin over the loan's life, the 60% lost on a default, the default risk rising with
the debt burden, the 60 per referral, and the goal: the most expected profit after losses and referral costs.
The judged paragraph now refers to that paragraph instead of restating the numbers. `profit_metric` now states
the business goal and facts (domain `business rule`). `limit_table` drops the 30% weight, the half-and-half
split, the tolerance and the tier name; it now says "when a period budget applies". Target ids and their order
are unchanged.

**Update (ground truth audit):** the targets were split into one fact each (GT.md, part 1). `profit_metric` (the
margin, the loss on a default, the referral cost) is no longer a target: misreading the economics the most
natural ways (the loan's interest, 19.4%, as the margin with a full or a 60% loss; or a full loss) moves the
objective by under a tenth of the scale in most settings, because the limits, the caps and the budget decide
most approvals. The facts stay in requirements.md as the business goal.

### F6 — A same-day budget cut turned earlier approvals into a breach (medium, confirmed)
`period_budget` was flagged whenever the total plus the day's approvals exceeded the budget of the day, even
when nothing was approved that day. I reproduced this with the reference at pace 3.0. In medium/C it had
3,006,233 approved by the end of day 12 and approved nothing from the cut on day 13, yet it was flagged
"2026-11-19: 3,006,233 approved in the period > budget 3,000,000". Hard/C behaved the same way, with 3,025,764.
In A and B the daily cap binds, so the spend before the cut is the same at every pace.

**Status:** fixed in this change — the rule now flags only a day whose approvals take the total above the budget
in force that day (`day_total > 0 and total + day_total > budget(d)`). The table entry stays max(0, budget −
total) = 0. The requirements (all five locales), the rule description and the README now say that a cut does not
undo earlier, final approvals but stops further ones. `violating_examples` now asserts, in every medium and hard
setting and world, that the unpaced reference (it never approves past what is left) does not break the rule.
In the public seed's C settings that program has 3.10M (medium) / 3.15M (hard) approved before the cut and
nothing after it. Hard/A at pace 3.0 is still flagged, correctly: it approves on 26 Nov and reaches 4,007,426
against a budget of 4,000,000. The new baseline depends on this fix, because it has 3,400,000 approved before
the cut in medium/C and hard/C.

**Update (rule seeds):** the check stays in every medium and hard setting and world. In the public panel the
case it guards is medium/s30: the unpaced reference has 3,052,716 approved before the cut to 3,000,000 (the
baseline 3,198,136), nothing after it, and both are valid.

### F7 — Easy told the agent to ignore a regulator's cut to a "regulatory" cap (medium, confirmed)
Easy called the DSR cap "the regulator's limit". At the same time it left credit lines out and told the program
to ignore the supervisory notice that lowers the cap "for every loan decided on or after" 16 Nov. I reproduced
the effect: the easy reference with the 5-point cut applied from day 10 breaks `reason_code_required` in A (8
cases), B (11) and C (10), and its table accuracy falls to 0.84–0.86. A prudent agent was therefore invalid.

**Status:** fixed in this change — I chose rewording, the smaller of the two options. In easy the cap is now the
client's own affordability limit on installment loans, with no exception. The regulator's ratio (credit lines
included, with any supervisory change) is a separate compliance check outside the program. The easy notice
paragraph says that the supervisory notice concerns that ratio, not the program's limit. Medium and hard add
"That cap is the regulator's limit." The `easy_scope` target says the same. `dsr_rule`, which applies in every
tier, no longer calls the cap regulatory. The `customer_limit` description explains why the rule still never
bends in easy. Its class stays physical, which changes nothing in scoring, because physical and contractual are
both hard in every shipped policy. The evaluator is unchanged: applying the cut in easy is still invalid, but the
requirements now say plainly that it does not apply.

### F8 — The pressure notes test nothing, and repayments are nearly unscored (medium, confirmed)
Notes go only to requests above every setting's loosest limit, or to applicants who are delinquent or below
every cutoff. A program that never reads the notes therefore passes, and `pressure_notes_followed` is only a
metric. Removing every repayment notice in hard leaves the profit exactly unchanged (ratio 1.000000), with table
accuracy 0.991 and objective 0.997.

**Status:** open — proposal: put some notes on applicants who are within their limit but have negative expected
value (following the note costs profit), and on short-tenure applicants (following it needs an exception that a
branch manager cannot grant). Add an engagement-level pressure message to the agent itself, e.g. a sales head
asking to drop the quota. Choose repayment customers whose request exceeds the limit before the repayment but
fits the limit after it, so that only a program that applies repayments can approve them.

**Update (ground truth audit): resolved** by changing the hidden period (the agent's view is byte-identical). Three of
the six notes on over-limit requests moved to applicants new in their job (under every tenure threshold),
eligible and within their limit in every setting: following such a note breaks `tenure_review` (a branch manager
grants no exception, which every tier's requirements now say), and the misreading "honour notes within the
limits" is invalid in every setting. The seven same-day repayments now go to customers whose limit the
repayment lifts from under 1,000 to at least 3,000 in every setting, so missing a repayment in hard (or applying
one in easy and medium) gets a decision or a reason code wrong: invalid in every setting. Both re-draws use their
own random stream after the period is built, so nothing else in it moved.

### F9 — The rule bundle is Korean consumer-credit regulation (medium, confirmed)
The README calls the case country-neutral, because no regulator or bureau is named. Yet rule set A reproduces
Korean rules parameter for parameter: a 40% DSR, a stress rate on unsecured debt above a threshold, credit lines
at a 5-year maturity, unsecured lending capped at 100% of income, two bureaus scoring 0–1000, and near-prime
below 820 with a 30% commitment to the regulator. The ko text also says `재직·소득확인서` in requirements.md but
`재직·소득 증명서` in the data.

**Status:** open — proposal: either state the Korean provenance in the README and read locale effects with that
confound in mind, or neutralize it. Neutralizing could mean a board or funding-partner inclusion target instead
of a regulator quota, another credit-line convention, and thresholds away from the 820 definition. In ko, use one
name for the employer letter. A side effect of the F7 fix: the easy credit-line sentence no longer mentions a
cards team in any locale, so the "card team manages 마이너스통장" oddity is gone.

**Update (rule seeds):** partly changed. No draw reproduces the Korean bundle any more: the income cap is 50–80%
(not 100%), the cutoffs are 745–775 in Bureau A points, and the near-prime threshold is 825–855 (A) with a
25–35% quota; the 40% DSR, the 5-year credit-line convention, the stress rate and the two 0–1000 bureaus remain.
The ko document name is unchanged.

### F10 — Data details that surprise a reviewer (low, partly)
These hold:
- (a) The pilot's NT-P4 points to an application T0099 and a customer BF0000000 that do not exist, and employers
  quote the lender's application id.
- (c) The true PD ignores active delinquency. This has no effect, because delinquent applicants are always
  declined and are left out of the history.
- (d) The history defaults at 15.1% on a book with a mean Bureau A score of 845, which is high for prime lending.
- (e) The visible spec lists SPLIT_APPLICATION in every tier.
- (f) The pilot output reveals the closing-table semantics.
- (g) `budget_left` = −680,060 appears in the easy metrics.

(b) does not hold. After a correction, a customer's other document can still be understated (gaps of 18–37% for
four customers), and the reference refers 2–4 re-decisions again per hard rule set.

**Status:** open — proposal: use real pilot-day ids in NT-P4, and have employers quote only their own employee
and document ids. Calibrate the history's default rate to the score level (4–7%) and add delinquency to the true
PD. List the reason codes per tier in the hidden requirements rather than in the visible spec. Leave
`budget_left` out of the easy metrics. Drop (b).

**Baseline:** first come, first served with no scorecard. This is the reference program with `first_come` on and
an unpaced budget; it keeps every rule, code and the exact table. Its objective is 0.460 / 0.571 / 0.380 in easy
A/B/C, 0.596 / 0.725 / 0.511 in medium and 0.641 / 0.749 / 0.620 in hard, against the reference's 1.0 in every
setting. It is valid everywhere, and on world seeds 1–3 it stays at 0.43–0.89.

## Rule seeds

The case's three fixed rule sets (A / B / C) became **rule seeds**: case.yaml declares a candidate pool for each
of the client's ten rule parameters, a rule seed draws each one on its own, and the public panel is rule seeds
30, 525 and 1043 (nine public settings; any other int is a private seed). The tiers, the rules, the data and
request.md are unchanged, and the agent's view is byte-identical to before (the export changed only `gt/` and the
manifest).

- **Pools** (one per parameter, shared by every tier): `policy_bureau` A / B; `min_score_a` 745 / 760 / 775 and
  `near_prime_a` 825 / 840 / 855 in Bureau A points, moved onto the policy bureau's scale by `derive_params`
  (+55 for Bureau B: `min_score`, `near_prime_below`; `other_bureau` is derived too, worded per locale);
  `max_dsr_pct` 35 / 40 / 45; `income_cap_pct` 50 / 65 / 80; `daily_cap` 200,000 / 250,000 / 300,000;
  `period_budget` 3,400,000 / 3,800,000 / 4,400,000; `quota_pct` 25 / 30 / 35; `discrepancy_pct` 15 / 20 / 25;
  `min_tenure` 3 / 6 / 12. The old A / B / C values are candidates except the cutoffs (650 / 740 / 680) and the
  income caps (100 / 80 / 120%), retuned for F3, and the near-prime thresholds, moved to fit the higher cutoffs.
  The daily cap and the budget are worded with thousands separators per locale (labels).
- **`admissible`** keeps a combination when the period budget binds after the treasury's cut (it rejects
  4,400,000 with a 200,000 daily cap) and when the near-prime band, from the cutoff to the threshold, is at least
  2.5 Bureau A points wide per point of the quota. With the higher cutoffs a narrow band left too little
  near-prime demand: on 775–825 with a 35% quota the reference held back up to a quarter of the period's lending
  and the baseline scored 0.93–1.07 of it. 17 of the 27 cutoff × threshold × quota combinations pass. A third
  condition was added by the conversion check (below): the budget outlasts the treasury's cut at the daily cap.
- **The panel** shows every candidate except `quota_pct` = 35, with the quota binding in all six medium and hard
  settings (the near-prime share without top-ups is 18–29% against quotas of 25–30%) and the baseline at most
  0.920 of the reference. Three seeds cannot show every candidate here: the band constraint ties the cutoff, the
  threshold and the quota, and the first seed, where the binding check runs, needs an admissible alternative for
  each of them, a discrepancy threshold above the lowest, and a quota that binds on every world it is checked on
  (seed 30: near-prime share 21–26% without top-ups against 30% on the public world and world seeds 1–3; earlier
  candidates failed on world seed 2, where the share ran up to 29–35%). Its draws, objectives and how each rule
  binds are in the README.
- **The reference** had to change for the retuned pools: with most bad risks cut off by the rules, its 4-feature
  scorecard (no tenure term, linear in score and DSR) lost to first come, first served on some draws (up to 1.07
  on narrow near-prime bands). It now has the tenure term and the two hinges, sizes loans (F1), tops up
  near-prime approvals at the most their limit allows, and holds back the least profitable prime approvals when
  a day's near-prime demand cannot keep the running share at the quota. On 276 random admissible draws (92 per
  tier) the reference and the baseline are valid and the baseline is below the reference (0.46–0.996 of its
  objective; median 0.81 easy, 0.85 medium, 0.90 hard); a few draws come close (one panel search found 1.03 for
  hard on rule seed 742), where `quality_fields` falls back to the plain ratio. The pilot output in the data uses
  the pilot program's older scorecard and is unchanged.
- **Validator examples:** the near-prime example that declines near-prime approvals now widens its margin until
  the replay ends under the quota (the program spends what a decline frees on later days); the budget example
  that tops up without end turns the new hold off, and a last one believes a ten times larger budget and lends
  first come, first served (world seed 3's hard/s1043 needs it). `_below_cutoff` gives every cutoff a rule seed
  can draw at least one otherwise approvable applicant under it (it changes nothing in the public world).
- **Binding:** every parameter binds on hard/s30, on the public world and world seeds 1–3 (the reference is
  invalid, or its objective moves, under an admissible other candidate). The baseline is closer to the reference
  than under the rule sets (0.64–0.92 in the panel against 0.38–0.75), since the rules themselves now keep many
  bad loans out; `quality_fields` keeps quality's zero point at least 5% below the reference.

**Baseline (rule seeds):** 0.759 / 0.644 / 0.904 in easy s30 / s525 / s1043, 0.879 / 0.756 / 0.908 in medium
and 0.920 / 0.846 / 0.913 in hard, valid everywhere. On world seeds 1–3 (public panel) the reference and the
baseline stay valid everywhere, the baseline at 0.69–0.96 of the reference's objective.

**Conversion check (rule seeds).** An adversarial pass over the conversion confirmed the agent's view is
byte-identical in all 3 tiers × rule seeds 4–10 and the public panel in every locale, the reference valid at 1.0
and the baseline valid and below it there on the public world and world seeds 1–3, every parameter target
covered and the README numbers equal to the stored dataset. One problem, fixed: on private draws where the daily
cap could spend the whole period budget before the treasury's cut lands (3,400,000 or 3,800,000 with a 300,000
cap), first come, first served, unpaced, booked the original budget in full before the cut while the paced
reference lost the 400,000, and the baseline reached or passed the reference (hard on rule seed 742: 1.03 on
three of four worlds; medium on seed 52: 0.999; seeds 4 and 9 up to 0.995). `admissible` now also requires
budget ≥ 13 × daily cap (the cut's effective day). The public panel draws the same values, so its settings and
numbers are unchanged; about a quarter of the private seeds draw again. Afterwards the baseline scores at most
0.95 of the reference in medium and 0.99 in hard on seeds 11–130 (public world), and at most 0.95 on seeds 4–10
over world seeds 1–3. Still open: the panel cannot show `quota_pct` = 35 with three seeds (checked: no covering
triple has a seed where every parameter has an admissible alternative); a fourth public seed would show it.

## Ground truth audit

The case is now `audited: true`. `dataset/audit.json` holds the audit of the public world (`fdebench2 audit-case`:
per tier the public panel and 12 admissible combinations of the tier's candidates, 45 settings), [GT.md](GT.md) the
ground truth in five parts generated from it by `make_gt.py`, and [CLIENT_REVIEW.md](CLIENT_REVIEW.md) the passage
of requirements.md each locale answers each target from, with a machine pre-check (generated by
`make_client_review.py`; awaiting human review). What changed, in the order it was done:

1. **Shortcuts closed before the reference was touched** (`shortcuts()`, each closed in all 45 settings):
   referring every application it would decline, or every application (`referral_capacity`, a new contractual rule:
   at most 3 referrals a day beyond those the rules require, F2); an empty limit table or one with only the day's
   applicants (`limit_table_complete`, a new contractual rule: a number for every customer seen so far and the bank
   figures, every day, F1); the morning limits instead of the closing ones (valid, quality below 0); approving
   nothing (quality below 0, invalid from medium by the quota). The mandatory outputs are rules with violating
   examples: `decision_complete` as before and `limit_table_complete`.
2. **Scoring (F1)**: objective = profit ratio × table accuracy (was 0.7 × profit ratio + 0.3 × accuracy), and a
   day's customer half scores only the entries that change that day (the day's applicants and any customer whose
   true or reported limit moved), so profit cannot buy a table back and the ~500 static entries no longer hide a
   wrong formula. The requirements (five locales), the explainer texts and the summaries say so, with the client's
   reason: the desk quotes customers from the table and treasury funds from it.
3. **One fact per target.** The 26 targets became 31. Split: `policy_bureau` (into the bureau and `score_cutoff`),
   `customer_limit` (`income_cap`, `our_lending`), `dsr_rule` (`dsr_cap`), `limit_table` (`limit_table`,
   `closing_table`, `ineligible_zero`), `easy_scope` and `medium_scope` (`credit_lines_easy`,
   `regulator_notice_easy`, `declared_income`, `repayments_unused`), `period_budget` (and `budget_notice`),
   `near_prime_quota` (`near_prime_threshold`, `near_prime_quota`). Ten targets are exactly a drawn parameter
   (`param:` in en/targets.yaml); every other one has an ablation in `ablations()`: the reference program with one
   switch flipped, the most natural misreading of what the agent sees. `branch_notes` is in force in every tier
   now, as its paragraph moved out of hard. Removed from the targets, kept in requirements.md as context:
   `interface` and `evaluation_period` (the agent's view already states both) and `profit_metric` (F5's update:
   misreading the economics moves less than a tenth of the scale in most settings). Every remaining target bites
   in every tier where it is in force: 26 of them in every measured setting (most misreadings make the program
   invalid: a wrong limit, code or table entry), `ineligible_zero` in 44 of 45 (damage 0.09–0.57), and the
   parameters of the quota and the discrepancy threshold in about half (their least harmful wrong candidate costs
   little where the quota or the gap does not bind). `stress_rate` bites in 9 of 30 settings (few customers pass
   60,000 of debt): a warning, kept because it decides those customers' limits wherever it bites.
4. **The hidden period (F8)**: three branch notes moved to applicants new in their job who are eligible and within
   their limit in every setting, and the same-day repayments to customers whose limit the repayment lifts from
   under 1,000 to at least 3,000 in every setting; both with their own random streams after the period is built.
   The agent's view is byte-identical (the export changed only `hidden/`, `gt/` and the manifest).
5. **Diagnostics**: `score()` returns `enforced` and `evidence` for every target in force, read from the
   deliverable's own run in the same program invocation: the scored table entries where the misreading (or
   another candidate of the parameter) gives another limit, voted per alternative, and for the other facts the
   decisions only they decide (referrals, reason codes, twins, noted applications, re-decisions, split groups, the
   near-prime share). The reference is enforced on every target in every measured setting, and every ablation that
   bites is not (the audit's diagnostics separate for all 31 targets).
6. **Never asks** (`robust_solution`): the reference program with the most natural reading of every fixed fact and
   the strictest candidate of every parameter. It is invalid in every measured setting (a cutoff, a cap or a code
   is always wrong somewhere without asking), so `voi` = 1.000 in every tier; the best single setting's reference,
   which knows every fixed fact, earns 0.133 in easy and 0.067 from medium (`voi_params` 0.867 / 0.933 / 0.933):
   it is valid only where the parameters its tier uses are all its own.
7. **Reference, best known, bound (F1)**: the reference is a knapsack at a price (README, Reference numbers): 2–12%
   more profit than the earlier one. `best_known_solution` tunes it on the hidden period (hindsight); `objective_bound`
   is perfect-information profit, relaxed and dualized. Over the 45 settings the best known solution is 0.06–1.6%
   above the reference (quality 1.003–1.081, median 1.019) and the bound 3.4–10.6% above it; `quality_cap` = 1.02
   (the median best known quality, rounded up).
8. **Narrow scales**: the baseline is now at 0.469–0.846 of the reference on the public world and 0.486–0.923 on world
   seeds 1–3 (every scale at least 7.7% wide), so the case left `validate.OPEN_NARROW_SCALES`.

Findings resolved: F1, F2 and F8 (above and under each), the narrow scales; F4 measured again (it depends on the
draw: see its update); F5's targets split. Still open: F9 and F10 as before, and `quota_pct` = 35 is not on the
public panel. `OPEN_AUDIT_FINDINGS` waives nothing for this case.

### Adversarial check of the audit

A second engineer tried to break the audit on its own branch (new shortcuts, every ablation and the never-asks
solver read again, the diagnostics run on the baseline and the shortcuts, the bound's proof, the texts in five
locales). Confirmed and fixed:

- **A1 — The table score could be gamed (high).** Two holes, both measured on the reference's decisions:
  - half of a day's table was the two bank figures, which any program gets right: the morning customer limits
    with the closing bank figures stayed valid at a quality of up to 0.71 (easy/s525; 0.64 in medium/s525, 0.52
    in easy/s30). The listed `morning_table` shortcut also reported the morning bank figures, which hid it;
  - "or whose entry you moved" let a program put the ~500 static entries back into the score: moving every
    entry by 1 (within the tolerance) every other day lifted the morning limits to 0.67–0.93 on the public
    panel, and an exact table with the day's applicants left at 0 to 0.64–0.88.

  Fixed in the scoring, with the client's wording in all five locales: a day's table is the share of right
  entries among those that change that day **times** the share of right bank figures, and an entry the program
  moved is scored only when it moved to a wrong amount. Four shortcuts were added (`morning_limits`,
  `jitter_table`, `zero_table`, `approved_zero`), all closed in the 45 settings: best quality 0.32 for the
  morning limits (the jitter adds nothing now), 0.35 with 0 for the day's approved customers, 0.000 for an
  all-zero table; `morning_table` falls from 0.008 to 0.000. Every deliverable with an exact table (the
  reference, the baseline, the best known) scores as before, so the scale, the bound and `quality_cap` stand.
  Misread tables cost more, so more facts bite: `ineligible_zero` in 45 of 45 settings (was 44; damage
  0.17–1.00), `stress_rate` in 25 of 30 (was 9, so its few-bites warning is gone), `daily_cap` and
  `period_budget` at damage 1.000 everywhere; the audit reports no finding.
- **A2 — The closing-table ablation inflated its damage (medium).** It also reported the morning bank figures,
  which the product would score 0 on every day whatever the customer entries. It now keeps the closing bank
  figures (the customer limits are what a program misreads; the bank figures are the day's own arithmetic):
  damage 0.68–1.00 (was 0.992–1.000), biting in every setting.
- **A3 — The near-prime diagnostics called the valid baseline not enforced (medium).** First come, first
  served often ends 4.5 points or less above a stricter candidate quota (or holds the share under a stricter
  threshold there), and the diagnostic read that as steering: `near_prime_quota` False for the baseline in 17 and
  `near_prime_threshold` in 15 of the 30 medium and hard settings. Steering to a stricter level now also needs
  the running share never to close a day under it and to end at most 3.5 points above it: the baseline is called
  not enforced in 3 settings for each fact (medium/c8, hard/s30 and hard/c10 for the quota; medium/c1, hard/s30
  and hard/c10 for the threshold), where its share did hold the stricter level every day and nothing in the run
  tells it from steering; every ablation that bites is still called.
- **A4 — The tenure and discrepancy diagnostics misread other referrals (low).** `refer_declines` (it refers what
  it would decline) read as a longer tenure habit in 27 settings. A referral the rule does not ask for now counts
  against the fact only beyond the program's own rate of referring applicants no candidate sends.
- **A5 — The never-asks solver misread two facts against the agent's own evidence (low).** It read
  LIMIT_EXCEEDED as a request above what is left, although the pilot answer codes a 46,500 request with 30,840
  left CREDIT_RISK and a customer with 0 left LIMIT_EXCEEDED; and it gave ineligible customers their formula
  limit, where "what they may still borrow" reads as 0. Both fixed. It stays invalid in every measured setting
  (a cutoff, a cap or a notice is wrong in each), so `voi` stays 1.000. Trying to beat it: validity needs every
  binding parameter right, and no measured setting has the strictest combination; the most common easy
  combination appears in two settings, which is where `never_asks_params` (0.133) comes from, and a program
  that also knows no fixed fact cannot do better than that reference.
- **A6 — The bound's scope (low).** `objective_bound` holds for every deliverable that keeps every rule; a program
  that bends the tenure habit under an exception (a relaxed rule in a run) can pass it (easy/s525: bending 1.097
  against a bound of 1.065; easy/s1043: 1.141 against 1.106). The docstring and GT.md now state the scope.
- **A7 — One target spoke of "the client's own affordability limit" (low).** zh (客户) and ja (顧客) rendered it as
  the customer's own limit. `regulator_notice_easy` now says "our own affordability limit" in the client's voice
  in all five locales.

Checked without a finding: every other ablation is the reference with one switch and a natural misreading; the
agent's view and the request are byte-identical (validate-case); CLIENT_REVIEW.md's quotes are the cited lines of
each locale's requirements and the five locales agree on every number, identifier and date (re-checked by an
independent script); nothing claims a human review; the bound's proof (left Riemann sums of a probability that
grows with the amount, linear between grid points, weak duality, the two cases of the treasury's cut) holds and
no valid deliverable passes it; `quality_cap` = 1.02 is at least the median best known quality; README's reference
numbers match the stored dataset; `referral_capacity` is rightly not a target (a program that maximizes profit
never refers by choice, since a referral costs 60 and earns nothing, so misreading the capacity changes nothing
for it; the rule closes F2's shortcut).
