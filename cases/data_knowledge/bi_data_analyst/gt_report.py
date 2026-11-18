"""Write GT.md (the case's ground truth in five parts) and CLIENT_REVIEW.md (what the simulated client answers from).

Run from the repository root:  python cases/data_knowledge/bi_data_analyst/gt_report.py [gt] [client]
GT.md takes every number in its tables from dataset/audit.json (`fdebench2 audit-case`, public world), and two small
tables from the case itself (the bend of the running-period habit and the sheet robust_solution writes); the prose
around them is fixed here. Neither file quotes the audit's fingerprint, so writing them again after a fresh audit of
the same sources gives the same files. Both are case docs (cases.CASE_DOCS), outside the audit's fingerprint, so
writing them never makes the stored audit stale; this script is a source of the audit, like case.py.
"""

from __future__ import annotations

import itertools
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

# Why each rule is a hard gate (validity check), in the client's terms.
RULE_WHY = {
    "answer_format": "the board pack has one slot per question: a missing id or a value that is neither a number nor "
                     "`null` cannot be placed (mandatory output: all twelve ids, whether the round uses them or not)",
    "exclude_test_accounts": "finance policy: QA accounts are not customers; the load-test account would be the "
                             "board's \"top customer\"",
    "report_rounding": "the board pack's tables are in the client's unit; a figure in another precision cannot be "
                       "pasted in (it was the bendable rule before the audit: bending it gained nothing, since a "
                       "rounded figure always counts as right)",
    "running_period": "finance's habit: no part-period figure under a full-period heading. The one bendable rule: "
                      "the CFO can approve a figure to date, which is then judged against the exact figure to date",
}
# How each fixed fact is misread in its ablation (case.py MISREADINGS, the first reading; running_period apart).
RUNNING_ABLATION = "the figure to date (the period counted up to the reference date)"
# What tells a correct sheet from the misreading (case.py diagnose).
DIAGNOSTIC = {
    "fiscal_year": "the fiscal-period questions answered: the client's figure, or the figure of a year starting in "
                   "another month (each of the eleven others)",
    "fy_naming": "the fiscal-period questions answered: the client's figure, or the figure of the year that ends in "
                 "the named calendar year",
    "running_period": "the scored questions whose period is still running: `null`, or a number (the figure to date, "
                      "or any other number on a sheet whose answers follow the client's fiscal year; a figure that "
                      "another fiscal year the sheet follows explains counts against that fact instead)",
    "active_customer": "Q03: the client's count, or the count of another window (7 to 365 days)",
    "report_rounding": "the scored money figures: all multiples of the unit, and none equal to the exact figure "
                       "rounded to a unit 10 or 100 times coarser where that is wrong",
}
FIGURES = "the answered questions where this misreading alone gives another figure: the client's figure or the misreading's"
# Facts that were targets (or clauses of targets) before this audit and are not now. They stay in requirements.md,
# where the client still answers them when asked.
REMOVED = [
    ("`answer_rewards` (a correct figure 2, `null` 0.5 / 1 / 1.5, a wrong figure 0)",
     "how the answers are judged (part 3), not a fact that changes a correct sheet: the reference written for "
     "another reward for a null is the same sheet, so misreading it loses nothing for an analyst who knows the "
     "definitions. It decides what an analyst who does not know them should leave `null`, which the value of asking "
     "measures (part 4). That `null` is an accepted answer is now part of `running_period`."),
    ("`fiscal_year`, the old bundle",
     "split into `fiscal_year` (the first month, exactly the drawn `fy_start`) and `fy_naming` (named after the year "
     "it starts in). Its third clause, \"a period still running is counted up to the reference date\", is replaced "
     "by the opposite habit, `running_period`."),
    ("`net_revenue`, the old bundle",
     "split into `revenue_ex_tax` (subtotal less the tax-free part of refunds) and `refund_period` (booked in the "
     "order's period), the latter in force from medium, where a refund question is scored."),
    ("\"refunds use the same rate as their order\" (a clause of `fx_order_date`)",
     "converting refunds at the refund date's rate moves Q08 and Q09 by 0.09-0.10% and Q01 by 0.01% on the public "
     "world (at most 0.15% on world seeds 1-3), inside the 0.5% tolerance: no answer changes."),
    ("\"an order's refunds are spread over its lines pro rata\" (a clause of `category_rename`)",
     "charging each refund to the line it matches moves Q06 by -0.02% to +0.27% on the public world (within 0.27% "
     "on world seeds 1-3): no answer changes."),
    ("the tolerances (a clause of `report_rounding`)",
     "how the answers are judged; the fact is the unit."),
]


