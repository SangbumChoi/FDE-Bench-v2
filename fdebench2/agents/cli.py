"""Vendor CLI harnesses (Claude Code, Codex, Gemini CLI, OpenCode) run headless.

Each gets the same rendered prompt as the reference agent and reaches the
client through the MCP bridge. Under a docker sandbox the CLI runs inside the
agent's container (which holds only /workspace) and the bridge serves HTTP on
the host, so nothing about the case, its settings or the run is reachable; the
image must have the CLIs installed (docker/Dockerfile.agent). The bridge needs
a random bearer token per run and listens on the container network's gateway
when it can; the CLI gets only its own API key and endpoint variables from the
host. Without docker the CLI runs on the host: development only, it can read
the whole machine. Command-line flags of these tools change often:
check `build_command` against the installed versions before a campaign, and
record the versions with the results (`version_command`).
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..mcp_bridge import TOKEN_ENV
from ..sandbox import DockerSandbox
from .base import AgentResult, RunContext

CONFIG_DIR = ".agent"          # CLI configuration inside the workspace (never collected as a deliverable)

# The only host variables a harness gets in its container: its own API key and endpoint. AgentSpec.env overrides.
HARNESS_ENV = {
    "claude_code": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"),
    "codex": ("OPENAI_API_KEY", "OPENAI_BASE_URL"),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_GEMINI_BASE_URL"),
}
# OpenCode reaches any provider: the key follows the provider of its "<provider>/<model>" id.
OPENCODE_ENV = {
    "anthropic": HARNESS_ENV["claude_code"], "openai": HARNESS_ENV["codex"],
    "google": ("GEMINI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"),
    "openrouter": ("OPENROUTER_API_KEY",), "deepseek": ("DEEPSEEK_API_KEY",),
}


def _bridge_cmd(run_dir: Path) -> list[str]:
    return [sys.executable, "-m", "fdebench2.mcp_bridge", "--run-dir", str(run_dir.resolve())]


def _listen_address(gateway: str | None) -> tuple[str, int]:
    """(host, free port) for the bridge: the container network's gateway if this host owns it, else all interfaces
    (still behind the token)."""
    for host in ([gateway] if gateway else []) + ["0.0.0.0"]:
        try:
            with socket.socket() as s:
                s.bind((host, 0))
                return host, s.getsockname()[1]
        except OSError:
            continue
    raise OSError("no address to serve the client bridge on")


def _wait_ready(proc: subprocess.Popen, host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline and proc.poll() is None:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


@dataclass
class CLIAgent:
    name: str                       # claude_code | codex | gemini | opencode
    model: str | None = None        # passed through to the CLI's own model flag
    extra_args: list[str] = field(default_factory=list)
    env: list[str] | None = None    # host variables passed into the container; None: env_names() defaults

    def version_command(self) -> list[str]:
        return {"claude_code": ["claude", "--version"], "codex": ["codex", "--version"],
                "gemini": ["gemini", "--version"], "opencode": ["opencode", "--version"]}[self.name]

    def env_names(self) -> tuple[str, ...]:
        if self.env is not None:
            return tuple(self.env)
        if self.name == "opencode":
            return OPENCODE_ENV.get((self.model or "").partition("/")[0], ())
        return HARNESS_ENV.get(self.name, ())

    def build_command(self, ctx: RunContext, prompt: str, url: str | None = None,
                      token: str | None = None) -> list[str]:
        """The CLI command line. `url`, `token`: the bridge's HTTP endpoint and bearer token (isolated runs);
        else a stdio bridge."""
        bridge = _bridge_cmd(ctx.run_dir)
        stdio = {"command": bridge[0], "args": bridge[1:]}
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        cfg_dir = ctx.workspace / CONFIG_DIR
        cfg_dir.mkdir(exist_ok=True)
        cfg_path = "/workspace/" + CONFIG_DIR if url else str(cfg_dir)
        if self.name == "claude_code":
            server = {"type": "http", "url": url, "headers": headers} if url else stdio
            (cfg_dir / "mcp.json").write_text(json.dumps({"mcpServers": {"client": server}}))
            cmd = ["claude", "-p", prompt, "--mcp-config", f"{cfg_path}/mcp.json", "--output-format", "stream-json",
                   "--verbose", "--permission-mode", "bypassPermissions"]
            if self.model:
                cmd += ["--model", self.model]
        elif self.name == "codex":
            # -c values are TOML: an inline table for the headers.
            toml_headers = "{" + ", ".join(f"{json.dumps(k)} = {json.dumps(v)}" for k, v in headers.items()) + "}"
            server = ([f"mcp_servers.client.url={json.dumps(url)}", f"mcp_servers.client.http_headers={toml_headers}"]
                      if url else
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
            server = {"httpUrl": url, "headers": headers} if url else stdio
            settings.write_text(json.dumps({"mcpServers": {"client": server}}))
            cmd = ["gemini", "-p", prompt, "--yolo", "--output-format", "json"]
            if self.model:
                cmd += ["-m", self.model]
        elif self.name == "opencode":
            server = ({"type": "remote", "url": url, "enabled": True, "headers": headers} if url else
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
        log = ctx.run_dir / "agent_stdout.log"
        try:
            if isolated:
                # A random token per run: no other container (another run's agent) can use this run's client.
                token = secrets.token_urlsafe(32)
                host, port = _listen_address(ctx.sandbox.gateway())
                bridge = subprocess.Popen(_bridge_cmd(ctx.run_dir) + ["--http", f"{host}:{port}"],
                                          env={**os.environ, TOKEN_ENV: token}, stdout=subprocess.DEVNULL,
                                          stderr=(ctx.run_dir / "bridge.log").open("w"))
                if not _wait_ready(bridge, "127.0.0.1" if host == "0.0.0.0" else host, port):
                    return AgentResult("harness_error", detail={"error": "client bridge did not start (bridge.log)"})
                url = f"http://{'host.docker.internal' if host == '0.0.0.0' else host}:{port}/mcp"
                cmd = ctx.sandbox.exec_argv(self.build_command(ctx, prompt, url=url, token=token),
                                            env=self.env_names())
                version_cmd = ctx.sandbox.exec_argv(self.version_command())
            else:
                cmd = self.build_command(ctx, prompt)
                version_cmd = self.version_command()
            try:
                v = subprocess.run(version_cmd, capture_output=True, text=True, timeout=60)
            except (OSError, subprocess.TimeoutExpired) as e:
                return AgentResult("harness_error", detail={"error": f"{self.name} not runnable: {e}"})
            if v.returncode != 0:
                return AgentResult("harness_error", detail={"error": f"{self.name} not runnable: "
                                                                     f"{(v.stderr or v.stdout)[-500:]}"})
            version = v.stdout.strip()
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
