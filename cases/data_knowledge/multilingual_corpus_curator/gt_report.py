"""Write GT.md (the case's ground truth in five parts) and CLIENT_REVIEW.md (what the simulated client answers from).

Run from the repository root:  python cases/data_knowledge/multilingual_corpus_curator/gt_report.py [gt] [client]
GT.md takes every number in its tables from dataset/audit.json (`fdebench2 audit-case`, public world) and the counts
of the hidden drive from the case's generator; the prose around them is fixed here. Neither file quotes the audit's
fingerprint, so writing them again after a fresh audit of the same sources gives the same files. Both are case docs
(cases.CASE_DOCS), outside the audit's fingerprint, so writing them never makes the stored audit stale.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import median

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))

from fdebench2.audit import (cross_flag_summary, false_negatives, shortcut_summary, target_summary,  # noqa: E402
                             tier_order)
from fdebench2.cases import NativeCase  # noqa: E402

TIERS = ("easy", "medium", "hard")
LANGS = ("en", "zh", "ko", "ja", "es")

# Why each rule is a hard gate (validity check), in the client's terms.
RULE_WHY = {
    "utf8_output": "the catalogue system reads the library and the manifest as UTF-8; a file in another encoding "
                   "shows as mojibake or is rejected on import",
    "safe_names": "the library is copied to Windows and macOS shares and archived; a name a file system cannot hold "
                  "breaks the copy",
    "one_file_per_book": "the catalogue holds one record per book; a second file for the same book is a duplicate "
                         "entry somebody has to find and delete",
    "review_reason": "the review team works the queue by reason code; a free-text reason cannot be routed",
    "manifest_rows": "the manifest is how the team finds what went where: a library file it does not list, a row "
                     "pointing at no file, a placed row that names no file of the drive (nothing to trace the book "
                     "back to) or a file listed twice makes the index wrong (mandatory output)",
    "review_copies": "the review team looks at the material, not at a manifest row: a book sent to review without "
                     "its files cannot be reviewed (mandatory output)",
    "no_fabrication": "a made-up or placeholder blurb would be published as the book's description; the client said "
                      "nothing may be invented",
    "no_guessing": "a book filed under a guessed year or under a generic file name as its title is a wrong catalogue "
                   "record; the request says anything that cannot be filed is set aside, not guessed",
    "missing_author_review": "the catalogue does not shelve anonymous books (the client's cataloguing policy; an "
                             "approved exception can bend it, scored with the rule switched off and a penalty)",
    "missing_author_shelved": "under a shelving policy the catalogue team agreed on one placeholder name for every "
                              "author-less book; another name, or the review queue, breaks that agreement",
}
# Facts that were targets before this audit and are not now (they stay in requirements.md as context, where the
# client still answers them), with why. `kinds` are the hidden books they concern: an upper bound on the damage of
# misreading the fact is those books lost entirely.
REMOVED = {
    "name_rules": ("split into `separator` and `max_len`; the fixed steps (NFKC, a forbidden character becomes a "
                   "space, trimming) concern only the full-width, decomposed and `: ?` titles, and replacing a "
                   "forbidden character by nothing gives the same name once whitespace runs collapse",
                   ("m_width", "m_forbidden")),
    "manifest_review": ("replaced by `review_codes`: the manifest columns, one row per book with `;`-separated "
                        "sources and the `_review/` copies are in the program interface the agent sees, and are "
                        "enforced as rules (`manifest_rows`, `review_copies`); the six codes are the client's", ()),
    "precedence": ("the ranking (embedded metadata > title page > file name) decides only the books whose title "
                   "page disagrees with their metadata", ("m_precedence",)),
    "scoring": ("how the result is judged changes no correct deliverable, so there is nothing to misread; the "
                "judging section stays in requirements.md", ()),
    "encodings": ("a data fact the sample shows (files that are not UTF-8), not a client fact (REVIEW.md F7)",
                  ("m_encoding",)),
    "year_notations": ("a data fact the sample shows (era, Minguo, Dangi, Chinese-numeral and Roman years; F7)",
                       ("m_era",)),
    "duplicates": ("a data fact the sample shows, and one book = one file is in the program interface (F7)",
                   ("m_dup",)),
    "containers": ("a data fact the sample shows (zip archives, catalog CSVs, scans, junk; F7)",
                   ("h_zip", "h_csv", "h_scan_only", "h_scan_plus")),
    "author_variants": ("the official pair is the one the drive itself gives (the author's other books); it concerns "
                        "few books", ("m_variant",)),
    "exceptions": ("split into `no_description`, `conflict` and `generic_titles`; the rest (a field taken from "
                   "another file of the book, a meaningful file name as the title, a year from a `©` line) is the "
                   "natural reading of the data and concerns 2-3 books each",
                   ("h_author_recover", "h_desc_recover", "h_title_filename", "h_year_copyright")),
}


def _num(x, digits=3):
    return "–" if x is None else f"{x:.{digits}f}"


def _table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def _fact(text: str) -> str:
    """A target's English text with its parameters and setting blocks written generically."""
    text = re.sub(r"<!-- when: (\w+)=([\w,]+) -->(.*?)<!-- /when -->", lambda m: f" [{m.group(2)}: {m.group(3)}]",
                  text)
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: f"*{m.group(1)}*", text).replace("|", "/").strip()


