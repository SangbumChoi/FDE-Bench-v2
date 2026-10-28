"""Mid-task events for the hard tier.

Real engagements are not static: requirements and data change while the work
is under way. v2 schedules events that change the agent's situation while it
works. Every kind below leaves the case evaluator valid, so no case needs extra
annotation:

  customer_unavailable  the client stops answering for a while
  data_correction       the agent started on a wrong file; the corrected one arrives
  customer_volunteer    the client remembers a requirement and sends it unprompted
  stakeholder_conflict  a non-owner stakeholder sends contradicting instructions
  deadline_change       the client pulls the deadline in

Triggers count agent tool steps (reference harness) or elapsed seconds (any
harness, including CLI agents whose steps the benchmark cannot see). The
client learns about an event only when it fires (Session.poll_events), so it
cannot reveal one before it happens.
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


# English templates; localized through the message catalog (fdebench2/prompts/messages.yaml).
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


def msg(template: str, **params: Any) -> dict[str, Any]:
    """A message to localize later: an English catalog template plus its parameters.

    A parameter may itself be a msg (nested templates are localized too).
    """
    return {"t": template, "p": params}


def build_events(specs: list[dict[str, Any]], rng: random.Random, *, volunteer: tuple[str, str] | None,
                 correction: tuple[str, str] | None, time_budget_s: float) -> list[Event]:
    """Instantiate event specs from an engagement.

    `volunteer` is the (target id, fact in the customer locale) the client
    remembers; the caller picks it the same way in every setting. Each event
    carries its message as a `msg` in payload["msg"], and what the client
    learns when it fires (if it did not send the message itself) in
    payload["client_fact"]; the variant builder localizes both. `rng` must be
    consumed the same way in every setting.
    """
    events: list[Event] = []
    for i, spec in enumerate(specs):
        spec = dict(spec)
        kind = spec.pop("kind")
        if kind not in KINDS:
            raise ValueError(f"unknown event kind {kind!r}")
        ev = Event(id=f"ev{i}_{kind}", kind=kind, **{k: spec.pop(k) for k in
                                                    ("at_step", "at_seconds", "after_questions") if k in spec})
        if kind == "customer_unavailable":
            ev.payload = {"msg": msg(UNAVAILABLE_MESSAGE), "duration_steps": int(spec.get("duration_steps", 15)),
                          "duration_seconds": float(spec.get("duration_seconds", 15 * SECONDS_PER_STEP))}
        elif kind == "data_correction":
            if correction is None:
                continue  # no tabular file to corrupt in this case
            rel, inbox_rel = correction
            ev.payload = {"msg": msg(CORRECTION_MESSAGE, file=rel, inbox=inbox_rel), "file": rel, "inbox": inbox_rel}
        elif kind == "customer_volunteer":
            if volunteer is None:
                continue
            target, fact = volunteer
            ev.payload = {"msg": msg(VOLUNTEER_MESSAGE), "fact": fact, "target": target}
        elif kind == "stakeholder_conflict":
            name, dept = rng.choice(_NAMES)
            ev.payload = {"msg": msg(STAKEHOLDER_MESSAGE, name=name, dept=msg(dept),
                                     demand=msg(rng.choice(STAKEHOLDER_DEMANDS))), "from": name,
                          "client_fact": msg(STAKEHOLDER_TRUTH, name=name, dept=msg(dept))}
        elif kind == "deadline_change":
            factor = float(spec.get("factor", 0.5))
            remaining = time_budget_s * factor
            ev.payload = {"msg": msg(DEADLINE_MESSAGE, minutes=round(remaining / 60)),
                          "new_budget_seconds_from_now": remaining}
        events.append(ev)
    return events
