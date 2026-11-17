# Review — `legal_compliance/contract_review_counsel`

Findings of the case review (F1–F9) and what this change did about each. Numbers are at world seed 20261026
unless stated. The rule-seed conversion (last section) updates several statuses; each update
follows the status it amends, and the older figures are kept as they were measured. The review was written before the F2 fix (reference 0.7677) and against a 1.0 quality cap; the
current figures are given where they differ. Comments welcome on the open proposals.

### F1 — Quality saturates below real review competence (high, confirmed)

The reference is a literal keyword checklist over the English rendering. Before this change it scored 0.7677,
and a full-information review that obeys the fast track scored 0.8794 (quality 1.145). Under the old 1.0 cap,
every single-trap mistake (no `TERMINATION_CONVENIENCE`, no renewal threshold, venue read as the law, equal caps
flagged, foreign paper left empty) still earned full credit. On the current scale (baseline 0, policy cap 1.5) and
after F2, the reference is 0.8825 and the full-information review is 1.0 (quality 1.153). The single-trap mistakes
now score 1.045–1.094 (1.018 when both renewal and termination are dropped), so they are told apart, but the best
possible review reaches only 1.153 / 1.5 ≈ 0.77 of the quality credit. At world seeds 1–3 the ceiling is 1.196,
1.239 and 1.320.

**Status:** open — proposal: strengthen the reference so that it resolves the paraphrase classes it misses today
(month and word notice periods, "continues for a further year", period caps as N/12, "US$… thousand",
"without stating a reason", mutual indemnity written as two promises, law vs. venue). That puts it near the
ceiling, and the remaining headroom then comes from genuinely hard items. Alternatively keep the weak reference
and set `quality_cap` near the full-information quality (about 1.15–1.3 depending on the world seed), so a perfect
review earns full credit. Either way, add more hard items per contract so that one missed trap costs measurable
quality.

**Update (rule seeds):** still open. The reference stays the literal checklist; it now also misses the venue trap
in more contracts, customers' personal data outside the listed categories (hard) and the superseded amendment
(hard). On the public panel the full-information review reaches quality 1.12–1.24 (1.121 / 1.195 / 1.161 easy,
1.169 / 1.179 / 1.154 medium, 1.218 / 1.235 / 1.172 hard at the stored seed), so the best review earns about
0.75–0.82 of the quality credit under the 1.5 cap.

### F2 — Obeying the fast-track rule was penalised (high, confirmed)

The truth for the 8 contracts below USD 20,000 held their playbook issues (11 codes; C029 a `reject`, C017 three
issues), while the fast-track rule forced `sign` with no issues. Obeying the client therefore cost 11 recall
points and 8 decisions: 11 of the reference's 20 misses came from following the rule. Bending the rule could not
help a reference-level agent either, because quality was clipped and the soft-rule penalty applied.

**Status:** fixed in this change — `evaluate_review` now judges a small contract against "sign, no issues" when
the review keeps the fast track. It uses the playbook issues only when the review breaks the rule, and such a
review counts only once the rule is relaxed through an approved exception. The reference rises from 0.7677 to
0.8825 (fn 20 → 9, decision accuracy 0.70 → 0.90). The reference with the fast track bent scores 0.8595 (quality
0.970) before the penalty, so bending never pays. The quality sentence in requirements.md says this in all five
locales. Still open: a scored reason to bend (e.g. a small IT contract that processes personal data with no
data-protection clause, where an approved exception plus flagging it beats obeying). Also open: the catalog row
in cases/README.md ("Accept vendor paper under a value threshold"), which lies outside this case's directory.

**Update (rule seeds):** the fix is kept unchanged; the fast track now applies in the hard tier only, with its
threshold drawn from 10,000 / 20,000 / 25,000, and the requirements say "every other contract is reviewed this
round, the small ones included" in easy and medium. Bending still never pays: at hard/s6 a perfect review scores
the same before the 0.1 soft-rule penalty, and the reference bent scores 0.8427 against 0.8343.

### F3 — The decision adds no information; two all-or-nothing gates (high, confirmed)

`decide()` is a pure function of the listed issues. `decision_consistency` invalidates the whole review on any
mismatch, and decision accuracy compares `decide(pred)` with `decide(truth)`, so the 0.3 weight only re-weights
issue correctness on the critical codes. An agent that never learns of the fast track is invalid under the
`baseline` and `regulated_strict` policies (exceptions forbidden), and so is one that guesses another reject rule.

