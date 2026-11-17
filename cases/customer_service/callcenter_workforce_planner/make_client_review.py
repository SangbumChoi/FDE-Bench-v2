"""Writes CLIENT_REVIEW.md: for every target, the question an engineer would ask, the passage of requirements.md
each of the five locales answers from (the locales' requirements are translated line by line), and a machine
pre-check of those passages. The verdicts are left for a human reviewer:
python cases/customer_service/callcenter_workforce_planner/make_client_review.py
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
    "one_language": ("Can a bilingual agent cover two languages at once, or do they take one language per shift?",
                     ["An agent takes calls in exactly one language"]),
    "understaffing_price": ("How do you weigh a missing agent against the labor cost?", ["**Quality**:"]),
    "ft_contract_week": ("How many hours or shifts a week does a full-timer work, and can they work more?",
                         ["A full-timer's contract week is", "Nobody works beyond the contract week this round",
                          "We do not plan overtime."]),
    "pt_contract_week": ("How many shifts a week can a part-timer work, and how are they paid?",
                         ["A part-timer's contract is"]),
    "min_rest": ("Is there a minimum rest between two shifts of the same agent?",
                 ["Between the end of one shift and the start"]),
    "holiday": ("Is any day next week special: a holiday, an event, a day the forecast does not reflect?",
                ["is a regional public holiday in our main market"]),
    "training_salary": ("How are new hires paid? Does a shift they do not work save anything?",
                        ["New hires are on a training salary"]),
    "buddy_rule": ("Can new hires be rostered like everyone else?", ["A new hire is never alone on a language"]),
    "sick_call": ("Is the team lead's note still right: will that agent be back on Monday?",
                  ["is out of date. On Friday morning"]),
}
NUMBER = re.compile(r"\d(?:[\d.,  ]*\d)?")
CODE = r"(?<![A-Za-z0-9_])({})(?![A-Za-z0-9_])"
TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}|" + CODE.format(r"[A-Z][A-Z_0-9]{3,}") + "|" + CODE.format(r"\d\d:\d\d"))
# words one language writes in figures and another in letters: the month in a CJK date (11月6日, 11월 6일; English
# and Spanish name the month) and the half-hour slot written as 30 minutes (30分, 30분; "half-hour", "media hora")
IN_WORDS = re.compile(r"\d+\s*(?:月|월)|30\s*(?:分|분)")


def numbers(text: str) -> list[str]:
    """The numbers of two digits or more in a passage, as a set, separators dropped (1,000 = 1.000 = 1000; 1,5 =
    1.5), placeholders, clock times (identifiers, below) and IN_WORDS left out. Single digits are left out: one
    language writes "one extra shift" in words where another writes 1回."""
    text = TOKEN.sub(" ", IN_WORDS.sub(" ", text))
    return sorted({n for n in (re.sub(r"[.,  ]", "", m) for m in NUMBER.findall(text)) if len(n) > 1})


def tokens(text: str) -> list[str]:
    """Identifiers in a passage: placeholders, upper-case codes such as shift ids, and clock times. Back-quoted
    names are left out: file and column names are localized (`team_lead_note.txt` is `팀장_메모.txt` in Korean)."""
    return sorted({next(g for g in m if g) for m in TOKEN.findall(text)})


def scorer_numbers() -> set[str]:
    """Numbers the scorer knows: case.py's constants and every parameter candidate, as numbers() writes them."""
    from fdebench2.cases import NativeCase
    mod = NativeCase(ROOT).module
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    vals = [mod.OVERTIME, mod.RATE["FT"], mod.RATE["PT"], 30, 2026, 22, 8, 10, 11, 12, 13, 15, 16, 21, 30, 6, 9]
    vals += [int(d[-2:]) for d in ("2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-15")]
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
    out = ["# Client answers review — customer_service/callcenter_workforce_planner", "",
           "**Status: awaiting human review.** No human has reviewed these entries yet.", "",
           "The simulated client answers only from `locales/<lang>/requirements.md` (plus event facts). For every "
           "target: the question an engineer would naturally ask, the passage each locale answers from (the five "
           "requirements are translated line by line, so the same lines; `{{…}}` is the rule seed's value, filled in "
           "per setting, and `<!-- tier -->` markers keep a line only in the tiers they name), and a machine "
           "pre-check: the same numbers and identifiers in every locale, no number the scorer does not know, and "
           "which other targets the same passage also states (a client quoting it whole would answer more than was "
           "asked). Generated by `make_client_review.py`.", ""]
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