def _diag(s: dict) -> str:
    return "no" if not s["has_diagnostic"] else ("untested" if s["separates"] is None else
                                                "separates" if s["separates"] else "does not separate")


def gt(case: NativeCase) -> str:
    module = case.module
    audit = json.loads((ROOT / "dataset" / "audit.json").read_text(encoding="utf-8"))
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    targets = yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))
    summary = {t["target"]: t for t in target_summary(audit)}
    tiers = tier_order(audit["settings"])
    n_set = {t: len([e for e in audit["settings"][t] if not e.get("skipped")]) for t in tiers}
    hidden = case.world.hidden
    kinds = Counter(b.kind for b in hidden.books)
    scope_n = {t: sum(1 for b in hidden.books if TIERS.index(b.scope) <= TIERS.index(t)) for t in TIERS}
    spans = {t: min(b["span"] for b in audit["bounds"] if b["setting"].startswith(t + "/")) for t in tiers}
    out = [f"# Ground truth: {audit['case']}", "",
           "The ground truth (GT) of a setting in five parts, with the reference as supporting evidence. Generated "
           "by `gt_report.py` from `dataset/audit.json` (`fdebench2 audit-case`, public world seed "
           f"{audit['world_seed']}): {sum(n_set.values())} settings, "
           + ", ".join(f"{t} {n_set[t]}" for t in tiers)
           + " (each tier's public panel plus admissible parameter combinations). Damage is 1 − credit, credit = 0 "
           "for an invalid program, else the quality score clipped to [0, 1]; a target bites in a setting when "
           f"misreading it alone loses at least {audit['thresholds']['ablation_min_damage']:.2f} of the credit (for a "
           "drawn parameter: its least harmful wrong candidate). The program runs once per setting on the hidden "
           f"drive ({len(hidden.books)} books, {len(hidden.files)} files; {scope_n['easy']} / {scope_n['medium']} / "
           f"{scope_n['hard']} scored in easy / medium / hard).", ""]

    # 1. client facts
    out += ["## 1. Client facts (targets)", "",
            "One row per target: the fact, the tiers where it is in force, how the audit misreads it (a drawn "
            "parameter: the reference written for each other candidate; another fact: the reference with one switch "
            "of `reference/organize.py` flipped, the most natural misreading of the data), the damage range over the "
            "settings where it is in force, the settings where it bites per tier (k/n) and whether its diagnostic "
            "(`enforced`, part 5) tells the reference from the misreading.", ""]
    rows = []
    for t in targets:
        s = summary.get(t["id"])
        if s is None:
            continue
        how = []
        if "param" in s["sources"]:
            how.append(f"the reference of each other candidate of `{t['param']}`")
        if "hook" in s["sources"]:
            flag, text = module.MISREADINGS[t["id"]]
            how.append(f"`{flag}`: {text}")
        bites = ", ".join(f"{tier} {k}/{n}" for tier, (k, n) in s["per_tier"].items())
        rows.append([f"`{t['id']}`", _fact(t["text"]), ", ".join(s["tiers"]), "; ".join(how) or "none",
                     f"{_num(s['low'])}–{_num(s['high'])}", bites, _diag(s)])
    out += _table(["target", "fact", "in force", "ablation (the natural misreading)", "damage", "bites k/n",
                   "diagnostic"], rows)
    out += ["", "Why the drawn rules bite: a book whose description sits at another path is misfiled and earns "
            f"{module.MISFILED_CREDIT} instead of 1, whichever component is wrong, and every rule reaches many books "
            f"of the hidden drive: two years ({sum(1 for b in hidden.books if b.edition is not None)} books), Chinese, "
            f"Korean or Japanese ({sum(1 for b in hidden.books if b.lang in module.CJK)}), two authors "
            f"({sum(1 for b in hidden.books if len(b.authors) > 1)}), a long subtitled title "
            f"({sum(1 for b in hidden.books if ' — ' in b.title)}).", "",
            "Facts that are no longer targets (they stay in requirements.md, and the client still answers them when "
            "asked). The bound is the damage if every hidden book the fact concerns were lost entirely (credit 0), "
            "per tier where such books are scored, against that tier's narrowest quality scale; a target must "
            "reach 0.10 in every tier where it is in force. A bound of 0.10 or more means the fact could matter, "
            "and it is removed for the reason given, not for its weight:", ""]
    def scope_of(kind):
        return "easy" if kind == "easy" else "medium" if kind.startswith("m_") else "hard"
    for name, (why, ks) in REMOVED.items():
        k = sum(kinds[x] for x in ks)
        if not k:
            out.append(f"- `{name}`: {why}.")
            continue
        per_tier = {t: sum(kinds[x] for x in ks if TIERS.index(scope_of(x)) <= TIERS.index(t)) / scope_n[t] / spans[t]
                    for t in tiers}
        out.append(f"- `{name}`: {why}. {k} hidden book(s); damage at most "
                   + ", ".join(f"{per_tier[t]:.3f} in {t}" for t in tiers if per_tier[t] > 0)
                   + (" (below 0.10 in hard, a tier where it would be in force)" if per_tier["hard"] < 0.10 else "")
                   + ".")

    # 2. validity checks
    out += ["", "## 2. Validity checks (hard gates)", "",
            "A program that breaks any of these on the hidden drive is invalid and earns no credit. A program that "
            "writes no `manifest.csv` (or crashes before it) is fatal. The rules are checked on everything the "
            "program writes, also for books the tier does not score.", ""]
    rows = []
    for r in meta["rules"]:
        when = f" (when {', '.join(f'{k} in {v}' for k, v in r['when'].items())})" if r.get("when") else ""
        rows.append([f"`{r['id']}`", r["class"], ", ".join(r.get("tiers", TIERS)) + when, RULE_WHY.get(r["id"], "")])
    out += _table(["rule", "class", "tiers", "why it is a hard gate"], rows)
    out += ["", "**Mandatory outputs.** The library is scored; the manifest and the review area are enforced "
            "directly (`manifest_rows`, `review_copies`), so a program cannot drop them, or keep the manifest's "
            "paths and leave its source column empty or filled with anything but files of the drive, and only lose "
            "a fifth of the credit. The shortcuts below are the degenerate programs a lazy or gaming agent would try; each is "
            f"invalid or scores at most {audit['thresholds']['shortcut_max_quality']} in every measured setting.", ""]
    rows = [[f"`{s['name']}`", s["description"], f"{s['closed']}/{s['settings']}", _num(s["best_quality"], 3)]
            for s in shortcut_summary(audit)]
    out += _table(["shortcut", "what it does", "closed", "best quality where valid"], rows)

    # 3. objective
    out += ["", "## 3. Objective (higher is better)", "",
            "100 × the mean credit per scored book (the tier's books of the hidden drive), minus penalties:", "",
            "- **Filed exactly**: 1 for the book's description at exactly the path the client's rules give. The "
            "catalogue team compares the library with its own catalogue path by path.",
            f"- **Misfiled**: {module.MISFILED_CREDIT} for the right description at any other path, whatever is "
            "wrong in it (layout, year, script, co-authors, separator, length). The description work is not lost, "
            "but somebody has to find the file and move it by hand: a wrong year is as lost on a shelf as a wrong "
            "author. (The first version gave 0.4 plus 0.2 per right component, so one misread rule cost a book only "
            "0.2 and most rules could not matter; see REVIEW.md, Ground truth audit.)",
            f"- **Wrong text**: {module.WRONG_DESC_CREDIT} for the right path holding anything other than the "
            "description (a heading, a title page, a placeholder).",
            "- **Review**: 1 for a book that belongs in review when every manifest row naming its files says "
            f"`review` with its reason code, 0.4 for another agreed code, 0 for rows that disagree or a library file "
            f"as well; a book with no author under the review policy earns {module.NO_AUTHOR_REVIEW_CREDIT} in "
            "review (it is not on the shelf yet; shelving it is the bend, see `missing_author_review`).",
            f"- **Manifest row**: a missing or wrong row for the book costs {module.MANIFEST_SHARE:.0%} of its credit "
            "(the row must be the only one naming the book's files, name all of them, and say placed with its path "
            "or review with the files copied).",
            f"- **Stray files** (medium, hard): {module.EXTRA_PENALTY} per library file that is no book.",
            "", "**Uncertainty.** The program is written on the sample and run once, unseen, on the full drive: the "
            "hidden drive has other books, other archive, catalog and numbered file names, a Shōwa-era year and zip "
            "members one folder deeper than the sample shows. What the program cannot settle from the files (a "
            "missing title or year, conflicting years, no description, no author) is not guessed: it goes to the "
            "review queue, where the team pays for it with its own time (the review credit), never as a wrong "
            "catalogue record (the rules).", ""]

    # 4. reference and bounds
    bounds = audit["bounds"]
    known = [b["best_known_quality"] for b in bounds if b["best_known_quality"] is not None]
    out += ["## 4. Reference and bounds", "",
            "- **Reference** (`reference/organize.py` with the setting's `config.json`): reads every format (JSON, "
            "ONIX, EPUB, DOCX, PDF, HTML, Markdown, text, catalog rows, zip members), decodes legacy encodings by the "
            "corpus's own character statistics, converts every year notation (eras, Minguo, Dangi, Chinese numerals, "
            "Roman numerals, `©` lines), groups copies by normalized title, takes each field by rank from any file "
            "of the book, maps every author to the official pair the drive gives for that person, detects same-rank "
            "year conflicts, and applies the setting's library rules and no-author policy. It files every hidden "
            "book exactly as `expected_output` does.",
            "- **Baseline** (quality 0, `reference/baseline.py`): the client's own script, which shelves only books "
            "with a complete UTF-8 JSON record (title, author, plain four-digit year, description) under the "
            "catalogue rules, leaves a JSON record whose ISBN also has an ONIX export for the team (it cannot tell "
            "which is right) and leaves every other file alone.",
            "- **Best known** (`best_known_solution`): the answer key (`expected_output`) written by a program, an "
            "oracle with every fact of the setting. It reaches the bound like the reference, but is another "
            "deliverable (only the books the tier scores, so no review row in easy and medium), on which the "
            "diagnostic is checked too (part 5).",
            "- **Bound** (`objective_bound`): a proven upper bound on a valid program's objective: every scored book "
            f"earns at most 1, a book with no author under the review policy at most {module.NO_AUTHOR_REVIEW_CREDIT} "
            "(shelving it breaks `missing_author_review`), and penalties only subtract. `expected_output` reaches it, "
            "and so does the reference: the gap is 0 in every measured setting.",
            f"- **quality_cap** = {meta.get('quality_cap')}: the best-known quality is "
            f"{_num(median(known)) if known else '–'} in every measured setting (median "
            f"{_num(median(known)) if known else '–'}, range {_num(min(known)) if known else '–'}–"
            f"{_num(max(known)) if known else '–'}), so a program as good as the reference earns full credit and "
            "nothing scores above it.", ""]
    rows = [[b["setting"], _num(b["reference"], 2), _num(b["baseline"], 2), _num(b["span"]), _num(b["best_known"], 2),
             _num(b["best_known_quality"]), _num(b["bound"], 2), _num(b["bound_quality"]), _num(b["gap_to_bound"])]
            for b in bounds]
    out += _table(["setting", "reference", "baseline", "span", "best known", "its quality", "bound",
                   "bound quality", "gap ref–bound"], rows)
    out += ["", "**Value of asking** (the GT's claim that the client must be asked): per tier, the best program that "
            "never asks against the reference of each setting. `never asks, knows the fixed facts` is the best of "
            "the other settings' references and the baseline (it measures the drawn parameters only); `never asks "
            "(robust)` is `robust_solution`, written from the agent's view alone: the natural reading of every fixed "
            "fact the data and the request show (description only, nothing guessed: conflicts, generic names, "
            "missing descriptions and authors set aside), the first candidate of each drawn rule (a wrong value "
            "misfiles the same books whichever it is) and the longest name limit of the tier (best on average). It "
            "cannot know the six reason codes, so it writes no review rows and lists the books it cannot file as "
            "skipped.", ""]
    rows = []
    for tier in tier_order(audit["voi"]):
        v = audit["voi"][tier]
        rows.append([tier, _num(v["never_asks_params"]), _num(v["voi_params"]), _num(v["never_asks"]),
                     _num(v["voi"])])
    out += _table(["tier", "never asks, knows the fixed facts", "value of the parameters", "never asks (robust)",
                   "value of asking"], rows)

    # 5. diagnostics
    out += ["", "## 5. Diagnostic cases", "",
            "`score()` reports `enforced[target]` and a line of evidence for every target in force, for valid and "
            "invalid programs alike, from the same run of the program on the hidden drive as the score (the "
            "program is run once). The diagnostic inputs are the hidden books where only that fact decides the "
            "output. For a drawn library rule the program's own path of each such book is read back under every "
            "layout, year basis, script, co-author rule, separator and cut (`_path_readings`; also with a dot or no "
            "separator, and with the co-authors joined by \"and\" or a comma or the last author alone, which no "
            "pool has, so that a program writing them is read as misreading that rule rather than giving no "
            "reading at all): the book counts for "
            "the fact when the client's value is among the readings that reproduce the path and not every candidate "
            "of the tier is, and against it when the client's value is not among them; a path that does not even "
            "have the client's layout's shape (e.g. `library/<title>.txt`) counts against `layout`. `content` counts "
            "a file at a book's path against the fact when it holds the description and more (a card, a title page) "
            "or no description at all (a placeholder); `missing_author` counts an author-less book that is neither "
            "shelved nor in review (left out, or listed as skipped) against it; `review_codes` counts every review "
            "row the program writes, and no review row at all against the fact where books the tier scores belong "
            "in review (hard: the six codes were never used; in easy and medium no scored book belongs in review, "
            "so the answer key itself has no review row). For the other facts the inputs are the books (or review "
            "rows) the fact is about. A stray library file that holds one book's whole description with more "
            "around it (a card at a path no rule gives) is no book's file for the score, but the diagnostic reads "
            "it as that book's, so a program that misreads the content and a library rule is flagged on both, and "
            "a book filed as a card under a guessed year or title counts as placed. `enforced` is True when no "
            "input counts against the fact and at least one counts for it. The audit checks that the reference is "
            "enforced everywhere and that every ablation that bites is not.", ""]
    rows = []
    for t in targets:
        s = summary.get(t["id"])
        if s is None:
            continue
        rows.append([f"`{t['id']}`", module.DIAGNOSTIC_BOOKS[t["id"]], _diag(s), ", ".join(s["undiagnosed"][:3]) or "–"])
    out += _table(["target", "diagnostic inputs (hidden drive)", "result", "settings where it fails"], rows)
    out += ["", "**Reliability on other deliverables.** A run's \"enforced\" stage applies the diagnostic to the "
            "agent's program, which is neither the reference nor an ablation. Per target, the settings where it "
            "calls a deliverable not enforced, of those where it gives a verdict: the best known solution (valid "
            "and built with every fact of its setting, so each False would be a false negative), the ablations of "
            "the target that also flag another target (of the settings where the ablation bites; it misreads only "
            "its own fact), and the baseline (each setting's own) and `robust_solution` (its tier's), which do not "
            "know every fact, so a False there may be right.", ""]
    negatives, cross = false_negatives(audit), cross_flag_summary(audit)
    profile = audit.get("diagnostic_profile") or {}

    def cell(k, n):
        return f"{k}/{n}" if n else "–"
    rows = []
    for t in targets:
        if t["id"] not in summary:
            continue
        fn, cf = negatives.get(t["id"]), cross.get(t["id"])
        flags = cell(len(cf["flagged"]), cf["biting"]) if cf else "–"
        if cf and cf["others"]:
            flags += " (" + ", ".join(f"`{u}`" for u in cf["others"]) + ")"
        rows.append([f"`{t['id']}`", cell(len(fn["false"]), fn["diagnosed"]) if fn else "–", flags]
                    + [cell(p[t["id"]]["false"], p[t["id"]]["diagnosed"]) if t["id"] in (p := profile.get(name) or {})
                       else "–" for name in ("baseline", "robust_solution")])
    out += _table(["target", "best known", "ablation flags another target", "baseline", "robust_solution"], rows)
    errors = (audit.get("diagnose_errors") or {}).get("count", 0)
    out += ["", "The case has no lazy `diagnose()` hook: the diagnostic is cheap and computed in `score()` from the "
            "program's one run, so the validator and every cell of the value-of-information matrix get it too"
            + (f"; `diagnose()` raised in {errors} evaluation(s) of the audit." if errors else ".")]
    out += ["", "## Findings of the audit", ""] + [f"- {x}" for x in audit["summary"]] + (
        [] if audit["summary"] else ["- none: every check passes"])
    return "\n".join(out) + "\n"