**Status:** open — proposal: give the decision a fact of its own that the client holds. Examples: approval levels
by value, supplier criticality, or which issues are walk-away points and which are negotiable. Score it
separately. Consider grading `decision_consistency` per contract instead of zeroing the review. If asking about
the fast track is meant as the key test, say so in the README.

**Update (rule seeds):** partly. The decision rule now holds a drawn fact the client must give: `reject_at` (a reject
with two or more, or one or more, critical issues), and which codes are critical depends on the tier (in easy only
`LIABILITY_CAP` and `INDEMNITY`). The decision is still a function of the listed issues, and `decision_consistency`
still voids the whole review; grading it per contract stays open.

### F4 — No settings, and the world hides the threshold gaps (high, confirmed)

There is one ground truth (`setting.json` is `{}`). Values come from three disjoint bands (6,000–19,500,
25,000–150,000, 160,000–1,200,000), and the observed values jump from 19,000 to 26,000 and from 131,500 to 268,000.
Any fast-track cut in (19k, 26k] or termination cut in [131.5k, 268k) therefore gives the same truth. Notice and
payment days come only from {30, 45, 60, 90}, and the gaps hint at where the thresholds lie.

**Status:** open — proposal: three tiers. Easy covers the four points that read straight off the clause (caps,
law, payment, indemnity), with renewal, data protection and termination "checked by procurement this round".
Medium adds month conversion, period caps, data protection by category, termination by value and the venue trap.
Hard adds the foreign paper, the fast track and the F5 situations. Three rule sets over law, notice days, payment
days, termination threshold, cap multiple, fast-track threshold and which codes are critical, for example
A = CH/SG, 60 d, 45 d, >150k, ≥1×, <20k; B = + England & Wales, 90 d, 60 d, >500k, ≥1.5×, <10k; C = SG only, 45 d,
30 d, >100k, ≥2× for IT, <25k. Redraw values, notice days, payment days and cap multiples so they straddle every
candidate threshold, and check that each rule set's reference is invalid or at least 1% worse under the others.

**Update (rule seeds):** fixed by the conversion (see Rule seeds below). Three tiers as proposed, eight parameters
drawn by rule seeds instead of fixed rule sets, and a generator that puts contract values strictly between and
exactly on every fast-track and termination candidate, caps on and between 1×, 1.5× and 2×, notice and payment
terms on both sides of every candidate. Every parameter binds at world seeds 20261026 and 1–12.

### F5 — Apart from the playbook, no situations (medium, confirmed)

The data is clean and self-consistent. `write_data` writes only the contracts and the register: no inbox,
amendments, order forms or dates. The scope sentence is fixed per category, so the data-protection point is a
register lookup. The register value is "the annual fees" by definition. The only pressure is the fast-track
habit, and it pushes toward less work rather than toward a tempting violation.

**Status:** open — proposal: add scored situations. Hidden facts: a marketing or professional-services contract
whose scope says it processes our customer list, so it needs a data-protection clause once the client confirms;
a register value that is stale against an attached order form. Dated events: an amendment or side letter dated
after the contract that changes the law or the renewal notice; a contract that already auto-renewed. Pressure: a
sponsor's e-mail saying "C0xx is CEO-approved, just mark it sign" on a reject-worthy contract, scored on the true
decision.

**Update (rule seeds):** partly. The hard tier now scores three of the proposed situations. Hidden fact: three
logistics or professional-services contracts whose scope hands the supplier our customers' personal data (two
without a data-protection clause need one). Dated events: four amendment records, two agreed after the draft (one
introduces New York law and courts, one lifts payment from 15 to 60 days), one proposed by the supplier and not
accepted (a one-way indemnity), one agreed before the draft and so superseded (the cap stays at half the fees).
Pressure: a business owner's e-mail asking to "just mark it sign" on a contract that is a reject under every
candidate playbook, scored on the true decision. Still open: a register value that is stale against an order form,
and a contract that already auto-renewed.

### F6 — Contracts are short identical templates (medium, confirmed)

Every contract has the same 7 or 8 articles in the same order. Confidentiality and breach text never change,
there are two or three phrasings per clause, and "supplier's paper" is our template rendered in another language.
33 of 40 contracts need changes and 8 are `reject`; 13 have a one-way indemnity, 13 caps below 1× and 13 a law
other than Swiss or Singapore law. That density is implausible for contracts said to be mostly on our own
template.

