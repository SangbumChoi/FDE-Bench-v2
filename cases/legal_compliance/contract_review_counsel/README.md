# Contract Review Counsel — `legal_compliance/contract_review_counsel`

The legal team of Brightvale Holdings, a company that buys services and materials from about forty suppliers, asks
the agent to "review these supplier contracts and tell us which ones need changes before we sign". The deliverable
is `review.json`: for every contract in the register, the issue codes found and a decision (`sign`, `negotiate` or
`reject`). The request says nothing about what counts as an issue. The company's playbook (seven points with their
thresholds), the issue codes, the decision rule and the small-contract fast track are all in the hidden
requirements, and the agent has to ask the client for them.

The case has no settings: one world, one ground truth, the same problem at every difficulty. The engagement knobs
(full spec vs. clarify first, client persona, data noise, events) apply on top, as for every case (see
[cases/README.md](../../README.md)).

## Data

- `contract_register.csv` (localized name, e.g. `계약대장.csv`): `contract_id`, `supplier`, `category` (six
  procurement categories; IT & data services is the largest with 12 of 40), `annual_value_usd` and
  `contract_file`. The requirements say the register value is "the annual fees" that the contracts refer to.
- `contracts/C001.txt` … `C040.txt`: one supply agreement per file, 7 or 8 articles (scope and term, fees and
  payment, confidentiality, data protection when present, indemnity, limitation of liability, termination,
  governing law and disputes). Contracts are written in the client's language. Six of them (C012, C021, C024,
  C028, C032, C036) are on the supplier's paper in another language: Spanish for an English client, English for
  the other four locales.
- Values at seed 20261026: 8 contracts below USD 20,000 (7,500 to 19,000), 14 between 26,000 and 131,500 and 18
  between 268,000 and 1,176,500.

## Rules

| Rule | Class | What it says |
|---|---|---|
| `all_contracts_reviewed` | physical | Every contract in the register has an entry. |
| `decision_consistency` | contractual | The decision follows from the listed issues: `reject` with two or more critical issues (`LIABILITY_CAP`, `DATA_PROTECTION`, `INDEMNITY`), `negotiate` with any issue, else `sign`. |
| `small_contract_fast_track` | business policy (bendable) | Contracts below USD 20,000 are marked `sign` with no issues, without review. |

**Quality** (higher is better) is 0.7 × the micro F1 of the issue codes over every contract × code pair plus
0.3 × the share of contracts whose decision matches the playbook decision for their true issues. It is scored
against the world, never against the rendered text.

## The playbook and the traps in each clause

| Code | Rule | How the contracts phrase it, and the trap |
|---|---|---|
| `LIABILITY_CAP` | cap ≥ 1 × annual value | A multiple in digits or words ("one half of", "twice"); a fixed amount in digits or paraphrased ("US$20 thousand in aggregate", 万/만 in zh/ko/ja, "mil dólares" in es); or "the fees paid in the six months preceding the claim", which is worth N/12 × the value. A cap exactly equal to the value passes (8 contracts above the fast track sit exactly at 1× at this seed), and so does an uncapped contract. |
| `GOVERNING_LAW` | Swiss or Singapore law | "Swiss law" or "the laws of Switzerland". In 14 of 40 contracts at this seed the courts or arbitration seat are in another jurisdiction than the law; only the law counts, so Hong Kong law with a Singapore seat is an issue. |
| `AUTO_RENEWAL` | non-renewal notice ≥ 60 days | "Renews automatically … unless notice" or "continues for a further year … unless a party objects"; notice in days or in months (a month is 30 days: "two months" passes, "forty-five days" fails). A contract that simply expires passes. |
| `PAYMENT_TERMS` | ≥ 45 days from receipt of invoice | Digits, words ("forty-five days") or "net 30". |
| `DATA_PROTECTION` | IT & data contracts need a personal-data clause | Titled "Data Protection" or "Personal Information" with different wording; only the register category decides whether one is needed. |
| `TERMINATION_CONVENIENCE` | above USD 150,000, we can terminate without cause | "For convenience" or "bring this Agreement to an end at any time and without stating a reason"; termination for breach does not count. Strictly above 150,000. |
| `INDEMNITY` | mutual | "Each party shall indemnify the other", or the same thing as two promises ("the Supplier shall indemnify the Customer … and the Customer shall indemnify the Supplier on the same terms"); one-way means only we indemnify the supplier. |

Truth at seed 20261026: 69 issue codes on 33 of the 40 contracts, 8 of them `reject`. Above the fast track (32
contracts) there are 58 codes; the decisions there are 7 `reject`, 18 `negotiate` and 7 `sign`.

## Situations present

- **Hidden facts.** Everything that decides correctness (the seven points and their thresholds, the codes, the
  decision rule, the fast track) is in the hidden requirements. Nothing in the data states them.
