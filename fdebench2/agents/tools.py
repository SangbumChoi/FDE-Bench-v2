"""Tools of the reference agent, as OpenAI function-calling schemas plus their implementations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .base import RunContext

MAX_READ = 40_000


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


BASH = _fn("bash", "Run a bash command in the working directory. Python 3 with the usual scientific stack is "
           "available. Long jobs: raise timeout_s (max 3600).",
           {"command": {"type": "string"}, "timeout_s": {"type": "integer"}}, ["command"])
READ = _fn("read_file", "Read a text file from the working directory.",
           {"path": {"type": "string"}, "offset": {"type": "integer", "description": "first line, 0-based"},
            "limit": {"type": "integer", "description": "max lines"}}, ["path"])
WRITE = _fn("write_file", "Create or overwrite a file in the working directory.",
            {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"])
LIST = _fn("list_files", "List files under a directory of the working directory.",
           {"path": {"type": "string"}}, [])
ASK = _fn("ask_customer", "Send questions to the client and wait for the answer. Put several questions in one "
          "message, one per line.", {"questions": {"type": "string"}}, ["questions"])
EXCEPTION = _fn("request_exception", "Ask the client for permission to break one of their business rules, or "
                "record that you are breaking one, as the engagement policy requires.",
                {"rule": {"type": "string"}, "justification": {"type": "string"}}, ["rule", "justification"])
FINISH = _fn("finish", "Declare the delivery complete. Deliverables and NOTES.md must already be written.",
             {"summary": {"type": "string"}}, ["summary"])


def tool_schemas(ctx: RunContext) -> list[dict[str, Any]]:
    tools = [BASH, READ, WRITE, LIST]
    if ctx.variant.can_ask:
        tools.append(ASK)
    if ctx.variant.policy.agent_visible:
        tools.append(EXCEPTION)
    tools.append(FINISH)
    return tools


def _resolve(ctx: RunContext, rel: str) -> Path:
    """A path inside the working directory reached without any symbolic link; anything else is refused.

    The file tools run on the host (the agent's shell may be in a container), so a link the agent made, or a
    FIFO that would block a read, must never be opened from here.
    """
    rel = (rel or ".").strip()
    if rel.startswith(ctx.sandbox.workdir_label + "/"):
        rel = rel[len(ctx.sandbox.workdir_label) + 1:]
    root = ctx.workspace.resolve()
    path = Path(os.path.normpath(root / rel))
    if path != root and root not in path.parents:
        raise PermissionError(f"{rel!r} is outside the working directory")
    for p in (path, *path.parents):
        if p == root:
            break
        if p.is_symlink():
            raise PermissionError(f"{rel!r} goes through a symbolic link")
    if path.exists() and not (path.is_file() or path.is_dir()):
        raise PermissionError(f"{rel!r} is not a regular file or directory")
    return path


def call_tool(ctx: RunContext, name: str, args: dict[str, Any]) -> str:
    if "_unparsed" in args:
        return f"error: arguments are not valid JSON: {args['_unparsed'][:300]}"
    try:
        if name == "bash":
            timeout = min(max(int(args.get("timeout_s") or 900), 1), 3600)
            return ctx.sandbox.exec(str(args["command"]), timeout=timeout).render()
        if name == "read_file":
            path = _resolve(ctx, args["path"])
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            off = int(args.get("offset") or 0)
            lim = int(args.get("limit") or len(lines))
            text = "\n".join(lines[off:off + lim])
            return text if len(text) <= MAX_READ else text[:MAX_READ] + "\n... [truncated; use offset/limit]"
        if name == "write_file":
            path = _resolve(ctx, args["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(args["content"]), encoding="utf-8")
            return f"wrote {path.relative_to(ctx.workspace.resolve())} ({len(str(args['content']))} chars)"
        if name == "list_files":
            base = _resolve(ctx, args.get("path") or ".")
            items = sorted(p.relative_to(ctx.workspace.resolve()).as_posix() + ("/" if p.is_dir() else "")
                           for p in base.rglob("*"))
            return "\n".join(items[:2000]) or "(empty)"
        if name == "ask_customer":
            return ctx.session.ask(str(args["questions"]))
        if name == "request_exception":
            return ctx.session.request_exception(str(args["rule"]), str(args["justification"]))
        return f"error: unknown tool {name!r}"
    except (KeyError, ValueError, TypeError) as e:
        return f"error: bad arguments for {name}: {e}"
    except (OSError, PermissionError) as e:
        return f"error: {e}"


def dump_args(args: dict[str, Any]) -> str:
    return json.dumps(args, ensure_ascii=False)[:2000]
