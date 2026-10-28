"""Turn one run's raw measurements into a score under a given policy.

    final = 0                                   if any hard gate fails (validity always, budget under hard_budgets)
          = clip(Σ w_i·c_i / Σ w_i − penalties)  otherwise, over the components that apply

Components (each in [0, 1]):
  quality        min(max(q, 0), cap) / cap, 0 if invalid. q is the case's normalized quality (its
                 baseline solution 0, its reference 1; the plain ratio to the reference when it has no
                 baseline), cap the case's quality_cap, else the policy's (1.5: beating the reference
                 by half of the baseline-to-reference gap earns full credit)
  clarification  Ask-F1 over case + noise targets (only when the client was reachable)
  communication  right language to the client and in NOTES.md, NOTES.md present
  efficiency     1 − ½·used/budget per budget, 0 once over budget

A case rule the policy lets bend is not a validity failure *if* the agent went
through the exception process the policy prescribes for each bent rule (the
client's first decision on a rule binds: asking again after a denial does not
overturn it); it costs `soft_rule_penalty` per rule instead, and the case
re-scores the deliverable with that rule switched off.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..cases import Case
from ..transforms.language import language_fidelity, resolve
from ..transforms.policy import Policy
from .clarify import split_questions


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


def apply_policy(policy: Policy, raw: dict[str, Any], facts: RunFacts, *, case: Case, submission_dir: Path,
                 clarification_f1: float | None, can_ask: bool,
                 customer_locale: str, agent_locale: str) -> dict[str, Any]:
    gates: dict[str, bool] = {}
    penalties: dict[str, float] = {}
    notes_out: list[str] = []

    # ── validity, with policy-sanctioned rule exceptions ──────────────────────
    scored = raw                        # the evaluation the quality fields come from
    valid = float(raw.get("validity_score") or 0.0) > 0
    bent: list[str] = []
    rules = case.rules()
    if not valid and rules is not None:
        found = [v["rule"] for v in raw.get("violations") or []]
        classified = [rules.by_id(r) for r in found]
        if found and all(r is not None and policy.relaxable(r.rule_class) for r in classified):
            bent = sorted({r.id for r in classified if r is not None})
            first: dict[str, str] = {}      # the first decision on a rule binds
            for e in facts.exceptions:
                first.setdefault(e.get("rule_id"), e.get("decision"))
            granted = {r for r, d in first.items() if d == "approve"}
            if set(bent) <= granted:
                rescored = case.evaluate(submission_dir, customer_locale, relaxed=frozenset(bent))
                if rescored.get("validity_score", 0) > 0:
                    valid, scored = True, rescored
                    penalties["bent_rules"] = policy.soft_rule_penalty * len(bent)
                else:
                    notes_out.append("still invalid after relaxing the bent rules")
            else:
                notes_out.append(f"broke {sorted(set(bent) - granted)} without an approved exception for it")
    gates["validity"] = valid
    quality_raw = float(scored.get("quality_score") or 0.0) if valid else 0.0
    cap = case.quality_cap if case.quality_cap is not None else policy.quality_cap

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
    if policy.hard_budgets or "budget" in policy.hard_gates:
        gates["budget"] = not over
        if not eff:                     # nothing to measure against: the gate passes, and says so
            notes_out.append("budget not measured")

    # ── components ────────────────────────────────────────────────────────────
    comm_locale = {"customer": customer_locale, "agent": agent_locale}.get(policy.communication_locale,
                                                                          policy.communication_locale)
    comm_parts = [x for x in (language_fidelity(facts.asks, resolve(comm_locale)),
                              language_fidelity([facts.notes], resolve(comm_locale)) if notes_ok else 0.0,
                              1.0 if notes_ok else 0.0) if x is not None]
    components: dict[str, float | None] = {
        "quality": min(max(quality_raw, 0.0), cap) / cap if valid else 0.0,
        "clarification": clarification_f1 if can_ask else None,
        "communication": sum(comm_parts) / len(comm_parts) if comm_parts else None,
        "efficiency": sum(eff) / len(eff) if eff else None,
    }

    # ── process penalties ─────────────────────────────────────────────────────
    n_q = len(split_questions(facts.asks))      # questions, not rounds of questions
    if policy.question_budget is not None and n_q > policy.question_budget:
        penalties["questions_over_budget"] = policy.over_budget_penalty * (n_q - policy.question_budget)
    if policy.confirm_before_build and can_ask and facts.wrote_before_asking:
        penalties["built_before_confirming"] = 0.1

    weighted = [(policy.weights[k], v) for k, v in components.items() if policy.weights.get(k) and v is not None]
    wsum = sum(w for w, _ in weighted)
    base = sum(w * v for w, v in weighted) / wsum if wsum else 0.0
    enforced = {"validity", *policy.hard_gates} | ({"budget"} if policy.hard_budgets else set())
    passed = all(gates[g] for g in enforced)     # every enforced gate was evaluated above
    final = max(0.0, min(1.0, base - sum(penalties.values()))) if passed else 0.0
    return {
        "policy": policy.id,
        "final": round(final, 6),
        "gates": gates,
        "components": components,
        "penalties": penalties,
        "quality_raw": quality_raw,
        "quality_ratio": scored.get("quality_ratio") if valid else 0.0,
        "quality_anchor": scored.get("quality_anchor") if valid else None,
        "quality_cap": cap,
        "bent_rules": bent,
        "notes": notes_out,
    }
