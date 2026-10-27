"""Benchmark cases behind one interface.

A case lives in cases/<field>/<role>/ (fields are listed in cases/fields.yaml)
and is addressed as "<field>/<role>": texts authored per locale, data generated
deterministically from a seed and written with localized headers and labels,
and an evaluator that scores against the generated ground truth. A case that
lacks a locale can still run in it: its texts are then machine-translated at
run time (see transforms.variant).

A case may declare settings: content tiers (`tiers:` in case.yaml: easy /
medium / hard, chosen by the difficulty) and rule sets (`rulesets:` A / B / C:
hyperparameters of the client's rules, e.g. a cap of 4 vs 5). The world and
the agent-visible data and request are the same in every setting; a setting
changes only the hidden requirements, the rules that apply, their parameters
and so the ground truth. Texts mark setting-specific passages with
`<!-- tier: medium hard -->` / `<!-- ruleset: A B -->` ... `<!-- /tier -->` /
`<!-- /ruleset -->` and insert parameters as `{{name}}`; targets and rules carry
`tiers: [...]` / `rulesets: [...]`.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from .transforms.policy import CaseRule, CaseRules

LOCALES = ("zh", "en", "ko", "ja", "es")
TIERS = ("easy", "medium", "hard")
RULESETS = ("A", "B", "C")
DEFAULT_TIER = "medium"
DEFAULT_RULESET = "A"
_BLOCK = {kind: re.compile(rf"<!-- {kind}: ([A-Za-z ]+) -->\n?(.*?)<!-- /{kind} -->\n?", re.S)
          for kind in ("tier", "ruleset")}
PARAM = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def filter_blocks(text: str, kind: str, value: str | None) -> str:
    """Keep the `<!-- kind: ... -->` blocks that name `value` (all of them when value is None); drop the markers."""
    return _BLOCK[kind].sub(lambda m: m.group(2) if value is None or value in m.group(1).split() else "", text)


def filter_tiers(text: str, tier: str | None) -> str:
    return filter_blocks(text, "tier", tier)


def fill_params(text: str, params: dict[str, Any], lang: str = "en",
                labels: dict[str, dict[Any, dict[str, str]]] | None = None) -> str:
    """Replace `{{name}}` with the rule set's parameter; an unknown name is an authoring error.

    `labels` (case.yaml `param_labels`) gives a parameter value's wording per locale, for values that are
    codes in the data (e.g. a department id) but words in the text.
    """
    labels = labels or {}

    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in params:
            raise KeyError(f"unknown parameter {{{{{name}}}}}")
        value = params[name]
        if name in labels:
            return str(labels[name][value][lang])
        return str(value)
    return PARAM.sub(sub, text)


@dataclass(frozen=True)
class Setting:
    """One ground truth of a case: a content tier and a rule set's parameters."""

    tier: str
    ruleset: str
    params: dict[str, Any] = field(default_factory=dict)

    def at_least(self, tier: str) -> bool:
        return TIERS.index(self.tier) >= TIERS.index(tier)

    def __getitem__(self, key: str) -> Any:
        return self.params[key]

    @property
    def label(self) -> str:
        return f"{self.tier}/{self.ruleset}"


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
    field: str = ""
    role: str = ""
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
    def tiers(self) -> tuple[str, ...]:
        """Content tiers the case declares; () when the case is the same at every difficulty."""
        return ()

    @property
    def rulesets(self) -> tuple[str, ...]:
        """Rule sets the case declares; () when it has one fixed set of rules."""
        return ()

    def at(self, tier: str | None = None, ruleset: str | None = None) -> "Case":
        """This case in one setting (itself when the case declares no settings)."""
        return self

    def at_tier(self, tier: str | None) -> "Case":
        return self.at(tier)

    @property
    def submission_files(self) -> list[str]:
        return []

    @property
    def deliverable_type(self) -> str:
        """"batch" (files the agent writes) or "program" (code the evaluator runs on hidden inputs)."""
        return "batch"

    @property
    def entrypoint(self) -> str:
        """Program cases: "file.py:function" inside the delivered program/ directory."""
        return ""

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
    """cases/<field>/<role>/ with case.yaml, case.py and locales/<lang>/{request.md, requirements.md, targets.yaml}.

    case.py implements:
      build_world(seed) -> world                    ground truth and everything the data is rendered from
      write_data(world, data_dir, lang)             render the agent-visible data in one locale
      reference_solution(world, out_dir)           write the reference deliverable (scores quality 1.0)
      score(world, submission_dir) -> dict          {"violations": [(rule_id, message)], "objective": float,
                                                     "metrics": {...}} or {"fatal": message}
                                                    Program cases call casekit.run_program(submission_dir,
                                                    ENTRYPOINT, hidden_inputs) here.
      violating_examples(world) -> {rule_id: fn(out_dir)}   for the validator (optional)
    A case that declares settings (`tiers:` and `rulesets:` in case.yaml) gets the setting as a last
    argument of reference_solution, score and violating_examples; build_world and write_data never see
    it, so the data is the same in every setting.
    case.yaml declares objective direction, the deliverable (`deliverable_type: batch` with `deliverables`,
    or `deliverable_type: program` with `entrypoint`), its spec, and rule classes.
    """

    def __init__(self, root: Path, tier: str | None = None, ruleset: str | None = None,
                 _family: dict | None = None):
        self.root = root.resolve()
        self.meta = yaml.safe_load((self.root / "case.yaml").read_text(encoding="utf-8"))
        self.field = self.meta.get("field", self.root.parent.name)
        self.role = self.meta.get("role", "")
        self.id = f"{self.field}/{self.meta['id']}"
        self.task_type = self.meta.get("task_type", "")
        self.source_locale = "en"
        if bool(self.tiers) != bool(self.rulesets):
            raise ValueError(f"{self.id}: case.yaml must declare both tiers and rulesets, or neither")
        if self.tiers:
            tier, ruleset = tier or DEFAULT_TIER, ruleset or DEFAULT_RULESET
            if tier not in self.tiers:
                raise KeyError(f"{self.id}: unknown tier {tier!r}; declared: {self.tiers}")
            if ruleset not in self.rulesets:
                raise KeyError(f"{self.id}: unknown rule set {ruleset!r}; declared: {self.rulesets}")
        self.tier = tier if self.tiers else None
        self.ruleset = ruleset if self.tiers else None
        self._family = _family if _family is not None else {}    # shared by every setting of this case

    # ── settings ────────────────────────────────────────────────────────────
    @property
    def tiers(self) -> tuple[str, ...]:
        return tuple(t for t in TIERS if t in (self.meta.get("tiers") or {}))

    @property
    def rulesets(self) -> tuple[str, ...]:
        return tuple(r for r in RULESETS if r in (self.meta.get("rulesets") or {}))

    @property
    def setting(self) -> Setting | None:
        if not self.tiers:
            return None
        return Setting(self.tier, self.ruleset, dict(self.meta["rulesets"][self.ruleset] or {}))

    def settings(self) -> list["NativeCase"]:
        """The case in every setting (just itself when it declares none)."""
        if not self.tiers:
            return [self]
        return [self.at(t, r) for t in self.tiers for r in self.rulesets]

    def at(self, tier: str | None = None, ruleset: str | None = None) -> "NativeCase":
        if not self.tiers:
            return self
        key = (tier or self.tier, ruleset or self.ruleset)
        if key == (self.tier, self.ruleset):
            return self
        cache = self._family.setdefault("settings", {})
        if key not in cache:
            cache[key] = NativeCase(self.root, *key, _family=self._family)
        return cache[key]

    def _applies(self, item: dict) -> bool:
        if self.tier is None:
            return True
        return (("tiers" not in item or self.tier in item["tiers"])
                and ("rulesets" not in item or self.ruleset in item["rulesets"]))

    def _render(self, text: str, lang: str = "en") -> str:
        if self.tier is None:
            return text
        text = filter_blocks(filter_blocks(text, "tier", self.tier), "ruleset", self.ruleset)
        return fill_params(text, self.setting.params, lang, self.meta.get("param_labels"))

    def _args(self) -> tuple:
        return (self.setting,) if self.tiers else ()

    # ── shared world and module ─────────────────────────────────────────────
    @property
    def module(self) -> ModuleType:
        if "module" not in self._family:
            self._family["module"] = _load_module(self.root / "case.py", f"fdeb2_case_{self.field}_{self.meta['id']}")
        return self._family["module"]

    @property
    def world(self) -> Any:
        if "world" not in self._family:
            self._family["world"] = self.module.build_world(int(self.meta.get("seed", 0)))
        return self._family["world"]

    # ── texts ───────────────────────────────────────────────────────────────
    def locales(self) -> tuple[str, ...]:
        return tuple(l for l in LOCALES if (self.root / "locales" / l / "request.md").is_file())

    def _raw(self, lang: str, name: str) -> str:
        path = self.root / "locales" / lang / name
        if not path.is_file():
            raise NotLocalized(f"{self.id}: no {name} in {lang}")
        return path.read_text(encoding="utf-8")

    def _text(self, lang: str, name: str) -> str:
        return self._render(self._raw(lang, name), lang).strip()

    def request(self, lang: str) -> str:
        return self._raw(lang, "request.md").strip()      # the same in every setting (checked by the validator)

    def requirements(self, lang: str) -> str:
        return self._text(lang, "requirements.md")

    def targets(self, lang: str) -> list[Target]:
        loc = yaml.safe_load(self._raw(lang, "targets.yaml")) or []
        src = {t["id"]: t for t in yaml.safe_load(self._raw("en", "targets.yaml")) or []}
        out = []
        for t in loc:
            meta = src.get(t["id"], t)
            if self._applies(meta):
                out.append(Target(id=t["id"], text=self._render(t["text"], lang), source_text=self._render(meta["text"]),
                                  kind=meta.get("kind", ""), domain=meta.get("domain", "")))
        return out

    def materialize_data(self, lang: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        self.module.write_data(self.world, dest, lang)

    # ── scoring ─────────────────────────────────────────────────────────────
    def write_reference(self, out_dir: Path) -> None:
        self.module.reference_solution(self.world, Path(out_dir), *self._args())

    def violating_examples(self) -> dict:
        fn = getattr(self.module, "violating_examples", None)
        return fn(self.world, *self._args()) if fn else {}

    def raw_score(self, submission_dir: Path) -> dict:
        return self.module.score(self.world, Path(submission_dir), *self._args())

    @cached_property
    def reference_objective(self) -> float:
        with tempfile.TemporaryDirectory() as tmp:
            self.write_reference(Path(tmp))
            res = self.raw_score(Path(tmp))
        if "fatal" in res or res["violations"]:
            raise AssertionError(f"{self.id} {self.setting.label if self.tiers else ''}: reference solution is "
                                 f"not valid: {res}")
        return float(res["objective"])

    def evaluate(self, submission_dir: Path, lang: str, relaxed: frozenset[str] = frozenset()) -> dict[str, Any]:
        out: dict[str, Any] = {"validity_score": 0.0, "quality_score": 0.0, "violations": [], "metrics": {},
                               "error_info": {}}
        try:
            res = self.raw_score(Path(submission_dir))
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
                                            description=self._render(r.get("description", "")))
                                   for r in self.meta.get("rules", []) if self._applies(r)])

    @property
    def submission_files(self) -> list[str]:
        if self.deliverable_type == "program":
            return [self.entrypoint.partition(":")[0]]
        return list(self.meta.get("deliverables", []))

    @property
    def deliverable_type(self) -> str:
        return self.meta.get("deliverable_type", "batch")

    @property
    def entrypoint(self) -> str:
        return self.meta.get("entrypoint", "")

    def deliverable_spec(self) -> str:
        return self.meta.get("deliverable_spec", "")      # agent-visible: the same in every setting


def load_fields(cases_root: str | Path = "cases") -> dict[str, dict[str, str]]:
    """Field id -> display name per locale, from cases/fields.yaml."""
    path = Path(cases_root) / "fields.yaml"
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def discover(cases_root: str | Path = "cases") -> dict[str, Case]:
    """Every case under `cases_root`, laid out as <field>/<role>/case.yaml, keyed "<field>/<role>"."""
    found: dict[str, Case] = {}
    root = Path(cases_root)
    if root.is_dir():
        for p in sorted(root.glob("*/*/case.yaml")):
            c = NativeCase(p.parent)
            found[c.id] = c
    return found
