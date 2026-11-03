"""Ground truth audit: evidence that a case's ground truth measures what it claims (DESIGN.md, Ground truth audit).

The ground truth of a setting describes acceptable behaviour in five parts: the client facts the agent must learn
(the targets), the validity checks (the rules), the objective, the reference with evidence of how close it is to
the best achievable, and diagnostic cases that tell a correct implementation from a shortcut. `audit_case` measures
them on one world, per tier, over the public panel plus up to AUDIT_COMBOS admissible parameter combinations of the
tier (combinations, not rule seeds, so no private seed's draw is exposed):

1. ablations: for every target in force, a deliverable that misreads only that fact (the reference of another
   value of a `param:` target's parameter, else case.py ablations()); the target bites when that loses at least
   ABLATION_MIN_DAMAGE of the credit;
2. shortcuts: case.py shortcuts(), each closed when invalid or scoring at most SHORTCUT_MAX_QUALITY;
3. value of information: what a deliverable that never asks earns on average over the tier's settings;
4. reference and bounds: the best known solution and a proven bound against the reference and the baseline;
5. diagnostics: whether the per-target "enforced" map (score()'s, merged with case.py diagnose()'s) tells the
   reference from each ablation that bites, and whether it is reliable on deliverables that are neither: the best
   known solution, built with full knowledge of the setting, must never be called not enforced on a target in
   force (diagnostic_false_negative); an ablation of one target that also flags other targets is reported
   (cross_flags); the baseline's and robust_solution's maps are profiled per target (diagnostic_profile).

Every evaluation asks for the diagnostic (evaluate(..., diagnose=True)) except the value-of-information matrix,
which needs only credit: there only robust_solution is diagnosed (for the profile).

A combination whose reference or baseline fails (raises or is not valid) is skipped, does not count towards
AUDIT_COMBOS, and is a finding: a rule seed can draw it.

Credit is 0 for an invalid deliverable, else the quality score clipped to [0, 1]. The result is deterministic and
JSON-serializable. `fdebench2 audit-case` prints it as a report and stores the public world's audit in
dataset/audit.json; validate-case requires a fresh one with passing findings for cases with `audited: true`.
"""

from __future__ import annotations

import hashlib
import heapq
import itertools
import json
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Callable

import yaml

from .cases import TIERS, NativeCase, is_case_doc, quality_span, value_text
from .dataset import AUDIT_FILE, DATASET_DIR

AUDIT_VERSION = 3              # 2: per-deliverable damage, unavailable values, failed settings, wider sources;
                               # 3: lazy diagnose(), diagnostic reliability (false negatives, cross flags, profile),
                               #    GT.md and CLIENT_REVIEW.md out of the sources
AUDIT_COMBOS = 12              # admissible parameter combinations measured per tier besides the public panel
ABLATION_MIN_DAMAGE = 0.10     # a target bites when misreading it loses a tenth of the way to the reference
SHORTCUT_MAX_QUALITY = 0.5     # a valid shortcut that scores above this is open
VOI_MIN = 0.10                 # audited cases: asking must be worth at least this much credit in every tier,
VOI_LOW = 0.30                 # and a tier below this is warned about
NO_TIER = "default"            # the one "tier" of a case without settings
DIGITS = 6
# case.yaml keys that decide what validate-case enforces, never what the audit measures: they stay out of the
# fingerprint, so a case can be marked audited (and given its quality_cap) after its audit without running it again.
ENFORCEMENT_KEYS = ("audited", "quality_cap")


# ── the settings measured ────────────────────────────────────────────────────

@dataclass
class _Setting:
    """One measured setting: the case in it, its label in the audit, whether the public panel holds it, the
    objectives of its reference and baseline (set once they are written and scored), and, when it could not be
    measured, which of the two failed ("reference" or "baseline") and why."""

    label: str
    case: NativeCase
    panel: bool
    reference: float | None = None
    baseline: float | None = None
    failed: str | None = None
    skipped: str | None = None

    @property
    def tier(self) -> str:
        return self.case.tier or NO_TIER

    @property
    def key(self) -> str:
        return _combo_key(self.case)


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _combo_key(case: NativeCase) -> str:
    """A setting's identity: its tier and drawn parameters (two rule seeds that draw the same are one setting)."""
    return _dump([case.tier, case.drawn_params])


def _unique(pool: list) -> list:
    return list({value_text(v): v for v in pool}.values())


def tier_order(tiers) -> list[str]:
    """Tiers easy, medium, hard (audit.json stores its keys sorted by name)."""
    return sorted(tiers, key=lambda t: TIERS.index(t) if t in TIERS else len(TIERS))


def params_text(tier: str, params: dict) -> str:
    """A combination as findings name it (and OPEN_AUDIT_FINDINGS keys it): "hard/cap=22,price=3"."""
    values = ",".join(f"{k}={value_text(v)}" for k, v in params.items())
    return f"{tier}/{values}" if values else tier


