"""Aggregate result.json files into per-axis tables.

Deltas are computed within an agent (same model, same harness) against the
baseline cell, never across agents, so adding agents adds evidence without
confounding.

The difficulty table has one column per difficulty (tier) and is shown when
difficulties differ or a case has settings. A case's score in a column is the
mean over its rule seeds (each a ground truth of the same data: the public
panel, or private seeds) of the mean over that seed's runs (noise seeds,
trials); columns are case-macro averages, and the per-axis tables weigh a
case's rule seeds the same way. "all valid" is the share of (case, noise seed,
trial, ...) cells valid under every rule seed of the tier.
The settings table lists every (case, tier, rule seed) with the parameters that
seed drew, its mean final score and how many of its runs were valid.

With few cases, differences between agents are noisy: every mean comes with a
95% bootstrap interval over cases (cases resampled with replacement, fixed
seed), so a gap smaller than the intervals is not evidence of a difference.

Runs that ended in a harness or infrastructure error say nothing about the
agent: they are counted per agent and listed, never averaged in as 0. With
repeated trials, pass^k (τ-bench) is the chance that k trials of one variant,
drawn from the n that ran, all pass the validity gate: C(c, k) / C(n, k) for c
passes, averaged over the variants that ran more than once and then over
cases, for k up to the fewest trials among those variants (at most 4).
"""

from __future__ import annotations

import json
from collections import defaultdict
from math import comb
from pathlib import Path
from statistics import mean
from typing import Any

from ..runner import NOT_SCORED, STATUSES

AXES = ("customer_locale", "agent_locale", "policy", "difficulty", "rule_seed", "engagement", "condition")
SETTING_KEYS = ("rule_seed", "ruleset")      # a run's rule seed (results from before rule seeds: its rule set)
TIERS = ("easy", "medium", "hard")
BOOT = 2000


def bootstrap_ci(values: list[float], n: int = BOOT, seed: int = 0) -> tuple[float, float]:
    """95% percentile interval of the mean, resampling the values (one per case) with replacement."""
    import random
    if len(values) < 2:
        return (values[0], values[0]) if values else (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def pass_hat_k(n: int, c: int, k: int) -> float:
    """τ-bench estimator: the chance that k of n trials (c of them passing), drawn without replacement, all pass."""
    return comb(c, k) / comb(n, k)


def _fmt(values: list[float]) -> str:
    lo, hi = bootstrap_ci(values)
    return f"{mean(values):.3f} [{lo:.2f}–{hi:.2f}]"


def _num(x: float | None, digits: int = 3) -> str:
    return "–" if x is None else f"{x:.{digits}f}"


def load_results(out: Path) -> list[dict[str, Any]]:
    """Every out/<agent>/<run key>/result.json (never a file of that name an agent left in its workspace)."""
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out.glob("*/*/result.json"))]


def status(r: dict[str, Any]) -> str:
    """How the run ended (results from before run statuses: by their validity gate)."""
    return r.get("status") or ("ok" if _valid(r) else "invalid")


def _valid(r: dict[str, Any]) -> bool:
    return bool(r["score"]["gates"].get("validity", False))


def _usage(r: dict[str, Any]) -> tuple[int | None, float | None]:
    """(total tokens, dollars) of a run's model calls; older results: the tokens they recorded."""
    if r.get("usage"):
        return r["usage"].get("total_tokens"), r["usage"].get("cost_usd")
    run = r.get("agent_run") or {}
    parts = [run.get("usage"), run.get("customer_usage"), (r.get("extraction") or {}).get("usage"),
             (r.get("clarification") or {}).get("usage")]
    tokens = [p["total_tokens"] for p in parts if p]
    return (sum(tokens) if tokens else None), run.get("cost_usd")


def _case_mean(rows: list[dict[str, Any]], key: str) -> float | None:
    """Case-macro mean of score[key] over the runs that report it."""
    by_case: dict[str, list[float]] = defaultdict(list)
    for x in rows:
        if x["score"].get(key) is not None:
            by_case[x["spec"]["case_id"]].append(x["score"][key])
    return mean(mean(v) for v in by_case.values()) if by_case else None


