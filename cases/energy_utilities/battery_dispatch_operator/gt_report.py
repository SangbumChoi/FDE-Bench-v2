"""Write GT.md (the case's ground truth in five parts) and CLIENT_REVIEW.md (what the simulated client answers from).

Run from the repository root:  python cases/energy_utilities/battery_dispatch_operator/gt_report.py [gt] [client]
GT.md takes every number in its audit tables from dataset/audit.json (`fdebench2 audit-case`, public world), and two
tables from the case itself, replayed in-process on the public settings (the literal plan and its next readings;
bending the evening reserve); the prose around them is fixed here, and its few other numbers (the never-asks search,
world seeds 1-3) are stated with how they were measured. Neither file quotes the audit's fingerprint, so writing them
again after a fresh audit of the same sources gives the same files. Both are case docs (cases.CASE_DOCS), outside the
audit's fingerprint, so writing them never makes the stored audit stale; this script is a source of the audit, like
case.py.
"""

from __future__ import annotations

import dataclasses
import json
import re
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

LANGS = ("en", "zh", "ko", "ja", "es")

# Why each rule is a hard gate, in the client's terms.
RULE_WHY = {
    "complete_plan": "the site controller runs the schedule quarter by quarter in local time: a quarter without a row "
                     "has no setpoint, and a setpoint at 02:00-02:45 on 28 March cannot be run (that time does not "
                     "exist). New with the audit: such a plan was unreadable (fatal) before; a row at a skipped time "
                     "that moves nothing is ignored",
    "soc_limits": "the warranty: outside its window (with the client's per-direction efficiencies) the warranty lapses",
    "power_limits": "the inverters: 20 MW each way, one direction at a time, and the connection's 20 MW import",
    "export_cap": "the amended connection agreement: the substation cannot take more while the works last",
    "grid_charging_window": "medium and hard: the grid supply contract allows import only in the off-peak window",
    "end_soc": "the handover to next week's plan",
    "evening_reserve": "company policy for emergencies. The one bendable rule: operations can approve an exception",
    "dso_limit": "hard: the DSO's notice for its works on the line",
    "maintenance_outage": "hard: the inverters are switched off for maintenance",
}
SOC_HOOK = ("where no other window is admissible (10-85% under a 15% reserve), the spec sheet's 5-95% "
            "(`ablations()`)")
# What tells a correct plan from the misreading (case.py diagnose), read from the plan's own numbers.
DIAGNOSTIC = {
    "efficiency": "the plan's SOC keeps the window, reserve and end level with the client's split; if not, another "
                  "split under which it does and sits on the limits is the plan's (False): another candidate, the "
                  "sheet's 84.6% split evenly (92/92) or all on charge or on discharge, or the client's applied the "
                  "wrong way round on discharge; a plan that falls short of the warranty limits every day under the "
                  "client's split but sits on them under another is that split's too",
    "soc_window": "on the plan's own split: a SOC outside the window but inside another candidate's (or the sheet's "
                  "5-95%, the log's 10-90%) is False; inside it, a SOC that stays inside a stricter candidate's "
                  "window and stops exactly (0.01 MWh) at its floor or ceiling where the optimum goes past is False, "
                  "unless that floor is the reserve's level (a planner that keeps the reserve all day stops there "
                  "too: not determinable); the 21-89% the log runs in counts the same way for a plan within 0.5% of "
                  "that range's optimum",
    "end_soc": "the week ends below the level (False), or exactly at a higher candidate the optimum sells below (False)",
    "export_cap": "site export while discharging above the limit before any candidate end of the works (False), or "
                  "held exactly at a lower candidate in 3 or more quarters while the optimum exports more (False)",
    "grid_charging": "no grid draw outside the window (else False); and no other candidate window that holds every "
                     "draw while, on two or more nights, a cheaper quarter of the client's window rests and a dearer "
                     "one imports (False)",
    "reserve_level": "the SOC in the reserve hours falls to a lower admissible candidate rather than through another "
                     "candidate's hours (False), or sits exactly on a higher candidate on two or more days the "
                     "optimum sells below (False)",
    "reserve_hours": "the reserve broken only outside another candidate's hours, held through them (False), or held "
                     "exactly through another candidate's extra hours where the optimum sells below it by a plan "
                     "within "
                     "0.5% of that window's optimum (False; a heuristic that just stops selling there: not "
                     "determinable)",
    "degradation": "on a plan that keeps every rule: of the pool's costs and none at all, the one for which the plan "
                   "comes closest to that cost's optimum; the client's is True, another within 0.3% of its optimum "
                   "False, else not determinable",
    "works_end": "export above the amended limit on days between an earlier candidate end and the client's (False), "
                 "or the amended limit kept from the client's end until a later candidate or the week's end where "
                 "the optimum exports more (False)",
    "dso_day": "site export while discharging on the DSO's evening within the largest candidate limit (True), else "
               "False",
    "dso_limit": "on the right evening: export above the limit (False), or held exactly at a lower candidate in two "
                 "or more quarters while the optimum exports more (False)",
    "maintenance_outage": "the battery rests through the outage",
}
# Facts that were targets before this audit and are not now. They stay in requirements.md, where the client still
# answers them when asked.
REMOVED = [
    ("`start_end_soc` (the old bundle)", "split: the start (50%) is where last week's log ends, the same in every "
                                         "setting, so context; the end level is `end_soc` (exactly the drawn "
                                         "`end_soc`)"),
    ("`quarter_settlement`", "the data settles it: the solar forecast and last week's log are quarter-hourly, the "
                             "log's SOC steps are 0.25 h of its power, and an hourly price for four quarters is the "
                             "only reading of the files"),
    ("`dst_clock`", "the data settles it: the solar forecast has 668 rows and the price forecast 23 hours on 28 "
                    "March. The 668 rows stay a hard gate (`complete_plan`)"),
    ("`profit_scoring`", "what \"money\" means changes no plan: the solar farm's own income is the same for every "
                         "plan, export is capped by the agreement's own clipping, and the settlement prices are the "
                         "forecast (part 3)"),
    ("`grid_charging` in easy", "the agreement allows 20 MW of import with no window, which is the client's easy "
                                "answer: nothing to ask. The either/or rule (never charge and discharge in one "
                                "quarter) "
                                "is in the agreement's physics and never binds an optimum"),
    ("`evening_reserve` (the old bundle)", "split into `reserve_level` (exactly the drawn `reserve_pct`) and "
                                           "`reserve_hours` (exactly the drawn `reserve_window`)"),
    ("`dso_limit` (the old bundle)", "split into `dso_day` (exactly the drawn `dso_day`) and `dso_limit` (exactly the "
                                     "drawn `dso_mw`)"),
]


