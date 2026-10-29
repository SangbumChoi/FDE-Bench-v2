"""Run an agent's program deliverable on hidden inputs, isolated from the scorer.

A Program case's deliverable is a directory (`submission/program/`) holding an
entry file and anything it needs (helper modules, model files). Scoring calls
the entry function once per hidden input, in order, inside a separate process:

* `local` runner: a subprocess in a private copy of the program directory, with a
  minimal environment, memory/CPU limits, and no network where the OS allows
  (`unshare -n`). For development; the program can still read the filesystem.
* `docker` runner: `docker run --network none` with only the program directory
  (read-only) and the host script mounted. Use this for real campaigns. The
  container is named, so a timeout removes it (`docker rm -f`) rather than only
  killing the docker client, which would leave it running.

Two ways to drive it:

* `run_program(...)`: all inputs known up front, sent in one go. With `input_dir`,
  a copy of that directory is given to the program (read-only under docker) and
  an empty output directory next to it; the strings "$INPUT_DIR" / "$OUTPUT_DIR"
  in the inputs are replaced by their paths, and `output_to` receives what the
  program wrote (e.g. `organize(corpus_dir, out_dir)`).
* `ProgramSession`: one input at a time, each chosen after seeing the previous
  output, in the same process (e.g. a trading strategy whose next day depends
  on its own orders).

The runner is chosen with `configure()` (the benchmark does this from its sandbox
settings) or the FDEB2_PROGRAM_RUNNER environment variable: `local` or
`docker:<image>`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .sandbox import host_user, sanitize

HOST = Path(__file__).resolve().parent / "program_host.py"
MAX_PROGRAM_BYTES = 500 * 1024 * 1024


@dataclass
class ProgramResult:
    """Outcome of running a program on a list of inputs (outputs[i] is None where errors[i] is set)."""

    loaded: bool
    outputs: list[Any] = field(default_factory=list)
    errors: list[str | None] = field(default_factory=list)
    load_error: str = ""
    timed_out: bool = False          # the whole run hit total_timeout (remaining inputs have errors)
    stderr: str = ""
    wall_seconds: float = 0.0

    @property
    def n_errors(self) -> int:
        return sum(e is not None for e in self.errors)

    @property
    def status(self) -> str:
        """ok | not_loaded | timeout (the whole run hit total_timeout and its process was killed)."""
        return "timeout" if self.timed_out else "ok" if self.loaded else "not_loaded"


@dataclass
class _Config:
    kind: str = "local"
    image: str = ""
    memory_mb: int = 4096
    cpus: float = 2.0


_config = _Config()


def configure(kind: str = "local", image: str = "", memory_mb: int = 4096, cpus: float = 2.0) -> None:
    if kind not in ("local", "docker"):
        raise ValueError(f"unknown program runner {kind!r}")
    if kind == "docker" and not image:
        raise ValueError("the docker program runner needs an image")
    _config.kind, _config.image, _config.memory_mb, _config.cpus = kind, image, memory_mb, cpus


def _current() -> _Config:
    env = os.environ.get("FDEB2_PROGRAM_RUNNER", "")
    if env.startswith("docker:"):
        return _Config("docker", env.split(":", 1)[1], _config.memory_mb, _config.cpus)
    if env == "local":
        return _Config("local", "", _config.memory_mb, _config.cpus)
    return _config


def _dir_size(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def _unshare_works() -> bool:
    try:
        return subprocess.run(["unshare", "-n", "true"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _local_command(cfg: _Config) -> tuple[list[str], Any]:
    def limits() -> None:
        import resource
        os.setsid()
        mem = cfg.memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    cmd = [sys.executable, "-I", str(HOST)]
    if _unshare_works():
        cmd = ["unshare", "-n", *cmd]
    return cmd, limits


def _check(program_dir: Path, entry: str) -> str:
    file_name = entry.partition(":")[0]
    if not (program_dir / file_name).is_file():
        return f"missing {file_name} in the program directory"
    if _dir_size(program_dir) > MAX_PROGRAM_BYTES:
        return "program directory is larger than 500 MB"
    return ""


def _substitute(x: Any, paths: dict[str, str]) -> Any:
    if isinstance(x, str):
        return paths.get(x, x)
    if isinstance(x, list):
        return [_substitute(v, paths) for v in x]
    if isinstance(x, dict):
        return {k: _substitute(v, paths) for k, v in x.items()}
    return x


def _launch(cfg: _Config, tmp: Path, has_io: bool) -> tuple[subprocess.Popen, dict[str, str], str | None]:
    """Start the host on the private copy tmp/program; returns the process, the in-process io paths and the
    docker container's name (None for the local runner)."""
    work = tmp / "program"
    container = None
    if cfg.kind == "docker":
        container = f"fdeb2-prog-{uuid.uuid4().hex[:12]}"
        cmd = ["docker", "run", "--rm", "-i", "--name", container, "--network", "none",
               "--memory", f"{cfg.memory_mb}m", "--cpus", str(cfg.cpus),
               "-v", f"{work}:/program:ro", "-v", f"{HOST}:/fdeb2_host.py:ro"]
        user = host_user()
        if user:
            cmd += ["--user", user]              # what it writes to /output stays removable by the host
        paths = {}
        if has_io:
            cmd += ["-v", f"{tmp / 'input'}:/input:ro", "-v", f"{tmp / 'output'}:/output"]
            paths = {"$INPUT_DIR": "/input", "$OUTPUT_DIR": "/output"}
        cmd += ["-w", "/program", "-e", "PYTHONHASHSEED=0", cfg.image, "python", "-I", "/fdeb2_host.py"]
        preexec, env, cwd = None, None, None
    else:
        cmd, preexec = _local_command(cfg)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp), "PYTHONHASHSEED": "0",
               "OMP_NUM_THREADS": str(max(1, int(cfg.cpus))), "LANG": "C.UTF-8"}
        paths = {"$INPUT_DIR": str(tmp / "input"), "$OUTPUT_DIR": str(tmp / "output")} if has_io else {}
        cwd = work
    proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, preexec_fn=preexec, text=True, encoding="utf-8", errors="replace")
    return proc, paths, container