def _num(x, digits=3):
    return "–" if x is None else f"{x:.{digits}f}"


def _table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def _fact(text: str) -> str:
    """A target's English text with its parameters written generically."""
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: f"*{m.group(1)}*", text).replace("|", "/").strip()


def _diag(s: dict) -> str:
    return "no" if not s["has_diagnostic"] else ("untested" if s["separates"] is None else
                                                "separates" if s["separates"] else "does not separate")


def _range(xs, digits=3):
    xs = [x for x in xs if x is not None]
    return "–" if not xs else _num(min(xs), digits) if min(xs) == max(xs) else f"{_num(min(xs), digits)}–{_num(max(xs), digits)}"


def _check_targets(module, targets: list) -> None:
    """case.py TARGET_TIERS and en/targets.yaml name the same targets in the same tiers."""
    want = {t["id"]: tuple(t.get("tiers", module.ALL_TIERS)) for t in targets}
    if want != {k: tuple(v) for k, v in module.TARGET_TIERS.items()}:
        raise SystemExit(f"case.py TARGET_TIERS and en/targets.yaml disagree: {want} vs {module.TARGET_TIERS}")


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


def _bend_rows(case: NativeCase) -> list[list[str]]:
    """Per tier and fiscal year with a running period: the reference with its nulls replaced by the figures to date,
    scored with the habit relaxed (an approved exception), against the reference itself (quality 1), and what that
    gain nets in the final score under each policy that allows the bend (its quality share x the gain, less its
    soft-rule penalty)."""
    module, rows = case.module, []
    policies = _bending_policies()
    pools = case.param_candidates
    with tempfile.TemporaryDirectory() as tmp:
        for tier in case.tiers:
            base = case.at(tier, case.rule_seeds[0])
            for fy in pools["fy_start"][tier]:
                gains = []
                for dk in pools["dont_know_reward"][tier]:
                    c = base.with_params(fy_start=fy, dont_know_reward=dk)
                    rules = module.rules_of(c.setting)
                    if not rules.running:
                        continue
                    out = Path(tmp) / f"{tier}_{fy}_{dk}"
                    out.mkdir()
                    module._write(out, module._sheet(c.world, rules, to_date=True))
                    plain = c.evaluate(out, "en")
                    bent = c.evaluate(out, "en", relaxed=frozenset({"running_period"}))
                    assert plain["validity_score"] == 0.0 and bent["validity_score"] == 1.0, (tier, fy, dk)
                    gains.append(bent["quality_score"] - 1.0)
                if gains:
                    row = [tier, str(fy), ", ".join(rules.running), f"{len(rules.running)} of {len(rules.scored)}",
                           "+" + _range(gains)]
                    for _, share, penalty in policies:
                        net = [share * g - penalty for g in gains]
                        word = "pays" if min(net) > 0.005 else "loses" if max(net) < -0.005 else "about even"
                        row.append(f"{'+' if min(net) > 0.0005 else ''}{_range(net)} ({word})")
                    rows.append(row)
    return rows


