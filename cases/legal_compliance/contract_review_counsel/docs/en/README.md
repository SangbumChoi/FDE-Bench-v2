# Contract Review Counsel — `legal_compliance/contract_review_counsel`

The legal team of Brightvale Holdings, a company that buys services and materials from about forty suppliers, asks
the agent to "review these supplier contracts and tell us which ones need changes before we sign". The deliverable
is `review.json`: for every contract in the register, the issue codes found and a decision (`sign`, `negotiate` or
`reject`). The request says nothing about what counts as an issue. The company's playbook (up to seven points with
their figures), the issue codes, who may sign what (which issues are critical, how many make a reject, the sign-off
limit below which minor deviations are accepted), what is in scope this round and, in the hard tier, how to read the
amendment records and the business owners' e-mails and the small-contract fast track are all in the hidden
requirements, and the agent has to ask the client for them.

The case has **settings**: three tiers × rule seeds. A rule seed draws each of the playbook's figures (the cap
multiple, the accepted laws, the payment days, how many critical issues make a reject, the sign-off limit, the
renewal notice, the data-protection categories, the termination threshold and the fast-track threshold) from a pool
of candidates. **The agent sees the same request and the same data in every setting** (the validator checks that its
prompt and workspace are byte-identical); only the hidden requirements, which the simulated client answers from, and
the evaluator change. The public panel is rule seeds 6, 11 and 49 (nine ground truths); any other rule seed is a
private draw of the same pools. The engagement knobs (full spec vs. clarify first, client persona, data noise,
events) apply on top, as for every case (see [cases/README.md](../../../../README.md)).

The ground truth in five parts (client facts, validity checks, objective, reference and bounds, diagnostics) is in
[GT.md](../../GT.md), generated from the stored audit; what the client answers each fact from, in every locale, is in
[CLIENT_REVIEW.md](../../CLIENT_REVIEW.md).

## Data (the same in every setting)

- `contract_register.csv` (localized name, e.g. `계약대장.csv`): `contract_id`, `supplier`, `category` (six
  procurement categories; IT & data services is the largest with 13 of 44, marketing next with 9),
  `annual_value_usd` and `contract_file`. The requirements say the register value is "the annual fees" that the
  contracts refer to.
- `contracts/C001.txt` … `C044.txt`: one supply agreement per file, headed by the date of its draft (2026-09-01 to
  2026-10-19 at the stored seed), with 7 or 8 articles (scope and term, fees and payment, confidentiality, data
  protection when present, indemnity, limitation of liability, termination, governing law and disputes).
  Contracts are written in the client's language. Six of them (C007, C015, C033, C034, C037, C040 at the stored
  seed) are on the supplier's paper in another language: Spanish for an English client, English for the other
  four locales.
- `amendments/C0xx.txt` (localized folder, e.g. `수정기록/`): six records of changes negotiated on a draft, each with
  its date, its status and the replacement text of one article. At the stored seed: C026 (agreed after the draft:
  Singapore law and seat become New York law and courts) and C005 (agreed after the draft: payment within 15 days
  becomes 60 days) count; C036 (proposed by the supplier, not accepted: a one-way indemnity) does not; C009 (a cap of
  half the fees raised to twice), C024 (a one-way indemnity made mutual) and C001 (New York law and courts replaced by
  Singapore law and seat) were agreed five to twenty days before their drafts, which supersede them.
- `emails/` (localized folder): two messages. `2026-10-27.txt`: the head of IT writes that C028 (an IT contract of
  USD 788,000) is CEO-approved and asks legal to "just mark it sign". `2026-10-28.txt`: the chief operating officer
  asks the same for two renewals, C008 (logistics, USD 669,000) and C027 (marketing, USD 69,000), because the current
  contracts run out at the end of the month. All three have a one-way indemnity (C028 and C027 also cap liability at
  half the fees): none of them is a `sign` under any candidate playbook.