def measured_settings(case: NativeCase, combos: int = AUDIT_COMBOS,
                      prepare: Callable[[_Setting], tuple[str, str] | None] | None = None) -> dict[str, list[_Setting]]:
    """{tier: settings}: the public panel (a combination drawn twice counted once) and `combos` other admissible
    combinations of the tier's candidates in hash order, built with with_params on the tier's first public setting.

    `prepare(setting)` (audit_case: write and score its reference and baseline) returns (which failed, why) for a
    setting that cannot be measured, or None. Such a setting stays in the list with `skipped` set but does not
    count: drawing goes on until `combos` combinations are measured, or until `combos` have been skipped (a case
    whose reference fails everywhere must not run through a space of half a million combinations)."""
    if combos < 0:
        raise ValueError(f"combos must be 0 or more, got {combos}")

    def measure(s: _Setting) -> _Setting:
        failure = prepare(s) if prepare else None
        if failure:
            s.failed, s.skipped = failure
        return s
    if not case.tiers:
        return {NO_TIER: [measure(_Setting(NO_TIER, case, True))]}
    out = {}
    for tier in case.tiers:
        panel = {}
        for seed in case.rule_seeds:
            c = case.at(tier, seed)
            panel.setdefault(_combo_key(c), _Setting(c.setting.label, c, True))
        settings = [measure(s) for s in panel.values()]
        measured = skipped = 0
        more = _combinations(settings[0].case, set(panel))
        while measured < combos and skipped < combos and (alt := next(more, None)) is not None:
            s = measure(_Setting(f"{tier}/c{measured + skipped + 1}", alt, False))
            settings.append(s)
            skipped, measured = (skipped + 1, measured) if s.skipped else (skipped, measured + 1)
        out[tier] = settings
    return out


def _in_hash_order(case_id: str, tier: str, pools: dict[str, dict[str, list]]):
    """Every combination of the tier's candidates, in the order of sha256(case id | tier | values): deterministic and
    spread over the whole space. Taken in growing batches, so a large space is never held or sorted whole."""
    options = [_unique(by_tier[tier]) for by_tier in pools.values()]
    total, size, done = math.prod(map(len, options)), 64, 0
    while done < total:
        combos = (dict(zip(pools, values)) for values in itertools.product(*options))
        batch = heapq.nsmallest(size, combos, key=lambda c: hashlib.sha256(f"{case_id}|{tier}|{_dump(c)}".encode())
                                .hexdigest())
        yield from batch[done:]
        done, size = len(batch), size * 8


def _combinations(first: NativeCase, seen: set[str]):
    """The admissible combinations of the tier's candidates that the panel does not hold, in hash order (lazily)."""
    for combo in _in_hash_order(first.id, first.tier, first.param_candidates):
        if _dump([first.tier, combo]) not in seen:
            alt = first.with_params(**combo)
            if alt.is_admissible():
                yield alt


# ── deliverables, written once and scored once per setting ──────────────────

def _objective(res: dict) -> float | None:
    """The objective of a raw score, None when the deliverable is not valid."""
    if "fatal" in res or res.get("violations"):
        return None
    obj = float(res["objective"])
    return obj if math.isfinite(obj) else None


def _r(x: float | None) -> float | None:
    return None if x is None else round(float(x), DIGITS) + 0.0


def _summary(res: dict) -> dict:
    """What the audit keeps of an evaluation: validity, quality, credit, broken rules and the diagnostic (and why
    case.py diagnose() failed, when it raised)."""
    valid = res["validity_score"] == 1.0
    quality = _r(res["quality_score"]) if valid else None
    out = {"valid": valid, "quality": quality, "credit": min(quality, 1.0) if valid else 0.0,
           "rules": sorted({v["rule"] for v in res["violations"]}),
           "objective": _r(res.get("objective")) if valid else None, "enforced": dict(res.get("enforced") or {})}
    return {**out, "diagnose_error": res["diagnose_error"]} if res.get("diagnose_error") else out


class WriteFailed(Exception):
    """A solver raised while writing a deliverable (a case may signal an infeasible combination that way)."""


class _Bench:
    """Deliverables in a scratch folder, each written once and scored once per setting (twice when it was first
    scored without the diagnostic and is then asked for with it)."""

    def __init__(self, root: Path):
        self.root = root
        self.paths: dict[tuple, Path] = {}
        self.failed: dict[tuple, str] = {}
        self.scores: dict[tuple, dict] = {}
        self.with_diagnostic: set[tuple] = set()        # (deliverable, setting) scored with diagnose=True

    def write(self, key: tuple, write: Callable[[Path], None]) -> tuple:
        """Write the deliverable `key` once; WriteFailed (every time it is asked for again) when the solver raises."""
        if key in self.failed:
            raise WriteFailed(self.failed[key])
        if key not in self.paths:
            out = self.root / str(len(self.paths) + len(self.failed))
            out.mkdir()
            try:
                write(out)
            except Exception as e:
                self.failed[key] = f"{e!r}"[:300]
                raise WriteFailed(self.failed[key]) from e
            self.paths[key] = out
        return key

    def score(self, key: tuple, s: _Setting, diagnose: bool = True) -> dict:
        """The summary of deliverable `key` under s; diagnose=False (the value-of-information matrix) skips case.py
        diagnose(), which a later call with diagnose=True then runs."""
        at = (key, s.key)
        if at not in self.scores or (diagnose and at not in self.with_diagnostic):
            self.record(key, s, s.case.evaluate(self.paths[key], "en", diagnose=diagnose), diagnose)
        return self.scores[at]

    def record(self, key: tuple, s: _Setting, evaluation: dict, diagnosed: bool = True) -> None:
        self.scores[(key, s.key)] = _summary(evaluation)
        if diagnosed:
            self.with_diagnostic.add((key, s.key))

    def diagnosed(self) -> set[str]:
        """The targets some evaluation gave a True or False diagnostic for."""
        return {t for x in self.scores.values() for t, v in x["enforced"].items() if isinstance(v, bool)}


