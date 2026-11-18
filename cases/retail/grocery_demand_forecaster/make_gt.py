"""Writes GT.md, the ground truth of retail/grocery_demand_forecaster in five parts, with every table generated from
dataset/audit.json (run `fdebench2 audit-case` first); the bending table is computed from case.py on the audit's own
settings: python cases/retail/grocery_demand_forecaster/make_gt.py
"""

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

# How each fact is misread (case.py ablations(); a param: target is read as another candidate of its parameter).
MISREAD = {
    "order_quantity": "the number read as a sales forecast to which the stores add their own cushion: the expected "
                      "demand handed in",
    "stockout_censoring": "stockout days read as normal sales and returns netted: the history as the till recorded it",
    "base_forecast": "the promotion plan read as part of the order (the file is attached), at the historical lift",
    "promo_plan": "the promotions read as somebody else's top-up: the order without them",
    "manager_note": "the store manager's e-mail followed: 20% on top for Central Plaza",
    "submission_format": "rows only where the store trades: S4's Sundays left out",
}
# What score()'s diagnostic reads in the plan (case.py diagnostics).
DIAGNOSTIC = {
    "order_quantity": "the share of ordinary store × item days whose demand the order covers: clearly above what the "
                      "expected demand, ordered as it is, covers",
    "lost_sale_cost": "the same share, against the share the best plan covers at each candidate ratio: not enforced "
                      "when it sits at another candidate's, within a quarter of the way from there to the client's "
                      "(not told for a plan that hands in the expected demand: no cushion to read). It reads the "
                      "cushion the plan ends up with, not the ratio its author had in mind",
    "stockout_censoring": "store by store and item by item, how far the orders stand above expected demand, set "
                          "against the item's stockout rate once its category, the store and the cell's variability "
                          "are accounted for: reading stockout days as sales lowers the orders most for the items "
                          "that run out most (enforced under half of that pattern)",
    "base_forecast": "promotion days against the same weekday of the other week (slow core items left out: a "
                     "display minimum flattens them): under half of what the best plan adds for a promotion at the "
                     "historical lift",
    "promo_plan": "the same comparison: at least one category of the promotions in force carries half the historical "
                  "lift or more",
    "promo_flyer": "the lift the promotion days carry, as a multiple of the historical lift: nearest to the flyer's "
                   "multiple among the candidates' and not past the largest one by more than half a step (not told "
                   "when stockout days are read as sales, which understates the lift itself)",
    "promo_revision": "the cancelled category's promotion days carry under a quarter of the historical lift, and no "
                      "category that still runs was dropped in its place (not told for a plan without any promotion)",
    "one_off_holiday": "the holiday against the same weekday of the other week: half the best plan's holiday lift or "
                       "more, overall and in bakery and in beverages, the categories the client names",
    "min_display": "no core order under the minimum on an open day, and the slow core items (basil, aged cheese) not "
                   "held flat at a higher candidate",
    "manager_note": "Central Plaza's orders against the other stores', each against its best plan: under half of the "
                    "20% the note asks for",
    "submission_format": "every store × item × date exactly once",
}
# Why each rule is a hard gate.
WHY = {
    "complete_grid": "the ordering system loads one number per store, item and day: a missing row is a product nobody "
                     "orders. The mandatory output: S4's Sundays and bread rolls have rows too, also where they are "
                     "not judged",
    "non_negative": "an order cannot be negative",
    "closed_day_zero": "nobody takes a delivery at a closed store",
    "min_display_stock": "the client's habit for its core shelves (business policy): a hard gate under the baseline "
                         "policy, bendable with an approved exception under the others. It is a rule on the order, "
                         "the decision; no forecast is invalid for being low",
}


WHEN = re.compile(r"<!-- when: \w+=([^>]*?) -->(.*?)<!-- /when -->")


def _fact(text: str) -> str:
    """A target's text for a table cell: each when-block as [values: text], no pipes."""
    return WHEN.sub(lambda m: f"[{m.group(1)}: {m.group(2).strip()}] ", text).strip().replace("|", "/")


def _num(x, d=3):
    return "–" if x is None else f"{x:.{d}f}"