- **A company habit (the fast track).** The client signs contracts below USD 20,000 without legal review. The rule
  is a bendable business policy. While it holds, the right answer for a small contract is `sign` with no issues,
  and a review that obeys it gets those contracts right. If the agent breaks it, the review counts only with an
  approved exception. The small contracts are then judged against the playbook like the others, and the policy's
  soft-rule penalty applies. At this seed all 8 small contracts carry playbook issues (11 codes; C029 would be a
  `reject`), so a reviewer who never learns of the fast track and reviews them is invalid without an exception.
  Bending does not pay in score: the reference with the fast track set aside scores 0.8595 against 0.8825 when it
  obeys, before the penalty.
- **Language.** Six contracts are written in a second language, and every clause has two or three phrasings.
- Not present: dated events (amendments, side letters, an already-renewed contract), inbox messages, conflicting
  sources or pressure to sign a bad contract. See REVIEW.md F5.

## Reference and baseline

The **reference** is a literal keyword checklist that reads the English rendering of each contract (whatever the
locale) and obeys the fast track. It handles digits, number words for payment days and "one half of", and misses
the paraphrases. **Baseline**: signs every contract as it stands, with no issues and decision `sign` (what the
client does without a reviewer). Both are valid. Normalized quality is (objective − baseline) / (reference −
baseline).

| World seed | Baseline | Reference | Full-information review (obeys the fast track) |
|---|---|---|---|
| 20261026 (stored dataset) | 0.1125 | 0.8825 | 1.0 (quality 1.153) |
| 1 | 0.0750 | 0.8485 | 1.0 (quality 1.196) |
| 2 | 0.1200 | 0.8301 | 1.0 (quality 1.239) |
| 3 | 0.0900 | 0.7793 | 1.0 (quality 1.320) |

At seed 20261026 the reference scores issue F1 0.875 (precision 0.907, recall 0.845: tp 49, fp 5, fn 9) and decision
accuracy 0.90. Its errors are all above the fast track:

- **Misses (9).** Three `LIABILITY_CAP`: two six-month period caps (C010, C011) and a paraphrased "US$20 thousand"
  (C027). Four `AUTO_RENEWAL`: "continues for a further year" (C021, C027, C039) and a notice written as
  "forty-five days" (C020). Two `GOVERNING_LAW`: Hong Kong law with a Singapore seat or courts (C037, C039).
- **False flags (5).** Three `INDEMNITY`, where the mutual indemnity is written as two promises (C001, C025, C039),
  and two `TERMINATION_CONVENIENCE`, where the right is worded as "without stating a reason" (C014, C033).

The baseline gets no codes (F1 0). Its decision accuracy is 0.375, from the 15 contracts whose right answer is
`sign`: the 8 fast-tracked ones and 7 larger ones with no issue.

Headroom at seed 20261026 (each review is the full-information review with one mistake, obeying the fast track):

| Review | Objective | Quality |
|---|---|---|
| Full information | 1.0 | 1.153 |
| Never flags `AUTO_RENEWAL` | 0.9550 | 1.094 |
| Never flags `TERMINATION_CONVENIENCE` | 0.9481 | 1.085 |
| Reads the venue instead of the governing law | 0.9321 | 1.064 |
| Leaves the 6 foreign-paper contracts empty | 0.9181 | 1.046 |
| Flags caps exactly equal to the value | 0.9173 | 1.045 |
| Never flags `AUTO_RENEWAL` or `TERMINATION_CONVENIENCE` | 0.8960 | 1.018 |
| Reference | 0.8825 | 1.0 |
| Reference with the fast track bent (before the penalty) | 0.8595 | 0.970 |

With the policy's default quality cap of 1.5, the best possible review reaches 1.153 / 1.5 ≈ 0.77 of the quality
component at this seed (REVIEW.md F1).

## Notes

- Practice behind the facts. The seven points are the usual items of an in-house procurement playbook. World
  Commerce & Contracting's "Most Negotiated Terms" surveys have long put limitation of liability and
  indemnification at the top of the list. A cap of one year's fees, a preferred governing law, a minimum
  non-renewal window, net payment terms and termination for convenience on large contracts are common positions.
  The data-protection clause the contracts use follows the processor terms of GDPR Article 28(3): processing
  only on documented instructions, security measures, and deletion or return at the end, plus a breach notice
  (Article 33(2)).
- Synthetic. The company, suppliers, values, thresholds (60 days, 45 days, USD 150,000, USD 20,000) and the
  decision rule are design choices, not taken from a real playbook. The world is built only from
  `random.Random(seed)`.
- The register value equals "the annual fees" by definition. The contract scope always matches the register
  category, so the data-protection point is a category lookup plus a clause check.
- `validate-case` checks deterministic data in five locales, a valid reference at quality 1.0, a valid baseline
  below it, one deliverable per rule that breaks only that rule, and world seeds 1–3.