def _written(bench: _Bench, s: _Setting, which: str) -> tuple[tuple | None, dict | str]:
    """(key, raw score) of the setting's reference or baseline, or (None, why it cannot be used)."""
    try:
        key = bench.write((which, s.key), s.case.write_reference if which == "reference" else s.case.write_baseline)
    except WriteFailed as e:
        return None, f"the {which} solution fails: {e}"
    try:
        res = s.case.raw_score(bench.paths[key])
    except Exception as e:
        return None, f"the {which} cannot be scored: {e!r}"[:300]
    return (key, res) if _objective(res) is not None else (None, f"the {which} is not valid")


def _prepare(bench: _Bench, s: _Setting) -> tuple[str, str] | None:
    """Write and score the setting's reference and baseline once, and fix their objectives for every evaluation
    under s (scoring never computes them again). Returns None, or (which failed, why) when either raises or is not
    valid there: the setting cannot be measured, and findings report it (a rule seed can draw it)."""
    raw = {}
    for which in ("reference", "baseline"):
        if which == "baseline" and not hasattr(s.case.module, "baseline_solution"):
            continue
        key, res = _written(bench, s, which)
        if key is None:
            return which, res
        raw[key] = res
        setattr(s, which, _objective(res))
        s.case.__dict__[f"{which}_objective"] = getattr(s, which)
    for key, res in raw.items():
        bench.record(key, s, s.case.judge(res, diagnose_dir=bench.paths[key]))
    return None


# ── 1. ablations ─────────────────────────────────────────────────────────────

