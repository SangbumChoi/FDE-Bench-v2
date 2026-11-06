"""The leaderboard page of the site: every submission in leaderboard/*.json (fdebench2 submit) as one table.

Ranked submissions (private rule seeds, enough trials) come first, ordered by their mean final score; development
submissions follow, unranked; the anchors (a file of `kind: anchors`: the cases' literal solution, baseline and
reference) close the table as reference rows. The page is written in every language with the same table and
localized headings (prompts/explainer.yaml, keys lb_*); build-site places it at leaderboard.html and
<lang>/leaderboard.html.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .explain import LANG_NAMES, LANGS, UI, _esc, _shell, _t
from .submit import load_submission

FOLDER = "leaderboard"          # in the repository: leaderboard/<name>.json
PAGE = "leaderboard.html"       # on the site
BADGE_CSS = ("<style>.badge{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.04em;padding:1px 6px;"
             "border-radius:4px;border:1px solid var(--line);color:var(--muted);margin-left:6px}"
             "tr.group td{font-weight:700;background:var(--code)}td.num{text-align:right;white-space:nowrap}</style>")


def load_submissions(folder: Path) -> list[tuple[str, dict[str, Any]]]:
    """(file name, submission) for every leaderboard/*.json that reads as a submission; one that does not is
    reported on stderr and left out."""
    found = []
    for path in sorted(Path(folder).glob("*.json")):
        try:
            found.append((path.name, load_submission(path)))
        except (ValueError, OSError) as e:
            print(f"leaderboard: skipped {path.name}: {e}", file=sys.stderr)
    return found


def _mean(agg: dict[str, Any], key: str) -> float | None:
    return ((agg or {}).get(key) or {}).get("mean")


def _num(x: float | None, digits: int = 3) -> str:
    return "–" if x is None else f"{x:.{digits}f}"


def _final(agg: dict[str, Any]) -> str:
    m = _mean(agg, "final")
    if m is None:
        return "–"
    lo, hi = agg["final"].get("ci") or (None, None)
    return f"{m:.3f}" + (f" [{lo:.2f}–{hi:.2f}]" if lo is not None and hi is not None else "")


def _cost(agg: dict[str, Any]) -> str:
    m = _mean(agg, "cost_usd")
    return "–" if m is None else f"${m:.2f}" if m >= 0.1 else f"${m:.4f}"


def ordered(subs: list[tuple[str, dict[str, Any]]]) -> list[tuple[str | None, str, dict[str, Any]]]:
    """(rank or None, file, submission) for the systems: ranked by mean final, then development; anchors left out."""
    systems = [(f, s) for f, s in subs if s.get("kind") != "anchors"]
    key = lambda fs: -(_mean(fs[1]["aggregate"], "final") or 0.0)  # noqa: E731
    ranked = sorted((fs for fs in systems if fs[1].get("status") == "ranked"), key=key)
    rest = sorted((fs for fs in systems if fs[1].get("status") != "ranked"), key=key)
    return [(str(i), f, s) for i, (f, s) in enumerate(ranked, 1)] + [(None, f, s) for f, s in rest]


def _row(rank: str | None, system: str, model: str, harness: str, agg: dict[str, Any],
         status: str) -> str:
    cells = [_esc(rank or "–"), system, model, harness, _final(agg), _num(_mean(agg, "validity"), 2),
             _num(_mean(agg, "quality")), _num(_mean(agg, "ask_f1"), 2), _num(_mean(agg, "enforced_share"), 2),
             _cost(agg), status]
    num = {0, 4, 5, 6, 7, 8, 9}
    return "<tr>" + "".join(f'<td class="num">{c}</td>' if i in num else f"<td>{c}</td>"
                            for i, c in enumerate(cells)) + "</tr>"


def build_page(lang: str, subs: list[tuple[str, dict[str, Any]]]) -> str:
    """The leaderboard page in `lang`, with links written as from the repository's leaderboard/ folder (build-site
    rewrites them for the site)."""
    t = lambda key, **kw: _t(lang, key, **kw)  # noqa: E731
    badge = f'<span class="badge">{t("lb_example")}</span>'
    status_word = {"ranked": t("lb_ranked"), "development": t("lb_development"), "anchor": t("lb_anchor")}
    head = [t(k) for k in ("lb_rank", "lb_system", "lb_model", "lb_harness", "lb_final", "lb_validity", "lb_quality",
                           "lb_ask_f1", "lb_enforced", "lb_cost", "lb_status")]
    rows = []
    for rank, file, s in ordered(subs):
        sysinfo, agg = s.get("system") or {}, s["aggregate"]
        name = (f'<a href="{_esc(file)}">{_esc(sysinfo.get("name"))}</a>' + (badge if s.get("example") else "")
                + f'<br><span class="muted">{t("lb_cases", n=agg.get("n_cases", 0), runs=agg.get("n_scored", 0))}'
                + (f" · v{_esc(sysinfo['version'])}" if sysinfo.get("version") else "") + "</span>")
        rows.append(_row(rank, name, _esc(sysinfo.get("model") or "–"), _esc(sysinfo.get("harness") or "–"),
                         agg, status_word.get(s.get("status"), _esc(s.get("status", "")))))
    if not rows:
        rows.append(f'<tr><td colspan="{len(head)}" class="muted">{t("lb_none")}</td></tr>')
    anchors = [(f, s) for f, s in subs if s.get("kind") == "anchors"]
    if anchors:
        rows.append(f'<tr class="group"><td colspan="{len(head)}">{t("lb_anchor_rows")}</td></tr>')
        for file, s in anchors:
            for name, agg in s["anchors"].items():
                label = (f'<a href="{_esc(file)}">{_esc(UI[lang].get(f"try_{name}", name))}</a>'
                         + (badge if s.get("example") else "")
                         + f'<br><span class="muted">{t("lb_cases", n=agg.get("n_cases", 0), runs=agg.get("n_scored", 0))}</span>')
                rows.append(_row(None, label, "–", "–", agg, status_word["anchor"]))
    current = ' aria-current="page"'
    switcher = "".join(f'<a href="{l}.html" data-lang="{l}" hreflang="{l}"{current if l == lang else ""}>'
                       f"{LANG_NAMES[l]}</a>" for l in LANGS)
    link = '<a href="../docs/SUBMITTING.md">docs/SUBMITTING.md</a>'
    table = (f'<div class="scroll"><table><thead><tr>{"".join(f"<th>{h}</th>" for h in head)}</tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>')
    body = (f'<header><nav class="langs" aria-label="{t("language")}">{switcher}</nav>'
            f'<p class="eyebrow">FDE-Bench v2</p><h1>{t("lb_title")}</h1>'
            f'<p class="muted">{t("lb_intro")}</p>'
            f'<p>{t("lb_how", link=link)}</p>'
            f"</header><section>{table}</section>")
    html = _shell(f"FDE-Bench v2 — {UI[lang]['lb_title']}", body, script=False, lang=lang)
    return html.replace("</head>", BADGE_CSS + "</head>", 1)