def _num(x, digits=3):
    return "–" if x is None else f"{x:.{digits}f}"


def _table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def _fact(text: str) -> str:
    text = re.sub(r"<!-- tier: ([a-z ]+) -->", lambda m: f"[{m.group(1)}] ", text).replace("*", "×")
    text = re.sub(r"<!-- /tier -->", " ", text)
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: f"*{m.group(1)}*", text).replace("|", "/").strip()


def _diag(s: dict) -> str:
    return "no" if not s["has_diagnostic"] else ("untested" if s["separates"] is None else
                                                "separates" if s["separates"] else "does not separate")


def _range(xs, digits=3):
    xs = [x for x in xs if x is not None]
    return "–" if not xs else _num(min(xs), digits) if min(xs) == max(xs) else f"{_num(min(xs), digits)}–{_num(max(xs), digits)}"


def _bending_policies() -> list[tuple[str, float, float]]:
    """(policy, the share of quality in its final score, its soft-rule penalty) for the shipped policies that let a
    business-policy rule bend (configs/policies/*.yaml)."""
    out = []
    for path in sorted((ROOT.parents[2] / "configs" / "policies").glob("*.yaml")):
        policy = yaml.safe_load(path.read_text(encoding="utf-8"))
        if (policy.get("rule_classes") or {}).get("business_policy") == "soft" and policy.get("exceptions") != "forbidden":
            weights = policy.get("weights") or {}
            out.append((path.stem, weights.get("quality", 0.0) / sum(weights.values()),
                        float(policy.get("soft_rule_penalty", 0.1))))
    return out


def _quality(c: NativeCase, plan, relaxed=frozenset()) -> float | None:
    with tempfile.TemporaryDirectory() as tmp:
        c.module._write_plan(c.world, Path(tmp), *plan)
        res = c.evaluate(Path(tmp), "en", relaxed=relaxed)
    return res["quality_score"] if res["validity_score"] == 1.0 else None


def _bend_rows(case: NativeCase, cap: float) -> list[list[str]]:
    """Per public medium and hard setting: what bending the evening reserve is worth (an approved exception, scored
    with the rule relaxed): the optimum without the reserve against the reference, in quality (uncapped), the
    client's planner without the reserve, and what the bend nets in the final score of a plan at quality 0.5 under
    each policy that allows it (the quality share / the cap x the gain it can still use, less the penalty)."""
    module, rows = case.module, []
    policies = _bending_policies()
    for tier in ("medium", "hard"):
        for seed in case.rule_seeds:
            c = case.at(tier, seed)
            r = module.rules_of(c.setting)
            hz = c.world.week
            rr = dataclasses.replace(r, reserve=None)
            ref, base = c.reference_objective, c.baseline_objective
            bent = module.simulate(c.world, rr, *module.optimum(hz, rr)[:2])[1]
            plan = module.simulate(c.world, rr, *module._planner(hz, rr))[1]
            gain = (bent - ref) / (ref - base)
            row = [c.setting.label, f"{100 * r.reserve / module.CAPACITY:g}% {r.res_from // 60:02d}-{r.res_to // 60:02d}",
                   f"{gain:+.3f}", f"{(plan - base) / (ref - base):.3f}"]
            for _, share, penalty in policies:
                net = share / cap * min(gain, cap - 0.5) - penalty
                row.append(f"{net:+.3f} ({'pays' if net > 0.005 else 'loses' if net < -0.005 else 'about even'})")
            rows.append(row)
    return rows