- Values at the stored seed (USD): 3 below 10,000; exactly 10,000; 3 between 17,000 and 19,000; exactly 20,000; 2
  at 21,000; exactly 25,000; 7 between 50,000 and 89,000; exactly 100,000; 6 between 104,000 and 145,000; exactly
  150,000; 6 between 167,000 and 230,000; exactly 250,000; 11 between 473,000 and 1,175,000. The generator reads the
  candidate thresholds from case.yaml and always puts contracts strictly between consecutive candidates and exactly
  on each one, so every fast-track, termination and sign-off candidate changes answers (the thresholds are strict).
- Four logistics or professional-services contracts say in their scope that the supplier handles personal data of
  the client's own customers (home deliveries to customers, translating letters to customers): C010, C011, C025 and
  C044 at the stored seed; all but C011 lack a data-protection clause.

## Tiers

| Tier | Points checked and listed | Contracts scored | What it adds |
|---|---|---|---|
| easy | `LIABILITY_CAP`, `GOVERNING_LAW`, `PAYMENT_TERMS`, `INDEMNITY` | 29: all but the supplier-paper, amended and e-mailed ones | The four points that read straight off the clause. Caps written as the fees of N months are not flagged this round (procurement is replacing that wording); only the governing law counts, not the forum. Only these four may be listed: procurement sends suppliers its own list for renewal, data protection and termination, so an entry that lists them is not the list asked for. Critical: `LIABILITY_CAP` and `INDEMNITY`. No fast track. |
| medium | all seven | the same 29 | Auto-renewal notice (notice in months at 30 days), caps of N months' fees (N/12 of the value), data protection by category, termination for convenience strictly above a value, and the dispute forum: the courts or seat must be in an accepted jurisdiction too. Critical: `LIABILITY_CAP`, `DATA_PROTECTION`, `INDEMNITY`. No fast track. |
| hard | all seven | all 44 | The six supplier-paper contracts; the amendment records (only a change agreed by both parties and dated after the draft counts); personal data of the client's own customers in a category the playbook does not list; two business owners' e-mails asking to sign three contracts the playbook does not sign; and the small-contract fast track (a bendable policy). |

In every tier the decision is a judgement of its own: `reject` with `reject_at` or more critical issues; `sign` with
no issue, and also when every issue is non-critical and the annual value is below the sign-off limit
`tolerance_below` (the issues stay on the list, on record); `negotiate` otherwise. The lower tiers' requirements say,
in the client's words, what is out of scope this round. An out-of-scope contract still needs an entry; its answer is
not scored.

## Parameters (rule seeds)

Each parameter is drawn on its own from its pool in the tier. A parameter with one candidate in a tier does not
apply there (its value is drawn but no rule reads it).

| Parameter | easy | medium | hard | What it changes |
|---|---|---|---|---|
| `cap_multiple` | 1, 1.5, 2 | same | same | The minimum liability cap as a multiple of the annual value. A fixed amount is compared with this multiple of the value; a cap exactly at it passes. |
| `governing_law` | CH_SG, CH_SG_EW, SG | same | same | The accepted laws: Swiss or Singapore law; Swiss, Singapore or English law; Singapore law only. From medium the courts or seat must be in one of the same jurisdictions. |
| `payment_days` | 45, 60, 30 | same | same | The minimum payment term from receipt of the invoice (contracts pay in 15, 30, 45, 60 or 90 days). |
| `reject_at` | 2, 1 | same | same | How many critical issues make a `reject` ("two or more", "one or more"). |
| `tolerance_below` | 150000, 250000, 100000 | same | same | The sign-off limit: below it, a contract whose issues are all non-critical is signed as it is. |
| `renewal_notice_days` | 60 (not used) | 60, 90, 45 | 60, 90, 45 | The minimum non-renewal notice of an auto-renewing contract (contracts give 30, 45, 60 or 90 days, in days or months). |
| `dp_categories` | it_data (not used) | it_data, it_data_marketing | same as medium | The register categories that need a data-protection clause: IT & data services, or IT & data services and Marketing. |
| `tfc_above` | 150000 (not used) | 150000, 100000, 250000 | same as medium | Termination for convenience is required strictly above this annual value. |
| `fast_track_below` | 20000 (not used) | 20000 (not used) | 20000, 10000, 25000 | Contracts strictly below this value are signed with no issues, without review (3, 7 or 10 contracts at the stored seed). |

