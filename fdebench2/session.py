"""Everything the agent can do *to the world* besides its own sandbox: talk to the
client, ask for rule exceptions, and receive events.

One Session serves every harness. The reference agent calls it in-process; CLI
agents (Claude Code, Codex, Gemini CLI, OpenCode) reach it through the MCP
bridge. All interaction is appended to `transcript.jsonl` in the run directory,
which is what clarification and compliance scoring read.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from .customer import Customer
from .llm import ChatModel, parse_json_reply
from .transforms.language import LOCALES
from .transforms.policy import RULE_CLASSES
from .transforms.variant import Variant

_EXCEPTION_SYSTEM = """You are the client of an engineering project. The engineer asks permission to break one of your business rules.
Company policy for exceptions: {policy_rule}
Rules that may bend: {soft}. Rules that never bend: {hard}.
Reply in {language}. Return JSON only: {{"decision": "approve" | "deny", "reply": "<your short reply to the engineer>"}}

What you know about this project:
{information}"""


class Session:
    def __init__(self, variant: Variant, run_dir: Path, workspace: Path, customer_model: ChatModel | None,
                 use_steps: bool = True, started_at: float | None = None):
        self.variant = variant
        self.run_dir = run_dir
        self.workspace = workspace
        self.customer = Customer(variant, customer_model) if customer_model is not None else None
        self.use_steps = use_steps
        self.t0 = started_at if started_at is not None else time.time()
        self.step = 0
        self.question_rounds = 0
        self.fired: set[str] = set()
        self.unavailable_until: tuple[int, float] | None = None
        self.deadline_s: float = variant.time_budget_s
        self._log = run_dir / "transcript.jsonl"

    # ── bookkeeping ─────────────────────────────────────────────────────────
    @property
    def elapsed(self) -> float:
        return time.time() - self.t0

    def log(self, kind: str, **data: Any) -> None:
        rec = {"kind": kind, "step": self.step, "t": round(self.elapsed, 2), **data}
        with self._log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def tick(self, tool: str = "") -> None:
        """Count one agent step (a tool call) and record which tool it was."""
        self.step += 1
        self.log("step", tool=tool)

    def out_of_time(self) -> bool:
        return self.elapsed >= self.deadline_s

    # ── events ──────────────────────────────────────────────────────────────
    def poll_events(self) -> list[str]:
        """Fire due events; return the messages to show the agent now."""
        out = []
        for ev in self.variant.events:
            if ev.id in self.fired or not ev.due(self.step, self.elapsed, self.question_rounds, self.use_steps):
                continue
            self.fired.add(ev.id)
            if ev.kind == "data_correction":
                src = self.run_dir / "held_back" / ev.payload["file"]
                dst = self.workspace / ev.payload["inbox"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            elif ev.kind == "customer_unavailable":
                self.unavailable_until = (self.step + ev.payload["duration_steps"],
                                          self.elapsed + ev.payload["duration_seconds"])
                continue  # announced by the auto-reply on the next question, not pushed
            elif ev.kind == "deadline_change":
                self.deadline_s = min(self.deadline_s, self.elapsed + ev.payload["new_budget_seconds_from_now"])
            if self.customer is not None and ev.kind != "stakeholder_conflict":
                self.customer.note_event(ev.message)
            self.log("event", id=ev.id, event=ev.kind, message=ev.message)
            self._inbox(ev.id, ev.message)
            out.append(ev.message)
        return out

    def _inbox(self, ev_id: str, message: str) -> None:
        box = self.workspace / "inbox"
        box.mkdir(exist_ok=True)
        (box / f"{len(self.fired):02d}_{ev_id}.md").write_text(message + "\n", encoding="utf-8")

    def _unavailable(self) -> bool:
        if self.unavailable_until is None:
            return False
        until_step, until_t = self.unavailable_until
        if (self.step < until_step) if self.use_steps else (self.elapsed < until_t):
            return True
        self.unavailable_until = None
        return False

    # ── client channel ──────────────────────────────────────────────────────
    def ask(self, questions: str) -> str:
        questions = (questions or "").strip()
        if not self.variant.can_ask or self.customer is None:
            self.log("ask_refused", questions=questions, reason="no_channel")
            return "No one is available to answer questions. Make a reasonable assumption and record it in NOTES.md."
        if not questions:
            return "(empty question)"
        if self.question_rounds >= self.variant.max_question_rounds:
            self.log("ask_refused", questions=questions, reason="round_limit")
            return "The client has stopped answering questions. Proceed with what you have."
        self.question_rounds += 1
        self.poll_events()  # after_questions triggers
        if self._unavailable():
            msg = next((e.message for e in self.variant.events if e.kind == "customer_unavailable"), "")
            self.log("ask", round=self.question_rounds, questions=questions, answer=msg, unavailable=True)
            return msg
        answer = self.customer.answer(questions)
        self.log("ask", round=self.question_rounds, questions=questions, answer=answer)
        return answer

    def request_exception(self, rule: str, justification: str) -> str:
        policy = self.variant.policy
        if policy.exceptions == "forbidden" or self.customer is None:
            decision, reply = "deny", "No. The rules stand."
        elif policy.exceptions == "justify":
            decision, reply = "approve", "Noted."
        else:
            soft = [c for c in RULE_CLASSES if policy.relaxable(c)] or ["none"]
            hard = [c for c in RULE_CLASSES if not policy.relaxable(c)] or ["none"]
            system = _EXCEPTION_SYSTEM.format(
                policy_rule="approve only when the engineer names the rule and gives a concrete business reason",
                soft=", ".join(soft), hard=", ".join(hard), language=LOCALES[self.variant.customer_locale],
                information=self.variant.information)
            resp = self.customer.model.chat([{"role": "system", "content": system},
                                             {"role": "user", "content": f"Rule: {rule}\nWhy: {justification}"}])
            self.customer.usage.add(resp.usage)
            try:
                doc = parse_json_reply(resp.content or "")
                decision = "approve" if doc.get("decision") == "approve" else "deny"
                reply = str(doc.get("reply", ""))
            except ValueError:
                decision, reply = "deny", (resp.content or "").strip()
        self.log("exception", rule=rule, justification=justification, decision=decision, reply=reply)
        return f"[{decision.upper()}] {reply}".strip()

    def inbox_note(self, messages: list[str]) -> str:
        if not messages:
            return ""
        return "\n\n[New messages in inbox/]\n" + "\n".join(f"- {m}" for m in messages)


def read_transcript(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "transcript.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
