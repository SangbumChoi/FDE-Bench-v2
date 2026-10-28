"""Where the agent's commands run.

`LocalSandbox` runs in a subprocess with the workspace as cwd (development and
tests only: it does not isolate anything). `DockerSandbox` mounts only the
workspace into a container, always at /workspace, so the case directory with
the hidden requirements and evaluator, other settings' ground truths and the
run directory's name are never reachable from inside. Vendor CLI agents run
inside the same container (see agents.cli) and reach the client over HTTP on
the host.
"""

from __future__ import annotations

import shlex
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

MAX_OUTPUT = 20_000


@dataclass
class ExecResult:
    exit_code: int
    output: str
    timed_out: bool = False

    def render(self) -> str:
        out = self.output
        if len(out) > MAX_OUTPUT:
            out = out[: MAX_OUTPUT // 2] + f"\n... [{len(out) - MAX_OUTPUT} chars truncated] ...\n" + out[-MAX_OUTPUT // 2:]
        status = "timed out" if self.timed_out else f"exit {self.exit_code}"
        return f"[{status}]\n{out}"


class LocalSandbox:
    workdir_label = "."

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def exec(self, command: str, timeout: float = 600) -> ExecResult:
        try:
            p = subprocess.run(["bash", "-lc", command], cwd=self.workspace, capture_output=True, text=True,
                               timeout=timeout, errors="replace")
            return ExecResult(p.returncode, p.stdout + p.stderr)
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            return ExecResult(-1, out, timed_out=True)


class DockerSandbox:
    workdir_label = "/workspace"

    def __init__(self, workspace: Path, image: str, cpus: float | None = None, memory: str | None = None,
                 network: str = "bridge", env: list[str] | None = None):
        self.workspace = workspace
        self.image = image
        self.cpus = cpus
        self.memory = memory
        self.network = network
        self.env = list(env or [])          # host variables passed through (API keys for CLI agents)
        self.name = f"fdeb2-{uuid.uuid4().hex[:12]}"

    def start(self) -> None:
        cmd = ["docker", "run", "-d", "--rm", "--name", self.name, "--network", self.network,
               "--add-host", "host.docker.internal:host-gateway",
               "-v", f"{self.workspace.resolve()}:/workspace", "-w", "/workspace"]
        if self.cpus:
            cmd += ["--cpus", str(self.cpus)]
        if self.memory:
            cmd += ["--memory", self.memory]
        cmd += [self.image, "sleep", "infinity"]
        subprocess.run(cmd, check=True, capture_output=True)

    def stop(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)

    def exec_argv(self, argv: list[str]) -> list[str]:
        """`docker exec` command line that runs argv in the container, with the passed-through environment."""
        cmd = ["docker", "exec", "-w", "/workspace"]
        for name in self.env:
            cmd += ["-e", name]
        return cmd + [self.name, *argv]

    def exec(self, command: str, timeout: float = 600) -> ExecResult:
        wrapped = f"timeout --kill-after=5 {int(timeout)} bash -lc {shlex.quote(command)}"
        try:
            p = subprocess.run(["docker", "exec", self.name, "bash", "-c", wrapped], capture_output=True,
                               text=True, timeout=timeout + 30, errors="replace")
            return ExecResult(p.returncode, p.stdout + p.stderr, timed_out=p.returncode == 124)
        except subprocess.TimeoutExpired:
            return ExecResult(-1, "", timed_out=True)
