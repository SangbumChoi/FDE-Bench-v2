# Contract Review Counsel — `legal_compliance/contract_review_counsel`

The legal team of Brightvale Holdings, a company that buys services and materials from about forty suppliers, asks
the agent to "review these supplier contracts and tell us which ones need changes before we sign". The deliverable
is `review.json`: for every contract in the register, the issue codes found and a decision (`sign`, `negotiate` or
`reject`). The request says nothing about what counts as an issue. The company's playbook (up to seven points with
their figures), the issue codes, the decision rule, what is in scope this round and, in the hard tier, how to read
the amendment records and the business owner's e-mail and the small-contract fast track are all in the hidden
requirements, and the agent has to ask the client for them.

The case has **settings**: three tiers × rule seeds. A rule seed draws each of the playbook's figures (the cap
multiple, the accepted laws, the payment days, how many critical issues make a reject, the renewal notice, the
data-protection categories, the termination threshold and the fast-track threshold) from a pool of candidates. **The
agent sees the same request and the same data in every setting** (the validator checks that its prompt and workspace
are byte-identical); only the hidden requirements, which the simulated client answers from, and the evaluator
change. The public panel is rule seeds 6, 11 and 49 (nine ground truths); any other rule seed is a private draw of
the same pools. The engagement knobs (full spec vs. clarify first, client persona, data noise, events) apply on top,
as for every case (see [cases/README.md](../../README.md)).

## Data (the same in every setting)

- `contract_register.csv` (localized name, e.g. `계약대장.csv`): `contract_id`, `supplier`, `category` (six
  procurement categories; IT & data services is the largest with 12 of 40), `annual_value_usd` and
  `contract_file`. The requirements say the register value is "the annual fees" that the contracts refer to.
- `contracts/C001.txt` … `C040.txt`: one supply agreement per file, headed by the date of its draft (2026-09-01 to
  2026-10-19 at the stored seed), with 7 or 8 articles (scope and term, fees and payment, confidentiality, data
  protection when present, indemnity, limitation of liability, termination, governing law and disputes).
  Contracts are written in the client's language. Six of them (C003, C014, C023, C026, C029, C032 at the stored
  seed) are on the supplier's paper in another language: Spanish for an English client, English for the other
  four locales.
- `amendments/C0xx.txt` (localized folder, e.g. `수정기록/`): four records of changes negotiated on a draft, each with
  its date, its status and the replacement text of one article. At the stored seed: C019 (agreed after the draft:
  Singapore law and seat become New York law and courts), C015 (agreed after the draft: payment within 15 days becomes
  60 days), C013 (proposed by the supplier, not accepted: a one-way indemnity) and C036 (agreed, but dated six days
  before the draft, which still caps liability at half the fees: superseded).
- `emails/2026-10-27.txt` (localized folder): the business owner of C040 (an IT contract of USD 1,040,000) writes
  that it is CEO-approved and asks legal to "just mark it sign". C040 caps liability at half the fees and has a
  one-way indemnity, a `reject` under every candidate playbook.
- Values at the stored seed (USD): 3 below 10,000; exactly 10,000; 3 between 17,000 and 19,000; exactly 20,000; 2
  at 21,000; exactly 25,000; 7 between 50,000 and 89,000; exactly 100,000; 4 between 122,000 and 145,000; exactly
  150,000; 4 between 157,000 and 214,000; exactly 250,000; 11 between 383,000 and 1,175,000. The generator reads the
  candidate thresholds from case.yaml and always puts contracts strictly between consecutive candidates and exactly
  on each one, so every fast-track and termination candidate changes answers (the thresholds are strict: a contract
  exactly at a termination candidate never has a termination right).
- Three logistics or professional-services contracts say in their scope that the supplier handles personal data of
  the client's own customers (home deliveries to customers, translating letters to customers): C006, C023 and C026
  at the stored seed; C023 and C026 have no data-protection clause.

