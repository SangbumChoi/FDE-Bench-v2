"""`fdebench2 submit`: a campaign's results as one leaderboard submission (docs/SUBMITTING.md has the format).

A submission is one JSON file: the system (name, model, harness, its version and disclosed flags, the date), the
benchmark it ran on (git commit and a hash of every case's files, so results are comparable), one record per run
(case × tier × rule seed × trial, with its final score, validity, normalized quality, Ask-F1, the target funnel's
revealed / learned / enforced counts and cost) and the aggregate means with 95% case-bootstrap intervals, computed
the way `fdebench2 report` computes them (case-macro: within a case, every rule seed weighs the same).

A rule seed in a case's public panel (case.yaml rule_seeds) is public: its answers are stored in the repository.
A submission is ranked only when it ran a leaderboard round (leaderboard/rounds.yaml): every case, at each of the
round's tiers and rule seeds, with at least MIN_TRIALS trials, on the round's track (English client and agent, the
baseline policy, standard engagement). Every system in a round therefore answers the same settings, and nobody
picks their own seeds. Any other submission is marked "development". Without a rounds file (a fork, a test) the
rule is: private rule seeds only, MIN_TRIALS trials.

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

import yaml

from .cases import NativeCase, discover
from .runner import NOT_SCORED, framework_version, never_in_a_run, tree_hash
from .scoring.report import _agent, _usage, _without, bootstrap_ci, load_results, rule_seed, status

FORMAT = "fdebench2-submission/1"
MIN_TRIALS = 3
ROUNDS_FILE = "leaderboard/rounds.yaml"       # next to the cases folder
TRACK = {"customer_locale": "en", "agent_locale": "en", "policy": "baseline", "engagement": "standard"}
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


def load_rounds(path: Path | None) -> list[dict[str, Any]]:
    """The leaderboard rounds, newest last: [{id, opened, rule_seeds: [...], tiers: [...]}]; [] without the file."""
    if path is None or not Path(path).is_file():
        return []
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return list(doc.get("rounds") or [])


def _round_gaps(records: list[dict[str, Any]], rnd: dict[str, Any], case_ids: Iterable[str]) -> list[str]:
    """Why these runs are not the round's track: runs off the track, and missing (case, tier, rule seed) cells."""
    reasons = []
    off = sum(any(x.get(k) != v for k, v in TRACK.items()) for x in records)
    if off:
        reasons.append(f"{off} run(s) off the round's track (English client and agent, the baseline policy, "
                       f"standard engagement)")
    count: dict[tuple, int] = defaultdict(int)
    for x in records:
        count[(x["case"], x["tier"], x["rule_seed"])] += 1
    cells = [(c, t, s) for c in sorted(case_ids) for t in rnd["tiers"] for s in rnd["rule_seeds"]]
    missing = [cell for cell in cells if count[cell] < MIN_TRIALS]
    if missing:
        c, t, sd = missing[0]
        reasons.append(f"round {rnd['id']} asks for every case at tiers {', '.join(rnd['tiers'])} and rule seeds "
                       f"{rnd['rule_seeds']} with {MIN_TRIALS} trials: {len(missing)} of {len(cells)} are missing "
                       f"(e.g. {c} {t}/s{sd})")
    return reasons


def ranking_status(records: list[dict[str, Any]], min_trials: int, rounds: list[dict[str, Any]] | None = None,
                   case_ids: Iterable[str] = ()) -> tuple[str, list[str], str | None]:
    """("ranked", [], round id or None) or ("development", the reasons, None)."""
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
    round_id = None
    if rounds:
        used = {x["rule_seed"] for x in records}
        rnd = next((r for r in reversed(rounds) if set(r["rule_seeds"]) == used), None)
        if rnd is None:
            listed = "; ".join(f"{r['id']}: {r['rule_seeds']}" for r in rounds)
            reasons.append(f"the rule seeds are not those of a leaderboard round ({listed})")
        else:
            reasons += _round_gaps(records, rnd, case_ids)
            round_id = str(rnd["id"])
    reasons = list(dict.fromkeys(reasons))
    return ("development", reasons, None) if reasons else ("ranked", [], round_id)


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
    """Every run's result.json under a campaign's results directory (report.load_results)."""
    return load_results(Path(out))


def build_submission(results_dir: Path, *, name: str, model: str | None = None, harness: str | None = None,
                     version: str = "", flags: Iterable[str] | dict[str, Any] = (), date: str | None = None,
                     agent: str | None = None, cases_root: Path = Path("cases"),
                     rounds_file: Path | None = None) -> dict[str, Any]:
    """The submission of one agent's runs under `results_dir` (a campaign's out/<agent>/<run key>/result.json).
    `rounds_file`: the leaderboard rounds (default: leaderboard/rounds.yaml next to the cases folder)."""
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
    rounds = load_rounds(rounds_file if rounds_file is not None else Path(cases_root).resolve().parent / ROUNDS_FILE)
    st, reasons, round_id = ranking_status(records, trials, rounds, cases)
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
        "round": round_id,
        "aggregate": aggregate(records),
        "runs": records,
    }


def anchor_submission(cases_root: Path, case_ids: list[str] | None = None, tiers: Iterable[str] = ("medium",),
                      date: str | None = None, round_id: str | None = None,
                      rounds_file: Path | None = None) -> dict[str, Any]:
    """The cases' anchors (literal solution, baseline, reference) scored offline, as `fdebench2 try` scores them;
    one record per anchor and setting. Without `round_id`: every public rule seed of `tiers`, marked as an example.
    With it: that leaderboard round's tiers and rule seeds, the reference rows of the round."""
    rnd = None
    if round_id is not None:
        rounds = load_rounds(rounds_file if rounds_file is not None
                             else Path(cases_root).resolve().parent / ROUNDS_FILE)
        rnd = next((r for r in rounds if str(r["id"]) == str(round_id)), None)
        if rnd is None:
            raise ValueError(f"no leaderboard round {round_id!r}; known: {[str(r['id']) for r in rounds]}")
        tiers = rnd["tiers"]
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
        seeds = rnd["rule_seeds"] if rnd else base.rule_seeds
        settings = [base.at(t, s) for t in tiers if t in base.tiers for s in seeds] if base.tiers else [base]
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
        "example": rnd is None,
        "round": str(rnd["id"]) if rnd else None,
        "system": {"name": (f"Anchors of round {rnd['id']} (literal solution, baseline, reference), not a model"
                            if rnd else "EXAMPLE: anchors (literal solution, baseline, reference), not a model"),
                   "model": None,
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
