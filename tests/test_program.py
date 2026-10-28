import shutil
from pathlib import Path

import pytest

from fdebench2 import program
from fdebench2.cases import NativeCase
from fdebench2.scoring.extract import collect

FIXTURE = Path(__file__).parent / "fixtures" / "program_case" / "finance" / "toy_fraud_screener"


@pytest.fixture(autouse=True)
def local_runner(monkeypatch):
    monkeypatch.delenv("FDEB2_PROGRAM_RUNNER", raising=False)
    program.configure("local")


def write(tmp_path, code: str, extra: dict | None = None) -> Path:
    d = tmp_path / "program"
    d.mkdir(parents=True)
    (d / "solution.py").write_text(code, encoding="utf-8")
    for name, body in (extra or {}).items():
        (d / name).write_text(body, encoding="utf-8")
    return d


def test_calls_in_order_with_state_helpers_and_prints(tmp_path):
    d = write(tmp_path, "import helper\nseen = []\n"
                        "def run(x):\n    print('noise on stdout')\n    seen.append(x['v'])\n"
                        "    return {'sum': sum(seen), 'k': helper.K}\n", {"helper.py": "K = 7\n"})
    res = program.run_program(d, "solution.py:run", [{"v": 1}, {"v": 2}, {"v": 3}])
    assert res.loaded and res.n_errors == 0
    assert [o["sum"] for o in res.outputs] == [1, 3, 6] and res.outputs[0]["k"] == 7
    assert "noise on stdout" in res.stderr


def test_per_call_failures_do_not_stop_the_run(tmp_path):
    d = write(tmp_path, "import math\n"
                        "def run(x):\n"
                        "    if x == 'boom': raise RuntimeError('bad input')\n"
                        "    if x == 'loop':\n        while True: pass\n"
                        "    if x == 'set': return {1, 2}\n"
                        "    if x == 'nan': return math.nan\n"
                        "    if x == 'exit': raise SystemExit(3)\n"
                        "    return x.upper()\n")
    res = program.run_program(d, "solution.py:run", ["a", "boom", "loop", "set", "nan", "exit", "b"],
                              per_call_timeout=0.5)
    assert res.outputs[0] == "A" and res.outputs[-1] == "B"
    assert "RuntimeError" in res.errors[1] and "exceeded" in res.errors[2]
    assert res.errors[3] and res.errors[4] and res.errors[5]


def test_load_failures(tmp_path):
    d = write(tmp_path, "def run(x) return x\n")
    res = program.run_program(d, "solution.py:run", [1, 2])
    assert not res.loaded and "SyntaxError" in res.load_error and res.errors == ["program not loaded"] * 2
    assert not program.run_program(d, "missing.py:run", [1]).loaded
    d2 = write(tmp_path / "x", "def other(x): return x\n")
    assert "AttributeError" in program.run_program(d2, "solution.py:run", [1]).load_error


def test_total_timeout_and_hard_exit(tmp_path):
    d = write(tmp_path, "import time, os\n"
                        "def run(x):\n"
                        "    if x == 'die': os._exit(1)\n"
                        "    time.sleep(0.4)\n    return x\n")
    res = program.run_program(d, "solution.py:run", ["a", "b", "c", "d", "e"], total_timeout=1.0)
    assert res.timed_out and res.outputs[0] == "a" and res.errors[-1] == "run timed out"
    res = program.run_program(d, "solution.py:run", ["a", "die", "b"])
    assert res.outputs[0] == "a" and res.errors[1:] == ["program process died"] * 2


def test_isolation_environment_and_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("FDEB2_TEST_SECRET", "s3cret")
    d = write(tmp_path, "import os\n"
                        "def run(x):\n"
                        "    open('written.txt', 'w').write('x')\n"
                        "    return [os.environ.get('FDEB2_TEST_SECRET'), os.getcwd()]\n")
    res = program.run_program(d, "solution.py:run", [0])
    secret, cwd = res.outputs[0]
    assert secret is None
    assert Path(cwd).resolve() != d.resolve() and not (d / "written.txt").exists()


@pytest.mark.skipif(not program._unshare_works(), reason="network namespaces unavailable here")
def test_no_network_in_local_runner(tmp_path):
    d = write(tmp_path, "import socket\n"
                        "def run(x):\n"
                        "    try:\n        socket.create_connection(('1.1.1.1', 443), timeout=2)\n        return 'connected'\n"
                        "    except OSError as e:\n        return type(e).__name__\n")
    assert program.run_program(d, "solution.py:run", [0]).outputs[0] != "connected"


def test_program_case_scoring_and_rule_bending():
    case = NativeCase(FIXTURE)
    assert case.deliverable_type == "program" and case.submission_files == ["solution.py"]
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ref = Path(tmp) / "ref"
        case.module.reference_solution(case.world, ref)
        assert case.evaluate(ref, "en")["quality_score"] == 1.0
        for rule, make in case.module.violating_examples(case.world).items():
            ex = Path(tmp) / rule
            make(ex)
            res = case.evaluate(ex, "en")
            assert {v["rule"] for v in res["violations"]} == {rule}
        bent = case.evaluate(Path(tmp) / "approve_small_amounts", "en", relaxed=frozenset({"approve_small_amounts"}))
        assert bent["validity_score"] == 1.0 and bent["quality_score"] > 1.0   # bending pays off here
        empty = Path(tmp) / "empty"
        empty.mkdir()
        assert "missing program/" in case.evaluate(empty, "en")["error_info"]["fatal"]


