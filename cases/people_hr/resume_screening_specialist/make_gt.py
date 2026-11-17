"""Writes GT.md, the ground truth of people_hr/resume_screening_specialist in five parts, with every table generated
from dataset/audit.json (run `fdebench2 audit-case` first):
python cases/people_hr/resume_screening_specialist/make_gt.py
"""

import json
import sys
from pathlib import Path
from statistics import median

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))
from fdebench2.audit import (cross_flag_summary, false_negatives, findings, shortcut_summary, summarize,  # noqa: E402
                             target_summary, tier_order)
from fdebench2.cases import NativeCase  # noqa: E402

MODULE = NativeCase(ROOT).module
# What diagnose() reads in the invited slots (case.py diagnose).
DIAGNOSTIC = {
    "shortlist_size": "a role's list shorter than the slots (with enough qualified applicants), or a qualified referral "
                      "ranked below the slots; a longer list gives no verdict (the first slots are the invited)",
    "must_haves": "an invited candidate without a must-have skill (or, for R3, without a CISSP or Security+ on record)",
    "relevant_experience": "an invited candidate below the minimum in the role's job family whom the whole career "
                           "would pass",
    "experience_minimums": "an invited candidate below the minimum whom the job descriptions' words (36 / 12 / 12 "
                           "months) would pass",
    "certificate_expiry": "an invited R3 candidate whose required certificate on record has expired by the interview "
                          "day; or the shortlist follows the export-day reading",
    "work_authorization": "an invited candidate who needs sponsorship on a role that requires authorization",
    "one_role_only": "a candidate invited for two roles",
    "application_cutoff": "an invited candidate who applied after the closing date",
    "referral_habit": "a qualified referral not invited and not listed within the first 10 either (one listed below "
                      "the slots was put there for the habit and cut by the size: `shortlist_size`)",
    "past_hire_bias": "the shortlist follows the face-value regression",
    "protected_attributes": "the fair-hiring screen fails (every tier) or the adverse-impact check (hard), or the "
                            "shortlist follows the regression on every column of the history",
}
# Why each rule is a hard gate.
WHY = {
    "must_have_skills": "the hiring managers' requirements: a candidate who lacks one cannot do the job",
    "certificate_validity": "a client data-centre contract requires a valid certificate on the first day",
    "work_authorization": "legal: nobody may be hired for an office or on-site role without existing authorization",
    "one_role_per_candidate": "a candidate interviews for one role; the client's slots are per role",
    "fair_hiring_screen": "company policy and the law since the internal audit: protected attributes must not drive the "
                          "ranking; compliance tests every list for the pattern the audit found (men, under-40s, "
                          "Singaporeans and their combinations favoured), at p < 0.001 so that a list ranked without "
                          "them practically never fails (0 of 3,924 protected-blind lists on four worlds)",
    "application_cutoff": "fairness to the people who saw the closing date",
    "adverse_impact": "legal requirement (the four-fifths rule with a significance test)",
    "referral_boost": "a business policy: the company's referral habit; an approved exception can bend it",
}


def _num(x, d=3):
    return "–" if x is None else f"{x:.{d}f}"


