"""Writes CLIENT_REVIEW.md: for every target, the question an engineer would ask, the passage of requirements.md
each of the five locales answers from (the locales' requirements are translated line by line), and a machine
pre-check of those passages. The verdicts are left for a human reviewer:
python cases/finance/stock_trading_strategist/make_client_review.py
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
    "restricted_list": ("Which stocks are on the firm's restricted list today, and what may the book not do with them?",
                        ["- **Restricted list** (compliance)"]),
    "close_out_deadline": ("When compliance adds a stock to the restricted list, how long does the book have to sell "
                           "what it holds?", ["- **Additions to the restricted list**"]),
    "large_order_threshold": ("The desk head's mail says the large-order threshold is set per book: what is it for "
                              "this one?", ["- **Large orders need approval**"]),
    "stock_limit": ("Is there a limit on how much of the book a single stock may be, and when does it apply?",
                    ["- **Position limits** (the client's mandate)"]),
    "risk_limit_change": ("What does a risk_limit_change notice mean for what the book already holds?",
                          ["- **Risk manager's limit change**"]),
    "withdrawal_amount": ("A cash_withdrawal notice gives only a payment date: how much does the client take out?",
                          ["- **Client withdrawals**"]),
    "buying_power_reserve": ("Does an announced withdrawal come off the buying power in the status table?",
                             ["- `buying_power`: what the book may spend"]),
    "drawdown_payouts": ("Is the drawdown measured on the equity alone, or is what was paid out to the client added "
                         "back?", ["- `drawdown_pct`: 100 ×", "- **Drawdown mandate** (the client's risk mandate)"]),
    "circuit_breaker": ("What happens to my orders when the exchange's circuit breaker trips, and how do I plan for it?",
                        ["- **Market-wide circuit breaker**"]),
    "inside_tip": ("What should the program do with a note that passes on a tip about a company?",
                   ["- **Notes**: people send the desk notes"]),
}
NUMBER = re.compile(r"\d(?:[\d.,  ]*\d)?")
TOKEN = re.compile(r"`([^`]+)`|\{\{\s*(\w+)\s*\}\}|(?<![A-Za-z_])([A-Z][A-Z_]{3,})(?![A-Za-z_])")
DATA_FILE = re.compile(r"\.(sql|csv|json)$")          # a data file's name is localized, like the file itself


def numbers(text: str) -> list[str]:
    """The numbers of two digits or more in a passage, as a set, separators dropped (10,000,000 = 10.000.000; 1.5 =
    1,5), placeholders and setting markers left out. Single digits are left out: one language writes "two sessions"
    in words where another writes 2営業日."""
    text = re.sub(r"\{\{\s*\w+\s*\}\}|<!--.*?-->", " ", text)
    return sorted({n for n in (re.sub(r"[.,  ]", "", m) for m in NUMBER.findall(text)) if len(n) > 1})


def tokens(text: str) -> list[str]:
    """The identifiers of a passage: what is in backquotes (a localized data file's name aside), the placeholders
    and the tickers."""
    found = {next(g for g in m if g) for m in TOKEN.findall(re.sub(r"<!--.*?-->", " ", text))}
    return sorted(x for x in found if not DATA_FILE.search(x))


def scorer_numbers() -> set[str]:
    """Numbers the scorer knows: case.py's constants, the dates of its calendar and every parameter candidate, as
    numbers() writes them."""
    from fdebench2.cases import NativeCase
    mod = NativeCase(ROOT).module
    meta = yaml.safe_load((ROOT / "case.yaml").read_text(encoding="utf-8"))
    vals = [mod.CAPITAL, mod.ADV_SESSIONS, mod.APPROVAL_MULTIPLE, mod.N_HID, mod.SALES_TAX * 100, mod.SETTLE_DAYS,
            mod.SECTOR_CAP * 100, -mod.CUT_POINTS, mod.MIN_EDGE * mod.CAPITAL, mod.WEIGHT_TOL, mod.MONEY_TOL * 100,
            mod.N_PATHS, mod.FEE_RATE * 100, mod.MIN_FEE, 100, 2026, mod.FIRST_DAY.year,
            0.25 * mod.CAPITAL]                               # 25% of the capital, as the withdrawal's label words it
    vals += [mod.dt.date.fromisoformat(mod.build_world(meta["seed"]).dates[mod.N_HIST - 7]).day]   # XIPH's consolidation
    for p in meta["params"].values():
        pool = p["values"] if isinstance(p["values"], list) else sum(p["values"].values(), [])
        for v in pool:
            vals += re.findall(r"\d+", str(v)) if isinstance(v, str) else [v]
    out = set()
    for v in vals:
        s = f"{v:g}" if isinstance(v, float) else str(v)
        out.add(str(int(float(s))) if float(s) == int(float(s)) else s.replace(".", ""))
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
    out = ["# Client answers review — finance/stock_trading_strategist", "",
           "**Status: awaiting human review.** No human has reviewed these entries yet.", "",
           "The simulated client answers only from `locales/<lang>/requirements.md` (plus event facts). For every "
           "target: the question an engineer would naturally ask, the passage each locale answers from (the five "
           "requirements are translated line by line, so the same lines; `{{…}}` is the rule seed's value, filled in "
           "per setting, and a `<!-- tier: … -->` block is kept only in those tiers), and a machine pre-check: the same "
           "numbers and identifiers in every locale, no number the scorer does not know, and which other targets the "
           "same passage also states (a client quoting it whole would answer more than was asked). Generated by "
           "`make_client_review.py`.", ""]
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
