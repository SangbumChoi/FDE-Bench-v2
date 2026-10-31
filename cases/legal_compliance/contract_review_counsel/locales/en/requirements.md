# Supplier contract review

## Background

Hi, procurement has lined up about forty supplier contracts that are waiting for signature. Please review these supplier contracts and tell us which ones need changes before we sign. The contract register and the contract texts are attached.

## Deliverable

One JSON file, `review.json`, with one entry for every contract in the register (40 contracts), keyed by contract id exactly as in the data:
`{"C001": {"issues": ["LIABILITY_CAP", "INDEMNITY"], "decision": "reject"}, "C002": {"issues": [], "decision": "sign"}, ...}`.
`issues` lists the issue codes found (empty list if none); `decision` is `sign`, `negotiate` or `reject`. Only these seven codes are allowed: `LIABILITY_CAP`, `GOVERNING_LAW`, `AUTO_RENEWAL`, `PAYMENT_TERMS`, `DATA_PROTECTION`, `TERMINATION_CONVENIENCE`, `INDEMNITY`.

<!-- tier: easy -->
- **This round**: we only need four points of the playbook checked: `LIABILITY_CAP`, `GOVERNING_LAW`, `PAYMENT_TERMS` and `INDEMNITY`. Procurement checks renewal, data protection and termination themselves this time, so leave `AUTO_RENEWAL`, `DATA_PROTECTION` and `TERMINATION_CONVENIENCE` out; if you list them we will ignore them.
<!-- /tier -->
<!-- tier: easy medium -->
- **Contracts outside this round**: procurement handles three kinds of contracts directly this time: the ones on the supplier's own paper, the ones with a record in the `amendments/` folder and the one the e-mail in the `emails/` folder is about. They still need an entry in the file, but we will not use your answer on them.
- **Every other contract is reviewed this round, the small ones included.**
<!-- /tier -->

## Data notes

- `contract_register.csv` has one row per contract: `contract_id`, `supplier`, `category`, `annual_value_usd` and `contract_file` (the path of the contract text in the `contracts/` folder).
- `annual_value_usd` is the expected annual fees under the contract. When a contract speaks of "the annual fees", it means this amount. All amounts are in US dollars.
- Most contracts are on our own template, but a few suppliers sent their own paper, written in Spanish. The same playbook applies to them.
- Clauses are not always worded the same way and headings differ. Judge each clause by what it says, not by its title or by a few keywords.
- Wherever a period is given in months, a month counts as 30 days.
- Every contract text starts with the date of its draft. The `amendments/` folder holds a record for each change negotiated on a draft, with its date and status, and the `emails/` folder a message we received about one contract.
<!-- tier: hard -->
- **Amendments**: a change counts only if both parties agreed to it and it is dated after the draft of its contract; the clause is then read as amended. A change the supplier proposed and we did not accept does not count, and a change dated before the draft is superseded by the draft (the draft is what we sign).
- **Requests to sign**: business owners sometimes write to us to push a contract through. The review follows the playbook alone: an approval or a request from the business does not change the issues or the decision.
<!-- /tier -->

## Our contracting playbook

<!-- tier: easy -->
This round each contract is checked against four points. Every point that fails is one issue, with this code:
<!-- /tier -->
<!-- tier: medium hard -->
Each contract is checked against seven points. Every point that fails is one issue, with this code:
<!-- /tier -->

- `LIABILITY_CAP`: the liability cap must be at least {{cap_multiple}}× the annual value. A fixed amount is compared with {{cap_multiple}} × `annual_value_usd`; a multiple of the annual fees must be at least {{cap_multiple}}. A cap exactly at that minimum is fine. A contract that does not cap liability at all is fine.
<!-- tier: easy -->
  Caps written as the fees paid over the last N months are being replaced with our standard wording in a separate exercise, so do not flag those this round.
<!-- /tier -->
<!-- tier: medium hard -->
  A cap equal to the fees paid over the last N months is worth N/12 × the annual value.
<!-- /tier -->
- `GOVERNING_LAW`: the contract must be governed by {{governing_law}}.
<!-- tier: easy -->
  Only the governing law counts this round; where disputes are heard (courts or arbitration seat) does not matter.
<!-- /tier -->
<!-- tier: medium hard -->
  Disputes must be heard there too: the courts or the arbitration seat named in the contract must be in one of those same jurisdictions. A contract with an accepted law but courts or a seat elsewhere is an issue, and so is one with courts or a seat in an accepted place but another law.
<!-- /tier -->
<!-- tier: medium hard -->
- `AUTO_RENEWAL`: if the contract renews by itself unless someone objects, whatever the wording, the notice period for stopping the renewal must be at least {{renewal_notice_days}} days. A contract that simply expires at the end of its term is fine.
<!-- /tier -->
- `PAYMENT_TERMS`: the payment term must be at least {{payment_days}} days from receipt of the invoice.
<!-- tier: medium hard -->
- `DATA_PROTECTION`: contracts in {{dp_categories}} must contain a clause on how the supplier handles personal data (whatever it is called).
<!-- /tier -->
<!-- tier: medium -->
  Other categories do not need one.
<!-- /tier -->
<!-- tier: hard -->
  A contract in another category needs one too when the supplier handles personal data of our own customers under it, for example deliveries to our customers' home addresses or our letters to customers: read the scope article.
<!-- /tier -->
<!-- tier: medium hard -->
- `TERMINATION_CONVENIENCE`: contracts with an annual value above USD {{tfc_above}} (strictly more) must let us terminate for convenience, i.e. at any time without having to give a reason. Termination for breach alone is not enough. Any notice period is acceptable.
<!-- /tier -->
- `INDEMNITY`: indemnities must be mutual, each party covering the other. A clause where only we indemnify the supplier is an issue.

<!-- tier: easy -->
`LIABILITY_CAP` and `INDEMNITY` are the critical issues this round.
<!-- /tier -->
<!-- tier: medium hard -->
`LIABILITY_CAP`, `DATA_PROTECTION` and `INDEMNITY` are critical issues.
<!-- /tier -->
Decision: `reject` if a contract has {{reject_at}} critical issues; `negotiate` if it has any issue; `sign` if it has none.
<!-- tier: hard -->

Our habit: contracts with an annual value below USD {{fast_track_below}} are fast-tracked. They are marked `sign` with no issues, without legal review, so that legal time goes to the larger contracts.
<!-- /tier -->

## How the review is judged

**Hard constraints** (if any is broken, the review does not count):

- Every contract in the register has an entry.
- Every decision follows from the issues listed for that contract, per the rule above.
<!-- tier: hard -->
- Contracts below USD {{fast_track_below}} are marked `sign` with an empty issue list.
<!-- /tier -->

**Quality**: 0.7 × the F1 score of the issue codes (micro-averaged over every contract × code pair, against the issues the contracts actually contain under the playbook) + 0.3 × the share of contracts whose decision equals the playbook decision for their actual issues.
<!-- tier: easy medium -->
Only the contracts and points of this round count.
<!-- /tier -->
<!-- tier: hard -->
A fast-tracked contract counts as correct when it is marked `sign` with no issues; only when an approved exception sets the fast track aside are the small contracts judged against the playbook like the others.
<!-- /tier -->
Higher is better.