def target_params(case: NativeCase) -> dict[str, str]:
    """{target id: parameter} for the targets whose fact is exactly a drawn parameter's value (`param:` in
    en/targets.yaml, read from en only like kind and domain)."""
    targets = yaml.safe_load((case.root / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8")) or []
    return {t["id"]: t["param"] for t in targets if t.get("param")}


def _ablation(bench: _Bench, s: _Setting, target: str, param: str | None,
              hooks: dict) -> tuple[str, dict[str, tuple], dict[str, str]]:
    """(source, {name: deliverable}, unavailable) of a target's ablation in s: the references of the other admissible
    values of its parameter (param), else case.py ablations() (hook, also for a param: target whose parameter has no
    other usable candidate here), else none. unavailable: {combination: why} for the other values whose reference
    solution fails."""
    keys, unavailable = {}, {}
    if param in s.case.drawn_params:
        current = value_text(s.case.drawn_params[param])
        for v in _unique(s.case.param_candidates[param][s.case.tier]):
            alt = s.case.with_params(**{param: v}) if value_text(v) != current else None
            if alt is not None and alt.is_admissible():
                try:
                    keys[f"{param}={value_text(v)}"] = bench.write(("reference", _combo_key(alt)), alt.write_reference)
                except WriteFailed as e:
                    unavailable[params_text(alt.tier, alt.drawn_params)] = f"the reference solution fails: {e}"
    if keys:
        return "param", keys, unavailable
    if target in hooks:
        return "hook", {"ablation": bench.write(("ablation", s.key, target), hooks[target])}, unavailable
    return "none", {}, unavailable


def _ablation_rows(bench: _Bench, s: _Setting, params: dict[str, str]) -> list[dict]:
    """One row per target in force in s. damage = 1 - credit, per deliverable in `damage`; for a param: target
    worst, best_guess and mean are over the wrong values (best_guess: the least harmful, a valid one on a tie), and
    it bites on best_guess: an agent that guesses wrong but sensibly. invalid is the best guess's validity; rules are
    every rule some wrong value breaks. cross_flags: for each deliverable that bites, the other targets in force
    whose enforced is False on it (it misreads only this target, so a correct diagnostic of the others passes it,
    unless the facts interact)."""
    hooks, rows = s.case.ablations(), []
    in_force = [t.id for t in s.case.targets("en")]
    for t in s.case.targets("en"):
        source, keys, unavailable = _ablation(bench, s, t.id, params.get(t.id), hooks)
        scores = {name: bench.score(key, s) for name, key in keys.items()}
        damage = {name: _r(1.0 - x["credit"]) for name, x in scores.items()}
        row = {"target": t.id, "tier": s.tier, "setting": s.label, "source": source, "worst": None,
               "best_guess": None, "mean": None, "invalid": None, "rules": [], "bites": None, "diag_ok": None,
               "damage": damage, "enforced": {name: x["enforced"].get(t.id) for name, x in scores.items()},
               "cross_flags": {name: [u for u in in_force if u != t.id and scores[name]["enforced"].get(u) is False]
                               for name, d in damage.items() if d >= ABLATION_MIN_DAMAGE},
               "unavailable": unavailable}
        if scores:
            damage = row["damage"]
            guess = min(scores, key=lambda n: (damage[n], not scores[n]["valid"]))
            row.update(worst=max(damage.values()), best_guess=damage[guess], mean=_r(mean(damage.values())),
                       invalid=not scores[guess]["valid"], bites=damage[guess] >= ABLATION_MIN_DAMAGE,
                       rules=sorted({r for x in scores.values() for r in x["rules"]}))
        rows.append(row)
    return rows


def _diagnose(rows: list[dict], reference: dict[str, dict], diagnosed: set[str]) -> dict[str, dict]:
    """Set each ablation row's diag_ok and return {target: {has_diagnostic, separates}}.

    diag_ok is False when the reference's enforced[t] is False. Otherwise it asks whether every ablation deliverable
    that bites (invalid, or losing at least ABLATION_MIN_DAMAGE) has enforced[t] False (or None when the case has no
    diagnostic for t), and is None when none bites: a wrong value that loses nothing may give the reference's own
    deliverable, which a correct diagnostic calls enforced."""
    for row in rows:
        t = row["target"]
        if row["source"] == "none":
            continue
        biting = [name for name, d in row["damage"].items() if d >= ABLATION_MIN_DAMAGE]
        if reference[row["setting"]].get(t) is False:
            row["diag_ok"] = False
        elif biting:
            row["diag_ok"] = all(row["enforced"][name] is False or (row["enforced"][name] is None and t not in diagnosed)
                                 for name in biting)
    out = {}
    for t in dict.fromkeys(row["target"] for row in rows):
        checked = [r["diag_ok"] for r in rows if r["target"] == t and r["diag_ok"] is not None]
        out[t] = {"has_diagnostic": t in diagnosed,
                  "separates": all(checked) if t in diagnosed and checked else None}
    return out


# ── 2. shortcuts ─────────────────────────────────────────────────────────────

def _doc(fn: Callable) -> str:
    return ((fn.__doc__ or "").strip().splitlines() or [""])[0]


def _shortcut_rows(bench: _Bench, s: _Setting) -> list[dict]:
    rows = []
    for name, fn in s.case.shortcuts().items():
        x = bench.score(bench.write(("shortcut", s.key, name), fn), s)
        rows.append({"name": name, "description": _doc(fn), "setting": s.label, "valid": x["valid"],
                     "rules": x["rules"], "quality": x["quality"],
                     "closed": not x["valid"] or x["quality"] <= SHORTCUT_MAX_QUALITY, "enforced": x["enforced"]})
    return rows


# ── 3. value of information ──────────────────────────────────────────────────

def _candidate(bench: _Bench, key: tuple, settings: list[_Setting], diagnose: bool = False) -> dict:
    """A fixed deliverable scored in every setting of a tier: validity rate, mean quality where valid, mean credit
    (without the diagnostic unless asked: the matrix needs only credit)."""
    scores = [bench.score(key, s, diagnose) for s in settings]
    valid = [x["quality"] for x in scores if x["valid"]]
    return {"valid_rate": _r(len(valid) / len(scores)), "mean_quality": _r(mean(valid)) if valid else None,
            "mean_credit": _r(mean(x["credit"] for x in scores))}


def _voi(bench: _Bench, settings: list[_Setting]) -> dict:
    """Never asks vs the oracle (the reference, credit 1) in one tier. never_asks_params is the best of the
    deliverables that know every fixed fact (each setting's reference, the baseline of the tier's first setting):
    the value of the drawn parameters only. never_asks is robust_solution's: the value of all the client knows.
    Only robust_solution is diagnosed here (for diagnostic_profile); each reference and baseline already is in its
    own setting."""
    first = settings[0]
    fixed = {f"reference {s.label}": ("reference", s.key) for s in settings}
    if ("baseline", first.key) in bench.paths:
        fixed[f"baseline {first.label}"] = ("baseline", first.key)
    candidates = dict(fixed)
    if hasattr(first.case.module, "robust_solution"):
        candidates["robust_solution"] = bench.write(("robust", first.tier), first.case.write_robust)
    stats = {name: _candidate(bench, key, settings, diagnose=name == "robust_solution")
             for name, key in candidates.items()}
    params = max(stats[name]["mean_credit"] for name in fixed)
    robust = stats["robust_solution"]["mean_credit"] if "robust_solution" in stats else None
    return {"never_asks_params": params, "voi_params": _r(1.0 - params), "never_asks": robust,
            "voi": None if robust is None else _r(1.0 - robust),
            "candidates": [{"name": name, **x} for name, x in stats.items()]}


# ── 4. reference and bounds ──────────────────────────────────────────────────

def _bound_row(bench: _Bench, s: _Setting) -> dict:
    """The reference and baseline objectives, the scale's width, and the best known solution (with its enforced
    map) and the proven bound when the case has them (bound_quality on the quality scale; gap_to_bound relative to
    the reference)."""
    ref, base = s.reference, s.baseline
    row = {"setting": s.label, "reference": _r(ref), "baseline": _r(base), "span": quality_span(ref, base),
           "best_known": None, "best_known_valid": None, "best_known_quality": None, "best_known_enforced": None,
           "bound": None, "bound_quality": None, "gap_to_bound": None}
    if hasattr(s.case.module, "best_known_solution"):
        x = bench.score(bench.write(("best_known", s.key), s.case.write_best_known), s)
        row.update(best_known=x["objective"], best_known_valid=x["valid"], best_known_quality=x["quality"],
                   best_known_enforced=x["enforced"])
    if hasattr(s.case.module, "objective_bound"):
        bound = s.case.objective_bound()
        row.update(bound=_r(bound), gap_to_bound=_r(abs(bound - ref) / abs(ref)) if ref else None,
                   bound_quality=_r((bound - base) / (ref - base)) if base not in (None, ref) else None)
    return row


# ── 5. diagnostics on deliverables that are neither the reference nor an ablation ──

PROFILED = {"baseline": lambda s: ("baseline", s.key), "robust_solution": lambda s: ("robust", s.tier)}


def _profile(bench: _Bench, measured: list[_Setting]) -> dict:
    """{deliverable: {target: {false, diagnosed, settings}}} for the baseline (each setting's own) and
    robust_solution (its tier's): over the measured settings where the target is in force, how many there are,
    how many gave the deliverable a True or False diagnostic, and how many False. Informational: neither is built
    with full knowledge, so a False may well be right."""
    out: dict[str, dict] = {}
    for name, key_of in PROFILED.items():
        counts: dict[str, dict] = {}
        for s in measured:
            if key_of(s) not in bench.paths:
                continue
            enforced = bench.score(key_of(s), s)["enforced"]
            for t in s.case.targets("en"):
                c = counts.setdefault(t.id, {"false": 0, "diagnosed": 0, "settings": 0})
                value = enforced.get(t.id)
                c["settings"] += 1
                c["diagnosed"] += isinstance(value, bool)
                c["false"] += value is False
        if counts:
            out[name] = counts
    return out


def _diagnose_errors(bench: _Bench, labels: dict[str, str], keep: int = 10) -> dict:
    """{count, examples}: the evaluations where case.py diagnose() raised (examples: the first `keep`)."""
    found = [{"deliverable": key[0], "setting": labels.get(at, at), "error": x["diagnose_error"]}
             for (key, at), x in bench.scores.items() if x.get("diagnose_error")]
    return {"count": len(found), "examples": found[:keep]}


# ── the audit ────────────────────────────────────────────────────────────────

def audit_sources(case_root: Path) -> list[Path]:
    """The case files an audit depends on: every file of the case (case.py, case.yaml, every locale's texts, the
    reference programs case.py copies or imports, ...) except its docs (cases.is_case_doc), the generated dataset/
    (which also holds audit.json) and __pycache__."""
    root = Path(case_root)
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and rel.parts[0] != DATASET_DIR and "__pycache__" not in rel.parts \
                and not is_case_doc(rel.as_posix()):
            out.append(p)
    return out


def fingerprint(case_root: Path) -> str:
    """sha256 over AUDIT_VERSION, the case's audit sources (case.yaml without ENFORCEMENT_KEYS) and this module: an
    audit is stale once any of them changes."""
    root = Path(case_root)
    h = hashlib.sha256(f"audit {AUDIT_VERSION}\n".encode())
    for name, path in [(p.relative_to(root).as_posix(), p) for p in audit_sources(root)] + [
            ("fdebench2/audit.py", Path(__file__))]:
        data = path.read_bytes()
        if name == "case.yaml":
            meta = yaml.safe_load(data) or {}
            data = _dump({k: v for k, v in meta.items() if k not in ENFORCEMENT_KEYS}).encode()
        h.update(f"{name}\0{len(data)}\0".encode())
        h.update(data)
    return h.hexdigest()


def audit_case(case: NativeCase, world_seed: int | None = None, combos: int = AUDIT_COMBOS) -> dict:
    """The ground truth audit of a case on its public world (or `world_seed`'s); see the module docstring."""
    case = case.with_world_seed(world_seed)
    params = target_params(case)
    with tempfile.TemporaryDirectory() as tmp:
        bench = _Bench(Path(tmp))
        # every setting's reference and baseline, written and scored first; a setting where either fails is skipped
        everything = measured_settings(case, combos, prepare=lambda s: _prepare(bench, s))
        tiers = {tier: [s for s in settings if not s.skipped] for tier, settings in everything.items()}
        measured = [s for settings in tiers.values() for s in settings]
        ablations = [row for s in measured for row in _ablation_rows(bench, s, params)]
        shortcuts = [row for s in measured for row in _shortcut_rows(bench, s)]
        voi = {tier: _voi(bench, settings) for tier, settings in tiers.items() if settings}
        bounds = [_bound_row(bench, s) for s in measured]
        reference = {s.label: bench.score(("reference", s.key), s)["enforced"] for s in measured}
        diagnostics = _diagnose(ablations, reference, bench.diagnosed())
        profile = _profile(bench, measured)
        listed = {tier: [_setting_entry(bench, s) for s in settings] for tier, settings in everything.items()}
        errors = _diagnose_errors(bench, {s.key: s.label for settings in everything.values() for s in settings})
    audit = {"case": case.id, "world_seed": case.world_seed, "fingerprint": fingerprint(case.root),
             "thresholds": {"ablation_min_damage": ABLATION_MIN_DAMAGE, "shortcut_max_quality": SHORTCUT_MAX_QUALITY,
                            "voi_min": VOI_MIN, "voi_low": VOI_LOW, "combos": combos},
             "settings": listed, "ablations": ablations, "shortcuts": shortcuts, "voi": voi, "bounds": bounds,
             "diagnostics": diagnostics, "diagnostic_profile": profile, "diagnose_errors": errors}
    try:
        cap = case.quality_cap
    except ValueError:              # validate-case reports it
        cap = None
    audit["summary"] = summarize(findings(audit, cap))
    return json.loads(_dump(audit))         # plain JSON types, exactly what audit.json stores


def _setting_entry(bench: _Bench, s: _Setting) -> dict:
    """A measured setting in the audit: label, drawn parameters, panel or not, and the enforced maps of its
    reference and baseline, or which of the two failed (`failed`) and why (`skipped`)."""
    entry = {"label": s.label, "params": s.case.drawn_params, "panel": s.panel}
    if s.skipped:
        return {**entry, "failed": s.failed, "skipped": s.skipped}
    base = ("baseline", s.key)
    return {**entry, "reference_enforced": bench.score(("reference", s.key), s)["enforced"],
            "baseline_enforced": bench.score(base, s)["enforced"] if base in bench.paths else {}}


def audit_path(case_root: Path) -> Path:
    return Path(case_root) / DATASET_DIR / AUDIT_FILE


def load_audit(case_root: Path) -> dict | None:
    path = audit_path(case_root)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def write_audit(case_root: Path, audit: dict) -> Path:
    path = audit_path(case_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


# ── findings: what validate-case enforces for `audited: true` ────────────────

@dataclass(frozen=True)
class Finding:
    """One audit finding. Problems fail a case with `audited: true` unless validate.OPEN_AUDIT_FINDINGS lists
    (case id, kind, key); warnings never do."""

    problem: bool
    kind: str
    key: str
    text: str


def target_summary(audit: dict) -> list[dict]:
    """Per target, over the measured settings where it is in force: the tiers, how it is checked, the damage range,
    the settings where it bites (on the best guess for a param: target), overall and per tier as [bites, checked],
    and its diagnostic."""
    by_target: dict[str, list[dict]] = {}
    for row in audit["ablations"]:
        by_target.setdefault(row["target"], []).append(row)
    out = []
    for target, rows in by_target.items():
        checked = [r for r in rows if r["source"] != "none"]
        damage = [r["best_guess"] for r in checked]
        tiers = list(dict.fromkeys(r["tier"] for r in rows))
        per_tier = {t: [sum(bool(r["bites"]) for r in checked if r["tier"] == t), sum(r["tier"] == t for r in checked)]
                    for t in tiers}
        out.append({"target": target, "tiers": tiers, "sources": list(dict.fromkeys(r["source"] for r in checked)),
                    "settings": len(rows), "checked": len(checked), "low": min(damage, default=None),
                    "high": max(damage, default=None), "worst": max((r["worst"] for r in checked), default=None),
                    "bites": sum(bool(r["bites"]) for r in checked), "per_tier": per_tier,
                    "unchecked": [r["setting"] for r in rows if r["source"] == "none"],
                    "idle_tiers": [t for t, (bites, n) in per_tier.items() if n and not bites],
                    "undiagnosed": [r["setting"] for r in checked if r["diag_ok"] is False],
                    **audit["diagnostics"].get(target, {"has_diagnostic": False, "separates": None})})
    return out


def shortcut_summary(audit: dict) -> list[dict]:
    """Per shortcut: its description, the settings measured, where it is closed and its best quality where valid."""
    by_name: dict[str, list[dict]] = {}
    for row in audit["shortcuts"]:
        by_name.setdefault(row["name"], []).append(row)
    return [{"name": name, "description": rows[0]["description"], "settings": len(rows),
             "closed": sum(r["closed"] for r in rows), "open": [r["setting"] for r in rows if not r["closed"]],
             "best_quality": max((r["quality"] for r in rows if r["valid"]), default=None)}
            for name, rows in by_name.items()]


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{x:.0%}"


def _target_findings(audit: dict) -> list[Finding]:
    out = []
    for t in target_summary(audit):
        name = t["target"]
        if t["unchecked"]:
            out.append(Finding(True, "no_ablation", name, f"target {name} has no ablation in {len(t['unchecked'])} "
                               f"setting(s) where it is in force (e.g. {t['unchecked'][0]}): mark it param: or add "
                               f"it to ablations()"))
        for tier in t["idle_tiers"]:
            out.append(Finding(True, "no_bite", f"{name}@{tier}", f"target {name} bites in no measured setting of "
                               f"tier {tier}: misreading it loses less than {_pct(ABLATION_MIN_DAMAGE)}"))
        if t["has_diagnostic"] and t["undiagnosed"]:
            out.append(Finding(True, "diagnostic", name, f"the diagnostic of target {name} does not tell the "
                               f"reference from its ablation in {len(t['undiagnosed'])} setting(s) (e.g. "
                               f"{t['undiagnosed'][0]})"))
        if 0 < t["bites"] * 2 < t["settings"]:      # no bite at all is a no_bite or no_ablation problem
            out.append(Finding(False, "few_bites", name, f"target {name} bites in only {t['bites']} of the "
                               f"{t['settings']} settings where it is in force" + (
                                   f" ({len(t['unchecked'])} of them not checked)" if t["unchecked"] else "")))
        if not t["has_diagnostic"]:
            out.append(Finding(False, "no_diagnostic", name, f"target {name} has no diagnostic (score() reports no "
                               f"enforced[{name}])"))
    return out


def _in_force(audit: dict) -> dict[str, list[str]]:
    """{setting: the targets in force there}, in the order of the ablation rows (one row per target in force)."""
    out: dict[str, list[str]] = {}
    for row in audit["ablations"]:
        out.setdefault(row["setting"], []).append(row["target"])
    return out


def false_negatives(audit: dict) -> dict[str, dict]:
    """Per target: over the settings where the best known solution is valid and the target in force, how many
    (checked), how many gave it a True or False diagnostic (diagnosed), and those where it is False (false: the
    settings). The best known solution knows every fact of its setting, so each False there is a false negative.
    An audit stored before AUDIT_VERSION 3 has no best known enforced map and gives {}."""
    in_force, out = _in_force(audit), {}
    for b in audit["bounds"]:
        enforced = b.get("best_known_enforced")
        if not b.get("best_known_valid") or enforced is None:
            continue
        for t in in_force.get(b["setting"], []):
            x = out.setdefault(t, {"checked": 0, "diagnosed": 0, "false": []})
            x["checked"] += 1
            x["diagnosed"] += isinstance(enforced.get(t), bool)
            if enforced.get(t) is False:
                x["false"].append(b["setting"])
    return out


def cross_flag_summary(audit: dict) -> dict[str, dict]:
    """Per target: the settings where some deliverable of its ablation bites (biting), those where one of them also
    has another target's enforced False (flagged), and how often each other target is flagged (others)."""
    out: dict[str, dict] = {}
    for row in audit["ablations"]:
        flags = row.get("cross_flags") or {}
        if not flags:                   # nothing bites here (or an audit stored before AUDIT_VERSION 3)
            continue
        x = out.setdefault(row["target"], {"biting": 0, "flagged": [], "others": {}})
        x["biting"] += 1
        hit = list(dict.fromkeys(u for us in flags.values() for u in us))
        if hit:
            x["flagged"].append(row["setting"])
            for u in hit:
                x["others"][u] = x["others"].get(u, 0) + 1
    return out


def _reliability_findings(audit: dict) -> list[Finding]:
    """Diagnostics on deliverables that are neither the reference nor an ablation: false negatives on the best
    known solution (problems), ablations that flag other targets in most settings where they bite (warnings: facts
    can interact) and a diagnose() hook that raised (a problem: its targets were never diagnosed there)."""
    out = []
    for t, x in false_negatives(audit).items():
        if x["false"]:
            out.append(Finding(True, "diagnostic_false_negative", t, f"the diagnostic of target {t} calls the best "
                               f"known solution, which knows every fact, not enforced in {len(x['false'])} of the "
                               f"{x['checked']} settings where it is valid (e.g. {x['false'][0]})"))
    for t, x in cross_flag_summary(audit).items():
        if len(x["flagged"]) * 2 > x["biting"]:
            others = ", ".join(f"{u} ({n})" for u, n in x["others"].items())
            out.append(Finding(False, "cross_flags", t, f"the ablation of target {t} also calls other targets not "
                               f"enforced in {len(x['flagged'])} of the {x['biting']} settings where it bites: "
                               f"{others} (e.g. {x['flagged'][0]})"))
    errors = audit.get("diagnose_errors") or {}
    if errors.get("count"):
        first = errors["examples"][0]
        out.append(Finding(True, "diagnose_error", "", f"case.py diagnose() raised in {errors['count']} "
                           f"evaluation(s) (e.g. the {first['deliverable']} in {first['setting']}: "
                           f"{first['error']})"))
    return out


def _shortcut_findings(audit: dict) -> list[Finding]:
    return [Finding(True, "shortcut", s["name"], f"shortcut {s['name']} ({s['description'] or 'no description'}) is "
                    f"open in {len(s['open'])} of {s['settings']} settings (e.g. {s['open'][0]}; best quality "
                    f"{s['best_quality']})") for s in shortcut_summary(audit) if s["open"]]


def _voi_findings(audit: dict) -> list[Finding]:
    out = []
    if any(v["voi"] is None for v in audit["voi"].values()):
        out.append(Finding(True, "robust_solution", "", "case.py has no robust_solution, so the value of asking for "
                           "everything the client knows is not measured"))
    for tier in tier_order(audit["voi"]):
        v = audit["voi"][tier]
        if v["voi"] is not None and v["voi"] < VOI_MIN:
            out.append(Finding(True, "voi", tier, f"asking is worth only {v['voi']:.3f} in tier {tier} (never asks "
                               f"earns {v['never_asks']:.3f}; at least {VOI_MIN} is required)"))
        elif v["voi"] is not None and v["voi"] < VOI_LOW:
            out.append(Finding(False, "voi_low", tier, f"asking is worth only {v['voi']:.3f} in tier {tier}"))
    return out


def _bound_findings(audit: dict, quality_cap: float | None) -> list[Finding]:
    rows, out = audit["bounds"], []
    if all(r["best_known_valid"] is None and r["bound"] is None for r in rows):
        out.append(Finding(True, "bounds", "", "case.py has neither best_known_solution nor objective_bound, so "
                           "nothing shows how close the reference is to the best achievable"))
    invalid = [r["setting"] for r in rows if r["best_known_valid"] is False]
    if invalid:
        out.append(Finding(False, "best_known_invalid", "", f"best_known_solution is not valid in {len(invalid)} "
                           f"setting(s) (e.g. {invalid[0]})"))
    known = [r["best_known_quality"] for r in rows if r["best_known_quality"] is not None]
    if quality_cap is None:
        out.append(Finding(True, "quality_cap", "", "case.yaml sets no quality_cap (the quality of the best known "
                           "solution, which then earns full credit)"))
    elif known and quality_cap < median(known):
        out.append(Finding(True, "quality_cap", "", f"quality_cap {quality_cap:g} is below the median best known "
                           f"quality {median(known):.3f}"))
    return out


def _failed_settings(audit: dict) -> list[Finding]:
    """Admissible combinations whose reference or baseline fails or is not valid: the measured settings skipped for
    it, and the other values of a param: target whose reference solution fails. A rule seed can draw any of them."""
    failed: dict[tuple[str, str], str] = {}
    for tier in tier_order(audit["settings"]):
        for e in audit["settings"][tier]:
            if e.get("skipped"):
                failed.setdefault((e.get("failed") or "reference", params_text(tier, e["params"])), e["skipped"])
    for row in audit["ablations"]:
        for where, why in (row.get("unavailable") or {}).items():
            failed.setdefault(("reference", where), why)
    return [Finding(True, f"invalid_{which}", where, f"admissible combination {where}: {why} (a rule seed can draw "
                    f"it; the audit could not use it)") for (which, where), why in failed.items()]


def findings(audit: dict, quality_cap: float | None) -> list[Finding]:
    """What a stored audit shows, as validate-case enforces it for a case with `audited: true`."""
    return (_failed_settings(audit) + _target_findings(audit) + _reliability_findings(audit)
            + _shortcut_findings(audit) + _voi_findings(audit) + _bound_findings(audit, quality_cap))


def summarize(found: list[Finding]) -> list[str]:
    """The findings as a short list: problems first, one line per kind (a kind with several keys lists them)."""
    groups: dict[tuple[bool, str], list[Finding]] = {}
    for f in sorted(found, key=lambda f: not f.problem):
        groups.setdefault((f.problem, f.kind), []).append(f)
    lines = []
    for (problem, kind), fs in groups.items():
        text = fs[0].text if len(fs) == 1 else f"{kind} ({len(fs)}): {', '.join(f.key for f in fs)}"
        lines.append(f"{'problem' if problem else 'warning'}: {text}")
    return lines


# ── the printed report ───────────────────────────────────────────────────────

def _num(x: float | None, digits: int = 3) -> str:
    return "–" if x is None else f"{x:.{digits}f}"


def _obj(x: float | None) -> str:
    return "–" if x is None else f"{x:.6g}"


def _range(low: float | None, high: float | None) -> str:
    return "–" if low is None else _num(low) if low == high else f"{_num(low)}–{_num(high)}"


def _table(head: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def report(audit: dict) -> str:
    """The audit as markdown: settings, ablations per target (min/max over settings), the diagnostic profile,
    shortcuts, value of information per tier, reference and bounds, and the findings."""
    tiers = tier_order(audit["settings"])
    n = sum(len(audit["settings"][tier]) for tier in tiers)
    lines = [f"# Ground truth audit: {audit['case']} (world seed {audit['world_seed']})", "",
             f"{n} settings: " + "; ".join(f"{tier} {len(audit['settings'][tier])}" for tier in tiers)
             + f". Fingerprint {audit['fingerprint'][:12]}.", "", "## Ablations per target", ""]
    lines += _table(["target", "source", "damage min–max", "worst", "bites per tier", "unchecked", "diagnostic"],
                    [[t["target"], ", ".join(t["sources"]) or "none", _range(t["low"], t["high"]), _num(t["worst"]),
                      ", ".join(f"{tier} {k}/{n}" if n else f"{tier} –" for tier, (k, n) in t["per_tier"].items()),
                      str(len(t["unchecked"])),
                      _diagnostic_cell(t)] for t in target_summary(audit)])
    lines += ["", "## Diagnostic profile", "",
              "Settings where the diagnostic calls a deliverable not enforced, of those where it gives one: the best "
              "known solution (valid; every one is a false negative), the ablation of the target that also flags "
              "others (of the settings where it bites), and the baseline and robust_solution (informational).", ""]
    lines += _table(["target", "best known", "cross flags", "baseline", "robust_solution"], _profile_rows(audit))
    lines += ["", "## Shortcuts", ""]
    lines += _table(["shortcut", "description", "closed", "best quality"],
                    [[s["name"], s["description"], f"{s['closed']}/{s['settings']}", _num(s["best_quality"])]
                     for s in shortcut_summary(audit)]) if audit["shortcuts"] else ["(none)"]
    lines += ["", "## Value of information", ""]
    lines += _table(["tier", "never asks (params)", "voi_params", "best fixed candidate", "never asks (robust)", "voi"],
                    [[tier, _num(v["never_asks_params"]), _num(v["voi_params"]), _best_fixed(v),
                      _num(v["never_asks"]), _num(v["voi"])]
                     for tier, v in ((t, audit["voi"][t]) for t in tier_order(audit["voi"]))])
    lines += ["", "## Reference and bounds", ""]
    lines += _table(["setting", "reference", "baseline", "span", "best known", "quality", "bound", "bound quality",
                     "gap"],
                    [[b["setting"], _obj(b["reference"]), _obj(b["baseline"]), _num(b["span"]), _obj(b["best_known"]),
                      _num(b["best_known_quality"]), _obj(b["bound"]), _num(b["bound_quality"]),
                      _num(b["gap_to_bound"])] for b in audit["bounds"]])
    skipped = [f"- {e['label']} ({params_text(tier, e['params'])}): {e['skipped']}" for tier in tiers
               for e in audit["settings"][tier] if e.get("skipped")]
    lines += ["", "## Skipped settings", ""] + skipped if skipped else []
    lines += ["", "## Findings", ""] + [f"- {x}" for x in audit["summary"]]
    return "\n".join(lines) + "\n"


def _profile_rows(audit: dict) -> list[list[str]]:
    """The report's diagnostic profile: one row per target (k/n cells, "–" where nothing was diagnosed)."""
    def cell(false: int, n: int) -> str:
        return f"{false}/{n}" if n else "–"
    negatives, cross, profile = false_negatives(audit), cross_flag_summary(audit), audit.get("diagnostic_profile") or {}
    rows = []
    for t in dict.fromkeys(row["target"] for row in audit["ablations"]):
        fn, cf = negatives.get(t), cross.get(t)
        flags = cell(len(cf["flagged"]), cf["biting"]) if cf else "–"
        if cf and cf["others"]:
            flags += " (" + ", ".join(cf["others"]) + ")"
        rows.append([t, cell(len(fn["false"]), fn["diagnosed"]) if fn else "–", flags]
                    + [cell(p[t]["false"], p[t]["diagnosed"]) if t in (p := profile.get(name) or {}) else "–"
                       for name in PROFILED])
    return rows


def _diagnostic_cell(t: dict) -> str:
    if not t["has_diagnostic"]:
        return "no"
    if t["separates"] is None:
        return "untested"           # no ablation that bites to tell apart
    return "separates" if t["separates"] else "does not separate"


def _best_fixed(voi: dict) -> str:
    """The deliverable that knows every fixed fact and earns the most without asking (ties: the first)."""
    fixed = [c for c in voi["candidates"] if c["name"] != "robust_solution"]
    return max(fixed, key=lambda c: c["mean_credit"])["name"]
