"""`fdebench2 validate-case`: the checks every native case must pass before it is used.

1. case.yaml is complete; every rule has a class; no TODO is left from the
   scaffold in case.yaml, case.py, README.md or the locales.
2. All five locales have request.md, requirements.md and targets.yaml, with the
   same target ids, parameters and setting blocks as en, written in the right script.
3. Data renders in every locale, deterministically (same bytes twice, and the same
   bytes in two processes with different PYTHONHASHSEED), with the same file set
   shape in every locale and no foreign-language labels.
4. The reference solution is valid and scores quality 1.0; an empty submission
   is not valid; a baseline_solution, when the case has one, is valid and worse
   than the reference.
5. Each declared violating example breaks exactly the rule it names; when the
   rule is not physical, relaxing it makes the example valid again.

A case with settings (tiers x rule sets) is checked in every setting (4-5 run
per setting, with that setting's rules and parameters), and also:

6. request.md has no setting markers or parameters, and the agent's whole view
   (prompt and workspace) is byte-identical in every setting;
7. the rule sets are really different ground truths: within a tier, each rule
   set's reference is invalid, or at least 1% worse, under every other rule set;
8. markers, parameters and `tiers:` / `rulesets:` lists only name declared ones.

Every case also stores its data and ground truth in dataset/ (fdebench2.dataset);
the stored files must match what the generator produces now.

Warnings do not fail a case but point at likely authoring slips: a case without a
baseline, two tiers with the same answer, a number in a rule that the requirements
never state, and a "name (ID)" in the texts that the data gives another name.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .cases import BASELINE_MIN_GAP, LOCALES, PARAM, RULESETS, TIERS, NativeCase, load_fields
from .transforms.language import detect_locale
from .transforms.policy import RULE_CLASSES

DISTINCT_MARGIN = 0.01           # on the objective ratio: rule sets whose answers differ by less look the same
BASELINE_REQUIRED = True         # a case without baseline_solution fails validation
REQUIRED_META = ("id", "role", "field", "task_type", "objective", "seed", "deliverable_spec", "rules")
HANGUL = re.compile(r"[가-힣]")
KANA = re.compile(r"[぀-ヿ]")
HAN = re.compile(r"[一-鿿]")
MARKER = re.compile(r"<!-- (tier|ruleset): ([A-Za-z ]+) -->")
TODO = re.compile(r"(?<![A-Za-z0-9])TODO(?![A-Za-z0-9])")   # also the scaffold's ids (TODO_rule, TODO_target)
NUMBER = re.compile(r"(?<![\w.,])\d+(?:,\d{3})*(?:\.\d+)?(?!\w)")
DATE_OR_TIME = re.compile(r"\d{4}-\d{2}-\d{2}|\b\d{1,2}:\d{2}\b")
# "The Clock Tower café (C11)": capitalized words, at most one lowercase head noun, then the ID in parentheses
LATIN_NAME = re.compile(r"(?<![A-Za-zÀ-ÿ])((?:[A-ZÀ-Þ][A-Za-zÀ-ÿ'-]* )*[A-ZÀ-Þ][A-Za-zÀ-ÿ'-]*)"
                        r"(?: [a-zß-ÿ][A-Za-zÀ-ÿ'-]*)? ?[(（]([A-Z]{1,3}\d{1,4})[)）]")
CJK_NAME = re.compile(r"([぀-ヿ가-힣一-鿿]{2,}) ?[(（]([A-Z]{1,3}\d{1,4})[)）]")
ARTICLES = {"the", "a", "an", "our", "la", "el", "los", "las"}
DATA_TEXT = (".csv", ".tsv", ".txt", ".md", ".sql", ".eml", ".json")
HASH_SEEDS = ("1", "2")
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_RENDER = """
import sys
from pathlib import Path
from fdebench2.cases import NativeCase
case, out = NativeCase(Path(sys.argv[1])), Path(sys.argv[2])
case.materialize_data("en", out / "data")
(out / "reference").mkdir()
case.write_reference(out / "reference")
"""


@dataclass
class Report:
    """What validate-case found: problems fail the case; warnings and notes are printed for its author."""

    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


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


def _todos(root: Path) -> list[str]:
    """Scaffold placeholders still in the case's own files: a new case fails until every TODO is filled."""
    problems = []
    for p in [root / "case.yaml", root / "case.py"] + sorted(root.glob("README*.md")) + sorted((root / "locales").rglob("*")):
        if p.is_file():
            lines = [str(i) for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
                     if TODO.search(line)]
            if lines:
                more = f" and {len(lines) - 3} more" if len(lines) > 3 else ""
                problems.append(f"{p.relative_to(root).as_posix()}: TODO left on line {', '.join(lines[:3])}{more}")
    return problems


