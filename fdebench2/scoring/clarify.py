"""Clarification coverage: did the agent's questions uncover the hidden requirements?

Criterion: would the client, answering these questions honestly, reveal this
requirement? Judged by a fixed panel with a majority vote.
  - Questions can be in any of the five locales, so each judge sees the target
    both in its canonical English wording and in the customer locale. Use
    judges that read all locales in the campaign.
  - Targets added by transforms (noise) are scored too; `recall_case` reports
    recall over the case's own targets only.
  - When the client's answers are given, judges see them under each round of
    questions: a target counts only if a specific question asked for it and the
    answer actually told the engineer (what was learned, not what might have
    been). Questions are still numbered for precision. A covered vote must then
    cite the question(s) and quote the answer that states the requirement; a
    quote that is not in a cited round's answer (whitespace-normalized) is not
    a vote.
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

The engineer's questions to the client, numbered{answered}:
{questions}

{criterion} A question counts only if it is specific enough that the answer would state this requirement; a broad "anything else?" does not.
Return {reply}"""
_REPLY_Q = '{"covered": true|false, "questions": [<numbers of the questions that revealed it>]}'
_REPLY_QA = ('{"covered": true|false, "questions": [<numbers of the questions that revealed it>], "quote": "<if '
             'covered: the short passage of the client\'s answer that states it, copied character for character>"}')
_CRITERION_Q = "Would a client who knows this requirement, answering these questions honestly, reveal it?"
_CRITERION_QA = ("Did this conversation reveal the requirement to the engineer: did a specific question ask for it and "
                 "did the client's answer state it?")


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


def score_clarification(targets: list[Target], asks: list[str], judges: list[ChatModel],
                        answers: list[str] | None = None) -> ClarifyScore:
    """`answers[i]` is the client's reply to the block of questions `asks[i]` (optional)."""
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

    said: dict[int, str] | None = None      # question number -> its round's answer, whitespace-normalized
    if answers is not None and len(answers) == len(asks):
        lines, said = [], {}
        for block, ans in zip(asks, answers):
            answer = " ".join(str(ans).split())
            for q in split_questions([block]):
                said[len(said) + 1] = answer
                lines.append(f"{len(said)}. {q}")
            lines.append(f"   Client's answer: {answer}")
        numbered, answered = "\n".join(lines), ", each round followed by the client's answer"
        criterion, reply = _CRITERION_QA, _REPLY_QA
    else:
        numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
        answered, criterion, reply = "", _CRITERION_Q, _REPLY_Q
    covered: dict[str, bool] = {}
    useful: set[int] = set()
    for t in targets:
        votes, cited = 0, set()
        for judge in judges:
            text, u = complete_text(judge, _SYSTEM, _USER.format(source=t.source_text, text=t.text, questions=numbered,
                                                                       answered=answered, criterion=criterion,
                                                                       reply=reply))
            usage.add(u)
            try:
                doc = parse_json_reply(text)
            except ValueError:
                continue
            if doc.get("covered") is not True:
                continue
            nums = {int(q) for q in doc.get("questions", []) if str(q).isdigit()}
            quote = " ".join(str(doc.get("quote") or "").split())
            if said is not None and not (quote and any(quote in said[q] for q in nums if q in said)):
                continue    # with answers, a vote stands only on a verbatim quote from a cited round's answer
            votes += 1
            cited |= nums
        covered[t.id] = votes * 2 > len(judges)
        if covered[t.id]:
            useful |= cited
    recall = sum(covered.values()) / len(targets)
    precision = len({q for q in useful if 1 <= q <= len(questions)}) / len(questions)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    own = [t for t in targets if t.origin == "case"]
    recall_case = sum(covered[t.id] for t in own) / len(own) if own else None
    return ClarifyScore(recall, precision, f1, recall_case, len(questions), covered, usage)