def _robust_rows(case: NativeCase) -> list[list[str]]:
    """Per tier, over every admissible combination of its pools (not only the audit's settings): the sheet
    robust_solution writes (the fiscal year it guesses, what it answers, its rounding unit, the credit it expects
    and the credit it earns on average), and the sheet of the same search space that earns the most in hindsight."""
    module, rows = case.module, []
    month = case.param_labels()["fy_start"]

    def year(fy) -> str:
        return "none" if fy is None else month[fy]["en"]

    def answers(sheet: dict, unit: int) -> str:
        given = [q for q in module.QIDS if sheet[q] is not None]
        money = any(q in module.MONEY_Q for q in given)
        return (", ".join(given) or "nothing") + (f" ({unit:,} KRW)" if money else "")

    with tempfile.TemporaryDirectory() as tmp:
        for tier in case.tiers:
            base = case.at(tier, case.rule_seeds[0])
            pools = {name: list(by_tier[tier]) for name, by_tier in case.param_candidates.items()}
            settings = [c for c in (base.with_params(**dict(zip(pools, values)))
                                    for values in itertools.product(*pools.values())) if c.is_admissible()]
            out = Path(tmp) / tier
            out.mkdir()
            base.write_robust(out)
            written = json.loads((out / "answers.json").read_text(encoding="utf-8"))
            found = module._never_asking_sheets(base.world, pools)
            earned = {}                 # the same sheet is reached from several starts: score it once
            for i, (_, _, sheet) in enumerate(found):
                key = json.dumps(sheet, sort_keys=True)
                if key not in earned:
                    out = Path(tmp) / f"{tier}_{i}"
                    out.mkdir()
                    module._write(out, sheet)
                    results = [c.evaluate(out, "en") for c in settings]
                    earned[key] = sum(min(1.0, r["quality_score"]) if r["validity_score"] == 1.0 else 0.0
                                      for r in results) / len(settings)
            sheets = [(expected, earned[json.dumps(sheet, sort_keys=True)], fy, unit, sheet)
                      for expected, (fy, _, unit), sheet in found]
            expected, got, fy, unit, sheet = next(x for x in sheets if x[4] == written)
            best = max(sheets, key=lambda x: x[1])
            per_guess = {g: max(x[0] for x in sheets if x[2] == g) for g in [None, *pools["fy_start"]]}
            rows.append([tier, year(fy), answers(sheet, unit),
                         ", ".join(f"{year(g)} {_num(v)}" for g, v in per_guess.items()),
                         f"{_num(got)} (over {len(settings)})",
                         f"{_num(best[1])} (guess: {year(best[2])}; answers {answers(best[4], best[3])})"])
    return rows