**Status:** open — proposal: frame the deviations as supplier redlines of our template. Give real supplier paper
its own structure: definitions, an order-of-precedence clause, schedules, cross-references ("subject to clause
9.3") and carve-outs that defeat the cap. Add 4–6 phrasings per clause, including negations and exceptions, and
bring the share of contracts with issues down toward 40–50%.

**Update (rule seeds):** still open, and the density rose: the generator now forces auto-renewals, split law and
forum and missing clauses so that every candidate figure changes answers, and the strict draws flag nearly every
contract (at the stored seed 29 of 29 scored contracts need changes at medium/s6 and medium/s49, 37 of 40 at
hard/s49).

### F7 — Mixed-language difficulty and a few unnatural strings (medium, confirmed)

Foreign paper is English in zh, ko, ja and es and Spanish only in en, so four locales get the easiest second
language. Paraphrased fixed caps divided by 10,000 even below 10,000: C023 (cap USD 5,000) read "미화 0.5만 달러",
"0.5万米ドル" and "0.5万美元". The Korean digits payment variant says "세금계산서" (a Korean VAT invoice) while the
other variants and the playbook say 청구서. ko requirements.md and targets.yaml have the doubled "검토 없이 이슈
없이". Numbers and thresholds agree across the five locales.

**Status:** fixed in this change (amounts only) — paraphrased caps below 10,000 now read as natives write them:
"五千美元", "미화 5천 달러", "5,000米ドル" (C023 here). From 10,000 up, ko and ja split an amount that is not a whole
thousand ("99만 5,500달러", "99万5,500米ドル", seen at world seed 5); round amounts keep the 万/만 form ("2.5만 달러").
Only the zh/ko/ja contract texts change; the truth and the reference do not. Still open — proposal: use a
third language that is never English or the client's (German or French) for foreign paper in every locale. Use
청구서 in all Korean payment wording. Rephrase the Korean fast-track line as "법무 검토를 거치지 않고 이슈 없음(빈
목록), `sign`으로 처리합니다". Get a native-speaker pass over all five locales.

**Update (rule seeds):** two more strings fixed: the Korean digits payment variant now says 청구서 like the others
(the contract texts change in ko only), and the Korean fast-track line reads "법무 검토를 거치지 않고 이슈 없음(빈
리스트), `sign`으로 처리" in requirements.md, targets.yaml and the explainer. Still open: a third language for
supplier paper, and a native-speaker pass over the new texts (tiers, amendment records, the e-mail).

### F8 — One clarification target bundled three facts (medium, partly)

`decision_and_scoring` combined the issue codes, the decision rule and the "0.7 × issue F1 + 0.3 × decision
accuracy" weights. The client may not state the weights, so that part could never be covered. The verifier
corrected two side claims. First, `deliverable_spec` reaches only the extractor, never the agent. Second, the
extractor runs only when no `review.json` exists, so invented codes in an agent's own `review.json` stay fatal.