# ── CLIENT_REVIEW.md: what the simulated client answers from, per target ─────
# The question an engineer would naturally ask, and how to find the passage of requirements.md the client answers
# from in every locale: every token must occur in the passage (a bullet or sub-bullet with its indented lines, or a
# paragraph); a dict token gives the words per locale; "first" takes the first passage that matches, "all" every one.
QUESTIONS = {
    "layout": ("How should the library be organised: which folders, and how is each book's file named?",
               ["{{layout}}"], "first"),
    "year_basis": ("A book has a first-publication year and an edition year: which one goes into the path?",
                   ["{{year_basis}}"], "first"),
    "script": ("Should Chinese, Korean and Japanese titles and author names be written in their own script or "
               "romanized?", ["{{script}}"], "first"),
    "co_authors": ("How do I write the author part for a book with two authors?", ["{{multi_author}}"], "first"),
    "separator": ("What should the spaces in a title or an author name become in a file name?", ["{{sep}}"],
                  "first"),
    "max_len": ("Is there a length limit on the title and author parts of a path?", ["{{max_len}}"], "first"),
    "content": ("What exactly goes into a book's library file?",
                [{"en": "**description only**", "zh": "**只放这本书的简介**", "ko": "**책 소개글만**",
                  "ja": "**その本の紹介文だけ**", "es": "**solo la sinopsis**"}], "first"),
    "review_codes": ("What reason should a book I cannot file get in the manifest?", ["`UNREADABLE`", "`CONFLICT`"],
                     "first"),
    "missing_author": ("What should happen to a book that has no author in any of its files?",
                       ["{{fallback_author}}"], "all"),
    "no_description": ("What if a book has no description in any of its files?",
                       ["`NO_DESCRIPTION`", {"en": "placeholder", "zh": "占位", "ko": "자리 표시", "ja": "仮の",
                                             "es": "relleno"}], "first"),
    "conflict": ("Two files of the same book give different years: which one should I use?",
                 ["`CONFLICT`", "JSON"], "first"),
    "generic_titles": ("Some books have no title in their files: can I use the file name as the title?",
                       ["doc_0042"], "first"),
}
# What the scorer uses, as it must read in the passage, per target.
SCORER = {
    "review_codes": ["UNREADABLE", "NO_TITLE", "NO_AUTHOR", "NO_YEAR", "NO_DESCRIPTION", "CONFLICT"],
    "no_description": ["NO_DESCRIPTION"],
    "conflict": ["CONFLICT"],
    "generic_titles": ["NO_TITLE", "doc_0042", "scan_0007", "book_0031"],
}


