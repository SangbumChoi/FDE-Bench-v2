"""Data noise for the hard tier, applied only to the agent's copy of the data.

Every op is *recoverable*: the evaluator keeps scoring against the case's
ground truth, and the customer knows the fact that undoes the noise (it is appended to
the hidden requirements and registered as a new clarification target). So a
noisy variant measures whether the agent notices and asks, not whether it can
read minds.

Ops edit files at the cell level so nothing but the injected noise changes, and
prefer the smallest eligible file so building a variant stays fast. An op that
finds no eligible file in a case is skipped and the variant records which ops
actually applied.
"""

from __future__ import annotations

import csv
import io
import json
import random
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .events import msg

MAX_CSV_BYTES = 50 * 1024 * 1024
MAX_XLSX_BYTES = 5 * 1024 * 1024     # openpyxl loads whole workbooks; bigger ones take minutes
MAX_JSON_BYTES = 20 * 1024 * 1024
MAX_SHEET_ROWS = 200_000             # sheets padded to Excel's row limit are formatting, not data
MIN_ROWS = 10


@dataclass
class NoiseResult:
    op: str
    files: list[str] = field(default_factory=list)   # workspace-relative paths touched or added
    knowledge: dict[str, Any] | None = None           # msg: fact the customer now knows
    target: dict[str, Any] | None = None              # msg: clarification target (None = none)


DUP_FACT = ("Our export tool sometimes writes the same record twice. Exact duplicate rows in `{file}` are export "
            "errors and must be removed before use; they are not real records.")
DUP_TARGET = "Exact duplicate rows in `{file}` are export artefacts and must be deduplicated."
STALE_FACT = "`{old}` is an outdated backup someone left in the folder. Only `{file}` is current; ignore the backup entirely."
STALE_TARGET = "`{old}` is a stale backup; only `{file}` is authoritative."
ENCODING_FACT = "`{file}` comes from our old ERP, which exports {encoding}, not UTF-8."
LEGACY_ENCODING = {"zh": "GB18030", "ko": "CP949", "ja": "Shift_JIS", "en": "CP1252", "es": "CP1252"}


# ── file helpers ─────────────────────────────────────────────────────────────

def _read_csv(path: Path) -> tuple[list[list[str]], str, csv.Dialect]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "cp949", "shift_jis", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"cannot decode {path}")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect)), enc, dialect


def _write_csv(path: Path, rows: list[list[str]], enc: str, dialect: csv.Dialect) -> None:
    buf = io.StringIO()
    csv.writer(buf, dialect, lineterminator="\n").writerows(rows)
    path.write_bytes(buf.getvalue().encode(enc))


def _data_sheet(wb):
    """The sheet with the most rows, ignoring sheets padded beyond MAX_SHEET_ROWS."""
    sheets = [ws for ws in wb.worksheets if 1 < ws.max_row <= MAX_SHEET_ROWS]
    return max(sheets, key=lambda ws: ws.max_row) if sheets else None