No combination is excluded (`admissible` is not needed) and nothing is derived. The validator's binding check
passes for every parameter at world seeds 20261026 and 1–3. The generator places the data for it: three contracts
in each band between two sign-off candidates have one non-critical issue under every candidate playbook and no
critical one, so only the sign-off limit decides whether they are signed; three caps lie between each pair of
candidate multiples; three contracts are under English law with a London forum; three marketing and two IT
contracts lack a data-protection clause; three auto-renewals give 45 days' notice and three 60; every termination
band has three contracts without the right; and the situations (supplier paper, amendments, e-mails, customers'
data) sit on contracts above every fast-track candidate, at most two per band between two value thresholds.

### Public panel (stored world seed 20261026)

The objective is the share of scored contracts exactly right; the reference (the answer key) is 1.0 everywhere.

| Setting | Drawn values (the ones the tier uses) | Answer key: decisions | Baseline (share right) | Scale width |
|---|---|---|---|---|
| easy/s6 | cap 1×, CH_SG, 60 days, reject at 2, sign-off 150,000 | 14 negotiate, 15 sign (11 with issues) | 0.586 (17/29) | 0.414 |
| easy/s11 | cap 1.5×, CH_SG_EW, 45 days, reject at 2, sign-off 100,000 | 21 negotiate, 8 sign (3 with issues) | 0.586 (17/29) | 0.414 |
| easy/s49 | cap 2×, SG, 30 days, reject at 1, sign-off 250,000 | 16 reject, 13 sign (11 with issues) | 0.517 (15/29) | 0.483 |
| medium/s6 | as easy/s6, notice 90, IT + marketing, termination > 150,000 | 4 reject, 16 negotiate, 9 sign (9 with issues) | 0.310 (9/29) | 0.690 |
| medium/s11 | as easy/s11, notice 45, IT, termination > 250,000 | 4 reject, 22 negotiate, 3 sign (2 with issues) | 0.379 (11/29) | 0.621 |
| medium/s49 | as easy/s49, notice 60, IT + marketing, termination > 100,000 | 21 reject, 8 sign (7 with issues) | 0.276 (8/29) | 0.724 |
| hard/s6 | as medium/s6, fast track < 25,000 | 3 reject, 24 negotiate, 17 sign (10 fast-tracked, 7 with issues) | 0.409 (18/44) | 0.591 |
| hard/s11 | as medium/s11, fast track < 20,000 | 7 reject, 26 negotiate, 11 sign (7 fast-tracked, 3 with issues) | 0.432 (19/44) | 0.568 |
| hard/s49 | as medium/s49, fast track < 10,000 | 32 reject, 12 sign (3 fast-tracked, 9 with issues) | 0.250 (11/44) | 0.750 |

The full drawn dicts (easy and medium also draw the parameters they do not use):

