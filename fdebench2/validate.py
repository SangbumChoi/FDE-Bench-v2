"""`fdebench2 validate-case`: the checks every native case must pass before it is used.

1. case.yaml is complete; every rule has a class.
2. All five locales have request.md, requirements.md and targets.yaml, with the
   same target ids, written in the right script.
3. Data renders in every locale, deterministically (same bytes twice), with the
   same file set shape in every locale and no foreign-language labels.
4. The reference solution is valid and scores quality 1.0; an empty submission
   is not valid.
5. Each declared violating example breaks exactly the rule it names; when the
   rule is not physical, relaxing it makes the example valid again.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path

import yaml

from .cases import LOCALES, NativeCase
from .transforms.language import detect_locale
from .transforms.policy import RULE_CLASSES

REQUIRED_META = ("id", "title", "task_type", "domain", "objective", "seed", "deliverables", "deliverable_spec", "rules")
HANGUL = re.compile(r"[가-힣]")
KANA = re.compile(r"[぀-ヿ]")
HAN = re.compile(r"[一-鿿]")


def _tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def _script_problem(text: str, lang: str) -> str | None:
    letters = re.sub(r"[`].*?[`]|\{.*?\}|[A-Za-z0-9_./\-]+", "", text)  # ignore code, ids, file names
    if lang == "ko" and not HANGUL.search(letters):
        return "no Hangul"
    if lang == "ja" and not KANA.search(letters):
        return "no kana"
    if lang == "zh" and (KANA.search(letters) or HANGUL.search(letters) or not HAN.search(letters)):
        return "not Chinese"
    if lang in ("en", "es") and (HAN.search(letters) or HANGUL.search(letters) or KANA.search(letters)):
        return "contains CJK text"
    if lang in ("en", "es") and detect_locale(text) not in (lang, None):
        return f"reads as {detect_locale(text)}"
    return None


def validate_case(root: Path) -> list[str]:
    problems: list[str] = []
    case = NativeCase(root)
    meta = case.meta
    problems += [f"case.yaml: missing {k}" for k in REQUIRED_META if k not in meta]
    if meta.get("id") != root.name:
        problems.append(f"case.yaml id {meta.get('id')!r} != directory name {root.name!r}")
    if meta.get("objective") not in ("minimize", "maximize"):
        problems.append("case.yaml: objective must be minimize or maximize")
    rule_ids = []
    for r in meta.get("rules", []):
        rule_ids.append(r.get("id"))
        if r.get("class") not in RULE_CLASSES:
            problems.append(f"rule {r.get('id')}: class must be one of {RULE_CLASSES}")
        if not r.get("description"):
            problems.append(f"rule {r.get('id')}: needs a description")

    # ── texts ────────────────────────────────────────────────────────────────
    ids_by_lang = {}
    for lang in LOCALES:
        d = root / "locales" / lang
        for name in ("request.md", "requirements.md", "targets.yaml"):
            if not (d / name).is_file():
                problems.append(f"{lang}: missing {name}")
        if problems and any(p.startswith(f"{lang}: missing") for p in problems):
            continue
        for name in ("request.md", "requirements.md"):
            why = _script_problem((d / name).read_text(encoding="utf-8"), lang)
            if why:
                problems.append(f"{lang}/{name}: {why}")
        targets = yaml.safe_load((d / "targets.yaml").read_text(encoding="utf-8")) or []
        ids_by_lang[lang] = [t.get("id") for t in targets]
        for t in targets:
            why = _script_problem(t.get("text", ""), lang)
            if why:
                problems.append(f"{lang}/targets.yaml {t.get('id')}: {why}")
            if lang == "en" and (not t.get("kind") or not t.get("domain")):
                problems.append(f"en/targets.yaml {t.get('id')}: needs kind and domain")
    if ids_by_lang and len({tuple(v) for v in ids_by_lang.values()}) > 1:
        problems.append(f"target ids differ across locales: {ids_by_lang}")
    if problems:
        return problems

    # ── data ─────────────────────────────────────────────────────────────────
    shapes = {}
    with tempfile.TemporaryDirectory() as tmp:
        for lang in LOCALES:
            a, b = Path(tmp) / lang / "a", Path(tmp) / lang / "b"
            case.materialize_data(lang, a)
            case.materialize_data(lang, b)
            if _tree_digest(a) != _tree_digest(b):
                problems.append(f"{lang}: data is not deterministic")
            files = sorted(p for p in a.rglob("*") if p.is_file())
            if not files:
                problems.append(f"{lang}: no data files")
            shapes[lang] = [(p.suffix, p.stat().st_size > 0) for p in files]
            if lang in ("en", "es"):
                for p in files:
                    if p.suffix in (".csv", ".json", ".md", ".txt") and (HAN.search(p.read_text(encoding="utf-8-sig"))
                                                                          or HANGUL.search(p.read_text(encoding="utf-8-sig"))):
                        problems.append(f"{lang}: {p.name} contains CJK labels")
                    if HAN.search(p.name) or HANGUL.search(p.name) or KANA.search(p.name):
                        problems.append(f"{lang}: file name {p.name} is not localized")
        if len({tuple(v) for v in shapes.values()}) > 1:
            problems.append("data file sets differ in shape across locales")

        # ── scoring ──────────────────────────────────────────────────────────
        ref_dir = Path(tmp) / "ref"
        ref_dir.mkdir()
        case.module.reference_solution(case.world, ref_dir)
        for lang in LOCALES:
            res = case.evaluate(ref_dir, lang)
            if res["validity_score"] != 1.0 or abs(res["quality_score"] - 1.0) > 1e-9:
                problems.append(f"{lang}: reference solution scores {res}")
        empty = Path(tmp) / "empty"
        empty.mkdir()
        if case.evaluate(empty, "en")["validity_score"] != 0.0:
            problems.append("an empty submission is valid")
        examples = getattr(case.module, "violating_examples", lambda w: {})(case.world)
        for rule_id in rule_ids:
            if rule_id not in examples:
                problems.append(f"rule {rule_id}: no violating example")
        for rule_id, make in examples.items():
            ex = Path(tmp) / f"viol_{rule_id}"
            ex.mkdir()
            make(ex)
            res = case.evaluate(ex, "en")
            broken = {v["rule"] for v in res["violations"]}
            if rule_id not in broken:
                problems.append(f"rule {rule_id}: its example does not violate it (got {sorted(broken)})")
            elif broken != {rule_id}:
                problems.append(f"rule {rule_id}: its example also violates {sorted(broken - {rule_id})}")
            rule = case.rules().by_id(rule_id)
            if rule and rule.rule_class != "physical":
                relaxed = case.evaluate(ex, "en", relaxed=frozenset({rule_id}))
                if relaxed["validity_score"] != 1.0:
                    problems.append(f"rule {rule_id}: example still invalid when the rule is relaxed: {relaxed}")
    return problems
