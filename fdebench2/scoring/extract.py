"""Collect the agent's deliverable into the shape the case evaluator reads.

Requests deliberately leave the file format open, so agents name and shape
their outputs freely. If the files the evaluator expects are already present
they are copied as-is; otherwise a fixed extractor model (any OpenAI-compatible
endpoint, pinned in models.yaml) converts what the agent produced, following
the case's deliverable spec. It may reshape, never re-solve.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..cases import Case
from ..llm import ChatModel, Usage
from ..sandbox import LocalSandbox

_SYSTEM = """You convert an engineer's delivered files into the exact submission format an evaluator expects.
Rules:
- Only reshape what the engineer actually decided. Never fabricate, fill gaps with new decisions, or re-solve the problem.
- Write the converted files into `_submission/` using the exact file names in the spec.
- If the deliverable cannot be converted faithfully, write nothing and explain why in your summary.
Call `finish` when done."""


def _find(workspace: Path, name: str) -> Path | None:
    hits = sorted((p for p in workspace.rglob(name) if p.is_file()
                   and p.relative_to(workspace).parts[0] not in ("data", "inbox", ".agent")),
                  key=lambda p: (len(p.relative_to(workspace).parts), -p.stat().st_mtime))
    return hits[0] if hits else None


_NOT_PROGRAM = shutil.ignore_patterns("data", "inbox", "__pycache__", ".git", ".gemini", ".agent", "opencode.json",
                                     "NOTES.md")


def _collect_program(case: Case, workspace: Path, out_dir: Path) -> dict:
    """Program cases: copy the directory holding the entry file to submission/program/."""
    entry_file = case.entrypoint.partition(":")[0]
    preferred = workspace / "program" / entry_file
    found = preferred if preferred.is_file() else _find(workspace, entry_file)
    if found is None:
        return {"method": "none", "missing": [entry_file]}
    dest = out_dir / "program"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(found.parent, dest, ignore=_NOT_PROGRAM)
    return {"method": "program", "from": found.parent.relative_to(workspace).as_posix() or ".",
            "files": sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())[:200]}


def collect(case: Case, workspace: Path, out_dir: Path, extractor: ChatModel | None) -> dict:
    """Fill `out_dir` with the submission. Returns a small report of how it was obtained."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if case.deliverable_type == "program":
        # Never reshaped by a model: rewriting code would mean re-solving the task.
        return _collect_program(case, workspace, out_dir)
    names = case.submission_files
    found = {n: _find(workspace, n) for n in names}
    if names and all(found.values()):
        for n, p in found.items():
            shutil.copy2(p, out_dir / n)
        return {"method": "direct", "files": names}
    if extractor is None:
        return {"method": "none", "missing": [n for n, p in found.items() if p is None]}
    return _extract_with_model(case, workspace, out_dir, extractor)


def _extract_with_model(case: Case, workspace: Path, out_dir: Path, model: ChatModel) -> dict:
    from ..agents.tools import BASH, FINISH, LIST, READ, WRITE, call_tool

    scratch = out_dir.parent / "extract_ws"
    if scratch.exists():
        shutil.rmtree(scratch)
    shutil.copytree(workspace, scratch, ignore=shutil.ignore_patterns(".gemini", "opencode.json", ".agent"))
    (scratch / "_submission").mkdir(exist_ok=True)

    class _Ctx:  # the subset of RunContext the file tools use
        sandbox = LocalSandbox(scratch)
        workspace = scratch
    ctx = _Ctx()

    messages = [{"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"Expected files: {case.submission_files}\n\nSpec:\n{case.deliverable_spec()}"}]
    usage = Usage()
    for _ in range(60):
        resp = model.chat(messages, tools=[BASH, READ, WRITE, LIST, FINISH])
        usage.add(resp.usage)
        messages.append(resp.assistant_message())
        if not resp.tool_calls:
            break
        done = False
        for tc in resp.tool_calls:
            if tc.name == "finish":
                done = True
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": "ok"})
                continue
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": call_tool(ctx, tc.name, tc.arguments)})
        if done:
            break
    produced = [p for p in (scratch / "_submission").iterdir() if p.is_file()]
    for p in produced:
        shutil.copy2(p, out_dir / p.name)
    return {"method": "extractor", "files": [p.name for p in produced], "usage": usage.to_dict()}
