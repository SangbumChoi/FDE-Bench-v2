"""Write CLIENT_REVIEW.md: for every target, the question an engineer would ask, the passage of requirements.md each
of the five locales answers from (the locales' requirements are translated line by line), and a machine pre-check of
those passages. The verdicts are left for a human reviewer:
    python cases/public_sector/benefits_eligibility_officer/client_review.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))
LOCALES = ("en", "zh", "ko", "ja", "es")

# target -> (the question, the en lines it is answered from, each found by a piece of its text)
ASK = {
    "earned_disregard": ("Is any part of the earnings from work left out of the income, and how much?",
                         ["- **Countable income** (members at the address only"]),
    "residency": ("How long must a household have lived in the city to qualify?", ["- **Residency**: the household"]),
    "uprating": ("The amount table is last year's. What are this year's amounts?",
                 ["- **This year's amounts**: `amount_table_2025.csv`"]),
    "renewals": ("How should the renewals be decided: re-assessed like new applications, or something else?",
                 ["- **Renewals** (`application_type = renewal`"]),
    "assets_out_of_round": ("Do I apply a savings or asset test this round?", ["- **Assets**: the intake desk"]),
    "supplement_out_of_round": ("Is there an extra amount for members with a disability this round?",
                                ["- **Disability**: the disability supplement"]),
    "child_support_out_of_round": ("Does child support count as income this round?", ["- **Child support**: the"]),
    "changes_out_of_round": ("Some households reported changes after applying. Do I take them into account?",
                             ["- **Reported changes**: the changes in",
                              "The changes in `reported_changes.csv` are handled separately this round"]),
    "circular_out_of_round": ("There is a finance circular about a heating supplement. Does it apply this round?",
                              ["- **Letters**: the documents in the `correspondence` folder",
                               "The documents in the `correspondence` folder are handled separately too"]),
    "asset_limit": ("Is there a limit on savings and property, and what is it?", ["- **Assets** (`assets.csv`)"]),
    "disability_supplement": ("Is there an extra amount for members with a disability, and how much?",
                              ["- **Need**: standard amount for the household size"]),
    "child_support": ("Does child support count as income?",
                      ["- **Countable income** (members at the address only"]),
    "amount_cap": ("Is there a maximum monthly amount?", ["- **Amount**: need − countable income"]),
    "reported_changes": ("Some households reported changes after applying. Which ones count?",
                         ["- **Reported changes** (`reported_changes.csv`)"]),
    "exception_requests": ("A councillor and an applicant ask for exceptions in the correspondence. Should I follow "
                           "them?", ["- **Letters asking for exceptions**"]),
}
NUMBER = re.compile(r"\d(?:[\d.,  ]*\d)?")
TOKEN = re.compile(r"`([^`]+)`|\{\{\s*(\w+)\s*\}\}|\b([A-Z][A-Z_]{3,})\b")
PLACEHOLDERS = {"earned_flat", "earned_ignored", "earned_counted", "residency_days", "residency_example", "uprating",
                "std1", "house1", "asset_base", "asset_extra", "disability_supplement", "cap"}


def numbers(text: str) -> list[str]:
    """The numbers of two digits or more in a passage, as a set, separators dropped (6,000 = 6.000 = 6000),
    placeholders and dates left out (each locale writes a date its own way)."""
    text = re.sub(r"<!--.*?-->", " ", text)
    text = re.sub(r"\{\{\s*\w+\s*\}\}", " ", text)
    text = re.sub(r"\d{1,2}/\d{1,2}/\d{4}|\d{4}年\d{1,2}月\d{1,2}日|\d{4}\. \d{1,2}\. \d{1,2}\.", " ", text)
    return sorted({n for n in (re.sub(r"[.,  ]", "", m) for m in NUMBER.findall(text)) if len(n) > 1})


def tokens(text: str) -> list[str]:
    """The identifiers of a passage: the reason codes and placeholders (a backticked word that is neither, such as a
    localized column or folder name, is left out: it is meant to differ)."""
    found = set()
    for m in TOKEN.findall(text):
        word = next(g for g in m if g)
        if re.fullmatch(r"[A-Z][A-Z_]{3,}", word) or word in PLACEHOLDERS:
            found.add(word)
    return sorted(found)


def scorer_numbers() -> set[str]:
    """Numbers the scorer knows: case.py's constants and every parameter candidate, as numbers() writes them."""
    from fdebench2.cases import NativeCase
    mod = NativeCase(ROOT).module
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    vals = [10, mod.N_HOUSEHOLDS, mod.WRONG_DECISION_PENALTY, mod.WRONG_REASON_PENALTY, mod.REASSESSMENT_COST,
            mod.HEATING, mod.LAST_YEAR_SUPPLEMENT, 2025, 2026, *mod.LAST_YEAR_EARNED, *mod.LAST_YEAR[1],
            *(v for table in mod.CAP_TABLES.values() for v in table), *(v for x in mod.EARNED.values() for v in x),
            *(v for x in mod.ASSET_LIMITS.values() for v in x)]
    vals += [v for p in meta["params"].values() for v in (p["values"] if isinstance(p["values"], list)
                                                         else sum(p["values"].values(), []))]
    return {(f"{v:g}" if isinstance(v, float) else str(v)).replace(".", "") for v in vals}


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
    out = ["# Client answers review: public_sector/benefits_eligibility_officer", "",
           "**Status: awaiting human review.** No human has reviewed these entries yet.", "",
           "The simulated client answers only from `locales/<lang>/requirements.md`. For every target: the question an "
           "engineer would naturally ask, the passage each locale answers from (the five requirements are translated "
           "line by line, so the same lines; `{{…}}` is the rule seed's value, filled in per setting, and `<!-- … -->` "
           "marks a passage kept only in some tiers or for some values), and a machine pre-check: the same numbers and "
           "identifiers in every locale (dates left out, as each locale writes them its own way), no number the scorer "
           "does not know, and which other targets the same passage also states (a client quoting it whole would "
           "answer more than was asked). Generated by `client_review.py`.", ""]
    for t in targets:
        tid = t["id"]
        q, _ = ASK[tid]
        lines = lines_of[tid]
        out += [f"## `{tid}`", "", f"In force: {', '.join(t.get('tiers', ['easy', 'medium', 'hard']))}. "
                f"Target: {t['text']}", "", f"**Question:** {q}", ""]
        passages = {lang: [req[lang][k] for k in lines] for lang in LOCALES}
        for lang in LOCALES:
            out.append(f"- {lang} (line{'s' if len(lines) > 1 else ''} {', '.join(str(k + 1) for k in lines)}):")
            out += [f"  > {line.strip()}" for line in passages[lang]]
        nums = {lang: numbers(" ".join(passages[lang])) for lang in LOCALES}
        ids = {lang: tokens(" ".join(passages[lang])) for lang in LOCALES}
        differ_nums = [lang for lang in LOCALES if nums[lang] != nums["en"]]
        differ_ids = [lang for lang in LOCALES if ids[lang] != ids["en"]]
        unknown = sorted({n for n in nums["en"] if n not in known})
        also = sorted({o for o, ls in lines_of.items() if o != tid and set(ls) & set(lines)})
        out += ["", "Machine pre-check:",
                f"- numbers of two digits or more ({', '.join(nums['en']) or 'none'}): " + (
                    "the same in every locale" if not differ_nums else f"DIFFER in {', '.join(differ_nums)}"),
                f"- identifiers ({', '.join(ids['en']) or 'none'}): " + (
                    "the same in every locale" if not differ_ids else f"DIFFER in {', '.join(differ_ids)}"),
                "- against the scorer: " + ("every number is one case.py or case.yaml uses" if not unknown else
                                            f"numbers the scorer does not use: {', '.join(unknown)}"),
                "- answers more than asked: " + ("no other target in these lines" if not also else
                                                 "the same lines also state " + ", ".join(f"`{o}`" for o in also)),
                "", "Reviewer verdict:", ""]
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "CLIENT_REVIEW.md"
    dest.write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
