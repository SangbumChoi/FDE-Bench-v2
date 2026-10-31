"""Benchmark cases behind one interface.

A case lives in cases/<field>/<role>/ (fields are listed in cases/fields.yaml)
and is addressed as "<field>/<role>": texts authored per locale, data generated
deterministically from a seed and written with localized headers and labels,
and an evaluator that scores against the generated ground truth. A case that
lacks a locale can still run in it: its texts are then machine-translated at
run time (see transforms.variant).

A case may declare settings: content tiers (`tiers:` in case.yaml: easy /
medium / hard, chosen by the difficulty) and rule parameters drawn by a rule
seed (`params:` candidate pools, `rule_seeds:` the public panel). A setting is
(tier, rule seed): the tier decides which rules apply, the rule seed draws each
parameter independently from its pool (a pool may differ per tier). The world
and the agent-visible data and request are the same in every setting; a setting
changes only the hidden requirements, the rules that apply, their parameters
and so the ground truth. Texts mark setting-specific passages with
`<!-- tier: medium hard -->` ... `<!-- /tier -->` and
`<!-- when: name=v1,v2 -->` ... `<!-- /when -->` and insert parameters as
`{{name}}`; targets and rules carry `tiers: [...]` and `when: {name: [...]}`.
DESIGN.md (Settings) is the authoring contract.
"""

from __future__ import annotations

import importlib.util
import math
import operator
import random
import re
import sys
import tempfile
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

import yaml

from .transforms.policy import RATIO_CAP, CaseRule, CaseRules

LOCALES = ("zh", "en", "ko", "ja", "es")
TIERS = ("easy", "medium", "hard")
DEFAULT_TIER = "medium"
MAX_REDRAWS = 100            # admissible(): salted redraws k = 1..MAX_REDRAWS before a rule seed is given up
_BLOCK = {kind: re.compile(rf"<!-- {kind}: ([A-Za-z ]+) -->\n?(.*?)<!-- /{kind} -->\n?", re.S)
          for kind in ("tier",)}
# The innermost when-block (its body holds no other when-marker), so nested blocks resolve from the inside out.
_WHEN = re.compile(r"<!-- when: ([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^>]*?) -->\n?"
                   r"((?:(?!<!-- /?when).)*?)<!-- /when -->\n?", re.S)
PARAM = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
BASELINE_MIN_GAP = 0.05   # quality's zero point is at least this share of the reference away from it


def quality_fields(obj: float, ref: float, base: float | None, maximize: bool) -> dict[str, Any]:
    """An objective's quality against the reference (and the baseline, when the case has one).

    quality_ratio is obj/ref (ref/obj when minimizing); quality_score is normalized so that the baseline
    scores 0 and the reference 1, or is the ratio itself when there is no baseline strictly worse than the
    reference (quality_anchor says which). The zero point is never closer to the reference than
    BASELINE_MIN_GAP of it, so a baseline that is nearly as good as the reference cannot blow small
    differences up. Both are capped at RATIO_CAP; the score is floored at 0.
    """
    if obj == ref:
        ratio = 1.0
    elif (ref if maximize else obj) > 0:
        ratio = min(obj / ref if maximize else ref / obj, RATIO_CAP)
    else:  # no meaningful ratio (e.g. zero cost): beating the reference earns the cap, falling short 0
        ratio = RATIO_CAP if (obj > ref) == maximize else 0.0
    if base is not None and (base < ref if maximize else base > ref):
        gap = BASELINE_MIN_GAP * abs(ref)
        zero = min(base, ref - gap) if maximize else max(base, ref + gap)
        score, anchor = (obj - zero) / (ref - zero), "baseline"
    else:
        score, anchor = ratio, "ratio"
    return {"quality_ratio": round(ratio, 8), "quality_score": round(min(max(score, 0.0), RATIO_CAP), 8) + 0.0,
            "quality_anchor": anchor}


# ── texts: setting blocks and parameters ─────────────────────────────────────