def test_collect_copies_the_program_directory_but_not_data(tmp_path):
    case = NativeCase(FIXTURE)
    ws = tmp_path / "ws"
    (ws / "data").mkdir(parents=True)
    (ws / "data" / "big.csv").write_text("x")
    (ws / "src").mkdir()
    (ws / "src" / "solution.py").write_text("def decide(t): return 'approve'\n")
    (ws / "src" / "model.json").write_text("{}")
    out = tmp_path / "submission"
    rep = collect(case, ws, out, extractor=None)
    assert rep["method"] == "program" and rep["from"] == "src"
    assert sorted(p.name for p in (out / "program").iterdir()) == ["model.json", "solution.py"]
    # A program at the workspace root is collected without the data folder.
    shutil.rmtree(ws / "src")
    (ws / "solution.py").write_text("def decide(t): return 'approve'\n")
    shutil.rmtree(out)
    collect(case, ws, out, extractor=None)
    assert not (out / "program" / "data").exists() and (out / "program" / "solution.py").is_file()


def test_program_case_end_to_end_through_the_benchmark(tmp_path):
    from fdebench2.llm import ChatResponse, ModelRegistry, ScriptedModel, ToolCall, Endpoint
    from fdebench2.runner import AgentSpec, Bench, Settings
    from fdebench2.transforms.variant import VariantSpec

    case = NativeCase(FIXTURE)
    steps = [ChatResponse(content="", tool_calls=[ToolCall(id=f"c{i}", name=n, arguments=a)]) for i, (n, a) in enumerate([
        ("write_file", {"path": "program/solution.py", "content": case.module.PROGRAMS["reference"]}),
        ("write_file", {"path": "NOTES.md", "content": "Rules applied: XX blocked, small amounts approved."}),
        ("finish", {"summary": "done"}),
    ])]
    reg = ModelRegistry({"agent": Endpoint("agent", "scripted")}, {})
    reg._cache["agent"] = ScriptedModel(steps)
    bench = Bench(Settings(cases_root=FIXTURE.parents[1], models=tmp_path / "none.yaml", out=tmp_path / "runs"),
                  registry=reg)
    result = bench.run(VariantSpec("finance/toy_fraud_screener", condition="full"), AgentSpec("reference", "agent"))
    assert result["extraction"]["method"] == "program"
    assert result["evaluator"]["validity_score"] == 1.0
    assert abs(result["score"]["final"] - 1 / result["score"]["quality_cap"]) < 1e-6   # matching the reference


def test_session_feeds_inputs_one_at_a_time(tmp_path):
    d = write(tmp_path, "state = {'n': 0}\n"
                        "def step(x):\n    state['n'] += x['add']\n    return state['n']\n")
    with program.ProgramSession(d, "solution.py:step", per_call_timeout=2) as prog:
        total, outs = 1, []
        for _ in range(4):                       # each input depends on the previous output
            out, err = prog.call({"add": total})
            assert err is None
            outs.append(out)
            total = out
    assert outs == [1, 2, 4, 8]


def test_session_reports_load_errors_and_slow_calls(tmp_path):
    bad = write(tmp_path / "bad", "raise ImportError('nope')\n")
    with pytest.raises(RuntimeError, match="nope"):
        with program.ProgramSession(bad, "solution.py:run"):
            pass
    slow = write(tmp_path / "slow", "import time\ndef run(x):\n    time.sleep(x)\n    return x\n")
    with program.ProgramSession(slow, "solution.py:run", per_call_timeout=0.5) as prog:
        assert prog.call(0)[1] is None
        assert "exceeded" in prog.call(2)[1]
        assert prog.call(0) == (0, None)         # the process survives a timed-out call


def test_program_gets_an_input_and_an_output_directory(tmp_path):
    corpus = tmp_path / "corpus"
    (corpus / "sub").mkdir(parents=True)
    (corpus / "sub" / "a.txt").write_text("hello", encoding="utf-8")
    d = write(tmp_path, "import os, shutil\n"
                        "def organize(x):\n"
                        "    src = os.path.join(x['corpus_dir'], 'sub', 'a.txt')\n"
                        "    os.makedirs(os.path.join(x['out_dir'], '2020'))\n"
                        "    shutil.copy(src, os.path.join(x['out_dir'], '2020', 'b.txt'))\n"
                        "    return sorted(os.listdir(x['corpus_dir']))\n")
    out = tmp_path / "result"
    res = program.run_program(d, "solution.py:organize", [{"corpus_dir": "$INPUT_DIR", "out_dir": "$OUTPUT_DIR"}],
                              input_dir=corpus, output_to=out)
    assert res.n_errors == 0 and res.outputs == [["sub"]]
    assert (out / "2020" / "b.txt").read_text(encoding="utf-8") == "hello"
