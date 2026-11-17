"""Write GT.md (the case's ground truth in five parts) from dataset/audit.json, case.yaml and the targets.

Run from the repository root after `fdebench2 audit-case`:
    python cases/public_sector/benefits_eligibility_officer/gt_report.py
Every number in the audit's tables comes from the stored audit (the public world). The tables the audit does not hold
(the literal solution's readings, what a slip costs, the attempts to beat the never-asks solver, the renewal practice
bent, the diagnostic on other deliverables, the bend on world seeds 1-3) are measured here with case.py on the
audit's own settings. GT.md never quotes the audit's fingerprint, so writing it again after a fresh audit gives the
same file.
"""

from __future__ import annotations

import json
import sys
import tempfile
from itertools import combinations
from pathlib import Path
from statistics import mean, median

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))

from fdebench2.audit import (cross_flag_summary, false_negatives, findings, measured_settings,  # noqa: E402
                             shortcut_summary, summarize, target_summary, tier_order)
from fdebench2.cases import NativeCase  # noqa: E402

BEND = frozenset({"auto_approve_renewals"})
RELAXABLE = frozenset({"auto_approve_renewals"})      # the business_policy rules

RULE_WHY = {
    "residency_requirement": "statutory: a household short of the residency period may not be paid at all, whatever "
                             "anyone asks (physical: no exception bends it)",
    "asset_limit": "the scheme's condition: approving a household above the limit pays someone the law excludes",
    "amount_cap": "budget law: no amount may exceed the cap for the household size (physical)",
    "reason_code_required": "every determination is a decision letter: an approval must say whether it is a renewal, "
                            "a refusal must name one of the three tests (mandatory output)",
    "auto_approve_renewals": "the office's practice, to keep the queue moving (business policy): hard under the "
                             "baseline policy, bendable with the director's exception under the others, and then "
                             "priced (part 4)",
}
# What the diagnostic reads for each target (case.py diagnostic, alternatives).
TELLS = {
    "earned_disregard": "the amounts of the households with earnings, against each other candidate disregard, the "
                        "candidates' figures crossed (the first 100 and 30% of the rest, ...), the disregard once per "
                        "household, on the applicant's earnings only, and none",
    "residency": "decisions (and a refusal's reason) of the households between two candidate periods, and of those "
                 "between the period in days and in calendar months",
    "uprating": "the amounts against each other candidate's table, last year's table and a guessed uprating of 1% "
                "to 8% in steps of 0.5",
    "renewals": "every renewal: approved at exactly last year's amount or not (one re-assessed is enough)",
    "assets_out_of_round": "decisions of the households above an asset limit any medium candidate draws",
    "supplement_out_of_round": "the amounts of the households with a disabled member at the address",
    "child_support_out_of_round": "the amounts of the households that receive child support",
    "changes_out_of_round": "the households that reported a change: every change applied, or those in effect",
    "circular_out_of_round": "the amounts of the applications dated on or after 1 October 2026",
    "asset_limit": "decisions (and a refusal's reason) of the households between two candidate limits, and of those "
                   "every car or no car exempt would decide otherwise",
    "disability_supplement": "the amounts of the households with a disabled member at the address: another "
                             "candidate, no supplement, or a guessed 100, 120 or 180",
    "child_support": "the amounts of the households that receive child support",
    "amount_cap": "the capped amounts: no cap, or another candidate table",
    "reported_changes": "the households that reported a change: every change applied, or none",
    "exception_requests": "the councillor's family (approved or not) and the letter writer's amount (her child "
                          "support counted or not, read only when the deliverable counts child support elsewhere); "
                          "one given in to is enough",
}
NOT_TARGETS = [
    ("`household_size` (only members at the address count; members living elsewhere are ignored entirely)",
     "the natural reading of the `lives_at_address` column: the literal solution and the never-asks solver read it "
     "right without asking. It stays in requirements.md, and the client's worksheet gets it wrong (it counts the "
     "earnings of adults living elsewhere), so it is part of the scale; counting those earnings costs {away}."),
    ("`need_formula` (standard amount + rent up to the housing maximum; need − income, rounded down; 0 or less is "
     "a refusal)", "the natural reading of the table's two columns and the leaflet; the literal solution does it."),
    ("`scoring` (pay exactly, decisions matter most; a refusal names the first failing test in the order residency, "
     "assets, income)", "the goal changes no exact answer, and the order is the order of the codes: reading income "
     "first costs {order}. Both stay in requirements.md and in the objective."),
    ("`cap_out_of_round` (easy: no cap this round)", "nothing the agent sees names a cap, so no cap is the natural "
     "reading; applying the 1,050 table costs {cap}."),
    ("`heating_supplement` (hard: the circular's 60 from 1 October 2026)", "an official circular in the folder, "
     "dated and worded precisely: the natural reading applies it (the literal solution does). The fact to be told is "
     "that easy and medium leave it aside (`circular_out_of_round`); leaving it out in hard would cost {heating}."),
    ("the details of the asset test (the home and the most valuable car exempt) and the date format", "the "
     "leaflet's \"your home and a car you need are treated fairly\" and the dates (165 of 300 application dates have "
     "a day above 12) give them; they stay in requirements.md, and the diagnostic of `asset_limit` and `residency` "
     "weighs the other readings."),
    ("what an exception to the renewal practice costs (the whole queue at 200 a household)", "it matters only under "
     "an approved exception, which no ablation can hold; it is a trade-off the client states, measured in part 4."),
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


def _evaluate(case, module, rows, relaxed=frozenset()):
    """(valid, quality, objective, raw) of a deliverable under a setting."""
    with tempfile.TemporaryDirectory() as tmp:
        module._write(Path(tmp), rows)
        res = case.evaluate(Path(tmp), "en", relaxed=relaxed)
        raw = module.score(case.world, Path(tmp), case.setting)
    valid = res["validity_score"] == 1.0
    return valid, (res["quality_score"] if valid else None), res.get("objective"), raw


def _credit(valid, quality):
    return min(max(quality, 0.0), 1.0) if valid else 0.0


def _dropped(measured, module, world):
    """The damage of the misreadings of the facts that are no longer targets, over the measured settings where they
    apply: "low–high (bites k of n)"."""
    found: dict[str, list[float]] = {}
    for tier, cases in measured.items():
        for _, case in cases:
            r = module.rules_of(case.setting)
            key = module.determinations(world, r)
            amount = {h.id: module.amount_due(h, r) for h in world.households}
            income_first = [[row[0], row[1], row[2], "DENY_INCOME"] if row[1] == "no" and amount[row[0]] <= 0 else row
                            for row in key]
            docs = {"order": income_first,
                    "away": module.determinations(world, module.replace(r, away_earnings="adults"))}
            if tier == "easy":
                docs["cap"] = module.determinations(world, module.replace(r, cap=module.CAP_TABLES[1050]))
            if tier == "hard":
                docs["heating"] = module.determinations(world, module.replace(r, circular=False))
            for name, doc in docs.items():
                found.setdefault(name, []).append(1 - _credit(*_evaluate(case, module, doc)[:2]))
    return {name: f"{_range(v)} of the scale (bites in {sum(x >= 0.1 for x in v)} of {len(v)} settings)"
            for name, v in found.items()}


def _measured(audit, base):
    """{tier: [(label, case)]}: the audit's measured settings, rebuilt from their parameters."""
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
    base = NativeCase(ROOT)
    module, world = base.module, base.world
    tiers = tier_order(audit["settings"])
    measured = _measured(audit, base)
    n_settings = sum(len(v) for v in measured.values())
    new = [h for h in world.households if not h.renewal]
    renewals = [h for h in world.households if h.renewal]
    out = [
        "# Ground truth: public_sector/benefits_eligibility_officer",
        "",
        "The ground truth (GT) of a setting in five parts, with the reference as supporting evidence. Generated by "
        f"`gt_report.py` from `dataset/audit.json` (`fdebench2 audit-case`, public world seed {audit['world_seed']}): "
        f"{n_settings} settings, " + ", ".join(f"{t} {len(measured[t])}" for t in tiers) + " (each tier's public "
        "panel plus admissible parameter combinations). Damage is 1 − credit, credit = 0 for an invalid batch, else "
        "the quality score clipped to [0, 1]; a target bites in a setting when misreading it alone loses at least "
        f"{audit['thresholds']['ablation_min_damage']:.2f} of the credit (for a drawn parameter: its least harmful "
        f"wrong candidate). The batch has {len(world.households)} applications: {len(new)} new ones and "
        f"{len(renewals)} renewals.",
        "",
        "## 1. Client facts (targets)",
        "",
        "One row per target: the fact, the tiers where it is in force, how the audit misreads it (a drawn parameter: "
        "the answer key of each other candidate; another fact: the answer key with that one fact read the most "
        "natural wrong way from what the agent sees, `case.py misreadings`), the damage range over the settings where "
        "it is in force, the settings where it bites per tier (k/n) and whether its diagnostic (part 5) tells the "
        "reference from the misreading.",
        "",
    ]
    misread = {}
    for _, case in sum(measured.values(), []):
        misread.update({t: label for t, (label, _) in module.misreadings(case.setting).items()})
    misread["renewals"] = "every renewal re-assessed under this year's rules (the request read as \"decide every " \
                          "application\")"
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
    summary = {t["target"]: t["per_tier"] for t in target_summary(audit)}

    def bites(target):
        return ", ".join(f"{k} of {n} {t} settings" for t, (k, n) in summary[target].items())
    upr = sorted(round(float(v) * 10) for v in module.POOLS["uprating"]["hard"])
    steps = [(module.table(n, a)[0] - module.table(n, b)[0], sum(module.table(n, a)) - sum(module.table(n, b)))
             for n in range(1, 7) for a, b in zip(upr[1:], upr)]
    out += ["", "Why they bite: every household is measured against its entitlement under the setting's rules, so a "
            "misread fact costs every household it touches, in money and in wrong decisions, and the scale runs from "
            "the client's own worksheet (0) to the answer key (1). The drawn figures bite least, on their least "
            f"harmful wrong candidate: `uprating` (candidates {(upr[1] - upr[0]) / 10:g} points apart, "
            f"{min(x for x, _ in steps)} to {max(y for _, y in steps)} a household of one to six) bites in "
            + bites("uprating") + "; `disability_supplement` (candidates 80 apart, on the households with a disabled "
            "member at the address) in " + bites("disability_supplement") + ". The supplement is misread as a wrong "
            "amount, not left out altogether: the leaflet's paragraph on how the amount is worked out says members "
            "with a disability may receive extra support, so an engineer who does not ask knows there is one and "
            "lacks only its amount, and the never-asks solver includes it (REVIEW.md, ground truth check, has the "
            "pools before the check and why they changed).", "",
            "Facts that are no longer targets (they stay in requirements.md, and the client still answers them when "
            "asked):", ""]
    dropped = _dropped(measured, module, world)
    out += [f"- {what}: {why.format(**dropped)}" for what, why in NOT_TARGETS]

    # ── 2. validity ──
    out += ["", "## 2. Validity checks (hard gates)", "",
            "A batch that breaks any of these is invalid and earns no credit. A file that cannot be read (no "
            "`determinations.csv`, an unknown or repeated household id, a missing row, a decision other than yes or "
            "no, a negative amount) is fatal.", ""]
    out += _table(["rule", "class", "tiers", "why it is a hard gate"],
                  [[f"`{r['id']}`", r["class"], ", ".join(r.get("tiers", tiers)), RULE_WHY[r["id"]]]
                   for r in meta["rules"]])
    out += ["", "**Shortcuts.** The degenerate batches a lazy or gaming agent would try; each is invalid or scores at "
            f"most {audit['thresholds']['shortcut_max_quality']:g} in every measured setting but one, which is known "
            "and open (below). The `worksheet_*` ones copy the client's own way (the baseline) and change one thing, "
            "every thing the worksheet does differently in the setting in turn (a shortcut that changes nothing in a "
            "tier is not measured there), print this year's figures on it, exploit the objective's arithmetic (a "
            "token award instead of a refusal for income) or change the two things that recover the most.", ""]
    out += _table(["shortcut", "what it does", "closed", "best quality where valid"],
                  [[f"`{s['name']}`", s["description"], f"{s['closed']}/{s['settings']}", _num(s["best_quality"])]
                   for s in shortcut_summary(audit)])
    # the open shortcut's family: every pair of the worksheet's differences, and its two halves
    pairs: dict[str, dict] = {}
    halves: dict[str, list] = {}
    counts: set[int] = set()
    for tier, cases in measured.items():
        for _, case in cases:
            r, w = module.rules_of(case.setting), module.worksheet_rules(case.setting)
            changes = {name: module._delta(w, reading) for name, (_, reading)
                       in module.worksheet_changes(case.setting).items() if name != "guessed_uprating"}
            counts.add(len(changes))
            for a, b in combinations(sorted(changes), 2):
                if not set(changes[a]) & set(changes[b]):
                    doc = module.determinations(world, module.replace(w, **changes[a], **changes[b]))
                    pairs.setdefault(tier, {}).setdefault((a, b), []).append(
                        _credit(*_evaluate(case, module, doc)[:2]))
            form = module.replace(w, disregard_on=r.disregard_on, away_earnings=r.away_earnings,
                                  residency_months=r.residency_months)
            figures = module.replace(w, uprating=r.uprating, earned_flat=r.earned_flat,
                                     earned_ignored=r.earned_ignored, cap=r.cap, disability=r.disability,
                                     child_support=r.child_support, circular=r.circular, changes=r.changes)
            qf, qg = (_credit(*_evaluate(case, module, module.determinations(world, x))[:2]) for x in (form, figures))
            halves.setdefault(tier, []).append((qf, qg))
    best_two = next(s for s in shortcut_summary(audit) if s["name"] == "worksheet_best_two_changes")
    single = max((s["best_quality"] or 0) for s in shortcut_summary(audit)
                 if s["name"].startswith("worksheet_") and s["name"] not in (
                     "worksheet_best_two_changes", "worksheet_this_years_figures", "worksheet_never_refuses_income"))
    rows = []
    for tier in tiers:
        top = max(pairs[tier].items(), key=lambda kv: max(kv[1]))
        over = sum(max(v) > 0.5 for v in pairs[tier].values())
        rows.append([tier, str(len(pairs[tier])), str(over), f"{_num(max(top[1]))} (`{top[0][0]}` + `{top[0][1]}`)",
                     _range([f for f, _ in halves[tier]]), _range([g for _, g in halves[tier]]),
                     _range([f + g for f, g in halves[tier]])])
    out += ["", f"**Known and open: `worksheet_best_two_changes`** ({best_two['closed']}/{best_two['settings']} "
            f"closed, best {_num(best_two['best_quality'])}; listed in `validate.OPEN_AUDIT_FINDINGS`). Copying the "
            "worksheet and changing any one of its differences reaches at most "
            f"{_num(single)}, but some pairs pass 0.5: the worksheet's two habits of reading the form (the disregard "
            "box for the applicant only, the earnings of adults living elsewhere counted) are each a quarter to two "
            "fifths of the scale, and so are this year's table and the supplement line. Every pair of differences, "
            "per tier, and the worksheet's two halves: *form* fixes the three reading habits (every earner's "
            "disregard, members living elsewhere left out, residency in days) and keeps last year's figures; "
            "*figures* puts this year's figures and lines on it (table, disregard, cap, supplement, child support, "
            "in hard the circular and the changes in effect) and keeps the habits.", ""]
    out += _table(["tier", "pairs", "pairs above 0.5 somewhere", "best pair", "form: quality", "figures: quality",
                   "form + figures"], rows)
    both = [f + g for tier in tiers for f, g in halves[tier]]
    near = sum(max(f, g) >= 0.45 for tier in tiers for f, g in halves[tier])
    out += ["", f"The two halves add to {_range(both)} (median {median(both):.2f}): the worksheet's differences "
            "interact little, so one half or the other is near half the scale or above in "
            f"{near} of the {len(both)} settings. A pair stays under 0.5 everywhere only if the scale is spread over "
            "many differences of similar weight, and this worksheet has "
            f"{min(n for n in counts)} to {max(n for n in counts)} that change the batch (one change of a tier's list "
            "can leave it as it is). Narrowing the two reading "
            "habits (the couple's disregard, only a partner's earnings) moves the excess to this year's figures "
            "(REVIEW.md, ground truth check), so the pair is listed as open rather than closed by a worse worksheet."]

    # the literal solution and its next readings
    literal, bendable = {}, {}
    for tier, cases in measured.items():
        for _, case in cases:
            r = module.rules_of(case.setting)
            readings = {
                "as delivered": module.determinations(world, module.LITERAL_RULES, reassess=True),
                "renewals rolled over, a 90-day wait guessed": module.determinations(
                    world, module.replace(module.LITERAL_RULES, residency_days=90)),
                "renewals rolled over, a 180-day wait guessed": module.determinations(
                    world, module.replace(module.LITERAL_RULES, residency_days=180)),
                "renewals rolled over, a 365-day wait guessed": module.determinations(
                    world, module.replace(module.LITERAL_RULES, residency_days=365)),
                "every rule it breaks kept (renewals, residency, assets, cap of the setting)": module.determinations(
                    world, module.replace(module.LITERAL_RULES, residency_days=r.residency_days,
                                          asset_limit=r.asset_limit, cap=r.cap)),
            }
            for name, doc in readings.items():
                for relaxed in (frozenset(), RELAXABLE):
                    valid, q, _, _ = _evaluate(case, module, doc, relaxed)
                    x = literal.setdefault((name, bool(relaxed)), {}).setdefault(tier, [0, 0, []])
                    x[0] += valid
                    x[1] += 1
                    if valid:
                        x[2].append(q)
            valid, q, _, _ = _evaluate(case, module, readings["as delivered"],
                                       RELAXABLE | {"residency_requirement"})
            bendable.setdefault(tier, []).append(q if valid else None)
    out += ["", "**The literal solution** (`literal_solution`: the request done as written, the same in every "
            "setting) decides every application, renewals included, with what the agent's view gives: last year's "
            "table, every income in full, the circular applied, every reported change at its latest value, no "
            "residency wait, no asset test, no cap. Its next most natural readings, measured here: a residency wait "
            "guessed from the leaflet's \"newcomers may need to wait a while\", the renewals rolled over (the data "
            "gives last year's amount for exactly them), and every rule it breaks kept. Valid settings and the best "
            "quality where valid, per tier, as delivered and with `auto_approve_renewals` relaxed (the only "
            "business_policy rule).", ""]
    rows = []
    for (name, relaxed), by_tier in literal.items():
        rows.append([name, "relaxed" if relaxed else "as delivered"]
                    + [f"{by_tier[t][0]}/{by_tier[t][1]}, {_num(max(by_tier[t][2])) if by_tier[t][2] else '–'}"
                       for t in tiers])
    out += _table(["literal reading", "rules"] + [f"{t}: valid, best quality" for t in tiers], rows)
    kept = [q for tier in tiers for q in literal[("every rule it breaks kept (renewals, residency, assets, cap of the "
                                                  "setting)", False)][tier][2]]
    out += ["", "The literal batch pays last year's table minus every income, earnings included. It is invalid as "
            "delivered and relaxed alike: approving recent arrivals breaks the statutory residency rule (statutory "
            "in all five locales' requirements: a physical rule no exception bends), and from medium it also "
            "approves households above the asset limit and pays above the cap. Were residency bendable (the "
            "business_policy class it had before the audit), the literal batch relaxed would score "
            f"{_range(bendable['easy'])} in easy (valid there) and still break the asset limit or the cap in "
            f"{sum(q is None for t in tiers if t != 'easy' for q in bendable[t])} of the "
            f"{sum(len(bendable[t]) for t in tiers if t != 'easy')} medium and hard settings. With every rule it "
            f"breaks kept it is valid and reaches at most {_num(max(kept))}, about the worksheet's own level."]

    # ── 3. objective ──
    slip, lapsed = {}, []
    for tier, cases in measured.items():
        for _, case in cases:
            key = module.truth(world, module.rules_of(case.setting))
            paid = [key[h.id][1] for h in new if key[h.id][0]]
            lapsed.append(sum(not key[h.id][0] for h in renewals))
            span = case.baseline_objective - case.reference_objective
            slip.setdefault(tier, []).append((module.WRONG_DECISION_PENALTY + median(paid)) / span)
    out += ["", "## 3. Objective (lower is better)", "",
            "The client's own measure, in its payment units, over every household:", "",
            "- **|paid − entitlement|**: the amount paid (0 when refused) against the household's true entitlement "
            "under this year's rules of the setting.",
            "- **400 per wrong yes/no**: a household approved that does not qualify, or refused that does.",
            "- **100 per wrong reason**: a household rightly refused with a code other than the first test it fails "
            "(residency, assets, income).",
            f"- **Renewals** are measured against their entitlement this year too. A valid batch rolls every one "
            f"over at last year's amount, so what that costs (`practice_cost`: {len(renewals)} renewals, "
            f"{_range(lapsed, 0)} of which no longer qualify) is the same for every valid batch: the price of the "
            "practice, which the client states. A renewal written within half a unit of last year's amount (352.0, "
            "351.99) counts as rolled over and is paid last year's amount: before the check, writing each renewal "
            "half a unit towards its entitlement stayed valid and beat the bound by 0.5 a renewal. It shifts every "
            "valid objective by the same amount and so never moves quality between them; "
            "before the audit it was the gap between the reference and the best compliant answer that capped a "
            "perfect batch at about 1.03 (REVIEW.md, F2).",
            f"- **An exception** to the renewal practice (the rule relaxed) costs {module.REASSESSMENT_COST} for "
            "every renewal household once any renewal is not rolled over: the director's exception covers the whole "
            "queue (equal treatment), and each re-assessment is half a day of a caseworker.",
            "",
            "Quality is normalized between the baseline (0), the client's own worksheet run with the setting's "
            "statutory period, asset limit and round, and the reference (1), the answer key.", "",
            "**What a slip costs.** One household wrongly refused costs 400 plus its amount: with the median award, "
            + ", ".join(f"{t} {_range(slip[t])}" for t in tiers) + " of quality. A misread fact costs every household "
            "it touches (part 1); a careful batch with every fact right and a couple of slips keeps most of its "
            "credit (the `two_slips` deliverable of part 5)."]
    out += ["", "**The zero point is the client's own way** (`baseline_solution`, requirements.md \"How the counter "
            "does it today\"): last year's paper worksheet. It keeps the statutory residency period, the asset limit "
            "and the round's arrangements, so it is valid, but it has last year's figures on it (table, earnings "
            "disregard of 150 and 30%, and from medium the 980 cap table), its disregard box takes only the "
            "applicant's earnings (the others' count in full, with those of adults on the form who live elsewhere), "
            "it counts every income column (child support too, which easy leaves out), it has no supplement line, "
            "it counts residency in calendar months and it decides every application as filed. No one of these "
            "carries the scale: copying the worksheet and fixing any one of them reaches at most "
            f"{single:.3f}"
            " (the `worksheet_*` shortcuts)."]

    # ── 4. reference and bounds ──
    out += ["", "## 4. Reference and bounds", "",
            "- **Reference** (`reference_solution`): the answer key, every rule of the setting applied exactly, "
            "renewals rolled over. Before the audit the reference applied the earnings disregard once per household "
            "and a perfect batch scored 1.015–1.082.",
            "- **Best known** (`best_known_solution`): the answer key.",
            "- **Bound** (`objective_bound`, proven): the renewal practice's own cost. A valid batch pays every "
            "renewal exactly last year's amount (a renewal within half a unit of it is read as it), which costs "
            "exactly that, re-assesses none (no queue cost), and every new application costs 0 or more; the answer "
            "key costs exactly the bound. A batch that bends the practice under an approved exception is "
            "outside the bound's scope and can end below it (below).",
            "- **Baseline** (`baseline_solution`): the client's worksheet (part 3).", ""]
    rows = []
    for tier in tiers:
        bs = [b for b in audit["bounds"] if b["setting"].startswith(tier + "/")]
        rows.append([tier, str(len(bs)), _range([b["reference"] for b in bs], 0), _range([b["baseline"] for b in bs], 0),
                     _range([b["span"] for b in bs]), _range([b["best_known_quality"] for b in bs]),
                     _range([b["bound_quality"] for b in bs]), _range([b["gap_to_bound"] for b in bs])])
    out += _table(["tier", "settings", "reference", "baseline", "span", "best known quality", "bound quality",
                   "gap to bound"], rows)
    known = [b["best_known_quality"] for b in audit["bounds"] if b["best_known_quality"] is not None]
    out += ["", f"**quality_cap** = {meta.get('quality_cap')}: the median best known quality ({median(known):.3f}); "
            "the answer key is the best a valid batch can do (the bound), so full credit is the answer key.", "",
            "The public panel:", ""]
    panel = {e["label"]: e["params"] for tier in tiers for e in audit["settings"][tier] if e.get("panel")}
    out += _table(["setting", "drawn values", "reference", "baseline", "span", "best known quality", "bound"],
                  [[b["setting"], ", ".join(f"{k}={v}" for k, v in panel[b["setting"]].items()), _num(b["reference"], 0),
                    _num(b["baseline"], 0), _num(b["span"]), _num(b["best_known_quality"]), _num(b["bound"], 0)]
                   for b in audit["bounds"] if b["setting"] in panel])

    # value of asking, and attempts to beat the never-asks solver
    out += ["", "**Value of asking.** `robust_solution` never asks: it reads every fixed fact the natural way (a rule "
            "exists for every figure the pools name, so the asset test, the supplement and the cap apply in every "
            "tier; child support is income; the finance circular applies; the letters are not granted; members "
            "living elsewhere are ignored; the disregard is per earner) and hedges the one fixed fact the data leaves "
            "open, the reported changes (none, those in effect, all). It rolls the renewals over and gives each new "
            "application the decision and amount with the lowest mean cost over every combination of the tier's "
            "candidates, within a plan: the residency period it approves from, the asset limit it approves under and "
            "the cap table it pays up to. The safe plan takes the strictest candidate of each and is valid "
            "everywhere; another plan gambles on the drawn figure. It takes the plan with the best mean credit over "
            "every combination of the tier's candidates (`plan_credits`): an engineer does not need the client's "
            "zero point to plan for the middle asset limit. Never asks (params) is the best single setting's answer "
            "key, which knows every fixed fact. The other columns are measured by `gt_report.py`: the *safe plan*; "
            "*in effect*, the solver reading the reported changes as in effect on the application date instead of "
            "hedging (an honest reading, the same in every tier); *lucky* reads the tier's fixed facts the client's "
            "way, as a solver that guessed them all right would; *one guess* is the mean over the tier's measured "
            "combinations of the answer key of that one guessed combination with the fixed facts read naturally.",
            ""]
    rows, beat = [], {}
    for tier in tiers:
        v = audit["voi"][tier]
        rob = next((c for c in v["candidates"] if c["name"] == "robust_solution"), {})
        cases = [case for _, case in measured[tier]]
        pools = {name: list(by_tier[tier]) for name, by_tier in cases[0].param_candidates.items()}

        def mean_credit(doc):
            return mean(_credit(*_evaluate(case, module, doc)[:2]) for case in cases)
        hedged = module._hedge(world, tier, pools)
        credits = module.plan_credits(world, tier, pools, hedged)
        safe = (max(int(x) for x in pools["residency_days"]), module.STRICTEST, min(int(x) for x in pools["cap"]))
        best = max(credits, key=lambda k: credits[k])
        chosen = safe if credits[safe] >= credits[best] - 1e-9 else best
        safe_credit = mean_credit(module.never_asks(world, tier, pools))
        in_effect = mean_credit(module.never_asks(world, tier, pools, changes=("in_effect",), plan=True))
        lucky = mean_credit(module.never_asks(world, tier, pools, lucky=True))
        guesses = [mean_credit(module.one_guess(world, tier, case.drawn_params)) for case in cases]
        plan = (f"{chosen[0]} days, " + ("the strictest limit" if chosen[1] == module.STRICTEST else
                                         "limit " + chosen[1].replace("_", " + ")) + f", cap {chosen[2]}")
        beat[tier] = {"safe": safe_credit, "in_effect": in_effect, "lucky": lucky, "guess": mean(guesses),
                      "plans": (credits[safe], credits[chosen])}
        rows.append([tier, _num(v["never_asks"]), _num(rob.get("valid_rate")), _num(v["voi"]),
                     _num(v["never_asks_params"]), _num(v["voi_params"]), _num(safe_credit), plan, _num(in_effect),
                     _num(lucky), _num(mean(guesses))])
    out += _table(["tier", "never asks (credit)", "its validity rate", "voi", "never asks (params)", "voi_params",
                   "safe plan (credit)", "plan taken", "in effect (credit)", "lucky (credit)", "one guess (credit)"],
                  rows)
    refused = []
    for _, case in measured["easy"]:
        r = module.rules_of(case.setting)
        key, tested = (module.truth(world, x) for x in (r, module.replace(r, asset_limit=module.ASSET_LIMITS[str(
            module.POOLS["asset_limit"]["easy"][0])])))
        paid = [h for h in new if key[h.id][0]]
        refused.append(sum(not tested[h.id][0] for h in paid) / len(paid))
    # easy: the out-of-round facts read as skipped (the cherry-pick the solver does not make)
    pools = {name: list(by_tier["easy"]) for name, by_tier in base.at("easy", base.rule_seeds[0])
             .param_candidates.items()}
    readings = [module.replace(x, asset_limit=None, disability=0, child_support=False)
                for x in module._hedge(world, "easy", pools, changes=("none",))[0]]
    readings = [module.replace(x, changes=c) for x in readings for c in module.CHANGE_READINGS]
    counts = {h.id: module.Counter(module.assess(h, x) for x in readings) for h in new}
    picked = iter(module._planned(world, counts, *module._envelope(readings, pools, None, None, None)))
    skip_rows = [[h.id, "yes", h.last_amount, "RENEWAL"] if h.renewal else
                 (lambda o: [h.id, "yes" if o[0] else "no", int(o[1]), o[2]])(next(picked))
                 for h in world.households]
    easy_cases = [case for _, case in measured["easy"]]
    skipped = mean(_credit(*_evaluate(case, module, skip_rows)[:2]) for case in easy_cases)
    other = {}
    for seed in (1, 2, 3):
        case_w = base.with_world_seed(seed)
        for tier, settings in measured_settings(case_w).items():
            cases = [x.case for x in settings]
            pools = {name: list(by_tier[tier]) for name, by_tier in cases[0].param_candidates.items()}
            doc = module.never_asks(case_w.world, tier, pools, plan=True)
            other.setdefault(tier, []).append(1 - mean(_credit(*_evaluate(case, module, doc)[:2]) for case in cases))
    out += ["", "In easy the never-asks solver applies the asset test, the supplement and child support that the "
            f"round leaves out, and the asset test alone refuses {_range(refused, 2)} of the new applications the "
            "client pays, "
            "so it ends at or below the client's worksheet in every setting. Those are the natural readings of what it "
            "sees in all five locales: the leaflet tells citizens that households with substantial savings must use "
            "them first and that members with a disability may receive extra support, in the paragraph on how the "
            "amount is worked out, and the request attaches the declared assets; child support is an income column, "
            "and only a letter asking for an exception says otherwise. Skipping the three facts (the literal "
            "solution's reading: no figure, no rule) would earn "
            f"{_num(skipped)} in easy, but a solver that skips them must skip them in every tier, where approving "
            "households above the asset limit is invalid, and it would still apply the leaflet's residency wait and "
            "earnings disregard from the pools: a cherry-pick of the round's arrangements, not a reading. In medium "
            "it applies the circular and the reported changes the round leaves aside.", "",
            "The plan: " + "; ".join(
                f"{t}: the safe plan earns {beat[t]['plans'][0]:.3f} over every combination of the candidates, the "
                f"plan "
                f"taken {beat[t]['plans'][1]:.3f}" for t in tiers) + ". Reading the reported changes as in effect "
            "instead of hedging earns " + ", ".join(f"{beat[t]['in_effect']:.3f} in {t}" for t in tiers) + " (with "
            "the same plan), " + ", ".join(f"{beat[t]['in_effect'] - audit['voi'][t]['never_asks']:+.3f} in {t}"
            for t in tiers) + " against the hedge: a reading of the same view in every tier, so the solver keeps the "
            "hedge, and the best of these honest never-askers on the measured settings leaves asking worth "
            + ", ".join(
                f"{1 - max(audit['voi'][t]['never_asks'], beat[t]['safe'], beat[t]['in_effect']):.3f} in {t}"
                for t in tiers) + ". The lucky reading is a strategy only in hard, where it is the in-effect reading "
            "with the safe plan; in easy and medium it needs the round's arrangements, which nothing the agent sees "
            "suggests. The value of asking against the never-asks solver on the other worlds "
            "(the same combinations, each world's own measured settings): " + "; ".join(
                f"{t} " + ", ".join(f"{x:.3f}" for x in other[t]) for t in tiers) + " (world seeds 1, 2, 3)."]

    # bending the renewal practice
    out += ["", "**Bending the renewal practice** (the rule relaxed, as under the director's exception; measured by "
            "`gt_report.py`). *Best exception*: the answer key with every renewal re-assessed under this year's "
            "rules; it saves what rolling over costs (the practice cost) and pays "
            f"{module.REASSESSMENT_COST} × {len(renewals)} = {module.REASSESSMENT_COST * len(renewals):,} for the "
            "queue. *One renewal*: the answer key with only the renewal that gains most re-assessed (cherry-picking), "
            "which buys the whole queue's cost too. Quality above 1 pays before the company policy's penalty for a "
            "bent rule; below 1 loses.", ""]
    rows, gains = [], []
    for tier, cases in measured.items():
        for label, case in cases:
            bends = module.bent_deliverables(world, case.setting)
            practice = module.practice_cost(world, module.rules_of(case.setting))
            qb = _evaluate(case, module, bends["best_exception"][1], BEND)[1]
            qo = _evaluate(case, module, bends["one_renewal"][1], BEND)[1]
            gains.append((tier, qb, qo))
            if label in panel:
                rows.append([label, f"{practice:,}", f"{practice / len(renewals):.0f}", _num(qb), _num(qo)])
    out += _table(["setting", "practice cost", "per renewal", "best exception: quality", "one renewal: quality"], rows)
    by_tier = {t: [g for g in gains if g[0] == t] for t in tiers}
    out += ["", "Over the measured settings: " + "; ".join(
        f"{t}: the best exception pays in {sum(qb > 1 + 1e-9 for _, qb, _ in g)} and loses in "
        f"{sum(qb < 1 - 1e-9 for _, qb, _ in g)} of {len(g)} ({_range([qb - 1 for _, qb, _ in g])} of quality)"
        for t, g in by_tier.items()) + f"; cherry-picking one renewal loses in all {len(gains)} "
        f"({_range([qo - 1 for _, _, qo in gains])})."]
    other, worlds = [], {}
    for seed in [None] + list(range(1, 21)):
        case_w = base.with_world_seed(seed)
        w, n_ren = case_w.world, sum(h.renewal for h in case_w.world.households)
        pays = loses = 0
        lapsed_w = []
        for tier, settings in measured.items():
            for _, case in settings:
                r = module.rules_of(case.setting)
                practice = module.practice_cost(w, r)
                pays += practice > module.REASSESSMENT_COST * n_ren
                loses += practice < module.REASSESSMENT_COST * n_ren
                true = module.truth(w, r)
                lapsed_w.append(sum(not true[h.id][0] for h in w.households if h.renewal) / n_ren)
        worlds[seed] = (pays, median(lapsed_w))
        if seed in (1, 2, 3):
            other.append(f"world seed {seed}: pays in {pays}, loses in {loses}")
    rest = [worlds[k][0] for k in worlds if k is not None]
    lapsed_rest = [worlds[k][1] for k in worlds if k is not None]
    out += ["", "Whether it pays depends on how far this year's rules (uprating, disregard, supplement, cap) and the "
            "households' new circumstances have moved the renewals from last year's amounts, against half a day "
            "of a caseworker per renewal: on the other worlds (the same 45 combinations) " + "; ".join(other) + ". "
            f"Over world seeds 1-20 it pays in a median of {median(rest):g} of the 45 ({min(rest)}-{max(rest)}); the "
            f"public world, at {worlds[None][0]}, ranks {1 + sum(x > worlds[None][0] for x in rest)} of the 21, "
            f"because more of its renewals no longer qualify this year (a median {worlds[None][1]:.0%} of them "
            "over the 45 settings, "
            f"against {median(lapsed_rest):.0%} on the other worlds), each at 400 plus last year's amount. At 200 a "
            "household the threshold sits at the median renewal's cost over the worlds, so the price is left as it "
            "is: bending pays in some settings and loses in others on every world. "
            "The company policies charge 0.10 (enterprise) or 0.05 (startup) of the final score for a bent rule, "
            "which at a quality weight of 0.6 is worth 0.167 or 0.083 of quality: the best exception clears 0.167 in "
            f"{sum(qb - 1 >= 0.1667 for _, qb, _ in gains)} and 0.083 in {sum(qb - 1 >= 0.0833 for _, qb, _ in gains)}"
            f" of the {len(gains)} settings. With quality_cap 1.0 a batch already at the answer key cannot gain from "
            "an exception; any batch below it can, where the practice costs more than the queue."]

    # ── 5. diagnostics ──
    out += ["", "## 5. Diagnostic cases", "",
            "`diagnose()` returns `enforced` and `evidence` per target (`case.py diagnostic`). For each fact and each "
            "other reading of it (another candidate of a drawn figure, the misreading of a fixed fact, or a less "
            "natural reading of `alternatives`: last year's table or a guessed uprating of 1% to 8%, the disregard "
            "once per household, on the applicant only, not at all or with the candidates' figures crossed, "
            "residency in calendar months, every car or none exempt, no supplement or a guessed one, another cap "
            "table, the changes ignored), it takes the new applications where the client's reading and that reading "
            "give different determinations and counts which one the deliverable follows (the same decision and an "
            "amount within one unit; for the facts that decide who qualifies, the same decision and refusal reason). "
            "Each fact is judged in a context: first the other facts are read the way that best explains the "
            "deliverable (greedily, one reading at a time while it matches at least 3 more households), so a batch "
            "that misreads two facts which both move every amount, such as the uprating and the disregard, has each "
            "judged with the other read its way (before the check the second fact went unflagged: 0 of 15 for the "
            "disregard beside a wrong uprating, the cap and the uprating both missed together). Not enforced: it "
            "follows the other reading on at least half of those households, more often than the client's, and "
            "agrees with the client's reading (in that context) on most of the others. An amount fact that ends with "
            "no verdict is not enforced when the batch is more than 10 off on three quarters of the households the "
            "fact moves and within 10 on three quarters of the others it pays (a figure no reading holds, such as a "
            "guessed supplement). Enforced: it follows the client's reading on at least half of them. None: no "
            "household tells, or it follows neither. The renewal practice and the letters are read directly: one "
            "renewal not rolled over, or one letter given in to, is enough.", ""]
    diag = audit["diagnostics"]
    ref_ok = {t: all(e.get("reference_enforced", {}).get(t) is not False for tier in tiers
                     for e in audit["settings"][tier] if not e.get("skipped")) for t in targets}
    out += _table(["target", "what tells the client's reading from the others", "reference enforced", "ablations"],
                  [[f"`{t}`", TELLS[t], "yes" if ref_ok[t] else "no",
                    "separates" if diag.get(t, {}).get("separates") else
                    "untested" if diag.get(t, {}).get("separates") is None else "no"] for t in targets])
    out += ["", "**Reliability on other deliverables** (a run's batch is neither the reference nor an ablation). "
            "Settings where the diagnostic calls the deliverable not enforced, of those where it gives a True or "
            "False: the best known solution (built with full knowledge, so every one would be a false negative), the "
            "ablation of the target that also calls other targets not enforced (of the settings where it bites), and "
            "the baseline (each setting's own) and `robust_solution` (its tier's), which are informational: neither "
            "is built with full knowledge.", ""]
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
    cases_seen: dict[str, dict] = {}
    for tier, settings in measured.items():
        for _, case in settings:
            in_force = [t.id for t in case.targets("en")]
            key = module.determinations(world, module.rules_of(case.setting))
            for name, (target, what, doc) in module.diagnostic_cases(world, case.setting).items():
                if target is not None and doc == key:
                    continue            # the misreading changes nothing here
                with tempfile.TemporaryDirectory() as tmp:
                    module._write(Path(tmp), doc)
                    sub = module._parse(world, Path(tmp))
                enforced, _ = module.diagnostic(world, sub, case.setting)
                misread = (target,) if isinstance(target, str) else tuple(target or ())
                row = cases_seen.setdefault(name, {"target": misread, "what": what, "tiers": {}, "flags": set()})
                hit = (not any(enforced.get(t) is False for t in in_force) if not misread
                       else all(enforced.get(t) is False for t in misread))
                row["flags"].update(t for t in in_force if t not in misread and enforced.get(t) is False)
                k, n = row["tiers"].get(tier, (0, 0))
                row["tiers"][tier] = (k + hit, n + 1)
    out += ["", "**Other deliverables** (`case.py diagnostic_cases`, measured by `gt_report.py`): batches with every "
            "fact right that differ from the answer key (the diagnostic must call no fact in force not enforced), and "
            "misreadings no ablation makes, one fact or two at once (it should call each misread fact not enforced). "
            "Settings where it does, of those where the batch differs from the answer key.", ""]
    out += _table(["deliverable", "target", "what it is"] + tiers + ["other targets called not enforced"],
                  [[f"`{name}`", " + ".join(f"`{t}`" for t in row["target"]) or "every fact right", row["what"]]
                   + [cell(*row["tiers"][t]) if t in row["tiers"] else "–" for t in tiers]
                   + [", ".join(f"`{u}`" for u in sorted(row["flags"])) or "none"]
                   for name, row in sorted(cases_seen.items(), key=lambda item: len(item[1]["target"]))])
    sheet = profile.get("baseline") or {}
    named = ", ".join(f"`{t}` ({x['false']} of {x['diagnosed']})" for t, x in sheet.items()
                      if x["false"] and t != "residency")
    out += ["", "The baseline's column is the worksheet's own profile. With each fact judged in the context of the "
            "others read the worksheet's way, the diagnostic names its misread figures and lines: " + named + "; "
            "where it gives no verdict the worksheet's other habits (the earnings of adults living elsewhere, which "
            "no target holds) move the same amounts. On `residency` it is the calendar-month reading wherever "
            "households sit between the period in days and in months.", "",
            f"`diagnose()` raised in {(audit.get('diagnose_errors') or {}).get('count', 0)} evaluation(s) of the "
            "audit."]
    found = summarize(findings(audit, meta.get("quality_cap")))
    out += ["", "**Findings** (as validate-case reads the stored audit with this quality_cap):", ""]
    out += [f"- {x}" for x in found or ["none"]] + [""]
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "GT.md"
    dest.write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
