# Loan Underwriting Specialist — `finance/loan_underwriting_specialist`

A lender's credit team asks the agent to decide a batch of 424 pending applications for its one unsecured
personal-loan product (PL36: 36 months, 11.9% a year, 1,000–50,000) and to set each approved amount, with
3,000 past funded loans and their default outcomes as training data. The deliverable is `decisions.csv`
(`application_id,decision,limit,reason_code`). The setting is country-neutral: no national regulator or
bureau is named, only rules most consumer lenders have (a debt-service cap, reason codes, fair lending,
income verification, one loan per person).

The case has nine settings: three tiers (which rules are in force) × three rule sets (the rules'
parameters). The agent's view is the same in all nine: the same request, the same data files
(`past_applications`, `pending_applications`, `credit_bureau` with `bureau_file_number`, `existing_debts`
with installment loans and credit lines, `income_documents`, `product_sheet.xlsx`) and the same deliverable
spec. Everything that differs lives in the hidden requirements (the simulated client answers from them) and
the evaluator. The engagement knobs (full spec vs. clarify first, client persona, data noise, events) apply
on top, as for every case (see [cases/README.md](../../README.md)).

## Tiers (same data, more rules in force)

| | easy | medium | hard |
|---|---|---|---|
| **Rules in force** | The underwriting core: income = 12 × **declared** base salary + documented bonus (undocumented bonus and stated income never count); the policy bureau's score ≥ cutoff (the other bureau is reference only); active delinquency always declined; DSR after the loan ≤ cap counting **installment loans only**; limit ≤ min(50,000, annual income, requested); planted twins that differ only in age band, gender and nationality; tenure referral habit | + credit lines in the DSR as balance / 5 + balance × rate, even with nothing due; +1.5 pt stress add-on on the new loan's rate when total unsecured debt after the loan exceeds 60,000; near-prime quota on the approved amount, a commitment to the regulator | + income verification: the lowest of the declared and documented salaries feeds the DSR and the income cap, and a document more than the threshold below the declared salary sends the application to fraud review; one loan per person (duplicates linked only by `bureau_file_number`) |
| **What the requirements put out of scope** | "Simplified interim policy": credit lines are reviewed by the cards team for now; income documents are checked by operations before disbursement; repeat applications are caught at disbursement (so no `DUPLICATE`) | Income documents checked before disbursement; repeat applications caught at disbursement | Nothing |
| **Reason codes used** | `DELINQUENCY`, `LOW_SCORE`, `DSR_EXCEEDED`, `CREDIT_RISK` | Same as easy | + `DUPLICATE` (before `CREDIT_RISK`: another application of the same person is approved) |
| **Rules** | `dsr_cap`, `no_protected_attributes` (physical); `decision_complete`, `delinquency_decline`, `score_cutoff`, `limit_cap`, `reason_code_required` (contractual); `tenure_review` (business policy, bendable) | + `near_prime_quota` (contractual); `dsr_cap` counts credit lines and the stress add-on | + `income_discrepancy_refer`, `one_loan_per_applicant` (contractual); `dsr_cap` / `limit_cap` use the verified salary |
| **Clarification targets** | 9: gross income, policy bureau, DSR, interim scope, limit caps, reason codes, protected attributes, tenure review, profit metric | 12: the easy ones without interim scope, + declared-income scope, credit-line amortization, stress add-on, near-prime quota | 14: medium without the scope target, + verified income, income discrepancy, duplicate applications |
| **What it tests** | Reading messy credit data, a scorecard from history, sizing each loan against a cap and a risk curve, an ordered reason code, fairness audits, when to bend a habit | Hidden debt-service terms that change the arithmetic, a portfolio constraint that costs money | Reconciling two sources of the same fact, a referral threshold that overrides profit, entity resolution across ids (and telling duplicates from audit twins) |

Quality is the same at every tier (higher is better): expected profit, per approval limit × 10% − true PD ×
0.60 × limit, and −60 per referral. The true PD follows the economics, not the round's policy: it uses
Bureau A, every debt (credit lines included), the real (documented) salary and the approved amount, so an
easy-tier agent that ignores credit lines because the policy does still pays for the risk.

## Rule sets (the client's parameters)

