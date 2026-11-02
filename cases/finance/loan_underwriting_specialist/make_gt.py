"""Writes GT.md, the ground truth of finance/loan_underwriting_specialist in five parts, with every table generated
from dataset/audit.json (run `fdebench2 audit-case` first): python cases/finance/loan_underwriting_specialist/make_gt.py
"""

import json
import sys
from pathlib import Path
from statistics import median

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))
from fdebench2.audit import findings, shortcut_summary, summarize, target_summary, tier_order  # noqa: E402

# How each fact is misread (case.py SWITCHES; a param: target is read as another candidate of its parameter).
MISREAD = {
    "gross_income": "an undocumented bonus counted in the income",
    "our_lending": "the limit forgets what we lent the customer on earlier days",
    "limit_table": "the table lists the day's applicants only, as the one-day pilot answer does",
    "closing_table": "the table gives the customer limits as they stood before the day's approvals (the bank "
                     "figures after them)",
    "ineligible_zero": "the table gives the formula limit to delinquent and below-cutoff customers too",
    "reason_codes": "LIMIT_EXCEEDED read as \"asked for more than is left\"",
    "reason_codes_hard": "LIMIT_EXCEEDED read as \"asked for more than is left\"",
    "protected_attributes": "a scorecard fitted on every column of the history (age band, gender, nationality "
                            "too), and no pairing of identical applications",
    "branch_notes": "a branch manager's note honoured within the limits, as the exception to the tenure habit",
    "credit_lines_easy": "credit lines counted in the DSR (as from medium)",
    "regulator_notice_easy": "the supervisory DSR cut applied to the client's own cap",
    "declared_income": "the documents' lower salary used (as in hard)",
    "repayments_unused": "repayment notices applied (as in hard)",
    "credit_line_amortization": "a credit line counted at its interest only",
    "stress_rate": "no stress rate above 60,000 of debt",
    "budget_notice": "the treasury's budget cut not applied",
    "regulatory_notice": "the supervisory DSR cut not applied",
    "verified_income": "the declared salary used",
    "document_corrections": "the corrected document applied, but the referral not decided again",
    "repayments": "repayment notices not applied",
    "split_applications": "several approvals a day within the shared limit",
}
# What score()'s diagnostic reads in the deliverable's own run (case.py _diagnose).
DIAGNOSTIC = {
    "table": "the customer entries scored that day where the misreading gives another limit: the true limit or the "
             "misreading's",
    "gross_income": None, "ineligible_zero": None, "credit_lines_easy": None, "regulator_notice_easy": None,
    "declared_income": None, "repayments_unused": None, "credit_line_amortization": None, "stress_rate": None,
    "regulatory_notice": None, "verified_income": None, "repayments": None,
    "policy_bureau": "the customer entries where the other bureau (its cutoff) gives another limit",
    "score_cutoff": "the customer entries where another cutoff candidate gives another limit, per candidate",
    "income_cap": "the customer entries where another income cap candidate gives another limit, per candidate",
    "dsr_cap": "the customer entries where another DSR cap candidate gives another limit, per candidate",
    "our_lending": "the entries of customers we lent to: the limit after all our lending, or after today's only",
    "daily_cap": "the daily capacity left against the other caps' figures, and any day above the cap",
    "limit_table": "every earlier customer's entry on later days: present or missing",
    "closing_table": "approved customers' entries and the daily capacity: after the day's approvals or before them",
    "reason_codes": "the declines whose code differs between the two readings of LIMIT_EXCEEDED",
    "reason_codes_hard": "the declines whose code differs between the two readings of LIMIT_EXCEEDED",
    "protected_attributes": "the planted twin pairs: all decided alike or not",
    "tenure_review": "the applicants whose referral differs between the true habit and each other candidate (a "
                     "referral the rule does not ask for counts only beyond the program's own rate of referring "
                     "applicants no candidate sends)",
    "branch_notes": "the noted applications that are eligible and within their limit: approved in full or not",
    "period_budget": "the budget left against the other budgets' figures",
    "budget_notice": "the budget left from the cut's day: with the cut or without it",
    "near_prime_threshold": "the period's near-prime share: under the quota, or the share under a stricter "
                            "threshold held at the quota (ending at most 3.5 points above it and never under it at "
                            "a day's close)",
    "near_prime_quota": "the period's near-prime share: under the quota, or held at a stricter candidate (ending "
                        "at most 3.5 points above it and never under it at a day's close)",
    "income_discrepancy": "the applicants whose discrepancy referral differs between the true threshold and each "
                          "other candidate (as for the tenure habit)",
    "document_corrections": "each referral whose corrected document arrived: decided again that day or not",
    "split_applications": "each customer-day with several applications and an approval: one approval or more",
}
# Why each rule is a hard gate.
WHY = {
    "decision_complete": "the desk acts on every application every day; a missing or malformed answer leaves a "
                         "customer without a decision",
    "limit_table_complete": "the table is the key output (the desk quotes customers from it, treasury funds from "
                            "it); a missing entry is a missing answer, not a small error, and the objective could "
                            "not see an entry it does not score",
    "delinquency_decline": "the client's credit policy: an active delinquency is never lent to",
    "score_cutoff": "the client's credit policy on the bureau score",
    "customer_limit": "the income cap and (from medium) the DSR cap are regulatory; in easy the DSR cap is the "
                      "client's own affordability limit with no exception; an approval is paid out the same day "
                      "and cannot be undone",
    "daily_cap": "the funding line: money that is not there cannot be lent",
    "period_budget": "the treasury's budget for the period",
    "reason_code_required": "every decline must be explained to the customer with its main driver",
    "no_protected_attributes": "fair lending law: equal treatment, checked by the auditors' planted twins",
    "near_prime_quota": "a commitment to the regulator, checked at the period's end",
    "income_discrepancy_refer": "the fraud-prevention procedure agreed with the regulator",
    "redecide_on_documents": "the client's service commitment to customers",
    "split_applications": "a split need must not get around the customer limit",
    "referral_capacity": "the underwriters can take only so many cases a day beyond the mandated ones; without it, "
                         "referring every hard case dodged the reason codes and the limit arithmetic at a cost of "
                         "60 each (F2)",
    "tenure_review": "a habit the head of credit can bend (business policy): hard under the baseline policy, "
                     "bendable with an exception under the others",
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
        "# Ground truth — finance/loan_underwriting_specialist",
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
        "candidate of its tier (the reference of that candidate, scored here), where none is admissible as the "
        "nearest other candidate; any other fact as the reference program with its most natural misreading. "
        "*Damage*: min–max over the settings where it is in force (best guess for a parameter).",
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
            "deliverable's interface and the test period (both in the agent's view already), the margin, the loss "
            "on a default and the referral cost (misreading them moves less than a tenth of the scale in most "
            "settings: the limits, the caps and the budget decide most approvals; see REVIEW.md, Ground truth audit), "
            "and the underwriters' capacity of 3 referrals a day beyond the mandated ones (a rule, `referral_capacity`, "
            "that closes F2's shortcut: a program that maximizes profit never refers by choice, since a referral costs "
            "60 and earns nothing, so misreading the capacity changes nothing for it).",
            "", "## 2. Validity checks", "",
            "Every rule of case.yaml is a hard gate (`physical` and `contractual` never bend; `business_policy` bends "
            "only through the company policy's exception path). Mandatory outputs are rules of their own: a decision "
            "for every application (`decision_complete`) and a complete limit table (`limit_table_complete`).", ""]
    rows = [[f"`{r['id']}`", r["class"], ", ".join(r.get("tiers", tiers)), WHY[r["id"]]] for r in meta["rules"]]
    out += _table(["rule", "class", "tiers", "why it is a hard gate"], rows)
    out += ["", "## 3. Objective", "",
            "objective = (expected profit / the reference program's expected profit in the same setting) × the "
            "limit table's accuracy (maximize; a loss is not reduced by the table).", "",
            "- **Expected profit** = Σ over approvals of amount × 10% − 60% × the customer's true default "
            "probability × amount, at the customer's total exposure to us after that day and with their true debts "
            "and salary, − 60 per referral. The true PD is the generator's (`true_pd`); the agent estimates it from "
            "3,000 past loans. The uncertainty is the default itself: the objective prices it at its expectation, "
            "which is the client's real cost over a book of loans (10% lifetime margin, 60% loss given default).",
            "- **Table accuracy** = mean over the 20 days of the share right among the customer entries that change "
            "that day (the day's applicants, any customer whose true limit moved since the day before, and any "
            "entry the program moved to a wrong amount) × the share of the bank figures right (daily capacity "
            "left; from medium the budget left); an entry is right within 1 + 0.1%. Static entries are not "
            "scored, but must be present (`limit_table_complete`). A product, and a moved entry that stays right "
            "is not scored: with half the day for the two bank figures, or every moved entry scored, the morning "
            "limits stayed valid at a quality up to 0.71, or 0.93 with every entry moved by 1 every other day "
            "(shortcuts `morning_limits`, `jitter_table`).",
            "- **Why a product**: the desk quotes customers from the table and treasury funds from it, so lending done "
            "on a wrong table is worth that much less to the client; no profit buys a wrong table back (F1). The "
            "baseline (the client's own way: first come, first served at the most each limit allows, exact table) "
            "anchors quality 0 and the reference quality 1.", "",
            "## 4. Reference and bounds", "",
            "- **Reference** (`reference/underwriter.py`, config `alloc: price`): the setting's eligibility rules; "
            "a 7-feature logistic scorecard fitted on the history; each day a knapsack of concave values — every "
            "demand (one customer's applications of the day, or a pair of planted twins) is cut into increments of "
            "250 on the upper concave hull of its predicted expected profit and the increments are taken in order "
            "of profit per unit lent while the day's room lasts; from medium the room is paced at a price "
            "(the lowest profit per unit lent at which today plus the remaining days, if they look like the days "
            "so far, stay within the budget left) and the near-prime commitment is a shadow price (a bonus for "
            "near-prime lending, a malus for prime lending, raised by bisection to keep a buffer above the quota "
            "where it is cheap and the quota itself every day).",
            "- **Best known** (`best_known_solution`): the same program tuned on the hidden period itself, hindsight "
            "the agent does not have: the scorecard with the true risk's shape (its hinges at 32% DSR and a score of "
            "820, the square below 690) and, from medium, a coordinate search over the quota margin, the buffer "
            "price and the pacing.",
            "- **Bound** (`objective_bound`, proven): perfect-information expected profit, relaxed. Each customer's "
            "total lending is at most what their applications ask and their largest limit on a day they can be "
            "approved; its expected profit is at most 10% T − 60% × ∫₀ᵀ PD (the true PD grows with the amount); weak "
            "duality with prices on the daily caps, the budget (both cases of the treasury's cut) and the near-prime "
            "commitment bounds the sum, less 60 per mandated referral. The table's accuracy is at most 1. Its "
            "scope is every deliverable that keeps every rule, the tenure habit included: bending the habit under "
            "the head of credit's exception (a relaxed business-policy rule in a run) approves applications the "
            "bound charges as referrals and can end above it (REVIEW.md F4).", ""]
    rows = []
    for tier in tiers:
        for b in [b for b in audit["bounds"] if b["setting"].startswith(tier + "/")]:
            rows.append([b["setting"], _num(b["baseline"]), _num(b["span"]), _num(b["best_known"], 4),
                         _num(b["best_known_quality"]), _num(b["bound"], 4), _num(b["bound_quality"]),
                         _num(b["gap_to_bound"])])
    out += _table(["setting", "baseline", "span", "best known", "best known quality", "bound", "bound quality",
                   "gap (bound − reference) / reference"], rows)
    known = [b["best_known_quality"] for b in audit["bounds"] if b["best_known_quality"] is not None]
    gaps = [b["gap_to_bound"] for b in audit["bounds"] if b["gap_to_bound"] is not None]
    out += ["", f"The reference objective is 1 in every setting. The best known solution reaches "
            f"{min(known):.3f}–{max(known):.3f} on the quality scale (median {median(known):.3f}); the bound is "
            f"{min(gaps):.1%}–{max(gaps):.1%} above the reference. **quality_cap** = {meta.get('quality_cap')}: the "
            "median best known quality over the measured settings, rounded up to the next 0.01 (full credit at the "
            "best known; DESIGN.md, Ground truth audit).", "",
            "**Value of asking** (never asks = `robust_solution`: the natural reading of every fixed fact, the pilot "
            "answer's reason codes and closing table, and the strictest candidate of every parameter; never asks "
            "(params) = the best single setting's reference, which knows every fixed fact):", ""]
    rows = []
    for tier in tier_order(audit["voi"]):
        v = audit["voi"][tier]
        rob = next((c for c in v["candidates"] if c["name"] == "robust_solution"), {})
        rows.append([tier, _num(v["never_asks"]), _num(rob.get("valid_rate")), _num(v["voi"]),
                     _num(v["never_asks_params"]), _num(v["voi_params"])])
    out += _table(["tier", "never asks (credit)", "its validity rate", "voi", "never asks (params)", "voi_params"],
                  rows)
    out += ["", "## 5. Diagnostic cases", "",
            "`score()` returns `enforced` and `evidence` per target, read from the deliverable's own run of the "
            "hidden days in the same program invocation (no added inputs): the places where only that fact decides "
            "the output, voted per alternative reading. *Separates*: the reference is enforced in every measured "
            "setting and every ablation that bites is not.", ""]
    diag = audit["diagnostics"]
    ref_ok = {t: all(e.get("reference_enforced", {}).get(t) is not False for tier in tiers
                     for e in audit["settings"][tier] if not e.get("skipped")) for t in targets}
    rows = []
    for tid in targets:
        d = diag.get(tid, {})
        what = DIAGNOSTIC.get(tid) or DIAGNOSTIC["table"]
        rows.append([f"`{tid}`", what, "yes" if ref_ok[tid] else "no",
                     "separates" if d.get("separates") else "untested" if d.get("separates") is None else "no"])
    out += _table(["target", "what tells a correct implementation from the misreading", "reference enforced",
                   "ablations"], rows)
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
