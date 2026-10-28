"""One self-contained explainer page per case: cases/<field>/<role>/explainer.html.

The page gathers everything a reviewer needs to understand a case without
running it: the request, the hidden requirements in every setting and locale,
the rules and their classes, the rule sets, the clarification targets, the
case README, the stored dataset, the reference scores and the findings of a
review (REVIEW.md, when the case has one). It is generated from the case files
(`fdebench2 explain-case`, also run by `export-dataset`), works offline, and
validate-case checks that it is up to date.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import yaml

from .cases import LOCALES, NativeCase
from .dataset import DATASET_DIR

PAGE = "explainer.html"
LANG_NAMES = {"en": "English", "ko": "한국어", "zh": "中文", "ja": "日本語", "es": "Español"}
CLASS_NOTE = {"physical": "never bends", "contractual": "bends only if the policy allows contractual exceptions",
              "business_policy": "may bend through the policy's exception process"}

# ── a small Markdown renderer (headings, lists, tables, code, emphasis) ─────────

def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', out)
    return out


def markdown(text: str) -> str:
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + html.escape("\n".join(lines[i + 1:j])) + "</pre>")
            i = j + 1
            continue
        m = re.match(r"(#{1,6})\s+(.*)", line)
        if m:
            level = min(len(m.group(1)) + 2, 6)
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|?\s*$", lines[i + 1]):
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            rows, j = [], i + 2
            while j < len(lines) and lines[j].startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            out.append(_table(head, rows, raw=False))
            i = j
            continue
        if re.match(r"\s*([-*]|\d+\.)\s+", line):
            ordered = bool(re.match(r"\s*\d+\.", line))
            items, j = [], i
            while j < len(lines) and (re.match(r"\s*([-*]|\d+\.)\s+", lines[j])
                                      or (lines[j].startswith("  ") and lines[j].strip())):
                if re.match(r"\s*([-*]|\d+\.)\s+", lines[j]):
                    items.append(re.sub(r"\s*([-*]|\d+\.)\s+", "", lines[j], count=1))
                else:
                    items[-1] += " " + lines[j].strip()
                j += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            i = j
            continue
        if not line.strip():
            i += 1
            continue
        para, j = [line.strip()], i + 1
        while j < len(lines) and lines[j].strip() and not re.match(r"(#{1,6}\s|```|\||\s*([-*]|\d+\.)\s)", lines[j]):
            para.append(lines[j].strip())
            j += 1
        out.append("<p>" + _inline(" ".join(para)) + "</p>")
        i = j
    return "\n".join(out)


def _table(head: list[str], rows: list[list[str]], raw: bool = True) -> str:
    cell = (lambda s: s) if raw else _inline
    h = "".join(f"<th>{cell(c)}</th>" for c in head)
    body = "".join("<tr>" + "".join(f"<td>{cell(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="scroll"><table><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table></div>'


def _esc(x) -> str:
    return html.escape(str(x), quote=True)


# ── the page ─────────────────────────────────────────────────────────────────

def _tree(root: Path, limit: int = 60) -> str:
    """A compact listing of a folder: files with sizes, folders summarized past `limit` entries."""
    if not root.is_dir():
        return "<p class='muted'>(none)</p>"
    rows = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rows.append((p.relative_to(root).as_posix(), p.stat().st_size))
    shown = rows[:limit]
    lines = [f"{_esc(name)}  <span class='muted'>{size:,} B</span>" for name, size in shown]
    if len(rows) > limit:
        lines.append(f"<span class='muted'>… and {len(rows) - limit} more files</span>")
    total = sum(s for _, s in rows)
    return (f"<p class='muted'>{len(rows)} files, {total:,} bytes</p>"
            f"<pre class='tree'>{chr(10).join(lines)}</pre>")


def build_page(case_root: Path) -> str:
    case = NativeCase(Path(case_root))
    meta = case.meta
    root = case.root
    review = root / "REVIEW.md"
    settings = case.settings()
    has_settings = bool(case.tiers)
    labels = meta.get("param_labels") or {}

    def param_text(name, value, lang="en"):
        return labels[name][value][lang] if name in labels else value

    parts: list[str] = []

    # header
    kind = meta.get("deliverable_type", "batch")
    deliverable = (f"Program <code>{_esc(meta.get('entrypoint', ''))}</code>" if kind == "program"
                   else "Batch files: " + ", ".join(f"<code>{_esc(d)}</code>" for d in meta.get("deliverables", [])))
    parts.append(f"""
