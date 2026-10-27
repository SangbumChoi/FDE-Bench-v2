# Supplier contract review

## Background

Hi, procurement has lined up about forty supplier contracts that are waiting for signature. Please review these supplier contracts and tell us which ones need changes before we sign. The contract register and the contract texts are attached.

## Deliverable

One JSON file, `review.json`, with one entry for every contract in the register (40 contracts), keyed by contract id exactly as in the data:
`{"C001": {"issues": ["LIABILITY_CAP", "INDEMNITY"], "decision": "reject"}, "C002": {"issues": [], "decision": "sign"}, ...}`.
`issues` lists the issue codes found (empty list if none); `decision` is `sign`, `negotiate` or `reject`. Only these seven codes are allowed: `LIABILITY_CAP`, `GOVERNING_LAW`, `AUTO_RENEWAL`, `PAYMENT_TERMS`, `DATA_PROTECTION`, `TERMINATION_CONVENIENCE`, `INDEMNITY`.

## Data notes

- `contract_register.csv` has one row per contract: `contract_id`, `supplier`, `category`, `annual_value_usd` and `contract_file` (the path of the contract text in the `contracts/` folder).
- `annual_value_usd` is the expected annual fees under the contract. When a contract speaks of "the annual fees", it means this amount. All amounts are in US dollars.
- Most contracts are on our own template, but a few suppliers sent their own paper, written in Spanish. The same playbook applies to them.
- Clauses are not always worded the same way and headings differ. Judge each clause by what it says, not by its title or by a few keywords.
- Wherever a period is given in months, a month counts as 30 days.

## Our contracting playbook

Each contract is checked against seven points. Every point that fails is one issue, with this code:

- `LIABILITY_CAP`: the liability cap must be at least 1× the annual value. A fixed amount is compared with `annual_value_usd`; a multiple of the annual fees must be at least 1; a cap equal to the fees paid over the last N months is worth N/12 × the annual value. A cap exactly equal to the annual value is fine. A contract that does not cap liability at all is fine.
- `GOVERNING_LAW`: the contract must be governed by the law of Switzerland or of Singapore. Only the governing law counts; where disputes are heard (courts or arbitration seat) does not matter.
- `AUTO_RENEWAL`: if the contract renews by itself unless someone objects, whatever the wording, the notice period for stopping the renewal must be at least 60 days. A contract that simply expires at the end of its term is fine.
- `PAYMENT_TERMS`: the payment term must be at least 45 days from receipt of the invoice.
- `DATA_PROTECTION`: contracts in the `IT & data services` category must contain a clause on how the supplier handles personal data (whatever it is called). Other categories do not need one.
- `TERMINATION_CONVENIENCE`: contracts with an annual value above USD 150,000 (strictly more) must let us terminate for convenience, i.e. at any time without having to give a reason. Termination for breach alone is not enough. Any notice period is acceptable.
- `INDEMNITY`: indemnities must be mutual, each party covering the other. A clause where only we indemnify the supplier is an issue.

`LIABILITY_CAP`, `DATA_PROTECTION` and `INDEMNITY` are critical issues. Decision: `reject` if a contract has two or more critical issues; `negotiate` if it has any issue; `sign` if it has none.

Our habit: contracts with an annual value below USD 20,000 are fast-tracked. They are marked `sign` with no issues, without legal review, so that legal time goes to the larger contracts.

## How the review is judged

**Hard constraints** (if any is broken, the review does not count):

- Every contract in the register has an entry.
- Every decision follows from the issues listed for that contract, per the rule above.
- Contracts below USD 20,000 are marked `sign` with an empty issue list.

**Quality**: 0.7 × the F1 score of the issue codes (micro-averaged over every contract × code pair, against the issues the contracts actually contain under the playbook) + 0.3 × the share of contracts whose decision equals the playbook decision for their actual issues. Higher is better.