LITERAL_READINGS = {
    "as delivered": {},
    "84.6% all on charge": dict(eta_c=0.846, eta_d=1.0),
    "no end-of-week level": dict(soc_end=2.0),
    "the log's 10-90% window": dict(soc_min=4.0, soc_max=36.0),
    "the 21-89% the log runs in": dict(soc_min=8.4, soc_max=35.6),
    "the log's import window": dict(import_window=(0, 360)),
}


def _literal_rows(case: NativeCase) -> list[list[str]]:
    """Per public setting: the literal plan (LITERAL_RULES) and its next most natural readings, scored as delivered
    and with the bendable rule relaxed: the rules it breaks (invalid either way), or its quality."""
    module, rows = case.module, []
    bendable = frozenset(r["id"] for r in case.meta["rules"] if r["class"] == "business_policy")
    for c in case.settings():
        row = [c.setting.label]
        for _, change in LITERAL_READINGS.items():
            plan = module.optimum(c.world.week, dataclasses.replace(module.LITERAL_RULES, **change))[:2]
            with tempfile.TemporaryDirectory() as tmp:
                module._write_plan(c.world, Path(tmp), *plan)
                res = c.evaluate(Path(tmp), "en", relaxed=bendable)
            broken = sorted({v["rule"] for v in res["violations"]} - bendable)
            row.append(", ".join(f"`{b}`" for b in broken) if broken else f"valid, {res['quality_score']:.3f}")
        rows.append(row)
    return rows