<header>
  <p class="eyebrow">{_esc(case.field)} · FDE-Bench v2 case</p>
  <h1>{_esc(case.role)}</h1>
  <p class="muted"><code>{_esc(case.id)}</code></p>
  <dl class="facts">
    <div><dt>Task type</dt><dd>{_esc(meta.get('task_type', ''))}</dd></div>
    <div><dt>Deliverable</dt><dd>{deliverable}</dd></div>
    <div><dt>Objective</dt><dd>{_esc(meta.get('objective', ''))}</dd></div>
    <div><dt>Settings</dt><dd>{f"{len(case.tiers)} tiers × {len(case.rulesets)} rule sets = {len(settings)} ground truths" if has_settings else "one fixed problem"}</dd></div>
  </dl>
  <nav>
    <a href="#request">Request</a><a href="#settings">Settings</a><a href="#rules">Rules</a>
    <a href="#requirements">Hidden requirements</a><a href="#targets">Targets</a><a href="#data">Data &amp; answers</a>
    <a href="#readme">Case notes</a>{'<a href="#review">Review findings</a>' if review.is_file() else ""}
  </nav>
</header>""")

    # request
    req = "".join(f"<details{' open' if lang in ('en', 'ko') else ''}><summary>{LANG_NAMES[lang]}</summary>"
                  f"{markdown(case.request(lang))}</details>" for lang in case.locales())
    # A batch spec only reaches scoring/extract.py; the agent's prompt never contains it.
    spec_label = ("the program interface" if kind == "program"
                  else "shown to the extractor that reshapes the agent's files, not to the agent")
    parts.append(f"""<section id="request"><h2>What the agent is asked</h2>
<p class="muted">The client's request, the only text the agent gets up front. It is the same in every setting.</p>
{req}
<h3>Deliverable spec ({spec_label})</h3><pre>{_esc(case.deliverable_spec().strip())}</pre></section>""")

    # settings
    if has_settings:
        tiers = meta.get("tiers") or {}
        trows = [[f"<strong>{_esc(t)}</strong>", _esc(tiers.get(t, ""))] for t in case.tiers]
        rs = meta.get("rulesets") or {}
        params = []
        for r in case.rulesets:
            for k in (rs[r] or {}):
                if k not in params:
                    params.append(k)
        prow = [[f"<code>{_esc(k)}</code>"] + [_esc(param_text(k, (rs[r] or {}).get(k, "–"))) for r in case.rulesets]
                for k in params]
        parts.append(f"""<section id="settings"><h2>Settings: one dataset, {len(settings)} ground truths</h2>
<p>The agent sees the same request and data in every setting. The <strong>tier</strong> (= difficulty) decides which
rules apply; the <strong>rule set</strong> gives their parameters. Each difficulty is reported as the mean over rule
sets A, B and C.</p>
<h3>Tiers</h3>{_table(["Tier", "What is in force"], trows)}
<h3>Rule sets</h3>{_table(["Parameter"] + list(case.rulesets), prow)}</section>""")
    else:
        parts.append('<section id="settings"><h2>Settings</h2><p>This case has no settings: one fixed problem at '
                     'every difficulty.</p></section>')

    # rules
    rrows = []
    for r in meta.get("rules", []):
        tiers_txt = ", ".join(r.get("tiers", case.tiers)) if has_settings else "–"
        rrows.append([f"<code>{_esc(r['id'])}</code>",
                      f"<span class='pill {_esc(r['class'])}'>{_esc(r['class'])}</span>",
                      _esc(tiers_txt), _esc(r.get("description", ""))])
    classes = "".join(f"<li><span class='pill {k}'>{k}</span> {v}</li>" for k, v in CLASS_NOTE.items())
    parts.append(f"""<section id="rules"><h2>Rules</h2>
<p>Breaking any rule makes the deliverable invalid, unless the rule's class may bend under the run's company policy
and the agent went through the exception process.</p><ul class="legend">{classes}</ul>
{_table(["Rule", "Class", "Tiers", "Description (parameters in {{…}} come from the rule set)"], rrows)}</section>""")

    # hidden requirements per setting and locale (JS switcher)
    texts = {}
    for c in settings:
        key = f"{c.tier}_{c.ruleset}" if has_settings else "default"
        texts[key] = {lang: markdown(c.requirements(lang)) for lang in case.locales()}
    keys = list(texts)
    opts_s = "".join(f'<option value="{_esc(k)}"{" selected" if k == keys[len(keys) // 2] else ""}>'
                     f'{_esc(k.replace("_", " / "))}</option>' for k in keys)
    opts_l = "".join(f'<option value="{l}"{" selected" if l == "en" else ""}>{LANG_NAMES[l]}</option>'
                     for l in case.locales())
    parts.append(f"""<section id="requirements"><h2>Hidden requirements</h2>
