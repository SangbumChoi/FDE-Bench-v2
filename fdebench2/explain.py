"""One self-contained explainer page per case: cases/<field>/<role>/explainer.html.

The page gathers everything a reviewer needs to understand a case without
running it: the request, the hidden requirements in every public setting and
locale, the rules and their classes, the rule parameters (candidates per tier
and the values the public rule seeds drew), the clarification targets, the
case README, the stored dataset, the reference scores, the findings of a
review (REVIEW.md, when the case has one) and the evidence of its ground truth
audit (dataset/audit.json, when audit-case stored one). It is generated from the case files
(`fdebench2 explain-case`, also run by `export-dataset`), works offline, and
validate-case checks that it is up to date.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import yaml

from .audit import load_audit, shortcut_summary, target_summary, tier_order
from .cases import LOCALES, NativeCase, load_fields, value_label, value_text
from .dataset import DATASET_DIR

PAGE = "explainer.html"
LANG_NAMES = {"en": "English", "ko": "한국어", "zh": "中文", "ja": "日本語", "es": "Español"}
LANGS = tuple(LANG_NAMES)                        # the order of the language switcher

# ── a small Markdown renderer (headings, lists, tables, code, emphasis) ─────────

def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', out)
    return out


# Chinese and Japanese text has no spaces between words: a line wrapped between two such characters joins
# without one. Korean, which spaces its words, joins like English.
_NO_SPACE = re.compile(r"[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")


def _join(lines: list[str]) -> str:
    out = lines[0]
    for line in lines[1:]:
        out += ("" if _NO_SPACE.match(out[-1:]) and _NO_SPACE.match(line[:1]) else " ") + line
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
                    items[-1] = _join([items[-1], lines[j].strip()])
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
        out.append("<p>" + _inline(_join(para)) + "</p>")
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


# ── languages: one page per locale ──────────────────────────────────────────

UI = yaml.safe_load((Path(__file__).parent / "prompts" / "explainer.yaml").read_text(encoding="utf-8"))
TRANSLATED_DOCS = ("README.md", "REVIEW.md")      # README.<lang>.md / REVIEW.<lang>.md next to them


def page_name(lang: str) -> str:
    return PAGE if lang == "en" else f"explainer.{lang}.html"


def index_name(lang: str) -> str:
    return "index.html" if lang == "en" else f"index.{lang}.html"


def _t(lang: str, key: str, **values) -> str:
    """Interface text (prompts/explainer.yaml) as HTML; values are HTML already."""
    text = UI[lang][key]
    out = text if "<" in text else _esc(text)
    for name, value in values.items():
        out = out.replace("{" + name + "}", str(value))
    return out


def case_texts(case_root: Path, lang: str) -> dict:
    """locales/<lang>/explainer.yaml: the case's own words for the explainer (role, task type, tiers, rules,
    deliverable spec and, optionally, `shortcuts: {name: description}` for the audit's shortcuts) in that language.
    English comes from case.yaml (and the shortcuts' docstrings)."""
    path = Path(case_root) / "locales" / lang / "explainer.yaml"
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if lang != "en" and path.is_file() else {}


SUMMARY_KEYS = ("task", "given", "ask", "invalid_if", "quality", "tiers")


def case_summary(case_root: Path, lang: str) -> dict:
    """locales/<lang>/summary.yaml: the case in plain words for the top of its page (what the AI has to do, what it
    is given, what it must ask, what makes it score 0, how quality is measured, what each difficulty adds)."""
    path = Path(case_root) / "locales" / lang / "summary.yaml"
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.is_file() else {}


def localized_doc(case_root: Path, name: str, lang: str) -> tuple[str | None, bool]:
    """(text, translated): README.<lang>.md for README.md and so on; the English file when it is missing."""
    base = Path(case_root) / name
    if lang != "en":
        own = base.with_name(f"{base.stem}.{lang}{base.suffix}")
        if own.is_file():
            return own.read_text(encoding="utf-8"), True
    return (base.read_text(encoding="utf-8"), lang == "en") if base.is_file() else (None, False)


def _switcher(lang: str, name) -> str:
    """Links to the same page in every language; the choice is remembered for the next page."""
    links = "".join(f'<a href="{name(l)}" data-lang="{l}" hreflang="{l}"{" aria-current=\"page\"" if l == lang else ""}>'
                    f"{LANG_NAMES[l]}</a>" for l in LANGS)
    return f'<nav class="langs" aria-label="{_t(lang, "language")}">{links}</nav>'


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{x:.0%}"


def _q(x: float | None) -> str:
    return "–" if x is None else f"{x:.2f}"


def _evidence(audit: dict, lang: str, src: list[dict], words: dict[str, str]) -> str:
    """The folded section "Evidence the facts matter", from dataset/audit.json (fdebench2.audit): per target (in
    en/targets.yaml's order, `src`) what misreading only it costs, the shortcuts (described in `words`, the page
    language's locales/<lang>/explainer.yaml `shortcuts:`, else by their docstring), the value of asking per tier,
    and how close the reference is to the best known solution and the bound."""
    t = lambda key, **kw: _t(lang, key, **kw)  # noqa: E731
    order, params = [x["id"] for x in src], {x["id"]: x.get("param", "") for x in src}
    checked = {"param": lambda target: t("checked_param", param=f"<code>{_esc(params.get(target, ''))}</code>"),
               "hook": lambda target: t("checked_hook")}
    targets = [[f"<code>{_esc(x['target'])}</code>", _esc(", ".join(x["tiers"])),
                "; ".join(checked[s](x["target"]) for s in x["sources"]) or t("checked_none"),
                _pct(x["low"]) if x["low"] == x["high"] else f"{_pct(x['low'])}–{_pct(x['high'])}",
                t("k_of_n", k=x["bites"], n=x["checked"]) if x["checked"] else "–",
                t("answer_yes" if x["has_diagnostic"] else "answer_no")]
               for x in sorted(target_summary(audit), key=lambda x: order.index(x["target"]) if x["target"] in order
                               else len(order))]
    shortcuts = [[f"<code>{_esc(s['name'])}</code>", _esc(words.get(s["name"]) or s["description"]),
                  t("k_of_n", k=s["closed"], n=s["settings"]), _q(s["best_quality"])] for s in shortcut_summary(audit)]
    voi = [[_esc(tier), _q(v["never_asks_params"]),
            t("not_measured") if v["never_asks"] is None else _q(v["never_asks"]), "1.00"]
           for tier, v in ((tier, audit["voi"][tier]) for tier in tier_order(audit["voi"]))]
    bounds = [[_esc(b["setting"]), _q(b["best_known_quality"]), _q(b["bound_quality"]), _pct(b["gap_to_bound"])]
              for b in audit["bounds"] if b["best_known_valid"] is not None or b["bound"] is not None]
    th = audit["thresholds"]
    n = sum(len(v) for v in audit["settings"].values())
    return f"""<section id="evidence"><h2>{t("evidence_title")}</h2>
<p class="muted">{t("evidence_intro", n=n)}</p>
<h3>{t("ablation_title")}</h3><p class="muted">{t("ablation_intro", min=_pct(th["ablation_min_damage"]))}</p>
{_table([t("target"), t("in_force_tiers"), t("checked_by"), t("score_lost"), t("matters_in"), t("diagnostic")], targets)}
<h3>{t("shortcuts_title")}</h3><p class="muted">{t("shortcuts_intro", max=_q(th["shortcut_max_quality"]))}</p>
{_table([t("shortcut"), t("what_it_does"), t("closed_in"), t("best_quality")], shortcuts) if shortcuts else f"<p class='muted'>{t('no_shortcuts')}</p>"}
<h3>{t("voi_title")}</h3><p class="muted">{t("voi_intro")}</p>
{_table([t("tier"), t("voi_params"), t("voi_robust"), t("voi_reference")], voi)}
<h3>{t("bounds_title")}</h3><p class="muted">{t("bounds_intro")}</p>
{_table([t("setting"), t("best_known"), t("bound"), t("gap_to_bound")], bounds) if bounds else f"<p class='muted'>{t('no_bounds')}</p>"}
</section>"""


def build_page(case_root: Path, lang: str = "en") -> str:
    """The explainer in one language: interface, case texts, README and REVIEW all in `lang`."""
    case = NativeCase(Path(case_root))
    meta = case.meta
    root = case.root
    settings = case.settings()
    has_settings = bool(case.tiers)
    labels = case.param_labels()
    own = case_texts(root, lang)
    t = lambda key, **kw: _t(lang, key, **kw)  # noqa: E731

    def candidate(name, value) -> str:
        """A candidate value as code, with its wording in the page's language when the case gives one."""
        code = f"<code>{_esc(value_text(value))}</code>"
        if name not in labels:
            return code
        try:
            word = str(value_label(labels[name], value)[lang])
        except KeyError:
            return code
        return code if word == value_text(value) else f"{code} {_esc(word)}"

    def condition(item) -> str:
        """" · only when name = v1, v2" for a rule or target with when: (empty without one)."""
        when = item.get("when") or {}
        if not when:
            return ""
        cond = "; ".join(f"{k} = {', '.join(value_text(v) for v in (vs if isinstance(vs, list) else [vs]))}"
                         for k, vs in when.items())
        return " · " + t("only_when", cond=_esc(cond))

    review_md, _ = localized_doc(root, "REVIEW.md", lang)
    summary = case_summary(root, lang)
    audit = load_audit(root)
    parts: list[str] = []

    # header
    kind = meta.get("deliverable_type", "batch")
    deliverable = (t("program", entry=f"<code>{_esc(meta.get('entrypoint', ''))}</code>") if kind == "program"
                   else t("batch_files", files=", ".join(f"<code>{_esc(d)}</code>" for d in meta.get("deliverables", []))))
    field_name = load_fields(root.parent.parent).get(case.field, {}).get(lang, case.field)
    settings_value = (t("settings_value", tiers=len(case.tiers), seeds=len(case.rule_seeds), n=len(settings))
                      if has_settings else t("one_problem"))
    objective = meta.get("objective", "")
    parts.append(f"""
<header>
  {_switcher(lang, page_name)}
  <p class="eyebrow">{t("case_eyebrow", field=_esc(field_name))}</p>
  <h1>{_esc(own.get("role") or case.role)}</h1>
  <p class="muted"><code>{_esc(case.id)}</code></p>
  <dl class="facts">
    <div><dt>{t("task_type")}</dt><dd>{_esc(own.get("task_type") or meta.get("task_type", ""))}</dd></div>
    <div><dt>{t("deliverable")}</dt><dd>{deliverable}</dd></div>
    <div><dt>{t("objective")}</dt><dd>{t(objective) if objective in ("maximize", "minimize") else _esc(objective)}</dd></div>
    <div><dt>{t("settings")}</dt><dd>{settings_value}</dd></div>
  </dl>
  <nav>
    {f'<a href="#glance">{t("nav_glance")}</a>' if summary else ""}<a href="#scoring">{t("nav_scoring")}</a><a href="#details">{t("nav_details")}</a>
  </nav>
</header>""")

    # the case in plain words: what the AI has to do, what it gets, what it must ask, how it is scored
    li = lambda items: "<ul>" + "".join(f"<li>{_inline(str(x))}</li>" for x in items or []) + "</ul>"  # noqa: E731
    if summary:
        parts.append(f"""<section id="glance"><h2>{t("glance_title")}</h2>
<div class="card"><h3>{t("task_title")}</h3><p>{_inline(str(summary.get("task", "")))}</p></div>
<div class="cols"><div><h3>{t("given_title")}</h3>{li(summary.get("given"))}</div>
<div><h3>{t("ask_title")}</h3>{li(summary.get("ask"))}</div></div></section>""")
    tiers_rows = [[f"<strong>{_esc(x)}</strong>", _inline(str((summary.get("tiers") or {}).get(x, "")))]
                  for x in case.tiers] if summary else []
    parts.append(f"""<section id="scoring"><h2>{t("scoring_title")}</h2>
{f'<div class="cols"><div><h3>{t("invalid_title")}</h3>{li(summary.get("invalid_if"))}</div><div><h3>{t("quality_title")}</h3><p>{_inline(str(summary.get("quality", "")))}</p></div></div>' if summary else ""}
{f'<h3 id="tiers">{t("tiers_title")}</h3>' + _table([t("difficulty"), t("asks_for")], tiers_rows) if tiers_rows else ""}
<h3>{t("common_title")}</h3><div class="common">{t("common_body")}</div></section>""")

    # everything else, folded: the full material behind the summary
    parts.append(f"""<details class="more" id="details"{"" if summary else " open"}><summary>{t("details_title")}</summary>
<p class="muted">{t("details_intro")}</p>
<nav class="sub"><a href="#request">{t("nav_request")}</a><a href="#settings">{t("nav_settings")}</a><a href="#rules">{t("nav_rules")}</a>
<a href="#requirements">{t("nav_requirements")}</a><a href="#targets">{t("nav_targets")}</a>{f'<a href="#evidence">{t("nav_evidence")}</a>' if audit else ""}<a href="#data">{t("nav_data")}</a>
<a href="#readme">{t("nav_readme")}</a>{f'<a href="#review">{t("nav_review")}</a>' if review_md else ""}</nav>""")

    # request, in the page's language only (the switcher at the top picks the language)
    req = f'<div class="doc">{markdown(case.request(lang))}</div>'
    # A batch spec only reaches scoring/extract.py; the agent's prompt never contains it.
    spec_label = t("spec_program") if kind == "program" else t("spec_batch")
    spec = f"<pre>{_esc((own.get('deliverable_spec') or case.deliverable_spec()).strip())}</pre>"   # page's language
    parts.append(f"""<section id="request"><h2>{t("request_title")}</h2>
<p class="muted">{t("request_intro")}</p>
{req}
<h3>{t("spec_title", label=spec_label)}</h3>{spec}</section>""")

    # settings
    if has_settings:
        tiers = {**(meta.get("tiers") or {}), **(own.get("tiers") or {})}
        trows = [[f"<strong>{_esc(x)}</strong>", _esc(tiers.get(x, ""))] for x in case.tiers]
        pools = case.param_candidates
        prow = [[f"<code>{_esc(k)}</code>"] + [", ".join(candidate(k, v) for v in pools[k][x]) for x in case.tiers]
                for k in pools]
        panel = [[_esc(c.tier), _esc(c.rule_seed),
                  f"<code>{_esc(json.dumps(c.drawn_params, ensure_ascii=False, default=str))}</code>"]
                 for c in settings]
        derived = sorted({k for c in settings for k in c.setting.params} - set(pools))
        note = (f"<p class='muted'>{t('derived_note', names=', '.join(f'<code>{_esc(k)}</code>' for k in derived))}</p>"
                if derived else "")
        parts.append(f"""<section id="settings"><h2>{t("settings_title", n=len(settings))}</h2>
<p>{t("settings_intro")}</p>
<h3>{t("tiers")}</h3>{_table([t("tier"), t("in_force")], trows)}
<h3>{t("param_candidates")}</h3>{_table([t("parameter")] + list(case.tiers), prow)}{note}
<h3>{t("public_panel")}</h3><p class="muted">{t("public_panel_intro")}</p>
{_table([t("tier"), t("rule_seed"), t("drawn_values")], panel)}</section>""")
    else:
        parts.append(f'<section id="settings"><h2>{t("settings")}</h2><p>{t("no_settings")}</p></section>')

    # rules
    descriptions = own.get("rules") or {}
    rrows = []
    for r in meta.get("rules", []):
        tiers_txt = ", ".join(r.get("tiers", case.tiers)) if has_settings else "–"
        rrows.append([f"<code>{_esc(r['id'])}</code>",
                      f"<span class='pill {_esc(r['class'])}'>{t('class_' + r['class'])}</span>",
                      _esc(tiers_txt) + condition(r), _esc(descriptions.get(r["id"]) or r.get("description", ""))])
    classes = "".join(f"<li><span class='pill {k}'>{t('class_' + k)}</span> {t('note_' + k)}</li>"
                      for k in ("physical", "contractual", "business_policy"))
    described = t("description_params") if has_settings else t("description")
    parts.append(f"""<section id="rules"><h2>{t("rules_title")}</h2>
<p>{t("rules_intro")}</p><ul class="legend">{classes}</ul>
{_table([t("rule"), t("class"), t("tiers"), described], rrows)}</section>""")

    # hidden requirements per setting (tier x public rule seed), in the page's language (JS switcher)
    texts, names = {}, {}
    for c in settings:
        key = c.setting.folder if has_settings else "default"
        texts[key] = markdown(c.requirements(lang))
        names[key] = f"{c.tier} / {UI[lang]['rule_seed']} {c.rule_seed}" if has_settings else key
    keys = list(texts)
    opts_s = "".join(f'<option value="{_esc(k)}"{" selected" if k == keys[len(keys) // 2] else ""}>'
                     f'{_esc(names[k])}</option>' for k in keys)
    parts.append(f"""<section id="requirements"><h2>{t("requirements_title")}</h2>
<p class="muted">{t("requirements_intro")}</p>
<div class="controls"><label>{t("setting")} <select id="req-setting">{opts_s}</select></label></div>
<div id="req-body" class="doc" data-empty="{t("not_available")}"></div>
<script id="req-data" type="application/json">{json.dumps(texts, ensure_ascii=False).replace("</", "<\\/")}</script>
</section>""")

    # targets, in the page's language
    src = yaml.safe_load((root / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8")) or []
    mine = {x["id"]: x["text"] for x in yaml.safe_load((root / "locales" / lang / "targets.yaml")
                                                       .read_text(encoding="utf-8")) or []}
    cols = [t("target"), t("kind"), t("tiers"), t("fact")]
    trows = [[f"<code>{_esc(x['id'])}</code>", _esc(x.get("kind", "")),
              _esc(", ".join(x["tiers"]) if x.get("tiers") else t("all_tiers")) + condition(x), _esc(mine.get(x["id"], ""))]
             for x in src]
    parts.append(f"""<section id="targets"><h2>{t("targets_title")}</h2>
<p class="muted">{t("targets_intro_params" if has_settings else "targets_intro")}</p>
{_table(cols, trows)}</section>""")
    if audit:       # the ground truth audit, when audit-case has stored one
        parts.append(_evidence(audit, lang, src, own.get("shortcuts") or {}))

    # data & answers
    ds = root / DATASET_DIR
    score_rows = []
    for gt in sorted((ds / "gt").glob("*")) if (ds / "gt").is_dir() else []:
        sc = json.loads((gt / "score.json").read_text(encoding="utf-8")) if (gt / "score.json").is_file() else {}
        metrics = sc.get("metrics", {})
        top = ", ".join(f"{k}={v}" for k, v in list(metrics.items())[:4])
        score_rows.append([f"<code>{_esc(gt.name)}</code>", _esc(sc.get("objective")),
                           _esc(sc.get("baseline_objective", "–")), _esc(top),
                           f'<a href="{DATASET_DIR}/gt/{_esc(gt.name)}/">{t("open")}</a>'])
    gt_example = next(iter(sorted((ds / "gt").glob("*"))), None) if (ds / "gt").is_dir() else None
    visible = ds / "agent_view" / lang if (ds / "agent_view" / lang).is_dir() else ds / "agent_view" / "en"
    score_head = [t("setting"), t("reference_objective"), t("baseline_objective"), t("metrics"), t("folder")]
    parts.append(f"""<section id="data"><h2>{t("data_title")} (<code>dataset/</code>)</h2>
<p>{t("data_intro")}</p>
<h3>{t("visible_data", language=LANG_NAMES[lang])}</h3>{_tree(visible)}
<h3>{t("hidden_inputs")}</h3>{_tree(ds / "hidden", limit=30)}
<h3>{t("scores_title")}</h3>
<p class="muted">{t("scores_intro")}</p>
{_table(score_head, score_rows) if score_rows else f"<p class='muted'>{t('no_dataset')}</p>"}
<h3>{t("answer_folder", folder=f"<code>gt/{_esc(gt_example.name if gt_example else '')}</code>")}</h3>
{_tree(gt_example, limit=40) if gt_example else ""}</section>""")

    # README and REVIEW.md, in the page's language when translated
    for doc, anchor, title, empty in (("README.md", "readme", "readme_title", "no_readme"),
                                      ("REVIEW.md", "review", "review_title", None)):
        text, translated = localized_doc(root, doc, lang)
        if text is None and empty is None:
            continue
        note = "" if translated or text is None else f"<p class='muted'>{t('untranslated')}</p>"
        body = markdown(text) if text is not None else f"<p class='muted'>{t(empty)}</p>"
        parts.append(f"""<section id="{anchor}"><h2>{t(title)}</h2>{note}
<div class="doc">{body}</div>
</section>""")

    parts.append("</details>")
    return _shell(own.get("role") or case.role, "\n".join(parts), lang=lang)


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
.card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;padding:4px 16px;margin:8px 0}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:4px 24px}
.common{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:4px 16px}
details.more{background:none;border:0;padding:0;margin-top:36px;border-top:1px solid var(--line)}
details.more>summary{font-size:21px;font-weight:700;padding:16px 0 8px}
nav.sub{margin:0 0 8px}
.langs{display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end;margin:0 0 8px}
.langs a{padding:2px 10px;border:1px solid var(--line);border-radius:999px;text-decoration:none;font-size:13px}
.langs a[aria-current]{background:var(--accent);border-color:var(--accent);color:var(--bg)}
"""

JS = """
(function(){var d=JSON.parse(document.getElementById('req-data').textContent);
var s=document.getElementById('req-setting'),b=document.getElementById('req-body');
function show(){b.innerHTML=d[s.value]||'<p>'+b.dataset.empty+'</p>';}
s.onchange=show;show();})();
(function(){function reveal(){var id=location.hash.slice(1),el=id&&document.getElementById(id);
if(el){var d=el.closest('details');if(d&&!d.open){d.open=true;el.scrollIntoView();}}}
window.addEventListener('hashchange',reveal);reveal();})();
"""

# The chosen language is remembered (a click on the switcher) and followed on every other page.
LANG_JS = """
(function(){var here=document.documentElement.lang,links=document.querySelectorAll('.langs a[data-lang]');
links.forEach(function(a){a.addEventListener('click',function(){try{localStorage.setItem('fde-lang',a.dataset.lang)}catch(e){}})});
var want=null;try{want=localStorage.getItem('fde-lang')}catch(e){}
if(want&&want!==here){links.forEach(function(a){if(a.dataset.lang===want)location.replace(a.href+location.hash)})}})();
"""


def _shell(title: str, body: str, script: bool = True, lang: str = "en") -> str:
    js = (f"<script>{JS}</script>" if script else "") + (f"<script>{LANG_JS}</script>" if 'class="langs"' in body
                                                          else "")
    return (f'<!doctype html>\n<html lang="{lang}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{_esc(title)}</title><style>{CSS}</style></head>"
            f"<body><main>{body}</main>{js}</body></html>\n")


def write_page(case_root: Path) -> Path:
    """Write the explainer in every language; returns the English page."""
    for lang in LANGS:
        (Path(case_root) / page_name(lang)).write_text(build_page(case_root, lang), encoding="utf-8")
    return Path(case_root) / PAGE


def build_index(cases_root: Path, lang: str = "en") -> str:
    """cases/index.html (and index.<lang>.html): every built case with its settings and a link to its explainer."""
    from .cases import discover
    fields = load_fields(cases_root)
    t = lambda key, **kw: _t(lang, key, **kw)  # noqa: E731
    rows = []
    for cid, case in discover(cases_root).items():
        meta, own = case.meta, case_texts(case.root, lang)
        kind = meta.get("deliverable_type", "batch")
        settings = f"{len(case.tiers)}×{len(case.rule_seeds)}" if case.tiers else "–"
        rel = f"{cid}/{page_name(lang)}"
        rows.append([_esc(fields.get(case.field, {}).get(lang, case.field)),
                     f'<a href="{_esc(rel)}">{_esc(own.get("role") or case.role)}</a>', f"<code>{_esc(cid)}</code>",
                     _esc(kind), _esc(settings), _esc(own.get("task_type") or meta.get("task_type", ""))])
    body = f"""<header>{_switcher(lang, index_name)}<p class="eyebrow">{t("index_eyebrow")}</p><h1>{t("index_title")}</h1>
<p class="muted">{t("index_intro", n=len(rows))}</p></header>
<section><h2>{t("scoring_title")}</h2><div class="common">{t("common_body")}</div></section>
<section>{_table([t("field"), t("role"), t("case_id"), t("deliverable"), t("settings"), t("task_type")], rows)}</section>"""
    return _shell(f"FDE-Bench v2 — {UI[lang]['index_title']}", body, script=False, lang=lang)


def write_index(cases_root: Path) -> Path:
    for lang in LANGS:
        (Path(cases_root) / index_name(lang)).write_text(build_index(cases_root, lang), encoding="utf-8")
    return Path(cases_root) / "index.html"


def check_page(case_root: Path) -> list[str]:
    problems = []
    for lang in LANGS:
        path = Path(case_root) / page_name(lang)
        if not path.is_file():
            problems.append(f"{path.name} is missing: run `fdebench2 explain-case` (or export-dataset)")
        elif path.read_text(encoding="utf-8") != build_page(case_root, lang):
            problems.append(f"{path.name} is out of date: run `fdebench2 explain-case` (or export-dataset)")
    return problems


__all__ = ["build_page", "write_page", "check_page", "LOCALES"]
