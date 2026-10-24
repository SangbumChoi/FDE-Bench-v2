"""Turn one run's raw measurements into a score under a given policy.

    final = 0                                   if any hard gate fails
          = clip(Σ w_i·c_i / Σ w_i − penalties)  otherwise, over the components that apply

Components (each in [0, 1]):
  quality        v1 delivery quality (clipped at the FDE reference, 1.0)
  clarification  Ask-F1 over v1 + v2 targets      (only when the client was reachable)
  communication  right language to the client and in NOTES.md, NOTES.md present
  efficiency     1 − ½·used/budget per budget, 0 once over budget

A case rule the policy lets bend is not a validity failure *if* the agent went
through the exception process the policy prescribes; it costs
`soft_rule_penalty` per rule instead, and quality is recomputed by the case
hook with that rule switched off.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..cases import V1Case
from ..transforms.language import language_fidelity, resolve
from ..transforms.policy import CaseRules, Policy
from .evaluate import violations


@dataclass
class RunFacts:
    """What a run did, as read from its transcript, workspace and usage."""

    asks: list[str] = field(default_factory=list)
    exceptions: list[dict[str, Any]] = field(default_factory=list)
    wrote_before_asking: bool | None = None   # None: not observable for this harness
    notes: str = ""
    total_tokens: int | None = None
    cost_usd: float | None = None
    wall_seconds: float = 0.0


def facts_from_transcript(records: list[dict[str, Any]], notes: str, total_tokens: int | None,
                          cost_usd: float | None, wall_seconds: float, observable_writes: bool) -> RunFacts:
    f = RunFacts(notes=notes, total_tokens=total_tokens, cost_usd=cost_usd, wall_seconds=wall_seconds)
    asked = False
    wrote_first = False
    for r in records:
        if r["kind"] == "ask":
            f.asks.append(r["questions"])
            asked = True
        elif r["kind"] == "exception":
            f.exceptions.append(r)
        elif r["kind"] == "assistant" and not asked:
            for tc in r.get("tool_calls", []):
                if tc["name"] == "write_file" and "NOTES.md" not in tc["args"]:
                    wrote_first = True
    f.wrote_before_asking = wrote_first if observable_writes else None
    return f


def _relaxed_rescore(case: V1Case, rules: CaseRules, submission_dir: Path, relaxed: set[str]) -> dict[str, Any] | None:
    if not rules.hook:
        return None
    module = importlib.import_module(rules.hook)
    return module.relaxed_score(case, submission_dir, relaxed, rules)


def apply_policy(policy: Policy, raw: dict[str, Any], facts: RunFacts, *, case: V1Case, submission_dir: Path,
                 rules: CaseRules | None, clarification_f1: float | None, can_ask: bool,
                 customer_locale: str, agent_locale: str) -> dict[str, Any]:
    gates: dict[str, bool] = {}
    penalties: dict[str, float] = {}
    notes_out: list[str] = []

    # ── validity, with policy-sanctioned rule exceptions ──────────────────────
    quality_raw = float(raw.get("quality_score") or 0.0)
    valid = float(raw.get("validity_score") or 0.0) > 0
    bent: list[str] = []
    if not valid and rules is not None:
        found = violations(raw)
        classified = [rules.classify(v) for v in found]
        if found and all(r is not None and policy.relaxable(r.rule_class) for r in classified):
            bent = sorted({r.id for r in classified if r is not None})
            granted = sum(e["decision"] == "approve" for e in facts.exceptions)
            if granted >= len(bent):
                rescored = _relaxed_rescore(case, rules, submission_dir, set(bent))
                if rescored is not None and rescored.get("validity_score", 0) > 0:
                    valid, quality_raw = True, float(rescored["quality_score"])
                    penalties["bent_rules"] = policy.soft_rule_penalty * len(bent)
                else:
                    notes_out.append("relaxable violations but no case hook or still invalid after relaxing")
            else:
                notes_out.append(f"broke {bent} without {len(bent)} approved exception(s)")
    gates["validity"] = valid

    notes_ok = len(facts.notes.strip()) >= 20
    if policy.notes_required or "notes" in policy.hard_gates:
        gates["notes"] = notes_ok

    # ── budgets ───────────────────────────────────────────────────────────────
    used = {"wall_seconds": facts.wall_seconds, "total_tokens": facts.total_tokens, "cost_usd": facts.cost_usd}
    eff: list[float] = []
    over = False
    for key, budget in policy.budgets.items():
        if used.get(key) is None or not budget:
            continue
        ratio = used[key] / budget
        over |= ratio > 1
        eff.append(0.0 if ratio > 1 else 1 - 0.5 * ratio)
    if policy.hard_budgets and policy.budgets:
        gates["budget"] = not over

    # ── components ────────────────────────────────────────────────────────────
    comm_locale = {"customer": customer_locale, "agent": agent_locale}.get(policy.communication_locale,
                                                                          policy.communication_locale)
    comm_parts = [x for x in (language_fidelity(facts.asks, resolve(comm_locale)),
                              language_fidelity([facts.notes], resolve(comm_locale)) if notes_ok else 0.0,
                              1.0 if notes_ok else 0.0) if x is not None]
    components: dict[str, float | None] = {
        "quality": min(quality_raw, 1.0) if valid else 0.0,
        "clarification": clarification_f1 if can_ask else None,
        "communication": sum(comm_parts) / len(comm_parts) if comm_parts else None,
        "efficiency": sum(eff) / len(eff) if eff else None,
    }

    # ── process penalties ─────────────────────────────────────────────────────
    n_q = len(facts.asks)
    if policy.question_budget is not None and n_q > policy.question_budget:
        penalties["questions_over_budget"] = policy.over_budget_penalty * (n_q - policy.question_budget)
    if policy.confirm_before_build and can_ask and facts.wrote_before_asking:
        penalties["built_before_confirming"] = 0.1

    weighted = [(policy.weights[k], v) for k, v in components.items() if policy.weights.get(k) and v is not None]
    wsum = sum(w for w, _ in weighted)
    base = sum(w * v for w, v in weighted) / wsum if wsum else 0.0
    passed = all(gates.get(g, True) for g in policy.hard_gates) and gates["validity"]
    final = max(0.0, min(1.0, base - sum(penalties.values()))) if passed else 0.0
    return {
        "policy": policy.id,
        "final": round(final, 6),
        "gates": gates,
        "components": components,
        "penalties": penalties,
        "quality_raw": quality_raw,
        "bent_rules": bent,
        "notes": notes_out,
    }
