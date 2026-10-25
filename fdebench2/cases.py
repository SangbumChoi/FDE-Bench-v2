"""Benchmark cases behind one interface.

Two kinds:

* `NativeCase` (cases/<id>/): FDE-Bench v2's own original cases. Every text is
  authored in all five locales, data is generated deterministically from a seed
  and written with localized headers and labels, and the evaluator scores against
  the generated ground truth, so no file is ever translated after the fact.
* `V1Case` (external/fde-bench-v1/case/<id>/): the optional external FDE-Bench v1
  benchmark (CC BY-NC-ND 4.0, fetched by `fdebench2 fetch-v1`, never committed).
  Chinese only; other customer locales fall back to run-time machine translation
  of the texts, which stays on the user's machine.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from .transforms.policy import CaseRule, CaseRules, load_case_rules

LOCALES = ("zh", "en", "ko", "ja", "es")


class NotLocalized(LookupError):
    """The case has no authored text in this locale."""


@dataclass(frozen=True)
class Target:
    """One hidden requirement the agent should uncover."""

    id: str
    text: str                 # in the variant's customer locale
    source_text: str          # canonical wording (native: English; v1: Chinese)
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
        return CaseRules(self.id, [CaseRule(id=r["id"], match=r["id"], rule_class=r["class"],
                                            description=r.get("description", ""))
                                   for r in self.meta.get("rules", [])])

    @property
    def submission_files(self) -> list[str]:
        return list(self.meta.get("deliverables", []))

    def deliverable_spec(self) -> str:
        return self.meta.get("deliverable_spec", "")


# ── external FDE-Bench v1 cases ──────────────────────────────────────────────

_GT_TEXT, _GT_KIND, _GT_DOMAIN = "澄清问题", "问题类型", "内容域"


def parse_gt(gt: dict[str, Any]) -> list[Target]:
    out = []
    for key, val in gt.items():
        if isinstance(val, dict):
            text = str(val.get(_GT_TEXT) or next((v for v in val.values() if isinstance(v, str)), ""))
            kind, domain = str(val.get(_GT_KIND) or ""), str(val.get(_GT_DOMAIN) or "")
        else:
            text, kind, domain = str(val), "", ""
        out.append(Target(id=key, text=text, source_text=text, kind=kind, domain=domain))
    return out


class V1Case(Case):
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.id = f"v1-{self.root.name}"
        self.v1_id = self.root.name
        task = tomllib.loads((self.root / "task.toml").read_text(encoding="utf-8")) if (self.root / "task.toml").is_file() else {}
        self.metadata = task.get("metadata", {})
        self.task_type = str(self.metadata.get("task_type", "")).strip()
        self.source_locale = "zh"
        schema = self.root / "tests" / "submission_schema.json"
        self.schema = json.loads(schema.read_text(encoding="utf-8")) if schema.is_file() else None

    @classmethod
    def load(cls, root: str | Path) -> "V1Case":
        return cls(Path(root))

    def locales(self) -> tuple[str, ...]:
        return ("zh",)

    def _zh(self, lang: str, name: str) -> str:
        if lang != "zh":
            raise NotLocalized(f"{self.id}: v1 cases are Chinese only")
        return (self.root / name).read_text(encoding="utf-8").strip()

    def request(self, lang: str) -> str:
        return self._zh(lang, "instruction.md")

    def requirements(self, lang: str) -> str:
        return self._zh(lang, "information.md")

    def targets(self, lang: str) -> list[Target]:
        if lang != "zh":
            raise NotLocalized(self.id)
        gt = self.root / "gt.json"
        return parse_gt(json.loads(gt.read_text(encoding="utf-8"))) if gt.is_file() else []

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def tests_dir(self) -> Path:
        return self.root / "tests"

    @property
    def evaluator(self) -> Path:
        return self.tests_dir / "evaluator.py"

    def data_files(self) -> list[Path]:
        return sorted(p for p in self.data_dir.rglob("*") if p.is_file()) if self.data_dir.is_dir() else []

    def materialize_data(self, lang: str, dest: Path) -> None:
        if dest.exists():
            shutil.rmtree(dest)
        if self.data_dir.is_dir():
            shutil.copytree(self.data_dir, dest)
        else:
            dest.mkdir(parents=True)

    def evaluate(self, submission_dir: Path, lang: str, relaxed: frozenset[str] = frozenset()) -> dict[str, Any]:
        from .scoring.evaluate import run_evaluator, violations
        rules = self.rules()
        raw = run_evaluator(self, submission_dir)
        raw["violations"] = []
        for v in violations(raw):
            r = rules.classify(v) if rules else None
            raw["violations"].append({"rule": r.id if r else "unclassified", "message": v})
        if not relaxed or raw.get("validity_score"):
            return raw
        # v1 evaluators stop at the first violation and report no quality: a per-case hook re-scores.
        if rules is None or not rules.hook:
            return raw
        hook = importlib.import_module(rules.hook)
        rescored = hook.relaxed_score(self, Path(submission_dir), set(relaxed), rules)
        return {**raw, **rescored}

    def rules(self) -> CaseRules | None:
        return load_case_rules(self.v1_id)

    @property
    def submission_files(self) -> list[str]:
        if not self.schema:
            return []
        return [f["name"] for f in self.schema.get("files", []) if f.get("name")]

    def deliverable_spec(self) -> str:
        import re
        src = self.evaluator.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'"""(.*?)"""', src, re.DOTALL)
        doc = m.group(1) if m else ""
        spec = re.search(r"(EXTRACTOR_SPEC:.*)", doc, re.DOTALL)
        return spec.group(1) if spec else doc


def discover(cases_root: str | Path | None = "cases", v1_root: str | Path | None = None) -> dict[str, Case]:
    """Native cases under `cases_root`, plus v1 cases under `v1_root` (if given and present)."""
    found: dict[str, Case] = {}
    if cases_root and Path(cases_root).is_dir():
        for p in sorted(Path(cases_root).iterdir()):
            if (p / "case.yaml").is_file():
                c = NativeCase(p)
                found[c.id] = c
    if v1_root:
        base = Path(v1_root)
        base = base / "case" if (base / "case").is_dir() else base
        if base.is_dir():
            for p in sorted(base.iterdir()):
                if (p / "instruction.md").is_file():
                    c = V1Case(p)
                    found[c.id] = c
    return found
