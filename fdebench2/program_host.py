"""Runs inside the isolated process that hosts an agent's program. Standard library only.

Protocol (one JSON document per line):
  stdin  line 1   {"entry": "solution.py:decide", "per_call_timeout": 2.0}
  stdin  line 2+  one input per line, passed as the single argument of the entry function
  stdout          {"ok": true, "output": <json>} or {"ok": false, "error": "<message>"} per input,
                  preceded by {"ready": true} once the program has loaded,
                  or a single {"ready": false, "error": "..."} if it cannot load.

Calls happen in order in one process, so a program may keep state between calls
(e.g. a trading strategy). Whatever the program prints goes to stderr: only this
host writes to the protocol stream.
"""

import importlib.util
import json
import os
import signal
import sys
import traceback

# Keep the protocol stream private before any agent code runs.
_proto = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1, encoding="utf-8")
os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
sys.stdout = sys.stderr


def _send(doc):
    _proto.write(json.dumps(doc, ensure_ascii=False, allow_nan=False) + "\n")
    _proto.flush()


class _CallTimeout(Exception):
    pass


def _on_alarm(signum, frame):
    raise _CallTimeout()


def main():
    header = json.loads(sys.stdin.readline())
    file_name, _, func_name = header["entry"].partition(":")
    per_call = float(header.get("per_call_timeout", 0) or 0)
    sys.path.insert(0, os.getcwd())
    try:
        spec = importlib.util.spec_from_file_location("solution", os.path.join(os.getcwd(), file_name))
        if spec is None:
            raise ImportError(f"cannot load {file_name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["solution"] = module
        spec.loader.exec_module(module)
        fn = getattr(module, func_name)
        if not callable(fn):
            raise TypeError(f"{func_name} is not callable")
    except BaseException as e:  # noqa: BLE001 - anything at load time means the program is unusable
        _send({"ready": False, "error": f"{type(e).__name__}: {e}"[:2000],
               "traceback": traceback.format_exc()[-4000:]})
        return
    _send({"ready": True})
    signal.signal(signal.SIGALRM, _on_alarm)
    for line in sys.stdin:
        if not line.strip():
            continue
        arg = json.loads(line)
        try:
            if per_call:
                signal.setitimer(signal.ITIMER_REAL, per_call)
            try:
                out = fn(arg)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
            _send({"ok": True, "output": out})
        except _CallTimeout:
            _send({"ok": False, "error": f"call exceeded {per_call:g}s"})
        except (TypeError, ValueError) as e:
            # Non-JSON-serializable outputs land here as well as the program's own errors.
            _send({"ok": False, "error": f"{type(e).__name__}: {e}"[:2000]})
        except BaseException as e:  # noqa: BLE001 - one failing call must not end the run
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                _send({"ok": False, "error": f"{type(e).__name__} raised"})
                continue
            _send({"ok": False, "error": f"{type(e).__name__}: {e}"[:2000]})


if __name__ == "__main__":
    main()
