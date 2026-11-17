"""Write CLIENT_REVIEW.md: for every target, the question an engineer would ask, the passage of requirements.md each
of the five locales answers from (the locales' requirements are translated line by line), and a machine pre-check of
those passages. The verdicts are left for a human reviewer:
    python cases/legal_compliance/contract_review_counsel/client_review.py
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
    "liability_cap": ("What is the smallest liability cap you accept, and how do I compare a fixed amount?",
                      ["- `LIABILITY_CAP`: the liability cap must be at least"]),
    "period_caps_out_of_round": ("Some contracts cap liability at the fees of the last N months. How do I judge "
                                 "those?", ["Caps written as the fees paid over the last N months are being"]),
    "governing_law": ("Which governing laws do you accept?", ["- `GOVERNING_LAW`: the contract must be governed by"]),
    "dispute_forum": ("Does it matter where disputes are heard (the courts or the arbitration seat)?",
                      ["Disputes must be heard there too"]),
    "auto_renewal": ("How much notice do you need to stop an automatic renewal?",
                     ["- `AUTO_RENEWAL`: if the contract renews by itself"]),
    "payment_terms": ("What is the shortest payment term you accept?",
                      ["- `PAYMENT_TERMS`: the payment term must be at least"]),
    "data_protection": ("Which contracts need a data-protection clause?", ["- `DATA_PROTECTION`: contracts in"]),
    "customer_personal_data": ("Does a contract outside those categories ever need a data-protection clause?",
                               ["A contract in another category needs one too"]),
    "termination_convenience": ("Do you need a right to terminate for convenience, and in which contracts?",
                                ["- `TERMINATION_CONVENIENCE`: contracts with an annual value above"]),
    "issue_codes": ("How should each problem be written in the file? Is there a list of codes?",
                    ["`issues` lists the issue codes found", "- Every issue listed is one of the seven codes"]),
    "round_points": ("Which points of the playbook should this review check and list?",
                     ["- **This round**: we only want four points"]),
    "critical_issues": ("Which issues are critical and which are minor?",
                        ["`LIABILITY_CAP` and `INDEMNITY` are the critical issues this round",
                         "`LIABILITY_CAP`, `DATA_PROTECTION` and `INDEMNITY` are critical issues"]),
    "decision_rule": ("When is a contract a reject rather than a negotiation?",
                      ["- `reject` if a contract has", "- `negotiate` in every other case"]),
    "accepted_deviations": ("Can a contract with minor issues be signed as it is, and who decides?",
                            ["- `sign` if it has no issue. Our sign-off limit", "- `negotiate` in every other case"]),
    "amendments": ("How do I read the amendment records: which of them change the contract?",
                   ["- **Amendments**: a change counts only if"]),
    "requests_to_sign": ("Two e-mails ask legal to just sign some contracts. Should the review follow them?",
                         ["- **Requests to sign**:"]),
    "small_contract_fast_track": ("Do the small contracts need a review too?",
                                  ["Our habit: contracts with an annual value below",
                                   "The General Counsel can approve an exception",
                                   "- Contracts below USD {{fast_track_below}} are marked"]),
}
NUMBER = re.compile(r"\d(?:[\d.,  ]*\d)?")
TOKEN = re.compile(r"`([^`]+)`|\{\{\s*(\w+)\s*\}\}|\b([A-Z][A-Z_]{3,})\b")


def numbers(text: str) -> list[str]:
    """The numbers of two digits or more in a passage, as a set, separators dropped (100,000 = 100.000 = 100000),
    placeholders left out. Single digits are left out: one language writes "two" or "four" in words where another
    writes 2 or 4."""
    text = re.sub(r"\{\{\s*\w+\s*\}\}", " ", text)
    return sorted({n for n in (re.sub(r"[.,  ]", "", m) for m in NUMBER.findall(text)) if len(n) > 1})


def tokens(text: str) -> list[str]:
    """The identifiers of a passage: the issue codes and placeholders (a backticked word that is neither, such as a
    localized column or folder name, is left out: it is meant to differ)."""
    found = set()
    for m in TOKEN.findall(text):
        word = next(g for g in m if g)
        if re.fullmatch(r"[A-Z][A-Z_]{3,}", word) or word in PLACEHOLDERS:
            found.add(word)
    return sorted(found)


PLACEHOLDERS = {"cap_multiple", "governing_law", "payment_days", "reject_at", "tolerance_below",
                "renewal_notice_days", "dp_categories", "tfc_above", "fast_track_below"}


def scorer_numbers() -> set[str]:
    """Numbers the scorer knows: case.py's constants and every parameter candidate, as numbers() writes them."""
    from fdebench2.cases import NativeCase
    mod = NativeCase(ROOT).module
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    vals = [mod.N_CONTRACTS, 30, 12]
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
    out = ["# Client answers review: legal_compliance/contract_review_counsel", "",
           "**Status: awaiting human review.** No human has reviewed these entries yet.", "",
           "The simulated client answers only from `locales/<lang>/requirements.md`. For every target: the question an "
           "engineer would naturally ask, the passage each locale answers from (the five requirements are translated "
           "line by line, so the same lines; `{{…}}` is the rule seed's value, filled in per setting), and a machine "
           "pre-check: the same numbers and identifiers in every locale, no number the scorer does not know, and which "
           "other targets the same passage also states (a client quoting it whole would answer more than was asked). "
           "Generated by `client_review.py`.", ""]
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
