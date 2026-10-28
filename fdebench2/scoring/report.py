"""Aggregate result.json files into per-axis tables.

Deltas are computed within an agent (same model, same harness) against the
baseline cell, never across agents, so adding agents adds evidence without
confounding.

The difficulty table has one column per difficulty. A case's score in a
column is the mean over its rule sets (A / B / C: three ground truths of the
same data) and seeds; columns are case-macro averages. "all-3" is the share of
(case, seed) cells valid under every rule set.

With few cases, differences between agents are noisy: every mean comes with a
95% bootstrap interval over cases (cases resampled with replacement, fixed
seed), so a gap smaller than the intervals is not evidence of a difference.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

AXES = ("customer_locale", "agent_locale", "policy", "difficulty", "ruleset", "engagement", "condition")
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


def _fmt(values: list[float]) -> str:
    lo, hi = bootstrap_ci(values)
    return f"{mean(values):.3f} [{lo:.2f}–{hi:.2f}]"


def load_results(out: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out.rglob("result.json"))]


def _cell(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_case[r["spec"]["case_id"]].append(r)
    valid = [r["score"]["gates"].get("validity", False) for r in rows]
    asks = [r["clarification"]["ask_f1"] for r in rows if r.get("clarification") and r["clarification"]["ask_f1"] is not None]
    # Case-macro averages: every case weighs the same regardless of how many seeds finished.
    return {
        "n": len(rows),
        "final": mean(mean(x["score"]["final"] for x in rs) for rs in by_case.values()),
        "final_ci": bootstrap_ci([mean(x["score"]["final"] for x in rs) for rs in by_case.values()]),
        "quality": mean(mean(x["score"]["components"]["quality"] for x in rs) for rs in by_case.values()),
        "validity": sum(valid) / len(valid),
        "dsr": sum(r["score"]["gates"].get("validity", False) and r["score"]["quality_raw"] >= 1.0 for r in rows) / len(rows),
        "pass^k": mean(all(x["score"]["gates"].get("validity", False) for x in rs) for rs in by_case.values()),
        "ask_f1": mean(asks) if asks else None,
    }


def table(results: list[dict[str, Any]], axis: str) -> str:
    groups: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        groups[(_agent(r), r["spec"].get(axis) or r.get(axis))].append(r)
    lines = [f"### by {axis}", "", f"| agent | {axis} | n | final [95% CI] | quality | validity | DSR | pass^k | Ask-F1 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for (agent, val), rows in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        c = _cell(rows)
        f1 = "–" if c["ask_f1"] is None else f"{c['ask_f1']:.3f}"
        lo, hi = c["final_ci"]
        lines.append(f"| {agent} | {val} | {c['n']} | {c['final']:.3f} [{lo:.2f}–{hi:.2f}] | {c['quality']:.3f} | {c['validity']:.2f} "
                     f"| {c['dsr']:.2f} | {c['pass^k']:.2f} | {f1} |")
    return "\n".join(lines)


def _agent(r: dict[str, Any]) -> str:
    return f"{r['agent']['harness']}--{r['agent']['model']}"


def difficulty_table(results: list[dict[str, Any]]) -> str:
    """Agents × difficulty; each cell = case-macro mean of (mean over rule sets and seeds)."""
    cells: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        cells[(_agent(r), r["spec"].get("difficulty", "medium"))][r["spec"]["case_id"]].append(r)
    agents = sorted({a for a, _ in cells})
    head = " | ".join(f"{t} final [95% CI] | {t} all-3" for t in TIERS)
    lines = ["### by difficulty (mean over rule sets A/B/C)", "", f"| agent | {head} |",
             "|---|" + "---|---|" * len(TIERS)]
    for agent in agents:
        row = []
        for t in TIERS:
            by_case = cells.get((agent, t))
            if not by_case:
                row += ["–", "–"]
                continue
            per_case = [mean(x["score"]["final"] for x in rs) for rs in by_case.values()]
            groups: dict[tuple[str, Any], list[bool]] = defaultdict(list)
            for cid, rs in by_case.items():
                for x in rs:
                    groups[(cid, x["spec"].get("seed"))].append(bool(x["score"]["gates"].get("validity", False)))
            all3 = mean(all(v) for v in groups.values())
            row += [_fmt(per_case), f"{all3:.2f}"]
        lines.append(f"| {agent} | " + " | ".join(row) + " |")
    return "\n".join(lines)


def report(out: Path) -> str:
    results = load_results(out)
    if not results:
        return "no results"
    parts = []
    if len({r["spec"].get("difficulty") for r in results}) > 1:
        parts.append(difficulty_table(results))
    varied = [ax for ax in AXES if ax not in ("difficulty", "ruleset")
              and len({str(r["spec"].get(ax)) for r in results}) > 1]
    parts += [table(results, ax) for ax in varied]
    return "\n\n".join(parts or [table(results, "policy")]) + "\n"