def value_text(value: Any) -> str:
    """A parameter value as `when` conditions compare it: YAML's spelling of booleans and null, str() else."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def filter_blocks(text: str, kind: str, value: str | None) -> str:
    """Keep the `<!-- kind: ... -->` blocks that name `value` (all of them when value is None); drop the markers."""
    return _BLOCK[kind].sub(lambda m: m.group(2) if value is None or value in m.group(1).split() else "", text)


def filter_tiers(text: str, tier: str | None) -> str:
    return filter_blocks(text, "tier", tier)


def when_values(spec: str) -> list[str]:
    """The values a `<!-- when: name=v1,v2 -->` marker lists."""
    return [v.strip() for v in spec.split(",") if v.strip()]


def filter_when(text: str, params: dict[str, Any]) -> str:
    """Keep the `<!-- when: name=v1,v2 -->` ... `<!-- /when -->` blocks whose parameter's value (as a string,
    see value_text) is listed; drop the others and every marker. Blocks may nest: each condition must hold."""
    def sub(m: re.Match) -> str:
        name, values, body = m.groups()
        return body if name in params and value_text(params[name]) in when_values(values) else ""

    while True:
        out = _WHEN.sub(sub, text)
        if out == text:
            return out
        text = out


def condition_holds(when: dict[str, Any] | None, params: dict[str, Any]) -> bool:
    """A rule's or target's `when: {name: [values]}`: every named parameter has one of its listed values."""
    for name, values in (when or {}).items():
        allowed = values if isinstance(values, (list, tuple)) else [values]
        if name not in params or value_text(params[name]) not in {value_text(v) for v in allowed}:
            return False
    return True


def value_label(labels: dict[Any, Any], value: Any) -> Any:
    """labels[value], also when YAML typed the key differently (1 vs "1"); KeyError when there is none."""
    if value in labels:
        return labels[value]
    for key, text in labels.items():
        if value_text(key) == value_text(value):
            return text
    raise KeyError(f"no label for value {value!r}")


def fill_params(text: str, params: dict[str, Any], lang: str = "en",
                labels: dict[str, dict[Any, dict[str, str]]] | None = None) -> str:
    """Replace `{{name}}` with the setting's parameter; an unknown name is an authoring error.

    `labels` gives a parameter value's wording per locale (case.yaml `params.<name>.labels`), for values that
    are codes in the data (e.g. a department id) but words in the text. A value that is itself a dict keyed by
    the five locales (a derived parameter may be one) is worded in `lang`.
    """
    labels = labels or {}

    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in params:
            raise KeyError(f"unknown parameter {{{{{name}}}}}")
        value = params[name]
        if name in labels:
            return str(value_label(labels[name], value)[lang])
        if isinstance(value, dict) and set(LOCALES) <= set(value):
            return str(value[lang])
        return str(value)
    return PARAM.sub(sub, text)


# ── rule seeds: drawing the parameters ───────────────────────────────────────

def param_pools(meta: dict[str, Any], tiers: tuple[str, ...]) -> dict[str, dict[str, list]]:
    """case.yaml `params:` as {name: {tier: candidates}}: one pool shared by every tier, or a pool per tier."""
    def pool(values: Any) -> list:
        return list(values) if isinstance(values, list) else []     # anything else: no candidates (validate-case)

    pools: dict[str, dict[str, list]] = {}
    spec_by_name = meta.get("params")
    for name, spec in (spec_by_name.items() if isinstance(spec_by_name, dict) else ()):
        values = spec.get("values") if isinstance(spec, dict) else None
        pools[name] = {t: pool(values.get(t) if isinstance(values, dict) else values) for t in tiers}
    return pools


def draw_index(case_id: str, name: str, rule_seed: int, size: int, salt: int = 0) -> int:
    """The position rule seed `rule_seed` draws in a pool of `size` candidates of parameter `name`.

    It does not depend on the tier (pools of the same size give the same position in every tier) nor on the
    other parameters, and it is the same in every process (random.Random seeded with a string)."""
    key = f"{case_id}|{name}|{rule_seed}" + (f"|{salt}" if salt else "")
    return random.Random(key).randrange(size)


def derive_full(drawn: dict[str, Any], tier: str, derive: Callable[[dict, str], dict] | None) -> dict[str, Any]:
    """The drawn parameters plus case.py derive_params' keys (which may add keys, not replace drawn ones)."""
    extra = dict(derive(dict(drawn), tier) or {}) if derive is not None else {}
    clash = sorted(set(extra) & set(drawn))
    if clash:
        raise ValueError(f"derive_params returns drawn parameters {clash}: it may only add keys")
    return {**drawn, **extra}