def _cell(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_case[r["spec"]["case_id"]].append(r)
    valid = [_valid(r) for r in rows]
    asks = [r["clarification"]["ask_f1"] for r in rows if r.get("clarification") and r["clarification"]["ask_f1"] is not None]
    # Case-macro averages: every case weighs the same regardless of how many seeds finished, and within a case
    # every rule seed weighs the same (as in the difficulty table).
    finals = [_seed_mean(rs) for rs in by_case.values()]
    return {
        "n": len(rows),
        "final": mean(finals),
        "final_ci": bootstrap_ci(finals),
        "quality": mean(_seed_mean(rs, lambda x: x["score"]["components"]["quality"]) for rs in by_case.values()),
        # Unclipped normalized quality (the reference 1.0; > 1.0 beats it) and the plain objective ratio to the
        # reference, where the scorer reports them.
        "quality_norm": _case_mean(rows, "quality_raw"),
        "quality_ratio": _case_mean(rows, "quality_ratio"),
        "validity": sum(valid) / len(valid),
        "dsr": sum(_valid(r) and r["score"].get("quality_raw", 0.0) >= 1.0 for r in rows) / len(rows),
        "all_valid": mean(all(_valid(x) for x in rs) for rs in by_case.values()),
        "ask_f1": mean(asks) if asks else None,
    }


def table(results: list[dict[str, Any]], axis: str) -> str:
    groups: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        groups[(_agent(r), r["spec"].get(axis) or r.get(axis))].append(r)
    lines = [f"### by {axis}", "",
             f"| agent | {axis} | n | final [95% CI] | quality | quality (norm) | ratio vs ref | validity | DSR "
             f"| all valid | Ask-F1 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for (agent, val), rows in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        c = _cell(rows)
        lo, hi = c["final_ci"]
        lines.append(f"| {agent} | {val} | {c['n']} | {c['final']:.3f} [{lo:.2f}–{hi:.2f}] | {c['quality']:.3f} "
                     f"| {_num(c['quality_norm'])} | {_num(c['quality_ratio'])} | {c['validity']:.2f} "
                     f"| {c['dsr']:.2f} | {c['all_valid']:.2f} | {_num(c['ask_f1'])} |")
    return "\n".join(lines)


def _agent(r: dict[str, Any]) -> str:
    return f"{r['agent']['harness']}--{r['agent']['model']}"


def _without(r: dict[str, Any], *keys: str) -> str:
    """The run's variant (its spec) without `keys`, as a grouping key."""
    return json.dumps({k: v for k, v in r["spec"].items() if k not in keys}, sort_keys=True)


def rule_seed(r: dict[str, Any]) -> Any:
    """The rule seed a run was scored at (None without settings; a result from before rule seeds: its rule set)."""
    if r.get("rule_seed") is not None:
        return r["rule_seed"]
    spec = r["spec"]
    return spec.get("rule_seed") if spec.get("rule_seed") is not None else spec.get("ruleset")


def _seed_mean(rows: list[dict[str, Any]], value=lambda x: x["score"]["final"]) -> float:
    """One case's score (final by default): the mean over its rule seeds of the mean over each seed's runs (a
    case without settings: the mean over its runs)."""
    by_seed: dict[str, list[float]] = defaultdict(list)
    for x in rows:
        by_seed[str(rule_seed(x))].append(value(x))
    return mean(mean(v) for v in by_seed.values())


def difficulty_table(results: list[dict[str, Any]]) -> str:
    """Agents × difficulty; each cell = case-macro mean of (mean over rule seeds of the mean over their runs)."""
    cells: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        cells[(_agent(r), r["spec"].get("difficulty", "medium"))][r["spec"]["case_id"]].append(r)
    agents = sorted({a for a, _ in cells})
    head = " | ".join(f"{t} final [95% CI] | {t} all valid" for t in TIERS)
    lines = ["### by difficulty (mean over rule seeds, then cases; all valid = valid under every rule seed)", "",
             f"| agent | {head} |", "|---|" + "---|---|" * len(TIERS)]
    for agent in agents:
        row = []
        for t in TIERS:
            by_case = cells.get((agent, t))
            if not by_case:
                row += ["–", "–"]
                continue
            per_case = [_seed_mean(rs) for rs in by_case.values()]
            groups: dict[str, list[bool]] = defaultdict(list)       # the same run under each rule seed
            for rs in by_case.values():
                for x in rs:
                    groups[_without(x, *SETTING_KEYS)].append(_valid(x))
            every = mean(all(v) for v in groups.values())
            row += [_fmt(per_case), f"{every:.2f}"]
        lines.append(f"| {agent} | " + " | ".join(row) + " |")
    return "\n".join(lines)


def settings_table(results: list[dict[str, Any]]) -> str | None:
    """Agents × case × tier × rule seed: the parameters the seed drew, the mean final score and the valid runs.
    None when no run has settings."""
    cells: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        if rule_seed(r) is not None:
            cells[(_agent(r), r["spec"]["case_id"], r["spec"].get("difficulty", "medium"), rule_seed(r))].append(r)
    if not cells:
        return None

    def order(key):
        agent, case_id, tier, seed = key
        return agent, case_id, TIERS.index(tier) if tier in TIERS else len(TIERS), str(type(seed)), seed

    lines = ["### by case and setting (tier × rule seed, with the parameters it drew)", "",
             "| agent | case | tier | rule seed | params | runs | final | valid |", "|---|---|---|---|---|---|---|---|"]
    for key in sorted(cells, key=order):
        rows = cells[key]
        params = next((x["params"] for x in rows if x.get("params") is not None), None)
        shown = "–" if params is None else "`" + json.dumps(params, ensure_ascii=False, default=str).replace("|", "\\|") + "`"
        agent, case_id, tier, seed = key
        lines.append(f"| {agent} | {case_id} | {tier} | {seed} | {shown} | {len(rows)} "
                     f"| {mean(x['score']['final'] for x in rows):.3f} | {sum(map(_valid, rows))}/{len(rows)} |")
    return "\n".join(lines)


def pass_k_table(results: list[dict[str, Any]]) -> str | None:
    """Agents × k: pass^k over each agent's variants that ran more than once (case-macro), for k = 1 .. the
    fewest trials any of them has (at most 4), so every k averages the same variants. None without trials."""
    groups: dict[str, dict[tuple[str, str], list[bool]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        groups[_agent(r)][(r["spec"]["case_id"], _without(r, "trial"))].append(_valid(r))
    repeated = {a: {key: v for key, v in g.items() if len(v) > 1} for a, g in groups.items()}
    n = {a: min(4, min((len(v) for v in g.values()), default=0)) for a, g in repeated.items()}
    top = max(n.values(), default=0)
    if top < 2:
        return None
    lines = ["### pass^k (repeated trials of one variant; pass = validity gate)", "",
             "| agent | variants | " + " | ".join(f"pass^{k}" for k in range(1, top + 1)) + " |",
             "|---|---|" + "---|" * top]
    for agent, mine in sorted(repeated.items()):
        row = []
        for k in range(1, top + 1):
            by_case: dict[str, list[float]] = defaultdict(list)
            for (cid, _), v in mine.items():
                by_case[cid].append(pass_hat_k(len(v), sum(v), k))
            row.append(_num(mean(mean(x) for x in by_case.values())) if k <= n[agent] else "–")
        lines.append(f"| {agent} | {len(mine)} | " + " | ".join(row) + " |")
    return "\n".join(lines)


def status_table(results: list[dict[str, Any]]) -> str:
    """Runs per agent by how they ended, with tokens and dollars per run (solver, client, extractor, judges)."""
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        by_agent[_agent(r)].append(r)
    lines = ["### runs by status", "", "| agent | runs | " + " | ".join(STATUSES) + " | tokens/run | $/run |",
             "|---|---|" + "---|" * (len(STATUSES) + 2)]
    unmeasured = []
    for agent, rows in sorted(by_agent.items()):
        tokens = [t for t, _ in map(_usage, rows) if t is not None]
        costs = [c for _, c in map(_usage, rows) if c is not None]
        counts = [str(sum(status(r) == s for r in rows)) for s in STATUSES]
        lines.append(f"| {agent} | {len(rows)} | " + " | ".join(counts)
                     + f" | {_num(mean(tokens) if tokens else None, 0)} | {_num(mean(costs) if costs else None, 4)} |")
        if any("agent" in (r.get("usage") or {}).get("unmeasured", []) for r in rows):
            unmeasured.append(agent)
    if unmeasured:
        lines += ["", f"Solver usage not measured (CLI logs are not parsed) for: {', '.join(unmeasured)}."]
    return "\n".join(lines)


def unscored_list(results: list[dict[str, Any]]) -> str | None:
    bad = sorted((r for r in results if status(r) in NOT_SCORED), key=lambda r: (_agent(r), r.get("key", "")))
    if not bad:
        return None
    lines = ["### not scored (harness or infrastructure errors, left out of every score table)", ""]
    lines += [f"- {_agent(r)} `{r.get('key') or r['spec']['case_id']}`: {status(r)}: {(r.get('error') or '')[:160]}"
              for r in bad]
    return "\n".join(lines)


def report(out: Path) -> str:
    results = load_results(out)
    if not results:
        return "no results"
    scored = [r for r in results if status(r) not in NOT_SCORED]
    parts: list[str | None] = []
    if scored:
        # per tier, averaged over rule seeds: whenever difficulties differ or a case has settings
        several = len({r["spec"].get("difficulty") for r in scored}) > 1
        if several or any(rule_seed(r) is not None for r in scored):
            parts.append(difficulty_table(scored))
        varied = [ax for ax in AXES if ax not in ("difficulty", "rule_seed")
                  and len({str(r["spec"].get(ax)) for r in scored}) > 1]
        # one table per varied axis; with none (and one difficulty), the full table of the single cell
        parts += [table(scored, ax) for ax in varied] or ([] if several else [table(scored, "policy")])
        parts.append(settings_table(scored))
        parts.append(pass_k_table(scored))
    parts += [status_table(results), unscored_list(results)]
    return "\n\n".join(p for p in parts if p) + "\n"