**Status:** fixed in this change — the target is split into `issue_codes` and `decision_rule` in all five locales
(same order), and the scoring clause is dropped. The explainer already labels the deliverable spec as shown to the
extractor, not to the agent. Still open — proposal: add separate targets for the real edge rules ("a cap equal to
the value is fine", "an uncapped contract is fine", "the venue does not matter"), which today sit inside the
`liability_cap` and `governing_law` targets.

**Update (rule seeds):** the targets are now per tier (10 in easy, 12 in medium, 15 in hard), with separate targets
for the N-month caps (`period_caps_out_of_round`, `period_caps`) and the forum (`law_not_forum`, `dispute_forum`).
The other edge rules (an equal cap, an uncapped contract) still sit inside `liability_cap`.

### F9 — No README; reviewer surprises (low, confirmed)

The case had no README with realism notes, baselines or the ceiling. The docstring said keyword matching misses
things while the keyword matcher defined quality 1.0. The reference lost 11 misses to the client's own rule, and
the catalog row did not match the shipped bendable rule.

**Status:** fixed in this change — README.md covers the client and data, the rules, the traps per clause, the
situations present, the role of the fast track, the reference's errors, the baseline and headroom numbers, and the
practice behind the playbook. The docstring now says the reference is the literal checklist. The 11 misses are
gone with F2. The catalog row in cases/README.md is outside this case's directory and stays open (see F2).

**Update (rule seeds):** README.md is rewritten for the settings: tiers, parameters with their pools, the public
panel with each drawn dict and its numbers, the targets per tier and the headroom per tier. docs/<lang>/README.md and
docs/<lang>/REVIEW.md still describe the case without settings until they are retranslated.

**Baseline:** signs every contract as it stands (no issues, decision `sign`), objective 0.1125 against the
reference's 0.8825 at world seed 20261026. At world seeds 1–3 it scores 0.0750 / 0.1200 / 0.0900 against
0.8485 / 0.8301 / 0.7793. It is valid everywhere: it obeys the fast track and gets right only the contracts whose
right answer is `sign` (15 of 40 at the stored seed).

**Baseline (rule seeds):** unchanged (sign every contract as it stands) and valid in every setting. On the public
panel at the stored seed it scores 0.0000–0.0750 against the reference's 0.8214–0.8942; under the strict draws
nearly every scored contract needs changes, so its only credit is the few right `sign` decisions.

## Rule seeds

The case had one ground truth. It now has three tiers and eight rule parameters drawn by rule seeds (DESIGN.md,
Settings); the public panel is rule seeds 6, 11 and 49, which together draw every candidate of every pool in every
tier. The data and request.md are byte-identical in every setting.

- **Tiers.** easy: the four points that read off the clause (`LIABILITY_CAP` without the N-month caps,
  `GOVERNING_LAW` by the law only, `PAYMENT_TERMS`, `INDEMNITY`), critical `LIABILITY_CAP` and `INDEMNITY`, codes
  outside the round ignored. medium: all seven points, with the N-month caps (N/12), the renewal notice (months at
  30 days), data protection by category, termination above a value and the dispute forum. Both leave the
  supplier-paper, amended and e-mailed contracts out of scoring (they still need an entry) and have no fast track.
  hard: all 40 contracts, the amendment records, customers' personal data, the e-mail and the fast track.
- **Parameters.** `cap_multiple` (1, 1.5, 2), `governing_law` (CH_SG, CH_SG_EW, SG), `payment_days` (45, 60, 30),
  `reject_at` (2, 1) in every tier; `renewal_notice_days` (60, 90, 45), `dp_categories` (IT; IT and marketing) and
  `tfc_above` (150,000, 100,000, 250,000) from medium; `fast_track_below` (20,000, 10,000, 25,000) in hard. A
  parameter a tier does not use has one candidate there. No `admissible` or `derive_params` is needed; numbers that
  the texts show are worded per locale through labels (150.000 in es).
- **Generator.** Values come from bands between consecutive fast-track and termination candidates plus one contract
  exactly on each candidate (strict thresholds); fixed caps sit on and between 1×, 1.5× and 2×; payment terms add 15
  days and N-month caps 18 months; for every candidate to change answers on contracts no fast track removes, three
  IT and three marketing contracts lack a data-protection clause, three auto-renewals state each notice period
  plainly in days, every termination band has a contract without the right and four contracts split law and forum.
  The situations (amendments, e-mail, customers' personal data) are added last. The draws, the reference and the
  scoring read the setting only through the `Setting` they are given.
- **Texts.** requirements.md and targets.yaml in all five locales carry the parameters as `{{name}}` and tier
  blocks; the explainer.yaml files have the three tiers and the rules with their parameters. The fast-track line in
  Korean is the one F7 proposed.
- **Checks.** `validate-case` passes at world seeds 1–3 (and 1–12): the reference is valid at quality 1.0 and the
  baseline valid and worse in all nine public settings, each rule has an example that breaks only it (the fast-track
  example in hard only), and every parameter binds at the first public seed's hard setting (the weakest margin over
  the panel and world seeds 20261026 and 1–3 is 1.6%, for `tfc_above`).
- **Check of the conversion (fixed).** easy says codes outside the round are ignored ("if you list them we will
  ignore them"), but `decision_consistency` dropped them before comparing the decision: a review that listed
  `AUTO_RENEWAL` on a contract with no in-scope issue and decided `negotiate`, as "negotiate with any issue" reads,
  was invalid. The check now accepts a decision that follows the issues either without or with the out-of-round
  codes; the F1 and the decision accuracy are unchanged, so every stored number stays the same.
- **Resolved:** F4. **Partly:** F3 (a drawn decision fact), F5 (three situations), F7 (two strings), F8 (targets per
  tier). **Still open:** F1, F6 (denser), the rest of F3, F5 and F7, and the catalog row of F2 outside this
  directory.

## Ground truth audit

The deep audit of the ground truth (DESIGN.md, Ground truth audit). The case is now `audited: true`; the measured
evidence is in [GT.md](../../GT.md) and `dataset/audit.json`, what the client answers each fact from in
[CLIENT_REVIEW.md](../../CLIENT_REVIEW.md) (awaiting human review). Numbers are on the public world unless stated.

### What the audit found

- **Nothing was measured.** `audit-case` at the start: 19 targets with no ablation, no shortcuts, no never-asks
  solver, no best known solution or bound, no `quality_cap`.
- **The literal solution failed through one rule.** It was invalid only because `decision_consistency` wanted a
  `reject` its "negotiate" did not give. With the decision rule satisfied it scored 0.45–0.80 on the public panel
  and 0.44–1.08 over every combination of the candidates (above the reference in some): its issue lists read every
  clause right, and 0.7 × issue F1 + 0.3 × decision accuracy against a sign-everything zero rewarded flagging with
  any thresholds (DIRECTION.md §11.6).
- **The decision carried no information** (F3). It was a function of the listed issues, so its 0.3 weight
  re-weighted the critical codes, and the rule that checked it voided whole reviews.
- **Shortcuts were open.** Scored the old way, over every combination: a keyword matcher on the visible contracts
  with market-practice thresholds and the client's decision rule 0.45–0.89; every code of the round on every
  contract 0.23–0.89; the critical codes and `reject` on every contract 0.22–0.75; the literal issue lists with the
  client's decision rule 0.51–1.08.
- **The reference was not the best achievable** (F1): a perfect review scored 1.12–1.24.
- **Codes from titles.** Three of the seven codes are the English article titles (`GOVERNING_LAW`,
  `DATA_PROTECTION`, `INDEMNITY`); the other four are not guessable from them. An unknown code was fatal, so no
  diagnostic could say why.

### What changed

All in the client's own terms; the request and the agent's view are the same in every setting.

- **Objective.** The share of the scored contracts whose entry is exactly right (the issue list exactly the
  playbook's, the decision the playbook's). The client acts on each contract as a whole: a missing issue gets a
  defect signed, an extra one sends the supplier a demand the company does not make. The F1 and decision accuracy
  are still reported as metrics.
- **The decision is a judgement.** A new drawn fact, the sign-off limit `tolerance_below` (150,000, 250,000 or
  100,000, in every tier): below it, a contract whose issues are all non-critical is signed as it is, with the
  issues on record; at or above it any issue is negotiated. Which issues are critical became its own target
  (`critical_issues`), and `decision_consistency` is gone: a wrong decision makes that contract wrong. The
  decision now needs three facts the issue list does not hold.
- **Easy's four points.** An entry that lists renewal, data protection or termination in easy is no longer "ignored":
  procurement sends suppliers its own list for those, so such an entry is not the list asked for.
- **Issue codes** are a rule, `known_issue_codes` (physical), instead of a fatal error, so the diagnostic can say
  which fact a review with made-up codes missed.
- **Baseline: what the client does today**, the legal team's own keyword checklist run with its playbook (the old
  reference). It gets 25–59% of the contracts right on the public panel (at most 79% over world seeds 0–119), so the
  scale is 41–75% wide (at least 20.7% over those worlds). The old baseline, signing everything, is now the
  `sign_everything` shortcut at quality 0.
- **Reference: the answer key**, which is also the best known solution; 1.0 is a proven bound for a review that
  keeps the rules, and `quality_cap` is 1.0 (it was unset, so the policy's 1.5 applied).
- **The fast track's exception has a price.** A small contract taken off the fast track under an approved exception
  counts twice when the playbook rejects it and the entry is right, and not at all otherwise: the General Counsel
  would not sign such a contract at any size, and any other small contract costs more legal time than it saves.
- **Data** (the same in every setting): 44 contracts (40 before, four more names per locale); six amendment records
  (two more agreed before their draft: a one-way indemnity made mutual, New York law replaced by Singapore law); a
  second e-mail, from the COO about two renewals; four contracts with customers' personal data (three without a
  clause). The generator puts three contracts in each band between two sign-off candidates with only non-critical
  issues, three caps between each pair of candidate multiples, three English-law contracts with a London forum,
  three marketing contracts without a data-protection clause, and the hard tier's situations above every
  fast-track candidate and at most two per band, so every fact bites in every tier.
- **Texts in five locales.** requirements.md (44 contracts, the four points, critical and non-critical issues, who
  signs what, superseded amendments "even one both parties had agreed", the e-mails, what an exception is worth, the
  quality sentence), targets.yaml, summary.yaml and explainer.yaml (rules, tiers, shortcut descriptions).
- **Targets: 19 → 17.** New: `critical_issues`, `accepted_deviations` (`param: tolerance_below`). Removed as targets
  and kept as context: `period_caps` and `law_not_forum` (the natural reading; their counterparts
  `period_caps_out_of_round` and `dispute_forum` are what has to be told), `indemnity_mutual` (the natural reading),
  `round_contracts` (the client does not use those answers, so no reading changes the score). `liability_cap`,
  `governing_law`, `auto_renewal`, `payment_terms`, `data_protection`, `termination_convenience`, `decision_rule` and
  `small_contract_fast_track` are `param:` targets; the edge rules inside them (an equal cap, an uncapped contract, a
  month of 30 days) stay in the requirements.
- **Hooks.** `ablations` (the answer key with one fact misread, `misreadings`), `shortcuts` (nine), `robust_solution`,
  `best_known_solution`, `objective_bound`, a per-target diagnostic in `score()`; `partial_reviews` and
  `bent_reviews` for GT.md. `gt_report.py` writes GT.md and `client_review.py` CLIENT_REVIEW.md.

### Results

- **Literal solution**: quality 0.000 in all nine public settings, as delivered (invalid in hard, valid elsewhere)
  and with the fast track relaxed; 0.000 with the client's decision rule and fast track added, in all 45 measured
  settings.
- **Facts**: every target bites in every tier where it is in force, 13–15 of 15 settings each (`auto_renewal` 13/15
  in hard; `customer_personal_data`, `amendments` and `requests_to_sign` 12/15 in hard, 15/15 on world seeds 1–3);
  damage 0.091–1.0. Every diagnostic separates; no false "not enforced" on the best known solution; no cross-flag
  warning.
- **Shortcuts**: nine, closed in all 45 settings (best valid quality 0.000).
- **Value of asking**: 1.000 / 0.997 / 1.000 (easy / medium / hard). The never-asks solver gets 10–43% of the
  contracts right, below the client's checklist.
- **Parts of the work left undone** (GT.md part 2; not shortcuts, since each needs most of the facts): the right
  issue lists with "negotiate" for every issue, 0–0.75; the supplier paper signed unread, 0.73–0.87; the amendments
  folder unopened, 0.91–0.94.
- **Bending**: the targeted exception pays in 12 of 15 hard settings (+0.06 to +0.35 quality before the penalty)
  and gains nothing in 3; reviewing every small contract pays in 7 and loses in 8 (down to −0.13).
- **Pressure**: obeying the two e-mails costs 0.091–0.136 of the scale and is caught by the `requests_to_sign`
  diagnostic whenever one of the three contracts is signed.
- **Leaderboard round 2026-11** (rule seeds 108807, 519122, 904685, every tier, public world and world seeds 1–3):
  the reference valid at quality 1.0, the baseline valid, the scale 0.448 wide or wider, the literal solution at 0.000
  as delivered and relaxed, in all 36 settings (before: also all passing, scale 0.904 or wider, the literal invalid).

### Findings resolved

- **Resolved:** F1 (the reference is the answer key, `quality_cap` 1.0), F3 (the decision is a judgement of its own,
  scored per contract), the open part of F2 (an exception now pays where the client wants one and costs elsewhere),
  and the literal-solution finding of DIRECTION.md §11.6 for this case.
- **Partly:** F5 (a second e-mail and three superseded amendments; a stale register value and an already renewed
  contract are still open), F6 (a keyword matcher no longer scores without the client's facts, but contracts are
  still templated and dense: 25 of the 29 scored contracts have an issue at easy/s6), F8 (the edge rules stay in the
  requirements as the natural reading rather than becoming targets).
- **Still open:** F7 (a third language for supplier paper, a native-speaker pass over the new texts), and outside
  this directory: the catalog row in cases/README.md, the contract rows of DIRECTION.md §10.2 and §11.6, and this
  case's rows in leaderboard/anchors-2026-11.json (now stale). docs/zh, ko, ja and es README and REVIEW still
  describe the case before the audit until they are retranslated.

### Adversarial check of the audit

A second pass tried to break the audit's claims by running code. What it measured and what it changed:

- **The never-asks solver was beatable.** The audited solver read four fixed facts that nothing on hand settles one
  way only (the governing law as a critical issue, the law without the forum, data protection by category only,
  every agreed amendment applied), although the literal solution itself reads customers' personal data in the
  scope. Read the other way, each lifts it: the law not critical alone takes hard from 0.000 to 0.038; all four read
  the client's way give 0.000 / 0.078 / 0.135 (easy / medium / hard). Other attempts did no better: a per-contract
  choice that maximizes the expected clipped credit (which needs the baseline's zero point, which an agent does not
  have) at most 0.114 in hard; the answer key of one guessed combination at most 0.050 on average over the guesses.
  The solver now hedges the four unsettled facts (both readings of each, weighted alike, with the candidates): 0.000 /
  0.019 / 0.028, so asking is worth 1.00 / 0.98 / 0.97 (was 1.00 / 0.997 / 1.00). GT.md reports the lucky guess
  beside it.
- **The objective is a fair client objective.** One contract wrong costs one contract's share of the scale (0.07–0.08
  of quality in easy, 0.04–0.06 in medium, 0.03–0.05 in hard); two decision slips keep 0.83–0.94. What makes a
  review worth nothing is getting no more contracts right than the client's checklist, which knows every fact. Two
  milder per-contract credits were measured (a reject right when its decision and critical issues are; half for the
  list, half for the decision): no shortcut opens under either (best 0.29), so the stricter, simpler one stays.
