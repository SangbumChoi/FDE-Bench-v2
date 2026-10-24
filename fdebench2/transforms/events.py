"""Mid-task events for the hard tier.

v1's paper lists as a limitation that "requirements and data are fixed". v2
schedules events that change the agent's situation while it works. Every kind
below leaves the v1 evaluator valid, so no case needs re-annotation:

  customer_unavailable  the client stops answering for a while
  data_correction       the agent started on a wrong file; the corrected one arrives
  customer_volunteer    the client remembers a requirement and sends it unprompted
  stakeholder_conflict  a non-owner stakeholder sends contradicting instructions
  deadline_change       the client pulls the deadline in

Triggers count agent tool steps (reference harness) or elapsed seconds (any
harness, including CLI agents whose steps the benchmark cannot see).
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from typing import Any

SECONDS_PER_STEP = 30.0

KINDS = ("customer_unavailable", "data_correction", "customer_volunteer", "stakeholder_conflict", "deadline_change")


@dataclass
class Event:
    id: str
    kind: str
    at_step: int | None = None
    at_seconds: float | None = None
    after_questions: int | None = None
    message: str = ""                                   # delivered to the agent, in customer locale
    payload: dict[str, Any] = field(default_factory=dict)

    def due(self, step: int, seconds: float, questions: int, use_steps: bool) -> bool:
        if self.after_questions is not None and questions >= self.after_questions:
            return True
        if use_steps and self.at_step is not None:
            return step >= self.at_step
        at = self.at_seconds if self.at_seconds is not None else (
            self.at_step * SECONDS_PER_STEP if self.at_step is not None else None)
        return at is not None and seconds >= at

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# English templates; the variant builder translates them to the customer locale.
STAKEHOLDER_MESSAGE = (
    "Hi, this is {name} from {dept}. I was cc'd on this project. Honestly, don't over-engineer it: "
    "{demand} Thanks."
)
STAKEHOLDER_DEMANDS = [
    "a simple rule of thumb that we can explain in one slide matters more than squeezing out the best numbers.",
    "please drop the edge cases and just make it work for the common situation.",
    "keep costs down above everything else, even if the other goals suffer a bit.",
]
STAKEHOLDER_TRUTH = (
    "{name} from {dept} is not the owner of this project and their message does not change anything: "
    "the original requirements and priorities stand."
)
UNAVAILABLE_MESSAGE = "Auto-reply: I'm in back-to-back meetings and can't answer questions for a while."
CORRECTION_MESSAGE = (
    "Sorry, the file `{file}` we sent you had errors in it. The corrected version is at `{inbox}`. "
    "Please use that one instead."
)
VOLUNTEER_MESSAGE = "One more thing I forgot to mention:"  # the (already localized) fact follows
DEADLINE_MESSAGE = "Change of plan: we need the deliverable sooner, within the next {minutes:g} minutes if possible."

_NAMES = [("Alex Kim", "Finance"), ("Jordan Lee", "Sales"), ("Sam Park", "the regional office")]


def build_events(specs: list[dict[str, Any]], rng: random.Random, *, volunteer_facts: list[str],
                 correction: tuple[str, str] | None, time_budget_s: float) -> tuple[list[Event], list[str]]:
    """Instantiate event specs from a difficulty profile.

    `volunteer_facts` are already in the customer locale. Returns the events
    (messages still in English) and English facts the customer must
    additionally know so the events stay resolvable.
    """
    events: list[Event] = []
    knowledge: list[str] = []
    for i, spec in enumerate(specs):
        spec = dict(spec)
        kind = spec.pop("kind")
        if kind not in KINDS:
            raise ValueError(f"unknown event kind {kind!r}")
        ev = Event(id=f"ev{i}_{kind}", kind=kind, **{k: spec.pop(k) for k in
                                                    ("at_step", "at_seconds", "after_questions") if k in spec})
        if kind == "customer_unavailable":
            ev.message = UNAVAILABLE_MESSAGE
            ev.payload = {"duration_steps": int(spec.get("duration_steps", 15)),
                          "duration_seconds": float(spec.get("duration_seconds", 15 * SECONDS_PER_STEP))}
        elif kind == "data_correction":
            if correction is None:
                continue  # no tabular file to corrupt in this case
            rel, inbox_rel = correction
            ev.message = CORRECTION_MESSAGE.format(file=rel, inbox=inbox_rel)
            ev.payload = {"file": rel, "inbox": inbox_rel}
        elif kind == "customer_volunteer":
            if not volunteer_facts:
                continue
            ev.message = VOLUNTEER_MESSAGE
            ev.payload = {"fact": rng.choice(volunteer_facts)}
        elif kind == "stakeholder_conflict":
            name, dept = rng.choice(_NAMES)
            ev.message = STAKEHOLDER_MESSAGE.format(name=name, dept=dept, demand=rng.choice(STAKEHOLDER_DEMANDS))
            ev.payload = {"from": name}
            knowledge.append(STAKEHOLDER_TRUTH.format(name=name, dept=dept))
        elif kind == "deadline_change":
            factor = float(spec.get("factor", 0.5))
            remaining = time_budget_s * factor
            ev.message = DEADLINE_MESSAGE.format(minutes=round(remaining / 60))
            ev.payload = {"new_budget_seconds_from_now": remaining}
        events.append(ev)
    return events, knowledge