def draw_params(case_id: str, pools: dict[str, dict[str, list]], tier: str, rule_seed: int,
                derive: Callable[[dict, str], dict] | None = None,
                admissible: Callable[[dict, str], bool] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """(drawn, full): the parameters rule seed `rule_seed` draws in `tier`, and those plus the derived ones.

    Each parameter independently: pool[Random(f"{case_id}|{name}|{rule_seed}").randrange(len(pool))] with
    pool its candidates in `tier`. `derive(params, tier)` (case.py derive_params) adds derived keys;
    `admissible(params, tier)` (case.py admissible, given drawn and derived values) may reject the
    combination, and then every parameter is drawn again with salt k = 1, 2, ...
    (Random(f"{case_id}|{name}|{rule_seed}|{k}")), at most MAX_REDRAWS times.
    """
    for salt in range(MAX_REDRAWS + 1):
        drawn = {}
        for name, by_tier in pools.items():
            pool = by_tier.get(tier) or []
            if not pool:
                raise ValueError(f"{case_id}: parameter {name} has no candidates in tier {tier}")
            drawn[name] = pool[draw_index(case_id, name, rule_seed, len(pool), salt)]
        full = derive_full(drawn, tier, derive)
        if admissible is None or admissible(dict(full), tier):
            return drawn, full
    raise ValueError(f"{case_id}: rule seed {rule_seed} draws no admissible parameters in tier {tier} "
                     f"(first draw and {MAX_REDRAWS} redraws rejected)")


def as_rule_seed(seed: Any) -> int:
    """A rule seed is an int (not a bool, not a name)."""
    if isinstance(seed, bool):
        raise TypeError(f"a rule seed is an int, got {seed!r}")
    try:
        return operator.index(seed)
    except TypeError:
        raise TypeError(f"a rule seed is an int, got {seed!r}") from None


@dataclass(frozen=True)
class Setting:
    """One ground truth of a case: a content tier and the parameters its rule seed draws.

    `params` is the full dict case code reads (drawn and derived values); `setting["name"]` reads one of them.
    """

    tier: str
    rule_seed: int
    params: dict[str, Any] = field(default_factory=dict)
    # A combination the validator builds by changing one drawn parameter ("name=value"). It keeps such a
    # setting's label apart from its rule seed's, since case code may cache by label.
    variation: str = field(default="", compare=False)

    def at_least(self, tier: str) -> bool:
        return TIERS.index(self.tier) >= TIERS.index(tier)

    def __getitem__(self, key: str) -> Any:
        return self.params[key]

    @property
    def _seed_name(self) -> str:
        return f"s{self.rule_seed}" if isinstance(self.rule_seed, int) else str(self.rule_seed)

    @property
    def label(self) -> str:
        """"easy/s1"; a validator variation adds the changed parameter: "easy/s1[cap=5]"."""
        return f"{self.tier}/{self._seed_name}" + (f"[{self.variation}]" if self.variation else "")

    @property
    def folder(self) -> str:
        """The setting's folder in dataset/gt/: "easy_s1"."""
        return f"{self.tier}_{self._seed_name}"


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
    tier: str | None = None
    rule_seed: int | None = None

    def locales(self) -> tuple[str, ...]:
        raise NotImplementedError

    def request(self, lang: str) -> str:
        raise NotImplementedError

    def requirements(self, lang: str) -> str:
        raise NotImplementedError

    def targets(self, lang: str) -> list[Target]:
        raise NotImplementedError

    def shared_target_ids(self) -> list[str]:
        """Ids of the targets that apply in every setting, private rule seeds included (sorted)."""
        return sorted(t.id for t in self.targets(self.source_locale))

    def materialize_data(self, lang: str, dest: Path) -> None:
        raise NotImplementedError

    def evaluate(self, submission_dir: Path, lang: str, relaxed: frozenset[str] = frozenset()) -> dict[str, Any]:
        """{validity_score, quality_score, violations: [{rule, message}], metrics, error_info}; a valid
        submission adds objective, reference_objective, baseline_objective and quality_fields()."""
        raise NotImplementedError

    def rules(self) -> CaseRules | None:
        return None

    @property
    def quality_cap(self) -> float | None:
        """The normalized quality that earns full quality credit on this case; None: the policy's."""
        return None

    @property
    def tiers(self) -> tuple[str, ...]:
        """Content tiers the case declares; () when the case is the same at every difficulty."""
        return ()

    @property
    def rule_seeds(self) -> tuple[int, ...]:
        """The public rule seeds (stored in dataset/, shown in the explainer); () without settings."""
        return ()

    @property
    def setting(self) -> Setting | None:
        return None

    @property
    def drawn_params(self) -> dict[str, Any]:
        """The parameters this setting's rule seed drew ({} without settings)."""
        return {}

    def at(self, tier: str | None = None, rule_seed: int | None = None) -> "Case":
        """This case in one setting (itself when the case declares no settings). Any int is a rule seed; the
        public ones are `rule_seeds`, every other one is a private draw of the same candidates."""
        return self

    def at_tier(self, tier: str | None) -> "Case":
        return self.at(tier)

    def with_world_seed(self, seed: int | None) -> "Case":
        """This case on a world generated from another seed (itself for None or the case's own seed)."""
        return self

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
      baseline_solution(world, out_dir)            the simplest sensible valid deliverable (do nothing, first-fit,
                                                    a naive rule); it scores quality 0 (optional)
      score(world, submission_dir) -> dict          {"violations": [(rule_id, message)], "objective": float,
                                                     "metrics": {...}} or {"fatal": message}
                                                    Program cases call casekit.run_program(submission_dir,
                                                    ENTRYPOINT, hidden_inputs) here.
      violating_examples(world) -> {rule_id: fn(out_dir)}   for the validator (optional)
    A case that declares settings (`tiers:`, `params:` and `rule_seeds:` in case.yaml) gets the Setting as a
    last argument of reference_solution, baseline_solution, score and violating_examples; build_world and
    write_data never see it, so the data is the same in every setting. Two optional hooks shape the draw:
      derive_params(params, tier) -> dict          extra keys computed from the drawn values (e.g. period dates
                                                    from a fiscal-year start); a value may be a dict keyed by
                                                    the five locales, which {{name}} words per locale
      admissible(params, tier) -> bool              False rejects a combination (drawn and derived values): every
                                                    parameter is drawn again with a salt (see draw_params)
    case.yaml declares objective direction, the deliverable (`deliverable_type: batch` with `deliverables`,
    or `deliverable_type: program` with `entrypoint`), its spec, rule classes and optionally `quality_cap`
    (the normalized quality of the best known solution, which then earns full quality credit).
    """

    def __init__(self, root: Path, tier: str | None = None, rule_seed: int | None = None,
                 _family: dict | None = None, _drawn: dict | None = None, _variation: str = ""):
        self.root = root.resolve()
        self.meta = yaml.safe_load((self.root / "case.yaml").read_text(encoding="utf-8"))
        self.field = self.meta.get("field", self.root.parent.name)
        self.role = self.meta.get("role", "")
        self.id = f"{self.field}/{self.meta['id']}"
        self.task_type = self.meta.get("task_type", "")
        self.source_locale = "en"
        self._family = _family if _family is not None else {}    # shared by every setting of this case
        if "rulesets" in self.meta:
            raise ValueError(f"{self.id}: case.yaml declares rulesets: (fixed rule sets A / B / C), which are no "
                             f"longer supported: declare params: (each parameter's candidate pool) and rule_seeds: "
                             f"(the public panel, e.g. [1, 2, 3]) instead, as DESIGN.md (Settings) describes")
        drawn_contract = self.meta.get("params") is not None or self.meta.get("rule_seeds") is not None
        if bool(self.tiers) != drawn_contract:
            raise ValueError(f"{self.id}: case.yaml must declare tiers together with params: and rule_seeds:, "
                             f"or neither")
        if self.tiers:
            if not self.rule_seeds:
                raise ValueError(f"{self.id}: case.yaml rule_seeds: must list the public rule seeds (ints)")
            tier = tier or DEFAULT_TIER
            rule_seed = self.rule_seeds[0] if rule_seed is None else as_rule_seed(rule_seed)
            if tier not in self.tiers:
                raise KeyError(f"{self.id}: unknown tier {tier!r}; declared: {self.tiers}")
        self.tier = tier if self.tiers else None
        self.rule_seed = rule_seed if self.tiers else None
        self._drawn = dict(_drawn) if _drawn is not None and self.tiers else None
        self._variation = _variation if self._drawn is not None else ""

    # ── settings ────────────────────────────────────────────────────────────
    @property
    def tiers(self) -> tuple[str, ...]:
        return tuple(t for t in TIERS if t in (self.meta.get("tiers") or {}))

    @property
    def rule_seeds(self) -> tuple[int, ...]:
        if not self.tiers:
            return ()
        return tuple(as_rule_seed(s) for s in (self.meta.get("rule_seeds") or []))

    @property
    def param_candidates(self) -> dict[str, dict[str, list]]:
        """{name: {tier: candidate values}} from case.yaml `params:` ({} for a case without them)."""
        return param_pools(self.meta, self.tiers)

    def param_labels(self) -> dict[str, dict[Any, dict[str, str]]]:
        """{name: {value: {locale: wording}}} for the parameters whose values case.yaml words per locale."""
        specs = self.meta.get("params")
        return {name: spec["labels"] for name, spec in (specs.items() if isinstance(specs, dict) else ())
                if isinstance(spec, dict) and isinstance(spec.get("labels"), dict)}

    def _hook(self, name: str):
        return getattr(self.module, name, None)

    def _draw(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """(drawn, full) parameters of this setting, cached per (tier, rule seed) for the case."""
        if self._drawn is not None:
            return dict(self._drawn), derive_full(self._drawn, self.tier, self._hook("derive_params"))
        cache = self._family.setdefault("draws", {})
        key = (self.tier, self.rule_seed)
        if key not in cache:
            cache[key] = draw_params(self.id, self.param_candidates, self.tier, self.rule_seed,
                                     self._hook("derive_params"), self._hook("admissible"))
        drawn, full = cache[key]
        return dict(drawn), dict(full)

    @property
    def setting(self) -> Setting | None:
        if not self.tiers:
            return None
        return Setting(self.tier, self.rule_seed, self._draw()[1], variation=self._variation)

    @property
    def drawn_params(self) -> dict[str, Any]:
        """The values the rule seed drew: the setting's params without the derived keys ({} without settings)."""
        if not self.tiers:
            return {}
        return self._draw()[0]

    def settings(self) -> list["NativeCase"]:
        """The case in every public setting: tiers x public rule seeds (just itself when it declares none)."""
        if not self.tiers:
            return [self]
        return [self.at(t, s) for t in self.tiers for s in self.rule_seeds]

    def at(self, tier: str | None = None, rule_seed: int | None = None) -> "NativeCase":
        if not self.tiers:
            return self
        key = (tier or self.tier, self.rule_seed if rule_seed is None else as_rule_seed(rule_seed))
        if key == (self.tier, self.rule_seed) and self._drawn is None:
            return self
        cache = self._family.setdefault("settings", {})
        if key not in cache:
            cache[key] = NativeCase(self.root, *key, _family=self._family)
        return cache[key]

    def with_params(self, **changes: Any) -> "NativeCase":
        """This setting with some drawn parameters replaced and the derived ones recomputed: a combination its
        rule seed did not draw (the validator's parameter-binding check). Not cached; its label names the change."""
        if not self.tiers:
            raise ValueError(f"{self.id}: only a case with params: has parameters to change")
        unknown = sorted(set(changes) - set(self.param_candidates))
        if unknown:
            raise KeyError(f"{self.id}: {unknown} are not parameters of the case")
        note = ",".join(f"{k}={value_text(v)}" for k, v in changes.items())
        return NativeCase(self.root, self.tier, self.rule_seed, _family=self._family,
                          _drawn={**self.drawn_params, **changes},
                          _variation=",".join(x for x in (self._variation, note) if x))

    def is_admissible(self) -> bool:
        """case.py admissible() on this setting's parameters (True without the hook or settings)."""
        fn = self._hook("admissible") if self.tiers else None
        return fn is None or bool(fn(dict(self.setting.params), self.tier))

    def _applies(self, item: dict) -> bool:
        if self.tier is None:
            return True
        if "tiers" in item and self.tier not in item["tiers"]:
            return False
        return condition_holds(item.get("when"), self.setting.params)

    def _render(self, text: str, lang: str = "en") -> str:
        if self.tier is None:
            return text
        setting = self.setting
        text = filter_blocks(text, "tier", self.tier)
        text = filter_when(text, setting.params)
        return fill_params(text, setting.params, lang, self.param_labels())

    def _args(self) -> tuple:
        return (self.setting,) if self.tiers else ()

    # ── shared world and module ─────────────────────────────────────────────
    @property
    def module(self) -> ModuleType:
        if "module" not in self._family:
            self._family["module"] = _load_module(self.root / "case.py", f"fdeb2_case_{self.field}_{self.meta['id']}")
        return self._family["module"]

    @property
    def world_seed(self) -> int:
        return int(self._family.get("world_seed", self.meta.get("seed", 0)))

    def with_world_seed(self, seed: int | None) -> "NativeCase":
        """The same case on a fresh world: same rules, texts and settings, data and answers from `seed`.

        The stored dataset/ uses the case's own (public) seed; campaigns can run on other seeds so that scores
        do not depend on worlds whose answers are published.
        """
        if seed is None or int(seed) == self.world_seed:
            return self
        fam = self._family.setdefault("other_worlds", {})
        if seed not in fam:
            fam[seed] = NativeCase(self.root, self.tier, self.rule_seed,
                                   _family={"module": self.module, "world_seed": int(seed)})
        other = fam[seed].at(self.tier, self.rule_seed)
        if self._drawn is not None:
            return NativeCase(self.root, self.tier, self.rule_seed, _family=other._family, _drawn=self._drawn,
                              _variation=self._variation)
        return other

    @property
    def world(self) -> Any:
        if "world" not in self._family:
            self._family["world"] = self.module.build_world(self.world_seed)
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

    def shared_target_ids(self) -> list[str]:
        """Targets with no `when:` that every tier has: they apply under any rule seed, so a pick among them is
        the same in every setting."""
        ids = []
        for t in yaml.safe_load(self._raw("en", "targets.yaml")) or []:
            if t.get("when") or ("tiers" in t and not set(self.tiers) <= set(t["tiers"])):
                continue
            ids.append(t["id"])
        return sorted(ids)

    def materialize_data(self, lang: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        self.module.write_data(self.world, dest, lang)

    # ── scoring ─────────────────────────────────────────────────────────────
    def write_reference(self, out_dir: Path) -> None:
        self.module.reference_solution(self.world, Path(out_dir), *self._args())

    def write_baseline(self, out_dir: Path) -> None:
        self.module.baseline_solution(self.world, Path(out_dir), *self._args())

    def violating_examples(self) -> dict:
        fn = getattr(self.module, "violating_examples", None)
        return fn(self.world, *self._args()) if fn else {}

    def raw_score(self, submission_dir: Path) -> dict:
        return self.module.score(self.world, Path(submission_dir), *self._args())

    def _valid_objective(self, write, name: str) -> float:
        with tempfile.TemporaryDirectory() as tmp:
            write(Path(tmp))
            res = self.raw_score(Path(tmp))
        if "fatal" in res or res["violations"] or not math.isfinite(float(res["objective"])):
            raise AssertionError(f"{self.id} {self.setting.label if self.tiers else ''}: {name} solution is "
                                 f"not valid: {res}")
        return float(res["objective"])

    @cached_property
    def reference_objective(self) -> float:
        return self._valid_objective(self.write_reference, "reference")

    @cached_property
    def baseline_objective(self) -> float | None:
        """The objective of case.py's baseline_solution; None when the case has none."""
        if not hasattr(self.module, "baseline_solution"):
            return None
        return self._valid_objective(self.write_baseline, "baseline")

    @cached_property
    def _scoring_baseline(self) -> tuple[float | None, str]:
        """(baseline objective or None, why it is unusable). A baseline that fails on some world (a case bug the
        validator reports) must not stop scoring: quality then falls back to the plain ratio."""
        try:
            return self.baseline_objective, ""
        except AssertionError as e:
            return None, str(e)[:300]

    @property
    def quality_cap(self) -> float | None:
        cap = self.meta.get("quality_cap")
        if cap is None:
            return None
        if not 0 < float(cap) <= RATIO_CAP:     # above RATIO_CAP full credit could never be reached
            raise ValueError(f"{self.id}: quality_cap must be in (0, {RATIO_CAP:g}], got {cap!r}")
        return float(cap)

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
        obj = float(res["objective"])
        if not math.isfinite(obj):      # NaN fails every comparison and would earn full credit
            out["error_info"] = {"fatal": f"the objective is not a finite number: {obj}"}
            return out
        ref, (base, base_error) = self.reference_objective, self._scoring_baseline
        higher = self.meta.get("objective", "minimize") == "maximize"
        out.update(validity_score=1.0, **quality_fields(obj, ref, base, higher), objective=obj,
                   reference_objective=ref, baseline_objective=base, relaxed_violations=len(out["violations"]))
        if base_error:
            out["baseline_error"] = base_error
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
        # The same in every setting. Batch cases: shown to the extractor, not the agent (the format is open).
        # Program cases: shown to the agent as the program interface.
        return self.meta.get("deliverable_spec", "")


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
