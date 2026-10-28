"""The simulated client.

Answers from the request plus the hidden requirements (localized, including any
v2 facts added by noise and events), in the customer's language, in a persona
set by the engagement. It never sees the clarification targets or the
evaluator, never reveals scoring formulas, and does not hand over its whole
brief on request: like a real client it answers specific questions, so the
clarification score measures what the engineer thought to ask.
"""

from __future__ import annotations

from .llm import ChatModel, Usage
from .transforms.language import LOCALES, REGISTER
from .transforms.variant import Variant

PERSONAS = {
    "cooperative": (
        "You are a helpful, organised business owner. Answer every question fully and precisely from the "
        "requirements. If several questions are asked, answer each one on its own line."
    ),
    "default": (
        "You are the business owner. Answer only what is asked, without explaining your reasons and without "
        "repeating the question. If several questions are asked, answer each one on its own line."
    ),
    "busy": (
        "You are a very busy business owner. Answer as briefly as possible: one short line per question, core "
        "conclusion only, no options, no counter-questions. A vague or overly broad question gets a vague "
        "answer; only a specific question gets a specific answer."
    ),
}

_SYSTEM = """{persona}

Language: always reply in {language}, written as {register}. Keep file, sheet, column and code names exactly as they appear in the data.

What you know about this project is below. Answer only from it.
- Do not volunteer information that was not asked for.
- You have no written specification to send. If asked to list all your requirements, rules or constraints, to "tell me everything", or to share a document with them, say you would rather answer specific questions and restate only the overall business goal in one or two sentences. A question about one topic gets the facts about that topic only.
- Do not mention how the work will be evaluated, scoring formulas or weights. If pressed, describe the business goal qualitatively.
- If something is not covered, give a sensible business default in one line, as a real client would.
- {exception_rule}

# Original request
{instruction}

# What you know (never shown to the engineer)
{information}"""

_EXCEPTION_RULE = {
    "forbidden": "If asked for permission to break one of your business rules, refuse: the rules stand.",
    "escalate": "If asked for permission to break one of your business rules, approve it only if the engineer "
                "names the rule and gives a concrete business reason; otherwise refuse.",
    "justify": "If the engineer tells you they will break a business rule and why, acknowledge it briefly.",
}


class Customer:
    def __init__(self, variant: Variant, model: ChatModel):
        self.variant = variant
        self.model = model
        self.usage = Usage()
        self.history: list[dict[str, str]] = []
        self.system = _SYSTEM.format(
            persona=PERSONAS[variant.persona],
            language=LOCALES[variant.customer_locale],
            register=REGISTER[variant.customer_locale],
            exception_rule=_EXCEPTION_RULE[variant.policy.exceptions],
            instruction=variant.instruction,
            information=variant.information,
        )

    def answer(self, questions: str) -> str:
        self.history.append({"role": "user", "content": questions})
        resp = self.model.chat([{"role": "system", "content": self.system}, *self.history])
        self.usage.add(resp.usage)
        text = (resp.content or "").strip()
        self.history.append({"role": "assistant", "content": text})
        return text

    def note_event(self, message: str) -> None:
        """Keep events the client 'sent' in its own memory so later answers stay consistent."""
        self.history.append({"role": "user", "content": "(no question)"})
        self.history.append({"role": "assistant", "content": message})
