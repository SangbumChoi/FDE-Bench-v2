# Supplier contract review

## Background

Hi, procurement has lined up about forty supplier contracts that are waiting for signature. Please review these supplier contracts and tell us which ones need changes before we sign. The contract register and the contract texts are attached.

## Deliverable

One JSON file, `review.json`, with one entry for every contract in the register (40 contracts), keyed by contract id exactly as in the data:
`{"C001": {"issues": ["LIABILITY_CAP", "INDEMNITY"], "decision": "reject"}, "C002": {"issues": [], "decision": "sign"}, ...}`.
`issues` lists the issue codes found (empty list if none); `decision` is `sign`, `negotiate` or `reject`. Only these seven codes are allowed: `LIABILITY_CAP`, `GOVERNING_LAW`, `AUTO_RENEWAL`, `PAYMENT_TERMS`, `DATA_PROTECTION`, `TERMINATION_CONVENIENCE`, `INDEMNITY`.

- **This round**: we only need four points of the playbook checked: `LIABILITY_CAP`, `GOVERNING_LAW`, `PAYMENT_TERMS` and `INDEMNITY`. Procurement checks renewal, data protection and termination themselves this time, so leave `AUTO_RENEWAL`, `DATA_PROTECTION` and `TERMINATION_CONVENIENCE` out; if you list them we will ignore them.
- **Contracts outside this round**: procurement handles three kinds of contracts directly this time: the ones on the supplier's own paper, the ones with a record in the `amendments/` folder and the one the e-mail in the `emails/` folder is about. They still need an entry in the file, but we will not use your answer on them.
- **Every other contract is reviewed this round, the small ones included.**

## Data notes

- `contract_register.csv` has one row per contract: `contract_id`, `supplier`, `category`, `annual_value_usd` and `contract_file` (the path of the contract text in the `contracts/` folder).
- `annual_value_usd` is the expected annual fees under the contract. When a contract speaks of "the annual fees", it means this amount. All amounts are in US dollars.
- Most contracts are on our own template, but a few suppliers sent their own paper, written in Spanish. The same playbook applies to them.
- Clauses are not always worded the same way and headings differ. Judge each clause by what it says, not by its title or by a few keywords.
- Wherever a period is given in months, a month counts as 30 days.
- Every contract text starts with the date of its draft. The `amendments/` folder holds a record for each change negotiated on a draft, with its date and status, and the `emails/` folder a message we received about one contract.

## Our contracting playbook

This round each contract is checked against four points. Every point that fails is one issue, with this code:

- `LIABILITY_CAP`: the liability cap must be at least 2× the annual value. A fixed amount is compared with 2 × `annual_value_usd`; a multiple of the annual fees must be at least 2. A cap exactly at that minimum is fine. A contract that does not cap liability at all is fine.
  Caps written as the fees paid over the last N months are being replaced with our standard wording in a separate exercise, so do not flag those this round.
- `GOVERNING_LAW`: the contract must be governed by the law of Singapore.
  Only the governing law counts this round; where disputes are heard (courts or arbitration seat) does not matter.
- `PAYMENT_TERMS`: the payment term must be at least 30 days from receipt of the invoice.
- `INDEMNITY`: indemnities must be mutual, each party covering the other. A clause where only we indemnify the supplier is an issue.

`LIABILITY_CAP` and `INDEMNITY` are the critical issues this round.
Decision: `reject` if a contract has one or more critical issues; `negotiate` if it has any issue; `sign` if it has none.

## How the review is judged

**Hard constraints** (if any is broken, the review does not count):

- Every contract in the register has an entry.
- Every decision follows from the issues listed for that contract, per the rule above.

**Quality**: 0.7 × the F1 score of the issue codes (micro-averaged over every contract × code pair, against the issues the contracts actually contain under the playbook) + 0.3 × the share of contracts whose decision equals the playbook decision for their actual issues.
Only the contracts and points of this round count.
Higher is better.
