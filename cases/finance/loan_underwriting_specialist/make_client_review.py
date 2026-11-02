"""Writes CLIENT_REVIEW.md: for every target, the question an engineer would ask, the passage of requirements.md
each of the five locales answers from (the locales' requirements are translated line by line), and a machine
pre-check of those passages. The verdicts are left for a human reviewer:
python cases/finance/loan_underwriting_specialist/make_client_review.py
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))
LOCALES = ("en", "zh", "ko", "ja", "es")

# target -> (the question, the en lines it is answered from, found by a piece of their text)
ASK = {
    "gross_income": ("How do you count a customer's annual income: base salary, bonus, the stated income?",
                     ["Annual gross income, used by every rule"]),
    "policy_bureau": ("Which bureau's score does your policy use?", ["We buy scores from two bureaus"]),
    "score_cutoff": ("What is the minimum score for an approval?", ["Otherwise we approve only when"]),
    "income_cap": ("Is there a cap on what a customer can borrow relative to their income?",
                   ["customer limit = min(50,000"]),
    "dsr_cap": ("What is your maximum debt-service ratio, and how is it computed?", ["**Debt-service ratio (DSR)**"]),
    "our_lending": ("Does what we already lent a customer reduce their limit?",
                    ["customer limit = min(50,000", "All of a customer's approvals on a day **together**"]),
    "daily_cap": ("Is there a limit on what we can approve in a day?", ["**Daily disbursement cap:**"]),
    "limit_table": ("Which customers and figures must the daily limit table hold?",
                    ["Every day, return the limits", "- `customers`: every customer", "- `daily_capacity_remaining`",
                     "- `period_budget_remaining`: the budget in force"]),
    "closing_table": ("Is the limit table as of the morning or after the day's approvals?",
                      ["Every day, return the limits"]),
    "ineligible_zero": ("What does the table show for a customer we cannot lend to?", ["- `customers`: every customer"]),
    "reason_codes": ("Which reason code wins when several apply, and when is it LIMIT_EXCEEDED?",
                     ["`DELINQUENCY` (active delinquency) → `LOW_SCORE` (`{{policy_bureau}}` below {{min_score}}) → "
                      "`LIMIT_EXCEEDED`"]),
    "reason_codes_hard": ("Which reason code wins when several apply, and when is it LIMIT_EXCEEDED?",
                          ["→ `SPLIT_APPLICATION`"]),
    "protected_attributes": ("May age, gender or nationality play any part, in the scorecard for instance?",
                             ["**Fairness:**"]),
    "tenure_review": ("Is there a rule about applicants new in their job?", ["Our habit: applicants with fewer than"]),
    "branch_notes": ("What should the program do with a branch manager's note asking for full approval?",
                     ["**Branch notes:**"]),
    "credit_lines_easy": ("Do credit lines count in the DSR?", ["This round that cap is **our own affordability"]),
    "regulator_notice_easy": ("Does the regulator's DSR notice change the cap this round?",
                              ["This round that cap is **our own affordability",
                               "This round the **notices are out of scope**"]),
    "declared_income": ("Do I use the declared salary or the income documents?",
                        ["This round the **notices are out of scope**",
                         "(our operations team checks the documents before payout)"]),
    "repayments_unused": ("Should a repayment notice change the customer's debts?",
                          ["This round the **notices are out of scope**",
                           "(our operations team checks the documents before payout)"]),
    "credit_line_amortization": ("How does a credit line count in the DSR?", ["That cap is the regulator's limit."]),
    "stress_rate": ("Is there a stressed rate for customers with a lot of debt?", ["**Stress rate:**"]),
    "period_budget": ("Is there a budget for the whole period?", ["**Period budget:**"]),
    "budget_notice": ("What does a budget_change notice do?", ["**Period budget:**"]),
    "regulatory_notice": ("What does a regulation_change notice do?", ["**Regulatory change:**"]),
    "near_prime_threshold": ("Who counts as near-prime?", ["**Near-prime commitment:**"]),
    "near_prime_quota": ("Is there a commitment on near-prime lending, and how is it measured?",
                         ["**Near-prime commitment:**"]),
    "verified_income": ("Which salary do I use when the documents disagree with the declaration?",
                        ["**Income verification:**"]),
    "income_discrepancy": ("What happens when a document shows a much lower salary than declared?",
                           ["**Income discrepancy:**"]),
    "document_corrections": ("What happens when a corrected document arrives for an application I referred?",
                             ["**Document corrections:**"]),
    "repayments": ("When a repayment is confirmed, from when does the debt stop counting?", ["**Repayments:**"]),
    "split_applications": ("Can a customer get several approvals on the same day?", ["**Split applications:**"]),
}
NUMBER = re.compile(r"\d(?:[\d.,  ]*\d)?")
TOKEN = re.compile(r"`([^`]+)`|\{\{\s*(\w+)\s*\}\}|\b([A-Z][A-Z_]{3,})\b")


def numbers(text: str) -> list[str]:
    """The numbers of two digits or more in a passage, as a set, separators dropped (1,000 = 1.000 = 1000; 33.17 =
    33,17), placeholders left out. Single digits are left out: one language writes "two bureaus" or "per day" in
    words where another writes 2社 or 1日."""
    text = re.sub(r"\{\{\s*\w+\s*\}\}", " ", text)
    return sorted({n for n in (re.sub(r"[.,  ]", "", m) for m in NUMBER.findall(text)) if len(n) > 1})


def tokens(text: str) -> list[str]:
    return sorted({next(g for g in m if g) for m in TOKEN.findall(text)})


def scorer_numbers() -> set[str]:
    """Numbers the scorer knows: case.py's constants and every parameter candidate, as numbers() writes them."""
    from fdebench2.cases import NativeCase
    mod = NativeCase(ROOT).module
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    vals = [mod.MIN_AMOUNT, mod.MAX_AMOUNT, mod.TERM, mod.APR, mod.STRESS_APR, mod.per_1000(), mod.per_1000(mod.STRESS_APR),
            mod.MARGIN * 100, mod.LGD * 100, mod.REFER_COST, mod.REFERRAL_CAPACITY, mod.LINE_YEARS, mod.STRESS_THRESHOLD,
            mod.N_DAYS, mod.N_HISTORY, mod.B_OFFSET, mod.REG_CUT, mod.BUDGET_CUT, 12, 100, 0, 1, 0.1, 19, 2, 27, 2026,
            1000, 55, 560]
    vals += [v for p in meta["params"].values() for v in (p["values"] if isinstance(p["values"], list)
                                                         else sum(p["values"].values(), []))]
    out = set()
    for v in vals:
        s = f"{v:g}" if isinstance(v, float) else str(v)
        out.add(s.replace(".", ""))
    return out