def gt(case: NativeCase) -> str:
    audit = json.loads((ROOT / "dataset" / "audit.json").read_text(encoding="utf-8"))
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    targets = yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))
    spec = {t["id"]: t for t in targets}
    tiers = tier_order(audit["settings"])
    counts = {t: len(audit["settings"][t]) for t in tiers}
    th = audit["thresholds"]
    cap = float(meta.get("quality_cap") or 1.0)
    policies = _bending_policies()
    spans = [b["span"] for b in audit["bounds"] if b["span"] is not None]
    out = [
        f"# Ground truth: {case.id}", "",
        "The ground truth (GT) of a setting in five parts, with the reference as supporting evidence. Generated by "
        f"`gt_report.py` from `dataset/audit.json` (`fdebench2 audit-case`, public world seed {audit['world_seed']}): "
        f"{sum(counts.values())} settings, " + ", ".join(f"{t} {counts[t]}" for t in tiers) + " (each tier's public "
        "panel plus admissible parameter combinations). Damage is 1 − credit, credit = 0 for an invalid plan, else "
        "the quality score clipped to [0, 1]; a target bites in a setting when misreading it alone loses at least "
        f"{th['ablation_min_damage']:.2f} of the credit (for a drawn parameter: its least harmful wrong candidate).",
        "", "## 1. Client facts (targets)", "",
        "One row per target: the fact, the tiers where it is in force, how the audit misreads it (every target is one "
        "drawn parameter: the reference written for each other admissible candidate), the damage range over the "
        "settings where it is in force, the settings where it bites per tier (k/n) and whether its diagnostic "
        "(`enforced`, part 5) tells the reference from the misreading.", "",
    ]
    rows = []
    for t in target_summary(audit):
        tid = t["target"]
        s = spec[tid]
        how = f"the reference of each other candidate of `{s['param']}`"
        if "hook" in t["sources"]:
            how += "; " + SOC_HOOK
        rows.append([f"`{tid}`", _fact(s["text"]), ", ".join(t["tiers"]), how, _range([t["low"], t["high"]]),
                     ", ".join(f"{tier} {k}/{n}" for tier, (k, n) in t["per_tier"].items()), _diag(t)])
    out += _table(["target", "fact", "in force", "ablation", "damage", "bites k/n", "diagnostic"], rows)
    out += ["", "What the agent's view shows, and so what each fact's natural misreading is: the spec sheet's 84.6% "
            "round trip (split evenly, 92% each way) and its manufacturer window 5-95%; the agreement's 30 MW export "
            "and 20 MW import at any hour; and last week's log, made by the client's planner with last week's "
            "settings (10-90%, 92% each way, back to 50%, a 20% reserve 17:00-21:00, import 00:00-06:00, a 25 MW cap; "
            "the planner keeps 1% inside the limits and the reserve all day, so the log runs 21-89%). No candidate is"
            " the sheet's or the log's "
            "window or split, and every cap is below both documents': a plan read off the files breaks the warranty "
            "and the export limit in every setting. The end level, import window and reserve do have the log's value "
            "among their candidates; reading them off the log is a guess right one time in three, which the "
            "ablations price.", "",
            "**Grid import is a weak fact.** `grid_charging` bites in fewer than half of its settings, and the "
            "shortcut `solar_only` (never draw from the grid, every other fact right) stays open where it bites "
            "least: at the forecast prices a night charge pays for its losses and degradation only at 5 EUR/MWh or "
            "on cloudy days, and the free solar above the export limit fills the battery for the evening anyway. "
            "There the best plan imports little or nothing and no window changes it; all six medium and hard settings "
            "of round 2026-11 (degradation 15 or 25 EUR/MWh) are such settings (`solar_only` 0.61-1.00). The natural "
            "misreading of the agreement, import at any hour, does break the rule in every medium and hard setting "
            "probed. Closing the shortcut trades the degradation fact away: with a morning peak 30 EUR/MWh dearer "
            "and nights 10 EUR/MWh cheaper in the price data it is still open in 4 of the 30 medium and hard "
            "settings while degradation bites in 21 instead of 30 (a peak 60 EUR/MWh dearer: open in 5, degradation "
            "biting in 15). It is not a way around the work: it needs every other fact and is the safe answer to "
            "the one question it skips, which matters only where a night charge pays. `grid_charging` stays a "
            "target because the files contradict the rule (the agreement allows import at any hour) and a plan "
            "that follows them is invalid. `validate.OPEN_AUDIT_FINDINGS` lists the shortcut with this reason.", "",
            "Facts that are no longer targets (they stay in requirements.md, and the client still answers them when "
            "asked):", ""]
    out += [f"- {name}: {why}" for name, why in REMOVED]
    out += ["", "## 2. Validity checks (hard gates)", "",
            "A plan that breaks any of these is invalid and earns no credit. A file that cannot be read (no "
            "`dispatch.csv`, no charge or discharge column, a number that is not one, a quarter given twice) is "
            "fatal. The format is otherwise open: the time column under any common name (else the first column), the "
            "charge and discharge columns by a word in any of the five languages, comma or semicolon separated with "
            "decimal commas, and timestamps with seconds, a `T`, a one-digit hour, a day-first (or month-first) date "
            "or "
            "a UTC offset (converted to local time).", ""]
    rows = [[f"`{r['id']}`", r["class"], ", ".join(r.get("tiers", tiers)), RULE_WHY[r["id"]]] for r in meta["rules"]]
    out += _table(["rule", "class", "tiers", "why it is a hard gate"], rows)
    out += ["", "**The literal plan.** `literal_solution` is the request read from the files alone: the optimum on "
            "the forecast with the sheet's 5-95% and 92% each way, the agreement's 30 MW and import at any hour, back "
            "at 50% on Sunday night, no reserve, no wear cost and no notice. Its next most natural readings change "
            "one of those. Every one is invalid in every public setting, as delivered and with the bendable reserve "
            "relaxed (the rules it still breaks):", ""]
    out += _table(["setting"] + list(LITERAL_READINGS), _literal_rows(case))
    out += ["", "**The bendable reserve.** `evening_reserve` is the one business-policy rule. With an approved "
            "exception it is switched off, and the policy takes its soft-rule penalty off the final score ("
            + ", ".join(f"{penalty:g} under `{name}`" for name, _, penalty in policies) + "), in which quality is one "
            "component (" + ", ".join(f"{share:.0%} under `{name}`" for name, share, _ in policies)
            + f", full credit at the quality cap {cap:g}). The table gives, per public setting, the bend's worth in "
            "quality (the optimum without the reserve against the reference), the client's planner without the "
            "reserve, and what the bend nets for a plan at quality 0.5 (the quality share / the cap x the gain it "
            "can still use before the cap − the penalty). A plan at the reference's level gains nothing: the cap is "
            "the best plan that keeps the rule. Where the reserve does not bind (15% from 16:00 to 20:00, when "
            "the battery is full for the evening peak anyway) the bend loses its penalty; elsewhere it pays.", ""]
    out += _table(["setting", "reserve", "gain of the optimum", "planner without reserve"]
                  + [f"net at 0.5, `{name}`" for name, _, _ in policies], _bend_rows(case, cap))
    out += ["", "**Shortcuts.** The plans a lazy or gaming engineer would hand in; each is invalid or scores at most "
            f"{th['shortcut_max_quality']:.1f} in every measured setting, except `solar_only` (above) and "
            "`planner_two_changes` (below). The literal plan with one rule it breaks kept stays invalid, because the "
            "window or split and the export limit are both wrong in every setting. Copying the client's planner and "
            "changing one thing (the night fill as before the cut, no buffer, selling the reserve after its hours, "
            "holding the reserve only through its hours) stays at or below 0.46. Dropping its two most costly habits "
            "together, the 1% buffer and the reserve kept all day, reaches 0.57: above 0.5 in 3 of the 30 medium "
            "and hard settings (2 on each of world seeds 1-3, none in round 2026-11), where the morning sale into the "
            "reserve pays "
            "most, and 0.80 with selling the reserve after its hours as a third change. Such a plan needs every "
            "client fact and the planner rebuilt from its description: it is the client's way improved by applying "
            "the rules as stated, not a way around them. A planner that dips into the reserve in the morning on its "
            "own (trusting the midday refill, as its night fill does) breaks the reserve on outage or cloudy days (2 "
            "of 234 sampled medium and hard settings, both hard), so the all-day reserve stays the client's habit and "
            "the shortcut is listed "
            "in `validate.OPEN_AUDIT_FINDINGS`. Doing the minimum (storing only the clipped solar) or repeating one "
            "day's plan all week earns nothing.", ""]
    out += _table(["shortcut", "what it does", "closed", "best quality where valid"],
                  [[f"`{s['name']}`", s["description"], f"{s['closed']}/{s['settings']}", _num(s["best_quality"])]
                   for s in shortcut_summary(audit)])
    out += ["", "## 3. Objective (higher is better)", "",
            "The battery's expected profit in EUR over the week: every quarter settled at its hour's forecast price "
            "(the client's best estimate; the actual prices differ, up or down). Per quarter, site net = solar + "
            "discharge − charge; export earns price x 0.25 x min(net, the quarter's export limit), import costs "
            "price x 0.25 x the import; less what the solar farm alone would have earned (price x 0.25 x min(solar, "
            "export limit)) and, in medium and hard, the degradation cost per MWh of charge plus discharge. The "
            "export limit is the amended cap, 30 MW from the works' end and the DSO's limit in its hours.", "",
            "**The zero point** is the client's own planner (`baseline_solution`, requirements.md \"How we run the "
            "battery today\"), run with the setting's values: two cycles a day by price rank, the night fill leaving "
            "room for the midday solar, 1% (0.4 MWh) kept inside the warranty window and above the reserve, and no "
            "sale below the reserve until its hours are over (the morning sale included). It made "
            "last week's log (with last week's settings). The quality scale (reference − planner) / reference is "
            f"{_range(spans)} wide over the audit's settings (5% is the validator's floor).", "",
            "**Uncertainty.** Until the audit the plan was settled at one draw of the actual prices (the forecast plus "
            "a daily bias and hourly noise). For a fixed plan the profit is linear in the price and the noise has mean "
            "zero, so the forecast optimum was already the best plan in expectation and the draw added only luck: "
            "on the public settings of world seeds 20270322 and 1-3 the same plan's profit moved by up to 14% (the "
            "client's planner) and 7% (the optimum) between the forecast and the draw, on a quality scale 7-29% wide. "
            "The profit at the week's actual prices is still reported as a metric (`profit_at_actual_prices_eur`).",
            "",
            "## 4. Reference and bounds", "",
            "- **Reference** (`reference_solution`): the plan of greatest expected profit under the setting's rules, "
            "exactly (`optimum`). The problem is a linear program with one state, the stored energy; a quarter's "
            "profit is a concave piecewise-linear function of the energy it moves, so the best profit still to come "
            "is one too, and a backward pass merges each quarter's segments into it (a sup-convolution) and cuts it "
            "at the SOC bounds. Pure Python, about 0.05 s; it matches scipy/HiGHS on every public setting.",
            "- **Baseline** (quality 0, `baseline_solution`): the client's planner (part 3).",
            "- **Best known** (`best_known_solution`): the reference itself, which no valid plan beats.",
            "- **Bound** (`objective_bound`, proven): the linear program's optimum before rounding. It allows every "
            "plan the rules allow and more (charging and discharging in one quarter), so no valid plan earns more; "
            "the reference's 4-decimal plan is within 0.1 EUR of it.", ""]
    known = [b["best_known_quality"] for b in audit["bounds"] if b["best_known_quality"] is not None]
    gaps = [b["gap_to_bound"] for b in audit["bounds"] if b["gap_to_bound"] is not None]
    out += [f"- **quality_cap** = {meta.get('quality_cap')}: the best known quality is {_range(known)} (median "
            f"{median(known):.3f}) and the gap to the bound {_range(gaps, 6)}. Before the audit the reference was a "
            "greedy two-cycle rule (the planner with two refinements) and a forecast LP reached 1.03-1.30 of it.", ""]
    out += _table(["setting", "reference", "baseline", "span", "best known", "its quality", "bound", "bound quality",
                   "gap ref–bound"],
                  [[b["setting"], _num(b["reference"], 2), _num(b["baseline"], 2), _num(b["span"]),
                    _num(b["best_known"], 2), _num(b["best_known_quality"]), _num(b["bound"], 2),
                    _num(b["bound_quality"]), _num(b["gap_to_bound"], 6)] for b in audit["bounds"]])
    out += ["", "**Value of asking** (the GT's claim that the client must be asked): per tier, the best plan that "
            "never asks against the reference of each setting. `never asks, knows the fixed facts` is the best of "
            "the measured settings' references and the baseline scored over the tier (each reference is a full "
            "guess of the drawn values, picked with hindsight); `never asks (robust)` is `robust_solution`: one "
            "linear program (scipy) over the tier's pools, valid under every combination: the SOC tracked under "
            "every candidate split and kept inside every candidate window and above every candidate reserve, the "
            "highest end level, the lowest export limit until every candidate's works have ended, the lowest DSO "
            "limit on every candidate day, rest through every candidate outage, import only where every candidate "
            "window allows; charging priced at its expected cost over the candidate limits, degradation at the "
            "pool's mean. It is a genuine attempt, checked against every plan that plans for a subset of each "
            "parameter's candidates (a single one is a guess, valid only where it is right; degradation at any value "
            "of the pool). In easy all 189 distinct such plans were scored over all 81 combinations: the full hedge "
            "earns the most, 0.186 (0.109 for the best single guessed setting), so asking is worth 0.81 over the "
            "whole pool. On the audit's 15 easy settings the hedge earns 0.089; planning for a 15-18 MW cap would earn "
            "0.19 there but 0.154 over all 81, so the 0.91 below is the luck of the sample, not a weak solver. In "
            "medium and hard a coordinate search over the same choices from four starts, on 150 sampled "
            "combinations, found at most 0.075 against the hedge's 0.061 in medium (0.000 on the audit's settings) "
            "and 0.010 against 0.000 in hard; no single change earns more than 0.049 (medium) or 0.011 (hard) on the "
            "audit's settings. Reading the files instead (the sheet's 5-95% and even split, the log's 10-90% or the "
            "21-89% it runs in, the agreement's 30 MW) is invalid in every setting. Without asking, no plan found "
            "beats the client's own planner by much: the hedges cost more than the optimizer gains.",
            ""]
    out += _table(["tier", "never asks, knows the fixed facts", "value of the parameters", "never asks (robust)",
                   "value of asking"],
                  [[tier, _num(v["never_asks_params"]), _num(v["voi_params"]), _num(v["never_asks"]), _num(v["voi"])]
                   for tier, v in ((t, audit["voi"][t]) for t in tier_order(audit["voi"]))])
    out += ["", "## 5. Diagnostic cases", "",
            "`diagnose()` reads each fact from the plan's own numbers (its SOC path under each candidate split, site "
            "export while discharging, grid draws, the SOC in each candidate's reserve hours, its throughput) "
            "against the facts, the setting's optimum and the other candidates' optima. A broken limit that another "
            "candidate explains is that candidate's; a stricter candidate the plan sits exactly on while the optimum "
            "uses the room is a misreading too.", ""]
    ref_fail = {tid: [e["label"] for tier in tiers for e in audit["settings"][tier]
                      if not e.get("skipped") and e["reference_enforced"].get(tid) is False] for tid in spec}
    rows = []
    for t in target_summary(audit):
        tid = t["target"]
        bad = sorted(set(t["undiagnosed"]) | set(ref_fail[tid]))
        rows.append([f"`{tid}`", DIAGNOSTIC[tid], _diag(t), ", ".join(bad) or "–"])
    out += _table(["target", "what tells a correct plan from the misreading", "result", "settings where it fails"],
                  rows)
    out += ["", "**Reliability on other deliverables.** Per target, the settings where the diagnostic calls a "
            "deliverable not enforced, of those where it gives a verdict: the best known solution (valid and built "
            "with every fact, so each False would be a false negative), the ablations of the target that also flag "
            "another target (of the settings where the ablation bites), and the baseline (each setting's own) and "
            "`robust_solution` (its tier's), which hedge or keep margins, so a False there may be right. Probed beyond "
            "the audit on the 45 settings of the public world: five correct-but-different plans (the optimum with "
            "0.4 MWh margins inside the window and above the reserve, the same linear program built from the agent's "
            "files and solved by HiGHS, the client's planner without its buffer, the planner without its buffer and "
            "its all-day reserve, the optimum floored to two decimals where that stays valid) got no False on a valid "
            "plan in 1,730 verdicts. Before the check the planner without its buffer got 10 (on `reserve_hours` and "
            "`soc_window`: a reserve held all day looks like longer reserve hours or a stricter floor); those "
            "readings now need the plan to earn within 0.5% of the misreading's optimum, or a window bound the "
            "reserve does not explain. The optimum rounded to two or three decimals is valid everywhere; floored "
            "to two decimals it breaks the window in 34 of 45 settings (the floored discharges add up). Of the "
            "misreadings, four were "
            "caught on their own target in all 45 settings only after the check (before it the first three were "
            "blamed on the window and the end level in every setting, the fourth caught only where it broke the "
            "window): the sheet's 84.6% all on charge, all on discharge, the client's discharge efficiency "
            "multiplied instead of divided, and the 21-89% the log runs in kept as the window. The export limit "
            "applied to the battery alone is caught in 42 of 45; the works' end read a day late in 8 of 15 (it "
            "bites in 7). Three that land between candidates are caught only where they hit one: degradation "
            "charged on discharge only 8 of 30 (it bites in 17), the reserve as a share of the warranty window 4 of "
            "30 (22), the end level as a share of the window 8 of 45 (14); a plan alone cannot tell them from a "
            "margin. The file shapes (other column names in five languages, semicolons with decimal commas, UTC "
            "offsets, the skipped hour as rows at rest, day-first dates, one-digit hours) score exactly as the "
            "reference.", ""]
    negatives, cross, profile = false_negatives(audit), cross_flag_summary(audit), audit.get("diagnostic_profile") or {}

    def cell(false, n):
        return f"{false}/{n}" if n else "–"
    rows = []
    for tid in spec:
        fn, cf = negatives.get(tid), cross.get(tid)
        flags = cell(len(cf["flagged"]), cf["biting"]) if cf else "–"
        if cf and cf["others"]:
            flags += " (" + ", ".join(f"`{u}`" for u in cf["others"]) + ")"
        rows.append([f"`{tid}`", cell(len(fn["false"]), fn["diagnosed"]) if fn else "–", flags]
                    + [cell(p[tid]["false"], p[tid]["diagnosed"]) if tid in (p := profile.get(name) or {}) else "–"
                       for name in ("baseline", "robust_solution")])
    out += _table(["target", "best known", "ablation flags another target", "baseline", "robust_solution"], rows)
    errors = (audit.get("diagnose_errors") or {}).get("count", 0)
    out += ["", f"`diagnose()` raised in {errors} evaluation(s) of the audit.", "", "## Findings of the audit", ""]
    found = summarize(findings(audit, meta.get("quality_cap")))
    out += [f"- {x}" for x in found] or ["- none: every check passes"]
    return "\n".join(out) + "\n"