def _difference(want, got) -> str:
    missing, extra = sorted(set(want) - set(got)), sorted(set(got) - set(want))
    return "; ".join(([f"missing {missing}"] if missing else []) + ([f"extra {extra}"] if extra else []))


def _translations(case: NativeCase) -> list[str]:
    """The explainer in every language: locales/<lang>/explainer.yaml covers the case's own words (role, task
    type, every tier and rule, the deliverable spec), and README.md / REVIEW.md have a README.<lang>.md /
    REVIEW.<lang>.md next to them."""
    problems = []
    rule_ids = [r["id"] for r in case.meta.get("rules", [])]
    for lang in LOCALES:
        if lang == "en":
            continue
        path = case.root / "locales" / lang / "explainer.yaml"
        if not path.is_file():
            problems.append(f"{lang}/explainer.yaml is missing (the explainer's case texts in this language)")
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        missing = [k for k in ("role", "task_type", "deliverable_spec") if not doc.get(k)]
        missing += [f"tiers.{t}" for t in case.tiers if not (doc.get("tiers") or {}).get(t)]
        missing += [f"rules.{r}" for r in rule_ids if not (doc.get("rules") or {}).get(r)]
        extra = sorted(set(doc.get("rules") or {}) - set(rule_ids)) + sorted(set(doc.get("tiers") or {}) - set(case.tiers))
        if missing or extra:
            problems.append(f"{lang}/explainer.yaml: " + "; ".join(
                ([f"missing {', '.join(missing)}"] if missing else []) + ([f"unknown {', '.join(extra)}"] if extra else [])))
        for doc_name in ("README", "REVIEW"):
            if (case.root / f"{doc_name}.md").is_file() and not (case.root / f"{doc_name}.{lang}.md").is_file():
                problems.append(f"{doc_name}.{lang}.md is missing (the translation of {doc_name}.md)")
    return problems


def _locale_parity(requirements: dict[str, str], targets: dict[str, list[dict]]) -> list[str]:
    """Every locale has en's parameters, setting blocks and target ids: a translation must not drop or add one."""
    def blocks(text: str) -> list[str]:
        return [f"{kind}: {' '.join(names.split())}" for kind, names in MARKER.findall(text)]

    problems = []
    en_ids = [t.get("id") for t in targets["en"]]
    en_params = {t.get("id"): PARAM.findall(t.get("text", "")) for t in targets["en"]}
    for lang in requirements:
        if lang == "en":
            continue
        diff = _difference(PARAM.findall(requirements["en"]), PARAM.findall(requirements[lang]))
        if diff:
            problems.append(f"{lang}/requirements.md: parameters differ from en ({diff})")
        want, got = blocks(requirements["en"]), blocks(requirements[lang])
        if got != want:
            i = next(i for i in range(max(len(got), len(want))) if got[i:i + 1] != want[i:i + 1])
            problems.append(f"{lang}/requirements.md: setting markers differ from en at block {i + 1}: "
                            f"{got[i] if i < len(got) else 'none'!r}, en has {want[i] if i < len(want) else 'none'!r}")
        ids = [t.get("id") for t in targets[lang]]
        if ids != en_ids:
            problems.append(f"{lang}/targets.yaml: target ids differ from en "
                            f"({_difference(en_ids, ids) or 'same ids in another order'})")
        for t in targets[lang]:
            diff = t.get("id") in en_params and _difference(en_params[t["id"]], PARAM.findall(t.get("text", "")))
            if diff:
                problems.append(f"{lang}/targets.yaml {t['id']}: parameters differ from en ({diff})")
    return problems