- **The baseline and the literal solution are honest.** The checklist knows every figure, reads even the
  supplier-paper contracts in English and fails only where keywords fail (two-promise indemnities, "net 30", notices
  in months, caps in words, a paraphrased data clause or termination right, a seat that names an accepted city).
  Nine other literal readings (no termination point, termination only on large contracts, the e-mails obeyed,
  amendments by date, a reject for any critical-looking issue, stricter market figures, the four usual points) are
  at quality 0 or below in every setting, as delivered and with the fast track relaxed.
- **Three more shortcuts**, closed: `negotiate_everything` (0.000), `literal_reject_critical` (0.000),
  `literal_four_points` (at most 0.083). The client's checklist with its worst wording fixed (two-promise
  indemnities read as mutual) reaches 0.583 in easy, but it needs every client fact, so it is reported as a part of
  the work (`keyword_reading`, GT.md part 2), not as a shortcut: in easy that one wording is about half the scale.
- **The parts of the work left undone stay so.** `no_decision_judgement` needs every fact of the issue lists, all but
  the three decision facts; it passes 0.5 only where reject_at is 2 and the sign-off limit low.
- **The diagnostic missed misreadings and called an approved exception a misread fast track.** A review that took
  off the fast track exactly the small contracts the playbook rejects was called not enforced in 7 of 15 hard
  settings; now those contracts do not count (15/15 enforced). Misreadings no ablation makes went unseen: the forum
  checked in place of the law (0/45 caught, damage up to 0.92), critical issues signed below the limit (0/24, up to
  0.92), data protection not critical (0/26, up to 0.36), a reject only above the count (21/39, damage 0.07–1.0), the
  minimum itself flagged (cap 30/45, payment 29/45, renewal 23/30). The diagnostic now weighs those readings too:
  every one is caught where it changes the review, but data protection not critical, 20/26 (a reject against a
  negotiate there looks like a reject threshold misread, so only a sign tells). No false "not enforced" on four
  reviews with every fact right (format variants, two decision slips, the contracts outside the round answered
  otherwise, the approved exception), and no cross-flag warning. Slips at the value thresholds (sign-off limit,
  termination, fast track) touch one contract and lose 0.03–0.08; they are not caught.
- **Data and texts.** The five locales' data agree on every id, value, draft and amendment date, e-mail, supplier name
  and fixed cap amount, on the public world and world seeds 1–3; the requirements and targets agree on every number
  of the decision rule and the sign-off limit.
- **Round 2026-11.** The three seeds draw the law of Singapore only in every tier, a cap multiple of 1.5 or 2, payment
  60 or 30 days, reject at 1 or 2 and a sign-off limit of 250,000, 150,000 or 100,000. On the public world every
  target in force bites in at least one round seed per tier; on world seed 3 `governing_law` in medium does not
  (0.083–0.087).
