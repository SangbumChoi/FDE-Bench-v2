"""Policy axis: the deploying company's rules of engagement.

A policy is two things at once:
  1. A document the agent may be shown (`agent_visible`), stating how this
     company wants FDE work done: when to ask, how to handle rule exceptions,
     what to document, budgets, which language to report in.
  2. A scoring profile: which outcomes are hard gates, how components are
     weighted, and which case rules may be relaxed under this policy.

The same agent run can be re-scored under any policy (`fdebench2 score
--policy`), but the headline number is policy-conditioned: the agent saw the
policy it is scored against.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

POLICY_DIR = Path(__file__).resolve().parents[2] / "configs" / "policies"

EXCEPTION_MODES = ("forbidden", "escalate", "justify")
RULE_CLASSES = ("physical", "contractual", "business_policy")
HARD_GATES = ("validity", "notes", "budget")
BUDGETS = ("wall_seconds", "total_tokens", "cost_usd")


@dataclass
class Policy:
    id: str
    title: str
    statement: str = ""                     # agent-visible text, authored in English
    agent_visible: bool = True
    confirm_before_build: bool = False      # must ask the customer before writing solution code
    question_budget: int | None = None      # soft cap on clarification questions
    over_budget_penalty: float = 0.02       # per question over the cap
    exceptions: str = "escalate"            # forbidden | escalate | justify
    rule_classes: dict[str, str] = field(default_factory=lambda: {
        "physical": "hard", "contractual": "hard", "business_policy": "hard"})
    soft_rule_penalty: float = 0.1          # per relaxed rule actually broken
    notes_required: bool = True
    communication_locale: str = "customer"  # "customer" | "agent" | a locale code
    budgets: dict[str, float] = field(default_factory=dict)   # wall_seconds / total_tokens / cost_usd
    hard_budgets: bool = False              # exceeding a budget fails the run instead of costing points
    hard_gates: list[str] = field(default_factory=lambda: ["validity"])   # validity | notes | budget
    weights: dict[str, float] = field(default_factory=lambda: {"quality": 1.0})
    quality_cap: float = 1.5                # normalized quality (baseline 0, reference 1) earning full credit

    def __post_init__(self) -> None:
        if self.exceptions not in EXCEPTION_MODES:
            raise ValueError(f"{self.id}: exceptions must be one of {EXCEPTION_MODES}")
        unknown = sorted(set(self.hard_gates) - set(HARD_GATES))
        if unknown:
            raise ValueError(f"{self.id}: unknown hard_gates {unknown}; known: {HARD_GATES}")
        unknown = sorted(set(self.budgets) - set(BUDGETS))
        if unknown:
            raise ValueError(f"{self.id}: unknown budgets {unknown}; known: {BUDGETS}")
        if self.quality_cap <= 0:
            raise ValueError(f"{self.id}: quality_cap must be positive")
        for cls, mode in self.rule_classes.items():
            if cls not in RULE_CLASSES or mode not in ("hard", "soft"):
                raise ValueError(f"{self.id}: bad rule_classes entry {cls}: {mode}")
        if self.rule_classes.get("physical", "hard") != "hard":
            raise ValueError(f"{self.id}: physical rules can never be relaxed")

    def relaxable(self, rule_class: str) -> bool:
        return self.exceptions != "forbidden" and self.rule_classes.get(rule_class, "hard") == "soft"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Policy":
        return cls(**d)


def load_policy(name_or_path: str) -> Policy:
    path = Path(name_or_path)
    if not path.suffix:
        path = POLICY_DIR / f"{name_or_path}.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc.setdefault("id", path.stem)
    return Policy(**doc)


def list_policies() -> list[str]:
    return sorted(p.stem for p in POLICY_DIR.glob("*.yaml"))


@dataclass
class CaseRule:
    """A case's hard constraint, classified so a policy can decide whether it may bend."""

    id: str
    rule_class: str         # physical | contractual | business_policy
    description: str = ""


@dataclass
class CaseRules:
    case_id: str
    rules: list[CaseRule]

    def by_id(self, rule_id: str) -> CaseRule | None:
        return next((r for r in self.rules if r.id == rule_id), None)


_CLASS_WORDS = {
    "physical": "physical or data-integrity limits (capacity, stock, time)",
    "contractual": "contractual terms (designated suppliers, SLAs)",
    "business_policy": "the client's internal business preferences (sourcing order, prioritisation habits)",
}
_EXCEPTION_LINES = {
    "forbidden": "Business rules stated by the client are never to be broken, even if breaking one would give a "
                 "better result.",
    "escalate": "If you believe breaking one of the client's business rules would give a clearly better result, you "
                "may not decide that yourself: request an exception with `request_exception` and follow the "
                "client's answer.",
    "justify": "You may break a soft business rule when it clearly improves the outcome, but you must record each "
               "exception with `request_exception`, giving the rule and your justification.",
}
_BUDGET_LINES = {
    ("wall_seconds", False): "Budget: {n:g} wall-clock seconds.",
    ("wall_seconds", True): "Hard limit: {n:g} wall-clock seconds.",
    ("total_tokens", False): "Budget: {n:g} model tokens.",
    ("total_tokens", True): "Hard limit: {n:g} model tokens.",
    ("cost_usd", False): "Budget: {n:g} USD of model spend.",
    ("cost_usd", True): "Hard limit: {n:g} USD of model spend.",
}


def policy_brief_msgs(policy: Policy) -> list[dict[str, Any]]:
    """The agent-visible policy as catalog messages (localized by fdebench2.i18n)."""
    from .events import msg

    lines = [msg("Engagement policy: {title}", title=msg(policy.title))]
    if policy.statement.strip():
        lines.append(msg(policy.statement.strip()))
    if policy.confirm_before_build:
        lines.append(msg("Confirm your understanding with the client before you write solution code."))
    if policy.question_budget is not None:
        lines.append(msg("Keep clarification to about {n} questions in total; the client's time is expensive.",
                         n=policy.question_budget))
    lines.append(msg(_EXCEPTION_LINES[policy.exceptions]))
    soft = [c for c in RULE_CLASSES if policy.relaxable(c)]
    if soft:
        hard = [c for c in RULE_CLASSES if c not in soft]
        lines.append(msg("Rules that may bend under this policy: {soft}. Never: {hard}.",
                         soft=[msg(_CLASS_WORDS[c]) for c in soft], hard=[msg(_CLASS_WORDS[c]) for c in hard]))
    if policy.notes_required:
        lines.append(msg("`NOTES.md` is mandatory: list every assumption and decision."))
    if policy.communication_locale == "customer":
        lines.append(msg("Write to the client, and write `NOTES.md`, in the client's language."))
    elif policy.communication_locale != "agent":
        lines.append(msg("Write to the client, and write `NOTES.md`, in locale `{loc}`.", loc=policy.communication_locale))
    hard = policy.hard_budgets or "budget" in policy.hard_gates
    for key in BUDGETS:
        if key in policy.budgets:
            lines.append(msg(_BUDGET_LINES[(key, hard)], n=policy.budgets[key]))
    return lines
