"""Run a v1 case evaluator, unmodified, against a submission directory.

The 49 v1 evaluators do not share one signature (`evaluate(submission_dir,
data_dir)`, `evaluate(data_dir, baseline_dir, submission_dir)`,
`evaluate(file_path, data_dir)`, ...). The shim below binds whatever
parameters a given evaluator declares. It always scores against the pristine
v1 data, never the agent's (possibly noisy) copy.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..cases import V1Case

_SHIM = r"""
import importlib.util, inspect, json, sys
from pathlib import Path
evaluator, data_dir, baseline_dir, sub_dir, names = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), json.loads(sys.argv[5])
spec = importlib.util.spec_from_file_location("v1_evaluator", evaluator)
mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
fn = getattr(mod, "evaluate", None) or getattr(mod, "compute_metrics")

def sub_file():
    for n in names:
        if (sub_dir / n).is_file():
            return sub_dir / n
    files = sorted(p for p in sub_dir.iterdir() if p.is_file()) if sub_dir.is_dir() else []
    return files[0] if len(files) == 1 else sub_dir / (names[0] if names else "solution.json")

kw = {}
params = inspect.signature(fn).parameters
for name, p in params.items():
    if name in ("plan_path", "file_path", "plan_file", "input_file"):
        kw[name] = sub_file()
    elif name in ("submission_dir", "submission", "sub_dir"):
        kw[name] = sub_dir
    elif name in ("data_dir", "data", "dataset_dir"):
        kw[name] = data_dir
    elif name in ("baseline_dir", "baseline"):
        kw[name] = baseline_dir
missing = [n for n, p in params.items() if p.default is inspect.Parameter.empty and n not in kw
           and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
if missing:
    raise TypeError(f"cannot bind evaluator parameters {missing}")
print("__RESULT__" + json.dumps(fn(**kw), ensure_ascii=False, default=str))
"""


def run_evaluator(case: V1Case, submission_dir: Path, timeout: float = 3600) -> dict[str, Any]:
    cmd = [sys.executable, "-c", _SHIM, str(case.evaluator), str(case.data_dir),
           str(case.tests_dir / "baseline"), str(submission_dir), json.dumps(case.submission_files)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=case.tests_dir)
    except subprocess.TimeoutExpired:
        return {"validity_score": 0.0, "quality_score": 0.0, "error_info": {"harness": "evaluator timed out"}}
    for line in p.stdout.splitlines():
        if line.startswith("__RESULT__"):
            result = json.loads(line[len("__RESULT__"):])
            return result if isinstance(result, dict) else {"raw": result}
    return {"validity_score": 0.0, "quality_score": 0.0,
            "error_info": {"harness": "evaluator produced no result", "stderr": p.stderr[-2000:]}}


def violations(result: dict[str, Any]) -> list[str]:
    """Hard-constraint violation messages, in the shapes v1 evaluators report them."""
    info = result.get("error_info") or {}
    out: list[str] = []
    for key in ("constraint", "constraints", "violations", "hard_constraints"):
        val = info.get(key) if isinstance(info, dict) else None
        if isinstance(val, list):
            out += [str(v) for v in val]
    return out
