"""`fdebench2 submit`: a campaign's results as one leaderboard submission (docs/SUBMITTING.md has the format).

A submission is one JSON file: the system (name, model, harness, its version and disclosed flags, the date), the
benchmark it ran on (git commit and a hash of every case's files, so results are comparable), one record per run
(case × tier × rule seed × trial, with its final score, validity, normalized quality, Ask-F1, the target funnel's
revealed / learned / enforced counts and cost) and the aggregate means with 95% case-bootstrap intervals, computed
the way `fdebench2 report` computes them (case-macro: within a case, every rule seed weighs the same).

A rule seed in a case's public panel (case.yaml rule_seeds) is public: its answers are stored in the repository.
Only a submission whose every run used a private rule seed, with at least MIN_TRIALS trials of every variant, is
ranked; any other is marked "development".

`anchor_submission` scores the cases' own anchors (literal solution, baseline, reference) offline, as `fdebench2
try` does, in the same format with `kind: anchors`: the leaderboard shows them as reference rows.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .cases import NativeCase, discover
from .runner import NOT_SCORED, framework_version, never_in_a_run, tree_hash
from .scoring.report import _agent, _usage, _without, bootstrap_ci, load_results, rule_seed, status

FORMAT = "fdebench2-submission/1"
MIN_TRIALS = 3
STAGES = ("revealed", "learned", "enforced")
METRICS = ("final", "validity", "quality", "ask_f1", "enforced_share", "cost_usd", "total_tokens")


def _git(repo: Path, *args: str) -> str:
    from .site import _git as git
    return git(repo, *args)


def benchmark_fingerprint(cases_root: Path, case_ids: Iterable[str]) -> dict[str, Any]:
    """What the results were measured on: the framework version, the repository's git commit (and whether the
    cases, framework or configs had uncommitted changes) and a hash of each case's files, the same hash a run's
    fingerprint uses (case files except the docs and the stored audit)."""
    root = Path(cases_root).resolve()
    cases = discover(root)
    repo = root.parent
    return {"framework_version": framework_version(),
            "git_commit": _git(repo, "rev-parse", "HEAD") or None,
            "git_dirty": bool(_git(repo, "status", "--porcelain", "--", "cases", "fdebench2", "configs")),
            "cases": {cid: tree_hash(cases[cid].root, never_in_a_run) if cid in cases else None
                      for cid in sorted(set(case_ids))}}


def seed_kind(case: Any, seed: int | None) -> str | None:
    """"public" (in the case's public panel), "private" (any other int), None (a case without settings), or
    "unknown" when the case is not in this benchmark version."""
    if case is None:
        return "unknown"
    if seed is None or not case.tiers:
        return None
    return "public" if seed in case.rule_seeds else "private"


def _counts(targets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The target funnel of one run: how many targets, and per stage how many passed and how many were measured."""
    out: dict[str, Any] = {"n": len(targets)}
    for stage in STAGES:
        values = [t.get(stage) for t in targets.values()]
        out[stage] = sum(v is True for v in values)
        out[f"{stage}_measured"] = sum(v is not None for v in values)
    return out


def run_record(r: dict[str, Any], cases: dict[str, Any]) -> dict[str, Any]:
    """One run of a result.json, as a submission records it."""
    spec = r.get("spec") or {}
    case_id = spec.get("case_id")
    seed = rule_seed(r)
    st = status(r)
    score = r.get("score") if st not in NOT_SCORED else None
    tokens, cost = _usage(r) if score else (None, None)
    funnel = _counts(r.get("targets") or {})
    clar = r.get("clarification") or {}
    return {
        "case": case_id, "tier": r.get("tier") or spec.get("difficulty"), "rule_seed": seed,
        "seeds": seed_kind(cases.get(case_id), seed), "trial": spec.get("trial", 0),
        "noise_seed": spec.get("noise_seed", spec.get("seed", 0)),
        **{k: spec.get(k) for k in ("customer_locale", "agent_locale", "policy", "engagement", "condition",
                                    "world_seed")},
        "status": st,
        "final": score["final"] if score else None,
        "valid": bool(score["gates"].get("validity")) if score else None,
        "quality": score.get("quality_raw") if score else None,
        "ask_f1": clar.get("ask_f1") if score else None,
        "targets": funnel,
        "enforced_share": (funnel["enforced"] / funnel["enforced_measured"]
                           if score and funnel["enforced_measured"] else None),
        "cost_usd": cost, "total_tokens": tokens,
        "fingerprint": r.get("fingerprint"),
    }


def _metric(rec: dict[str, Any], key: str) -> float | None:
    if key == "validity":
        return None if rec["valid"] is None else float(rec["valid"])
    return rec.get(key)


def _case_values(records: list[dict[str, Any]], key: str) -> list[float]:
    """One value per case: the mean over its rule seeds of the mean over each seed's runs (report._seed_mean)."""
    by_case: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for rec in records:
        value = _metric(rec, key)
        if value is not None:
            by_case[rec["case"]][str(rec["rule_seed"])].append(float(value))
    return [mean(mean(v) for v in seeds.values()) for seeds in by_case.values()]


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Case-macro means of the scored runs with their 95% case-bootstrap intervals, and the run counts."""
    scored = [x for x in records if x["status"] not in NOT_SCORED]
    out: dict[str, Any] = {"n_runs": len(records), "n_scored": len(scored), "n_cases": len({x["case"] for x in scored}),
                           "statuses": {s: n for s in sorted({x["status"] for x in records})
                                        if (n := sum(x["status"] == s for x in records))}}
    for key in METRICS:
        values = _case_values(scored, key)
        out[key] = ({"mean": round(mean(values), 6), "ci": [round(v, 6) for v in bootstrap_ci(values)],
                     "n_cases": len(values)} if values else {"mean": None, "ci": [None, None], "n_cases": 0})
    return out


def _trials(results: list[dict[str, Any]]) -> int:
    """The fewest trials any variant ran (scored or not)."""
    groups: dict[str, int] = defaultdict(int)
    for r in results:
        groups[_without(r, "trial")] += 1
    return min(groups.values(), default=0)


def seeds_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = {x["seeds"] for x in records if x["seeds"] is not None}
    kind = "none" if not kinds else kinds.pop() if len(kinds) == 1 else "mixed"
    return {"kind": kind,
            "public": sorted({x["rule_seed"] for x in records if x["seeds"] == "public"}),
            "private": sorted({x["rule_seed"] for x in records if x["seeds"] == "private"})}


def ranking_status(records: list[dict[str, Any]], min_trials: int) -> tuple[str, list[str]]:
    """("ranked", []) or ("development", the reasons)."""
    reasons = []
    kinds = {x["seeds"] for x in records}
    if "public" in kinds:
        reasons.append("public rule seeds: their answers are in the repository")
    if "unknown" in kinds:
        reasons.append("cases that are not in this benchmark version")
    if not kinds & {"private"}:
        reasons.append("no run on a private rule seed")
    if min_trials < MIN_TRIALS:
        reasons.append(f"{min_trials} trial(s) per variant, fewer than {MIN_TRIALS}")
    return ("development" if reasons else "ranked"), list(dict.fromkeys(reasons))


def _flags(flags: Iterable[str] | dict[str, Any]) -> dict[str, str]:
    if isinstance(flags, dict):
        return {str(k): str(v) for k, v in flags.items()}
    out = {}
    for f in flags:
        key, sep, value = f.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"--flag {f!r}: write it as KEY=VALUE")
        out[key.strip()] = value.strip()
    return out


def _date(date: str | None) -> str:
    if date is None:
        return dt.datetime.now(dt.timezone.utc).date().isoformat()
    return dt.date.fromisoformat(date).isoformat()


def load_runs(out: Path) -> list[dict[str, Any]]:
    """Every run's result.json under a campaign's results directory: out/<agent>/<run key>/result.json, where a run
    key holds its case id `<field>/<role>`, so a campaign's run directory is out/<agent>/<field>/<role>__c-.../
    (report.load_results reads out/*/*/result.json only). Never a result.json an agent left in its workspace."""
    found = load_results(out)
    for p in sorted(Path(out).glob("*/*/*/result.json")):
        if "__c-" in p.parent.name:                      # a run directory, not a run's workspace/ or submission/
            r = json.loads(p.read_text(encoding="utf-8"))
            if "ruleset" in r or "ruleset" in (r.get("spec") or {}):
                raise ValueError(f"{p}: this run was scored under a rule set, before rule seeds replaced rule "
                                 f"sets; run it again")
            found.append(r)
    return found


def build_submission(results_dir: Path, *, name: str, model: str | None = None, harness: str | None = None,
                     version: str = "", flags: Iterable[str] | dict[str, Any] = (), date: str | None = None,
                     agent: str | None = None, cases_root: Path = Path("cases")) -> dict[str, Any]:
    """The submission of one agent's runs under `results_dir` (a campaign's out/<agent>/<run key>/result.json)."""
    results = load_runs(Path(results_dir))
    if not results:
        raise ValueError(f"{results_dir}: no results (expected <agent>/<run key>/result.json)")
    agents = sorted({_agent(r) for r in results})
    if agent is None and len(agents) > 1:
        raise ValueError(f"{results_dir} holds runs of several agents {agents}: pick one with --agent")
    label = agent or agents[0]
    results = [r for r in results if _agent(r) == label]
    if not results:
        raise ValueError(f"{results_dir}: no runs of agent {label!r}; found {agents}")
    cases = discover(cases_root)
    records = sorted((run_record(r, cases) for r in results),
                     key=lambda x: (x["case"], x["tier"] or "", str(x["rule_seed"]), x["noise_seed"], x["trial"]))
    trials = _trials(results)
    st, reasons = ranking_status(records, trials)
    spec_agent = results[0]["agent"]
    return {
        "format": FORMAT,
        "kind": "system",
        "example": False,
        "system": {"name": name, "model": model or spec_agent.get("model"),
                   "harness": harness or spec_agent.get("harness"), "version": version,
                   "agent_label": label, "max_steps": spec_agent.get("max_steps"), "flags": _flags(flags),
                   "date": _date(date)},
        "benchmark": benchmark_fingerprint(cases_root, {x["case"] for x in records}),
        "seeds": seeds_summary(records),
        "trials": trials,
        "status": st,
        "status_reasons": reasons,
        "aggregate": aggregate(records),
        "runs": records,
    }


def anchor_submission(cases_root: Path, case_ids: list[str] | None = None, tiers: Iterable[str] = ("medium",),
                      date: str | None = None) -> dict[str, Any]:
    """The cases' anchors (literal solution, baseline, reference) scored offline on every public rule seed of
    `tiers`, as `fdebench2 try` scores them; one record per anchor and setting."""
    from .tryout import ANCHORS, DEFAULT_POLICY, anchor_writers, score_anchor
    from .transforms.policy import load_policy
    from . import program

    program.configure("local")
    policy = load_policy(DEFAULT_POLICY)
    found = discover(cases_root)
    ids = case_ids or sorted(found)
    records: list[dict[str, Any]] = []
    for cid in ids:
        base: NativeCase = found[cid]
        settings = ([base.at(t, s) for t in tiers if t in base.tiers for s in base.rule_seeds] if base.tiers
                    else [base])
        for case in settings:
            for name in anchor_writers(case):
                s = score_anchor(case, name, "en", policy, diagnose=True)
                funnel = _counts({t: {"enforced": v} for t, v in (s.evaluation.get("enforced") or {}).items()})
                records.append({"anchor": name, "case": cid, "tier": case.tier, "rule_seed": case.rule_seed,
                                "seeds": seed_kind(case, case.rule_seed), "trial": 0, "noise_seed": 0,
                                "customer_locale": "en", "agent_locale": "en", "policy": policy.id,
                                "engagement": "standard", "condition": None, "world_seed": None,
                                "status": "ok" if s.valid else "invalid", "final": s.final, "valid": s.valid,
                                "quality": s.score["quality_raw"], "ask_f1": 0.0, "targets": funnel,
                                "enforced_share": (funnel["enforced"] / funnel["enforced_measured"]
                                                   if funnel["enforced_measured"] else None),
                                "cost_usd": None, "total_tokens": None, "fingerprint": None})
    return {
        "format": FORMAT,
        "kind": "anchors",
        "example": True,
        "system": {"name": "EXAMPLE: anchors (literal solution, baseline, reference), not a model", "model": None,
                   "harness": None, "version": "", "agent_label": None, "max_steps": None,
                   "flags": {"scored": "offline, as `fdebench2 try` scores them: no client conversation, Ask-F1 0"},
                   "date": _date(date)},
        "benchmark": benchmark_fingerprint(cases_root, ids),
        "seeds": seeds_summary(records),
        "trials": 1,
        "status": "anchor",
        "status_reasons": ["the cases' own anchors, shown as reference rows; never ranked"],
        "anchors": {name: aggregate([x for x in records if x["anchor"] == name]) for name in ANCHORS
                    if any(x["anchor"] == name for x in records)},
        "runs": records,
    }


def write_submission(doc: dict[str, Any], out: Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return out


def load_submission(path: Path) -> dict[str, Any]:
    """A submission file, checked for the fields the leaderboard reads."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("format") != FORMAT:
        raise ValueError(f"{path}: format must be {FORMAT!r}, got {doc.get('format')!r}")
    if doc.get("kind") == "anchors":
        if not isinstance(doc.get("anchors"), dict):
            raise ValueError(f"{path}: an anchors file needs `anchors`")
    elif not isinstance(doc.get("aggregate"), dict) or not (doc.get("system") or {}).get("name"):
        raise ValueError(f"{path}: a submission needs `system.name` and `aggregate`")
    return doc