# The question an engineer would naturally ask, and how to find the passages of requirements.md the client answers
# from: each spec is a list of tokens that must all occur in a passage of en (a bullet with its indented lines, or a
# paragraph; a token starting with ^ must start it), "first" takes the first such passage, "all" every one. Every
# locale's requirements.md has the same passages in the same order, so the other locales quote the same passages.
QUESTIONS = {
    "efficiency": ("The sheet gives an 84.6% round trip: how does it split between charging and discharging?",
                   [(["{{eta_charge_pct}}% on charge"], "first")]),
    "soc_window": ("Which state of charge may the battery use? The sheet says 5-95%.",
                   [(["our warranty is narrower"], "first")]),
    "end_soc": ("Where should the battery be at the end of the week?", [(["must end the week"], "first")]),
    "export_cap": ("Is the agreement's 30 MW export limit still current?", [(["is out of date on one point"], "first")]),
    "grid_charging": ("When may the site draw power from the grid to charge the battery?",
                      [(["Drawing power from the grid", "{{import_from}}"], "first")]),
    "reserve_level": ("Do you keep part of the charge in reserve? How much?",
                      [(["for emergencies at every moment"], "first")]),
    "reserve_hours": ("In which hours does the reserve apply?", [(["for emergencies at every moment"], "first")]),
    "degradation": ("Should battery wear count as a cost in the plan?",
                    [(["costs us EUR {{degradation}}"], "first")]),
    "works_end": ("Will the export limit change during the week?",
                  [(["The substation contractor finishes early"], "first")]),
    "dso_day": ("Has the grid operator announced any limits for next week?",
                [(["The DSO has planned works"], "first")]),
    "dso_limit": ("How much may the site export during the DSO's works?", [(["The DSO has planned works"], "first")]),
    "maintenance_outage": ("Is the battery out of service at any time next week?",
                           [(["Inverter maintenance"], "first")]),
}


