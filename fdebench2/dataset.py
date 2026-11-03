"""Stored datasets: every case's data and answers as files in the repository.

Cases are generated from their seed, but a reader should be able to open the
data and the answers without running anything. `fdebench2 export-dataset`
writes, next to case.yaml:

    dataset/
      agent_view/<lang>/...   what the agent receives, per customer locale (identical in every setting)
      hidden/...              inputs the agent never sees: a program case's hidden period or corpus
                              (case.py `write_hidden(world, dir)`, optional)
      answer/                 the answers, one folder per public setting, grouped by tier:
        easy/s<seed>/  ...    one per public rule seed (case.yaml `rule_seeds`), as in the setting label
        medium/s<seed>/ ...   easy/s42; a case without settings has the one folder answer/default/
        hard/s<seed>/  ...
          setting.json        {tier, rule_seed, params: the drawn values}, plus derived: the derive_params
                              values when the case has that hook, rules: the rules in force (id, class and
                              the English description as rendered for the setting) and targets: the ids of
                              the targets in force
          client/<lang>/      what the client knows in this version, in each locale: requirements.md (the
                              hidden requirements rendered for the setting) and targets.yaml (the targets
                              in force: id, kind, domain and the rendered text)
          reference/          the reference deliverable (files, or program/): quality 1
          baseline/           the client's own way without an engineer (case.py `baseline_solution`, when
                              the case has one): quality 0
          score.json          the reference's objective and metrics under this setting; with a baseline,
                              also its objective and both solutions' quality fields (reference_quality,
                              baseline_quality)
          ...                 anything case.py `write_ground_truth(world, dir, setting)` adds
                              (e.g. the expected daily tables or the expected library)
      MANIFEST.json           sha256 of every file above
      audit.json              the ground truth audit (`fdebench2 audit-case`, fdebench2.audit): not part of the
                              manifest, kept when the dataset is exported again, and checked by its own
                              fingerprint

`validate-case` regenerates the dataset and compares it with MANIFEST.json, so
the stored files can never drift from the generator. The dataset is part of
the repository only: the agent's sandbox mounts its workspace, never the case.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import yaml

from .cases import LOCALES, NativeCase, NotLocalized, quality_fields

DATASET_DIR = "dataset"
AUDIT_FILE = "audit.json"       # dataset/audit.json: written by audit-case, never by export-dataset
ANSWER_DIR = "answer"           # dataset/answer/<tier>/s<seed>/ (dataset/answer/default/ without settings)
LEGACY_ANSWER_DIR = "gt"        # dataset/gt/<tier>_s<seed>/, the layout before dataset/answer/
CLIENT_DIR = "client"           # <answer folder>/client/<lang>/{requirements.md, targets.yaml}
BASELINE_DIR = "baseline"       # <answer folder>/baseline/: the baseline deliverable


def answer_folder(case: NativeCase) -> str:
    """A setting's folder in dataset/answer/: "<tier>/s<seed>" (Setting.folder), "default" without settings."""
    return case.setting.folder if case.tiers else "default"


def setting_record(case: NativeCase) -> dict:
    """setting.json: {tier, rule_seed, params} with params the drawn values, and derived (the derive_params
    keys) when there are any (none of them without settings); then rules, the rules in force with their class
    and English description as rendered for the setting, and targets, the ids of the targets in force."""
    s = case.setting
    out: dict = {}
    if s is not None:
        drawn = case.drawn_params
        derived = {k: v for k, v in s.params.items() if k not in drawn}
        out = {"tier": s.tier, "rule_seed": s.rule_seed, "params": drawn, **({"derived": derived} if derived else {})}
    out["rules"] = [{"id": r.id, "class": r.rule_class, "description": r.description} for r in case.rules().rules]
    try:
        out["targets"] = [t.id for t in case.targets(case.source_locale)]
    except NotLocalized:
        out["targets"] = []
    return out


def client_texts(case: NativeCase, lang: str) -> dict[str, str] | None:
    """What the client knows in this setting, in `lang`: {"requirements.md": the hidden requirements rendered for
    the setting, "targets.yaml": the targets in force (id, kind, domain, rendered text)}; None when the case has no
    such texts in that locale."""
    try:
        requirements = case.requirements(lang)
        targets = [{"id": t.id, "kind": t.kind, "domain": t.domain, "text": t.text} for t in case.targets(lang)]
    except NotLocalized:
        return None
    return {"requirements.md": requirements + "\n",
            "targets.yaml": yaml.safe_dump(targets, allow_unicode=True, sort_keys=False, width=100)}


def _json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
                    encoding="utf-8")


