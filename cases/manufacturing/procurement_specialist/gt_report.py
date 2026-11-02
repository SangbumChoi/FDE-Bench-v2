"""Write GT.md (the case's ground truth in five parts) from dataset/audit.json, case.yaml and the targets.

Run from the repository root after `fdebench2 audit-case`:  python cases/manufacturing/procurement_specialist/gt_report.py
Every number in the tables comes from the stored audit (the public world); the prose around them is fixed here.
GT.md never quotes the audit's fingerprint, so writing it again after a fresh audit gives the same file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import median

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))

from fdebench2.audit import shortcut_summary, target_summary, tier_order  # noqa: E402
from fdebench2.cases import NativeCase  # noqa: E402

TIERS = ("easy", "medium", "hard")

# Why each rule is a hard gate (validity check), in the client's terms.
RULE_WHY = {
    "approved_vendor": "a part from a supplier that is pending or suspended cannot go on the boards: the quality "
                       "system rejects it, whatever it costs",
    "moq": "the supplier does not ship an order line below its minimum, so a plan that relies on one is short in "
           "reality",
    "budget_cap": "the parent company's monthly cap is not negotiable: a plan that overspends a month is not "
                  "approved, however cheap it is overall",
    "quality_hold": "lots from the supplier on hold that arrive while the hold lasts are rejected at incoming "
                    "inspection and never reach the line",
    "allocation_cap": "the allocated supplier confirms no more than its monthly allocation; anything above it is "
                      "simply not delivered",
    "dual_source_critical": "the company keeps a qualified second source for every critical part (its habit, which "
                            "the client may waive for a real saving through the exception process: the policy scores "
                            "a granted bend with the rule switched off and a penalty)",
}
# Targets that were removed (they stay in requirements.md as context) and why.
REMOVED = {
    "resistor_reels": "reading the resistor stock in pieces makes a planner over-order 3 KRW resistors; that cost 0.1-0.3% "
                      "of the objective (damage 0.01-0.13, below 0.10 in eight of nine panel settings)",
    "holding_cost (from cost_model)": "a planner that ignores the 0.5% weekly holding cost still orders as late as "
                                       "possible; damage 0-0.04 on the panel",
    "expected_cost": "its only natural misreading (plan on the promised dates) is the one supplier_lateness already "
                     "ablates; it changes nothing on top",
    "price_rise_week in hard": "the allocation (3,500 displays a month from Nara Display) caps how much of the "
                               "display need from W4 on can be brought into W3, so misreading the week loses less "
                               "than 10% of the credit in every measured hard setting; the fact stays in the hard "
                               "requirements",
    "shortfall_cost in easy and medium": "its natural misreading keeps the safety stock as a floor never to be broken "
                                         "(an agent told the level but not the price of dipping below it); no "
                                         "measured easy or medium setting then loses a tenth of the scale (at most "
                                         "0.09), since without late deliveries keeping the floor costs about what "
                                         "the client's 1.5x trade-off does. The first audit's misreading, a "
                                         "shortfall that costs nothing, made the planner throw the safety stock "
                                         "away and so measured the safety_stock fact (damage 1.0 everywhere). The "
                                         "fact stays in the easy and medium requirements; in hard, where late "
                                         "deliveries make a floor dear, it bites",
    "usd_planning_rate in easy and hard": "in easy no wrong candidate rate loses 10% of the credit in any measured "
                                          "setting (Pacific Parts stays the cheapest source of its parts at every "
                                          "candidate, so the rate only moves the dollar spend); hard has one rate",
    "round_scope_easy / round_scope_medium": "split into scope_list_prices, scope_no_flash_change, scope_on_time and "
                                             "scope_no_allocation",
    "lead_time_weeks / business_day_lead_times": "split into lead_time_business_days, scope_whole_weeks and "
                                                 "holiday_weeks (the arrival-week convention moved into bom_explosion)",
    "monthly_budget_cap": "split into budget_hard_cap and budget_month",
    "dual_source_critical": "split into dual_source_two and max_share (the bendable habit stays in its text)",
    "cost_model": "split into shortfall_cost and backlog_cost (hard); the holding weight was dropped (above)",
    "engineering_change": "split into eco_switch and eco_c04_exempt",
}


def _num(x, digits=3):
    return "–" if x is None else f"{x:.{digits}f}"


def _m(x):
    return "–" if x is None else f"{x / 1e6:.2f}"


def _table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def _fact(text: str) -> str:
    """A target's English text with its parameters and tier blocks written generically."""
    import re
    text = re.sub(r"<!-- tier: ([a-z ]+) -->(.*?)<!-- /tier -->", lambda m: f" [{m.group(1)}:{m.group(2)}]", text)
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: f"*{m.group(1)}*", text).replace("|", "/")