def _rendered_texts(case: NativeCase, lang: str) -> str:
    """requirements.md and the targets of one locale, rendered in every setting."""
    out = []
    for c in case.settings():
        try:
            out += [c.requirements(lang)] + [t.text for t in c.targets(lang)]
        except KeyError:  # reported with the setting's texts
            pass
    return "\n".join(out)


def _data_rows(data_dir: Path) -> list[str]:
    """Every line of the text files and every row of the workbooks in a data folder, lowercased."""
    from openpyxl import load_workbook
    rows = []
    for p in sorted(data_dir.rglob("*")):
        if p.is_file() and p.suffix in DATA_TEXT:
            rows += p.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        elif p.is_file() and p.suffix == ".xlsx":
            wb = load_workbook(p, read_only=True)
            rows += [",".join(str(v) for v in row if v is not None)
                     for ws in wb.worksheets for row in ws.iter_rows(values_only=True)]
            wb.close()
    return [r.lower() for r in rows]


def _name_mismatches(text: str, data_dir: Path) -> list[str]:
    """A "name (ID)" in the texts whose ID's data rows never mention the name (the data calls it something else)."""
    rows = _data_rows(data_dir)
    found = []
    for pattern in (LATIN_NAME, CJK_NAME):
        for name, ident in sorted(set(pattern.findall(text))):
            token = re.compile(rf"(?<![A-Za-z0-9]){ident}(?![A-Za-z0-9])", re.I)
            hits = [r for r in rows if token.search(r)]
            if pattern is LATIN_NAME:
                if name.isupper():  # an acronym (MCU) that the data may spell out
                    continue
                words = [w.lower() for w in name.split() if w.lower() not in ARTICLES and len(w) >= 3]
                if hits and words and not any(words[0] in r for r in hits):
                    found.append(f'the texts call {ident} "{name}", but no data row with {ident} says "{words[0]}"')
            elif any(name[-1] in r for r in hits):  # the data names things of this kind (店, 점), so compare
                if not any(name[i:i + 2] in r for r in hits for i in range(len(name) - 1)):
                    found.append(f'the texts call {ident} "{name}", but no data row with {ident} says so')
    return found


