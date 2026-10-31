"""Stored datasets: every case's data and ground truth as files in the repository.

Cases are generated from their seed, but a reader should be able to open the
data and the answers without running anything. `fdebench2 export-dataset`
writes, next to case.yaml:

    dataset/
      agent_view/<lang>/...   what the agent receives, per customer locale (identical in every setting)
      hidden/...              inputs the agent never sees: a program case's hidden period or corpus
                              (case.py `write_hidden(world, dir)`, optional)
      gt/<tier>_s<seed>/      one folder per public setting, tier x public rule seed (gt/default/ for a case
                              without settings):
        setting.json          {tier, rule_seed, params: the drawn values}, plus derived: the derive_params
                              values when the case has that hook
        reference/            the reference deliverable (files, or program/)
        score.json            the reference's objective and metrics under this setting; with a case.py
                              `baseline_solution`, also the baseline's objective and both solutions'
                              quality fields (reference_quality, baseline_quality)
        ...                   anything case.py `write_ground_truth(world, dir, setting)` adds
                              (e.g. the expected daily tables or the expected library)
      MANIFEST.json           sha256 of every file above

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

from .cases import LOCALES, NativeCase, quality_fields

DATASET_DIR = "dataset"


def setting_record(case: NativeCase) -> dict:
    """setting.json: {tier, rule_seed, params} with params the drawn values, and derived (the derive_params
    keys) when there are any; {} without settings."""
    s = case.setting
    if s is None:
        return {}
    drawn = case.drawn_params
    derived = {k: v for k, v in s.params.items() if k not in drawn}
    return {"tier": s.tier, "rule_seed": s.rule_seed, "params": drawn, **({"derived": derived} if derived else {})}


def _write(case: NativeCase, out: Path) -> None:
    for lang in LOCALES:
        case.materialize_data(lang, out / "agent_view" / lang)
    hidden = getattr(case.module, "write_hidden", None)
    if hidden is not None:
        (out / "hidden").mkdir(parents=True, exist_ok=True)
        hidden(case.world, out / "hidden")
    extra = getattr(case.module, "write_ground_truth", None)
    for c in case.settings():
        gt = out / "gt" / (c.setting.folder if c.tiers else "default")
        (gt / "reference").mkdir(parents=True)
        c.write_reference(gt / "reference")
        res = c.raw_score(gt / "reference")
        setting = setting_record(c)
        (gt / "setting.json").write_text(json.dumps(setting, ensure_ascii=False, indent=2, sort_keys=True,
                                                    default=str) + "\n", encoding="utf-8")
        score = {"objective": res.get("objective"), "violations": res.get("violations"),
                 "metrics": res.get("metrics", {})}
        if c.baseline_objective is not None:
            ref, base = float(res["objective"]), c.baseline_objective
            maximize = c.meta.get("objective") == "maximize"
            score.update(baseline_objective=base, reference_quality=quality_fields(ref, ref, base, maximize),
                         baseline_quality=quality_fields(base, ref, base, maximize))
        (gt / "score.json").write_text(json.dumps(score, ensure_ascii=False, indent=2, sort_keys=True,
                                                  default=str) + "\n", encoding="utf-8")
        if extra is not None:
            extra(case.world, gt, *( (c.setting,) if c.tiers else () ))
    for p in out.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)


def _manifest(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.name != "MANIFEST.json"}


def export_dataset(case_root: Path) -> Path:
    """(Re)write case_root/dataset/ from the generator."""
    case = NativeCase(Path(case_root))
    dest = case.root / DATASET_DIR
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / DATASET_DIR
        _write(case, out)
        (out / "MANIFEST.json").write_text(json.dumps(_manifest(out), indent=1, sort_keys=True) + "\n",
                                           encoding="utf-8")
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(out, dest)
    return dest


def check_dataset(case_root: Path) -> list[str]:
    """Problems if dataset/ is missing or differs from what the generator produces now."""
    case = NativeCase(Path(case_root))
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