def main() -> None:
    req = {lang: (ROOT / "locales" / lang / "requirements.md").read_text(encoding="utf-8").split("\n")
           for lang in LOCALES}
    assert len({len(v) for v in req.values()}) == 1, "the locales' requirements are no longer line by line"
    targets = yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))
    known = scorer_numbers()
    lines_of = {}
    for t in targets:
        found = []
        for piece in ASK[t["id"]][1]:
            hits = [k for k, line in enumerate(req["en"]) if piece in line]
            assert len(hits) == 1, (t["id"], piece, hits)
            found.append(hits[0])
        lines_of[t["id"]] = found
    out = ["# Client answers review — finance/loan_underwriting_specialist", "",
           "**Status: awaiting human review.** No human has reviewed these entries yet.", "",
           "The simulated client answers only from `locales/<lang>/requirements.md` (plus event facts). For every "
           "target: the question an engineer would naturally ask, the passage each locale answers from (the five "
           "requirements are translated line by line, so the same lines; `{{…}}` is the rule seed's value, filled in "
           "per setting), and a machine pre-check: the same numbers and identifiers in every locale, no number the "
           "scorer does not know, and which other targets the same passage also states (a client quoting it whole "
           "would answer more than was asked). Generated by `make_client_review.py`.", ""]
    for t in targets:
        tid = t["id"]
        q, _ = ASK[tid]
        lines = lines_of[tid]
        out += [f"## `{tid}`", "", f"In force: {', '.join(t.get('tiers', ['easy', 'medium', 'hard']))}. "
                f"Target: {t['text']}", "", f"**Question:** {q}", ""]
        passages = {lang: [req[lang][k] for k in lines] for lang in LOCALES}
        for lang in LOCALES:
            out.append(f"- {lang} (line{'s' if len(lines) > 1 else ''} {', '.join(str(k + 1) for k in lines)}):")
            out += [f"  > {line}" for line in passages[lang]]
        nums = {lang: numbers(" ".join(passages[lang])) for lang in LOCALES}
        ids = {lang: tokens(" ".join(passages[lang])) for lang in LOCALES}
        same_nums = [lang for lang in LOCALES if nums[lang] != nums["en"]]
        same_ids = [lang for lang in LOCALES if ids[lang] != ids["en"]]
        unknown = sorted({n for n in nums["en"] if n not in known})
        also = sorted({o for o, ls in lines_of.items() if o != tid and set(ls) & set(lines)})
        out += ["", "Machine pre-check:",
                f"- numbers of two digits or more ({', '.join(nums['en']) or 'none'}): " + (
                    "the same in every locale" if not same_nums else f"DIFFER in {', '.join(same_nums)}"),
                f"- identifiers ({', '.join(ids['en']) or 'none'}): " + (
                    "the same in every locale" if not same_ids else f"DIFFER in {', '.join(same_ids)}"),
                "- against the scorer: " + ("every number is one case.py or case.yaml uses" if not unknown else
                                            f"numbers the scorer does not use: {', '.join(unknown)}"),
                "- answers more than asked: " + ("no other target in these lines" if not also else
                                                 "the same lines also state " + ", ".join(f"`{o}`" for o in also)),
                "", "Reviewer verdict:", ""]
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "CLIENT_REVIEW.md"
    dest.write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
