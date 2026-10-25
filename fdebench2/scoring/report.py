"""Aggregate result.json files into per-axis tables.

Deltas are computed within an agent (same model, same harness) against the
baseline cell, never across agents, so adding agents adds evidence without
confounding.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

AXES = ("customer_locale", "agent_locale", "policy", "difficulty", "condition")


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
        "quality": mean(mean(x["score"]["components"]["quality"] for x in rs) for rs in by_case.values()),
        "validity": sum(valid) / len(valid),
        "dsr": sum(r["score"]["gates"].get("validity", False) and r["score"]["quality_raw"] >= 1.0 for r in rows) / len(rows),
        "pass^k": mean(all(x["score"]["gates"].get("validity", False) for x in rs) for rs in by_case.values()),
        "ask_f1": mean(asks) if asks else None,
    }


def table(results: list[dict[str, Any]], axis: str) -> str:
    groups: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        label = f"{r['agent']['harness']}--{r['agent']['model']}"
        groups[(label, r["spec"].get(axis) or r.get(axis))].append(r)
    lines = [f"### by {axis}", "", f"| agent | {axis} | n | final | quality | validity | DSR | pass^k | Ask-F1 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for (agent, val), rows in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        c = _cell(rows)
        f1 = "–" if c["ask_f1"] is None else f"{c['ask_f1']:.3f}"
        lines.append(f"| {agent} | {val} | {c['n']} | {c['final']:.3f} | {c['quality']:.3f} | {c['validity']:.2f} "
                     f"| {c['dsr']:.2f} | {c['pass^k']:.2f} | {f1} |")
    return "\n".join(lines)


def report(out: Path) -> str:
    results = load_results(out)
    if not results:
        return "no results"
    varied = [ax for ax in AXES if len({str(r["spec"].get(ax)) for r in results}) > 1] or ["policy"]
    return "\n\n".join(table(results, ax) for ax in varied) + "\n"