def _table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def main() -> None:
    audit = json.loads((ROOT / "dataset" / "audit.json").read_text(encoding="utf-8"))
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    targets = {t["id"]: t for t in yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))}
    tiers = tier_order(audit["settings"])
    n_settings = {t: len(audit["settings"][t]) for t in tiers}
    out = [
        "# Ground truth — people_hr/resume_screening_specialist",
        "",
        "The ground truth of every setting in five parts: the client facts the agent must learn, the validity checks, "
        "the objective, the reference with its bounds, and the diagnostic cases. Every table is generated from "
        "`dataset/audit.json` by `make_gt.py` (world seed "
        f"{audit['world_seed']}; per tier the public panel and up to {audit['thresholds']['combos']} admissible "
        "combinations of the tier's candidates: " + ", ".join(f"{t} {n_settings[t]}" for t in tiers) + " settings; "
        "easy has only three combinations). Credit is 0 for an invalid deliverable, else quality clipped to [0, 1]; "
        "damage = 1 − credit. A fact bites in a setting when misreading it loses at least "
        f"{audit['thresholds']['ablation_min_damage']:g} of credit (for a parameter: the other candidate's reference, "
        "an agent that guesses wrong but sensibly).",
        "",
        "## 1. Client facts",
        "",
        "One row per target (`locales/en/targets.yaml`). *Ablated as*: a parameter is read as another candidate of its "
        "tier (the reference of that candidate, scored here); any other fact as the reference solver with its most "
        "natural misreading (`case.py` MISREAD, the same learner and exact placement otherwise). *Damage*: min–max over "
        "the settings where it is in force.",
        "",
    ]
    rows = []
    for t in target_summary(audit):
        tid = t["target"]
        spec = targets[tid]
        how = (f"another candidate of `{spec['param']}`" if spec.get("param") else MODULE.MISREAD[tid])
        diag = "no" if not t["has_diagnostic"] else ("separates" if t["separates"] else
                                                      "untested" if t["separates"] is None else "does not separate")
        per = ", ".join(f"{tier} {k}/{n}" for tier, (k, n) in t["per_tier"].items())
        low, high = t["low"], t["high"]
        rows.append([f"`{tid}`", spec["text"].replace("|", "/"), ", ".join(t["tiers"]), how,
                     _num(low) if low == high else f"{_num(low)}–{_num(high)}", per, diag])
    out += _table(["target", "fact", "in force", "ablated as", "damage", "bites", "diagnostic"], rows)
    out += ["", "Facts the client states that are not targets (they stay in requirements.md as context): how the "
            "recruiters screen today (the baseline), how the shortlist is judged, and in easy the experience minimums "
            "(fixed at 36 / 24 / 24 months; without the referral habit nobody strong lies between the candidate "
            "minimums, so the job descriptions' words as minimums cost nothing there) and the scope notes that are "
            "not certificates (every application counts, referrals like everyone else, R2 needs authorization: "
            "`work_authorization`'s easy text, statistics later: `protected_attributes`' easy text). The old targets "
            "`adverse_impact` and `hiring_manager_note` are part of `protected_attributes` (the same misreading: the "
            "managers' bias in the ranking), `easy_scope` was a bundle of five facts (REVIEW.md, Ground truth audit). "
            "The fair-hiring screen is a rule in every tier, not a fact to ask for: a list ranked without the protected "
            "attributes passes it whether or not the agent asked; what the agent must learn is `protected_attributes` "
            "(the note is not to be followed), and a list that follows the note fails the screen.",
            "", "## 2. Validity checks", "",
            "Every rule of case.yaml is a hard gate on the invited (the first `shortlist_size` of each role's list) "
            "(`physical` and `contractual` never bend; `business_policy` bends only through the company policy's "
            "exception path). A file that cannot be read (an unknown id, a role the candidate did not apply to, a "
            "rank that is not a whole number, a rank or candidate twice in one role) is not scored at all.", ""]
    rows = [[f"`{r['id']}`", r["class"], ", ".join(r.get("tiers", tiers)), WHY[r["id"]]] for r in meta["rules"]]
    out += _table(["rule", "class", "tiers", "why it is a hard gate"], rows)
    out += ["", "## 3. Objective", "",
            "objective = Σ over the invited of (1 − 0.05 × (position − 1)) × (true fit − 30) (maximize).", "",
            "- **Invited**: the first `shortlist_size` of each role's list, by rank; a longer list is cut there, a "
            "shorter one leaves slots empty (an empty slot counts 0). The client books interviews from the top down "
            "and usually makes an offer before the bottom, so rank 1 counts in full and each rank below 5% less.",
            "- **True fit** (hidden, per candidate and role, the same in every setting): 30 + a weight per year of "
            "relevant experience above the old minimum (capped) + the valuable nice-to-haves (two per role; the other "
            "listed ones are worth 0–2) + one skill per role the job description does not list (Linux, R, AWS) + a "
            "bonus certificate valid on 1 November + education (R2) + noise (sd 3). The past hires' scores are this "
            "fit plus noise (sd 3) plus the old managers' bias (men +6, women −5, under 30 +6, 30s +2, 40s −8, 50 and "
            "over −12, Singaporeans +6, others −2); the seasoned hires (two in five) brought the senior skills, the "
            "young hires the newer tools, so the bias lands on skill weights in a model that takes the scores at face "
            "value.",
            "- **Uncertainty**: the agent learns the weights from 360 noisy, biased past scores; the fit's own noise "
            "is out of reach (the bound below).",
            "- The baseline (the client's way, requirements.md \"How we screen today\": every rule that decides who may "
            "be listed, the referral habit, then the most months of relevant experience first) anchors quality 0 and "
            "the reference quality 1.", "",
            "## 4. Reference and bounds", "",
            "- **Reference** (`reference_solution`): per role a least-squares regression of the past scores on the "
            "job-related columns (relevant years capped at the cap that fits best, every skill but the must-haves, "
            "the bonus certificate, master's and PhD) with gender, age band and nationality as controls, of which only "
            "the job weights score; the shortlist is the exact optimum of the weighted objective on those values "
            "(a rectangular assignment, scipy's `linear_sum_assignment`), every qualified referral forced in where the "
            "habit applies. Deterministic, under a second per setting.",
            "- **Best known** (`best_known_solution`): the same placement with one regression over all 360 hires and "
            "the bias controls shared by the three roles (the bias is the same in every role). Reachable from the "
            "agent's view with the client's facts; no consistent improvement on the reference (median 1.002 here; "
            "1.015, 0.972 and 1.029 on world seeds 1, 2 and 3).",
            "- **Bound** (`objective_bound`, proven): the exact assignment on the true fits without the adverse-impact "
            "check (a relaxation of every rule set), which no valid shortlist can beat. It needs the hidden fits.", ""]
    rows = []
    for tier in tiers:
        for b in [b for b in audit["bounds"] if b["setting"].startswith(tier + "/")]:
            rows.append([b["setting"], _num(b["reference"], 1), _num(b["baseline"], 1), _num(b["span"]),
                         _num(b["best_known"], 1), _num(b["best_known_quality"]), _num(b["bound"], 1),
                         _num(b["bound_quality"]), _num(b["gap_to_bound"])])
    out += _table(["setting", "reference", "baseline", "span", "best known", "best known quality", "bound",
                   "bound quality", "gap (bound − reference) / reference"], rows)
    known = [b["best_known_quality"] for b in audit["bounds"] if b["best_known_quality"] is not None]
    gaps = [b["gap_to_bound"] for b in audit["bounds"] if b["gap_to_bound"] is not None]
    out += ["", f"The best known solution reaches {min(known):.3f}–{max(known):.3f} on the quality scale (median "
            f"{median(known):.3f}); the reference is {min(gaps):.1%}–{max(gaps):.1%} below the bound. **quality_cap** "
            f"= {meta.get('quality_cap')}: the median best known quality, rounded up to the next 0.01 (full credit at "
            "the best known; DESIGN.md, Ground truth audit).", "",
            "**Value of asking** (never asks = `robust_solution`: ten per role, ranked (the client cuts each list at "
            "its slots); the must-haves read off the job descriptions and the past hires; experience in the role's "
            "family at the strictest candidate minimums; certificates valid on the tier's latest candidate interview "
            "day, the earliest candidate closing date; one list per candidate (a cheap hedge); the past scores "
            "debiased with controls shared by the roles (the strongest reading the view supports); placed like the "
            "reference. Two hedges are chosen per tier, the better of each pair in that tier (generous: the solver "
            "knows which pays): in easy nobody who needs sponsorship on any role and referrals like everyone else; in "
            "medium and hard R2 open to sponsorship (its job description offers an employer of record) and every "
            "referral who meets the loosest candidate requirements invited in the slots every size invites, which "
            "is valid where the drawn minimums happen to be the loosest (without that hedge never asks is invalid "
            "everywhere in medium and hard; with minimums guessed per role to suit the measured settings it reaches "
            "0.23 in medium and 0.18 in hard). never asks (params) = the best single setting's reference or the "
            "baseline, which know every fixed fact):", ""]
    rows = []
    for tier in tier_order(audit["voi"]):
        v = audit["voi"][tier]
        rob = next((c for c in v["candidates"] if c["name"] == "robust_solution"), {})
        rows.append([tier, _num(v["never_asks"]), _num(rob.get("valid_rate")), _num(v["voi"]),
                     _num(v["never_asks_params"]), _num(v["voi_params"])])
    out += _table(["tier", "never asks (credit)", "its validity rate", "voi", "never asks (params)", "voi_params"],
                  rows)
    out += ["", "## 5. Diagnostic cases", "",
            "`diagnose()` returns `enforced` and `evidence` per target from the invited slots. A fact that is a rule "
            "is read off the rule, and a broken rule is attributed to the misreading that explains it (a candidate "
            "below the experience minimum counts for the whole-career reading or for the job descriptions' words, "
            "whichever passes them; both pass: the misreading whose shortlist is nearer). A fact that moves only the "
            "ranking (`past_hire_bias`, `protected_attributes`, and `certificate_expiry` in easy) is measured against "
            "its misreading: the shortlist *follows* it when it loses at least 5% of the quality scale, keeps every "
            "rule but possibly the fair-hiring screen and the adverse-impact check, and its invited slots are nearer to that misreading's than "
            "to every other such misreading's and at most half as far from it as from the reference's. "
            "*Separates*: the reference is enforced in every measured setting and every ablation that bites is not.",
            ""]
    diag = audit["diagnostics"]
    ref_ok = {t: all(e.get("reference_enforced", {}).get(t) is not False for tier in tiers
                     for e in audit["settings"][tier] if not e.get("skipped")) for t in targets}
    rows = []
    for tid in targets:
        d = diag.get(tid, {})
        rows.append([f"`{tid}`", DIAGNOSTIC[tid], "yes" if ref_ok[tid] else "no",
                     "separates" if d.get("separates") else "untested" if d.get("separates") is None else "no"])
    out += _table(["target", "not enforced when", "reference enforced", "ablations"], rows)
    out += ["", "**Reliability on other deliverables** (a run's deliverable is neither the reference nor an "
            "ablation). Settings where the diagnostic calls the deliverable not enforced, of those where it gives a "
            "True or False: the best known solution (valid, built with full knowledge of its setting, so every one "
            "would be a false negative), the ablation of the target that also calls other targets not enforced (of "
            "the settings where it bites; facts can interact), and the baseline (each setting's own) and "
            "`robust_solution` (its tier's), which are informational: neither is built with full knowledge.", ""]
    negatives, cross = false_negatives(audit), cross_flag_summary(audit)
    profile = audit.get("diagnostic_profile") or {}

    def cell(false, n):
        return f"{false}/{n}" if n else "–"
    rows = []
    for tid in targets:
        fn, cf = negatives.get(tid), cross.get(tid)
        flags = cell(len(cf["flagged"]), cf["biting"]) if cf else "–"
        if cf and cf["others"]:
            flags += " (" + ", ".join(f"`{u}`" for u in cf["others"]) + ")"
        rows.append([f"`{tid}`", cell(len(fn["false"]), fn["diagnosed"]) if fn else "–", flags]
                    + [cell(p[tid]["false"], p[tid]["diagnosed"]) if tid in (p := profile.get(name) or {}) else "–"
                       for name in ("baseline", "robust_solution")])
    out += _table(["target", "best known", "cross flags", "baseline", "robust_solution"], rows)
    errors = (audit.get("diagnose_errors") or {}).get("count", 0)
    out += ["", f"`diagnose()` raised in {errors} evaluation(s) of the audit.",
            "", "Probed with other deliverables on the audit's 33 settings (REVIEW.md, Ground truth audit): correct but "
            "different shortlists (the reference with three more candidates per role below the slots and gaps in the ranks, "
            "the reference in reverse order, the reference with each role's last candidate swapped for the next "
            "best, the best known) are never called not enforced (0 of 132); new misreadings are caught by their "
            "own fact (IT-support jobs counted as experience: `relevant_experience` and `experience_minimums` in "
            "13 of 33; certificates valid on the closing date: `certificate_expiry` in 27 of 30; only R3 needing "
            "authorization: `work_authorization` in 32 of 33; graduation year in the face-value model: "
            "`protected_attributes` in 12 and `past_hire_bias` in 3 of 33). The checker's probes: four more correct "
            "but different shortlists (the reference written with float ranks numbered across the roles, an extra "
            "column, shuffled rows, CRLF and a byte-order mark; the reference with four more per role below the slots "
            "and gaps in the ranks; the reference's values with noise of sd 1; the pooled learner placed greedily) are "
            "never called not enforced (0 of 132); new misreadings: the past hires' minimum years as the minimums "
            "(`experience_minimums` in all 25 settings where they break a rule), a lapsed certificate accepted in "
            "every tier (`certificate_expiry` in 30 of 30), the note leaned on with a bonus of 8 points "
            "(`protected_attributes` in the 21 of 33 where the screen fails it; the other 12 keep 0.80–0.94 of the "
            "scale unflagged), the past scores debiased for gender only (`past_hire_bias` in 8 of 33; it keeps "
            "0.71–0.85), and work authorization required for R2 in medium and hard as in easy (valid, 0.80–1.00, "
            "never flagged: an over-strict reading breaks no rule, and a follows-test would flag the baseline)."]
    out += ["", "**Shortcuts** (closed: invalid, or quality at most "
            f"{audit['thresholds']['shortcut_max_quality']:g}). The keyword screens (`skill_count`, "
            "`skills_and_years`, `jd_position`, `jd_scorecard`) keep every client rule but leave the attached past "
            "hires unread, and with them the two facts about reading them (`past_hire_bias`, `protected_attributes`): "
            "they are shortcuts, not a part of the work left undone, and they stay open (REVIEW.md, Ground truth "
            "audit, checker's review). `note_on_top` follows the note only in the order of the reference's own "
            "invited, which no test of the lists can tell from chance without failing protected-blind lists:", ""]
    out += _table(["shortcut", "what it does", "closed in", "best quality where valid"],
                  [[f"`{s['name']}`", s["description"], f"{s['closed']}/{s['settings']}", _num(s["best_quality"])]
                   for s in shortcut_summary(audit)])
    found = summarize(findings(audit, meta.get("quality_cap")))
    out += ["", "**Findings** (as validate-case reads the stored audit with this quality_cap; "
            "`validate.OPEN_AUDIT_FINDINGS` waives the five open shortcuts, with the reasons in REVIEW.md):", ""]
    out += [f"- {x}" for x in found or ["none"]] + [""]
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "GT.md"
    dest.write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
