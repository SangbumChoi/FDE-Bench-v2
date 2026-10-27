"""Helpers for writing native cases (cases/<id>/case.py).

Conventions every case follows, so the benchmark stays language-independent:
  - The world (entities, ground truth, hidden future) is built from a seed,
    never from the data files, and never depends on the locale.
  - Data files render the world in one locale: localized file names, sheet
    names, column headers and categorical labels; IDs and numbers unchanged.
  - Deliverables use ASCII keys and the IDs that appear in the data, so one
    evaluator scores submissions made in any locale.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

LOCALES = ("zh", "en", "ko", "ja", "es")


class Fatal(Exception):
    """The submission cannot be scored at all (missing file, unparseable, wrong shape)."""


def run_program(submission_dir: Path, entry: str, inputs: list[Any], *, per_call_timeout: float = 5.0,
                total_timeout: float = 600.0, input_dir: Path | None = None, output_to: Path | None = None):
    """Program cases: call the delivered `entry` ("file.py:function") once per hidden input, in order.

    The program runs isolated from the scorer (see fdebench2.program). Returns a ProgramResult whose
    `outputs[i]` is None where `errors[i]` is set; a program that cannot load at all raises Fatal.
    Per-input failures are the case's to score (usually as a wrong or default answer).
    """
    from .program import run_program as _run

    prog = Path(submission_dir) / "program"
    if not prog.is_dir():
        raise Fatal("missing program/ directory")
    res = _run(prog, entry, inputs, per_call_timeout=per_call_timeout, total_timeout=total_timeout,
               input_dir=input_dir, output_to=output_to)
    if not res.loaded:
        raise Fatal(f"program failed to load: {res.load_error}")
    return res


class program_session:
    """Program cases whose next input depends on earlier outputs: a ProgramSession on submission/program/.

        with casekit.program_session(submission_dir, ENTRYPOINT, per_call_timeout=2) as prog:
            output, error = prog.call(x)

    A missing program/ directory or a program that cannot load raises Fatal.
    """

    def __init__(self, submission_dir: Path, entry: str, **kw: Any):
        from .program import ProgramSession

        prog = Path(submission_dir) / "program"
        if not prog.is_dir():
            raise Fatal("missing program/ directory")
        self._session = ProgramSession(prog, entry, **kw)

    def __enter__(self):
        try:
            return self._session.__enter__()
        except RuntimeError as e:
            raise Fatal(f"program failed to load: {e}") from e

    def __exit__(self, *exc) -> None:
        self._session.__exit__(*exc)


def pick(table: Mapping[str, Mapping[str, str]], key: str, lang: str) -> str:
    """table[key][lang], with a clear error when a label is missing."""
    try:
        return table[key][lang]
    except KeyError as e:
        raise KeyError(f"label {key!r} has no {lang!r} text") from e


def labels(table: Mapping[str, Mapping[str, str]], lang: str) -> dict[str, str]:
    return {k: pick(table, k, lang) for k in table}


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    """UTF-8 with BOM, so spreadsheet tools open CJK text correctly."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    path.write_bytes(buf.getvalue().encode("utf-8-sig"))


def write_xlsx(path: Path, sheets: Mapping[str, tuple[Sequence[str], Iterable[Sequence[Any]]]]) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for title, (header, rows) in sheets.items():
        ws = wb.create_sheet(title[:31])
        ws.append(list(header))
        for r in rows:
            ws.append(list(r))
    # Fixed metadata and zip timestamps keep the bytes identical across runs (the validator checks determinism).
    import datetime
    import zipfile
    wb.properties.created = wb.properties.modified = datetime.datetime(2026, 1, 1)
    raw = io.BytesIO()
    wb.save(raw)
    with zipfile.ZipFile(raw) as src, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            fixed = zipfile.ZipInfo(info.filename, date_time=(2026, 1, 1, 0, 0, 0))
            fixed.compress_type = zipfile.ZIP_DEFLATED
            body = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                # openpyxl stamps the save time here regardless of wb.properties.
                body = re.sub(rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*(<)", rb"\g<1>2026-01-01T00:00:00Z\g<2>", body)
            dst.writestr(fixed, body)


def write_json(path: Path, doc: Any) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(submission_dir: Path, name: str) -> Any:
    p = submission_dir / name
    if not p.is_file():
        raise Fatal(f"missing {name}")
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise Fatal(f"{name} is not valid JSON: {e}") from e


def read_csv(submission_dir: Path, name: str, required: Sequence[str]) -> list[dict[str, str]]:
    p = submission_dir / name
    if not p.is_file():
        raise Fatal(f"missing {name}")
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "cp949", "shift_jis", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise Fatal(f"{name}: unknown text encoding")
    rows = list(csv.DictReader(io.StringIO(text)))
    if rows:
        missing = [c for c in required if c not in rows[0]]
        if missing:
            raise Fatal(f"{name}: missing columns {missing}")
    return rows


def number(v: Any, what: str) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError) as e:
        raise Fatal(f"{what}: not a number: {v!r}") from e
    if x != x or x in (float("inf"), float("-inf")):
        raise Fatal(f"{what}: not a finite number: {v!r}")
    return x