def _write(case: NativeCase, out: Path) -> None:
    for lang in LOCALES:
        case.materialize_data(lang, out / "agent_view" / lang)
    hidden = getattr(case.module, "write_hidden", None)
    if hidden is not None:
        (out / "hidden").mkdir(parents=True, exist_ok=True)
        hidden(case.world, out / "hidden")
    extra = getattr(case.module, "write_ground_truth", None)
    for c in case.settings():
        answer = out / ANSWER_DIR / answer_folder(c)
        (answer / "reference").mkdir(parents=True)
        c.write_reference(answer / "reference")
        res = c.raw_score(answer / "reference")
        _json(answer / "setting.json", setting_record(c))
        for lang in LOCALES:
            texts = client_texts(c, lang)
            if texts is not None:
                (answer / CLIENT_DIR / lang).mkdir(parents=True)
                for name, text in texts.items():
                    (answer / CLIENT_DIR / lang / name).write_text(text, encoding="utf-8")
        score = {"objective": res.get("objective"), "violations": res.get("violations"),
                 "metrics": res.get("metrics", {})}
        if c.baseline_objective is not None:
            (answer / BASELINE_DIR).mkdir()
            c.write_baseline(answer / BASELINE_DIR)
            ref, base = float(res["objective"]), c.baseline_objective
            maximize = c.meta.get("objective") == "maximize"
            score.update(baseline_objective=base, reference_quality=quality_fields(ref, ref, base, maximize),
                         baseline_quality=quality_fields(base, ref, base, maximize))
        _json(answer / "score.json", score)
        if extra is not None:
            extra(case.world, answer, *( (c.setting,) if c.tiers else () ))
    for p in out.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)


def legacy_answers(case_root: Path) -> list[str]:
    """A dataset/gt/ left from the layout before dataset/answer/, with the layout that replaced it."""
    old = Path(case_root) / DATASET_DIR / LEGACY_ANSWER_DIR
    if not old.exists():
        return []
    return [f"{DATASET_DIR}/{LEGACY_ANSWER_DIR}/: the stored answers are in {DATASET_DIR}/{ANSWER_DIR}/<tier>/s<seed>/ "
            f"now ({DATASET_DIR}/{ANSWER_DIR}/default/ without settings), each with setting.json, "
            f"{CLIENT_DIR}/<lang>/, reference/, {BASELINE_DIR}/ and score.json: run `fdebench2 export-dataset`, which "
            f"writes them and removes {DATASET_DIR}/{LEGACY_ANSWER_DIR}/"]


def _manifest(root: Path) -> dict[str, str]:
    """sha256 of every generated file (not MANIFEST.json itself, nor the audit, which has its own fingerprint)."""
    return {rel: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*"))
            if p.is_file() and (rel := p.relative_to(root).as_posix()) not in ("MANIFEST.json", AUDIT_FILE)}


def export_dataset(case_root: Path) -> Path:
    """(Re)write case_root/dataset/ from the generator, keeping a stored audit (too slow to run here)."""
    case = NativeCase(Path(case_root))
    dest = case.root / DATASET_DIR
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / DATASET_DIR
        _write(case, out)
        (out / "MANIFEST.json").write_text(json.dumps(_manifest(out), indent=1, sort_keys=True) + "\n",
                                           encoding="utf-8")
        if (dest / AUDIT_FILE).is_file():
            shutil.copy2(dest / AUDIT_FILE, out / AUDIT_FILE)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(out, dest)
    return dest


def check_dataset(case_root: Path) -> list[str]:
    """Problems if dataset/ is missing or differs from what the generator produces now."""
    case = NativeCase(Path(case_root))
    legacy = legacy_answers(case.root)
    if legacy:
        return legacy
    stored = case.root / DATASET_DIR / "MANIFEST.json"
    if not stored.is_file():
        return ["dataset/ is missing: run `fdebench2 export-dataset` for this case"]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / DATASET_DIR
        _write(case, out)
        fresh = _manifest(out)
    old = json.loads(stored.read_text(encoding="utf-8"))
    on_disk = _manifest(case.root / DATASET_DIR)
    problems = []
    if old != fresh:
        changed = sorted(k for k in set(old) | set(fresh) if old.get(k) != fresh.get(k))
        problems.append(f"dataset/ is out of date ({len(changed)} files differ, e.g. {changed[:3]}): "
                        f"run `fdebench2 export-dataset`")
    elif on_disk != old:
        changed = sorted(k for k in set(old) | set(on_disk) if old.get(k) != on_disk.get(k))
        problems.append(f"dataset/ files were edited by hand ({changed[:3]}): run `fdebench2 export-dataset`")
    return problems