def run_program(program_dir: Path, entry: str, inputs: list[Any], *, per_call_timeout: float = 5.0,
                total_timeout: float = 600.0, input_dir: Path | None = None,
                output_to: Path | None = None) -> ProgramResult:
    """Call `entry` ("file.py:function") once per input, in order, in an isolated process."""
    program_dir = Path(program_dir)
    problem = _check(program_dir, entry)
    if problem:
        return ProgramResult(loaded=False, load_error=problem,
                             errors=["program not loaded"] * len(inputs), outputs=[None] * len(inputs))
    cfg = _current()
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="fdeb2-prog-") as tmp_name:
        tmp = Path(tmp_name)
        shutil.copytree(program_dir, tmp / "program")
        if input_dir is not None:
            shutil.copytree(input_dir, tmp / "input")
            (tmp / "output").mkdir()
        proc, paths, container = _launch(cfg, tmp, input_dir is not None)
        payload = "\n".join([json.dumps({"entry": entry, "per_call_timeout": per_call_timeout}),
                             *(json.dumps(_substitute(x, paths), ensure_ascii=False) for x in inputs)]) + "\n"
        timed_out = False
        try:
            out, err = proc.communicate(payload, timeout=total_timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill(proc, container)
            out, err = proc.communicate()
        if output_to is not None and input_dir is not None:
            if Path(output_to).exists():
                shutil.rmtree(output_to)
            sanitize(tmp / "output")             # links the program made would point the scorer at host files
            shutil.copytree(tmp / "output", output_to, symlinks=True)
    wall = time.monotonic() - t0
    return _parse(out or "", err or "", len(inputs), timed_out, wall)


class ProgramSession:
    """Drive a program one input at a time in one isolated process:

        with ProgramSession(program_dir, "strategy.py:on_day", per_call_timeout=2) as prog:
            for day in days:
                output, error = prog.call(make_input(day, state))   # error is None on success

    A program that cannot load raises RuntimeError from __enter__ (`load_error` is kept). After the total
    timeout, or once the process has died, every further call returns an error without running.
    """

    def __init__(self, program_dir: Path, entry: str, *, per_call_timeout: float = 5.0,
                 total_timeout: float = 600.0):
        self.program_dir, self.entry = Path(program_dir), entry
        self.per_call_timeout, self.total_timeout = per_call_timeout, total_timeout
        self.load_error = ""
        self.dead = ""
        self.calls = 0

    def __enter__(self) -> "ProgramSession":
        import queue
        import threading

        problem = _check(self.program_dir, self.entry)
        if problem:
            self.load_error = problem
            raise RuntimeError(problem)
        self._tmp = tempfile.TemporaryDirectory(prefix="fdeb2-prog-")
        tmp = Path(self._tmp.name)
        shutil.copytree(self.program_dir, tmp / "program")
        self._t0 = time.monotonic()
        self._proc, _, self._container = _launch(_current(), tmp, False)
        self._lines: "queue.Queue[str | None]" = queue.Queue()

        def pump() -> None:
            for line in self._proc.stdout:
                if line.strip():
                    self._lines.put(line)
            self._lines.put(None)
        threading.Thread(target=pump, daemon=True).start()
        self._send({"entry": self.entry, "per_call_timeout": self.per_call_timeout})
        head = self._read(max(30.0, self.per_call_timeout + 10))
        if head is None or not head.get("ready"):
            self.load_error = (head or {}).get("error", "program exited before loading")
            self.__exit__(None, None, None)
            raise RuntimeError(self.load_error)
        return self

    def _send(self, doc: Any) -> None:
        self._proc.stdin.write(json.dumps(doc, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

    def _read(self, wait: float) -> dict | None:
        import queue
        try:
            line = self._lines.get(timeout=max(0.0, wait))
        except queue.Empty:
            return None
        return None if line is None else json.loads(line)

    def call(self, x: Any) -> tuple[Any, str | None]:
        if self.dead:
            return None, self.dead
        left = self.total_timeout - (time.monotonic() - self._t0)
        if left <= 0:
            self.dead = "run timed out"
            _kill(self._proc, self._container)
            return None, self.dead
        self.calls += 1
        try:
            self._send(x)
        except (BrokenPipeError, OSError):
            self.dead = "program process died"
            return None, self.dead
        doc = self._read(min(left, self.per_call_timeout + 10))
        if doc is None:
            self.dead = "run timed out" if time.monotonic() - self._t0 >= self.total_timeout else "program process died"
            _kill(self._proc, self._container)
            return None, self.dead
        return (doc.get("output"), None) if doc.get("ok") else (None, str(doc.get("error", "error")))

    def __exit__(self, *exc) -> None:
        try:
            if self._proc.poll() is None:
                self._proc.stdin.close()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _kill(self._proc, self._container)
        finally:
            self._tmp.cleanup()


def _kill(proc: subprocess.Popen, container: str | None = None) -> None:
    """Stop the program: its docker container by name (killing the docker client alone leaves the container
    running), and the process (group) we started."""
    if container:
        try:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        os.killpg(proc.pid, 9)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()


def _parse(out: str, err: str, n: int, timed_out: bool, wall: float) -> ProgramResult:
    lines = [ln for ln in out.splitlines() if ln.strip()]
    res = ProgramResult(loaded=False, stderr=err[-4000:], wall_seconds=round(wall, 3), timed_out=timed_out)
    if not lines:
        res.load_error = "program exited before loading" + (" (timed out)" if timed_out else "")
        if err.strip():
            res.load_error += f": {err.strip().splitlines()[-1][:500]}"
        res.outputs, res.errors = [None] * n, ["program not loaded"] * n
        return res
    head = json.loads(lines[0])
    if not head.get("ready"):
        res.load_error = head.get("error", "program failed to load")
        res.outputs, res.errors = [None] * n, ["program not loaded"] * n
        return res
    res.loaded = True
    for ln in lines[1:n + 1]:
        doc = json.loads(ln)
        if doc.get("ok"):
            res.outputs.append(doc.get("output"))
            res.errors.append(None)
        else:
            res.outputs.append(None)
            res.errors.append(str(doc.get("error", "error")))
    missing = n - len(res.outputs)
    if missing > 0:
        why = "run timed out" if timed_out else "program process died"
        res.outputs += [None] * missing
        res.errors += [why] * missing
    return res
