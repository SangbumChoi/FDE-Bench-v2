"""Writes CLIENT_REVIEW.md: for every target, the question an engineer would ask, the passage of requirements.md
each of the five locales answers from (the locales' requirements are translated line by line), and a machine
pre-check of those passages. The verdicts are left for a human reviewer:
python cases/retail/grocery_demand_forecaster/make_client_review.py
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))
LOCALES = ("en", "zh", "ko", "ja", "es")

# target -> (the question, the en lines it is answered from, each found by a piece of its text)
ASK = {
    "order_quantity": ("What do the stores do with these numbers: do they order them as they are, or add a margin?",
                       ["**What the numbers are for.**"]),
    "lost_sale_cost": ("What does it cost you when a store runs out, compared with a unit left over?",
                       ["**What a wrong number costs us.**"]),
    "stockout_censoring": ("What does stockout = yes mean for that day's units_sold, and should I forecast sales or "
                           "demand?", ["- The order has to cover customer demand"]),
    "base_forecast": ("Do the promotions in promo_plan.csv belong in the numbers?",
                      ["**This round** we need the order without the promotions",
                       "The promotions in `promo_plan.csv` are added by the category team this round"]),
    "promo_plan": ("Do the promotions in promo_plan.csv belong in the numbers?",
                   ["nobody adds them afterwards. Bread rolls (I07) are not judged",
                    "nobody adds them afterwards. Bread rolls (I07) are part of it",
                    "The promotions for the forecast period are in `promo_plan.csv`"]),
    "promo_flyer": ("Will the November promotions work like the ones in the history?",
                    ["- The November promotions run like the past ones",
                     "- The November promotions are also in our printed flyer"]),
    "promo_revision": ("Is promo_plan.csv still current?", ["- On Friday 30 October"]),
    "one_off_holiday": ("Are there holidays or special days in the two weeks that holidays.csv does not list?",
                        ["is a one-off regional public holiday"]),
    "min_display": ("Is there a minimum quantity for any product?", ["- Our habit: we never order fewer than"]),
    "manager_note": ("Should I do what the Central Plaza manager's e-mail asks?",
                     ["- The e-mail in `mail/` is from the manager"]),
    "submission_format": ("What does the file have to contain: a row for every store, product and day, also the days "
                          "a store is closed?", ["One CSV file, `forecast.csv`"]),
}
NUMBER = re.compile(r"\d(?:[\d.,  ]*\d)?")
PERCENT = re.compile(r"(?<![\d.,])(\d)\s?%")
TOKEN = re.compile(r"`([^`]+)`|\{\{\s*(\w+)\s*\}\}")
CODE = re.compile(r"(?<![A-Za-z0-9])([SI]\d{1,2})(?![0-9])")
MONTHS = {"en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                 "November", "December"],
          "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                 "noviembre", "diciembre"]}
DATES = {
    "en": re.compile(r"(\d{1,2}) (" + "|".join(MONTHS["en"]) + r")(?: (\d{4}))?"),
    "es": re.compile(r"(\d{1,2}) de (" + "|".join(MONTHS["es"]) + r")(?: de (\d{4}))?"),
    "zh": re.compile(r"(?:(\d{4}) ?年 ?)?(\d{1,2}) ?月 ?(\d{1,2}) ?日"),
    "ko": re.compile(r"(?:(\d{4})년 ?)?(\d{1,2})월 ?(\d{1,2})일"),
    "ja": re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日"),
}
ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
MONTH = {"en": re.compile(r"\b(?:" + "|".join(MONTHS["en"]) + r")\b"),
         "es": re.compile(r"\b(?:" + "|".join(MONTHS["es"]) + r")\b"),
         "zh": re.compile(r"(\d{1,2}) ?月"), "ko": re.compile(r"(\d{1,2})월"), "ja": re.compile(r"(\d{1,2})月")}


def dates(text: str, lang: str) -> tuple[list[str], str]:
    """(the dates a passage states as [YYYY-]MM-DD and the months it names as MM, the passage without them):
    30 October, 10 月 30 日, 10월 30일, 10月30日 and 30 de octubre are one date, November and 11 月 one month, and
    their digits are not numbers of the passage."""
    found = set(ISO.findall(text))
    text = ISO.sub(" ", text)
    for m in DATES[lang].finditer(text):
        if lang in MONTHS:
            day, month, year = int(m.group(1)), MONTHS[lang].index(m.group(2)) + 1, m.group(3)
        else:
            year, month, day = m.group(1), int(m.group(2)), int(m.group(3))
        found.add((f"{year}-" if year else "") + f"{month:02d}-{day:02d}")
    text = DATES[lang].sub(" ", text)
    for m in MONTH[lang].finditer(text):
        found.add(f"{MONTHS[lang].index(m.group(0)) + 1:02d}" if lang in MONTHS else f"{int(m.group(1)):02d}")
    return sorted(found), MONTH[lang].sub(" ", text)


def numbers(text: str) -> list[str]:
    """The numbers of two digits or more in a passage, and the single digits written as a percentage, as a set,
    separators dropped (1,000 = 1.000 = 1000), placeholders, codes and dates left out. Other single digits are
    left out: one language writes "four weeks" or "five stores" in words where another writes 4주 or 5 家."""
    text = CODE.sub(" ", re.sub(r"\{\{\s*\w+\s*\}\}", " ", text))
    out = {n for n in (re.sub(r"[.,  ]", "", m) for m in NUMBER.findall(text)) if len(n) > 1}
    return sorted(out | {m + "%" for m in PERCENT.findall(text)})


def labels() -> dict[str, dict[str, str]]:
    """{locale: {localized data name: English name}} for the file names, column headers and values of the data,
    longest first, so that `缺货 = 是` reads as `stockout = yes`."""
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
    """The identifiers of a passage (`code spans` and {{placeholders}}), data names put back into English."""
    found = set()
    for m in TOKEN.findall(text):
        token = m[0] or "{{" + m[1] + "}}"
        for own, english in table.items():
            token = token.replace(own, english)
        found.add(token)
    return sorted(found)


def scorer_numbers() -> set[str]:
    """Numbers the scorer knows: case.py's constants and every parameter candidate, as numbers() writes them."""
    from fdebench2.cases import NativeCase
    mod = NativeCase(ROOT).module
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    grid = len(mod.STORES) * len(mod.ITEMS) * mod.HORIZON_DAYS
    vals = [grid, mod.PACK, round(mod.NOTE_EXTRA * 100), *mod.HABIT_CUSHION.values()]
    vals += [v for p in meta["params"].values() for v in (p["values"] if isinstance(p["values"], list)
                                                         else sum(p["values"].values(), []))]
    out = {f"{v:g}" if isinstance(v, float) else str(v) for v in vals}
    return out | {f"{round(mod.HABIT_PROMO * 100)}%", f"{round(mod.NOTE_EXTRA * 100)}%"}


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
    out = ["# Client answers review — retail/grocery_demand_forecaster", "",
           "**Status: awaiting human review.** No human has reviewed these entries yet.", "",
           "The simulated client answers only from `locales/<lang>/requirements.md` (plus event facts). For every "
           "target: the question an engineer would naturally ask, the passage each locale answers from (the five "
           "requirements are translated line by line, so the same lines; `{{…}}` is the rule seed's value, filled in "
           "per setting; a target with several lines has one per tier or per value), and a machine pre-check: the "
           "same numbers, dates, store and item codes and identifiers in every locale (file names, column headers "
           "and values of the data are compared in English), no number the scorer does not know, and which other "
           "targets the same passage also states (a client quoting it whole would answer more than was asked). "
           "Generated by `make_client_review.py`.", ""]
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
        when, rest = {}, {}
        for lang in LOCALES:
            when[lang], rest[lang] = dates(" ".join(passages[lang]), lang)
        nums = {lang: numbers(rest[lang]) for lang in LOCALES}
        codes = {lang: sorted(set(CODE.findall(" ".join(passages[lang])))) for lang in LOCALES}
        ids = {lang: tokens(" ".join(passages[lang]), names[lang]) for lang in LOCALES}

        def same(found: dict, what: str) -> str:
            off = [lang for lang in LOCALES if found[lang] != found["en"]]
            return (f"- {what} ({', '.join(found['en']) or 'none'}): "
                    + ("the same in every locale" if not off else f"DIFFER in {', '.join(off)}"))
        unknown = sorted({n for n in nums["en"] if n not in known})
        also = sorted({o for o, ls in lines_of.items() if o != tid and set(ls) & set(lines)})
        out += ["", "Machine pre-check:",
                same(nums, "numbers of two digits or more, and percentages"),
                same(when, "dates"),
                same(codes, "store and item codes"),
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