def _passages(text: str) -> list[str]:
    """Bullets (each with its indented continuation lines) and paragraphs, each with the opening setting markers
    (tier, when) that stand right before it, so the reviewer sees in which settings it is said."""
    out, cur, markers = [], [], []
    for line in text.splitlines():
        starts = line.startswith("- ") or (line and not line.startswith(" ") and not line.startswith("<!--"))
        if starts:
            if cur:
                out.append("\n".join(cur))
            cur, markers = markers + [line], []
        elif line.startswith("  ") and cur:
            cur.append(line)
        else:
            if cur:
                out.append("\n".join(cur))
            cur = []
            if line.startswith("<!-- ") and not line.startswith("<!-- /"):
                markers.append(line)
            elif line.startswith("<!-- /"):
                markers = []
    if cur:
        out.append("\n".join(cur))
    return out


def _body(p: str) -> str:
    return "\n".join(line for line in p.splitlines() if not re.fullmatch(r"<!-- [^>]* -->", line))


MONTHS = r"March|June|marzo|junio"


def _tokens_of(text: str, files: dict[str, str]) -> list[str]:
    """The tokens a translation must keep: parameters, dates, clock times, numbers of 10 and more or with a decimal
    (a month or day number written with its month is left out), and what stands in backticks (a field name as it is;
    a localized file name as the file it stands for)."""
    out = set(re.findall(r"\{\{\w+\}\}", text))
    for code in re.findall(r"`([^`]+)`", text):
        out.add(f"`file:{files[code]}`" if code in files else f"`{code}`")
    t = re.sub(r"`[^`]+`|\{\{\w+\}\}", " ", text)
    out |= set(re.findall(r"\d{4}-\d{2}-\d{2}", t)) | set(re.findall(r"\d{1,2}:\d{2}", t))
    t = re.sub(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}", " ", t)
    t = re.sub(r"\d{1,2}月\d{1,2}日|\d{1,2}월 ?\d{1,2}일|\d{1,2} (?:de )?(?:" + MONTHS + r")|\d{1,2}일|\d{1,2}日", " ", t)
    t = re.sub(r"\d{1,2} ?[月월]", " ", t)
    # a quarter-hour, which some locales write as 15 minutes
    t = re.sub(r"15[- ]minutes?|15 ?분|15 ?分|15 minutos", " ", t)
    t = re.sub(r"(\d),(\d{1,2})(?!\d)", r"\1.\2", t)
    out |= {n for n in re.findall(r"(?<![0-9A-Za-z_.])\d+(?:\.\d+)?(?![0-9A-Za-z_])", t) if "." in n or float(n) >= 10}
    return sorted(out)


