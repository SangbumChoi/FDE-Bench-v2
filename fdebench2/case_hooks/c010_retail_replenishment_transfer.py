"""Relaxed re-scoring for v1 case 010 (retail replenishment / transfer).

The v1 evaluator stops at the first sign of a violation and reports no quality.
Its `_simulate` already recomputes fulfilment, lateness and cost for any plan,
so a policy that lets "same-city internal stock first" (HC2/HC3) bend can still
score the plan: drop the relaxed violations, keep every other rule hard, and
normalise with the evaluator's own formula and reference value.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from ..cases import V1Case
from ..transforms.policy import CaseRules


def _load(case: V1Case):
    spec = importlib.util.spec_from_file_location(f"v1_eval_{case.id}", case.evaluator)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def relaxed_score(case: V1Case, submission_dir: Path, relaxed: set[str], rules: CaseRules) -> dict[str, Any]:
    m = _load(case)
    data = m.load_data(case.data_dir)
    submission = json.loads((submission_dir / m.PLAN_FILE).read_text(encoding="utf-8"))
    violations, rec = m._simulate(data, submission, {"lt_defaults_used": 0})
    remaining = [v for v in violations if (r := rules.classify(v)) is None or r.id not in relaxed]
    if remaining:
        return {"validity_score": 0.0, "quality_score": 0.0, "remaining": remaining[:8]}
    absolute = m._absolute_score(rec["fulfillment_rate"], rec["late_units"], rec["total_cost"],
                                 max(rec["total_demand"], 1.0))
    reference = m.load_baseline()
    return {"validity_score": 1.0, "quality_score": absolute / reference if reference > 0 else 0.0,
            "relaxed_violations": len(violations)}
