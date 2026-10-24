"""Vendor CLI harnesses (Claude Code, Codex, Gemini CLI, OpenCode) run headless.

Each gets the same rendered prompt as the reference agent and reaches the
client through the MCP bridge. Command-line flags of these tools change often:
check `build_command` against the installed versions before a campaign, and
record the versions with the results (`version_command`).
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .base import AgentResult, RunContext


def _bridge_cmd(run_dir: Path) -> list[str]:
    return [sys.executable, "-m", "fdebench2.mcp_bridge", "--run-dir", str(run_dir.resolve())]


@dataclass
class CLIAgent:
    name: str                       # claude_code | codex | gemini | opencode
    model: str | None = None        # passed through to the CLI's own model flag
    extra_args: list[str] = field(default_factory=list)

    def version_command(self) -> list[str]:
        return {"claude_code": ["claude", "--version"], "codex": ["codex", "--version"],
                "gemini": ["gemini", "--version"], "opencode": ["opencode", "--version"]}[self.name]

    def build_command(self, ctx: RunContext, prompt: str) -> list[str]:
        bridge = _bridge_cmd(ctx.run_dir)
        cfg_dir = ctx.run_dir / "agent_config"
        cfg_dir.mkdir(exist_ok=True)
        if self.name == "claude_code":
            mcp = cfg_dir / "mcp.json"
            mcp.write_text(json.dumps({"mcpServers": {"client": {"command": bridge[0], "args": bridge[1:]}}}))
            cmd = ["claude", "-p", prompt, "--mcp-config", str(mcp), "--output-format", "stream-json",
                   "--verbose", "--permission-mode", "bypassPermissions"]
            if self.model:
                cmd += ["--model", self.model]
        elif self.name == "codex":
            cmd = ["codex", "exec", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox", "--json",
                   "-c", f"mcp_servers.client.command={json.dumps(bridge[0])}",
                   "-c", f"mcp_servers.client.args={json.dumps(bridge[1:])}"]
            if self.model:
                cmd += ["-m", self.model]
            cmd.append(prompt)
        elif self.name == "gemini":
            settings = ctx.workspace / ".gemini" / "settings.json"
            settings.parent.mkdir(exist_ok=True)
            settings.write_text(json.dumps({"mcpServers": {"client": {"command": bridge[0], "args": bridge[1:]}}}))
            cmd = ["gemini", "-p", prompt, "--yolo", "--output-format", "json"]
            if self.model:
                cmd += ["-m", self.model]
        elif self.name == "opencode":
            (ctx.workspace / "opencode.json").write_text(json.dumps(
                {"$schema": "https://opencode.ai/config.json",
                 "mcp": {"client": {"type": "local", "command": bridge, "enabled": True}}}))
            cmd = ["opencode", "run", "--format", "json"]
            if self.model:
                cmd += ["--model", self.model]
            cmd.append(prompt)
        else:
            raise ValueError(f"unknown CLI agent {self.name!r}")
        return cmd + self.extra_args

    def run(self, ctx: RunContext) -> AgentResult:
        prompt = f"{ctx.system_prompt}\n\n{ctx.user_prompt}"
        cmd = self.build_command(ctx, prompt)
        log = ctx.run_dir / "agent_stdout.log"
        try:
            version = subprocess.run(self.version_command(), capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.TimeoutExpired) as e:
            return AgentResult("error", detail={"error": f"{self.name} not runnable: {e}"})
        ctx.session.log("cli_start", agent=self.name, version=version)
        try:
            with log.open("w", encoding="utf-8") as out:
                p = subprocess.run(cmd, cwd=ctx.workspace, stdout=out, stderr=subprocess.STDOUT,
                                   timeout=ctx.session.deadline_s, text=True)
            status = "finished" if p.returncode == 0 else "error"
            detail = {"exit_code": p.returncode, "version": version}
        except subprocess.TimeoutExpired:
            status, detail = "out_of_time", {"version": version}
        # Token usage is in each CLI's own log format (agent_stdout.log) and is not parsed yet.
        # Steps and events are counted by the bridge process and land in transcript.jsonl.
        return AgentResult(status, detail=detail)