def main() -> None:
    case = NativeCase(ROOT)
    module = case.module
    audit = json.loads((ROOT / "dataset" / "audit.json").read_text(encoding="utf-8"))
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    targets = yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))
    by_id = {t["id"]: t for t in targets}
    summary = {t["target"]: t for t in target_summary(audit)}
    tiers = tier_order(audit["settings"])
    n_set = {t: len([e for e in audit["settings"][t] if not e.get("skipped")]) for t in tiers}
    out = [f"# Ground truth: {audit['case']}", "",
           "The ground truth (GT) of a setting in five parts, with the reference as supporting evidence. Generated "
           "by `gt_report.py` from `dataset/audit.json` (`fdebench2 audit-case`, public world seed "
           f"{audit['world_seed']}): {sum(n_set.values())} settings, "
           + ", ".join(f"{t} {n_set[t]}" for t in tiers)
           + " (each tier's public panel plus admissible parameter combinations). Damage is 1 − credit, credit = 0 "
           "for an invalid plan, else the quality score clipped to [0, 1]; a target bites in a setting when misreading "
           f"it alone loses at least {audit['thresholds']['ablation_min_damage']:.2f} of the credit (for a drawn "
           "parameter: its least harmful wrong candidate).", ""]

    # 1. client facts
    out += ["## 1. Client facts (targets)", "",
            "One row per target: the fact, the tiers where it is in force, how the audit misreads it, the damage "
            "range over the settings where it is in force, the settings where it bites per tier (k/n) and whether "
            "its diagnostic (`enforced`, part 5) tells the reference from the misreading.", ""]
    rows = []
    for t in targets:
        s = summary.get(t["id"])
        if s is None:
            continue
        param = t.get("param")
        flag = module.TARGET_MISREADING.get(t["id"])
        how = []
        if "param" in s["sources"]:
            how.append(f"the reference of each other candidate of `{param}`")
        if "hook" in s["sources"] and flag:
            how.append(f"`{flag}`: {module.MISREADINGS[flag]}")
        bites = ", ".join(f"{tier} {k}/{n}" for tier, (k, n) in s["per_tier"].items())
        diag = "no" if not s["has_diagnostic"] else ("untested" if s["separates"] is None else
                                                    "separates" if s["separates"] else "does not separate")
        rows.append([f"`{t['id']}`", _fact(t["text"]), ", ".join(s["tiers"]), "; ".join(how) or "none",
                     f"{_num(s['low'])}–{_num(s['high'])}", bites, diag])
    out += _table(["target", "fact", "in force", "ablation (the natural misreading)", "damage", "bites k/n",
                   "diagnostic"], rows)
    out += ["", "Removed or split targets (the facts stay in requirements.md where they are context):", ""]
    out += [f"- `{k}`: {v}." for k, v in REMOVED.items()]

    # 2. validity checks
    out += ["", "## 2. Validity checks (hard gates)", "",
            "A plan that breaks any of these is invalid and earns no quality credit. The deliverable is `orders.csv` "
            "(`order_week,component_id,supplier_id,quantity`); a row with an unknown part, a supplier without a quote "
            "for it, a week outside W1-W8 or a quantity that is not a whole number makes the file unreadable "
            "(fatal). Every row is an order line; rows of the same week, part and supplier are added up.", ""]
    rows = []
    for r in meta["rules"]:
        rows.append([f"`{r['id']}`", r["class"], ", ".join(r.get("tiers", TIERS)), RULE_WHY.get(r["id"], "")])
    out += _table(["rule", "class", "tiers", "why it is a hard gate"], rows)
    out += ["", "Mandatory content. The plan has no separate report: what it must contain is enforced by the rules "
            "above (every critical part in use is ordered from two suppliers, so an empty or partial plan is invalid) "
            "and by the objective (a part left out is a backlog of boards). The shortcuts below show that each "
            "degenerate plan is invalid or scores at most "
            f"{audit['thresholds']['shortcut_max_quality']}.", ""]
    rows = [[f"`{s['name']}`", s["description"], f"{s['closed']}/{s['settings']}", _num(s["best_quality"], 2)]
            for s in shortcut_summary(audit)]
    out += _table(["shortcut", "what it does", "closed", "best quality where valid"], rows)

    # 3. objective
    out += ["", "## 3. Objective (lower is better, KRW)", "",
            "- **Purchases**: every order line at its price (medium and hard: the all-units break the line reaches), "
            "Nara Display's display module C06 12% dearer from order week W4, the dollar quotes of Pacific Parts at the "
            "planning rate. Cash the client pays.",
            "- **Holding**: 0.5% of the standard cost per piece in stock at the end of a week (about 26% a year, the "
            "usual carrying cost of capital, storage and obsolescence).",
            "- **Backlog**: 10,000 KRW per board that waits a week for a missing part (late-delivery penalties and "
            "overtime), counted per part: a missing piece costs 10,000 KRW divided by the part's pieces per board. A "
            "missing capacitor stops a board as surely as a missing display, which the first version's 5x the part's "
            "own cost per piece did not reflect (REVIEW.md F4).",
            "- **Safety-stock shortfall**: 1.5x the standard cost per piece of a critical part below its safety stock at "
            "the end of a week in which it is used: the client's price for running without the buffer it asked for.",
            "- **Scrap** (hard): C04 left at the end of W5 at its standard cost (the supplier does not take it back).",
            "", "**Uncertainty.** In hard each delivery is one or two weeks late with the supplier's true probabilities, "
            "which the agent only sees as a sample (the delivery history). Holding, backlog, shortfall and scrap are "
            "their exact expectation over every combination of late deliveries (enumerated, never sampled); purchases "
            "are paid either way. The reference plans on smoothed history estimates, never the true rates. Stock left "
            "after W10 is worth nothing.", ""]

    # 4. reference and bounds
    bounds = audit["bounds"]
    known = [b["best_known_quality"] for b in bounds if b["best_known_quality"] is not None]
    out += ["## 4. Reference and bounds", "",
            "- **Reference** (`reference_solution`): a time-phased MRP per part (netting stock and open orders against "
            "the exploded demand, cheapest timely approved supplier, as late as possible), with whole-line or "
            "quota second sourcing, a leftover trim and a budget step that defers, pulls or cuts lines; the cheapest "
            "of fifteen such variants by its own cost view is then improved by a local search (lines moved to another "
            "week or supplier, resized to a break or by hundreds, removed; every rule kept), which also brings C06 "
            "orders forward into W3 before Nara Display's increase. In hard it plans one week of safety lead time "
            "for suppliers whose smoothed late rate in the history is above 5%.",
            "- **Baseline** (quality 0): the client's own MRP run, lot for lot from the cheapest timely supplier at "
            "list prices, critical parts split at the share cap, the budget fixed afterwards; in hard the buyer adds "
            "one week to every lead time.",
            "- **Best known** (`best_known_solution`): the wide local search (also new lines, transfers between lines "
            "and longer moves) from the three cheapest variants and from the reference, by the same own cost view.",
            "- **Bound** (`objective_bound`): a linear relaxation solved exactly with HiGHS (no MOQ, every piece at the "
            "lowest price its line could reach, the share cap, budget, allocation, hold and lead times kept; in hard "
            "the expected net position, a lower bound by Jensen's inequality). A mixed-integer version with the price "
            "tiers and MOQs (scipy's HiGHS MILP) was tried on the first panel seed: in easy/s42 it closes the gap to "
            "3.6% after 1,000 nodes (61 s), in medium/s42 and hard/s42 200 nodes took 70-90 s and left 9% and 14%, "
            "so the LP bound is kept.",
            f"- **quality_cap** = {meta.get('quality_cap')}: the median best-known quality over the measured settings "
            f"is {_num(median(known)) if known else '–'} (range {_num(min(known)) if known else '–'}–"
            f"{_num(max(known)) if known else '–'}); the cap is set at or above it, so the best plan known earns full "
            "quality credit and a plan as good as the reference earns 1/cap.", ""]
    rows = [[b["setting"], _m(b["reference"]), _m(b["baseline"]), _num(b["span"]), _m(b["best_known"]),
             _num(b["best_known_quality"]), _m(b["bound"]), _num(b["bound_quality"]), _num(b["gap_to_bound"])]
            for b in bounds]
    out += _table(["setting", "reference (M)", "baseline (M)", "span", "best known (M)", "its quality",
                   "bound (M)", "bound quality", "gap ref–bound"], rows)
    out += ["", "**Value of asking** (part of the GT's claim that the client must be asked): per tier, the best plan "
            "that never asks (`robust_solution`: the natural reading of the request and the data, the same in every "
            "tier, so the flash change applied, the delivery history and the allocation used as the request asks, "
            "planned across the tier's pools: the middle safety stock, the tightest share cap, the dearest dollar, "
            "every candidate hold avoided) against the reference of each setting. Other never-asks readings measured "
            "on the same settings (REVIEW.md, second pass): hedging both flashes, the strictest safety stock and "
            "Nara Display's rise from W3 do worse; ignoring the change, which the request contradicts, does about as "
            "well over all 39 settings (mean credit 0.158 against 0.151) but in the other tiers: 0.315 in easy, 0.095 "
            "in medium, invalid in every hard setting (C25 never bought). No reading tried, the same in every tier, "
            "beats 0.32 in easy, 0.13 in medium or 0.66 in hard.", ""]
    rows = []
    for tier in tier_order(audit["voi"]):
        v = audit["voi"][tier]
        rows.append([tier, _num(v["never_asks_params"]), _num(v["voi_params"]), _num(v["never_asks"]),
                     _num(v["voi"])])
    out += _table(["tier", "never asks, knows the fixed facts", "value of the parameters", "never asks (robust)",
                   "value of asking"], rows)

    # 5. diagnostics
    out += ["", "## 5. Diagnostic cases", "",
            "`score()` reports `enforced[target]` for every target in force, for valid and invalid plans alike. For a "
            "target with a natural misreading, the plan D is scored under the client's view S and under the misread "
            "view S' and compared with the reference R: delta = [g_S(D) − g_S(R)] − [g_S'(D) − g_S'(R)], where g is the "
            "objective plus 10^10 per distinct rule broken. The target is enforced when delta ≤ 0.01% of the "
            "reference's objective: the client's reading does not make D look worse next to the reference than the "
            "misreading does. A rule broken only under the client's reading fails it; one broken only under the "
            "misreading passes it. The planning rate and the safety stock compare the same way with every other "
            "candidate of their parameter. The quality hold checks that nothing from the held supplier arrives "
            "during the hold and that the plan does not avoid a supplier only another candidate holds (where the "
            "reference uses it); the share cap checks the cap and that the plan uses the room a stricter candidate "
            "would not leave (where the reference does). The audit checks that the reference is enforced everywhere "
            "and that every ablation that bites is not.",
            "", "Limits (second pass, REVIEW.md). The comparison is with the reference R under S', so a plan that merely "
            "differs from R can be called a misreading. The client's own MRP, which knows every fact, is 'not "
            "enforced' on the lead times in 28 of 39 settings and on the planning rate in 13 of 15 (often R breaks a rule "
            "under the misreading that the MRP keeps), and the tolerance (0.01% of the objective, about 0.1% of the "
            "scale) lets any other difference decide. Comparing regrets with the reference planner's own plan for the "
            "misreading, within 5% of the scale, frees the client's MRP of most of these and still separates every "
            "ablation on the four settings checked, but scoring then plans the misreadings and validate-case takes "
            "seven times as long; it waits for a framework change (diagnostics only where evaluate() is asked for "
            "them). Read the enforced column of a run's funnel for plans far from the reference with this in mind.", ""]
    rows = []
    for t in targets:
        s = summary.get(t["id"])
        if s is None:
            continue
        flag = module.TARGET_MISREADING.get(t["id"])
        param = t.get("param")
        if t["id"] == "quality_hold":
            kind = "plan shape: arrivals from the held supplier, and suppliers only another candidate holds"
        elif t["id"] == "max_share":
            kind = "plan shape: top share per critical part against the cap and the next stricter candidate" + (
                f"; hard: delta against `{flag}`" if flag else "")
        elif param:
            kind = f"delta against every other candidate of `{param}`"
        else:
            kind = f"delta against `{flag}`"
        diag = "no" if not s["has_diagnostic"] else ("untested" if s["separates"] is None else
                                                    "separates" if s["separates"] else "does not separate")
        rows.append([f"`{t['id']}`", kind, diag, ", ".join(s["undiagnosed"][:3]) or "–"])
    out += _table(["target", "diagnostic", "result", "settings where it fails"], rows)
    out += ["", "## Findings of the audit", ""] + [f"- {x}" for x in audit["summary"]]
    (ROOT / "GT.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("wrote", ROOT / "GT.md")


# ── CLIENT_REVIEW.md: what the simulated client answers from, per target ─────
# The question an engineer would naturally ask, and how to find the passage of requirements.md the client answers
# from in every locale: every token must occur in the passage (a bullet with its indented lines, or a paragraph);
# a token "@name" is the localized column or file name (case.py COLS / FILES); "first" takes the first passage that
# matches, "all" every one (a fact stated in two places, e.g. the data notes and the hard constraints).
QUESTIONS = {
    "bom_explosion": ("How do I get each component's weekly demand from the production plan and the BOM, and in which "
                      "week must the parts be in stock?", ["@qty_per", "B100"], "first"),
    "lead_time_business_days": ("Is lead_time_days in calendar days or business days, and from when is it counted?",
                                ["@lead"], "all"),
    "scope_whole_weeks": ("Should I account for the Christmas and New Year holidays in the lead times this round?",
                          ["@lead", "w+L"], "first"),
    "holiday_weeks": ("Which weeks have fewer working days because of holidays?", ["@lead", "W5", "W6"], "first"),
    "usd_planning_rate": ("Which exchange rate should I use for Pacific Parts' dollar quotes?",
                          ["{{usd_krw}}", "S04"], "first"),
    "moq_per_line": ("Does the MOQ apply to each order or to the total I buy from a supplier?", ["@moq"], "all"),
    "price_breaks": ("How do the price breaks work: per order line or on the total volume, and for the whole line?",
                     ["@moq", "@b1q"], "first"),
    "scope_list_prices": ("Should I use the price breaks in this plan?",
                          ["@price", {"en": "frame agreement", "zh": "框架协议", "ko": "기본계약", "ja": "基本契約",
                                      "es": "acuerdo marco"}], "first"),
    "price_rise_week": ("Nara Display's increase starts on Wednesday 9 December: which of our order weeks does it hit?",
                        ["C06", "12%", "W4"], "first"),
    "quality_hold": ("Are any suppliers blocked or on hold at the moment?", ["{{hold_supplier}}", "{{hold_until}}"],
                     "first"),
    "budget_hard_cap": ("Is the monthly budget a hard limit or a target?", ["@budget_file", "W1"], "first"),
    "budget_month": ("Which month's budget does an order count against, for example W2, which straddles November and "
                     "December?", ["@budget_file", "W1"], "first"),
    "approved_status_only": ("Can I buy from a supplier whose status is pending or suspended?", ["@avl_file"], "first"),
    "safety_stock": ("How much safety stock do you want for the critical parts?", ["{{safety_weeks}}"], "first"),
    "shortfall_cost": ("How bad is it to dip below the safety stock for a week?", ["@std_cost", "1.5"], "first"),
    "dual_source_two": ("Do you have a sourcing policy for critical parts, such as a second source?", ["{{max_share}}"],
                        "all"),
    "max_share": ("How much of a critical part may one supplier get?", ["{{max_share}}"], "all"),
    "backlog_cost": ("What does it cost you when boards wait for a missing part?", ["10,000"], "first"),
    "scope_no_flash_change": ("The BOM shows the flash changing from C04 to C25 in W6: should I plan for that change?",
                              ["@bom_file", "C25", "W6"], "first"),
    "scope_on_time": ("Should I plan with the late deliveries in the delivery history?",
                      ["@history_file", "@alloc_file"], "first"),
    "scope_no_allocation": ("Do the allocation caps apply to this plan?", ["@history_file", "@alloc_file"], "first"),
    "supplier_lateness": ("How should I use the delivery history: how late do suppliers deliver?",
                          ["@history_file", "14"], "first"),
    "allocation_caps": ("How do the allocation caps work?", ["@alloc_file", "S08", "C06"], "first"),
    "eco_switch": ("When does C25 replace C04, and what happens to the C04 left over?", ["C25", "W1-W5", "W6"],
                   "first"),
    "eco_c04_exempt": ("Does the phased-out C04 still need safety stock and a second source?", ["C25", "W1-W5", "W6"],
                       "first"),
}
# What the scorer uses, as it must read in the passage (case.py constants), per target.
SCORER = {
    "price_rise_week": ["12%", "W4", "W3"],
    "backlog_cost": ["10,000"],
    "shortfall_cost": ["1.5"],
    "holiday_weeks": ["W5", "W6", "4"],
    "lead_time_business_days": ["5"],
    "budget_month": ["W1", "W2", "W3", "W6", "W7", "W8"],
    "supplier_lateness": ["1", "7", "8", "14"],
    "eco_switch": ["C04", "C25", "W5", "W6"],
}
LOCAL_NAMES = {"@budget_file": ("FILES", "budget"), "@avl_file": ("FILES", "avl"), "@bom_file": ("FILES", "bom"),
               "@history_file": ("FILES", "history"), "@alloc_file": ("FILES", "alloc")}
LANGS = ("en", "zh", "ko", "ja", "es")


def _passages(text: str) -> list[str]:
    """Bullets (with their indented continuation lines) and paragraphs, setting markers kept."""
    out, cur = [], []
    for line in text.splitlines():
        if line.startswith("- ") or (line and not line.startswith(" ") and not line.startswith("<!--")):
            if cur:
                out.append("\n".join(cur))
            cur = [line]
        elif line.startswith("  ") and cur:
            cur.append(line)
        else:
            if cur:
                out.append("\n".join(cur))
            cur = []
    if cur:
        out.append("\n".join(cur))
    return out


def _dash(text: str) -> str:
    """W1〜W5, W1～W5, W1~W5 and W1–W5 all read W1-W5."""
    for d in ("〜", "～", "~", "–"):
        text = text.replace(d, "-")
    return text


def _es_numbers(text: str, lang: str) -> str:
    """Spanish 10.000 and 1,5 written as 10,000 and 1.5."""
    import re
    if lang == "es":
        text = re.sub(r"(\d)\.(\d{3})(?!\d)", r"\1,\2", text)
        text = re.sub(r"(\d),(\d)(?!\d)", r"\1.\2", text)
    return text


def _norm_numbers(text: str, lang: str) -> list[str]:
    """The tokens a translation must keep, written the same way in every locale: IDs, weeks, parameters,
    percentages and numbers from 100 up or with decimals (es writes 10.000 and 1,5). Small whole numbers are left
    out: the languages write counts and dates differently (en "9 December", ko "12월 9일", ja "2機種")."""
    import re
    t = _es_numbers(_dash(text), lang)
    out = set(re.findall(r"\{\{\w+\}\}", t))
    out |= set(re.findall(r"(?<![A-Za-z0-9])(?:[CSB]\d{2,3}|W\d+)(?![0-9])", t))
    for num in re.findall(r"(?<![A-Za-z0-9.,])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(%?)", t):
        value, pct = num
        if pct or "." in value or float(value.replace(",", "")) >= 100:
            out.add(value + pct)
    return sorted(out)


def client_review(module) -> str:
    cols, files = module.COLS, module.FILES
    texts = {lang: (ROOT / "locales" / lang / "requirements.md").read_text(encoding="utf-8") for lang in LANGS}
    targets = yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))

    def tokens(lang, spec):
        out = []
        for tok in spec:
            if isinstance(tok, dict):
                out.append(tok[lang])
            elif tok in LOCAL_NAMES:
                table, key = LOCAL_NAMES[tok]
                out.append({"FILES": files}[table][key][lang])
            elif tok.startswith("@"):
                out.append(cols[tok[1:]][lang])
            elif lang == "es" and tok in ("10,000", "1.5"):
                out.append({"10,000": "10.000", "1.5": "1,5"}[tok])
            else:
                out.append(tok)
        return out

    def find(lang, spec, which):
        hits = [p for p in _passages(texts[lang]) if all(t in _dash(p) for t in tokens(lang, spec))]
        return hits[:1] if which == "first" else hits

    out = ["# Client answers: human review", "",
           "The simulated client answers only from `locales/<lang>/requirements.md` (plus event facts; this case has "
           "none). For every target: the question an engineer would naturally ask, the passage each locale answers "
           "from (quoted as written, with setting markers and parameters), a machine pre-check and an empty verdict "
           "for a human reviewer. Generated by `gt_report.py`.", "",
           "Pre-check: (1) the passage is found in all five locales; (2) the same IDs, weeks, parameters and numbers "
           "in every locale (thousands separators and decimal commas normalized); (3) the numbers the scorer uses "
           "(case.py constants) appear in every locale; (4) other targets whose passage is the same one, i.e. what "
           "the passage answers beyond the question (the client may state them together when asked).", "",
           "**Status: awaiting human review.** No passage below has been reviewed by a person yet.", ""]
    by_target = {}
    for t in targets:
        q, spec, which = QUESTIONS[t["id"]]
        by_target[t["id"]] = {lang: find(lang, spec, which) for lang in LANGS}
    for t in targets:
        tid = t["id"]
        q, spec, which = QUESTIONS[tid]
        found = by_target[tid]
        out += [f"## `{tid}`" + (f" ({', '.join(t['tiers'])})" if t.get("tiers") else ""), "",
                f"**Question.** {q}", "", f"**Target (en).** {t['text']}", ""]
        for lang in LANGS:
            out.append(f"**{lang}:**")
            out.append("")
            for p in found[lang] or ["(not found)"]:
                out += ["> " + line for line in p.splitlines()]
                out.append(">")
            if out[-1] == ">":
                out.pop()
            out.append("")
        checks = []
        missing = [lang for lang in LANGS if not found[lang]]
        checks.append("passage found in every locale" if not missing else f"NOT FOUND in {', '.join(missing)}")
        nums = {lang: _norm_numbers("\n".join(found[lang]), lang) for lang in LANGS if found[lang]}
        ref = nums.get("en", [])
        diff = {lang: (sorted(set(ref) - set(n)), sorted(set(n) - set(ref))) for lang, n in nums.items()
                if set(n) != set(ref)}
        if diff:
            checks.append("numbers differ from en: " + "; ".join(
                f"{lang} lacks {a or '–'}, adds {b or '–'}" for lang, (a, b) in diff.items()))
        else:
            checks.append("same IDs, weeks, parameters and numbers in all five locales: " + (", ".join(ref) or "none"))
        want = SCORER.get(tid, [])
        if want:
            import re
            flat = {lang: _es_numbers(_dash("\n".join(found[lang])), lang) for lang in nums}
            lacking = {lang: [w for w in want if not re.search(r"(?<![0-9.,])" + re.escape(w) + r"(?![0-9])", t)]
                       for lang, t in flat.items()}
            lacking = {k: v for k, v in lacking.items() if v}
            checks.append("scorer values present in every locale (" + ", ".join(want) + ")" if not lacking else
                          "scorer values missing: " + "; ".join(f"{k} {v}" for k, v in lacking.items()))
        same = [o for o, f in by_target.items() if o != tid and f["en"] and found["en"]
                and set(f["en"]) & set(found["en"])]
        checks.append("the passage also states: " + (", ".join(f"`{o}`" for o in same) if same else "nothing else "
                                                      "that is a target"))
        out += ["**Machine pre-check.**", ""] + [f"- {c}" for c in checks] + ["", "Reviewer verdict:", ""]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    which = sys.argv[1:] or ["gt", "client"]      # "client" needs no audit, "gt" reads dataset/audit.json
    if "client" in which:
        (ROOT / "CLIENT_REVIEW.md").write_text(client_review(NativeCase(ROOT).module), encoding="utf-8")
        print("wrote", ROOT / "CLIENT_REVIEW.md")
    if "gt" in which:
        main()
