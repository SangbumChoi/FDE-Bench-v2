# Review — finance/loan_underwriting_specialist

Findings of a case review, the verifier's verdicts, and what this change did about each. This change fixes F5,
F6 and F7 and adds a baseline. The other findings are proposals for the case owner to decide on.

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
