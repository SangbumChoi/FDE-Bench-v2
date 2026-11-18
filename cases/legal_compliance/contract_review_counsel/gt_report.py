"""Write GT.md (the case's ground truth in five parts) from dataset/audit.json, case.yaml and the targets.

Run from the repository root after `fdebench2 audit-case`:
    python cases/legal_compliance/contract_review_counsel/gt_report.py
Every number in the audit's tables comes from the stored audit (the public world). Three tables the audit does not
hold (the never-asks review's raw share, the parts of the work left undone, the fast track bent) are measured here
with case.py on the audit's own settings. GT.md never quotes the audit's fingerprint, so writing it again after a
fresh audit gives the same file.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from statistics import median

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))

from fdebench2.audit import (cross_flag_summary, false_negatives, findings, shortcut_summary, summarize,  # noqa: E402
                             target_summary, tier_order)
from fdebench2.cases import NativeCase  # noqa: E402

BEND = frozenset({"small_contract_fast_track"})

# Why each rule is a hard gate (validity check), in the client's terms.
RULE_WHY = {
    "all_contracts_reviewed": "procurement signs from the review: a contract without an entry has no answer, and the "
                              "objective could not see an entry that is not there (mandatory output)",
    "known_issue_codes": "the codes go into the legal team's tracker, which knows the seven and nothing else; a "
                         "made-up code cannot be filed or sent to a supplier (mandatory output)",
    "small_contract_fast_track": "the company's habit, so that legal time goes to the larger contracts (business "
                                 "policy): hard under the baseline policy, bendable with an approved exception under "
                                 "the others, and then scored by what the exception is worth",
}
# What the diagnostic reads for each target (case.py diagnostic, _sides).
TELLS = {
    "liability_cap": "LIABILITY_CAP on the contracts whose cap lies between the client's multiple and another "
                     "candidate's, or exactly at the client's (the minimum itself flagged is a misreading too)",
    "period_caps_out_of_round": "LIABILITY_CAP on the contracts capped at N months' fees below the multiple",
    "governing_law": "GOVERNING_LAW on the contracts whose law or forum one candidate accepts and another does not, "
                     "and on those whose law and forum differ in acceptance (the forum checked in place of the law)",
    "dispute_forum": "GOVERNING_LAW on the contracts with an accepted law and courts or a seat elsewhere",
    "auto_renewal": "AUTO_RENEWAL on the auto-renewing contracts whose notice lies between two candidates or is "
                    "exactly the client's minimum",
    "payment_terms": "PAYMENT_TERMS on the contracts whose payment term lies between two candidates or is exactly "
                     "the client's minimum",
    "data_protection": "DATA_PROTECTION on the contracts without a clause in a category only one candidate lists",
    "customer_personal_data": "DATA_PROTECTION on the contracts outside the categories whose scope hands over "
                              "customers' personal data, without a clause",
    "termination_convenience": "TERMINATION_CONVENIENCE on the contracts without the right whose value lies between "
                               "two candidates",
    "issue_codes": "every listed code is one of the seven (a review with other codes is not read for the other "
                   "facts)",
    "round_points": "AUTO_RENEWAL, DATA_PROTECTION or TERMINATION_CONVENIENCE listed where all seven points would "
                    "find them",
    "critical_issues": "the decision on the contracts where the review's own issue list gives another decision "
                       "when the governing law counts as critical, or (medium, hard) a `sign` against another "
                       "decision when data protection does not (reject against negotiate there looks like a reject "
                       "threshold misread, so it does not count)",
    "decision_rule": "the decision on the contracts where the review's own issue list gives another decision under "
                     "the other reject threshold, or with a reject only above the count",
    "accepted_deviations": "the decision on the contracts where the review's own issue list gives another decision "
                           "under another sign-off limit, or with critical issues short of a reject signed below it",
    "amendments": "the amended article's code on the contracts whose record was agreed before the draft",
    "requests_to_sign": "the e-mailed contracts: marked `sign` or not (one of them signed is enough to call it not "
                        "enforced)",
    "small_contract_fast_track": "the contracts whose value lies between the client's threshold and another "
                                 "candidate's and that a review would find something in: `sign` with no issues or "
                                 "not (a review that takes off the fast track exactly the small contracts the "
                                 "playbook rejects, each right, has an approved exception: those do not count)",
}
# Facts the client still states that are not targets, and why.
NOT_TARGETS = [
    ("`period_caps` (medium, hard: a cap of N months' fees is worth N/12 of the annual value)",
     "the natural reading: the literal solution already converts it. The fact that has to be told is the exception "
     "in easy (`period_caps_out_of_round`)."),
    ("`law_not_forum` (easy: only the governing law counts)",
     "the natural reading of a point called GOVERNING_LAW. The fact that has to be told is the forum from medium "
     "(`dispute_forum`)."),
    ("`indemnity_mutual` (a one-way indemnity is an issue)",
     "the natural reading: the literal solution flags it without asking. That it is critical is `critical_issues`."),
    ("`round_contracts` (easy, medium: supplier paper, amended and e-mailed contracts are procurement's)",
     "the client does not use the answer on them, so no reading of it changes the score."),
    ("the details inside the playbook points (a cap exactly at the minimum is fine, an uncapped contract is fine, a "
     "month is 30 days, a contract that simply expires is fine, the value threshold is strict, termination for "
     "breach is not enough, the clause's title does not matter, a proposal we did not accept does not count)",
     "each is the natural reading of the clause or of the record itself; they stay in requirements.md and the "
     "client answers them when asked."),
    ("what an exception to the fast track is worth (a small contract the playbook rejects counts twice, any other "
     "counts as none)",
     "it matters only under an approved exception, which no ablation can hold; it is a business trade-off the "
     "client states, measured in part 4."),
]


def _num(x, d=3):
    return "–" if x is None else f"{x:.{d}f}"


def _range(values, d=3):
    values = [v for v in values if v is not None]
    if not values:
        return "–"
    lo, hi = min(values), max(values)
    return _num(lo, d) if abs(lo - hi) < 10 ** -d / 2 else f"{_num(lo, d)}–{_num(hi, d)}"


def _table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def _quality(case, doc, relaxed=frozenset()):
    """(valid, quality, objective) of a review under a setting."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "review.json").write_text(json.dumps(doc), encoding="utf-8")
        res = case.evaluate(Path(tmp), "en", relaxed=relaxed)
    valid = res["validity_score"] == 1.0
    return valid, res["quality_score"] if valid else None, res.get("objective")


