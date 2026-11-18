"""Writes GT.md, the ground truth of finance/stock_trading_strategist in five parts, with every table generated from
dataset/audit.json (run `fdebench2 audit-case` first): python cases/finance/stock_trading_strategist/make_gt.py
[destination [audit.json]]
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

# How each fact is misread (case.py _switches; a param: target is read as another candidate of its parameter).
MISREAD = {
    "risk_limit_change": "the lower limit read like the standing one, a limit on what is bought: nothing is bought "
                         "over it, but a holding over it stays",
    "buying_power_reserve": "the buying power as the pilot's table shows it: usable cash, nothing taken off for the "
                            "announced withdrawal",
    "drawdown_payouts": "the drawdown on the equity alone (the pilot had no payout, so its table fits both readings): "
                        "a payout reads as a loss, in the table and for the program's own risk switch",
    "circuit_breaker": "no session to spare: the close-out sized for the whole deadline, the withdrawal raised in the "
                       "last session whose sales settle in time",
    "inside_tip": "a note is a note: the tipped stock is traded like any other",
}
# What diagnose() reads in the program's own run (case.py _diagnose).
DIAGNOSTIC = {
    "restricted_list": "its buy orders: one for a restricted stock is not enforced; one for a stock that another "
                       "candidate list bars shows it was not built for that list",
    "close_out_deadline": "its largest holding at any close, in sessions of its own largest order: more than the "
                          "deadline sells under the threshold (or the added stock still held at it, unless a circuit "
                          "breaker took the orders) is not enforced; more than the next shorter candidate allows "
                          "shows it uses the deadline it was given",
    "large_order_threshold": "its largest ordinary order as a share of the 20-session average volume: above the "
                             "threshold is not enforced; above the next lower candidate shows it uses the threshold it "
                             "was given",
    "stock_limit": "the largest weight of a stock at the close of a session in which it was bought (the risk "
                   "manager's 5 points added back from their date): above the limit is not enforced; above the next "
                   "lower candidate shows it uses the limit it was given",
    "risk_limit_change": "per scenario: a holding left, or bought, over the lower limit from its effective close is "
                         "not enforced (one such scenario is enough); a holding that was over it before and is within "
                         "it at that close is enforced (the lower limit taken 5 points under the one the run keeps "
                         "before it)",
    "withdrawal_amount": "the status tables between the notice and the payment whose buying power only one clause "
                         "gives: the agreement's or another candidate's; settled cash short of the payment is not "
                         "enforced",
    "buying_power_reserve": "the status tables between the notice and the payment: something taken off the usable "
                            "cash, or the usable cash as it is",
    "drawdown_payouts": "the status tables after the payout: the drawdown with the payout added back, or on the "
                        "equity alone, or (where the run's drawdown was right before the payout) any other figure; "
                        "wrong on more than a tenth of them is not enforced",
    "circuit_breaker": "a deadline missed in a scenario where the circuit breaker took the orders meant to meet it, "
                       "or a holding that takes every session of the deadline, is not enforced; a holding that takes "
                       "all but one is enforced",
    "inside_tip": "its buy orders for the tipped stock: any after the tip is not enforced; bought before and never "
                  "after is enforced",
}
# Why each rule is a hard gate.
WHY = {
    "order_format": "the engine can only execute well-formed orders; a call that fails leaves the desk without a "
                    "decision that day",
    "status_table_complete": "the table is the daily report the request asks for and the desk steers by: a missing "
                             "one is a missing answer, not a small error (and the objective cannot score what is not "
                             "there)",
    "lot_size": "the exchange trades whole board lots",
    "no_short_selling": "a cash account cannot sell what it does not hold",
    "restricted_list": "compliance: the firm advises these companies",
    "restricted_liquidation": "compliance: the client agreement's deadline for closing out a newly restricted stock",
    "order_size_limit": "the client's agreement repeats the desk's threshold for the book's ordinary trading, and the "
                        "desk head never approves more than 1.5 times it for a close-out: beyond that nothing bends "
                        "(REVIEW.md F4: the approved exception was unbounded)",
    "large_order_approval": "the desk head's approval for close-out sells between the threshold and 1.5 times it "
                            "(business policy): hard under the baseline policy, bendable with an exception under "
                            "the others",
    "position_limit": "the client's mandate, and the risk manager's cut of it",
    "sector_limit": "the client's mandate",
    "cash_withdrawal": "the client's instruction: the money must be there, settled, on the day",
    "max_drawdown": "the client's risk mandate: past it the book is closed",
    "insider_tip": "inside information: compliance and the law",
}


def _num(x, d=3):
    return "–" if x is None else f"{x:.{d}f}"


def _table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def main() -> None:
    source = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "dataset" / "audit.json"
    audit = json.loads(source.read_text(encoding="utf-8"))
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    targets = {t["id"]: t for t in yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))}
    tiers = tier_order(audit["settings"])
    n_settings = {t: len(audit["settings"][t]) for t in tiers}
    out = [
        "# Ground truth — finance/stock_trading_strategist",
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
        "## 1. Client facts",
        "",
        "One row per target (`locales/en/targets.yaml`). *Ablated as*: a parameter is read as each other admissible "
        "candidate of its tier (the reference of that candidate, scored here), where none is admissible as the next "
        "candidate of its pool; any other fact as the reference program with its most natural misreading. *Damage*: "
        "min–max over the settings where it is in force (best guess for a parameter).",
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
        rows.append([f"`{tid}`", spec["text"].replace("|", "/"), ", ".join(t["tiers"]), how,
                     _num(low) if low == high else f"{_num(low)}–{_num(high)}", per, diag])
    out += _table(["target", "fact", "in force", "ablated as", "damage", "bites", "diagnostic"], rows)
    out += ["", "Facts the client states that are not targets (they stay in requirements.md as context): the "
            "program's interface, the test period and its four scenarios (the agent's view states the interface, and a "
            "program that keeps its state in module variables needs nothing more); how orders fill, the commission, "
            "board lots, the cash account and halts (the pilot's fills and the stock list show them, and misreading "
            "the rest moves less than a tenth of the scale); the engine's simple mode in easy (a program built for "
            "the pilot's full mode loses a session on reinvesting and nothing else); the OMNY split and the earnings "
            "calendar (the engine converts positions and bars, and the reference does not trade on earnings); that a "
            "newly restricted stock may not be bought and must be closed out, and that close-out sells are under the "
            "large-order threshold (the desk's e-mails say both: only the deadline and the threshold are missing); "
            "that the withdrawal is paid from settled cash (the natural reading under T+2); the sector limit of 35% "
            "(a book sized for the close-out never comes near it: no draw of it changed an answer, so it is one value "
            "now and a rule, not a question); the level of the drawdown mandate (the reference's own risk switch "
            "keeps its largest drawdown at 2–5% against mandates of 10–15%, so another level changes no answer: the "
            "rule stands, and how the drawdown is measured is the target `drawdown_payouts`); the client's \"make it "
            "10%\" note (no plausible program follows it); the scope lines of easy and medium (nothing in the "
            "agent's view tempts a program to apply what they leave out); and that volumes are raw while prices are "
            "adjusted (the requirements say so, and the book seldom trades XIPH while its 20-session window still "
            "holds pre-consolidation volumes: reading them raw moved no setting by 1% of the scale). See REVIEW.md, "
            "Ground truth audit.",
            "", "## 2. Validity checks", "",
            "Every rule of case.yaml is a hard gate, in every one of the four scenarios (`physical` and `contractual` "
            "never bend; `business_policy` bends only through the company policy's exception path). The mandatory "
            "output is a rule of its own: the status table in every call (`status_table_complete`).", ""]
    rows = [[f"`{r['id']}`", r["class"], ", ".join(r.get("tiers", tiers)), WHY[r["id"]]] for r in meta["rules"]]
    out += _table(["rule", "class", "tiers", "why it is a hard gate"], rows)
    out += ["", "## 3. Objective", "",
            "objective = the return component × the status table's accuracy (maximize).", "",
            "- **Scenarios.** The engine replays the 80 hidden sessions in four market scenarios, each from a freshly "
            "loaded program and 10,000,000 in cash: the same history, calendar and dated events, different prices from "
            "the first hidden session on. Scenario 1 is the period the case always had, scenario 2 its mirror image "
            "(every normal draw of the hidden period reflected around its mean); scenarios 3 and 4 are a second "
            "mirrored pair with its own market regime. A pair has no lucky direction, so the average shows what a "
            "program earns from the drifts rather than from the noise. This is how the uncertainty is priced: the "
            "client's cost of a strategy is its result over the paths the market may take, not over one of them.",
            "- **Return component** = (V − Y) / (V_ref − Y), 0 below Y, where V is the book's final net equity plus "
            "everything paid out to the client, averaged over the scenarios, V_ref the same for the reference program "
            "in the same setting, and the yardstick Y is the index bought at the first session and held (averaged "
            "the same way) or the starting capital if that is more: leaving the money in the account does not beat a "
            "falling index. Where the reference beats Y by less than 500,000 (5% of the capital), Y is set 500,000 "
            "below V_ref instead, so the scale is the last 5% of the capital below the reference; where that falls "
            "below the starting capital, the baseline (all cash) keeps the part of the band under it and quality "
            "counts from the cash.",
            "- **Table accuracy** = the share of the calls of all four scenarios whose status table is right in "
            "every figure: every stock weight and sector weight within 0.05 points (and no weight reported for a "
            "stock not held), the buying power within 1 + 0.1%, the drawdown within 0.05 points. A table with one "
            "wrong figure is a wrong table.",
            "- **Why a product**: the desk steers the book and reports to the client from the table, so a return made "
            "on a wrong table is worth that much less, and no return buys a table back. The baseline (the client's "
            "own way: the book left in cash, a correct table) anchors quality 0 and the reference quality 1.",
            "- **Usable worlds.** The scale runs from the cash to the reference, so a world is usable only if the "
            "reference makes money in it. `build_world` draws a world's scenario set again until the reference ends "
            "at least 1% of the capital above the starting capital, on average over the scenarios, in every public "
            "setting; the public world passes with its first set. The rule selects on the reference's result: on 36 "
            "scenario sets of world seeds 0-11 it kept 27, and the sets it rejects are mostly weak markets (the "
            "reference makes 1.8% there against 7.2%), where programs with more exposure than the reference do worse "
            "relative to it (by 1.3-1.9% of the capital). A rule on the index's own path (the index held ends at or "
            "above the capital) keeps as many sets with the same effect on the alternatives (within 0.14% of the "
            "capital) but is unusable: worlds 1 and 4 draw no such set in 31 tries.", "",
            "## 4. Reference and bounds", "",
            "- **Reference** (`reference/strategy.py` with a per-setting config): cross-sectional momentum inside the "
            "client's limits. Every 5 sessions it ranks the stocks it may buy by their 60-session return (skipping the "
            "last 5) over volatility and holds the four strongest, each at its target weight (24% in easy, the stock "
            "limit less 2 points from medium) or at most 80% of what it could sell out within the close-out deadline "
            "in orders under the threshold (the 20-session average volume projected forward; in hard with one session "
            "to spare). It trades in the opening auction, reserves and raises the withdrawal as soon as it is "
            "announced, trades down to a cut limit from its notice, never buys a tipped stock, and goes to cash when "
            "the index falls 4% in 20 sessions below its 20-session mean or the book is 4% below its peak since it "
            "last went in (in hard also 4 points inside the mandate, with the exposure a further 8% loss can take).",
            "- **Best known** (`best_known_solution`): the same program tuned without hindsight, as an agent can: a "
            "coordinate search over its own knobs (how many names, how often and how tightly it rebalances, how much "
            "of the close-out room it fills, its risk switch, and in hard how much exposure it keeps in a drawdown) "
            "scored on the visible history replayed as a test period (three windows of 80 sessions, the test period's "
            "notices and the setting's rules), each move kept while every window stays valid and the mean final value "
            "grows; then run on the hidden scenarios like any program. The same search scored on the hidden "
            "scenarios themselves (hindsight) reached q 1.42-3.24 (median 1.785) before the cut moved; an agent "
            "cannot reach that, so it no longer sets quality_cap.",
            "- **Bound** (`objective_bound`, proven): the return component of the mean, over the scenarios, of a "
            "perfect-foresight bound on the final value, with a table right every day. Per scenario a linear program "
            "chooses, with every price known, what to buy and sell each session: orders at most the threshold of the "
            "20-session average volume, the better of the open and p10 with the spread, commission and sales tax "
            "(the minimum commission and the market impact left out), no shorts, the restricted list, the added stock "
            "gone by its deadline, halts and the circuit breaker, settled cash for buys and for the withdrawal, and "
            "in hard the drawdown mandate against every earlier close. The stock and sector limits (which apply only "
            "where the book buys) are relaxed. It covers every program that keeps every rule; an approved exception "
            "for close-out sells is outside it. It is far above the reference: foresight of every price is worth much "
            "more than any signal, so the bound shows the scale has no ceiling near the reference rather than how "
            "close the reference is.", ""]
    rows = []
    for tier in tiers:
        for b in [b for b in audit["bounds"] if b["setting"].startswith(tier + "/")]:
            rows.append([b["setting"], _num(b["baseline"]), _num(b["span"]), _num(b["best_known"], 4),
                         _num(b["best_known_quality"]), _num(b["bound"], 2), _num(b["bound_quality"], 1)])
    out += _table(["setting", "baseline", "span", "best known", "best known quality", "bound", "bound quality"], rows)
    known = [b["best_known_quality"] for b in audit["bounds"] if b["best_known_quality"] is not None]
    bq = [b["bound_quality"] for b in audit["bounds"] if b["bound_quality"] is not None]
    spans = [b["span"] for b in audit["bounds"] if b["span"] is not None]
    out += ["", f"The reference objective is 1 in every setting; the baseline's is the part of the 5% band the cash "
            f"covers (0 where the reference ends 5% or more above the capital), so the scale is {min(spans):.3f}–"
            f"{max(spans):.3f} wide. The best known solution reaches {min(known):.3f}–{max(known):.3f} on the quality "
            f"scale (median {median(known):.3f}); the bound is at quality {min(bq):.1f}–{max(bq):.1f}. **quality_cap** "
            f"= {meta.get('quality_cap')}: the median best known quality over the measured settings, rounded up to "
            "the next 0.01 (full credit at the best known; DESIGN.md, Ground truth audit).", "",
            "**Value of asking** (never asks = `robust_solution`: the natural reading of every fixed fact and the "
            "strictest candidate of every drawn value; never asks (params) = the best single setting's reference, "
            "which knows every fixed fact):", ""]
    rows = []
    for tier in tier_order(audit["voi"]):
        v = audit["voi"][tier]
        rob = next((c for c in v["candidates"] if c["name"] == "robust_solution"), {})
        rows.append([tier, _num(v["never_asks"]), _num(rob.get("valid_rate")), _num(v["voi"]),
                     _num(v["never_asks_params"]), _num(v["voi_params"])])
    out += _table(["tier", "never asks (credit)", "its validity rate", "voi", "never asks (params)", "voi_params"],
                  rows)
    out += ["", "## 5. Diagnostic cases", "",
            "`diagnose()` returns `enforced` and `evidence` per target, read from the trace `score()` records of the "
            "program's own run of the four scenarios (one run per evaluation, no added inputs; a run's evaluation and "
            "the audit ask for it, the validator does not). A limit whose value the client must tell is read from how "
            "much of its room the run uses: over it is not enforced; more than the next stricter candidate allows is "
            "enforced; a run that fits a stricter candidate is not enforced where the reference shows the room is "
            "worth using, and undetermined where the reference does not use it either, unless its orders are exactly "
            "those of the reference built for another candidate. The dated facts are read where the run and the "
            "misreading differ. *Separates*: the reference is enforced (or undetermined) in every measured setting "
            "and every ablation that bites is not.", ""]
    diag = audit["diagnostics"]
    ref_ok = {t: all(e.get("reference_enforced", {}).get(t) is not False for tier in tiers
                     for e in audit["settings"][tier] if not e.get("skipped")) for t in targets}
    rows = []
    for tid in targets:
        d = diag.get(tid, {})
        rows.append([f"`{tid}`", DIAGNOSTIC[tid], "yes" if ref_ok[tid] else "no",
                     "separates" if d.get("separates") else "untested" if d.get("separates") is None else "no"])
    out += _table(["target", "what tells a correct implementation from the misreading", "reference enforced",
                   "ablations"], rows)
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