def client_review(case: NativeCase) -> str:
    module = case.module
    texts = {lang: (ROOT / "locales" / lang / "requirements.md").read_text(encoding="utf-8") for lang in LANGS}
    passages = {lang: _passages(texts[lang]) for lang in LANGS}
    lengths = {lang: len(p) for lang, p in passages.items()}
    if len(set(lengths.values())) != 1:
        raise SystemExit(f"the locales' requirements.md have different passages: {lengths}")
    targets = yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))
    files = {lang: {names[lang]: key for key, names in module.FILES.items()} for lang in LANGS}

    def matches(p: str, toks: list) -> bool:
        return all(_body(p).startswith(t[1:]) if t.startswith("^") else t in p for t in toks)

    def indices(specs) -> list[int]:
        out = []
        for toks, which in specs:
            hits = [i for i, p in enumerate(passages["en"]) if matches(p, toks)]
            out += hits[:1] if which == "first" else hits
        return list(dict.fromkeys(out))

    out = ["# Client answers: human review", "",
           "The simulated client answers only from `locales/<lang>/requirements.md` (plus event facts; this case has "
           "none). For every target: the question an engineer would naturally ask, the passages each locale answers "
           "from (quoted as written, with setting markers and parameters; a parameter is worded per locale by "
           "`params.<name>.labels` in case.yaml or by `derive_params` in case.py), a machine pre-check and an empty "
           "verdict for a human reviewer. Generated by `gt_report.py`.", "",
           "Pre-check: (1) the passages are found in en (every locale's requirements.md has the same passages in the "
           "same order, so the others quote the same ones); (2) the same parameters, dates, clock times, numbers "
           "and names in backticks in every locale (a localized file name compared as the file it stands for); (3) "
           "the other targets that share a passage, i.e. what the passage would answer beyond the question (the "
           "client may state them together when asked).", "",
           "**Status: awaiting human review.** No passage below has been reviewed by a person yet.", ""]
    found = {t["id"]: indices(QUESTIONS[t["id"]][1]) for t in targets}
    for t in targets:
        tid = t["id"]
        idx = found[tid]
        scope = ", ".join(t["tiers"]) if t.get("tiers") else ""
        out += [f"## `{tid}`" + (f" ({scope})" if scope else ""), "",
                f"**Question.** {QUESTIONS[tid][0]}", "", f"**Target (en).** {t['text']}", ""]
        for lang in LANGS:
            out += [f"**{lang}:**", ""]
            for i in idx or [None]:
                out += ["> " + line for line in (passages[lang][i] if i is not None else "(not found)").splitlines()]
                out.append(">")
            out.pop()
            out.append("")
        checks = ["passages found (" + str(len(idx)) + ")" if idx else "NOT FOUND in en"]
        toks = {lang: _tokens_of("\n".join(passages[lang][i] for i in idx), files[lang]) for lang in LANGS}
        ref = toks["en"]
        diff = {lang: (sorted(set(ref) - set(n)), sorted(set(n) - set(ref))) for lang, n in toks.items()
                if set(n) != set(ref)}
        checks.append("tokens differ from en: " + "; ".join(f"{lang} lacks {a or '–'}, adds {b or '–'}"
                                                             for lang, (a, b) in diff.items()) if diff else
                      "same parameters, dates, times, numbers and names in all five locales: " + (", ".join(ref) or
                                                                                                  "none"))
        same = [o for o, f in found.items() if o != tid and set(f) & set(idx)]
        checks.append("the passages also state: " + (", ".join(f"`{o}`" for o in same) if same else
                                                       "nothing else that is a target"))
        out += ["**Machine pre-check.**", ""] + [f"- {c}" for c in checks] + ["", "Reviewer verdict:", ""]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    which = sys.argv[1:] or ["gt", "client"]      # "client" needs no audit, "gt" reads dataset/audit.json
    the_case = NativeCase(ROOT)
    if "client" in which:
        (ROOT / "CLIENT_REVIEW.md").write_text(client_review(the_case), encoding="utf-8")
        print("wrote", ROOT / "CLIENT_REVIEW.md")
    if "gt" in which:
        (ROOT / "GT.md").write_text(gt(the_case), encoding="utf-8")
        print("wrote", ROOT / "GT.md")