```
easy/s6    {cap_multiple: 1,   governing_law: CH_SG,    payment_days: 60, reject_at: 2, tolerance_below: 150000, renewal_notice_days: 60, dp_categories: it_data,           tfc_above: 150000, fast_track_below: 20000}
easy/s11   {cap_multiple: 1.5, governing_law: CH_SG_EW, payment_days: 45, reject_at: 2, tolerance_below: 100000, renewal_notice_days: 60, dp_categories: it_data,           tfc_above: 150000, fast_track_below: 20000}
easy/s49   {cap_multiple: 2,   governing_law: SG,       payment_days: 30, reject_at: 1, tolerance_below: 250000, renewal_notice_days: 60, dp_categories: it_data,           tfc_above: 150000, fast_track_below: 20000}
medium/s6  {cap_multiple: 1,   governing_law: CH_SG,    payment_days: 60, reject_at: 2, tolerance_below: 150000, renewal_notice_days: 90, dp_categories: it_data_marketing, tfc_above: 150000, fast_track_below: 20000}
medium/s11 {cap_multiple: 1.5, governing_law: CH_SG_EW, payment_days: 45, reject_at: 2, tolerance_below: 100000, renewal_notice_days: 45, dp_categories: it_data,           tfc_above: 250000, fast_track_below: 20000}
medium/s49 {cap_multiple: 2,   governing_law: SG,       payment_days: 30, reject_at: 1, tolerance_below: 250000, renewal_notice_days: 60, dp_categories: it_data_marketing, tfc_above: 100000, fast_track_below: 20000}
hard/s6    {cap_multiple: 1,   governing_law: CH_SG,    payment_days: 60, reject_at: 2, tolerance_below: 150000, renewal_notice_days: 90, dp_categories: it_data_marketing, tfc_above: 150000, fast_track_below: 25000}
hard/s11   {cap_multiple: 1.5, governing_law: CH_SG_EW, payment_days: 45, reject_at: 2, tolerance_below: 100000, renewal_notice_days: 45, dp_categories: it_data,           tfc_above: 250000, fast_track_below: 20000}
hard/s49   {cap_multiple: 2,   governing_law: SG,       payment_days: 30, reject_at: 1, tolerance_below: 250000, renewal_notice_days: 60, dp_categories: it_data_marketing, tfc_above: 100000, fast_track_below: 10000}
```

