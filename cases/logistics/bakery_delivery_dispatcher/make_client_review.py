"""Writes CLIENT_REVIEW.md: for every target, the question an engineer would ask, the passage of requirements.md each
of the five locales answers from (the locales' requirements are translated line by line), and a machine pre-check of
those passages. The verdicts are left for a human reviewer:
python cases/logistics/bakery_delivery_dispatcher/make_client_review.py
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
    "road_distance": ("How do I turn the coordinates into driving distances?", ["Road distance is 1.3 times"]),
    "speed": ("How fast do the vans drive on Monday morning?", ["- Driving speed: count 25 km/h"]),
    "rush_hour": ("How fast do the vans drive on Monday morning? Is there a rush hour?",
                  ["- Driving speed depends on the time"]),
    "rush_start": ("When does the morning rush start?", ["- Driving speed depends on the time"]),
    "service_time": ("How long does a stop at a café take?", ["- Unloading at a café takes"]),
    "shift_end": ("When do the vans have to be back?", ["must be back at the kitchen by {{shift_end}}"]),
    "tray_limit": ("How many trays fit in a van this week? Is max_trays the limit?",
                   ["this week we deliver in the new, deeper crates"]),
    "closed_cafe": ("Is every café on the list open on Monday?", ["is closed this week for renovation"]),
    "cold_chain": ("What does partner_brand mean for which van may serve a café?",
                   ["Only the refrigerated van (V4) may serve them"]),
    "partner_this_week": ("What does partner_brand mean for which van may serve a café?",
                          ["this week the partner brings its chilled range itself"]),
    "premium_first": ("Does the order of the cafés on a route matter, for example premium before standard?",
                      ["- Our habit: on every route", "- Our habit of serving premium cafés first is suspended"]),
    "lateness": ("Is deliver_by a hard deadline, or what does a late delivery cost you?",
                 ["- A late delivery is accepted but not free"]),
    "workshop": ("Are all four vans available from 05:00 on Monday?", ["- Monday only: V2 is in the workshop"]),
    "manager_pressure": ("The East Lake café's manager wants to be first: do I have to plan around that?",
                         ["- The manager of the East Lake café (C07)"]),
}
NUMBER = re.compile(r"\d(?:[\d.,]*\d)?")
TOKEN = re.compile(r"`([^`]+)`|\{\{\s*(\w+)\s*\}\}")
CODE = re.compile(r"(?<![A-Za-z0-9])([CV]\d{1,2})(?![0-9])")
TIME = re.compile(r"(?<!\d)\d{2}:\d{2}(?!\d)")


def numbers(text: str) -> list[str]:
    """The numbers of two characters or more in a passage (decimal commas read as points), times, codes and
    placeholders left out. Single digits are left out: one language writes "one van" in words where another writes
    1台 or 1개."""
    text = TIME.sub(" ", CODE.sub(" ", re.sub(r"\{\{\s*\w+\s*\}\}", " ", text)))
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    return sorted({n for n in NUMBER.findall(text) if len(n) > 1})


def labels() -> dict[str, dict[str, str]]:
    """{locale: {localized data name: English name}} for the file names, column headers and values of the data."""
    from fdebench2.cases import NativeCase
    mod = NativeCase(ROOT).module
    out = {}
    for lang in LOCALES:
        table = {}
        for group in (mod.FILES, mod.COLS, mod.VALUES):
            for names in group.values():
                table[names[lang]] = names["en"]
        out[lang] = dict(sorted(table.items(), key=lambda kv: -len(kv[0])))
    return out


def tokens(text: str, table: dict[str, str]) -> list[str]:
    found = set()
    for m in TOKEN.findall(text):
        token = m[0] or "{{" + m[1] + "}}"
        for own, english in table.items():
            token = token.replace(own, english)
        found.add(token)
    return sorted(found)


def scorer_numbers() -> set[str]:
    """Numbers the scorer knows: case.py's constants and every parameter candidate."""
    from fdebench2.cases import NativeCase
    mod = NativeCase(ROOT).module
    tr = mod.TRAVEL
    vals = [tr.road, tr.average, tr.fast, tr.slow, tr.stop, tr.per_tray, mod.CAPACITY, mod.LATE_COST,
            len(mod.TIERS) + 1, 0, 1]
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    for p in meta["params"].values():
        pool = p["values"] if isinstance(p["values"], list) else sum(p["values"].values(), [])
        vals += [v for v in pool if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return {f"{float(v):g}" for v in vals}


def main() -> None:
    req = {lang: (ROOT / "locales" / lang / "requirements.md").read_text(encoding="utf-8").split("\n")
           for lang in LOCALES}
    assert len({len(v) for v in req.values()}) == 1, "the locales' requirements are no longer line by line"
    targets = yaml.safe_load((ROOT / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))
    known, names = scorer_numbers(), labels()
    lines_of = {}
    for t in targets:
        found = []
        for piece in ASK[t["id"]][1]:
            hits = [k for k, line in enumerate(req["en"]) if piece in line]
            assert len(hits) == 1, (t["id"], piece, hits)
            found.append(hits[0])
        lines_of[t["id"]] = found
    out = ["# Client answers review — logistics/bakery_delivery_dispatcher", "",
           "**Status: awaiting human review.** No human has reviewed these entries yet.", "",
           "The simulated client answers only from `locales/<lang>/requirements.md`. For every target: the question an "
           "engineer would naturally ask, the passage each locale answers from (the five requirements are translated "
           "line by line, so the same lines; `{{…}}` is the rule seed's value, filled in per setting; a target with "
           "several lines has one per value), and a machine pre-check: the same numbers, times, café and van codes and "
           "identifiers in every locale (file names, column headers and values of the data are compared in English), "
           "no number the scorer does not know, and which other targets the same passage also states (a client "
           "quoting it whole would answer more than was asked). Generated by `make_client_review.py`.", ""]
    for t in targets:
        tid = t["id"]
        q, _ = ASK[tid]
        lines = lines_of[tid]
        out += [f"## `{tid}`", "", f"In force: {', '.join(t.get('tiers', ['easy', 'medium', 'hard']))}"
                + (f" (when {t['when']})" if t.get("when") else "") + f". Target: {t['text']}", "",
                f"**Question:** {q}", ""]
        passages = {lang: [req[lang][k] for k in lines] for lang in LOCALES}
        for lang in LOCALES:
            out.append(f"- {lang} (line{'s' if len(lines) > 1 else ''} {', '.join(str(k + 1) for k in lines)}):")
            out += [f"  > {line}" for line in passages[lang]]
        joined = {lang: " ".join(passages[lang]) for lang in LOCALES}
        nums = {lang: numbers(joined[lang]) for lang in LOCALES}
        times = {lang: sorted(set(TIME.findall(joined[lang]))) for lang in LOCALES}
        codes = {lang: sorted(set(CODE.findall(joined[lang]))) for lang in LOCALES}
        ids = {lang: tokens(joined[lang], names[lang]) for lang in LOCALES}

        def same(found: dict, what: str) -> str:
            off = [lang for lang in LOCALES if found[lang] != found["en"]]
            return (f"- {what} ({', '.join(found['en']) or 'none'}): "
                    + ("the same in every locale" if not off else f"DIFFER in {', '.join(off)}"))
        unknown = sorted({n for n in nums["en"] if f"{float(n):g}" not in known})
        also = sorted({o for o, ls in lines_of.items() if o != tid and set(ls) & set(lines)})
        out += ["", "Machine pre-check:",
                same(nums, "numbers"),
                same(times, "times"),
                same(codes, "café and van codes"),
                same(ids, "identifiers"),
                "- against the scorer: " + ("every number is one case.py or case.yaml uses" if not unknown else
                                            f"numbers the scorer does not use: {', '.join(unknown)}"),
                "- answers more than asked: " + ("no other target in these lines" if not also else
                                                 "the same lines also state " + ", ".join(f"`{o}`" for o in also)),
                "", "Reviewer verdict:", ""]
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "CLIENT_REVIEW.md"
    dest.write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
