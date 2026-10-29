"""Collect the agent's deliverable into the shape the case evaluator reads.

Requests deliberately leave the file format open, so agents name and shape
their outputs freely. If the files the evaluator expects are already present
they are copied as-is; otherwise a fixed extractor model (any OpenAI-compatible
endpoint, pinned in models.yaml) converts what the agent produced, following
the case's deliverable spec. It may reshape, never re-solve: it sees a copy of
the agent's own files only (no data/, inbox/ or hidden files) and has file tools
confined to that copy, no shell.

Nothing here follows a symbolic link: the workspace is sanitized before
collection (sandbox.sanitize), and every lookup and copy skips links and special
files as well.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..cases import Case
from ..llm import ChatModel, Usage
from ..sandbox import LocalSandbox

NOT_DELIVERED = ("data", "inbox", ".agent")      # top-level folders that never hold the agent's deliverable

_SYSTEM = """You convert an engineer's delivered files into the exact submission format an evaluator expects.
Rules:
- Only reshape what the engineer actually decided. Never fabricate, fill gaps with new decisions, or re-solve the problem.
- Write the converted files into `_submission/` using the exact file names in the spec.
- If the deliverable cannot be converted faithfully, write nothing and explain why in your summary.
Call `finish` when done."""


def _unsafe(path: Path) -> bool:
    return path.is_symlink() or not (path.is_file() or path.is_dir())


def _find(workspace: Path, name: str) -> Path | None:
    """The shallowest (then newest) regular file called `name` outside NOT_DELIVERED; rglob never enters links."""
    hits = sorted((p for p in workspace.rglob(name) if not _unsafe(p) and p.is_file()
                   and p.relative_to(workspace).parts[0] not in NOT_DELIVERED),
                  key=lambda p: (len(p.relative_to(workspace).parts), -p.stat().st_mtime))
    return hits[0] if hits else None


def read_notes(workspace: Path) -> str:
    """NOTES.md at the workspace root, else the shallowest one outside data/ and inbox/ ("" if there is none)."""
    path = _find(workspace, "NOTES.md")
    return path.read_text(encoding="utf-8", errors="replace") if path else ""


def _skip(root: Path, top: tuple[str, ...] = (), anywhere: tuple[str, ...] = ()):
    """copytree ignore: `top` names in root itself, `anywhere` patterns at any depth, every link or special file."""
    by_pattern = shutil.ignore_patterns(*anywhere)

    def ignore(directory: str, names: list[str]) -> set[str]:
        skip = set(by_pattern(directory, names)) | {n for n in names if _unsafe(Path(directory, n))}
        return skip | (set(names) & set(top) if Path(directory) == root else set())
    return ignore


_NOT_PROGRAM = ("data", "inbox", "__pycache__", ".git", ".gemini", ".agent", "opencode.json", "NOTES.md")


def _collect_program(case: Case, workspace: Path, out_dir: Path) -> dict:
    """Program cases: copy the directory holding the entry file to submission/program/."""
    entry_file = case.entrypoint.partition(":")[0]
    preferred = workspace / "program" / entry_file
    usable = not (preferred.parent.is_symlink() or _unsafe(preferred)) and preferred.is_file()
    found = preferred if usable else _find(workspace, entry_file)
    if found is None:
        return {"method": "none", "missing": [entry_file]}
    dest = out_dir / "program"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(found.parent, dest, symlinks=True, ignore=_skip(found.parent, anywhere=_NOT_PROGRAM))
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
    from ..agents.tools import FINISH, LIST, READ, WRITE, call_tool

    scratch = out_dir.parent / "extract_ws"
    if scratch.exists():
        shutil.rmtree(scratch)
    # Only what the agent wrote: never the client's data, the inbox, harness configs or hidden files.
    shutil.copytree(workspace, scratch, symlinks=True,
                    ignore=_skip(workspace, top=("data", "inbox", "held_back", "opencode.json"),
                                 anywhere=(".*", "__pycache__")))
    (scratch / "_submission").mkdir(exist_ok=True)

    class _Ctx:  # the subset of RunContext the file tools use; their paths are confined to `workspace`
        sandbox = LocalSandbox(scratch)
        workspace = scratch
    ctx = _Ctx()
    file_tools = {"read_file", "write_file", "list_files"}      # no shell

    messages = [{"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"Expected files: {case.submission_files}\n\nSpec:\n{case.deliverable_spec()}"}]
    usage = Usage()
    for _ in range(60):
        resp = model.chat(messages, tools=[READ, WRITE, LIST, FINISH])
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
            out = call_tool(ctx, tc.name, tc.arguments) if tc.name in file_tools else f"error: unknown tool {tc.name!r}"
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
        if done:
            break
    produced = [p for p in (scratch / "_submission").iterdir() if p.is_file()]
    for p in produced:
        shutil.copy2(p, out_dir / p.name)
    return {"method": "extractor", "files": [p.name for p in produced], "usage": usage.to_dict()}
