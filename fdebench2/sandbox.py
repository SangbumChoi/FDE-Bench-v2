"""Where the agent's commands run.

`LocalSandbox` runs in a subprocess with the workspace as cwd (development and
tests only: it does not isolate anything). `DockerSandbox` mounts only the
workspace into a container, always at /workspace, so the case directory with
the hidden requirements and evaluator, other settings' ground truths and the
run directory's name are never reachable from inside. The mounted directory is
a copy at a random temporary path (`stage`), because a bind mount's host path is
visible in the container (/proc/self/mountinfo) and the run directory's name
encodes the setting. Vendor CLI agents run inside the same container (see
agents.cli) and reach the client over HTTP on the host.

Whatever the sandbox, `sanitize` runs on the host once the agent has finished
and before anything reads its workspace: it removes every symbolic link and
special file, so no collection step can be pointed at a file outside it.
"""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import tempfile
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


def sanitize(root: Path) -> list[str]:
    """Remove every symbolic link and special file (FIFO, socket, device) under root, never following a link,
    and give the owner back read and write access to what stays: a file or directory the agent locked would
    otherwise break collection, the move back from staging and cleanup.

    Returns what was removed (for the run record); a directory that cannot be read is left in place and listed.
    """
    removed: list[str] = []
    stack = [Path(root)]
    while stack:
        d = stack.pop()
        _grant(d, stat.S_IRWXU)
        try:
            entries = list(os.scandir(d))
        except OSError:
            removed.append(f"{d.relative_to(root).as_posix()}/ (unreadable, left in place)")
            continue
        for e in entries:
            rel = Path(e.path).relative_to(root).as_posix()
            if e.is_dir(follow_symlinks=False):
                stack.append(Path(e.path))
            elif e.is_symlink():
                removed.append(f"{rel} -> {os.readlink(e.path)}")
                os.unlink(e.path)
            elif not e.is_file(follow_symlinks=False):
                removed.append(f"{rel} (special file)")
                os.unlink(e.path)
            else:
                _grant(e.path, stat.S_IRUSR | stat.S_IWUSR)
    return sorted(removed)


def _grant(path: str | Path, bits: int) -> None:
    """Add permission bits to a file or directory (never a link); one this user does not own is left as it is."""
    try:
        mode = os.lstat(path).st_mode
        if mode & bits != bits:
            os.chmod(path, stat.S_IMODE(mode) | bits)
    except OSError:
        pass


def stage(workspace: Path) -> Path:
    """Copy the workspace to a new directory with a random name, to mount instead of the run directory."""
    live = Path(tempfile.mkdtemp())
    shutil.copytree(workspace, live, symlinks=True, dirs_exist_ok=True)
    return live


def unstage(live: Path, workspace: Path) -> None:
    """Put a staged (and sanitized) workspace back in place of the run's workspace."""
    shutil.rmtree(workspace)
    shutil.move(str(live), str(workspace))


def host_user() -> str | None:
    """`uid:gid` of this process for `docker run --user`, so the host can clean up what the container wrote."""
    if not hasattr(os, "getuid") or os.getuid() == 0:
        return None
    return f"{os.getuid()}:{os.getgid()}"


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
                 network: str = "bridge", user: str | None = None):
        self.workspace = workspace          # mounted at /workspace: a staged copy (see `stage`) in real runs
        self.image = image
        self.cpus = cpus
        self.memory = memory
        self.network = network
        self.user = user                    # `docker run --user`; None: the image's default user
        self.name = f"fdeb2-{uuid.uuid4().hex[:12]}"

    def run_argv(self) -> list[str]:
        """The `docker run` command line. The container starts with no host environment at all."""
        cmd = ["docker", "run", "-d", "--rm", "--name", self.name, "--network", self.network,
               "--add-host", "host.docker.internal:host-gateway",
               "-v", f"{self.workspace.resolve()}:/workspace", "-w", "/workspace"]
        if self.user:
            cmd += ["--user", self.user]
        if self.cpus:
            cmd += ["--cpus", str(self.cpus)]
        if self.memory:
            cmd += ["--memory", self.memory]
        return cmd + [self.image, "sleep", "infinity"]

    def start(self) -> None:
        subprocess.run(self.run_argv(), check=True, capture_output=True)

    def stop(self) -> None:
        try:
            subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
        except OSError:
            pass                            # no docker client: start() failed and said so

    def gateway(self) -> str | None:
        """The host's IPv4 address on the container's network, if docker reports one."""
        try:
            out = subprocess.run(["docker", "network", "inspect", self.network, "--format",
                                  "{{range .IPAM.Config}}{{.Gateway}} {{end}}"],
                                 capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.TimeoutExpired):
            return None
        return next((ip for ip in out.split() if ip.count(".") == 3), None)

    def exec_argv(self, argv: list[str], env: tuple[str, ...] | list[str] = ()) -> list[str]:
        """`docker exec` command line that runs argv in the container with only the named host variables."""
        cmd = ["docker", "exec", "-w", "/workspace"]
        for name in env:
            if name in os.environ:
                cmd += ["-e", name]         # the value is copied by docker, never on the command line
        return cmd + [self.name, *argv]

    def exec(self, command: str, timeout: float = 600) -> ExecResult:
        wrapped = f"timeout --kill-after=5 {int(timeout)} bash -lc {shlex.quote(command)}"
        try:
            p = subprocess.run(["docker", "exec", self.name, "bash", "-c", wrapped], capture_output=True,
                               text=True, timeout=timeout + 30, errors="replace")
            return ExecResult(p.returncode, p.stdout + p.stderr, timed_out=p.returncode == 124)
        except subprocess.TimeoutExpired:
            return ExecResult(-1, "", timed_out=True)
