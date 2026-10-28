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

A case with settings (tiers x rule sets) is checked in every setting (3-5 run
per setting, with that setting's rules and parameters), and also:

6. request.md has no setting markers or parameters, and the agent's whole view
   (prompt and workspace) is byte-identical in every setting;
7. the rule sets are really different ground truths: within a tier, each rule
   set's reference is invalid, or at least 1% worse, under every other rule set;
8. markers, parameters and `tiers:` / `rulesets:` lists only name declared ones.

Every case also stores its data and ground truth in dataset/ (fdebench2.dataset);
the stored files must match what the generator produces now.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import time
from pathlib import Path

import yaml

from .cases import LOCALES, PARAM, RULESETS, TIERS, NativeCase, load_fields
from .transforms.language import detect_locale
from .transforms.policy import RULE_CLASSES

DISTINCT_MARGIN = 0.01
REQUIRED_META = ("id", "role", "field", "task_type", "objective", "seed", "deliverable_spec", "rules")
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
                        if res["validity_score"] == 1.0 and res["quality_score"] > 1.0 - DISTINCT_MARGIN:
                            problems.append(f"[seed {seed} {tier}] rule sets {x} and {y} give the same solution")
    finally:
        keep.cleanup()
    return problems


def validate_case(root: Path, world_seeds: list[int] = ()) -> list[str]:
    problems: list[str] = []
    case = NativeCase(root)
    meta = case.meta
    problems += [f"case.yaml: missing {k}" for k in REQUIRED_META if k not in meta]
    if meta.get("id") != root.name:
        problems.append(f"case.yaml id {meta.get('id')!r} != directory name {root.name!r}")
    if meta.get("field") != root.parent.name:
        problems.append(f"case.yaml field {meta.get('field')!r} != parent directory {root.parent.name!r}")
    if meta.get("field") not in load_fields(root.parent.parent):
        problems.append(f"field {meta.get('field')!r} is not listed in cases/fields.yaml")
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
    ids_by_lang = {}
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
            for kind, bad in (("tier", bad_tiers), ("ruleset", bad_rulesets)):
                opened = re.findall(rf"<!-- {kind}: ([A-Za-z ]+) -->", body)
                if len(opened) != body.count(f"<!-- /{kind} -->"):
                    problems.append(f"{lang}/{name}: unbalanced {kind} markers")
                if any(bad(o.split()) for o in opened):
                    problems.append(f"{lang}/{name}: {kind} markers name undeclared {kind}s")
            unknown = set(PARAM.findall(body)) - params
            if unknown:
                problems.append(f"{lang}/{name}: unknown parameters {sorted(unknown)}")
            if name == "request.md" and ("<!--" in body or PARAM.search(body)):
                problems.append(f"{lang}/request.md: must be the same in every setting (no markers or parameters)")
        targets = yaml.safe_load((d / "targets.yaml").read_text(encoding="utf-8")) or []
        ids_by_lang[lang] = [t.get("id") for t in targets]
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
    if ids_by_lang and len({tuple(v) for v in ids_by_lang.values()}) > 1:
        problems.append(f"target ids differ across locales: {ids_by_lang}")
    if problems:
        return problems

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
        if len({tuple(v) for v in shapes.values()}) > 1:
            problems.append("data file sets differ in shape across locales")

    # ── scoring, in every setting ───────────────────────────────────────────
    refs: dict[tuple, Path] = {}
    keep = tempfile.TemporaryDirectory()
    for c in case.settings():
        at = f"[{c.setting.label}] " if c.tiers else ""
        try:
            c.requirements("en"), c.targets("en"), c.rules()
        except KeyError as e:
            problems.append(f"{at}texts: {e}")
            continue
        with tempfile.TemporaryDirectory() as tmp:
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

    # ── rule sets are different ground truths ───────────────────────────────
    for tier in tiers:
        for x in rulesets:
            for y in rulesets:
                if x == y or (tier, x) not in refs:
                    continue
                res = case.at(tier, y).evaluate(refs[(tier, x)], "en")
                if res["validity_score"] == 1.0 and res["quality_score"] > 1.0 - DISTINCT_MARGIN:
                    problems.append(f"[{tier}] rule set {x}'s reference scores {res['quality_score']:.4f} under "
                                    f"rule set {y}: the two rule sets do not lead to different solutions")
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
    return problems


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