## Tiers

| Tier | Points checked (codes in scope) | Contracts scored | What it adds |
|---|---|---|---|
| easy | `LIABILITY_CAP`, `GOVERNING_LAW`, `PAYMENT_TERMS`, `INDEMNITY` | 29: all but the supplier-paper, amended and e-mailed ones | The four points that read straight off the clause. Caps written as the fees of N months are not flagged this round (procurement is replacing that wording); only the governing law counts, not the forum. Critical: `LIABILITY_CAP` and `INDEMNITY`. Other codes in the file are ignored. No fast track. |
| medium | all seven | the same 29 | Auto-renewal notice (notice in months at 30 days), caps of N months' fees (N/12 of the value), data protection by category, termination for convenience strictly above a value, and the dispute forum: the courts or seat must be in an accepted jurisdiction too. Critical: `LIABILITY_CAP`, `DATA_PROTECTION`, `INDEMNITY`. No fast track. |
| hard | all seven | all 40 | The six supplier-paper contracts; the amendment records (only a change agreed by both parties and dated after the draft counts); personal data of the client's own customers in a category the playbook does not list; the business owner's e-mail asking to sign a contract the playbook rejects; and the small-contract fast track (a bendable policy). |

The lower tiers' requirements say, in the client's words, what is out of scope this round ("procurement checks
renewal, data protection and termination themselves this time", "procurement handles three kinds of contracts
directly this time … we will not use your answer on them", "every other contract is reviewed this round, the small
ones included"). An out-of-scope contract still needs an entry; its answer is not scored.

## Parameters (rule seeds)

Each parameter is drawn on its own from its pool in the tier. A parameter with one candidate in a tier does not
apply there (its value is drawn but no rule reads it).

| Parameter | easy | medium | hard | What it changes |
|---|---|---|---|---|
| `cap_multiple` | 1, 1.5, 2 | 1, 1.5, 2 | 1, 1.5, 2 | The minimum liability cap as a multiple of the annual value. A fixed amount is compared with this multiple of the value; a cap exactly at it passes. |
| `governing_law` | CH_SG, CH_SG_EW, SG | same | same | The accepted laws: Swiss or Singapore law; Swiss, Singapore or English law; Singapore law only. From medium the courts or seat must be in one of the same jurisdictions. |
| `payment_days` | 45, 60, 30 | same | same | The minimum payment term from receipt of the invoice (contracts pay in 15, 30, 45, 60 or 90 days). |
| `reject_at` | 2, 1 | 2, 1 | 2, 1 | How many critical issues make a `reject` ("two or more", "one or more"). |
| `renewal_notice_days` | 60 (not used) | 60, 90, 45 | 60, 90, 45 | The minimum non-renewal notice of an auto-renewing contract (contracts give 30, 45, 60 or 90 days, in days or months). |
| `dp_categories` | it_data (not used) | it_data, it_data_marketing | same as medium | The register categories that need a data-protection clause: IT & data services, or IT & data services and Marketing. |
| `tfc_above` | 150000 (not used) | 150000, 100000, 250000 | same as medium | Termination for convenience is required strictly above this annual value. |
| `fast_track_below` | 20000 (not used) | 20000 (not used) | 20000, 10000, 25000 | Contracts strictly below this value are signed with no issues, without review (3, 7 or 10 contracts at the stored seed). |

No combination is excluded (`admissible` is not needed) and nothing is derived. The validator's binding check
passes for every parameter at world seeds 20261026 and 1–12: at the first public seed's hard setting, changing any
one parameter to another candidate makes the reference invalid (`reject_at`, and `fast_track_below` when the
threshold rises) or moves its objective, or lets the other setting's reference beat it, by at least 1%. The
generator was adjusted for this (see REVIEW.md, Rule seeds): three IT and three marketing contracts above every
fast-track candidate lack a data-protection clause, three auto-renewing contracts state each notice period plainly
in days, every termination band has a contract without the right, and four contracts split law and forum.

### Public panel (stored world seed 20261026)

| Setting | Drawn values | Reference | Baseline | Full-information review (quality) |
|---|---|---|---|---|
| easy/s6 | cap 1×, CH_SG, 60 days, reject at 2 | 0.8942 | 0.0207 | 1.0 (1.121) |
| easy/s11 | cap 1.5×, CH_SG_EW, 45 days, reject at 2 | 0.8451 | 0.0517 | 1.0 (1.195) |
| easy/s49 | cap 2×, SG, 30 days, reject at 1 | 0.8672 | 0.0414 | 1.0 (1.161) |
| medium/s6 | cap 1×, CH_SG, 60 days, reject at 2, notice 90, IT + marketing, termination > 150,000 | 0.8555 | 0.0000 | 1.0 (1.169) |
| medium/s11 | cap 1.5×, CH_SG_EW, 45 days, reject at 2, notice 45, IT, termination > 250,000 | 0.8494 | 0.0103 | 1.0 (1.179) |
| medium/s49 | cap 2×, SG, 30 days, reject at 1, notice 60, IT + marketing, termination > 100,000 | 0.8663 | 0.0000 | 1.0 (1.154) |
| hard/s6 | as medium/s6, fast track < 25,000 | 0.8343 | 0.0750 | 1.0 (1.218) |
| hard/s11 | as medium/s11, fast track < 20,000 | 0.8214 | 0.0600 | 1.0 (1.235) |
| hard/s49 | as medium/s49, fast track < 10,000 | 0.8562 | 0.0225 | 1.0 (1.172) |

The full drawn dicts (easy and medium also draw the parameters they do not use):

```
easy/s6    {cap_multiple: 1,   governing_law: CH_SG,    payment_days: 60, reject_at: 2, renewal_notice_days: 60, dp_categories: it_data,           tfc_above: 150000, fast_track_below: 20000}
easy/s11   {cap_multiple: 1.5, governing_law: CH_SG_EW, payment_days: 45, reject_at: 2, renewal_notice_days: 60, dp_categories: it_data,           tfc_above: 150000, fast_track_below: 20000}
easy/s49   {cap_multiple: 2,   governing_law: SG,       payment_days: 30, reject_at: 1, renewal_notice_days: 60, dp_categories: it_data,           tfc_above: 150000, fast_track_below: 20000}
medium/s6  {cap_multiple: 1,   governing_law: CH_SG,    payment_days: 60, reject_at: 2, renewal_notice_days: 90, dp_categories: it_data_marketing, tfc_above: 150000, fast_track_below: 20000}
medium/s11 {cap_multiple: 1.5, governing_law: CH_SG_EW, payment_days: 45, reject_at: 2, renewal_notice_days: 45, dp_categories: it_data,           tfc_above: 250000, fast_track_below: 20000}
medium/s49 {cap_multiple: 2,   governing_law: SG,       payment_days: 30, reject_at: 1, renewal_notice_days: 60, dp_categories: it_data_marketing, tfc_above: 100000, fast_track_below: 20000}
hard/s6    {cap_multiple: 1,   governing_law: CH_SG,    payment_days: 60, reject_at: 2, renewal_notice_days: 90, dp_categories: it_data_marketing, tfc_above: 150000, fast_track_below: 25000}
hard/s11   {cap_multiple: 1.5, governing_law: CH_SG_EW, payment_days: 45, reject_at: 2, renewal_notice_days: 45, dp_categories: it_data,           tfc_above: 250000, fast_track_below: 20000}
hard/s49   {cap_multiple: 2,   governing_law: SG,       payment_days: 30, reject_at: 1, renewal_notice_days: 60, dp_categories: it_data_marketing, tfc_above: 100000, fast_track_below: 10000}
```

Together the three seeds draw every candidate of every pool in every tier.
`dataset/gt/<tier>_s<seed>/` holds each setting's `setting.json`, the reference, its score and `truth.json` (the
playbook's issues and decision of every scored contract, fast track kept).

## Rules

| Rule | Class | Tiers | What it says |
|---|---|---|---|
| `all_contracts_reviewed` | physical | all | Every contract in the register has an entry. |
| `decision_consistency` | contractual | all | The decision follows from the listed issues: `reject` with `reject_at` or more critical issues, `negotiate` with any issue, else `sign`. In easy only `LIABILITY_CAP` and `INDEMNITY` are critical, and codes outside the round are ignored: the decision may follow the listed issues with them or without them. |
| `small_contract_fast_track` | business policy (bendable) | hard | Contracts below `fast_track_below` are marked `sign` with no issues, without review. |

**Quality** (higher is better) is 0.7 × the micro F1 of the issue codes over every scored contract × in-scope code
pair plus 0.3 × the share of scored contracts whose decision matches the playbook decision for their true issues.
It is scored against the world, never against the rendered text. The fast-track scoring fix of F2 stands: while a
review keeps the fast track, a small contract is right when marked `sign` with no issues; a review that breaks it
counts only with an approved exception, and the small contracts are then judged against the playbook like the
others.

## The playbook and the traps in each clause

| Code | Rule (parameter) | How the contracts phrase it, and the trap |
|---|---|---|
| `LIABILITY_CAP` | cap ≥ `cap_multiple` × annual value | A multiple in digits or words ("one half of", "twice"); a fixed amount in digits or paraphrased ("US$37.5 thousand in aggregate", 万/만 in zh/ko/ja, "mil dólares" in es); or "the fees paid in the six months preceding the claim", worth N/12 × the value (6, 12, 18 or 24 months). Fixed caps sit exactly on 1×, 1.5× and 2× of the value and strictly between them, so a cap at the minimum passes and one just below fails. An uncapped contract passes. Easy does not flag the N-month caps. |
| `GOVERNING_LAW` | law in `governing_law`; from medium also the forum | "Swiss law" or "the laws of Switzerland". In 13 of 40 contracts at the stored seed the courts or seat are elsewhere than the law. In easy only the law counts (Hong Kong law with a Singapore seat is an issue); from medium a Singapore-law contract with New York courts is an issue too. |
| `AUTO_RENEWAL` (medium, hard) | non-renewal notice ≥ `renewal_notice_days` | "Renews automatically … unless notice" or "continues for a further year … unless a party objects"; notice in days or months (a month is 30 days). A contract that simply expires passes. |
| `PAYMENT_TERMS` | ≥ `payment_days` from receipt of invoice | Digits, words ("forty-five days") or "net 30"; the Korean and Japanese word forms are months ("두 달", "2か月"). |
| `DATA_PROTECTION` (medium, hard) | categories in `dp_categories` need a personal-data clause; in hard also any contract whose scope handles our customers' personal data | Titled "Data Protection" or "Personal Information" with different wording. |
| `TERMINATION_CONVENIENCE` (medium, hard) | strictly above `tfc_above`, we can terminate without cause | "For convenience" or "bring this Agreement to an end at any time and without stating a reason"; termination for breach does not count. A contract exactly at a candidate threshold has no termination right. |
| `INDEMNITY` | mutual | "Each party shall indemnify the other", or the same thing as two promises; one-way means only we indemnify the supplier. |

## Situations present

- **Hidden facts.** Everything that decides correctness (the points, their figures, the codes, the decision rule,
  the round's scope) is in the hidden requirements; a rule seed redraws the figures, so a review tuned to one draw
  is wrong under another.
- **Dated events (hard).** The four amendment records: two agreed after their draft (they count and flip an issue
  each way), one proposed by the supplier and not accepted, one agreed but dated before the draft (superseded).
- **Pressure (hard).** The business owner's e-mail asks to mark a reject-worthy contract `sign`; the true decision is
  scored. In easy and medium that contract is out of scope.
- **The hardest hidden fact (hard).** Personal data of the client's own customers in a logistics or
  professional-services contract needs the clause although the category does not.
- **A company habit (hard).** The fast track is a bendable business policy. Bending it never pays: a perfect
  review scores the same before the 0.1 soft-rule penalty, and the reference bent scores 0.8427 against 0.8343 at
  hard/s6, less than the penalty.
- **Language.** Six contracts are written in a second language (scored in hard only), and every clause has two or
  three phrasings.

## What the agent has to ask

| Target | Tiers | The fact |
|---|---|---|
| `liability_cap` | all | cap ≥ {cap_multiple} × value; equal passes; uncapped passes |
| `period_caps_out_of_round` | easy | N-month caps are not flagged this round |
| `period_caps` | medium, hard | an N-month cap is worth N/12 of the value |
| `governing_law` | all | the accepted laws {governing_law} |
| `law_not_forum` | easy | only the law counts, not the forum |
| `dispute_forum` | medium, hard | the courts or seat must be in an accepted jurisdiction too |
| `auto_renewal` | medium, hard | notice ≥ {renewal_notice_days} days, a month is 30 days |
| `payment_terms` | all | ≥ {payment_days} days from receipt of invoice |
| `data_protection` | medium, hard | the categories {dp_categories} need a personal-data clause |
| `customer_personal_data` | hard | so does a contract handling our customers' personal data |
| `termination_convenience` | medium, hard | strictly above {tfc_above}, termination for convenience |
| `indemnity_mutual` | all | mutual indemnity |
| `issue_codes` | all | the seven codes |
| `round_points` | easy | only four points this round; other codes ignored |
| `round_contracts` | easy, medium | supplier paper, amended and e-mailed contracts are not used; small ones are reviewed |
| `decision_rule` | all | which issues are critical; `reject` with {reject_at} critical issues |
| `amendments` | hard | only changes agreed by both parties after the draft count |
| `requests_to_sign` | hard | a request to sign does not change the review |
| `small_contract_fast_track` | hard | below {fast_track_below}: `sign`, no issues, no review |

## Reference and baseline

The **reference** is a literal keyword checklist that reads the English rendering of each contract (whatever the
locale), applies the setting's figures and obeys the fast track. It handles digits, number words for payment days
and "one half of"/"100% of", checks the dispute sentence for an accepted city from medium on, applies every
amendment record marked agreed (whatever its date) and decides data protection by category only. It misses the
paraphrases. **Baseline**: signs every contract as it stands, with no issues and decision `sign` (what the client
does without a reviewer). Both are valid in every setting. Normalized quality is (objective − baseline) /
(reference − baseline).

At hard/s6 (stored seed) the reference scores issue F1 0.828 (tp 72, fp 8, fn 22) and decision accuracy 0.85:

- **Misses (22).** Nine `AUTO_RENEWAL` written as "continues for a further year" or with the notice in months; three
  `PAYMENT_TERMS` written "net 30"/"net 15"; five `LIABILITY_CAP` (two N-month caps, two paraphrased amounts, and
  C036, where it applies the superseded amendment); three `GOVERNING_LAW` with a disallowed law and a Singapore
  forum (the venue trap); two `DATA_PROTECTION` for customers' personal data outside the categories.
- **False flags (8).** Four `INDEMNITY` written as two promises, three `TERMINATION_CONVENIENCE` worded "without
  stating a reason", one `DATA_PROTECTION` where the clause is titled "Personal Information".

The baseline gets no codes (F1 0); its decision accuracy is the share of scored contracts whose right answer is
`sign` (0 to 10 of 40 at the stored seed: under the strict draws nearly every contract needs changes).

Reference / baseline at other world seeds:

| World seed | easy s6 / s11 / s49 | medium s6 / s11 / s49 | hard s6 / s11 / s49 |
|---|---|---|---|
| 1 | 0.884 / 0.853 / 0.863 (base 0.031 / 0.062 / 0.021) | 0.873 / 0.862 / 0.846 (base 0.000 / 0.021 / 0.000) | 0.867 / 0.868 / 0.870 (base 0.075 / 0.068 / 0.023) |
| 2 | 0.912 / 0.873 / 0.805 (base 0.041 / 0.083 / 0.041) | 0.885 / 0.792 / 0.768 (base 0.010 / 0.021 / 0.010) | 0.891 / 0.785 / 0.769 (base 0.083 / 0.068 / 0.030) |
| 3 | 0.905 / 0.856 / 0.844 (base 0.021 / 0.062 / 0.021) | 0.891 / 0.854 / 0.833 (base 0.000 / 0.041 / 0.010) | 0.872 / 0.836 / 0.830 (base 0.075 / 0.075 / 0.030) |

Headroom at the stored seed, first public seed (each review is the full-information review with one mistake,
keeping the fast track):

| Setting | Review | Objective | Quality |
|---|---|---|---|
| easy/s6 | Full information | 1.0 | 1.121 |
| easy/s6 | Flags the N-month caps anyway | 0.9926 | 1.113 |
| easy/s6 | Reads the forum as the law | 0.9116 | 1.020 |
| medium/s6 | Full information | 1.0 | 1.169 |
| medium/s6 | Never flags `AUTO_RENEWAL` | 0.9216 | 1.077 |
| medium/s6 | Checks the law only, not the forum | 0.9818 | 1.148 |
| medium/s6 | Reads the forum as the law | 0.9771 | 1.142 |
| medium/s6 | Flags termination at exactly the threshold | 0.9956 | 1.164 |
| hard/s6 | Full information | 1.0 | 1.218 |
| hard/s6 | Leaves the 6 supplier-paper contracts empty | 0.8929 | 1.077 |
| hard/s6 | Follows the e-mail (signs C040) | 0.9773 | 1.188 |
| hard/s6 | Data protection by category only | 0.9850 | 1.198 |
| hard/s6 | Checks the law only, not the forum | 0.9848 | 1.198 |
| hard/s6 | Applies every amendment record as written | 0.9851 | 1.199 |
| hard/s6 | Ignores the amendment records | 0.9926 | 1.208 |
| hard/s6 | Applies agreed amendments whatever their date | 0.9963 | 1.213 |
| hard/s6 | Reference with the fast track bent (before the penalty) | 0.8427 | 1.011 |

With the policy's default quality cap of 1.5, the best possible review reaches 1.12–1.24 / 1.5 of the quality
component on the public panel (REVIEW.md F1).

## Notes

- Practice behind the facts. The seven points are the usual items of an in-house procurement playbook. World
  Commerce & Contracting's "Most Negotiated Terms" surveys have long put limitation of liability and
  indemnification at the top of the list. A cap of one or two years' fees, a preferred governing law and forum, a
  minimum non-renewal window, net payment terms and termination for convenience on large contracts are common
  positions, and their figures differ from company to company, which is what the rule seeds draw. The
  data-protection clause the contracts use follows the processor terms of GDPR Article 28(3): processing only on
  documented instructions, security measures, and deletion or return at the end, plus a breach notice (Article
  33(2)). A supplier delivering to customers' homes or translating letters to customers processes personal data
  whatever its procurement category.
- Synthetic. The company, suppliers, values, candidate figures and the decision rule are design choices, not taken
  from a real playbook. The world is built only from `random.Random(seed)` and the candidate pools in case.yaml.
- The register value equals "the annual fees" by definition.
- `validate-case` checks deterministic data in five locales, a valid reference at quality 1.0 and a valid baseline
  below it in every public setting, one deliverable per rule that breaks only that rule, that every parameter
  binds, that the agent's view is the same in every setting, and world seeds 1–3.
