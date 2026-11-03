"""Stored datasets: every case's data and answers as files in the repository.

Cases are generated from their seed, but a reader should be able to open the
data and the answers without running anything. `fdebench2 export-dataset`
writes, next to case.yaml:

    dataset/
      agent_view/<lang>/...   what the agent receives, per customer locale (identical in every setting)
      hidden/...              inputs the agent never sees: a program case's hidden period or corpus
                              (case.py `write_hidden(world, dir)`, optional)
      answer/                 the answers of the public settings (tier x public rule seed), as tables:
        answers.csv           one row per setting: difficulty, seed, every drawn parameter, the reference's and
                              the baseline's objective, the quality scale's width, the rules and targets in force
                              (ids) and the reference's scalar metrics
        <name>.csv            every CSV the answers hold (the reference deliverable as reference_<file>.csv,
                              the baseline's as baseline_<file>.csv, the case's extra answer tables under their
                              own name), the settings stacked, with difficulty and seed as the first columns
        <name>.jsonl          every JSON file, stacked the same way, one line per setting and file:
                              {difficulty, seed, file, content}, grouped by the folder it lives in
        files/                anything else (a reference program, an expected library): files/<path> when it
                              is the same in every setting, else files/<difficulty>_s<seed>/<path>
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
import csv
import json
import shutil
import tempfile
from pathlib import Path

import yaml

from .cases import LOCALES, NativeCase, NotLocalized, quality_span

DATASET_DIR = "dataset"
AUDIT_FILE = "audit.json"       # dataset/audit.json: written by audit-case, never by export-dataset
ANSWER_DIR = "answer"           # dataset/answer/: answers.csv and the stacked answer files
ANSWERS_CSV = "answers.csv"     # one row per public setting
FILES_DIR = "files"             # dataset/answer/files/: answer files that are neither CSV nor JSON
LEGACY_ANSWER_DIR = "gt"        # dataset/gt/<tier>_s<seed>/, the layout before dataset/answer/
BASELINE_DIR = "baseline"       # the baseline deliverable's prefix (baseline_<file>.csv)


def setting_key(case: NativeCase) -> tuple[str, str]:
    """(difficulty, seed) of a setting's rows: ("easy", "42"); ("default", "") for a case without settings."""
    return (case.setting.tier, str(case.setting.rule_seed)) if case.tiers else ("default", "")


def _cell(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def answer_row(case: NativeCase, res: dict) -> dict:
    """answers.csv's row for a setting: difficulty, seed, the drawn parameters, the objectives, the scale's width,
    the rules and targets in force and the reference's scalar metrics."""
    difficulty, seed = setting_key(case)
    row = {"difficulty": difficulty, "seed": seed}
    row.update({k: _cell(v) for k, v in (case.drawn_params.items() if case.tiers else [])})
    ref, base = res.get("objective"), case.baseline_objective
    row["reference_objective"] = ref
    row["baseline_objective"] = "" if base is None else base
    span = quality_span(float(ref), base) if ref is not None else None
    row["quality_span"] = "" if span is None else span
    row["reference_violations"] = len(res.get("violations") or [])
    row["rules"] = ";".join(r.id for r in case.rules().rules)
    try:
        row["targets"] = ";".join(t.id for t in case.targets(case.source_locale))
    except NotLocalized:
        row["targets"] = ""
    for k, v in (res.get("metrics") or {}).items():
        if isinstance(v, (int, float, str, bool)) or v is None:
            row[f"metric_{k}"] = "" if v is None else v
    return row


def _json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
                    encoding="utf-8")


def _bundle(case: NativeCase, c: NativeCase, extra, dest: Path) -> dict:
    """Write one setting's answer files into dest (reference/, baseline/ and the case's write_ground_truth extras);
    return its answers.csv row."""
    (dest / "reference").mkdir(parents=True)
    c.write_reference(dest / "reference")
    res = c.raw_score(dest / "reference")
    if c.baseline_objective is not None:
        (dest / BASELINE_DIR).mkdir()
        c.write_baseline(dest / BASELINE_DIR)
    if extra is not None:
        extra(case.world, dest, *((c.setting,) if c.tiers else ()))
    return answer_row(c, res)


