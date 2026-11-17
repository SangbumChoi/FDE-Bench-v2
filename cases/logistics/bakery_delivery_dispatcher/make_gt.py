"""Writes GT.md, the ground truth of logistics/bakery_delivery_dispatcher in five parts. Every table comes from
dataset/audit.json (run `fdebench2 audit-case` first), except four that are computed here from case.py on the
audit's own settings (the bending table, the cheapest-insertion plan, the planner's guess of the travel times and the
never-asks plan with one lucky guess): python cases/logistics/bakery_delivery_dispatcher/make_gt.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from statistics import median

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))
from fdebench2.audit import (cross_flag_summary, false_negatives, findings, shortcut_summary, summarize,  # noqa: E402
                             target_summary, tier_order)
from fdebench2.cases import NativeCase  # noqa: E402

PENALTY = {"startup_velocity": 0.05, "enterprise_balanced": 0.10}    # configs/policies: soft_rule_penalty
QUALITY_WEIGHT = 0.6                                                  # both policies weigh quality 0.6

# How each fixed fact is misread (case.py _misread; a param: target is read as each other candidate).
MISREAD = {
    "road_distance": "the straight line between the coordinates (no 1.3 for the roads)",
    "speed": "a city van's 30 km/h all morning",
    "rush_hour": "30 km/h all morning, no rush",
    "service_time": "five minutes at every café, whatever its trays (the literal's guess)",
    "cold_chain": "any van for the partner cafés",
    "partner_this_week": "the partner cafés by the refrigerated V4 only",
    "lateness": "deliver_by read as a firm target: a late minute weighted as ten van minutes (the literal's reading)",
    "workshop": "V2 available from 05:00",
    "manager_pressure": "her demand followed: C07 the first stop of its round, reached by 06:30",
}
# What tells a plan that implements the fact from one that misreads it (case.py _diagnostics).
DIAGNOSTIC = {
    "road_distance": "regret against the reference under the client's travel times, explained by the plan's fit to "
                     "a misreading (the straight line; 1.15, 1.45 or 1.6 times it), or a rule it breaks only with "
                     "the client's times",
    "speed": "the same, against 30, 20, 22 or 28 km/h",
    "rush_hour": "the same, against 30, 20 or 25 km/h all morning",
    "rush_start": "the same, against each other start of the rush in the pool, 06:00 and 08:00",
    "service_time": "the same, against five, none or ten minutes a stop, or two minutes plus 0.4 a tray",
    "shift_end": "a van back after the shift end; else regret explained by another candidate's shift end",
    "tray_limit": "a van above the limit; else regret explained by another candidate's limit",
    "closed_cafe": "the closed café served",
    "cold_chain": "a partner café on a dry van",
    "partner_this_week": "regret explained by the V4-only reading (all partners on V4 at a material cost)",
    "premium_first": "where the habit holds, a premium café after a standard one; where it is suspended, regret "
                     "explained by keeping it",
    "lateness": "regret explained by the firm-deadline reading, deliver_by ignored, or a late minute worth one "
                "van minute",
    "workshop": "V2 out before 06:40",
    "manager_pressure": "C07 the first stop of its round and reached by 06:30",
}
WHY = {
    "van_capacity": "the crates do not fit: a van cannot carry more trays than this week's limit",
    "shift_window": "the drivers' shift: no van leaves before 05:00 or comes back after the shift end",
    "van_ready": "V2 is in the workshop until 06:40 on Monday (hard): it cannot leave before then",
    "closed_cafe": "nobody is there to take the trays at the café closed for renovation",
    "serve_each_once": "the cafés' contract: every open café gets all its trays, in one visit",
    "cold_chain": "the partner's chilled products may only travel in the refrigerated van (medium, hard)",
    "premium_first": "the client's habit (business policy): a hard gate under the baseline policy, bendable with an "
                     "approved exception under the others",
}
WHEN = re.compile(r"<!-- when: \w+=([^>]*?) -->(.*?)<!-- /when -->")


def _fact(text: str) -> str:
    return WHEN.sub(lambda m: f"[{m.group(1)}: {m.group(2).strip()}] ", text).strip().replace("|", "/")


def _num(x, d=3):
    return "–" if x is None else f"{x:.{d}f}"


def _range(xs, d=2):
    if not xs:
        return "–"
    low, high = (_num(round(x, d) + 0.0, d) for x in (min(xs), max(xs)))
    return low if low == high else f"{low}–{high}"


def _table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def _settings(case, audit):
    """(label, case in that setting) for every measured setting of the audit."""
    out = []
    for tier in tier_order(audit["settings"]):
        first = case.at(tier, case.rule_seeds[0])
        for e in audit["settings"][tier]:
            if not e.get("skipped"):
                out.append((e["label"], first.with_params(**e["params"])))
    return out


def _quality(c, plan, relaxed=frozenset()):
    m = c.module
    with tempfile.TemporaryDirectory() as tmp:
        m._write(Path(tmp), plan)
        res = c.evaluate(Path(tmp), "en", relaxed=relaxed)
    return res["quality_score"] if res["validity_score"] == 1.0 else None


def _bending(case, audit, cap):
    """Per setting where the habit holds: what it costs the reference planner (share of the objective) and what the
    reference gains in quality when it drops the habit under an approved exception (scored with the rule relaxed)."""
    rows = []
    bend = frozenset({"premium_first"})
    for label, c in _settings(case, audit):
        m = c.module
        rules = m.rules_of(c.setting)
        if not rules.premium_first:
            continue
        free = m._plan(c.world, replace(rules, premium_first=False))
        q = _quality(c, free, bend)
        ref = c.reference_objective
        cost = (ref - m.simulate(c.world, free, rules)[1]) / ref
        gain = q - 1.0
        pays = [p for p, pen in PENALTY.items() if QUALITY_WEIGHT * gain / cap > pen]
        rows.append([label, f"{cost:.1%}", _num(gain, 2), ", ".join(pays) or "neither"])
    return rows


def _insertion(case, audit):
    """Quality of the cheapest-insertion plan (case.py insertion_plan) per tier: [low, high, settings above 0.5]."""
    out = {}
    for label, c in _settings(case, audit):
        q = _quality(c, c.module.insertion_plan(c.world, c.module.rules_of(c.setting)))
        out.setdefault(c.tier, []).append(q if q is not None else 0.0)
    return out


def _guessed_travel(case, audit):
    """Quality per tier of the reference planner with every fact the client states but the travel times, which it
    guesses as a planner would (case.py PLANNER_GUESS: 1.3 times the straight line, 25 km/h, five minutes a stop,
    no rush): [qualities, 0.0 for an invalid plan]."""
    out = {}
    for label, c in _settings(case, audit):
        m = c.module
        rules = m.rules_of(c.setting)
        q = _quality(c, m._plan(c.world, replace(rules, travel=m.PLANNER_GUESS, rush=None)))
        out.setdefault(c.tier, []).append(q if q is not None else 0.0)
    return out


def _lucky(case, audit):
    """Mean credit per tier of robust_solution with one lucky guess about a fact nothing on hand settles: the partner
    cafés free for any van (the client's reading in easy), or V2 on the latest round (V2's workshop morning in
    hard); the better of the two."""
    out = {}
    for tier in tier_order(audit["settings"]):
        first = case.at(tier, case.rule_seeds[0])
        m = first.module
        pools = {name: list(by_tier[tier]) for name, by_tier in first.param_candidates.items()}
        plans = [m._robust_plan(first.world, tier, pools, cold_chain=False)]
        swapped = json.loads(json.dumps(m._robust_plan(first.world, tier, pools)))
        dry = sorted([r for r in swapped if r["van"] in ("V1", "V2", "V3")], key=lambda r: r["depart"])
        if dry:
            latest = dry[-1]["van"]
            for r in swapped:
                r["van"] = {"V2": latest, latest: "V2"}.get(r["van"], r["van"])
        plans.append(swapped)
        best = 0.0
        for plan in plans:
            credits = []
            for _, c in [x for x in _settings(case, audit) if x[1].tier == tier]:
                q = _quality(c, plan)
                credits.append(0.0 if q is None else min(max(q, 0.0), 1.0))
            best = max(best, sum(credits) / len(credits))
        out[tier] = best
    return out


def main() -> None:
    audit = json.loads((ROOT / "dataset" / "audit.json").read_text(encoding="utf-8"))
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    en = (ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8")
    targets = {t["id"]: t for t in yaml.safe_load(en)}
    case = NativeCase(ROOT)
    cap = float(meta.get("quality_cap") or 1.0)
    tiers = tier_order(audit["settings"])
    n = {t: len(audit["settings"][t]) for t in tiers}
    out = [
        "# Ground truth — logistics/bakery_delivery_dispatcher",
        "",
        "The ground truth of every setting in five parts: the client facts the agent must learn, the validity checks, "
        "the objective, the reference with its bounds, and the diagnostic cases. Every table is generated by "
        f"`make_gt.py` from `dataset/audit.json` (world seed {audit['world_seed']}; per tier the public panel and up "
        "to "
        f"{audit['thresholds']['combos']} admissible combinations of the tier's candidates: "
        + ", ".join(f"{t} {n[t]}" for t in tiers) + " settings; easy has only 9 combinations), except the bending, "
        "cheapest-insertion, guessed-travel and lucky never-asks numbers, which it computes from case.py on the same "
        "settings. Credit "
        "is 0 for an invalid plan, else quality clipped to [0, 1]; damage = 1 − credit. A fact bites in a setting when "
        f"misreading it loses at least {audit['thresholds']['ablation_min_damage']:g} of credit (for a parameter: the "
        "least harmful other candidate, an agent that guesses wrong but sensibly).",
        "",
        "## 1. Client facts",
        "",
        "One row per target (`locales/en/targets.yaml`). *Ablated as*: a parameter is read as each other candidate of "
        "its tier (the reference of that candidate, scored here); any other fact as the reference planner's plan with "
        "that one fact read the most natural wrong way the agent's view allows. *Damage*: min–max over the settings "
        "where it is in force (best guess for a parameter).",
        "",
    ]
    rows = []
    for t in target_summary(audit):
        tid = t["target"]
        spec = targets[tid]
        how = MISREAD.get(tid) or (f"another candidate of `{spec['param']}`" if spec.get("param") else "?")
        if tid == "tray_limit":
            how = "another candidate of `van_capacity`; in hard, where it is always 110, the racks' 120 from the data"
        diag = "no" if not t["has_diagnostic"] else ("separates" if t["separates"] else
                                                      "untested" if t["separates"] is None else "does not separate")
        per = ", ".join(f"{tier} {k}/{m}" for tier, (k, m) in t["per_tier"].items())
        rows.append([f"`{tid}`", _fact(spec["text"]), ", ".join(t["tiers"]), how, _range([t["low"], t["high"]], 3),
                     per, diag])
    out += _table(["target", "fact", "in force", "ablated as", "damage", "bites", "diagnostic"], rows)
    out += ["", "A parameter with an ordered pool bites only where the client's value is the strict end of it: a "
            "smaller tray limit or an earlier shift end than the client's costs little (a plan that keeps the "
            "stricter rule is valid), so `tray_limit` bites only where the limit is 100 (or in hard, 110 against the "
            "racks' 120) and `shift_end` only where the shift ends at 09:00 and the later shifts' plans come back "
            "after it.",
            "", "Facts the client states that are not targets (they stay in requirements.md as context, and the "
            "client still answers them when asked):", "",
            "- **One visit per café**: the deliverable has no tray count per stop, so a split delivery cannot be "
            "written; a café listed twice is already a `serve_each_once` violation. The fact changes no plan.",
            "- **The lateness cost in easy** (a late minute costs as much as 3 van minutes): the first version drew "
            "it from 2, 3 and 5, but the reference is on time or nearly so in almost every setting, so no other "
            "weight changes its plan by a tenth of the scale (the validator found no binding in easy). It is now a "
            "fixed fact of every tier, and a target (`lateness`) in medium and hard only, where reading deliver_by "
            "as a firm deadline costs a tenth of the scale or more in some settings; in easy it never does.",
            "- **The shift end in easy and medium** (10:00): no good plan comes back after 09:00 there, so it was "
            "drawn only in hard; in easy and medium it is a fixed rule that never binds the reference.",
            "- **Vans may leave from 05:00** and **waiting until a café opens**: every plan worth handing in leaves "
            "after 05:00 and does not plan on dropping trays before opening; the scorer makes a van wait anyway.",
            "- **How the dispatcher plans today**: context for the client's own way, the zero of the quality scale "
            "(part 3).",
            "", "## 2. Validity checks", "",
            "Every rule of case.yaml is a hard gate (`physical` and `contractual` never bend; `business_policy` bends "
            "only through the company policy's exception path). A file that cannot be read (no `routes.json`, an "
            "unknown van or café, two routes for one van, a departure not written HH:MM) is fatal.", ""]
    out += _table(["rule", "class", "tiers", "why it is a hard gate"],
                  [[f"`{r['id']}`", r["class"], ", ".join(r.get("tiers", tiers)), WHY[r["id"]]] for r in meta["rules"]])
    out += ["", "**Bending the premium-first habit.** What an approved exception is worth where the habit holds: what "
            "keeping it costs the reference planner, and the quality the reference planner reaches without it "
            "(scored with the rule relaxed) minus the reference's 1. A bent rule costs a policy's penalty (0.05 "
            f"under the startup policy, 0.10 under the enterprise one) and quality weighs {QUALITY_WEIGHT:g} there, "
            "so a gain g in quality pays when 0.6 × g / quality_cap exceeds the penalty: g above "
            f"{0.05 * cap / QUALITY_WEIGHT:.3f} and {0.10 * cap / QUALITY_WEIGHT:.3f}.", ""]
    bend = _bending(case, audit, cap)
    out += _table(["setting", "the habit costs", "gain when bent (quality)", "pays under"], bend)
    out += ["", "The premium cafés open first (06:00 or 06:30), so the habit mostly agrees with the clock; it costs "
            "where the East Lake café (C07, premium, opening at 07:00 or later) or a partner café on V4 has to come "
            "before a standard café that opens earlier. So the bend pays under both policies in some settings, under "
            "the startup policy only in others, and loses in the rest. The first version's habit cost about 28% of "
            "the objective everywhere (the premium cafés opened at any time), so bending paid in every setting. "
            "A plan already at the reference's level gains nothing from a bend: quality_cap is "
            f"{cap:g}, the best known level, so full credit is already its own." if cap <= 1.0 else
            "For a plan already at the reference's level the gain is capped by quality_cap: at most "
            f"{cap - 1:.2f} of quality credit, less than either penalty.",
            "", "## 3. Objective", "",
            "objective = the minutes all vans are out (leaving the kitchen to coming back, waiting at a café that is "
            "not open yet included) + 3 × the minutes cafés are reached after their deliver_by; minimize.",
            "",
            "- **Travel times.** Road distance is 1.3 times the straight line; vans drive 25 km/h all morning in easy "
            "and medium, and in hard 30 km/h before the rush and 20 km/h from it, also on a leg under way. Unloading "
            "takes 4 minutes plus 0.2 a tray. None of this is in the data: the request gives positions only.",
            "- **The zero and the one.** Quality 0 is the dispatcher's hand plan (`baseline_solution`, described to "
            "the agent in the requirements): he gives out the cafés by opening time (or by deliver_by, or splits the "
            "map into four slices: he draws up the three and drives the cheapest), each to the van that can be there "
            "first, puts each round in its best order and sends each van out to reach its first café as it opens. It "
            "knows every rule and the travel times. The first version's zero point sent every van out at 05:00 along "
            "a slice of the map, 1.2 to 3.8 times the reference: a strawman that made a plan 20% worse than the "
            "reference still score about 0.9. Quality 1 is the reference (part 4).",
            "", "## 4. Reference and bounds", "",
            "- **Reference** (`reference_solution`): starts from the greedy cheapest-insertion construction, the "
            "tier's fallback plan and the dispatcher's plan; local search (relocation, exchanges between routes, "
            "reversals within one) and three ruin-and-recreate runs of 300 rounds (one with a cooling threshold), "
            "departures on a 5-minute grid; the best plan polished again with departures to the minute.",
            "- **Best known** (`best_known_solution`, stored by `make_bounds.py` in `reference/best_known.json`): "
            "the best of a long ruin-and-recreate search (4 runs of 3,000 rounds), the mixed-integer model's best "
            "routes below, given to the vans in the cheapest valid way and driven with departures to the minute, and "
            "a search from them.",
            "- **Bound** (`objective_bound`, proven): the dual bound of a mixed-integer model (scipy's HiGHS, 300 s "
            "per setting) of a relaxation: every café visited once by at most four routes, the tray limit, back by "
            "the shift end, the cold chain (the partner cafés on one route), no premium café right after a standard "
            "one where the habit holds, waiting and lateness priced as in the objective, and the client's travel "
            "times with the morning rush priced exactly (every leg at the speed before the rush plus the extra "
            "minutes the rush adds to it, a binary per leg for the side of the rush it starts on). Relaxed: "
            "departures free to the second, waiting allowed anywhere, and V2's workshop morning as \"at most three "
            "routes leave before 06:40\". Every valid plan maps onto a solution of the model that costs no more, so "
            "its dual bound is a lower bound. The first version drove every leg at 30 km/h in hard, 11% to 28% below "
            "the reference; now HiGHS solves the model to optimality in every stored setting (`mip` in "
            "`reference/best_known.json`), in 10 to 180 s each.", ""]
    rows = []
    for tier in tiers:
        for b in [b for b in audit["bounds"] if b["setting"].startswith(tier + "/")]:
            rows.append([b["setting"], _num(b["reference"], 2), _num(b["baseline"], 2), _num(b["span"]),
                         _num(b["best_known"], 2), _num(b["best_known_quality"]), _num(b["bound"], 2),
                         _num(b["bound_quality"]), _num(b["gap_to_bound"], 4)])
    out += _table(["setting", "reference", "baseline", "span", "best known", "best known quality", "bound",
                   "bound quality", "gap (reference − bound) / reference"], rows)
    known = [b["best_known_quality"] for b in audit["bounds"] if b["best_known_quality"] is not None]
    spans = [b["span"] for b in audit["bounds"]]
    gaps = {t: [b["gap_to_bound"] for b in audit["bounds"] if b["setting"].startswith(t + "/") and
                b["gap_to_bound"] is not None] for t in tiers}
    out += ["", f"The quality scale is {min(spans):.1%} to {max(spans):.0%} of the reference's objective wide. The "
            f"best known plan reaches {min(known):.3f}–{max(known):.3f} (median {median(known):.3f}). The reference is "
            + "; ".join(f"{t} {_range(g, 4)}" for t, g in gaps.items() if g)
            + " above the bound. "
            f"**quality_cap** = {meta.get('quality_cap')}: the median best known quality, rounded up to the next 0.01.",
            "", "**Value of asking** (never asks = `robust_solution`: the client's travel times granted; the partner "
            "cafés on V4; deliver_by read as a target but not a wall, a late minute weighted as five van minutes; the "
            "smallest tray limit and earliest shift end of the "
            "pool; one candidate café left out as the closed one, the habit kept or not and the rush planned at one "
            "candidate start, chosen by its own estimate over every combination of the pools; V2's workshop morning "
            "and the C07 demand unknown. never asks (params) = the best single setting's reference or the baseline, "
            "which know every fixed fact):", ""]
    lucky = _lucky(case, audit)
    rows = []
    for tier in tier_order(audit["voi"]):
        v = audit["voi"][tier]
        rob = next((c for c in v["candidates"] if c["name"] == "robust_solution"), {})
        rows.append([tier, _num(v["never_asks"]), _num(rob.get("valid_rate")), _num(v["voi"]), _num(lucky[tier]),
                     _num(v["never_asks_params"]), _num(v["voi_params"])])
    out += _table(["tier", "never asks (credit)", "its validity rate", "voi", "with one lucky guess",
                   "never asks (params)", "voi_params"], rows)
    out += ["", "Leaving one of the three candidate cafés out makes the plan valid in a third of the settings at most; "
            "serving all of them makes it invalid everywhere. Keeping the partner cafés on V4 costs it in easy, where "
            "any van may serve them; in hard V2's workshop morning (nothing on hand mentions it) makes it invalid "
            "wherever V2 happens to leave before 06:40. *With one lucky guess*: the better of the same solver with the "
            "partner cafés free for any van and the same plan with V2 on its latest round, guesses nothing on hand "
            "supports.",
            "", "## 5. Diagnostic cases", "",
            "`diagnose()` returns `enforced` and `evidence` per target in force, for valid and invalid plans alike "
            "(see case.py, diagnostics). A rule that only one fact states is read off the plan; every other fact by "
            "regret: a plan that loses at least 0.05 of the scale against the reference, and whose loss one of the "
            "fact's misreadings explains (its ablation's, the other candidates of its parameter, and a small grid "
            "round the client's value in both directions, `_other_way`; under the misread rules it is at least half "
            "its loss, 60% for the grid, closer to the reference planner's own plan for them), or that breaks a rule "
            "of the client's that the misreading would keep, is "
            "not enforced on that fact. *Separates*: the reference is enforced in every measured setting and every "
            "ablation that bites is not.", ""]
    ref_ok = {t: all(e.get("reference_enforced", {}).get(t) is not False for tier in tiers
                     for e in audit["settings"][tier] if not e.get("skipped")) for t in targets}
    diag = audit["diagnostics"]
    out += _table(["target", "what tells a plan that implements the fact from one that misreads it",
                   "reference enforced", "ablations"],
                  [[f"`{t}`", DIAGNOSTIC[t], "yes" if ref_ok[t] else "no",
                    "separates" if diag.get(t, {}).get("separates") else
                    "untested" if diag.get(t, {}).get("separates") is None else "no"] for t in targets])
    out += ["", "**Reliability on other deliverables.** Settings where the diagnostic calls the deliverable not "
            "enforced, of those where it gives a True or False: the best known solution (valid, built with full "
            "knowledge, so every one would be a false negative), the ablation of the target that also calls other "
            "targets not enforced (of the settings where it bites), and the baseline and `robust_solution` "
            "(informational). The travel facts all change how long the vans take, so a plan made with one of them "
            "misread is often explained by another as well: those cross flags are the facts interacting, not the "
            "diagnostic failing.", ""]
    negatives, cross = false_negatives(audit), cross_flag_summary(audit)
    profile = audit.get("diagnostic_profile") or {}

    def cell(false, m):
        return f"{false}/{m}" if m else "–"
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
    out += ["", "**Shortcuts** (closed: invalid, or quality at most "
            f"{audit['thresholds']['shortcut_max_quality']:g}). Every lazy plan is given every rule of its setting "
            "that it can keep and the client's travel times, so that only its laziness is measured:", ""]
    out += _table(["shortcut", "what it does", "closed in", "best quality where valid"],
                  [[f"`{s['name']}`", s["description"], f"{s['closed']}/{s['settings']}", _num(s["best_quality"])]
                   for s in shortcut_summary(audit)])
    ins = _insertion(case, audit)
    out += ["", "**A part of the work, not a shortcut.** Cheapest insertion (`insertion_plan`: the cafés in the "
            "dispatcher's order, each where it adds the least on any round, each van at its best departure) needs "
            "every fact the client knows: the rules and the travel times. Its quality per tier: "
            + "; ".join(f"{t} {_range(v)} (above 0.5 in {sum(x > 0.5 for x in v)} of {len(v)})" for t, v in ins.items())
            + ". It stays at or below 0.5 on this world but not on every world (REVIEW.md, Ground truth audit), so it "
            "is reported here and not as a shortcut: with every fact right, a good construction heuristic does a "
            "large part of the work, and the reference's search the rest.",
            "", "**The travel times are guessable** (open, `literal_plus_closed_cafe_planner_guess`). Each travel "
            "fact bites against its own misreading (part 1), but a planner's guess of all of them together comes "
            "close: with every other fact the client states and the travel times guessed (1.3 times the straight "
            "line, 25 km/h, five minutes a stop, no rush), the reference planner reaches "
            + "; ".join(f"{t} {_range(v)} (above 0.5 in {sum(x > 0.5 for x in v)} of {len(v)})"
                        for t, v in _guessed_travel(case, audit).items())
            + ". So in the easy settings, where the closed café is often the only rule the literal solution breaks "
            "(with the racks' 120 trays, or a load that happens to fit the week's limit), knowing that café and "
            "guessing the rest scores above 0.5. Closing it needs a "
            "travel fact no uniform guess approximates (a prototype in which the vans cross the river only at the "
            "kitchen closed it, but drew a new world and opened the one-move shortcut in 19 of 39 settings): a "
            "redesign, left open (REVIEW.md, Ground truth audit).",
            "", "**Findings** (as validate-case reads the stored audit with this quality_cap; OPEN_AUDIT_FINDINGS may "
            "waive a problem):", ""]
    out += [f"- {x}" for x in summarize(findings(audit, meta.get("quality_cap"))) or ["none"]] + [""]
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "GT.md"
    dest.write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