def _range(xs, d=2):
    """min–max of xs to d decimals (one number when they round the same; never a negative zero)."""
    if not xs:
        return "–"
    low, high = (_num(round(x, d) + 0.0, d) for x in (min(xs), max(xs)))
    return low if low == high else f"{low}–{high}"


def _table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def _bending(audit: dict) -> list[list[str]]:
    """Per display minimum and cost ratio, over the audit's settings: what the reference gains when it drops the
    minimum under an approved exception (scored with the rule relaxed), and what the best plan then reaches."""
    case = NativeCase(ROOT)
    m = case.module
    bend = frozenset({"min_display_stock"})
    rows: dict[tuple, dict] = {}
    for tier in tier_order(audit["settings"]):
        first = case.at(tier, case.rule_seeds[0])
        for entry in audit["settings"][tier]:
            if entry.get("skipped"):
                continue
            c = first.with_params(**entry["params"])
            rules = m.rules_of(c.setting)
            free = dataclasses.replace(rules, floor=0.0)
            out = {}
            for name, plan in (("reference", m._reference(c.world, rules, floor=0.0)), ("best", m._best(c.world, free))):
                with tempfile.TemporaryDirectory() as tmp:
                    m._write(Path(tmp), plan)
                    res = c.evaluate(Path(tmp), "en", relaxed=bend)
                out[name] = res["quality_score"]
            key = (int(rules.floor), int(rules.lost_sale))
            row = rows.setdefault(key, {"n": 0, "reference": [], "best": []})
            row["n"] += 1
            row["reference"].append(out["reference"] - 1.0)
            row["best"].append(out["best"])
    return [[str(floor), str(ratio), str(r["n"]), _range(r["reference"]), _range(r["best"])]
            for (floor, ratio), r in sorted(rows.items())]