<p class="muted">What the simulated client knows and answers from. The agent only learns it by asking (in the
<code>full_spec</code> engagement it is handed over).</p>
<div class="controls"><label>Setting <select id="req-setting">{opts_s}</select></label>
<label>Language <select id="req-lang">{opts_l}</select></label></div>
<div id="req-body" class="doc"></div>
<script id="req-data" type="application/json">{json.dumps(texts, ensure_ascii=False).replace("</", "<\\/")}</script>
</section>""")

    # targets
    src = yaml.safe_load((root / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8")) or []
    ko = {t["id"]: t["text"] for t in yaml.safe_load((root / "locales" / "ko" / "targets.yaml")
                                                     .read_text(encoding="utf-8")) or []}
    trows = [[f"<code>{_esc(t['id'])}</code>", _esc(t.get("kind", "")), _esc(", ".join(t.get("tiers", ["all"]))),
              _esc(t.get("text", "")), _esc(ko.get(t["id"], ""))] for t in src]
    parts.append(f"""<section id="targets"><h2>Clarification targets</h2>
<p class="muted">The facts a good engineer should ask the client for; Ask-F1 is scored against them.
<code>{{{{param}}}}</code> is filled from the rule set.</p>
{_table(["Target", "Kind", "Tiers", "English", "한국어"], trows)}</section>""")

    # data & answers
    ds = root / DATASET_DIR
    score_rows = []
    for gt in sorted((ds / "gt").glob("*")) if (ds / "gt").is_dir() else []:
        sc = json.loads((gt / "score.json").read_text(encoding="utf-8")) if (gt / "score.json").is_file() else {}
        metrics = sc.get("metrics", {})
        top = ", ".join(f"{k}={v}" for k, v in list(metrics.items())[:4])
        score_rows.append([f"<code>{_esc(gt.name)}</code>", _esc(sc.get("objective")),
                           _esc(sc.get("baseline_objective", "–")), _esc(top),
                           f'<a href="{DATASET_DIR}/gt/{_esc(gt.name)}/">open</a>'])
    gt_example = next(iter(sorted((ds / "gt").glob("*"))), None) if (ds / "gt").is_dir() else None
    parts.append(f"""<section id="data"><h2>Data &amp; answers (<code>dataset/</code>)</h2>