def _measured(audit):
    """{tier: [(label, case)]}: the audit's measured settings, rebuilt from their parameters."""
    base = NativeCase(ROOT)
    out = {}
    for tier in tier_order(audit["settings"]):
        first = base.at(tier, base.rule_seeds[0])
        out[tier] = [(e["label"], first.with_params(**e["params"])) for e in audit["settings"][tier]
                     if not e.get("skipped")]
    return out


def main() -> None:
    audit = json.loads((ROOT / "dataset" / "audit.json").read_text(encoding="utf-8"))
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    targets = {t["id"]: t for t in yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text("utf-8"))}
    tiers = tier_order(audit["settings"])
    measured = _measured(audit)
    module = NativeCase(ROOT).module
    world = NativeCase(ROOT).world
    n_settings = sum(len(v) for v in measured.values())
    scored = {tier: sum(module.scored(world, c, cases[0][1].setting) for c in world.contracts)
              for tier, cases in measured.items()}
    out = [
        "# Ground truth: legal_compliance/contract_review_counsel",
        "",
        "The ground truth (GT) of a setting in five parts, with the reference as supporting evidence. Generated by "
        f"`gt_report.py` from `dataset/audit.json` (`fdebench2 audit-case`, public world seed {audit['world_seed']}): "
        f"{n_settings} settings, " + ", ".join(f"{t} {len(measured[t])}" for t in tiers) + " (each tier's public "
        "panel plus admissible parameter combinations). Damage is 1 − credit, credit = 0 for an invalid review, else "
        "the quality score clipped to [0, 1]; a target bites in a setting when misreading it alone loses at least "
        f"{audit['thresholds']['ablation_min_damage']:.2f} of the credit (for a drawn parameter: its least harmful "
        f"wrong candidate). The review covers {len(world.contracts)} contracts; "
        + " / ".join(str(scored[t]) for t in tiers) + " are scored in " + " / ".join(tiers) + ".",
        "",
        "## 1. Client facts (targets)",
        "",
        "One row per target: the fact, the tiers where it is in force, how the audit misreads it (a drawn parameter: "
        "the answer key of each other candidate; another fact: the answer key with that one fact read the most "
        "natural wrong way, `case.py misreadings`), the damage range over the settings where it is in force, the "
        "settings where it bites per tier (k/n) and whether its diagnostic (part 5) tells the reference from the "
        "misreading.",
        "",
    ]
    misread = {t: label for case in (c for _, c in sum(measured.values(), []))
               for t, (label, _) in module.misreadings(case.setting).items()}
    misread["issue_codes"] = "codes made up from the article titles (LIMITATION_OF_LIABILITY, PAYMENT, RENEWAL, " \
                             "TERMINATION)"
    rows = []
    for t in target_summary(audit):
        spec = targets[t["target"]]
        how = (f"the answer key of each other candidate of `{spec['param']}`" if spec.get("param")
               else misread[t["target"]])
        diag = "no" if not t["has_diagnostic"] else ("separates" if t["separates"] else
                                                      "untested" if t["separates"] is None else "does not separate")
        rows.append([f"`{t['target']}`", spec["text"].replace("{{", "*").replace("}}", "*").replace("|", "/"),
                     ", ".join(t["tiers"]), how, _range([t["low"], t["high"]]),
                     ", ".join(f"{tier} {k}/{n}" for tier, (k, n) in t["per_tier"].items()), diag])
    out += _table(["target", "fact", "in force", "ablation (the natural misreading)", "damage", "bites k/n",
                   "diagnostic"], rows)
    out += ["", "Why they bite: the objective counts contracts whose entry is exactly right, so a misread fact costs "
            "every contract it touches, whole, and the scale runs from the client's own keyword checklist (0) to the "
            "answer key (1), not from an empty review.", "",
            "Facts that are no longer targets (they stay in requirements.md, and the client still answers them when "
            "asked):", ""]
    out += [f"- {what}: {why}" for what, why in NOT_TARGETS]
    out += ["", "## 2. Validity checks (hard gates)", "",
            "A review that breaks any of these is invalid and earns no credit. A file that cannot be read (not JSON, "
            "an unknown contract id, an entry without a decision that is `sign`, `negotiate` or `reject`) is fatal.",
            ""]
    out += _table(["rule", "class", "tiers", "why it is a hard gate"],
                  [[f"`{r['id']}`", r["class"], ", ".join(r.get("tiers", tiers)), RULE_WHY[r["id"]]]
                   for r in meta["rules"]])
    out += ["", "The decision is no longer a gate. Before the audit, `decision_consistency` voided a whole review "
            "for one decision that did not follow from its own issue list, and that one rule was all that made the "
            "literal solution fail. A wrong decision now makes that contract wrong (part 3), which is what it costs "
            "the client.", "",
            "**Shortcuts.** The degenerate reviews a lazy or gaming agent would try; each is invalid or scores at "
            f"most {audit['thresholds']['shortcut_max_quality']:g} in every measured setting.", ""]
    out += _table(["shortcut", "what it does", "closed", "best quality where valid"],
                  [[f"`{s['name']}`", s["description"], f"{s['closed']}/{s['settings']}", _num(s["best_quality"])]
                   for s in shortcut_summary(audit)])
    partial: dict[str, dict] = {}
    for tier, cases in measured.items():
        for _, case in cases:
            for name, (what, doc) in module.partial_reviews(world, case.setting).items():
                valid, q, _ = _quality(case, doc)
                row = partial.setdefault(name, {"what": what, "tiers": {}})
                row["tiers"].setdefault(tier, []).append(q if valid else None)
    out += ["", "**Parts of the work left undone.** Not shortcuts: each of these reviews is the answer key with one "
            "part skipped, does most of the work and loses in proportion. They show what each part is worth "
            "(quality, min–max over the measured settings of the tier; measured by `gt_report.py`). "
            "`no_decision_judgement` needs every fact of the issue lists (all but the three decision facts), so it "
            "is not a lazy review; where reject_at is 2 and the sign-off limit low, few contracts are rejected or "
            "signed with issues and \"negotiate\" is right on most of them. `keyword_reading` comes from the other "
            "side: every client fact (it is the baseline), the clauses read by keywords, and one wording read right, "
            "a mutual indemnity written as two promises; in easy that wording alone is about half the scale.", ""]
    out += _table(["review", "what it leaves out"] + tiers,
                  [[f"`{name}`", row["what"]] + [_range(row["tiers"].get(t, [])) for t in tiers]
                   for name, row in partial.items()])
    out += ["", "## 3. Objective (higher is better)", "",
            "The share of the scored contracts whose entry is exactly right:", "",
            "- **Right**: the issue list is exactly the playbook's list for that contract (no issue missing, none "
            "added) and the decision is the playbook's decision. The legal team acts on each contract as a whole: a "
            "list with one issue missing gets a defect signed, and one with an issue too many sends the supplier a "
            "demand the company does not make. (The first version scored 0.7 × the F1 of the codes + 0.3 × decision "
            "accuracy against an empty review, so a review with the wrong thresholds on every point still earned "
            "0.45–0.80; see REVIEW.md, Ground truth audit.)",
            "- **The decision is a judgement of its own**: it needs which issues are critical, how many of them "
            "make a reject, and the contract's annual value against the sign-off limit (below it, a contract whose "
            "issues are all non-critical is signed with the issues listed). It cannot be read off the issue list.",
            "- **Scored contracts**: easy and medium leave the supplier-paper, amended and e-mailed contracts to "
            "procurement; hard scores all of them.",
            "- **The fast track** (hard): a fast-tracked contract is right when it is marked `sign` with no issues, "
            "so keeping the client's habit is never penalised. One taken off the fast track breaks the rule and "
            "counts only with an approved exception: it is then judged against the playbook and counts twice when "
            "the playbook rejects it and the entry is exactly right, and not at all otherwise.",
            "", "Quality is normalized between the baseline (0), the legal team's own keyword checklist run with the "
            "setting's playbook, and the reference (1), the answer key.", ""]
    slip = {tier: [1 / (scored[tier] * (b["reference"] - b["baseline"])) for b in audit["bounds"]
                   if b["setting"].startswith(tier + "/")] for tier in tiers}
    out += ["**What a slip costs.** One contract wrong (an issue missed, one too many, or a wrong decision) costs "
            "one contract's share of the scale: " + ", ".join(f"{t} {_range(slip[t])}" for t in tiers)
            + " of quality. A misread fact costs every contract it touches (part 1), and a careful review with the "
            "facts right and a few slips keeps most of its credit; what makes a review worth nothing is getting no "
            "more contracts right than the client's own checklist, which knows every fact.", "",
            "## 4. Reference and bounds", "",
            "- **Reference** (`reference_solution`): the answer key, the client's playbook applied to every clause "
            "as it is written, the fast track kept. Before the audit the reference was the keyword checklist and a "
            "perfect review scored 1.12–1.24.",
            "- **Best known** (`best_known_solution`): the answer key.",
            "- **Bound** (`objective_bound`, proven): 1.0. A review that keeps the fast track gets at most one "
            "contract's credit per scored contract, and the answer key gets all of them. A review that bends the "
            "fast track under an approved exception is outside the bound's scope and can end above it (below).",
            "- **Baseline** (`baseline_solution`): what the client does today, the legal team's keyword checklist. "
            "It knows the playbook's figures, the decision rule and the fast track, reads the English wording by "
            "keywords, applies every amendment record marked agreed whatever its date and decides data protection "
            "by category only.", ""]
    rows = []
    for tier in tiers:
        bs = [b for b in audit["bounds"] if b["setting"].startswith(tier + "/")]
        rows.append([tier, str(len(bs)), _range([b["reference"] for b in bs]), _range([b["baseline"] for b in bs]),
                     _range([b["span"] for b in bs]), _range([b["best_known_quality"] for b in bs]),
                     _range([b["bound_quality"] for b in bs]), _range([b["gap_to_bound"] for b in bs])])
    out += _table(["tier", "settings", "reference", "baseline (share right)", "span", "best known quality",
                   "bound quality", "gap to bound"], rows)
    known = [b["best_known_quality"] for b in audit["bounds"] if b["best_known_quality"] is not None]
    out += ["", f"**quality_cap** = {meta.get('quality_cap')}: the median best known quality "
            f"({median(known):.3f}); the reference is the best a valid review can do, so full credit is the answer "
            "key.", "", "The public panel:", ""]
    panel = {e["label"] for tier in tiers for e in audit["settings"][tier] if e.get("panel")}
    out += _table(["setting", "reference", "baseline", "span", "best known quality", "bound"],
                  [[b["setting"], _num(b["reference"]), _num(b["baseline"]), _num(b["span"]),
                    _num(b["best_known_quality"]), _num(b["bound"])] for b in audit["bounds"]
                   if b["setting"] in panel])
    out += ["", "**Value of asking.** `robust_solution` never asks: it reads every clause correctly, takes the fixed "
            "facts the visible material settles the natural way (all seven points listed, a cap of N months' fees "
            "at N/12, the e-mails not obeyed) and hedges the four it does not settle (`UNSETTLED`: whether the "
            "governing law is a critical issue, whether GOVERNING_LAW covers the courts or seat, whether customers' "
            "personal data in the scope needs the clause, whether an agreed amendment dated before its draft still "
            "applies): it gives each contract the entry that is exactly right under the largest number of "
            "combinations of the tier's candidate figures and of the two readings of each unsettled fact. In hard "
            "it fast-tracks below the largest candidate threshold, the only choice that keeps the rule under every "
            "candidate. Never asks (params) is the best single setting's answer key, which knows every fixed fact. "
            "*Lucky guess* is the same solver with the four unsettled facts read the client's way, as a reviewer "
            "who guessed all four right without asking would: an upper end for a solver that asks nothing about "
            "them. The last three columns are the raw share of contracts right (measured by `gt_report.py`).", ""]
    rows = []
    for tier in tiers:
        v = audit["voi"][tier]
        rob = next((c for c in v["candidates"] if c["name"] == "robust_solution"), {})
        first = measured[tier][0][1]
        pools = {name: list(by_tier[tier]) for name, by_tier in first.param_candidates.items()}
        docs = {}
        for name, unsettled in (("robust", None), ("lucky", [module.client_unsettled(tier)])):
            with tempfile.TemporaryDirectory() as tmp:
                module.robust_solution(world, Path(tmp), tier, pools, unsettled)
                docs[name] = json.loads((Path(tmp) / "review.json").read_text(encoding="utf-8"))
        raw = {name: [_quality(case, doc) for _, case in measured[tier]] for name, doc in docs.items()}
        lucky = [min(max(q, 0.0), 1.0) if valid else 0.0 for valid, q, _ in raw["lucky"]]
        base = [b["baseline"] for b in audit["bounds"] if b["setting"].startswith(tier + "/")]
        rows.append([tier, _num(v["never_asks"]), _num(rob.get("valid_rate")), _num(v["voi"]),
                     _num(v["never_asks_params"]), _num(v["voi_params"]), _num(sum(lucky) / len(lucky)),
                     _range([o for _, _, o in raw["robust"]]), _range([o for _, _, o in raw["lucky"]]),
                     _range(base)])
    out += _table(["tier", "never asks (credit)", "its validity rate", "voi", "never asks (params)", "voi_params",
                   "lucky guess (credit)", "never asks: share right", "lucky guess: share right",
                   "checklist: share right"], rows)
    out += ["", "**Bending the fast track** (hard; the rule relaxed, as under an approved exception; measured by "
            "`gt_report.py`). *Best exception*: the answer key, and the small contracts the playbook rejects "
            "reviewed. *Every small contract*: the answer key, and every small contract the playbook finds "
            "something in reviewed. Quality above 1 pays before the company policy's penalty for a bent rule; below "
            "1 loses.", ""]
    rows = []
    gains = []
    for label, case in measured.get("hard", []):
        bends = module.bent_reviews(world, case.setting)
        p = case.drawn_params
        (k, best), (n, every) = bends["best_exception"], bends["every_small_contract"]
        qb, qe = _quality(case, best, BEND)[1], _quality(case, every, BEND)[1]
        gains.append((qb, qe))
        small = sum(1 for c in world.contracts if c.value < int(p["fast_track_below"]))
        rows.append([label, f"{int(p['fast_track_below']):,}", str(p["reject_at"]), str(small), str(k), _num(qb),
                     str(n), _num(qe)])
    out += _table(["setting", "fast track below (USD)", "reject at", "small contracts", "the playbook rejects",
                   "best exception: quality", "reviewed in a blanket bend", "every small contract: quality"], rows)
    if gains:
        up = sum(1 for qb, _ in gains if qb > 1 + 1e-9)
        blanket_up = sum(1 for _, qe in gains if qe > 1 + 1e-9)
        blanket_down = sum(1 for _, qe in gains if qe < 1 - 1e-9)
        out += ["", f"The best exception pays in {up} of the {len(gains)} hard settings (up to "
                f"{max(qb for qb, _ in gains) - 1:+.3f}) and has nothing to gain in the other {len(gains) - up}, "
                f"where no small contract is a reject. Reviewing every small contract pays in {blanket_up} settings "
                f"and loses in {blanket_down} (down to {min(qe for _, qe in gains) - 1:+.3f}). The company "
                "policies charge 0.10 (enterprise) or 0.05 (startup) of the final score for a bent rule, which at "
                "a quality weight of 0.6 is worth 0.167 or 0.083 of quality: the best exception clears 0.167 in "
                f"{sum(1 for qb, _ in gains if qb - 1 >= 0.1667)} settings and 0.083 in "
                f"{sum(1 for qb, _ in gains if qb - 1 >= 0.0833)}. With quality_cap 1.0 a review already at the "
                "answer key cannot gain from an exception; any review below it can."]
    out += ["", "## 5. Diagnostic cases", "",
            "`score()` returns `enforced` and `evidence` per target (`case.py diagnostic`). For each fact it takes "
            "the scored contracts where the client's reading and another reading (another candidate of a drawn "
            "figure, the misreading of a fixed fact, or one of the less natural readings of `_other_readings`: the "
            "minimum itself flagged, the forum checked in place of the law, data protection not critical, a reject "
            "only above the count, critical issues signed below the limit) give different entries, looks only at "
            "the aspect of the entry "
            "that tells the two apart, and counts which one the review follows. Not enforced: the review sides with "
            "some other reading more often than with the client's. Enforced: it sides with the client's more often "
            "than with every other. None: no contract tells, or the review follows neither. The three decision "
            "facts are read from the decision against the review's own issue list, so a review that misreads "
            "clauses but decides by the client's rule is still called enforced on them.", ""]
    diag = audit["diagnostics"]
    ref_ok = {t: all(e.get("reference_enforced", {}).get(t) is not False for tier in tiers
                     for e in audit["settings"][tier] if not e.get("skipped")) for t in targets}
    out += _table(["target", "what tells the client's reading from the misreading", "reference enforced",
                   "ablations"],
                  [[f"`{t}`", TELLS[t], "yes" if ref_ok[t] else "no",
                    "separates" if diag.get(t, {}).get("separates") else
                    "untested" if diag.get(t, {}).get("separates") is None else "no"] for t in targets])
    out += ["", "**Reliability on other deliverables** (a run's review is neither the reference nor an ablation). "
            "Settings where the diagnostic calls the deliverable not enforced, of those where it gives a True or "
            "False: the best known solution (built with full knowledge, so every one would be a false negative), "
            "the ablation of the target that also calls other targets not enforced (of the settings where it bites; "
            "facts can interact), and the baseline (each setting's own) and `robust_solution` (its tier's), which "
            "are informational: neither is built with full knowledge.", ""]
    negatives, cross = false_negatives(audit), cross_flag_summary(audit)
    profile = audit.get("diagnostic_profile") or {}

    def cell(false, n):
        return f"{false}/{n}" if n else "–"
    rows = []
    for t in targets:
        fn, cf = negatives.get(t), cross.get(t)
        flags = cell(len(cf["flagged"]), cf["biting"]) if cf else "–"
        if cf and cf["others"]:
            flags += " (" + ", ".join(f"`{u}`" for u in cf["others"]) + ")"
        rows.append([f"`{t}`", cell(len(fn["false"]), fn["diagnosed"]) if fn else "–", flags]
                    + [cell(p[t]["false"], p[t]["diagnosed"]) if t in (p := profile.get(name) or {}) else "–"
                       for name in ("baseline", "robust_solution")])
    out += _table(["target", "best known", "cross flags", "baseline", "robust_solution"], rows)
    cases: dict[str, dict] = {}
    for tier, settings in measured.items():
        for _, case in settings:
            in_force = [t.id for t in case.targets("en")]
            key = module.review_under(world, module.reading_of(case.setting))
            for name, (target, what, doc) in module.diagnostic_cases(world, case.setting).items():
                review, unknown = module._parse(world, json.loads(json.dumps(doc)))
                if target is not None and all(doc[cid] == key[cid] for cid in key
                                              if module.scored(world, world.by_id()[cid], case.setting)):
                    continue            # the misreading changes nothing here
                enforced, _ = module.diagnostic(world, review, case.setting, unknown)
                row = cases.setdefault(name, {"target": target, "what": what, "tiers": {}, "flags": set()})
                hit = (not any(enforced.get(t) is False for t in in_force) if target is None
                       else enforced.get(target) is False)
                row["flags"].update(t for t in in_force if t != target and enforced.get(t) is False)
                k, n = row["tiers"].get(tier, (0, 0))
                row["tiers"][tier] = (k + hit, n + 1)
    out += ["", "**Other deliverables** (`case.py diagnostic_cases`, measured by `gt_report.py`): reviews with every "
            "fact right that differ from the answer key (the diagnostic must call no fact in force not enforced), "
            "and misreadings no ablation makes (it should call their fact not enforced). Settings where it does, of "
            "those where the review differs from the answer key on a scored contract.", ""]
    out += _table(["review", "target", "what it is"] + tiers + ["other targets called not enforced"],
                  [[f"`{name}`", f"`{row['target']}`" if row["target"] else "every fact right", row["what"]]
                   + [cell(*row["tiers"][t]) if t in row["tiers"] else "–" for t in tiers]
                   + [", ".join(f"`{u}`" for u in sorted(row["flags"])) or "none"]
                   for name, row in sorted(cases.items(), key=lambda item: item[1]["target"] is not None)])
    out += ["", "The baseline's column is the checklist's own profile: it knows the playbook's figures (0 on most "
            "facts), does not compare an amendment's date with the draft's and does not read the scope for "
            "customers' personal data (not enforced in every hard setting), misreads enough caps written in "
            "words to look like another multiple in some settings, and looks for an accepted jurisdiction anywhere in "
            "the article, so a law nobody accepts with a seat in Singapore passes as if it checked the forum in "
            "place of the law.", "",
            f"`diagnose()` raised in {(audit.get('diagnose_errors') or {}).get('count', 0)} evaluation(s) of the "
            "audit."]
    found = summarize(findings(audit, meta.get("quality_cap")))
    out += ["", "**Findings** (as validate-case reads the stored audit with this quality_cap):", ""]
    out += [f"- {x}" for x in found or ["none"]] + [""]
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "GT.md"
    dest.write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
