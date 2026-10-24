"""The neutral reference harness: a plain tool-calling loop over OpenAI Chat Completions.

Every model that serves the OpenAI wire format runs here on identical tools,
prompts and budgets, so differences between rows are differences between
models. Comparing a model here with the same model inside its vendor's CLI
(Claude Code, Codex, Gemini CLI) isolates what the harness adds.
"""

from __future__ import annotations

import json
from typing import Any

from ..llm import ChatModel, Usage
from .base import AgentResult, RunContext
from .tools import call_tool, dump_args, tool_schemas

NUDGE = ("Continue by calling tools. To talk to the client use `ask_customer`; when the deliverables and NOTES.md "
         "are written, call `finish`.")
CONTEXT_CHAR_BUDGET = 400_000   # rough stand-in for a token budget; old tool output is elided beyond it


class ReferenceAgent:
    name = "reference"

    def __init__(self, model: ChatModel, max_steps: int = 400, max_nudges: int = 3):
        self.model = model
        self.max_steps = max_steps
        self.max_nudges = max_nudges

    def run(self, ctx: RunContext) -> AgentResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": ctx.system_prompt},
            {"role": "user", "content": ctx.user_prompt},
        ]
        tools = tool_schemas(ctx)
        usage = Usage()
        nudges = 0
        session = ctx.session

        while session.step < self.max_steps:
            if session.out_of_time():
                return AgentResult("out_of_time", usage=usage, steps=session.step)
            _elide(messages)
            try:
                resp = self.model.chat(messages, tools=tools)
            except Exception as e:  # provider errors end the run but are recorded, not raised
                session.log("model_error", error=repr(e)[:2000])
                return AgentResult("error", usage=usage, steps=session.step, detail={"error": repr(e)[:2000]})
            usage.add(resp.usage)
            messages.append(resp.assistant_message())
            session.log("assistant", content=(resp.content or "")[:4000],
                        tool_calls=[{"name": tc.name, "args": dump_args(tc.arguments)} for tc in resp.tool_calls])

            if not resp.tool_calls:
                nudges += 1
                if nudges > self.max_nudges:
                    return AgentResult("stalled", summary=resp.content or "", usage=usage, steps=session.step)
                messages.append({"role": "user", "content": NUDGE})
                continue
            nudges = 0

            for tc in resp.tool_calls:
                session.tick(tc.name)
                if tc.name == "finish":
                    summary = str(tc.arguments.get("summary", ""))
                    session.log("finish", summary=summary)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": "ok"})
                    return AgentResult("finished", summary=summary, usage=usage, steps=session.step)
                result = call_tool(ctx, tc.name, tc.arguments)
                result += session.inbox_note(session.poll_events())
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        return AgentResult("max_steps", usage=usage, steps=session.step)


def _elide(messages: list[dict[str, Any]]) -> None:
    """Keep the history under budget by blanking the oldest tool outputs (never the task prompt)."""
    total = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
    for m in messages[2:]:
        if total <= CONTEXT_CHAR_BUDGET:
            return
        if m["role"] == "tool" and len(m["content"]) > 200:
            total -= len(m["content"]) - 40
            m["content"] = "[output elided to save context]"
