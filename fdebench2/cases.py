"""Benchmark cases behind one interface.

A case lives in cases/<id>/: texts authored per locale, data generated
deterministically from a seed and written with localized headers and labels,
and an evaluator that scores against the generated ground truth. A case that
lacks a locale can still run in it: its texts are then machine-translated at
run time (see transforms.variant).
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from .transforms.policy import CaseRule, CaseRules

LOCALES = ("zh", "en", "ko", "ja", "es")


class NotLocalized(LookupError):
    """The case has no authored text in this locale."""


@dataclass(frozen=True)
class Target:
    """One hidden requirement the agent should uncover."""

    id: str
    text: str                 # in the variant's customer locale
    source_text: str          # canonical wording (English)
    kind: str = ""            # missing | ambiguous | ...
    domain: str = ""          # data semantics | calculation | scoring | business rule ...
    origin: str = "case"      # "case" or the v2 transform that introduced it

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class Case:
    id: str
    root: Path
    task_type: str = ""
    domain: str = ""
    source_locale: str = "en"

    def locales(self) -> tuple[str, ...]:
        raise NotImplementedError

    def request(self, lang: str) -> str:
        raise NotImplementedError

    def requirements(self, lang: str) -> str:
        raise NotImplementedError

    def targets(self, lang: str) -> list[Target]:
        raise NotImplementedError

    def materialize_data(self, lang: str, dest: Path) -> None:
        raise NotImplementedError

    def evaluate(self, submission_dir: Path, lang: str, relaxed: frozenset[str] = frozenset()) -> dict[str, Any]:
        """{validity_score, quality_score, violations: [{rule, message}], metrics, error_info}."""
        raise NotImplementedError

    def rules(self) -> CaseRules | None:
        return None

    @property
    def submission_files(self) -> list[str]:
        return []

    def deliverable_spec(self) -> str:
        return ""


# ── native v2 cases ──────────────────────────────────────────────────────────

def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class NativeCase(Case):
    """cases/<id>/ with case.yaml, case.py and locales/<lang>/{request.md, requirements.md, targets.yaml}.

    case.py implements:
      build_world(seed) -> world                    ground truth and everything the data is rendered from
      write_data(world, data_dir, lang)             render the agent-visible data in one locale
      reference_solution(world, out_dir)           write the reference deliverable (scores quality 1.0)
      score(world, submission_dir) -> dict          {"violations": [(rule_id, message)], "objective": float,
                                                     "metrics": {...}} or {"fatal": message}
      violating_examples(world) -> {rule_id: fn(out_dir)}   for the validator (optional)
    case.yaml declares objective direction, deliverable files and spec, and rule classes.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.meta = yaml.safe_load((self.root / "case.yaml").read_text(encoding="utf-8"))
        self.id = self.meta["id"]
        self.task_type = self.meta.get("task_type", "")
        self.domain = self.meta.get("domain", "")
        self.source_locale = "en"

    @cached_property
    def module(self) -> ModuleType:
        return _load_module(self.root / "case.py", f"fdeb2_case_{self.id}")

    @cached_property
    def world(self) -> Any:
        return self.module.build_world(int(self.meta.get("seed", 0)))

    def locales(self) -> tuple[str, ...]:
        return tuple(l for l in LOCALES if (self.root / "locales" / l / "request.md").is_file())

    def _text(self, lang: str, name: str) -> str:
        path = self.root / "locales" / lang / name
        if not path.is_file():
            raise NotLocalized(f"{self.id}: no {name} in {lang}")
        return path.read_text(encoding="utf-8").strip()

    def request(self, lang: str) -> str:
        return self._text(lang, "request.md")

    def requirements(self, lang: str) -> str:
        return self._text(lang, "requirements.md")

    def targets(self, lang: str) -> list[Target]:
        loc = yaml.safe_load(self._text(lang, "targets.yaml")) or []
        src = {t["id"]: t for t in yaml.safe_load(self._text("en", "targets.yaml")) or []}
        return [Target(id=t["id"], text=t["text"], source_text=src.get(t["id"], t)["text"],
                       kind=src.get(t["id"], t).get("kind", ""), domain=src.get(t["id"], t).get("domain", ""))
                for t in loc]

    def materialize_data(self, lang: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        self.module.write_data(self.world, dest, lang)

    @cached_property
    def reference_objective(self) -> float:
        with tempfile.TemporaryDirectory() as tmp:
            self.module.reference_solution(self.world, Path(tmp))
            res = self.module.score(self.world, Path(tmp))
        if "fatal" in res or res["violations"]:
            raise AssertionError(f"{self.id}: reference solution is not valid: {res}")
        return float(res["objective"])

    def evaluate(self, submission_dir: Path, lang: str, relaxed: frozenset[str] = frozenset()) -> dict[str, Any]:
        out: dict[str, Any] = {"validity_score": 0.0, "quality_score": 0.0, "violations": [], "metrics": {},
                               "error_info": {}}
        try:
            res = self.module.score(self.world, Path(submission_dir))
        except Exception as e:  # a malformed submission must never crash scoring
            out["error_info"] = {"fatal": f"evaluator error: {e!r}"}
            return out
        if "fatal" in res:
            out["error_info"] = {"fatal": res["fatal"]}
            return out
        out["metrics"] = res.get("metrics", {})
        out["violations"] = [{"rule": r, "message": m} for r, m in res["violations"]]
        blocking = [v for v in out["violations"] if v["rule"] not in relaxed]
        if blocking:
            out["error_info"] = {"constraint": [f"{v['rule']}: {v['message']}" for v in blocking[:8]]}
            return out
        obj, ref = float(res["objective"]), self.reference_objective
        higher = self.meta.get("objective", "minimize") == "maximize"
        if higher:
            quality = obj / ref if ref > 0 else 0.0
        else:
            quality = ref / obj if obj > 0 else (1.0 if ref == 0 else 0.0)
        out.update(validity_score=1.0, quality_score=round(quality, 8), objective=obj, reference_objective=ref,
                   relaxed_violations=len(out["violations"]))
        return out

    def rules(self) -> CaseRules:
        return CaseRules(self.id, [CaseRule(id=r["id"], rule_class=r["class"],
                                            description=r.get("description", ""))
                                   for r in self.meta.get("rules", [])])

    @property
    def submission_files(self) -> list[str]:
        return list(self.meta.get("deliverables", []))

    def deliverable_spec(self) -> str:
        return self.meta.get("deliverable_spec", "")


def discover(cases_root: str | Path = "cases") -> dict[str, Case]:
    """Every case under `cases_root` (a directory holding <id>/case.yaml)."""
    found: dict[str, Case] = {}
    root = Path(cases_root)
    if root.is_dir():
        for p in sorted(root.iterdir()):
            if (p / "case.yaml").is_file():
                c = NativeCase(p)
                found[c.id] = c
    return found