def _is_number(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    try:
        float(str(v))
        return str(v).strip() != ""
    except ValueError:
        return False


def _scale(v: float | int, rng: random.Random) -> float | int:
    out = v * rng.uniform(0.7, 1.3)
    return round(out) if isinstance(v, int) else round(out, 4)


def candidates(data_dir: Path, kinds: tuple[str, ...] = (".csv", ".xlsx")) -> list[Path]:
    caps = {".csv": MAX_CSV_BYTES, ".xlsx": MAX_XLSX_BYTES, ".json": MAX_JSON_BYTES}
    files = [p for p in data_dir.rglob("*")
             if p.is_file() and p.suffix.lower() in kinds and p.stat().st_size <= caps[p.suffix.lower()]]
    return sorted(files, key=lambda p: (p.stat().st_size, p.as_posix()))


# ── ops ──────────────────────────────────────────────────────────────────────

def duplicate_rows(workspace: Path, rng: random.Random, lang: str = "zh", frac: float = 0.03) -> NoiseResult | None:
    """Re-insert a few exact copies of existing rows, as a flaky export would."""
    for path in candidates(workspace / "data"):
        rel = path.relative_to(workspace).as_posix()
        if path.suffix.lower() == ".csv":
            rows, enc, dialect = _read_csv(path)
            header, body = rows[:1], rows[1:]
            if len(body) < MIN_ROWS or len({tuple(r) for r in body}) != len(body):
                continue  # the data already has exact duplicates: deduplicating would be wrong
            picks = set(rng.sample(range(len(body)), k=max(1, min(200, int(len(body) * frac)))))
            out = []
            for i, r in enumerate(body):
                out.append(r)
                if i in picks:
                    out.append(list(r))
            _write_csv(path, header + out, enc, dialect)
        else:
            from openpyxl import load_workbook
            wb = load_workbook(path)
            ws = _data_sheet(wb)
            if ws is None:
                continue
            body = [tuple(c.value for c in row) for row in ws.iter_rows(min_row=2)]
            body = [r for r in body if any(v is not None for v in r)]
            if len(body) < MIN_ROWS or len(set(body)) != len(body):
                continue
            for i in rng.sample(range(len(body)), k=max(1, min(200, int(len(body) * frac)))):
                ws.append(list(body[i]))
            wb.save(path)
        return NoiseResult(
            op="duplicate_rows", files=[rel],
            knowledge=msg(DUP_FACT, file=rel), target=msg(DUP_TARGET, file=rel),
        )
    return None


def _perturb_json(node: Any, rng: random.Random, share: float) -> tuple[Any, int]:
    if isinstance(node, dict):
        changed = 0
        for k, v in node.items():
            node[k], c = _perturb_json(v, rng, share)
            changed += c
        return node, changed
    if isinstance(node, list):
        changed = 0
        for i, v in enumerate(node):
            node[i], c = _perturb_json(v, rng, share)
            changed += c
        return node, changed
    # Small integers are usually flags, indices or counts that identify things; leave them alone.
    if _is_number(node) and not isinstance(node, str) and (isinstance(node, float) or abs(node) >= 10):
        if rng.random() < share:
            return _scale(node, rng), 1
    return node, 0


def _perturb(path: Path, dest: Path, rng: random.Random, share: float = 0.15) -> int:
    """Copy `path` to `dest`, scaling a share of numeric cells by 0.7-1.3. Returns cells changed."""
    changed = 0
    suffix = path.suffix.lower()
    if suffix == ".csv":
        rows, enc, dialect = _read_csv(path)
        for r in rows[1:]:
            for j, v in enumerate(r):
                if _is_number(v) and rng.random() < share:
                    r[j] = f"{float(v) * rng.uniform(0.7, 1.3):.4g}"
                    changed += 1
        _write_csv(dest, rows, enc, dialect)
    elif suffix == ".json":
        doc, changed = _perturb_json(json.loads(path.read_text(encoding="utf-8")), rng, share)
        dest.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        from openpyxl import load_workbook
        wb = load_workbook(path)
        ws = _data_sheet(wb)
        if ws is not None:
            for row in ws.iter_rows(min_row=2):
                for c in row:
                    if isinstance(c.value, (int, float)) and not isinstance(c.value, bool) and rng.random() < share:
                        c.value = _scale(c.value, rng)
                        changed += 1
        wb.save(dest)
    return changed


_PERTURBABLE = (".csv", ".xlsx", ".json")


def stale_copy(workspace: Path, rng: random.Random, lang: str = "zh") -> NoiseResult | None:
    """Leave an outdated, plausible-looking copy of a data file next to the real one."""
    for path in candidates(workspace / "data", _PERTURBABLE):
        dest = path.with_name(f"{path.stem}_backup_old{path.suffix}")
        if dest.exists() or _perturb(path, dest, rng) == 0:
            dest.unlink(missing_ok=True)
            continue
        rel, rel_old = path.relative_to(workspace).as_posix(), dest.relative_to(workspace).as_posix()
        return NoiseResult(
            op="stale_copy", files=[rel_old],
            knowledge=msg(STALE_FACT, old=rel_old, file=rel), target=msg(STALE_TARGET, old=rel_old, file=rel),
        )
    return None


def legacy_encoding(workspace: Path, rng: random.Random, lang: str = "zh") -> NoiseResult | None:
    """Re-encode a UTF-8 CSV with non-ASCII text in the locale's legacy code page, like an old ERP export."""
    encoding = LEGACY_ENCODING[lang]
    for path in candidates(workspace / "data", (".csv",)):
        try:
            text = path.read_bytes().decode("utf-8-sig")
            if text.isascii():
                continue
            data = text.encode(encoding)
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue  # not representable in that code page: try another file
        path.write_bytes(data)
        rel = path.relative_to(workspace).as_posix()
        return NoiseResult(op="legacy_encoding", files=[rel], knowledge=msg(ENCODING_FACT, file=rel, encoding=encoding))
    return None


def corrupt_for_correction(workspace: Path, rng: random.Random) -> tuple[str, Path] | None:
    """Swap one data file for a wrong version; the pristine file is kept for a later correction event.

    Returns (workspace-relative path, path of the pristine copy held back from the agent).
    """
    held = workspace.parent / "held_back"
    for path in candidates(workspace / "data", _PERTURBABLE):
        rel = path.relative_to(workspace).as_posix()
        keep = held / rel
        keep.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, keep)
        if _perturb(keep, path, rng, share=0.05) == 0:
            shutil.copy2(keep, path)
            keep.unlink()
            continue
        return rel, keep
    return None


OPS = {
    "duplicate_rows": duplicate_rows,
    "stale_copy": stale_copy,
    "legacy_encoding": legacy_encoding,
}