def check_hash_seed(root: Path) -> list[str]:
    """The en data and the default setting's reference are the same in processes with different PYTHONHASHSEED
    (str hashes and set order change between processes, so a generator that uses them is not reproducible)."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in (str(PACKAGE_ROOT), os.environ.get("PYTHONPATH"))
                                                       if p)}
    digests = []
    with tempfile.TemporaryDirectory() as tmp:
        for seed in HASH_SEEDS:
            out = Path(tmp) / seed
            # -P: no cwd on sys.path, so the child imports this package (PYTHONPATH), not a checkout in the cwd
            run = subprocess.run([sys.executable, "-P", "-c", _RENDER, str(Path(root).resolve()), str(out)],
                                 env={**env, "PYTHONHASHSEED": seed}, capture_output=True, text=True, timeout=900)
            if run.returncode:
                return [f"rendering in a fresh process fails: {(run.stderr.strip().splitlines() or ['?'])[-1]}"]
            digests.append({p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(out.rglob("*")) if p.is_file()})
    a, b = digests
    changed = sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))
    if changed:
        return [f"data or reference differs between processes with PYTHONHASHSEED {' and '.join(HASH_SEEDS)} "
                f"({len(changed)} files, e.g. {changed[:3]}): set order or hash() leaks into the output"]
    return []


def check_world_seed(case: NativeCase, seed: int) -> list[str]:
    """The case also works on a world from another seed: every setting's reference is valid at quality 1.0,
    every rule has a clean violating example, and rule sets still lead to different solutions."""
    other = case.with_world_seed(seed)
    problems: list[str] = []
    refs: dict[tuple, Path] = {}
    keep = tempfile.TemporaryDirectory()
    try:
        for c in other.settings():
            at = f"[seed {seed}{' ' + c.setting.label if c.tiers else ''}] "
            ref = Path(keep.name) / f"ref_{c.tier}_{c.ruleset}"
            ref.mkdir()
            try:
                c.write_reference(ref)
                res = c.evaluate(ref, "en")
                examples = c.violating_examples()
            except Exception as e:  # a generator that cannot handle this seed
                problems.append(f"{at}fails: {e!r}"[:400])
                continue
            refs[(c.tier, c.ruleset)] = ref
            if res["validity_score"] != 1.0 or abs(res["quality_score"] - 1.0) > 1e-9:
                problems.append(f"{at}reference scores {res.get('error_info') or res['quality_score']}")
            for rule_id in [r.id for r in c.rules().rules]:
                if rule_id not in examples:
                    problems.append(f"{at}rule {rule_id}: no violating example")
            for rule_id, make in examples.items():
                ex = ref.parent / f"viol_{c.tier}_{c.ruleset}_{rule_id}"
                ex.mkdir()
                make(ex)
                broken = {v["rule"] for v in c.evaluate(ex, "en")["violations"]}
                if broken != {rule_id}:
                    problems.append(f"{at}rule {rule_id}: example breaks {sorted(broken)}")
        for tier in other.tiers:
            for x in other.rulesets:
                for y in other.rulesets:
                    if x != y and (tier, x) in refs:
                        res = other.at(tier, y).evaluate(refs[(tier, x)], "en")
                        if res["validity_score"] == 1.0 and res["quality_ratio"] > 1.0 - DISTINCT_MARGIN:
                            problems.append(f"[seed {seed} {tier}] rule sets {x} and {y} give the same solution")
    finally:
        keep.cleanup()
    return problems


def _scores_as_reference(case: NativeCase, submission: Path) -> bool:
    res = case.evaluate(submission, "en")
    return res["validity_score"] == 1.0 and abs(res["quality_score"] - 1.0) <= 1e-9


def validate_case(root: Path, world_seeds: list[int] = ()) -> list[str]:
    """The problems that fail the case (check_case also returns its warnings and notes)."""
    return check_case(root, world_seeds).problems


def check_case(root: Path, world_seeds: list[int] = ()) -> Report:
    report = Report()
    problems, warnings = report.problems, report.warnings
    case = NativeCase(root)
    meta = case.meta
    problems += [f"case.yaml: missing {k}" for k in REQUIRED_META if k not in meta]
    if meta.get("id") != root.name:
        problems.append(f"case.yaml id {meta.get('id')!r} != directory name {root.name!r}")
    if meta.get("field") != root.parent.name:
        problems.append(f"case.yaml field {meta.get('field')!r} != parent directory {root.parent.name!r}")
    if meta.get("field") not in load_fields(root.parent.parent):
        problems.append(f"field {meta.get('field')!r} is not listed in cases/fields.yaml")
    problems += _todos(case.root)
    kind = meta.get("deliverable_type", "batch")
    if kind == "batch" and not meta.get("deliverables"):
        problems.append("case.yaml: batch cases need deliverables")
    elif kind == "program":
        entry = str(meta.get("entrypoint", ""))
        if not re.fullmatch(r"[A-Za-z0-9_./-]+\.py:[A-Za-z_][A-Za-z0-9_]*", entry):
            problems.append("case.yaml: program cases need entrypoint 'file.py:function'")
        if getattr(case.module, "ENTRYPOINT", entry) != entry:
            problems.append("case.py ENTRYPOINT differs from case.yaml entrypoint")
    elif kind not in ("batch", "program"):
        problems.append("case.yaml: deliverable_type must be batch or program")
    if meta.get("objective") not in ("minimize", "maximize"):
        problems.append("case.yaml: objective must be minimize or maximize")
    tiers, rulesets = case.tiers, case.rulesets
    if meta.get("tiers") and set(meta["tiers"]) - set(TIERS):
        problems.append(f"case.yaml: tiers must be among {TIERS}")
    if meta.get("rulesets") and set(meta["rulesets"]) - set(RULESETS):
        problems.append(f"case.yaml: rulesets must be among {RULESETS}")
    if tiers and (len(tiers) != 3 or len(rulesets) != 3):
        problems.append("case.yaml: a case with settings declares all three tiers and all three rule sets")
    if rulesets and len({tuple(sorted((meta["rulesets"][r] or {}).items(), key=str)) for r in rulesets}) < len(rulesets):
        problems.append("case.yaml: two rule sets have the same parameters")
    params = set().union(*[(meta["rulesets"][r] or {}).keys() for r in rulesets]) if rulesets else set()

    def bad_tiers(names) -> bool:
        return not tiers or not set(names) <= set(tiers)

    def bad_rulesets(names) -> bool:
        return not rulesets or not set(names) <= set(rulesets)

    for r in meta.get("rules", []):
        if "tiers" in r and bad_tiers(r["tiers"]):
            problems.append(f"rule {r.get('id')}: tiers {r['tiers']} are not declared in case.yaml")
        if "rulesets" in r and bad_rulesets(r["rulesets"]):
            problems.append(f"rule {r.get('id')}: rulesets {r['rulesets']} are not declared in case.yaml")
        if r.get("class") not in RULE_CLASSES:
            problems.append(f"rule {r.get('id')}: class must be one of {RULE_CLASSES}")
        if not r.get("description"):
            problems.append(f"rule {r.get('id')}: needs a description")

    # ── texts ────────────────────────────────────────────────────────────────
    requirements_by_lang, targets_by_lang = {}, {}
    for lang in LOCALES:
        d = root / "locales" / lang
        for name in ("request.md", "requirements.md", "targets.yaml"):
            if not (d / name).is_file():
                problems.append(f"{lang}: missing {name}")
        if problems and any(p.startswith(f"{lang}: missing") for p in problems):
            continue
        for name in ("request.md", "requirements.md"):
            body = (d / name).read_text(encoding="utf-8")
            why = _script_problem(body, lang)
            if why:
                problems.append(f"{lang}/{name}: {why}")
            for marker, bad in (("tier", bad_tiers), ("ruleset", bad_rulesets)):
                opened = re.findall(rf"<!-- {marker}: ([A-Za-z ]+) -->", body)
                if len(opened) != body.count(f"<!-- /{marker} -->"):
                    problems.append(f"{lang}/{name}: unbalanced {marker} markers")
                if any(bad(o.split()) for o in opened):
                    problems.append(f"{lang}/{name}: {marker} markers name undeclared {marker}s")
            unknown = set(PARAM.findall(body)) - params
            if unknown:
                problems.append(f"{lang}/{name}: unknown parameters {sorted(unknown)}")
            if name == "request.md" and ("<!--" in body or PARAM.search(body)):
                problems.append(f"{lang}/request.md: must be the same in every setting (no markers or parameters)")
            if name == "requirements.md":
                requirements_by_lang[lang] = body
        targets = yaml.safe_load((d / "targets.yaml").read_text(encoding="utf-8")) or []
        targets_by_lang[lang] = targets
        for t in targets:
            why = _script_problem(t.get("text", ""), lang)
            if why:
                problems.append(f"{lang}/targets.yaml {t.get('id')}: {why}")
            if lang == "en" and (not t.get("kind") or not t.get("domain")):
                problems.append(f"en/targets.yaml {t.get('id')}: needs kind and domain")
            if lang == "en" and "tiers" in t and bad_tiers(t["tiers"]):
                problems.append(f"en/targets.yaml {t.get('id')}: tiers {t['tiers']} are not declared")
            if lang == "en" and "rulesets" in t and bad_rulesets(t["rulesets"]):
                problems.append(f"en/targets.yaml {t.get('id')}: rulesets {t['rulesets']} are not declared")
            unknown = set(PARAM.findall(t.get("text", ""))) - params
            if unknown:
                problems.append(f"{lang}/targets.yaml {t.get('id')}: unknown parameters {sorted(unknown)}")
    if "en" in targets_by_lang:
        problems += _locale_parity(requirements_by_lang, targets_by_lang)
    if problems:
        return report

    # ── data: one world for every setting ───────────────────────────────────
    shapes = {}
    with tempfile.TemporaryDirectory() as tmp:
        # Render every locale twice, more than a second apart, so time-stamped output cannot pass.
        for lang in LOCALES:
            case.materialize_data(lang, Path(tmp) / lang / "a")
        time.sleep(1.1)
        for lang in LOCALES:
            a, b = Path(tmp) / lang / "a", Path(tmp) / lang / "b"
            case.materialize_data(lang, b)
            if _tree_digest(a) != _tree_digest(b):
                problems.append(f"{lang}: data is not deterministic")
            files = sorted(p for p in a.rglob("*") if p.is_file())
            if not files:
                problems.append(f"{lang}: no data files")
            shapes[lang] = sorted((p.suffix, p.stat().st_size > 0) for p in files)
            if lang in ("en", "es"):
                # content_dirs (case.yaml): folders whose files are the client's multilingual content (e.g. a
                # book corpus), not labels, so they may hold any script.
                content = tuple(str(d).strip("/") + "/" for d in meta.get("content_dirs", []))
                for p in files:
                    if p.relative_to(a).as_posix().startswith(content) and content:
                        continue
                    if p.suffix in (".csv", ".json", ".md", ".txt") and (HAN.search(p.read_text(encoding="utf-8-sig"))
                                                                          or HANGUL.search(p.read_text(encoding="utf-8-sig"))):
                        problems.append(f"{lang}: {p.name} contains CJK labels")
                    if HAN.search(p.name) or HANGUL.search(p.name) or KANA.search(p.name):
                        problems.append(f"{lang}: file name {p.name} is not localized")
            warnings += [f"{lang}: {w}" for w in _name_mismatches(_rendered_texts(case, lang), a)]
        if len({tuple(v) for v in shapes.values()}) > 1:
            problems.append("data file sets differ in shape across locales")
    problems += check_hash_seed(root)

    # ── scoring, in every setting ───────────────────────────────────────────
    refs: dict[tuple, Path] = {}
    keep = tempfile.TemporaryDirectory()
    baseline = getattr(case.module, "baseline_solution", None)
    if baseline is None:
        (problems if BASELINE_REQUIRED else warnings).append(
            "case.py has no baseline_solution (the simplest sensible valid deliverable)")
    ratios, unstated, close = [], {}, []
    # Numbers the agent meets in the data or at run time (a dated notice in the hidden inputs) count as stated,
    # from 10 up: small numbers are everywhere in data and would hide a rule that says 2 where the text says 6.
    # Each row is read whole (1,200 in a text) and as cells (a CSV's ,120,).
    in_data = {x for d in (root / "dataset" / "visible" / "en", root / "dataset" / "hidden") if d.is_dir()
               for row in _data_rows(d) for text in (row, re.sub(r"[,;\t|]", " ", row))
               for x in (float(n.replace(",", "")) for n in NUMBER.findall(text)) if x >= 10}
    broken_baseline = False
    try:
        case.quality_cap
    except ValueError as e:
        problems.append(f"case.yaml: {e}")
    for c in case.settings():
        at = f"[{c.setting.label}] " if c.tiers else ""
        try:
            c.requirements("en"), c.targets("en"), c.rules()
        except KeyError as e:
            problems.append(f"{at}texts: {e}")
            continue
        # A number in a rule (dates and clock times aside) should be one the client can actually tell the agent.
        stated = {float(n.replace(",", "")) for n in NUMBER.findall(c.requirements("en"))} | in_data
        for rule in c.rules().rules:
            missing = [n for n in NUMBER.findall(DATE_OR_TIME.sub(" ", rule.description))
                       if float(n.replace(",", "")) not in stated]
            if missing:
                unstated.setdefault((rule.id, tuple(dict.fromkeys(missing))), []).append(c)
        with tempfile.TemporaryDirectory() as tmp:
            # The baseline first: every evaluation of a valid submission scores against it.
            if baseline is not None:
                base_dir = Path(tmp) / "baseline"
                base_dir.mkdir()
                try:
                    baseline(c.world, base_dir, *((c.setting,) if c.tiers else ()))
                    res = c.raw_score(base_dir)
                except Exception as e:
                    res = {"fatal": f"baseline_solution fails: {e!r}"[:400]}
                if "fatal" in res or res["violations"]:
                    problems.append(f"{at}the baseline is not valid: "
                                    f"{res.get('fatal') or sorted({r for r, _ in res['violations']})}")
                    broken_baseline = True
                    continue
                base_obj = res["objective"]
            ref_dir = Path(keep.name) / f"ref_{c.tier}_{c.ruleset}"
            ref_dir.mkdir()
            c.write_reference(ref_dir)
            refs[(c.tier, c.ruleset)] = ref_dir
            first = c.evaluate(ref_dir, "en")
            if first["validity_score"] != 1.0 or abs(first["quality_score"] - 1.0) > 1e-9:
                problems.append(f"{at}reference solution scores {first}")
            if c.evaluate(ref_dir, "en").get("objective") != first.get("objective"):
                problems.append(at + "scoring is not deterministic (two evaluations of the reference differ)")
            if kind == "program" and not (ref_dir / "program").is_dir():
                problems.append(at + "program case: reference_solution must write program/")
            empty = Path(tmp) / "empty"
            empty.mkdir()
            if c.evaluate(empty, "en")["validity_score"] != 0.0:
                problems.append(at + "an empty submission is valid")
            if baseline is not None and first["validity_score"] == 1.0:
                ref = c.reference_objective
                if (base_obj >= ref) if meta.get("objective") == "maximize" else (base_obj <= ref):
                    problems.append(f"{at}the baseline ({base_obj}) is not worse than the reference ({ref})")
                else:
                    ratio = f"{base_obj / ref:.3f}" if ref else "n/a (reference 0)"
                    ratios.append(f"{c.setting.label} {ratio}" if c.tiers else ratio)
                    if abs(ref - base_obj) < BASELINE_MIN_GAP * abs(ref):
                        close.append(c.setting.label if c.tiers else "the case")
            examples = c.violating_examples()
            for rule_id in [r.id for r in c.rules().rules]:
                if rule_id not in examples:
                    problems.append(f"{at}rule {rule_id}: no violating example")
            for rule_id, make in examples.items():
                ex = Path(tmp) / f"viol_{rule_id}"
                ex.mkdir()
                make(ex)
                res = c.evaluate(ex, "en")
                broken = {v["rule"] for v in res["violations"]}
                if rule_id not in broken:
                    problems.append(f"{at}rule {rule_id}: its example does not violate it (got {sorted(broken)})")
                elif broken != {rule_id}:
                    problems.append(f"{at}rule {rule_id}: its example also violates {sorted(broken - {rule_id})}")
                rule = c.rules().by_id(rule_id)
                if rule and rule.rule_class != "physical":
                    relaxed = c.evaluate(ex, "en", relaxed=frozenset({rule_id}))
                    if relaxed["validity_score"] != 1.0:
                        problems.append(f"{at}rule {rule_id}: example still invalid when the rule is relaxed: {relaxed}")
    if ratios:
        report.notes.append("baseline/reference objective: " + ", ".join(ratios))
    if close:
        report.notes.append(f"baseline within {BASELINE_MIN_GAP:.0%} of the reference in {', '.join(close)}: "
                            f"quality's zero point sits {BASELINE_MIN_GAP:.0%} from the reference there")
    for (rule_id, numbers), where in unstated.items():
        at = f"[{where[0].setting.label}{f' and {len(where) - 1} more' if len(where) > 1 else ''}] " if tiers else ""
        warnings.append(f"{at}rule {rule_id}: its description says {', '.join(numbers)}, "
                        f"which neither en/requirements.md nor the data ever says")

    if broken_baseline:  # every further evaluation would fail on the baseline
        keep.cleanup()
        return report

    # ── rule sets are different ground truths ───────────────────────────────
    for tier in tiers:
        for x in rulesets:
            for y in rulesets:
                if x == y or (tier, x) not in refs:
                    continue
                res = case.at(tier, y).evaluate(refs[(tier, x)], "en")
                if res["validity_score"] == 1.0 and res["quality_ratio"] > 1.0 - DISTINCT_MARGIN:
                    problems.append(f"[{tier}] rule set {x}'s reference scores {res['quality_ratio']:.4f} under "
                                    f"rule set {y}: the two rule sets do not lead to different solutions")

    # ── tiers add signal: two tiers with the same answer test the same thing ─
    for i, low in enumerate(tiers):
        for high in tiers[i + 1:]:
            same, scored = [], []
            for r in rulesets:
                if (low, r) not in refs or (high, r) not in refs:
                    continue
                if _tree_digest(refs[(low, r)]) == _tree_digest(refs[(high, r)]):
                    same.append(r)
                elif (_scores_as_reference(case.at(high, r), refs[(low, r)])
                      and _scores_as_reference(case.at(low, r), refs[(high, r)])):
                    scored.append(r)
            if same:
                warnings.append(f"[{low} vs {high}] the references are byte-identical in rule set(s) "
                                f"{', '.join(same)}: the tier adds no signal")
            if scored:
                warnings.append(f"[{low} vs {high}] each reference scores as the other tier's reference in rule "
                                f"set(s) {', '.join(scored)}: the tier adds no signal")
    keep.cleanup()

    # ── the stored dataset matches the generator ────────────────────────────
    if not problems:
        from .dataset import check_dataset
        from .explain import check_page
        problems += check_dataset(root)
        problems += check_page(root)

    # ── optional: other worlds (contamination-resistant runs use private seeds) ──
    for seed in world_seeds:
        problems += check_world_seed(case, seed)

    # ── the agent sees the same thing in every setting ──────────────────────
    if tiers:
        views = {}
        for c in case.settings():
            views[c.setting.label] = agent_view(c)
        if len(set(views.values())) > 1:
            problems.append(f"the agent's view differs between settings: {sorted(views)} -> "
                            f"{len(set(views.values()))} distinct views")
    problems += _translations(case)     # last, so a missing translation never hides the other checks
    return report


def agent_view(case: NativeCase, lang: str = "en") -> str:
    """Digest of everything an agent is shown in the default engagement: prompt text and workspace files."""
    from .prompts import render_task_prompt
    from .transforms.language import Translator
    from .transforms.variant import VariantSpec, build_variant

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "workspace"
        spec = VariantSpec(case.id, customer_locale=lang, agent_locale=lang, difficulty=case.tier or "medium",
                           ruleset=case.ruleset or "A")
        variant = build_variant(spec, case, ws, Translator(None, Path(tmp) / "cache"))
        files = sorted(p.relative_to(ws).as_posix() for p in (ws / "data").rglob("*") if p.is_file())
        system, user = render_task_prompt(variant, "/workspace", files)
        h = hashlib.sha256((system + "\n" + user).encode())
        h.update(_tree_digest(ws).encode())
        return h.hexdigest()
