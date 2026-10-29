# Review — `legal_compliance/contract_review_counsel`

Findings of the case review (F1–F9) and what this change did about each. Numbers are at world seed 20261026
unless stated. The review was written before the F2 fix (reference 0.7677) and against a 1.0 quality cap; the
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

### F3 — The decision adds no information; two all-or-nothing gates (high, confirmed)

`decide()` is a pure function of the listed issues. `decision_consistency` invalidates the whole review on any
mismatch, and decision accuracy compares `decide(pred)` with `decide(truth)`, so the 0.3 weight only re-weights
issue correctness on the critical codes. An agent that never learns of the fast track is invalid under the
`baseline` and `regulated_strict` policies (exceptions forbidden), and so is one that guesses another reject rule.

**Status:** open — proposal: give the decision a fact of its own that the client holds. Examples: approval levels
by value, supplier criticality, or which issues are walk-away points and which are negotiable. Score it
separately. Consider grading `decision_consistency` per contract instead of zeroing the review. If asking about
the fast track is meant as the key test, say so in the README.

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

### F9 — No README; reviewer surprises (low, confirmed)

The case had no README with realism notes, baselines or the ceiling. The docstring said keyword matching misses
things while the keyword matcher defined quality 1.0. The reference lost 11 misses to the client's own rule, and
the catalog row did not match the shipped bendable rule.

**Status:** fixed in this change — README.md covers the client and data, the rules, the traps per clause, the
situations present, the role of the fast track, the reference's errors, the baseline and headroom numbers, and the
practice behind the playbook. The docstring now says the reference is the literal checklist. The 11 misses are
gone with F2. The catalog row in cases/README.md is outside this case's directory and stays open (see F2).

**Baseline:** signs every contract as it stands (no issues, decision `sign`), objective 0.1125 against the
reference's 0.8825 at world seed 20261026. At world seeds 1–3 it scores 0.0750 / 0.1200 / 0.0900 against
0.8485 / 0.8301 / 0.7793. It is valid everywhere: it obeys the fast track and gets right only the contracts whose
right answer is `sign` (15 of 40 at the stored seed).