| Parameter | A | B | C |
|---|---|---|---|
| Policy bureau and cutoff (`policy_bureau`, `min_score`) | Bureau A ≥ 650 | **Bureau B** ≥ 740 | Bureau A ≥ 680 |
| Near-prime: policy score below (`near_prime_below`) | 820 | 870 (Bureau B) | 850 |
| DSR cap (`max_dsr_pct`) | 40% | 35% | 45% |
| Near-prime quota, medium/hard (`quota_pct`) | 30% | 25% | 35% |
| Income discrepancy to refer, hard (`discrepancy_pct`) | 20% | 15% | 25% |
| Tenure habit: refer below (`min_tenure`, months) | 6 | 3 | 12 |

Rule set A is the ground truth agreed for the untiered case (medium/A = one product PL36, salaried only,
Bureau A ≥ 650, DSR ≤ 40%, quota 30% below 820). The bureau is the non-nested parameter: Bureau B runs
about 55 points higher than Bureau A with noise (sd 30), so a Bureau B cutoff and near-prime band pick
different applicants, not a subset. The tenure threshold is non-nested in effect too: a looser habit's
approvals of 3–11-month applicants are tenure breaches under a stricter one, and a stricter one's
referrals waste approvals under a looser one. Within every tier each rule set's reference is invalid under
both other rule sets (typically `dsr_cap`, `tenure_review`, `near_prime_quota`, `income_discrepancy_refer`
and `reason_code_required`).

## Reference numbers (seed 20261026)

The reference fits a plain logistic scorecard on the history (Bureau A, economic DSR with every debt,
inquiries, credit-history length), applies the setting's policy, approves the largest allowed amount when
the predicted PD is below break-even, keeps the most profitable application per person (hard), and then
tops up near-prime approvals until the quota holds (medium, hard). It keeps the tenure habit. The oracle
uses the true PD to pick each amount (100-unit grid), same rules.

| Setting | Reference objective | Approve / decline / refer | Bending `tenure_review` | Oracle headroom |
|---|---|---|---|---|
| easy/A | 327,578 | 219 / 143 / 62 | +6.4% | +26.6% |
| easy/B | 361,972 | 241 / 152 / 31 | +3.5% | +18.0% |
| easy/C | 303,879 | 194 / 132 / 98 | +13.1% | +25.9% |
| medium/A | 317,230 | 271 / 91 / 62 | +10.5% | +17.2% |
| medium/B | 374,794 | 273 / 120 / 31 | +3.0% | +11.8% |
| medium/C | 304,211 | 205 / 121 / 98 | +12.1% | +25.6% |
| hard/A | 284,694 | 247 / 78 / 99 | +6.6% | +6.5% |
| hard/B | 324,697 | 242 / 90 / 92 | +5.3% | +7.5% |
| hard/C | 292,940 | 185 / 114 / 125 | +13.0% | +16.5% |

| Per-tier mean (A, B, C) | easy | medium | hard |
|---|---|---|---|
| Reference objective | 331,143 | 332,078 | 300,777 |

Binding facts in the shared data: 206 of 424 pending applicants hold credit lines; 24 people applied twice
(6–11 of the pairs get two approvals when the one-loan rule is not in force; 7–12 `DUPLICATE` declines in
hard); 47 / 65 / 37 non-delinquent applications must be referred for an income discrepancy in hard/A / B / C;
62 / 31 / 98 non-delinquent applicants fall under the tenure habit in A / B / C; the policy score's cutoff
gives 2 / 10 / 3 `LOW_SCORE` declines (few applicants score low on Bureau A, and most of them are delinquent; the Bureau B cutoff of 740 catches applicants whose Bureau A score passes).

Bending the habit pays in every setting, so a policy that allows exceptions rewards an agent that asks for
one. The headroom above the reference comes from sizing loans below the maximum where the marginal risk
outweighs the margin (largest in easy, where the policy DSR leaves out credit lines, and under the loose
45% cap of C), and from a better scorecard.

## Notes

- Scores, salaries, debts and default probabilities are synthetic; the true PD uses no protected attribute.
  The twins audit (physical rule) catches any model or rule that does.
- Planted twins are separate applicants for the audit and have different bureau file numbers; duplicates
  share one. A naive deduplication on matching columns would merge twins.
- The data comes from separate random streams (core history, core pending, credit lines, documents and
  duplicates), as when the case had tier-specific data; the world is now always the full one. The numbers
  moved from the tiered version (medium was 329,626) because the true PD now uses the economic DSR (all
  debts, real salary, no stress add-on) whatever the round's policy.
- `validate-case` checks all nine settings: deterministic data in five locales, the reference at quality
  1.0, one deliverable per rule of the setting that breaks only that rule, an identical agent view, and
  that the three rule sets lead to different solutions within each tier.
