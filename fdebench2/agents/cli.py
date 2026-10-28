"""Vendor CLI harnesses (Claude Code, Codex, Gemini CLI, OpenCode) run headless.

Each gets the same rendered prompt as the reference agent and reaches the
client through the MCP bridge. Under a docker sandbox the CLI runs inside the
agent's container (which holds only /workspace) and the bridge serves HTTP on
the host, so nothing about the case, its settings or the run is reachable; the
image must have the CLIs installed (docker/Dockerfile.agent). Without docker
the CLI runs on the host: development only, it can read the whole machine. Command-line flags of these tools change often:
check `build_command` against the installed versions before a campaign, and
record the versions with the results (`version_command`).
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..sandbox import DockerSandbox
from .base import AgentResult, RunContext

CONFIG_DIR = ".agent"          # CLI configuration inside the workspace (never collected as a deliverable)


def _bridge_cmd(run_dir: Path) -> list[str]:
    return [sys.executable, "-m", "fdebench2.mcp_bridge", "--run-dir", str(run_dir.resolve())]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@dataclass
class CLIAgent:
    name: str                       # claude_code | codex | gemini | opencode
    model: str | None = None        # passed through to the CLI's own model flag
    extra_args: list[str] = field(default_factory=list)

    def version_command(self) -> list[str]:
        return {"claude_code": ["claude", "--version"], "codex": ["codex", "--version"],
                "gemini": ["gemini", "--version"], "opencode": ["opencode", "--version"]}[self.name]

    def build_command(self, ctx: RunContext, prompt: str, url: str | None = None) -> list[str]:
        """The CLI command line. `url`: the bridge's HTTP endpoint (isolated runs); else a stdio bridge."""
        bridge = _bridge_cmd(ctx.run_dir)
        stdio = {"command": bridge[0], "args": bridge[1:]}
        cfg_dir = ctx.workspace / CONFIG_DIR
        cfg_dir.mkdir(exist_ok=True)
        cfg_path = "/workspace/" + CONFIG_DIR if url else str(cfg_dir)
        if self.name == "claude_code":
            server = {"type": "http", "url": url} if url else stdio
            (cfg_dir / "mcp.json").write_text(json.dumps({"mcpServers": {"client": server}}))
            cmd = ["claude", "-p", prompt, "--mcp-config", f"{cfg_path}/mcp.json", "--output-format", "stream-json",
                   "--verbose", "--permission-mode", "bypassPermissions"]
            if self.model:
                cmd += ["--model", self.model]
        elif self.name == "codex":
            server = ([f"mcp_servers.client.url={json.dumps(url)}"] if url else
                      [f"mcp_servers.client.command={json.dumps(bridge[0])}",
                       f"mcp_servers.client.args={json.dumps(bridge[1:])}"])
            cmd = ["codex", "exec", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox", "--json"]
            for item in server:
                cmd += ["-c", item]
            if self.model:
                cmd += ["-m", self.model]
            cmd.append(prompt)
        elif self.name == "gemini":
            settings = ctx.workspace / ".gemini" / "settings.json"
            settings.parent.mkdir(exist_ok=True)
            server = {"httpUrl": url} if url else stdio
            settings.write_text(json.dumps({"mcpServers": {"client": server}}))
            cmd = ["gemini", "-p", prompt, "--yolo", "--output-format", "json"]
            if self.model:
                cmd += ["-m", self.model]
        elif self.name == "opencode":
            server = ({"type": "remote", "url": url, "enabled": True} if url else
                      {"type": "local", "command": bridge, "enabled": True})
            (ctx.workspace / "opencode.json").write_text(json.dumps(
                {"$schema": "https://opencode.ai/config.json", "mcp": {"client": server}}))
            cmd = ["opencode", "run", "--format", "json"]
            if self.model:
                cmd += ["--model", self.model]
            cmd.append(prompt)
        else:
            raise ValueError(f"unknown CLI agent {self.name!r}")
        return cmd + self.extra_args

    def run(self, ctx: RunContext) -> AgentResult:
        prompt = f"{ctx.system_prompt}\n\n{ctx.user_prompt}"
        isolated = isinstance(ctx.sandbox, DockerSandbox)
        bridge = None
        if isolated:
            port = _free_port()
            bridge = subprocess.Popen(_bridge_cmd(ctx.run_dir) + ["--http", f"0.0.0.0:{port}"],
                                      stdout=subprocess.DEVNULL, stderr=(ctx.run_dir / "bridge.log").open("w"))
            time.sleep(2)
            cmd = ctx.sandbox.exec_argv(self.build_command(ctx, prompt, url=f"http://host.docker.internal:{port}/mcp"))
            version_cmd = ctx.sandbox.exec_argv(self.version_command())
        else:
            cmd = self.build_command(ctx, prompt)
            version_cmd = self.version_command()
        log = ctx.run_dir / "agent_stdout.log"
        try:
            try:
                version = subprocess.run(version_cmd, capture_output=True, text=True, timeout=60).stdout.strip()
            except (OSError, subprocess.TimeoutExpired) as e:
                return AgentResult("error", detail={"error": f"{self.name} not runnable: {e}"})
            ctx.session.log("cli_start", agent=self.name, version=version, isolated=isolated)
            try:
                with log.open("w", encoding="utf-8") as out:
                    p = subprocess.run(cmd, cwd=None if isolated else ctx.workspace, stdout=out,
                                       stderr=subprocess.STDOUT, timeout=ctx.session.deadline_s, text=True)
                status = "finished" if p.returncode == 0 else "error"
                detail = {"exit_code": p.returncode, "version": version, "isolated": isolated}
            except subprocess.TimeoutExpired:
                status, detail = "out_of_time", {"version": version, "isolated": isolated}
        finally:
            if bridge is not None:
                bridge.terminate()
        # Token usage is in each CLI's own log format (agent_stdout.log) and is not parsed yet.
        # Steps and events are counted by the bridge process and land in transcript.jsonl.
        return AgentResult(status, detail=detail)