def _flat(rel: str) -> str:
    return rel.replace("/", "_")


def _pack(bundles: list[tuple[tuple[str, str], Path]], out: Path) -> None:
    """Stack the settings' answer files into out: each CSV path into one CSV with difficulty and seed first, the JSON
    files of each folder into one JSONL, anything else into files/ (once when the same in every setting)."""
    by_rel: dict[str, list[tuple[tuple[str, str], Path]]] = {}
    for key, root in bundles:
        for p in sorted(root.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                by_rel.setdefault(p.relative_to(root).as_posix(), []).append((key, p))
    jsonl: dict[str, list[dict]] = {}
    for rel, items in by_rel.items():
        if rel.endswith(".csv") and _stack_csv(items, out / _flat(rel)):
            continue
        if rel.endswith(".json"):
            parent, name = rel.rpartition("/")[::2]
            group = _flat(parent) if parent else name[:-5]
            for (difficulty, seed), p in items:
                jsonl.setdefault(group, []).append({"difficulty": difficulty, "seed": seed, "file": name,
                                                    "content": json.loads(p.read_text(encoding="utf-8"))})
            continue
        blobs = {p.read_bytes() for _, p in items}
        if len(blobs) == 1 and len(items) == len(bundles):
            target = out / FILES_DIR / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blobs.pop())
            continue
        for (difficulty, seed), p in items:
            target = out / FILES_DIR / (f"{difficulty}_s{seed}" if seed else difficulty) / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(p.read_bytes())
    for group, rows in jsonl.items():
        (out / f"{group}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                                                    for r in rows), encoding="utf-8")


def _stack_csv(items: list[tuple[tuple[str, str], Path]], dest: Path) -> bool:
    """One CSV from the same CSV of every setting, with difficulty and seed first; False when their headers differ
    (the caller then keeps the files apart)."""
    header, rows = None, []
    for (difficulty, seed), p in items:
        with p.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            head = next(reader, [])
            if header is not None and head != header:
                return False
            header = head
            rows += [[difficulty, seed, *r] for r in reader]
    with dest.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["difficulty", "seed", *(header or [])])
        w.writerows(rows)
    return True


def _write_answers(rows: list[dict], dest: Path) -> None:
    columns: list[str] = []
    for r in rows:
        columns += [k for k in r if k not in columns]
    with dest.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n", restval="")
        w.writeheader()
        w.writerows(rows)


def _write(case: NativeCase, out: Path) -> None:
    for lang in LOCALES:
        case.materialize_data(lang, out / "agent_view" / lang)
    hidden = getattr(case.module, "write_hidden", None)
    if hidden is not None:
        (out / "hidden").mkdir(parents=True, exist_ok=True)
        hidden(case.world, out / "hidden")
    extra = getattr(case.module, "write_ground_truth", None)
    rows, bundles = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for i, c in enumerate(case.settings()):
            dest = Path(tmp) / str(i)
            rows.append(_bundle(case, c, extra, dest))
            bundles.append((setting_key(c), dest))
        answer = out / ANSWER_DIR
        answer.mkdir(parents=True)
        _write_answers(rows, answer / ANSWERS_CSV)
        _pack(bundles, answer)
    for p in out.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)


def legacy_answers(case_root: Path) -> list[str]:
    """A dataset/gt/ left from the layout before dataset/answer/, with the layout that replaced it."""
    old = Path(case_root) / DATASET_DIR / LEGACY_ANSWER_DIR
    if not old.exists():
        return []
    return [f"{DATASET_DIR}/{LEGACY_ANSWER_DIR}/: the stored answers are in {DATASET_DIR}/{ANSWER_DIR}/ now "
            f"({ANSWERS_CSV}, one row per setting, and the answer files stacked with difficulty and seed columns): run "
            f"`fdebench2 export-dataset`, which writes them and removes {DATASET_DIR}/{LEGACY_ANSWER_DIR}/"]


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