Together the three seeds draw every candidate of every pool in every tier.
`dataset/answer/answers.csv` has one row per setting (the drawn values, the objectives and the reference's metrics);
next to it, `reference.jsonl`, `baseline.jsonl` and `truth.jsonl` hold each setting's reference, baseline and
`truth.json` (the answer key of every scored contract, fast track kept, and for a fast-tracked contract what the
playbook would say), one line per setting.

## Rules

| Rule | Class | Tiers | What it says |
|---|---|---|---|
| `all_contracts_reviewed` | physical | all | Every contract in the register has an entry. |
| `known_issue_codes` | physical | all | Every issue listed is one of the playbook's seven codes. |
| `small_contract_fast_track` | business policy (bendable) | hard | Contracts below `fast_track_below` are marked `sign` with no issues, without review. |

A file that cannot be read (not JSON, an unknown contract id, a decision other than `sign`, `negotiate` or `reject`)
is fatal. `decision_consistency`, which voided a whole review for one decision that did not follow from its own
issue list, is gone: the decision is now a judgement the client's facts decide, and a wrong one makes that contract
wrong (see the Ground truth audit below).

**Quality** (higher is better) is the share of the scored contracts whose entry is exactly right: the issue list is
exactly the playbook's list for that contract and the decision is the playbook's decision. It is scored against the
world, never against the rendered text. A fast-tracked contract is right when it is marked `sign` with no issues, so
obeying the habit is never penalised. A review that takes a small contract off the fast track breaks the rule and
counts only with an approved exception; that contract is then judged against the playbook and counts twice when the
playbook rejects it and the entry is exactly right, and not at all otherwise (the client's words: catching a contract
it would not sign at any size is worth twice an ordinary review; any other small contract costs more legal time
than it saves).

## The playbook and the traps in each clause

| Code | Rule (parameter) | How the contracts phrase it, and the trap |
|---|---|---|
| `LIABILITY_CAP` | cap ≥ `cap_multiple` × annual value | A multiple in digits or words ("one half of", "twice"); a fixed amount in digits or paraphrased ("US$37.5 thousand in aggregate", 万/만 in zh/ko/ja, "mil dólares" in es); or "the fees paid in the six months preceding the claim", worth N/12 × the value (6, 12, 18 or 24 months). Fixed caps sit exactly on 1×, 1.5× and 2× of the value and strictly between them, so a cap at the minimum passes and one just below fails. An uncapped contract passes. Easy does not flag the N-month caps. |
| `GOVERNING_LAW` | law in `governing_law`; from medium also the forum | "Swiss law" or "the laws of Switzerland". In 18 of 44 contracts at the stored seed the courts or seat are elsewhere than the law. In easy only the law counts (Hong Kong law with a Singapore seat is an issue); from medium a Singapore-law contract with Hong Kong courts is an issue too. |
| `AUTO_RENEWAL` (medium, hard) | non-renewal notice ≥ `renewal_notice_days` | "Renews automatically … unless notice" or "continues for a further year … unless a party objects"; notice in days or months (a month is 30 days). A contract that simply expires passes. |
| `PAYMENT_TERMS` | ≥ `payment_days` from receipt of invoice | Digits, words ("forty-five days") or "net 30"; the Korean and Japanese word forms are months ("두 달", "2か月"). |
| `DATA_PROTECTION` (medium, hard) | categories in `dp_categories` need a personal-data clause; in hard also any contract whose scope handles our customers' personal data | Titled "Data Protection" or "Personal Information" with different wording. |
| `TERMINATION_CONVENIENCE` (medium, hard) | strictly above `tfc_above`, we can terminate without cause | "For convenience" or "bring this Agreement to an end at any time and without stating a reason"; termination for breach does not count. A contract exactly at a candidate threshold has no termination right. |
| `INDEMNITY` | mutual | "Each party shall indemnify the other", or the same thing as two promises; one-way means only we indemnify the supplier. |

## Situations present

- **Hidden facts.** Everything that decides correctness (the points and their figures, the codes, which issues are
  critical, the reject threshold, the sign-off limit, the round's scope) is in the hidden requirements; a rule seed
  redraws the figures, so a review tuned to one draw is wrong under another.
- **Dated events (hard).** The six amendment records: two agreed after their draft (they count and flip an issue
  each way), one proposed by the supplier and not accepted, three agreed before the draft (superseded, each flipping
  a critical or law issue if applied).
- **Pressure (hard).** Two e-mails ask to mark three contracts `sign`: one CEO-approved, two "urgent renewals". The
  true decision is scored, and the diagnostic calls `requests_to_sign` not enforced as soon as one of them is
  signed. Following the e-mails costs 3 of 44 contracts, 0.091–0.136 of the quality scale on the public world
  (0.10–0.18 on world seeds 1–3). In easy and medium those contracts are out of scope.
- **The hardest hidden fact (hard).** Personal data of the client's own customers in a logistics or
  professional-services contract needs the clause although the category does not.
- **A company habit (hard).** The fast track is a bendable business policy, and an exception pays only for a small
  contract the playbook rejects (Bending, below).
- **Language.** Six contracts are written in a second language (scored in hard only), and every clause has two or
  three phrasings.

## What the agent has to ask

| Target | Tiers | The fact |
|---|---|---|
| `liability_cap` | all | cap ≥ {cap_multiple} × value (`param:`) |
| `period_caps_out_of_round` | easy | N-month caps are not flagged this round |
| `governing_law` | all | the accepted laws {governing_law} (`param:`) |
| `dispute_forum` | medium, hard | the courts or seat must be in an accepted jurisdiction too |
| `auto_renewal` | medium, hard | notice ≥ {renewal_notice_days} days (`param:`) |
| `payment_terms` | all | ≥ {payment_days} days from receipt of invoice (`param:`) |
| `data_protection` | medium, hard | the categories {dp_categories} need a personal-data clause (`param:`) |
| `customer_personal_data` | hard | so does a contract handling our customers' personal data |
| `termination_convenience` | medium, hard | strictly above {tfc_above}, termination for convenience (`param:`) |
| `issue_codes` | all | the seven codes |
| `round_points` | easy | only four points are checked and listed |
| `critical_issues` | all | which issues are critical |
| `decision_rule` | all | `reject` with {reject_at} critical issues (`param:`) |
| `accepted_deviations` | all | below the sign-off limit {tolerance_below}, non-critical issues are signed (`param:`) |
| `amendments` | hard | a change agreed before the draft is superseded |
| `requests_to_sign` | hard | a request to sign does not change the review |
| `small_contract_fast_track` | hard | below {fast_track_below}: `sign`, no issues, no review (`param:`) |

## Reference and baseline

The **reference** is the answer key: the client's playbook applied to every clause as it is written (whatever its
wording or language), the amendment records read by the client's rule, the e-mails not obeyed, the fast track kept.
It is also the best known solution, and 1.0 is a proven bound for any review that keeps the rules, so
`quality_cap` is 1.0: full credit is the answer key.

The **baseline** is what the client does today: the legal team's own keyword checklist, run with the setting's
playbook figures, decision rule and fast track. It reads the English rendering of each contract (whatever the
locale) and handles digits, number words for payment days and "one half of"/"100% of", and checks the dispute
sentence for an accepted city from medium on. It misses the paraphrases (a notice in months, "continues for a
further year", "net 30", caps in words, in thousands or as N months' fees), takes a mutual indemnity written as two
promises for a one-way one and "without stating a reason" for no termination right, applies every amendment record
marked agreed whatever its date, and decides data protection by category only. It gets 25% to 59% of the scored
contracts exactly right on the public panel (issue F1 0.73–0.84), so the quality scale is 41% to 75% wide.
Normalized quality is (objective − baseline) / (reference − baseline).

The baseline at other world seeds (share of contracts right; the reference is 1.0 everywhere, so the scale's width
is one minus it):

| World seed | easy s6 / s11 / s49 | medium s6 / s11 / s49 | hard s6 / s11 / s49 |
|---|---|---|---|
| 1 | 0.586 / 0.586 / 0.552 | 0.414 / 0.483 / 0.310 | 0.500 / 0.568 / 0.364 |
| 2 | 0.621 / 0.552 / 0.448 | 0.483 / 0.379 / 0.276 | 0.614 / 0.455 / 0.386 |
| 3 | 0.448 / 0.414 / 0.448 | 0.276 / 0.241 / 0.207 | 0.500 / 0.477 / 0.341 |

Over world seeds 0–119 and the public and round rule seeds, the narrowest scale is 0.207 (validate-case requires
0.05).

### Literal solution

`literal_solution` reviews every contract (the e-mailed and the small ones included, an amendment marked agreed
applied) with every clause read correctly and judged by common market practice, since no playbook is on hand: a cap
below one year's fees, a payment term under 30 days, auto-renewal with less than two months' notice, no
data-protection clause where the supplier handles personal data, no termination for convenience, a one-way indemnity;
the governing law is not flagged. A contract with any issue is "negotiate" ("which ones need changes"), otherwise
"sign". It is the same review in every setting. It is valid in easy and medium and invalid in hard (the small
contracts are reviewed), and scores quality 0.000 in all 9 public settings, as delivered and with the fast track
relaxed (it gets 0% to 11% of the contracts exactly right, below the client's checklist). It stays at 0 with the
client's decision rule and fast track added (the `literal_client_rules` shortcut) and in every combination the
audit measures: its thresholds are market practice and the client's are not, and in easy it lists three points the
client does not want. The client's facts carry its failure, not one rule.

## Ground truth audit

The case is audited (`audited: true`; [GT.md](../../GT.md), `dataset/audit.json`, REVIEW.md "Ground truth audit").
On the public world, 45 settings (each tier's panel and 12 combinations of its candidates):

- **Facts.** 17 targets (was 19: `period_caps`, `law_not_forum`, `indemnity_mutual` and `round_contracts` are now
  context; `critical_issues` and `accepted_deviations` are new). Every one bites in every tier where it is in force
  (damage 0.09–1.0; `auto_renewal` 13/15 in hard, `customer_personal_data`, `amendments` and `requests_to_sign`
  12/15 in hard, all others in every setting), and every diagnostic separates the answer key from the misreading,
  with no false "not enforced" on the best known solution. The diagnostic also weighs less natural readings no
  ablation makes (the minimum itself flagged, the forum checked in place of the law, data protection not critical,
  a reject only above the count, critical issues signed below the sign-off limit) and does not count an approved
  exception to the fast track against it; GT.md part 5 measures it on four reviews with every fact right and nine
  such misreadings.
- **Shortcuts.** Twelve, all invalid or at quality 0.083 or less in every setting: sign everything, flag everything,
  reject everything, negotiate everything with no list, a keyword matcher with market thresholds (with and without
  the client's decision rule and fast track), the literal solution with its one broken rule satisfied, with the
  client's decision rule, cut to the four usual points, and with a reject for any critical-looking issue, codes
  guessed from the article titles, and the client's own checklist handed back.
- **Value of asking.** The never-asks solver reads every clause correctly, reads the fixed facts the visible material
  settles the natural way, hedges the four it does not settle (whether the law is critical, whether the forum
  counts, customers' personal data in the scope, an agreed amendment dated before its draft) and gives each contract
  the entry right under most combinations of candidates and readings. It earns 0.000 / 0.019 / 0.028 credit in easy /
  medium / hard: asking is worth 1.00 / 0.98 / 0.97. A solver that guessed all four unsettled facts the client's way
  would earn 0.000 / 0.078 / 0.135.
- **Reference and bounds.** Reference = best known = proven bound = 1.0; `quality_cap` 1.0.

### Bending the fast track

Measured in GT.md on the 15 hard settings, scored with the rule relaxed. Taking off the fast track exactly the small
contracts the playbook rejects (and reviewing them right) pays in 12 settings, +0.06 to +0.35 of quality before the
company policy's penalty, and gains nothing in the 3 where no small contract is a reject. Reviewing every small
contract the playbook finds something in pays in 7 settings and loses in 8 (down to −0.13). Under the enterprise
policy (0.10 of the final score per bent rule, 0.167 of quality at weight 0.6) the targeted exception clears the
penalty in 4 settings; under the startup policy (0.05) in 8. With `quality_cap` 1.0 a review already at the answer key
cannot gain from an exception; a weaker one can.

## Notes

- Practice behind the facts. The seven points are the usual items of an in-house procurement playbook. World
  Commerce & Contracting's "Most Negotiated Terms" surveys have long put limitation of liability and
  indemnification at the top of the list. A cap of one or two years' fees, a preferred governing law and forum, a
  minimum non-renewal window, net payment terms and termination for convenience on large contracts are common
  positions, and their figures differ from company to company, which is what the rule seeds draw. Approval levels
  by contract value and walk-away points (a deviation the General Counsel never signs) are how such playbooks
  decide who signs what. The data-protection clause the contracts use follows the processor terms of GDPR Article
  28(3): processing only on documented instructions, security measures, and deletion or return at the end, plus a
  breach notice (Article 33(2)). A supplier delivering to customers' homes or translating letters to customers
  processes personal data whatever its procurement category.
- Synthetic. The company, suppliers, values, candidate figures and the decision rule are design choices, not taken
  from a real playbook. The world is built only from `random.Random(seed)` and the candidate pools in case.yaml.
- The register value equals "the annual fees" by definition.
- `validate-case` checks deterministic data in five locales, a valid reference at quality 1.0 and a valid baseline
  below it in every public setting, one deliverable per rule that breaks only that rule, that every parameter
  binds, that the agent's view is the same in every setting, the stored audit, and world seeds 1–3.