def main() -> None:
    audit = json.loads((ROOT / "dataset" / "audit.json").read_text(encoding="utf-8"))
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    targets = {t["id"]: t for t in yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))}
    tiers = tier_order(audit["settings"])
    n_settings = {t: len(audit["settings"][t]) for t in tiers}
    out = [
        "# Ground truth — retail/grocery_demand_forecaster",
        "",
        "The ground truth of every setting in five parts: the client facts the agent must learn, the validity checks, "
        "the objective, the reference with its bounds, and the diagnostic cases. Every table is generated from "
        "`dataset/audit.json` by `make_gt.py` (world seed "
        f"{audit['world_seed']}; per tier the public panel and {audit['thresholds']['combos']} admissible "
        "combinations of the tier's candidates: " + ", ".join(f"{t} {n_settings[t]}" for t in tiers) + " settings). "
        "Credit is 0 for an invalid deliverable, else quality clipped to [0, 1]; damage = 1 − credit. A fact bites "
        f"in a setting when misreading it loses at least {audit['thresholds']['ablation_min_damage']:g} of credit "
        "(for a parameter: the least harmful other candidate, an agent that guesses wrong but sensibly).",
        "",
        "This is the benchmark's forecasting case, and its ground truth follows the rules for such cases "
        "(docs/DIRECTION.md, section 5): no forecast is \"the\" answer, so nothing is compared with a reference "
        "forecast or with one realized November. The deliverable is the decision the client takes from the forecast, "
        "an order per store, item and day; it is scored by its expected cost under the demand distribution the world "
        "itself draws from; the client's costs choose the loss; and the rules are rules on the order.",
        "",
        "## 1. Client facts",
        "",
        "One row per target (`locales/en/targets.yaml`). *Ablated as*: a parameter is read as each other candidate "
        "of its tier (the reference of that candidate, scored here); any other fact as the reference with its most "
        "natural misreading of the agent's own view. *Damage*: min–max over the settings where it is in force (best "
        "guess for a parameter).",
        "",
    ]
    rows = []
    for t in target_summary(audit):
        tid = t["target"]
        spec = targets[tid]
        how = (f"another candidate of `{spec['param']}`" if spec.get("param") else MISREAD.get(tid, "?"))
        diag = "no" if not t["has_diagnostic"] else ("separates" if t["separates"] else
                                                      "untested" if t["separates"] is None else "does not separate")
        per = ", ".join(f"{tier} {k}/{n}" for tier, (k, n) in t["per_tier"].items())
        low, high = t["low"], t["high"]
        rows.append([f"`{tid}`", _fact(spec["text"]), ", ".join(t["tiers"]), how,
                     _num(low) if low == high else f"{_num(low)}–{_num(high)}", per, diag])
    out += _table(["target", "fact", "in force", "ablated as", "damage", "bites", "diagnostic"], rows)
    out += ["", "Facts the client states that are no longer targets (they stay in requirements.md as context, and the "
            "client still answers them when asked):", "",
            "- **Returns** (the rows with negative units are not demand): netting them moves the reference by less "
            "than 0.003 of the scale (1,255 return rows, 2,097 units against 1,943,585 sold). The reference leaves "
            "them out, and the `stockout_censoring` ablation nets them, as a reader of the till record would.",
            "- **S4's Sunday closure**: the data settles it (the history has no Sunday row for S4), and the natural "
            "reading is the right one. It stays a rule (`closed_day_zero`); what the data does not settle, that the "
            "closed days still need their rows, is in `submission_format`.",
            "- **Bread rolls' unit change** (hard): the data settles it too (`items.csv` says pack of 6 and the "
            "history drops sixfold on 1 June 2026). Taking the history as recorded costs the reference 0.09 to 0.21 "
            "in hard, so it is dropped because the data answers it, not for its weight. Bread rolls are still "
            "judged in hard only.",
            "- **How the plan is judged**: the first version's `wape_metric` bundled the error weight with what the "
            "actuals were. The weight became the business fact `lost_sale_cost`; the actuals are no longer a choice "
            "(an order has to cover demand, so `stockout_censoring` is in force in every tier).",
            "- **How the stores order today** (the managers' habit and its cushion): context for the client's own "
            "way, which is the zero of the quality scale.",
            "", "## 2. Validity checks", "",
            "Every rule of case.yaml is a hard gate (`physical` and `contractual` never bend; `business_policy` bends "
            "only through the company policy's exception path). All four are rules on the order quantity, the "
            "decision the client takes from the forecast: a forecast is never invalid for being low, since the file "
            "is the order and a low order is only costly. A file that cannot be read (no `forecast.csv`, no quantity "
            "column, an unknown store or item, a date outside the horizon, a quantity that is not a number) is "
            "fatal. The header decides nothing, because the request names no format and the stores order the number "
            "they are given: the quantity is read from `order_qty`, else from a `forecast` column, else from the "
            "file's one other column of numbers, and the key columns may carry the names the client's own data "
            "gives them in any of the five languages.", ""]
    rows = [[f"`{r['id']}`", r["class"], ", ".join(r.get("tiers", tiers)), WHY[r["id"]]] for r in meta["rules"]]
    out += _table(["rule", "class", "tiers", "why it is a hard gate"], rows)
    out += ["", "**Bending the display minimum.** What an approved exception is worth: the reference with the minimum "
            "dropped (every core item at its own cost-minimizing order), scored with the rule relaxed, against the "
            "reference that keeps it; and the quality of the best plan without the minimum. Over the audit's "
            "settings, by drawn minimum and cost ratio:", ""]
    out += _table(["display minimum", "a missed sale costs", "settings", "gain of the reference when it bends",
                   "best plan without the minimum (quality)"], _bending(audit))
    cap = float(meta.get("quality_cap"))
    out += ["", "A bent rule costs a policy's penalty (0.05 under the startup policy, 0.10 under the enterprise one) "
            "and quality weighs 0.6 there, so a gain g pays when 0.6 × g / quality_cap exceeds the penalty: g above "
            f"{0.05 * cap / 0.6:.2f} and {0.10 * cap / 0.6:.2f}. The bend therefore pays under both policies where "
            "the minimum is 12 and a missed sale costs 5 (the minimum forces eight or nine units a day of items that "
            "sell three), under the startup policy where it is 12 and a missed sale costs 12 or 30 (under the "
            "enterprise policy only in the settings at the top of the range at 12), and loses with a minimum of 4 "
            "or 6, where the cost-minimizing order is already at or near the minimum. This holds for "
            f"a plan with room under `quality_cap` {meta.get('quality_cap')}: a plan at the reference's level can "
            f"gain at most {cap - 1:.2f} of quality credit from any bend, less than "
            "either penalty, because the cap is the best plan that keeps the rule.",
            "", "## 3. Objective", "",
            "objective = the mean over the five stores of (Σ over the store's judged items and days of the expected "
            "units left over + `lost_sale_cost` × the expected units short) ÷ (Σ of the expected demand); minimize.",
            "",
            "- **The decision picks the loss.** The stores order exactly the number in the file, so a unit too many "
            "is a unit left over at closing (written off or cleared at a loss: one unit's worth) and a unit too few "
            "is a missed sale, which costs the client `lost_sale_cost` times as much (5, 12 or 30: the margin, and "
            "customers who go elsewhere). The same forecast is a good order under one ratio and a poor one under "
            "another, for a reason the client can explain.",
            "- **Expected loss, not one draw.** A day's demand in a cell is the cell's mean times lognormal day noise "
            "(sd 0.07), counted as a Poisson number (a rounded normal from 30 on), exactly as the history was drawn. "
            "`score()` integrates the day noise with 16 Gauss-Hermite nodes and sums the counts, so the expected "
            "units left over and short of any order are exact and the same on every machine: no realized future, no "
            "luck. The first version scored the weighted WAPE against one drawn horizon.",
            "- **Whose demand.** The cell's mean is the world's own: the store's scale and trend, the category's "
            "weekday profile and season, the holiday's effect on the drawn date, and in medium and hard the "
            "promotions that run (the plan minus the cancelled category, times the flyer's multiple). In easy the "
            "promotions are the category team's, so demand is the demand without them. Bread rolls are judged in "
            "hard only; a closed day has no demand, so anything ordered there is left over (and breaks "
            "`closed_day_zero`).",
            "- **The zero and the one.** Quality 0 is the store managers' habit (`baseline_solution`): the average of "
            "the last eight weeks' sales of that weekday, days the store ran out left aside, plus a cushion of 10, "
            "20 or 30% at a cost ratio of 5, 12 or 30, 2% more per point of discount times the flyer's multiple on "
            "promotion days, the holiday ordered like a Saturday, the display minimum and S4's Sundays at 0. The "
            "managers know their business, not statistics. The habit is taken at its fairest: over the measured "
            "settings of the public world and world seeds 1 and 2 these cushions cost it at most 0.002 more than "
            "the flat cushion that costs it least at each ratio, and no other window or cushion lifts it by half the "
            "scale (shortcuts `habit_last_year`, `habit_more_cushion`). Quality 1 is the reference (part 4).",
            "", "## 4. Reference and bounds", "",
            "- **Reference** (`reference_solution`): a model of expected demand per cell from the history only: "
            "stockout days and return rows left out, bread rolls' early history divided by 6; a weekday profile per "
            "category pooled over its items, stores and both years; a level per store and item over the last twelve "
            "weeks, carried into November by last year's change of the category's level; a promotion lift per "
            "category and discount and a holiday lift per category against the local level; and the day noise left "
            "once Poisson counting is taken out. The order is the `lost_sale_cost / (1 + lost_sale_cost)` quantile "
            "of the demand the model predicts for the cell, with S4's Sundays at 0 and the display minimum on core "
            "items.",
            "- **Best known** (`best_known_solution`): every cell's cost-minimizing order under the true demand "
            "distribution (hindsight no agent has: the true mean of every cell), raised to the display minimum.",
            "- **Bound** (`objective_bound`, proven, and attained): the objective is a sum over cells of a cost that "
            "depends on that cell's order alone, divided by constants, and every rule bounds one cell's order. A "
            "cell's expected cost is convex in the order with its minimum at the `k / (1 + k)` quantile, so no valid "
            "plan costs less in a cell than that quantile, or the display minimum where it is higher. The best "
            "known solution is that plan, so the gap between the two is zero and the gap below is the reference's "
            "distance from the optimum.", ""]
    rows = []
    for tier in tiers:
        for b in [b for b in audit["bounds"] if b["setting"].startswith(tier + "/")]:
            rows.append([b["setting"], _num(b["reference"], 4), _num(b["baseline"], 4), _num(b["span"]),
                         _num(b["best_known"], 4), _num(b["best_known_quality"]), _num(b["bound"], 4),
                         _num(b["bound_quality"]), _num(b["gap_to_bound"])])
    out += _table(["setting", "reference", "baseline", "span", "best known", "best known quality", "bound",
                   "bound quality", "gap (reference − bound) / reference"], rows)
    known = [b["best_known_quality"] for b in audit["bounds"] if b["best_known_quality"] is not None]
    gaps = [b["gap_to_bound"] for b in audit["bounds"] if b["gap_to_bound"] is not None]
    spans = [b["span"] for b in audit["bounds"]]
    out += ["", f"The quality scale is {min(spans):.0%} to {max(spans):.0%} of the reference's cost wide. The best "
            f"plan reaches {min(known):.3f}–{max(known):.3f} on it (median {median(known):.3f}); the reference is "
            f"{min(gaps):.1%}–{max(gaps):.1%} above the optimum. **quality_cap** = {meta.get('quality_cap')}: the "
            "median quality of the best plan over the measured settings, rounded up to the next 0.01 (full credit "
            "at the optimum; DESIGN.md, Ground truth audit).", "",
            "**Value of asking** (never asks = `robust_solution`: the agent's view at its natural reading, with "
            "stockout days left out, the promotion plan in the order and bread rolls in packs; every candidate date "
            "of the holiday, flyer multiple and cancelled category taken as an equally likely scenario; one cost "
            "ratio for the whole pool; the strictest display minimum. It is granted two facts it could not know, "
            "that the number is ordered as it is and that the manager's e-mail is not followed. never asks (params) "
            "= the best single setting's reference, which knows every fixed fact):", ""]
    rows = []
    for tier in tier_order(audit["voi"]):
        v = audit["voi"][tier]
        rob = next((c for c in v["candidates"] if c["name"] == "robust_solution"), {})
        rows.append([tier, _num(v["never_asks"]), _num(rob.get("valid_rate")), _num(v["voi"]),
                     _num(v["never_asks_params"]), _num(v["voi_params"])])
    out += _table(["tier", "never asks (credit)", "its validity rate", "voi", "never asks (params)", "voi_params"],
                  rows)
    out += ["", "## 5. Diagnostic cases", "",
            "`score()` returns `enforced` and `evidence` per target in force, for valid and invalid plans alike, "
            "from the plan itself: each check reads the orders where only that fact decides them and compares them "
            "with the demand distribution, which the scorer knows. *Ordinary* store × item days are open, judged, "
            "without a promotion in `promo_plan.csv`, not on a date the holiday can fall on and not a slow core "
            "item; a promotion day and the holiday are compared with the same weekday of the other week, itself an "
            "ordinary day. The yardstick is the best plan (part 4), so it is enforced by construction; for a plan "
            "that hands in the expected demand it is the expected demand, since a cushion grows more slowly than "
            "the demand it covers. Central Plaza "
            "is left out of the cost-ratio check and has its own store effect in the stockout check, so that "
            "following the note flags the note alone; the stockout check also takes out what an item's category "
            "shares, so that a model that misses a category's season is not read as one that misreads stockouts. "
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
    out += _table(["target", "what tells a plan that implements the fact from one that misreads it",
                   "reference enforced", "ablations"], rows)
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
    out += ["", "The baseline leaves out the days the store ran out, and the stockout check passes it; it orders the "
            "holiday like a Saturday, which misses bakery's lift where the holiday is a Friday, and the holiday "
            "check says so. `robust_solution` plans for one cost ratio, the strictest minimum and every scenario of "
            "the flyer and the cancellation, and keeps the promotions in easy: it is called not enforced where the "
            "client's value is another one, which is the diagnostic working as meant.",
            "", "**Shortcuts** (closed: invalid, or quality at most "
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
