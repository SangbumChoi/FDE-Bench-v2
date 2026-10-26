"""Clarification coverage: did the agent's questions uncover the hidden requirements?

Criterion: would the client, answering these questions honestly, reveal this
requirement? Judged by a fixed panel with a majority vote.
  - Questions can be in any of the five locales, so each judge sees the target
    both in its canonical English wording and in the customer locale. Use
    judges that read all locales in the campaign.
  - Targets added by transforms (noise) are scored too; `recall_case` reports
    recall over the case's own targets only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..cases import Target
from ..llm import ChatModel, Usage, complete_text, parse_json_reply

_SYSTEM = ("You grade whether an engineer's clarification questions would uncover one specific hidden requirement. "
           "Judge strictly. Reply with JSON only.")
_USER = """Hidden requirement (as annotated):
{source}

Same requirement in the client's language:
{text}

The engineer's questions to the client, numbered:
{questions}

Would a client who knows this requirement, answering these questions honestly, reveal it? A question counts only if it is specific enough that the answer would state this requirement; a broad "anything else?" does not.
Return {{"covered": true|false, "questions": [<numbers of the questions that would reveal it>]}}"""


@dataclass
class ClarifyScore:
    recall: float | None
    precision: float | None
    ask_f1: float | None
    recall_case: float | None
    n_questions: int
    covered: dict[str, bool]
    usage: Usage

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["usage"] = self.usage.to_dict()
        return d


def split_questions(asks: list[str]) -> list[str]:
    out = []
    for block in asks:
        for line in block.splitlines():
            line = line.strip().lstrip("-*•0123456789.)、 ").strip()
            if len(line) >= 4:
                out.append(line)
    return out


def score_clarification(targets: list[Target], asks: list[str], judges: list[ChatModel]) -> ClarifyScore:
    questions = split_questions(asks)
    usage = Usage()
    if not targets:
        return ClarifyScore(None, None, None, None, len(questions), {}, usage)
    if not questions:
        covered = {t.id: False for t in targets}
        own = [t for t in targets if t.origin == "case"]
        return ClarifyScore(0.0, None, 0.0, 0.0 if own else None, 0, covered, usage)
    if not judges:
        raise ValueError("clarification scoring needs at least one judge model")

    numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    covered: dict[str, bool] = {}
    useful: set[int] = set()
    for t in targets:
        votes, cited = 0, set()
        for judge in judges:
            text, u = complete_text(judge, _SYSTEM, _USER.format(source=t.source_text, text=t.text, questions=numbered))
            usage.add(u)
            try:
                doc = parse_json_reply(text)
            except ValueError:
                continue
            if doc.get("covered") is True:
                votes += 1
                cited |= {int(q) for q in doc.get("questions", []) if str(q).isdigit()}
        covered[t.id] = votes * 2 > len(judges)
        if covered[t.id]:
            useful |= cited
    recall = sum(covered.values()) / len(targets)
    precision = len({q for q in useful if 1 <= q <= len(questions)}) / len(questions)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    own = [t for t in targets if t.origin == "case"]
    recall_case = sum(covered[t.id] for t in own) / len(own) if own else None
    return ClarifyScore(recall, precision, f1, recall_case, len(questions), covered, usage)