def gt(case: NativeCase) -> str:
    module = case.module
    audit = json.loads((ROOT / "dataset" / "audit.json").read_text(encoding="utf-8"))
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    targets = yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))
    _check_targets(module, targets)
    spec = {t["id"]: t for t in targets}
    tiers = tier_order(audit["settings"])
    counts = {t: len(audit["settings"][t]) for t in tiers}
    th = audit["thresholds"]
    out = [
        f"# Ground truth: {case.id}", "",
        "The ground truth (GT) of a setting in five parts, with the reference as supporting evidence. Generated by "
        f"`gt_report.py` from `dataset/audit.json` (`fdebench2 audit-case`, public world seed {audit['world_seed']}): "
        f"{sum(counts.values())} settings, " + ", ".join(f"{t} {counts[t]}" for t in tiers) + " (each tier's public "
        "panel plus admissible parameter combinations). Damage is 1 − credit, credit = 0 for an invalid sheet, else "
        "the quality score clipped to [0, 1]; a target bites in a setting when misreading it alone loses at least "
        f"{th['ablation_min_damage']:.2f} of the credit (for a drawn parameter: its least harmful wrong candidate). "
        f"The sheet has twelve answers; {len(module.SCORED['easy'])} / {len(module.SCORED['medium'])} / "
        f"{len(module.SCORED['hard'])} of them are scored in easy / medium / hard.", "",
        "## 1. Client facts (targets)", "",
        "One row per target: the fact, the tiers where it is in force, how the audit misreads it (a drawn parameter: "
        "the reference written for each other candidate; another fact: the reference sheet with that one fact read "
        "the most natural wrong way, every other figure, the rounding and the nulls unchanged), the damage range "
        "over the settings where it is in force, the settings where it bites per tier (k/n) and whether its "
        "diagnostic (`enforced`, part 5) tells the reference from the misreading.", "",
    ]
    rows = []
    for t in target_summary(audit):
        tid = t["target"]
        s = spec[tid]
        if s.get("param"):
            how = f"the reference of each other candidate of `{s['param']}`"
        elif tid == "running_period":
            how = RUNNING_ABLATION
        else:
            how = next(iter(module.MISREADINGS[tid]))
        where = ", ".join(t["tiers"]) + (" (when " + "; ".join(f"{k} in {v}" for k, v in s["when"].items()) + ")"
                                         if s.get("when") else "")
        rows.append([f"`{tid}`", _fact(s["text"]), where, how, _range([t["low"], t["high"]]),
                     ", ".join(f"{tier} {k}/{n}" for tier, (k, n) in t["per_tier"].items()), _diag(t)])
    out += _table(["target", "fact", "in force", "ablation (the natural misreading)", "damage", "bites k/n",
                   "diagnostic"], rows)
    out += ["", "A scored question earns 2 when right, so one question a misreading gets wrong costs 2 of the "
            "(scored − running) × (2 − null reward) points between the all-null sheet and the reference: at least "
            "0.11 in hard, 0.12 in medium and 0.19 in easy. Every fact above moves at least one scored question in "
            "every tier where it is in force.", "",
            "Facts that are no longer targets (they stay in requirements.md, and the client still answers them when "
            "asked):", ""]
    out += [f"- {name}: {why}" for name, why in REMOVED]
    out += ["", "## 2. Validity checks (hard gates)", "",
            "A sheet that breaks any of these is invalid and earns no credit. `answers.json` that cannot be read as "
            "an object is fatal.", ""]
    rows = []
    for r in meta["rules"]:
        where = ", ".join(r.get("tiers", tiers)) + (" (when " + "; ".join(f"{k} in {v}" for k, v in r["when"].items())
                                                    + ")" if r.get("when") else "")
        rows.append([f"`{r['id']}`", r["class"], where, RULE_WHY[r["id"]]])
    out += _table(["rule", "class", "tiers", "why it is a hard gate"], rows)
    out += ["", "**Mandatory outputs.** Every question id Q01 to Q12, each a finite number or `null` "
            "(`answer_format`). Nothing else is mandatory: `null` is always an accepted answer and earns the null's "
            "reward, so abstaining is priced by the objective, not forbidden. The count gate "
            "(`exclude_test_accounts`) does not hold a count against a sheet when another reading of the export "
            "without test accounts gives the same count (the stored UTC dates, another fiscal year or window, other "
            "orders counted): only a figure that needs the test accounts breaks it.", "",
            "**The bendable habit.** `running_period` is the one business-policy rule. With an approved exception "
            "the rule is switched off and the figure to date is judged like any other answer; the policy then takes "
            "its soft-rule penalty off the final score ("
            + ", ".join(f"{penalty:g} under `{name}`" for name, _, penalty in _bending_policies())
            + "), in which quality is one component ("
            + ", ".join(f"{share:.0%} under `{name}`" for name, share, _ in _bending_policies())
            + " when every component applies). The table gives the reference sheet with its nulls replaced by the "
            "exact figures to date: its quality gain over the reference with the rule relaxed (the same for every "
            "null reward: k running questions of n scored add k / (n − k)), and what the bend nets in the final "
            "score of a sheet below the quality cap under each policy that allows it (the quality share × the gain "
            "− the penalty). So the bend pays in some settings and loses in others. A sheet already at the cap ("
            f"{meta.get('quality_cap')}) gains nothing, so for it the bend always loses the penalty; under an April "
            "year no period is running and there is nothing to bend.", ""]
    out += _table(["tier", "fiscal year starts in month", "running questions", "running of scored",
                   "quality gain when bent"] + [f"net in the final score, `{name}`" for name, _, _ in _bending_policies()],
                  _bend_rows(case))
    out += ["", "**Shortcuts.** The sheets a lazy or gaming analyst would send; each is invalid or scores at most "
            f"{th['shortcut_max_quality']:.1f} in every measured setting. The literal sheet (the request done exactly "
            "as written, `literal_solution`) breaks `report_rounding` in every setting and `running_period` where a "
            "period is running; its near misses keep one rule, or both. The last four were added by the check of "
            "this audit: the all-null sheet with one safe answer, the answers that need no client fact, the literal "
            "sheet with the one fact the export itself shows (its days are Korea-time days) and every rule kept, "
            "and the literal sheet made valid under every draw without knowing a parameter. They are closed but not "
            "worthless: `data_only` earns up to a third of the scale, which is what never asking is worth (part "
            "4).", ""]
    out += _table(["shortcut", "what it does", "closed", "best quality where valid"],
                  [[f"`{s['name']}`", s["description"], f"{s['closed']}/{s['settings']}", _num(s["best_quality"])]
                   for s in shortcut_summary(audit)])
    out += ["", "## 3. Objective (higher is better)", "",
            "objective = Σ over the scored questions of the answer's reward / (2 × scored questions):", "",
            "- **Right**: 2. The customer id and the counts (Q03, Q04, Q05, Q10) must match exactly; a money figure "
            "must be within 0.5% or half the rounding unit of the exact figure, whichever is wider, so the exact "
            "figure rounded as the rule requires always counts; the September change (Q11) within 0.05 percentage "
            "points; Q08 and Q12 within 0.5%.",
            "- **`null`** (\"not available yet\"): the drawn reward, 0.5, 1 or 1.5.",
            "- **Wrong**: 0. A wrong figure in the board pack has to be corrected at the next meeting; a gap only "
            "leaves a gap.",
            "- A question the round does not use counts neither way.", "",
            "**Uncertainty.** The reward for a null prices the analyst's own doubt: a figure is worth giving only "
            "when its chance of being right is above null reward / 2 (25%, 50% or 75%). The all-null sheet is the "
            "baseline (quality 0), so abstaining everywhere earns nothing and a wrong figure costs null reward / "
            "(2 − null reward) of a right one (a third, one, or three). One kind of question has no figure at all: a "
            "period that is still running on the reference date (the first half of FY2026 under a July year; its "
            "first quarter too under a September year). Finance shows \"not available yet\" for it, so `null` is the "
            "right answer there, and the most a valid sheet earns on it is the null's reward.", "",
            "## 4. Reference and bounds", "",
            "- **Reference** (`reference_solution`): a careful analyst who knows every one of the setting's "
            "conventions. Each scored question's exact figure, money rounded to the setting's unit; `null` for the "
            "questions the round does not use and for a period still running. (Before the audit it missed the "
            "category rename on purpose, so that the reward for a null changed its sheet in hard; it now enforces "
            "every fact in force.)",
            "- **Baseline** (quality 0, `baseline_solution`): \"not available yet\" for every question, what finance "
            "reports without an analyst.",
            "- **Best known** (`best_known_solution`): the answer key for all twelve questions, whether the round "
            "uses them or not: another sheet than the reference in easy and medium, with the same objective.",
            "- **Bound** (`objective_bound`, proven): a scored question earns at most 2, and one whose period is "
            "still running at most the null's reward, because a number there breaks `running_period`. The reference "
            "reaches it: the gap is 0 in every measured setting. Its scope is every valid sheet, the habit kept: a "
            "figure to date makes the sheet invalid, so it cannot beat the bound. A sheet that bends the habit under "
            "an approved exception is judged with the rule off and ends above it (quality up to 1 + k / (n − k), the "
            "table in part 2); the quality cap of 1.0 stops there, so a bent sheet earns no more quality credit than "
            "the reference and pays the penalty, and the reference keeps full credit without an exception.", ""]
    known = [b["best_known_quality"] for b in audit["bounds"] if b["best_known_quality"] is not None]
    gaps = [b["gap_to_bound"] for b in audit["bounds"] if b["gap_to_bound"] is not None]
    out += [f"- **quality_cap** = {meta.get('quality_cap')}: the best known quality is {_range(known)} over the "
            f"measured settings (median {median(known):.3f}), and the bound is {max(gaps):.1%} above the reference, "
            "so a sheet as good as the reference earns full credit and no valid sheet scores above it.", ""]
    out += _table(["setting", "reference", "baseline", "span", "best known", "its quality", "bound", "bound quality",
                   "gap ref–bound"],
                  [[b["setting"], _num(b["reference"], 4), _num(b["baseline"], 3), _num(b["span"]),
                    _num(b["best_known"], 4), _num(b["best_known_quality"]), _num(b["bound"], 4),
                    _num(b["bound_quality"]), _num(b["gap_to_bound"])] for b in audit["bounds"]])
    out += ["", "**Value of asking** (the GT's claim that the client must be asked): per tier, the best sheet that "
            "never asks against the reference of each setting. `never asks, knows the fixed facts` is the best of "
            "the other settings' references and the baseline (it measures the drawn parameters only); `never asks "
            "(robust)` is `robust_solution`, written from the agent's view and the tier's pools alone. It reads the "
            "export as the literal sheet does (the pantry label, completed orders, test accounts out, revenue without "
            "tax at the order date's rate), except for the days, which it reads off the export itself: the sale-day "
            "surge starts at 15:00 UTC on the eve and the export's last order falls before 15:00 UTC on the reference "
            "date, so the days are Korea-time days. It knows the rules as rules, not their draw: money off the "
            "client's unit, or a number for a period still running under the client's fiscal year, makes a sheet "
            "unusable. Every fiscal-year start, window, rounding unit and reward for a null in the pools is equally "
            "likely to it, and all twelve questions count. It starts from one guess of the fiscal year (or none: a "
            "fiscal-period question then gets a figure only when more than one fiscal year of the pool gives it), "
            "one window (or none) and one rounding unit, leaves null one answer at a time while that raises its "
            "expected credit, and delivers the sheet that expects the most. What it earns comes from the answers "
            "that need no client fact (the sale-day orders, the September change, the units per order) and from its "
            "fiscal-year guess where that is right; its pantry label is wrong in every setting.", ""]
    out += _table(["tier", "never asks, knows the fixed facts", "value of the parameters", "never asks (robust)",
                   "value of asking"],
                  [[tier, _num(v["never_asks_params"]), _num(v["voi_params"]), _num(v["never_asks"]), _num(v["voi"])]
                   for tier, v in ((t, audit["voi"][t]) for t in tier_order(audit["voi"]))])
    out += ["", "The sheet `robust_solution` writes, measured over every combination of the tier's pools (the table "
            "above is over the audit's settings), and the sheet of its search space that earns the most in "
            "hindsight. The best sheets of the guesses expect nearly the same credit (fourth column), so which one "
            "is delivered is close to a coin toss; no sheet of the search space earns more than the last column:", ""]
    out += _table(["tier", "fiscal year it guesses", "what it answers (money rounded to)",
                   "credit expected, best sheet per guess", "credit it earns",
                   "best of its search space in hindsight"], _robust_rows(case))
    out += ["", "## 5. Diagnostic cases", "",
            "`diagnose()` reports `enforced[target]` and a line of evidence for every target in force, for valid and "
            "invalid sheets alike, from the sheet's own figures (a run's scoring and the audit ask for it; the "
            "validator does not). The diagnostic cases are the scored questions where only that fact decides the "
            "figure: the export is computed under every other reading (a fiscal year from each other month, the "
            "other naming, each misreading of a fixed fact listed in case.py `MISREADINGS` and its `VARIANTS`, "
            "other active windows), and a question tells a reading from the client's when that reading's figure, "
            "exact or rounded to the unit, would be scored wrong. A right answer there counts for the fact (not "
            "where only a variant differs: staying clear of US time says little about Korea time). A wrong figure "
            "counts against "
            "the one fact whose reading gives it as a sheet would write it (rounded to the unit or to two decimals, "
            "or within 0.1%: five times tighter than the scorer's tolerance), the nearest when several do; a figure "
            "that two facts' readings give alike, or that no single reading explains, tells nothing. A fact is not "
            "enforced when more questions carry some misreading's figure than the client's, enforced when some "
            "carry the client's, and not determinable otherwise.", ""]
    ref_fail = {tid: [e["label"] for tier in tiers for e in audit["settings"][tier]
                      if not e.get("skipped") and e["reference_enforced"].get(tid) is False] for tid in spec}
    rows = []
    for t in target_summary(audit):
        tid = t["target"]
        bad = sorted(set(t["undiagnosed"]) | set(ref_fail[tid]))
        rows.append([f"`{tid}`", DIAGNOSTIC.get(tid, FIGURES), _diag(t), ", ".join(bad) or "–"])
    out += _table(["target", "what tells a correct sheet from the misreading", "result", "settings where it fails"],
                  rows)
    out += ["", "**Reliability on other deliverables.** A run's \"enforced\" stage applies the diagnostic to the "
            "agent's sheet, which is neither the reference nor an ablation. Per target, the settings where it calls "
            "a deliverable not enforced, of those where it gives a verdict: the best known solution (valid and built "
            "with every fact of its setting, so each False would be a false negative), the ablations of the target "
            "that also flag another target (of the settings where the ablation bites; it misreads only its own "
            "fact), and the baseline (each setting's own; all null, so it gives a verdict only on the running "
            "periods) and `robust_solution` (its tier's), which do not know every fact, so a False there may be "
            "right.", ""]
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