<p>Everything is stored as files next to the case. <code>visible/</code> is what the agent receives;
<code>hidden/</code> is what it never sees (a program's hidden period or corpus); <code>gt/</code> holds one answer
folder per setting. <code>validate-case</code> checks the files still match the generator.</p>
<h3>Agent-visible data (English locale)</h3>{_tree(ds / "visible" / "en")}
<h3>Hidden inputs</h3>{_tree(ds / "hidden", limit=30)}
<h3>Reference score per setting</h3>
<p class="muted">Quality is normalized per setting: the baseline (the simplest valid deliverable) is 0, the reference
is 1, and better than the reference goes above 1 (full credit at the policy's quality cap).</p>
{_table(["Setting", "Reference objective", "Baseline objective", "Metrics (first four)", "Folder"], score_rows) if score_rows else "<p class='muted'>(no dataset yet)</p>"}
<h3>One answer folder: <code>gt/{_esc(gt_example.name if gt_example else '')}</code></h3>
{_tree(gt_example, limit=40) if gt_example else ""}</section>""")

    # README
    readme = root / "README.md"
    parts.append(f"""<section id="readme"><h2>Case notes (README.md)</h2>
<div class="doc">{markdown(readme.read_text(encoding="utf-8")) if readme.is_file() else "<p class='muted'>(no README)</p>"}</div>
</section>""")

    # REVIEW.md: findings of a review of the case, when there is one
    if review.is_file():
        parts.append(f"""<section id="review"><h2>Review findings (REVIEW.md)</h2>
<div class="doc">{markdown(review.read_text(encoding="utf-8"))}</div>
</section>""")

    return _shell(case.role, "\n".join(parts))


CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a65;--line:#e4e1d8;--card:#ffffff;--accent:#2f5d8a;--code:#f2efe8;
--phys:#8a2f2f;--cont:#8a6a1f;--biz:#2f6d4a}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#161615;--fg:#ecebe6;--muted:#a3a198;
--line:#33322e;--card:#1e1e1c;--accent:#8ab4e0;--code:#262623;--phys:#e08a8a;--cont:#e0c27a;--biz:#86d0a4}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans","Noto Sans CJK KR",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 80px}
header{border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:8px}
.eyebrow{text-transform:uppercase;letter-spacing:.08em;font-size:12px;color:var(--muted);margin:0}
h1{font-size:28px;margin:4px 0}h2{font-size:21px;margin:36px 0 8px;padding-top:8px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:20px 0 6px}h4,h5,h6{font-size:15px;margin:16px 0 4px}
.muted{color:var(--muted)}a{color:var(--accent)}
code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:.92em}
pre{background:var(--code);padding:12px;border-radius:8px;overflow:auto;font-size:13px;line-height:1.45}
pre.tree{max-height:420px}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;margin:12px 0}
.facts div{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
dt{font-size:12px;color:var(--muted)}dd{margin:2px 0 0}
nav{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:10px}nav a{text-decoration:none}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;margin:6px 0;font-size:14px}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{background:var(--card)}
details{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 12px;margin:6px 0}
summary{cursor:pointer;font-weight:600}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;border:1px solid currentColor}
.pill.physical{color:var(--phys)}.pill.contractual{color:var(--cont)}.pill.business_policy{color:var(--biz)}
.legend{list-style:none;padding:0}.legend li{margin:3px 0}
.controls{display:flex;flex-wrap:wrap;gap:12px;margin:8px 0}
select{font:inherit;padding:4px 6px;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px}
.doc{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:4px 16px}
"""

JS = """
(function(){var d=JSON.parse(document.getElementById('req-data').textContent);
var s=document.getElementById('req-setting'),l=document.getElementById('req-lang'),b=document.getElementById('req-body');
function show(){var t=d[s.value]||{};b.innerHTML=t[l.value]||'<p>(not available)</p>';}
s.onchange=show;l.onchange=show;show();})();
"""


def _shell(title: str, body: str, script: bool = True) -> str:
    js = f"<script>{JS}</script>" if script else ""
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{_esc(title)}</title><style>{CSS}</style></head>"
            f"<body><main>{body}</main>{js}</body></html>\n")


def write_page(case_root: Path) -> Path:
    path = Path(case_root) / PAGE
    path.write_text(build_page(case_root), encoding="utf-8")
    return path


def build_index(cases_root: Path) -> str:
    """cases/index.html: every built case with its settings and a link to its explainer."""
    from .cases import discover, load_fields
    fields = load_fields(cases_root)
    rows = []
    for cid, case in discover(cases_root).items():
        meta = case.meta
        kind = meta.get("deliverable_type", "batch")
        settings = f"{len(case.tiers)}×{len(case.rulesets)}" if case.tiers else "–"
        rel = f"{cid}/{PAGE}"
        rows.append([_esc(fields.get(case.field, {}).get("en", case.field)),
                     f'<a href="{_esc(rel)}">{_esc(case.role)}</a>', f"<code>{_esc(cid)}</code>",
                     _esc("program" if kind == "program" else "batch"), _esc(settings),
                     _esc(meta.get("task_type", ""))])
    body = f"""<header><p class="eyebrow">FDE-Bench v2</p><h1>Built cases</h1>
<p class="muted">{len(rows)} cases. Each link opens the case's explainer: request, settings, rules, hidden requirements,
targets, stored data and answers. The full catalog of planned roles is in README.md next to this page.</p></header>
<section>{_table(["Field", "Role", "Case id", "Deliverable", "Settings", "Task type"], rows)}</section>"""
    return _shell("FDE-Bench v2 cases", body, script=False)


def write_index(cases_root: Path) -> Path:
    path = Path(cases_root) / "index.html"
    path.write_text(build_index(cases_root), encoding="utf-8")
    return path


def check_page(case_root: Path) -> list[str]:
    path = Path(case_root) / PAGE
    if not path.is_file():
        return [f"{PAGE} is missing: run `fdebench2 explain-case` (or export-dataset)"]
    if path.read_text(encoding="utf-8") != build_page(case_root):
        return [f"{PAGE} is out of date: run `fdebench2 explain-case` (or export-dataset)"]
    return []


__all__ = ["build_page", "write_page", "check_page", "LOCALES"]