def _passages(text: str) -> list[str]:
    """Bullets and sub-bullets (each with its indented continuation lines) and paragraphs, each with the opening
    setting markers (tier, when) that stand right before it, so the reviewer sees in which settings it is said."""
    out, cur, markers = [], [], []
    for line in text.splitlines():
        starts = line.startswith("- ") or line.startswith("  - ") or (
            line and not line.startswith(" ") and not line.startswith("<!--"))
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


def _tokens_of(text: str) -> list[str]:
    """The tokens a translation must keep, written the same way in every locale: parameters, reason codes, file
    names and numbers with a decimal or of 10 and more (es writes 0,7)."""
    t = re.sub(r"(\d),(\d)", r"\1.\2", text)
    out = set(re.findall(r"\{\{\w+\}\}", t))
    edge, end = r"(?<![0-9A-Za-z_])", r"(?![0-9A-Za-z_])"        # ASCII edges: ko and ja attach particles
    out |= set(re.findall(edge + r"(?:UNREADABLE|NO_TITLE|NO_AUTHOR|NO_YEAR|NO_DESCRIPTION|CONFLICT|JSON|ONIX)" + end,
                          t))
    out |= set(re.findall(edge + r"(?:doc|scan|book)_\d{4}" + end, t))
    out |= {n for n in re.findall(r"(?<![0-9A-Za-z_.])\d+(?:\.\d+)?" + end, t) if "." in n or float(n) >= 10}
    return sorted(out)


