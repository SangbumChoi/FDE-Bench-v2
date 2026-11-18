"""Writes GT.md, the ground truth of customer_service/callcenter_workforce_planner in five parts, with every table
generated from dataset/audit.json (run `fdebench2 audit-case` first):
python cases/customer_service/callcenter_workforce_planner/make_gt.py
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

# How each fact is misread (case.py _misreading; a param: target is read as the other candidate of its parameter).
MISREAD = {
    "one_language": "a bilingual agent on shift counts on each of their languages at once",
    "holiday": "the forecast file as it is: no day cut",
    "training_salary": "a new hire paid by the shift like everyone else in labor_cost.csv",
    "buddy_rule": "new hires rostered like everyone else",
    "sick_call": "the team lead's note followed: the agent rostered as usual",
}
# What diagnose() reads in the roster.
DIAGNOSTIC = {
    "one_language": "follows the double-counting reading (see below)",
    "understaffing_price": "follows the other price of a missing agent",
    "ft_contract_week": "a full-timer above the contract week (from medium: beyond it without the approval), or "
                        "follows the other contract week",
    "pt_contract_week": "a part-timer above the contract week, or follows the other contract week",
    "min_rest": "two shifts closer than the rest time, or follows the other rest time",
    "holiday": "follows the uncut forecast, or the cut on another candidate day",
    "training_salary": "follows the reading where new hires are paid by the shift",
    "buddy_rule": "a new hire alone on a language (none when no new hire is rostered)",
    "sick_call": "the note's agent rostered on a certified sick day (none when that agent is not rostered at all)",
}
# Why each rule is a hard gate.
WHY = {
    "skill_valid": "an agent cannot take calls in a language they do not speak",
    "shift_type": "the contracts fix the shift length",
    "max_shifts": "the contract weeks: nobody is paid or scheduled beyond them (from medium, one approved overtime "
                  "shift more for a full-timer)",
    "min_rest": "the labor agreement's rest time (11 h is the EU minimum, 13 h a stricter company agreement)",
    "leave_respected": "approved leave cannot be taken back",
    "overtime_approval": "a business policy: the operations manager approves each overtime shift; an approved "
                         "exception can bend it, and with the 1.5 times premium that pays only where a missing "
                         "agent is dear",
    "buddy_rule": "the training agreement: a new hire is never alone on a language (contractual since the audit; "
                  "it was a bendable habit)",
    "sick_leave": "a doctor's certificate: the agent is not fit to work",
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
        "# Ground truth — customer_service/callcenter_workforce_planner",
        "",
        "The ground truth of every setting in five parts: the client facts the agent must learn, the validity checks, "
        "the objective, the reference with its bounds, and the diagnostic cases. Every table is generated from "
        "`dataset/audit.json` by `make_gt.py` (world seed "
        f"{audit['world_seed']}; per tier the public panel and {audit['thresholds']['combos']} admissible "
        "combinations of the tier's candidates: " + ", ".join(f"{t} {n_settings[t]}" for t in tiers) + " settings). "
        "Credit is 0 for an invalid deliverable, else quality clipped to [0, 1]; damage = 1 − credit. A fact bites "
        f"in a setting when misreading it loses at least {audit['thresholds']['ablation_min_damage']:g} of credit "
        "(for a parameter: the other candidate's reference, an agent that guesses wrong but sensibly).",
        "",
        "## 1. Client facts",
        "",
        "One row per target (`locales/en/targets.yaml`). *Ablated as*: a parameter is read as the other candidate of "
        "its tier (the reference of that candidate, scored here); any other fact as the reference planner with its "
        "most natural misreading (the reference itself where that roster is valid and no worse by the misreading). "
        "*Damage*: min–max over the settings where it is in force.",
        "",
    ]
    rows = []
    for t in target_summary(audit):
        tid = t["target"]
        spec = targets[tid]
        how = (f"the other candidate of `{spec['param']}`" if spec.get("param") else MISREAD.get(tid, "?"))
        diag = "no" if not t["has_diagnostic"] else ("separates" if t["separates"] else
                                                      "untested" if t["separates"] is None else "does not separate")
        per = ", ".join(f"{tier} {k}/{n}" for tier, (k, n) in t["per_tier"].items())
        low, high = t["low"], t["high"]
        rows.append([f"`{tid}`", spec["text"].replace("|", "/"), ", ".join(t["tiers"]), how,
                     _num(low) if low == high else f"{_num(low)}–{_num(high)}", per, diag])
    out += _table(["target", "fact", "in force", "ablated as", "damage", "bites", "diagnostic"], rows)
    out += ["", "Facts the client states that are not targets (they stay in requirements.md as context, or are rules "
            "the agent can read off its own data): that the forecast is already in agents per half-hour slot (the "
            "column is `agents_needed` per `slot_start`), the shift types per contract (`shifts.csv` has a "
            "`contract` column), the leave file's day/month/year dates (read as day/month, every request falls inside the "
            "week asked for, 9 to 12 November; read as month/day, they would spread from September to December, and "
            "the one request that reads the same either way, 11/11, is inside it too) and that a rejected request is not leave (its `status` says "
            "`rejected`). A careful agent infers each of these from the data in every setting, so asking for them "
            "is not scored (REVIEW.md, Ground truth audit). The old `easy_scope` and `one_shift_a_day` targets went "
            "with the rules they described: the rest time now applies in every tier, and overtime is out of easy's "
            "scope by the contract week itself. `overtime_approval` is part of `ft_contract_week` from medium (the "
            "client states the cap and the approval in one breath, and a roster cannot tell the two misreadings "
            "apart); the rule `overtime_approval` stays.",
            "", "## 2. Validity checks", "",
            "Every rule of case.yaml is a hard gate (`physical` and `contractual` never bend; `business_policy` bends "
            "only through the company policy's exception path).", ""]
    rows = [[f"`{r['id']}`", r["class"], ", ".join(r.get("tiers", tiers)), WHY[r["id"]]] for r in meta["rules"]]
    out += _table(["rule", "class", "tiers", "why it is a hard gate"], rows)
    out += ["", "## 3. Objective", "",
            "objective = `under_weight` × the under-covered agent-slots + the labor cost (minimize).", "",
            "- **Under-covered agent-slots**: per day, half-hour slot and language, the forecast's agents needed (on "
            "the holiday `holiday_factor` of it, rounded up) minus the agents assigned to that language in that slot, "
            "when positive. An agent counts in one language only, in every slot of their shift.",
            "- **Labor cost**: hours × rate (22 full-time, 18 part-time) for every shift worked; a part-timer's "
            "contract week (guaranteed hours) and a new hire's (training salary) are paid in full even when fewer of "
            "their shifts are rostered; a full-timer's shift beyond the contract week (possible from medium, only "
            "with an approved exception) at 1.5 times.",
            "- **Uncertainty**: none in the objective; the forecast is the client's planning figure. The uncertain "
            "part of the case is the client's facts, above all in hard the sick call that contradicts the team "
            "lead's note.",
            "- The baseline (the client's own way: the supervisor's fixed rota, one shift all week in the main "
            "language, every experienced agent their contract week, new hires shadowing a senior) anchors quality 0 "
            "and the reference quality 1.", "",
            "## 4. Reference and bounds", "",
            "- **Reference** (`reference_solution`, `_Planner`): each agent's week is re-planned exactly given "
            "everyone else's, a dynamic program over the seven days (shift and language each day, within the "
            "contract week and the rest time, a new hire only beside an experienced colleague of the same language), "
            "agents in turn until no week improves; then every pair of agents who share a language is taken off and "
            "re-planned together (an experienced agent and a new hire also with the first planning for both) while "
            "that lowers the objective. No overtime shift (the policy is not bent). Deterministic, 1–10 s per setting.",
            "- **Best known** (`best_known_solution`): the exact optimum of the same model, a mixed-integer program "
            "solved by HiGHS (scipy) to proven optimality (time limit 300 s, never reached in the audit).",
            "- **Bound** (`objective_bound`, proven): the MILP's dual bound. Its scope is every roster that keeps "
            "every rule, the overtime approval included: a roster with an approved overtime exception can end below "
            "it (section Bending in REVIEW.md).", ""]
    rows = []
    for tier in tiers:
        for b in [b for b in audit["bounds"] if b["setting"].startswith(tier + "/")]:
            rows.append([b["setting"], _num(b["reference"], 0), _num(b["baseline"], 0), _num(b["span"]),
                         _num(b["best_known"], 0), _num(b["best_known_quality"]), _num(b["bound"], 0),
                         _num(b["gap_to_bound"])])
    out += _table(["setting", "reference", "baseline", "span", "best known", "best known quality", "bound",
                   "gap (reference − bound) / reference"], rows)
    known = [b["best_known_quality"] for b in audit["bounds"] if b["best_known_quality"] is not None]
    gaps = [b["gap_to_bound"] for b in audit["bounds"] if b["gap_to_bound"] is not None]
    out += ["", f"The best known solution reaches {min(known):.3f}–{max(known):.3f} on the quality scale (median "
            f"{median(known):.3f}); the reference is {min(gaps):.1%}–{max(gaps):.1%} above the bound. **quality_cap** "
            f"= {meta.get('quality_cap')}: the median best known quality over the measured settings, rounded up to the "
            "next 0.01 (full credit at the best known; DESIGN.md, Ground truth audit).", "",
            "**Value of asking** (never asks = `robust_solution`: the strictest candidate of every rule (the shorter "
            "contract weeks, the longer rest, from medium the buddy rule, in hard the latest sick day), no overtime, "
            "and the exact optimum of the expected objective over every price, holiday day and holiday share of the "
            "tier's pools, a stochastic MILP; every shift read as paid by the hour, as the view suggests; never asks "
            "(params) = the best single setting's reference or the baseline, which know every fixed fact):", ""]
    rows = []
    for tier in tier_order(audit["voi"]):
        v = audit["voi"][tier]
        rob = next((c for c in v["candidates"] if c["name"] == "robust_solution"), {})
        rows.append([tier, _num(v["never_asks"]), _num(rob.get("valid_rate")), _num(v["voi"]),
                     _num(v["never_asks_params"]), _num(v["voi_params"])])
    out += _table(["tier", "never asks (credit)", "its validity rate", "voi", "never asks (params)", "voi_params"],
                  rows)
    out += ["", "## 5. Diagnostic cases", "",
            "`diagnose()` returns `enforced` and `evidence` per target from the roster `score()` parsed. A fact that "
            "is a rule is read off the rule (a part-timer or full-timer above the contract week, two shifts closer "
            "than the rest time, an overtime shift, a new hire alone, the sick agent on a sick day). Every other "
            "fact, and a contract week or rest time that is kept, is measured against each other reading (the "
            "other candidate of the parameter, or the natural misreading; for the holiday also the cut on each other "
            "candidate day): the roster *follows* that reading when it "
            "loses at least 5% of the quality scale against the reference, keeps that reading's rules, and is "
            "closer to the reference planner's roster under that reading than to the true one's (by at least 5% of "
            "the scale and with at most half the distance). A roster at least as good as the reference never "
            "follows another reading. *Separates*: the reference is enforced in every measured setting and every "
            "ablation that bites is not.", ""]
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
    out += ["", f"`diagnose()` raised in {errors} evaluation(s) of the audit."]
    out += ["", "**Shortcuts** (closed: invalid, or quality at most "
            f"{audit['thresholds']['shortcut_max_quality']:g}):", ""]
    out += _table(["shortcut", "what it does", "closed in", "best quality where valid"],
                  [[f"`{s['name']}`", s["description"], f"{s['closed']}/{s['settings']}", _num(s["best_quality"])]
                   for s in shortcut_summary(audit)])
    found = summarize(findings(audit, meta.get("quality_cap")))
    out += ["", "**Findings** (as validate-case reads the stored audit with this quality_cap; "
            "OPEN_AUDIT_FINDINGS may waive a problem):", ""] + [f"- {x}" for x in found or ["none"]] + [""]
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "GT.md"
    dest.write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
