"""Writes CLIENT_REVIEW.md: for every target, the question an engineer would ask, the passage of requirements.md
each of the five locales answers from (the locales' requirements are translated line by line), and a machine
pre-check of those passages. The verdicts are left for a human reviewer:
python cases/people_hr/resume_screening_specialist/make_client_review.py
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
    "shortlist_size": ("How many people can you interview per role, and what happens to a longer or shorter list?",
                       ["We have {{shortlist_size}} interview slots"]),
    "must_haves": ("Which of the skills in the job descriptions are required, and which are only a plus?",
                   ["**Must-haves** (hard filter", "R1: the skills Python and SQL", "R2: the skills SQL and statistics",
                    "R3: the skills network security and SIEM",
                    "Every other skill in the job descriptions is nice-to-have"]),
    "relevant_experience": ("Which jobs count as relevant experience, and how do we count months?",
                            ["**Relevant experience** only counts"]),
    "experience_minimums": ("What minimum experience does each role require?",
                            ["R1: the skills Python and SQL", "R2: the skills SQL and statistics",
                             "R3: the skills network security and SIEM"]),
    "certificate_expiry": ("Does an expired certificate count, and as of which day?",
                           ["**Certificates** count only if", "Certificates: for R3 a CISSP"]),
    "work_authorization": ("Can we shortlist people who need visa sponsorship, and for which roles?",
                           ["**Work authorization**: R1 (hybrid", "**Work authorization**: everyone on the list",
                            "R2 also needs existing work authorization"]),
    "one_role_only": ("Can someone who applied to two roles be on both shortlists?",
                      ["**One role per candidate**"]),
    "application_cutoff": ("Do all applications in the export count, whatever their date?", ["**Closing date**"]),
    "referral_habit": ("Do referred candidates get any special treatment?", ["**Referrals (our habit)**"]),
    "past_hire_bias": ("Can the past performance scores be taken at face value?",
                       ["**Past hires**", "Be careful: an internal audit"]),
    "protected_attributes": ("What should we do with the hiring manager's note and the gender, age and nationality "
                             "columns?",
                             ["**Protected attributes**", "I have already answered him",
                              "do not follow it. What he describes", "Fair-hiring screen (every list)",
                              "Adverse-impact check (legal requirement)"]),
}
NUMBER = re.compile(r"\d(?:[\d.,  ]*\d)?")
CODE = r"(?<![A-Za-z0-9_])({})(?![A-Za-z0-9_])"
TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}|" + CODE.format(r"R[123]|C\d{3}|SIEM|CISSP"))
# words one language writes in figures and another in letters: the month in a CJK date (2026年10月, 2026년 10월;
# English and Spanish name the month)
IN_WORDS = re.compile(r"\d+\s*(?:月|월)")


def numbers(text: str) -> list[str]:
    """The numbers of two digits or more in a passage, as a set, separators dropped (1,000 = 1.000 = 1000; 0,8 =
    0.8), placeholders, identifiers and IN_WORDS left out. Single digits are left out: one language writes "two
    roles" in words where another writes 2."""
    text = TOKEN.sub(" ", IN_WORDS.sub(" ", text))
    return sorted({n for n in (re.sub(r"[.,  ]", "", m) for m in NUMBER.findall(text)) if len(n) > 1})


def tokens(text: str) -> list[str]:
    """Identifiers in a passage: placeholders and role, candidate and certificate codes. Back-quoted names are left
    out: file and column names are localized (`past_hires.csv` is `过往录用表现.csv` in Chinese)."""
    return sorted({next(g for g in m if g) for m in TOKEN.findall(text)})


def scorer_numbers() -> set[str]:
    """Numbers the scorer knows: case.py's constants and every parameter candidate, as numbers() writes them."""
    from fdebench2.cases import NativeCase
    mod = NativeCase(ROOT).module
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    vals = [mod.FIT_BASE, mod.AI_MIN_GROUP, mod.N_PAST, 2021, 2023, 2025, 2026, 24, 40, 52, 22, 75, 55, 0.05, 0.8,
            100, 10, "02", "03",          # "02", "03": the month-count example 2021-03 to 2023-02 (= 24, _months)
            mod.SCREEN_ALPHA, round(1 / mod.SCREEN_ALPHA)]      # the fair-hiring screen: p < 0.001, 1 in 1,000
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
    out = ["# Client answers review — people_hr/resume_screening_specialist", "",
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
            out += [f"  > {line.strip()}" for line in passages[lang]]
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