def client_review() -> str:
    texts = {lang: (ROOT / "locales" / lang / "requirements.md").read_text(encoding="utf-8") for lang in LANGS}
    targets = yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))

    def find(lang, spec, which):
        toks = [t[lang] if isinstance(t, dict) else t for t in spec]
        hits = [p for p in _passages(texts[lang]) if all(t in p for t in toks)]
        return hits[:1] if which == "first" else hits

    out = ["# Client answers: human review", "",
           "The simulated client answers only from `locales/<lang>/requirements.md` (plus event facts; this case has "
           "none). For every target: the question an engineer would naturally ask, the passage each locale answers "
           "from (quoted as written, with setting markers and parameters; a parameter is worded per locale by "
           "`params.<name>.labels` in case.yaml), a machine pre-check and an empty verdict for a human reviewer. "
           "Generated by `gt_report.py`.", "",
           "Pre-check: (1) the passage is found in all five locales; (2) the same parameters, reason codes, file "
           "names and numbers in every locale (decimal commas normalized); (3) the values the scorer uses appear in "
           "every locale; (4) the other targets whose passage is the same one, i.e. what the passage would answer "
           "beyond the question (the client may state them together when asked).", "",
           "**Status: awaiting human review.** No passage below has been reviewed by a person yet.", ""]
    by_target = {t["id"]: {lang: find(lang, *QUESTIONS[t["id"]][1:]) for lang in LANGS} for t in targets}
    for t in targets:
        tid = t["id"]
        q = QUESTIONS[tid][0]
        found = by_target[tid]
        out += [f"## `{tid}`" + (f" ({', '.join(t['tiers'])})" if t.get("tiers") else ""), "",
                f"**Question.** {q}", "", f"**Target (en).** {t['text']}", ""]
        for lang in LANGS:
            out += [f"**{lang}:**", ""]
            for p in found[lang] or ["(not found)"]:
                out += ["> " + line for line in p.splitlines()] + [">"]
            if out[-1] == ">":
                out.pop()
            out.append("")
        checks = []
        missing = [lang for lang in LANGS if not found[lang]]
        checks.append("passage found in every locale" if not missing else f"NOT FOUND in {', '.join(missing)}")
        toks = {lang: _tokens_of("\n".join(found[lang])) for lang in LANGS if found[lang]}
        ref = toks.get("en", [])
        diff = {lang: (sorted(set(ref) - set(n)), sorted(set(n) - set(ref))) for lang, n in toks.items()
                if set(n) != set(ref)}
        checks.append("tokens differ from en: " + "; ".join(f"{lang} lacks {a or '–'}, adds {b or '–'}"
                                                             for lang, (a, b) in diff.items()) if diff else
                      "same parameters, codes, names and numbers in all five locales: " + (", ".join(ref) or "none"))
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
    if "client" in which:
        (ROOT / "CLIENT_REVIEW.md").write_text(client_review(), encoding="utf-8")
        print("wrote", ROOT / "CLIENT_REVIEW.md")
    if "gt" in which:
        (ROOT / "GT.md").write_text(gt(NativeCase(ROOT)), encoding="utf-8")
        print("wrote", ROOT / "GT.md")