# The question an engineer would naturally ask, and how to find the passage of requirements.md the client answers
# from in every locale: every token must occur in the passage (a bullet with its indented lines, or a paragraph); a
# dict token gives the words per locale; "first" takes the first passage that matches, "all" every one.
QUESTIONS = {
    "fiscal_year": ("When does your fiscal year start?", ["{{fy_start}}"], "first"),
    "fy_naming": ("Is FY2025 the year that starts in 2025 or the one that ends in 2025?", ["{{fy2025}}"], "first"),
    "running_period": ("Some of the periods you ask about are not over on the reference date: do you want the figure "
                       "to date?",
                       ["Q07", {"en": "CFO", "zh": "首席财务官", "ko": "CFO", "ja": "CFO", "es": "director financiero"},
                        "`null`"], "all"),
    "local_day": ("The timestamps are in UTC: which time zone decides the day an order or a sign-up belongs to?",
                  ["UTC+9"], "first"),
    "test_accounts": ("accounts_meta has test and staff accounts: which of them count as customers?",
                      ["`accounts_meta.csv`", "`account_type`"], "first"),
    "counted_orders": ("Which order statuses count, and what about cancelled orders that were paid?",
                       ["`payments.csv`", {"en": "`completed`", "zh": "`已完成`", "ko": "`완료`", "ja": "`完了`",
                                           "es": "`completado`"}], "first"),
    "revenue_ex_tax": ("Is net revenue before or after tax, and do refunds come off with or without their tax?",
                       ["`amount × subtotal / total`"], "first"),
    "refund_period": ("Does a refund reduce the revenue of the period of the order or of the period of the refund?",
                      [{"en": "Which period a refund belongs to", "zh": "退款归属哪个期间", "ko": "환불이 속하는 기간",
                        "ja": "返金を計上する期間", "es": "A qué periodo pertenece un reembolso"}], "first"),
    "late_refunds": ("refunds.csv has refunds dated after the reference date: do they count?", ["2026-10-31"],
                     "first"),
    "fx_order_date": ("Which exchange rate converts the yen and dollar orders to KRW?", ["`krw_per_unit`"], "first"),
    "active_customer": ("What makes a customer \"active\" on the reference date?", ["{{active_days}}"], "first"),
    "category_rename": ("products.csv has a snacks and a pantry category: which products does \"pantry\" cover?",
                        ["2025-10-01"], "first"),
    "report_rounding": ("To what precision should money figures be reported?", ["{{rounding_unit}}"], "first"),
}
# What the scorer uses, as it must read in the passage, per target.
SCORER = {
    "running_period": ["null", "Q07"],
    "local_day": ["UTC+9"],
    "revenue_ex_tax": ["subtotal", "total"],
    "late_refunds": ["2026-10-31"],
    "category_rename": ["2025-10-01"],
    "active_customer": ["2026-09-30"],
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


def _tokens_of(text: str, labels: dict[str, str]) -> list[str]:
    """The tokens a translation must keep, written the same way in every locale: parameters, question ids, dates,
    clock times, numbers of 10 and more or with a decimal (es writes 0,5; a month number, 10月, is left out), and
    what stands in backticks (a file, column or JSON name as it is; a localized data label as the label it stands
    for)."""
    out = set(re.findall(r"\{\{\w+\}\}", text))
    for code in re.findall(r"`([^`]+)`", text):
        out.add(f"`label:{labels[code]}`" if code in labels else f"`{code}`")
    t = re.sub(r"`[^`]+`|\{\{\w+\}\}", " ", text)
    out |= set(re.findall(r"\d{4}-\d{2}-\d{2}", t))
    t = re.sub(r"\d{4}-\d{2}-\d{2}", " ", t)
    out |= set(re.findall(r"(?<![0-9A-Za-z_])Q\d{2}(?![0-9])", t)) | set(re.findall(r"UTC\+\d+", t))
    out |= set(re.findall(r"\d{1,2}:\d{2}", t))
    t = re.sub(r"Q\d{2}|UTC\+\d+|FY\d{4}|\d{1,2}:\d{2}", " ", t)
    t = re.sub(r"\d{1,2} ?[月월]", " ", t)                    # a month, which en and es write as a word
    t = re.sub(r"(\d),(\d{1,2})(?!\d)", r"\1.\2", t)          # a decimal comma
    out |= {n for n in re.findall(r"(?<![0-9A-Za-z_.])\d+(?:\.\d+)?(?![0-9A-Za-z_])", t) if "." in n or float(n) >= 10}
    return sorted(out)


def client_review(case: NativeCase) -> str:
    module = case.module
    texts = {lang: (ROOT / "locales" / lang / "requirements.md").read_text(encoding="utf-8") for lang in LANGS}
    targets = yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))
    labels = {lang: {words[lang]: key for key, words in module.L.items()} for lang in LANGS}

    def find(lang, spec, which):
        toks = [t[lang] if isinstance(t, dict) else t for t in spec]
        hits = [p for p in _passages(texts[lang]) if all(t in p for t in toks)]
        return hits[:1] if which == "first" else hits

    out = ["# Client answers: human review", "",
           "The simulated client answers only from `locales/<lang>/requirements.md` (plus event facts; this case has "
           "none). For every target: the question an engineer would naturally ask, the passage each locale answers "
           "from (quoted as written, with setting markers and parameters; a parameter is worded per locale by "
           "`params.<name>.labels` in case.yaml or by `derive_params` in case.py), a machine pre-check and an empty "
           "verdict for a human reviewer. Generated by `gt_report.py`.", "",
           "Pre-check: (1) the passage is found in all five locales; (2) the same parameters, question ids, dates, "
           "numbers and names in backticks in every locale (decimal commas normalized; a data label such as "
           "`completed` is compared as the label it stands for, since the data is localized); (3) the values the "
           "scorer uses appear in every locale; (4) the other targets whose passage is the same one, i.e. what the "
           "passage would answer beyond the question (the client may state them together when asked).", "",
           "**Status: awaiting human review.** No passage below has been reviewed by a person yet.", ""]
    by_target = {t["id"]: {lang: find(lang, *QUESTIONS[t["id"]][1:]) for lang in LANGS} for t in targets}
    for t in targets:
        tid = t["id"]
        found = by_target[tid]
        scope = ", ".join(t["tiers"]) if t.get("tiers") else ""
        if t.get("when"):
            scope = "; ".join(x for x in (scope, "when " + "; ".join(f"{k} in {v}" for k, v in t["when"].items())) if x)
        out += [f"## `{tid}`" + (f" ({scope})" if scope else ""), "",
                f"**Question.** {QUESTIONS[tid][0]}", "", f"**Target (en).** {t['text']}", ""]
        for lang in LANGS:
            out += [f"**{lang}:**", ""]
            for p in found[lang] or ["(not found)"]:
                out += ["> " + line for line in p.splitlines()] + [">"]
            if out[-1] == ">":
                out.pop()
            out.append("")
        checks = []
        missing = [lang for lang in LANGS if not found[lang]]
        uneven = [lang for lang in LANGS if len(found[lang]) != len(found["en"])]
        checks.append("passage found in every locale" + (f" ({len(found['en'])} passages each)" if len(found["en"]) > 1
                                                          else "") if not missing and not uneven else
                      f"NOT FOUND in {', '.join(missing)}" if missing else f"passage count differs in {', '.join(uneven)}")
        toks = {lang: _tokens_of("\n".join(found[lang]), labels[lang]) for lang in LANGS if found[lang]}
        ref = toks.get("en", [])
        diff = {lang: (sorted(set(ref) - set(n)), sorted(set(n) - set(ref))) for lang, n in toks.items()
                if set(n) != set(ref)}
        checks.append("tokens differ from en: " + "; ".join(f"{lang} lacks {a or '–'}, adds {b or '–'}"
                                                             for lang, (a, b) in diff.items()) if diff else
                      "same parameters, question ids, dates, numbers and names in all five locales: "
                      + (", ".join(ref) or "none"))
        want = SCORER.get(tid, [])
        if want:
            lacking = {lang: [w for w in want if w not in "\n".join(found[lang])] for lang in toks}
            lacking = {k: v for k, v in lacking.items() if v}
            checks.append("scorer values present in every locale (" + ", ".join(want) + ")" if not lacking else
                          "scorer values missing: " + "; ".join(f"{k} {v}" for k, v in lacking.items()))
        same = [o for o, f in by_target.items() if o != tid and f["en"] and found["en"]
                and set(f["en"]) & set(found["en"])]
        checks.append("the passage also states: " + (", ".join(f"`{o}`" for o in same) if same else
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
