"""Run isolation, collection safety, campaign bookkeeping and reporting (no docker needed)."""

import json
import os
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from fdebench2 import program
from fdebench2.agents.cli import CLIAgent, _listen_address
from fdebench2.agents.tools import call_tool
from fdebench2.cases import NativeCase
from fdebench2.llm import ChatResponse, Endpoint, ModelRegistry, ScriptedModel, ToolCall
from fdebench2.runner import AgentSpec, Bench, RunLocked, Settings, claim, expand, load_campaign, run_status
from fdebench2.sandbox import DockerSandbox, LocalSandbox, sanitize, unstage
from fdebench2.scoring.extract import collect, read_notes
from fdebench2.scoring.report import pass_hat_k, pass_k_table, report
from fdebench2.transforms.language import Translator
from fdebench2.transforms.variant import VariantSpec, build_variant

from conftest import NATIVE, REPO

PROGRAM_CASE = Path(__file__).parent / "fixtures" / "program_case" / "finance" / "toy_fraud_screener"


def call(name, **args):
    return ChatResponse(content="", tool_calls=[ToolCall(id=f"c_{name}", name=name, arguments=args)])


def _ws(tmp_path) -> tuple[Path, Path]:
    """A workspace with client data, and a secret file outside it."""
    ws = tmp_path / "ws"
    (ws / "data").mkdir(parents=True)
    (ws / "data" / "stores.csv").write_text("id\nC1\n", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("ground truth", encoding="utf-8")
    return ws, secret


# ── symlinks and special files ───────────────────────────────────────────────

def test_sanitize_removes_links_and_special_files(tmp_path):
    ws, secret = _ws(tmp_path)
    (tmp_path / "other_run").mkdir()
    (ws / "NOTES.md").symlink_to(secret)
    (ws / "routes.json").symlink_to(secret)
    (ws / "out").symlink_to(tmp_path / "other_run", target_is_directory=True)
    os.mkfifo(ws / "pipe")
    (ws / "plan.txt").write_text("mine", encoding="utf-8")

    case = NativeCase(REPO / "cases" / NATIVE)
    # Collection never follows a link, even before sanitizing ...
    assert read_notes(ws) == ""
    assert collect(case, ws, tmp_path / "sub", extractor=None)["method"] == "none"

    removed = sanitize(ws)
    assert removed == sorted([f"NOTES.md -> {secret}", f"routes.json -> {secret}",
                              f"out -> {tmp_path / 'other_run'}", "pipe (special file)"])
    assert sorted(p.name for p in ws.iterdir()) == ["data", "plan.txt"]
    assert secret.read_text(encoding="utf-8") == "ground truth" and (tmp_path / "other_run").is_dir()


def test_sanitize_unlocks_what_the_agent_locked(tmp_path):
    """A file or folder the agent made unreadable would break collection and the move back from staging."""
    ws, secret = _ws(tmp_path)
    (ws / "out").mkdir()
    (ws / "out" / "routes.json").write_text("{}", encoding="utf-8")
    (ws / "out" / "gt").symlink_to(secret)
    os.chmod(ws / "out" / "routes.json", 0)
    os.chmod(ws / "out", 0)
    os.chmod(ws, 0o100)
    assert sanitize(ws) == [f"out/gt -> {secret}"]
    assert all(stat.S_IMODE(os.stat(d).st_mode) & 0o700 == 0o700 for d in (ws, ws / "out"))
    assert stat.S_IMODE(os.stat(ws / "out" / "routes.json").st_mode) & 0o600 == 0o600


def test_program_collection_does_not_enter_a_linked_directory(tmp_path):
    ws, _ = _ws(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "solution.py").write_text("def decide(t): return 'approve'\n")
    (ws / "program").symlink_to(outside, target_is_directory=True)
    rep = collect(NativeCase(PROGRAM_CASE), ws, tmp_path / "sub", extractor=None)
    assert rep["method"] == "none" and not (tmp_path / "sub" / "program").exists()


def test_file_tools_stay_in_the_workspace(tmp_path):
    ws, secret = _ws(tmp_path)
    (ws / "link.txt").symlink_to(secret)
    (ws / "linkdir").symlink_to(tmp_path, target_is_directory=True)
    os.mkfifo(ws / "pipe")
    ctx = SimpleNamespace(workspace=ws, sandbox=LocalSandbox(ws))
    assert "outside" in call_tool(ctx, "read_file", {"path": "../secret.txt"})
    assert "symbolic link" in call_tool(ctx, "read_file", {"path": "link.txt"})
    assert "symbolic link" in call_tool(ctx, "write_file", {"path": "linkdir/new.txt", "content": "x"})
    assert not (tmp_path / "new.txt").exists()
    assert "not a regular file" in call_tool(ctx, "read_file", {"path": "pipe"})     # and does not block
    assert call_tool(ctx, "read_file", {"path": "data/stores.csv"}) == "id\nC1"
    docker = SimpleNamespace(workspace=ws, sandbox=DockerSandbox(ws, image="img"))  # paths as the container sees them
    assert "data/stores.csv" in call_tool(docker, "list_files", {"path": "/workspace"})
    assert call_tool(docker, "read_file", {"path": "/workspace/data/stores.csv"}) == "id\nC1"


def test_notes_are_read_from_the_root_else_the_shallowest_outside_data_and_inbox(tmp_path):
    ws, _ = _ws(tmp_path)
    for rel, text in [("data/NOTES.md", "client"), ("inbox/NOTES.md", "event"), ("a/b/NOTES.md", "deep"),
                      ("a/NOTES.md", "shallow")]:
        (ws / rel).parent.mkdir(parents=True, exist_ok=True)
        (ws / rel).write_text(text, encoding="utf-8")
    assert read_notes(ws) == "shallow"
    (ws / "NOTES.md").write_text("root", encoding="utf-8")
    assert read_notes(ws) == "root"


# ── extractor ────────────────────────────────────────────────────────────────

class _Recorder(ScriptedModel):
    def chat(self, messages, tools=None, **kwargs):
        self.tools = [t["function"]["name"] for t in tools or []]
        return super().chat(messages, tools, **kwargs)


def test_extractor_has_no_shell_and_sees_only_the_agents_files(tmp_path):
    ws, _ = _ws(tmp_path)
    (ws / "inbox").mkdir()
    (ws / "inbox" / "01_event.md").write_text("event", encoding="utf-8")
    (ws / ".agent").mkdir()
    (ws / ".agent" / "mcp.json").write_text("{}", encoding="utf-8")
    (ws / "my_routes.txt").write_text("V1: C1", encoding="utf-8")
    model = _Recorder([call("list_files", path="."), call("read_file", path="data/stores.csv"),
                       call("read_file", path="../secret.txt"), call("bash", command="cat ../secret.txt"),
                       call("write_file", path="_submission/routes.json", content='{"routes": []}'),
                       call("finish", summary="done")])
    rep = collect(NativeCase(REPO / "cases" / NATIVE), ws, tmp_path / "run" / "submission", model)

    assert "bash" not in model.tools and {"read_file", "write_file", "list_files", "finish"} <= set(model.tools)
    listing, read_data, read_secret, shell = [m["content"] for m in model.calls[-1] if m["role"] == "tool"][:4]
    assert "my_routes.txt" in listing and not any(x in listing for x in ("data", "inbox", ".agent"))
    assert read_data.startswith("error") and "outside" in read_secret and "unknown tool 'bash'" in shell
    assert rep["files"] == ["routes.json"] and (tmp_path / "run" / "submission" / "routes.json").is_file()


# ── seeds, trials and campaign bookkeeping ───────────────────────────────────

def test_noise_seed_and_trial_are_separate(cases_root, tmp_path):
    base = VariantSpec(NATIVE)
    assert base.key().endswith("__s0") and VariantSpec(NATIVE, noise_seed=2).key().endswith("__s2")
    assert VariantSpec(NATIVE, trial=1).key() == base.key() + "__t1"
    old = VariantSpec.from_dict({**{k: v for k, v in asdict(base).items() if k not in ("noise_seed", "trial")},
                                 "seed": 3})
    assert old.noise_seed == 3 and old.trial == 0 and old.key().endswith("__s3")

    case = NativeCase(cases_root / NATIVE)

    def view(**kw):
        v = build_variant(VariantSpec(NATIVE, engagement="messy", **kw), case, tmp_path / str(kw) / "ws",
                          Translator(None, tmp_path / "c"))
        return json.dumps([asdict(e) for e in v.events] + v.noise, sort_keys=True), v.information
    # A repeated trial is the same variant; another noise seed is another engagement.
    assert view(trial=0) == view(trial=1)
    assert len({view(noise_seed=s) for s in range(6)}) > 1


def test_campaign_trials_seeds_alias_and_dedup(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("""
defaults: {models: m.yaml, seeds: [0, 1], trials: 2, cases: [healthcare/hospital_appointment_scheduler]}
agents: [{harness: reference, model: a}]
experiments:
  all_rules: {}
  only_a: {rule_seeds: [1]}
""")
    settings, agents, jobs, _ = load_campaign(cfg)
    assert len(jobs) == 8
    assert {(s.noise_seed, s.trial) for _, s in jobs} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    bench = Bench(Settings(cases_root=REPO / "cases", models=tmp_path / "none.yaml", out=tmp_path / "runs"))
    runs = expand(bench, agents, jobs)
    keys = [spec.key() for _, spec in runs]
    assert len(runs) == 12 and len(set(keys)) == 12          # rule seeds 1/2/3 x 2 seeds x 2 trials, 1 once
    assert any(k.endswith("__s1__t1") for k in keys)

    cfg.write_text("defaults: {models: m.yaml}\nagents: [{harness: reference, model: a}, "
                   "{harness: reference, model: a, max_steps: 5}]\n")
    with pytest.raises(ValueError, match="share run directories"):
        load_campaign(cfg)


def test_the_old_sandbox_env_list_is_not_dropped_silently(tmp_path, capsys):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("defaults: {models: m.yaml, sandbox: {kind: docker, image: img, env: [OPENAI_API_KEY]}}\n")
    load_campaign(cfg)
    assert "sandbox.env is no longer read" in capsys.readouterr().err


def test_a_run_directory_is_claimed_by_one_worker(tmp_path):
    run_dir = tmp_path / "runs" / "agent" / "key"
    with claim(run_dir):
        with pytest.raises(RunLocked):
            with claim(run_dir):
                pass
    with claim(run_dir):                                   # released after use
        pass
    dead = subprocess.Popen(["true"])
    dead.wait()
    lock = run_dir.with_name("key.lock")
    lock.write_text(json.dumps({"host": socket.gethostname(), "pid": dead.pid}))
    with claim(run_dir):                                   # a file left by a dead worker holds nothing
        assert json.loads(lock.read_text())["pid"] == os.getpid()
    assert not lock.exists()

    # Another process holds it until it ends, even when it is killed and never cleans up.
    holder = subprocess.Popen([sys.executable, "-c", "import fcntl, os, sys, time\n"
                               "fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR)\n"
                               "fcntl.flock(fd, fcntl.LOCK_EX)\nprint('held', flush=True)\ntime.sleep(60)",
                               str(lock)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(RunLocked):
            with claim(run_dir):
                pass
    finally:
        holder.send_signal(signal.SIGKILL)
        holder.wait()
    with claim(run_dir):
        pass


def _bench(cases_root, tmp_path, steps=None) -> Bench:
    reg = ModelRegistry({"agent": Endpoint("agent", "scripted")}, {})
    case = NativeCase(cases_root / NATIVE)
    out = tmp_path / "ref"
    out.mkdir(exist_ok=True)
    case.write_reference(out)
    reg._cache["agent"] = ScriptedModel(steps or [
        call("write_file", path="routes.json", content=(out / "routes.json").read_text(encoding="utf-8")),
        call("write_file", path="NOTES.md", content="Routes follow the van capacity and premium-first rules."),
        call("finish", summary="done")])
    return Bench(Settings(cases_root=cases_root, models=tmp_path / "none.yaml", out=tmp_path / "runs"), registry=reg)


def test_results_are_reused_only_while_the_case_and_config_are_unchanged(cases_root, tmp_path, monkeypatch):
    spec, agent = VariantSpec(NATIVE, condition="full"), AgentSpec("reference", "agent")
    bench = _bench(cases_root, tmp_path)
    first = bench.run(spec, agent)
    assert first["status"] == "ok" and first["fingerprint"] == bench.fingerprint(spec, agent)
    assert first["usage"]["total_tokens"] == 0 and first["agent_run"]["sanitized"] == []

    again = _bench(cases_root, tmp_path)
    assert again.run(spec, agent) == first and again.registry._cache["agent"].calls == []     # reused

    with (cases_root / NATIVE / "case.yaml").open("a", encoding="utf-8") as f:
        f.write("\n# edited\n")
    edited = _bench(cases_root, tmp_path)
    assert edited.fingerprint(spec, agent) != first["fingerprint"]
    assert edited.run(spec, agent)["status"] == "ok" and edited.registry._cache["agent"].calls    # re-run

    # An infrastructure failure is recorded, never reused, and never scored as the agent's 0.
    broken = _bench(cases_root, tmp_path)
    monkeypatch.setattr(broken, "_agent", lambda a: (_ for _ in ()).throw(RuntimeError("docker is down")))
    failed = broken.run(spec, agent, force=True)
    assert failed["status"] == "infra_error" and failed["score"] is None and "docker is down" in failed["error"]
    fixed = _bench(cases_root, tmp_path)
    assert fixed.run(spec, agent)["status"] == "ok"

    with claim(fixed.run_dir(fixed.resolve(spec), agent)):
        with pytest.raises(RunLocked):
            fixed.run(spec, agent, force=True)


def test_run_status():
    direct = {"method": "direct", "files": ["a.csv"]}
    assert run_status("finished", direct, True) == "ok" and run_status("max_steps", direct, False) == "invalid"
    assert run_status("error", direct, True) == "agent_error" and run_status("out_of_time", direct, True) == "timeout"
    assert run_status("finished", {"method": "none", "missing": ["a.csv"]}, False) == "extract_failed"
    assert run_status("finished", {"method": "extractor", "files": []}, False) == "extract_failed"
    assert run_status("harness_error", {}, False) == "harness_error"


# ── report ───────────────────────────────────────────────────────────────────

def _result(model, case, final, valid, status=None, trial=0, ratio=None, tokens=100, cost=0.01):
    spec = VariantSpec(case, trial=trial)
    score = None if final is None else {
        "final": final, "gates": {"validity": valid}, "components": {"quality": final},
        "quality_raw": final, **({"quality_ratio": ratio} if ratio is not None else {})}
    return {"spec": asdict(spec), "agent": {"harness": "reference", "model": model}, "key": spec.key(),
            "status": status or ("ok" if valid else "invalid"), "score": score, "clarification": None,
            "error": "boom" if final is None else "", "usage": {"total_tokens": tokens, "cost_usd": cost}}


def test_pass_hat_k():
    assert pass_hat_k(4, 2, 1) == 0.5 and pass_hat_k(4, 2, 2) == 1 / 6
    assert pass_hat_k(4, 4, 4) == 1.0 and pass_hat_k(3, 2, 3) == 0.0
    rows = [_result("m", "x/a", 1.0, True, trial=0), _result("m", "x/a", 1.0, True, trial=1),
            _result("m", "x/a", 0.0, False, trial=2)]
    text = pass_k_table(rows)
    assert "| agent | variants | pass^1 | pass^2 | pass^3 |" in text
    assert "| reference--m | 1 | 0.667 | 0.333 | 0.000 |" in text
    assert pass_k_table(rows[:1]) is None                   # no repeated trials, no table


def test_report_counts_statuses_and_leaves_errors_out_of_the_means(tmp_path):
    rows = [_result("m", "x/a", 1.0, True, ratio=1.2), _result("m", "x/b", 0.5, True, ratio=0.8),
            _result("m", "x/c", 0.0, False, ratio=0.0),
            _result("m", "x/d", None, False, status="infra_error", tokens=0, cost=None),
            _result("m", "x/e", None, False, status="harness_error", tokens=0, cost=None)]
    for i, r in enumerate(rows):
        d = tmp_path / "out" / "m" / str(i)
        d.mkdir(parents=True)
        (d / "result.json").write_text(json.dumps(r), encoding="utf-8")
    (tmp_path / "out" / "m" / "0" / "workspace").mkdir()
    (tmp_path / "out" / "m" / "0" / "workspace" / "result.json").write_text("an agent's own file", encoding="utf-8")
    text = report(tmp_path / "out")
    policy_row = next(line for line in text.splitlines() if line.startswith("| reference--m | baseline |"))
    cells = [c.strip() for c in policy_row.strip("|").split("|")]
    assert cells[2] == "3" and cells[3].startswith("0.500")          # n and final: 3 scored runs, mean 0.5
    assert cells[5] == "0.500" and cells[6] == "0.667"               # quality (norm), ratio vs ref
    status_row = next(line for line in text.splitlines() if line.startswith("| reference--m | 5 |"))
    assert [c.strip() for c in status_row.strip("|").split("|")][2:11] == \
        ["2", "1", "0", "0", "0", "1", "1", "60", "0.0100"]
    assert "not scored" in text and "`" + rows[3]["key"] + "`: infra_error: boom" in text
    # Older results (no ratio) still render.
    assert "| – |" in report_without_ratio(tmp_path)


def report_without_ratio(tmp_path) -> str:
    d = tmp_path / "old" / "m" / "0"
    d.mkdir(parents=True)
    r = _result("m", "x/a", 1.0, True)
    del r["status"], r["usage"]
    (d / "result.json").write_text(json.dumps(r), encoding="utf-8")
    return report(tmp_path / "old")


# ── container: opaque mount, environment, client bridge ──────────────────────

def test_docker_mounts_an_opaque_copy_of_the_workspace(cases_root, tmp_path):
    bench = Bench(Settings(cases_root=cases_root, models=tmp_path / "none.yaml", out=tmp_path / "runs",
                           sandbox={"kind": "docker", "image": "img"}, isolation="strict"))
    run_dir = bench.run_dir(VariantSpec(NATIVE, policy="regulated_strict", difficulty="hard"),
                            AgentSpec("claude_code", "m"))
    workspace = run_dir / "workspace"
    (workspace / "data").mkdir(parents=True)
    (workspace / "data" / "stores.csv").write_text("id\n", encoding="utf-8")
    sb = bench._sandbox(NATIVE, workspace)
    argv = sb.run_argv()
    mount = argv[argv.index("-v") + 1]
    assert mount.endswith(":/workspace") and "-e" not in argv
    assert not any(part in mount for part in ("regulated_strict", "d-hard", "bakery", "claude_code", str(run_dir)))
    assert Path(mount.rsplit(":", 1)[0]).parent == Path(tempfile.gettempdir()).resolve()
    assert ("--user" in argv) == (os.getuid() != 0)

    (sb.workspace / "routes.json").write_text("{}", encoding="utf-8")       # what the agent wrote
    (sb.workspace / "gt").symlink_to(cases_root, target_is_directory=True)
    assert sanitize(sb.workspace) == [f"gt -> {cases_root}"]
    unstage(sb.workspace, workspace)
    assert sorted(p.name for p in workspace.iterdir()) == ["data", "routes.json"] and not sb.workspace.exists()


def test_a_run_that_fails_before_the_agent_starts_still_puts_the_staged_copy_back(cases_root, tmp_path,
                                                                                  monkeypatch):
    import fdebench2.runner as runner
    real_stage, staged = runner.stage, []
    monkeypatch.setattr(runner, "stage", lambda ws: staged.append(real_stage(ws)) or staged[-1])
    monkeypatch.setattr(runner, "render_task_prompt", lambda *a: (_ for _ in ()).throw(RuntimeError("no prompt")))
    bench = Bench(Settings(cases_root=cases_root, models=tmp_path / "none.yaml", out=tmp_path / "runs",
                           sandbox={"kind": "docker", "image": "img"}, isolation="strict"))
    spec, agent = VariantSpec(NATIVE, condition="full"), AgentSpec("reference", "agent")
    result = bench.run(spec, agent)                 # docker itself may be missing too: stop() is then a no-op
    assert result["status"] == "infra_error" and "no prompt" in result["agent_run"]["detail"]["error"]
    assert not staged[0].exists() and (bench.run_dir(bench.resolve(spec), agent) / "workspace" / "data").is_dir()


def test_cli_harness_gets_only_its_own_variables_and_the_bridge_token(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
    argv = DockerSandbox(tmp_path, image="img").exec_argv(["claude"], env=CLIAgent("claude_code").env_names())
    assert "ANTHROPIC_API_KEY" in argv and "OPENAI_API_KEY" not in argv and not any("sk-" in a for a in argv)
    assert "OPENAI_API_KEY" in CLIAgent("opencode", "openai/gpt-6").env_names()
    assert CLIAgent("codex", env=["MY_PROXY_KEY"]).env_names() == ("MY_PROXY_KEY",)

    ws = tmp_path / "ws"
    ws.mkdir()
    ctx = SimpleNamespace(workspace=ws, run_dir=tmp_path / "run")
    url, bearer = "http://172.17.0.1:9000/mcp", {"Authorization": "Bearer TOK"}
    CLIAgent("claude_code").build_command(ctx, "p", url=url, token="TOK")
    assert json.loads((ws / ".agent" / "mcp.json").read_text())["mcpServers"]["client"]["headers"] == bearer
    codex = CLIAgent("codex").build_command(ctx, "p", url=url, token="TOK")
    headers = next(c for c in codex if c.startswith("mcp_servers.client.http_headers="))
    assert tomllib.loads("h = " + headers.split("=", 1)[1])["h"] == bearer
    CLIAgent("gemini").build_command(ctx, "p", url=url, token="TOK")
    assert json.loads((ws / ".gemini" / "settings.json").read_text())["mcpServers"]["client"]["headers"] == bearer
    CLIAgent("opencode").build_command(ctx, "p", url=url, token="TOK")
    assert json.loads((ws / "opencode.json").read_text())["mcp"]["client"]["headers"] == bearer


def test_bridge_listens_on_the_most_specific_address():
    assert _listen_address("127.0.0.1")[0] == "127.0.0.1"
    assert _listen_address("203.0.113.7")[0] == "0.0.0.0"          # not this host's: all interfaces + token
    assert _listen_address(None)[0] == "0.0.0.0"


def test_bridge_requires_the_runs_bearer_token(cases_root, tmp_path):
    pytest.importorskip("mcp")
    from starlette.testclient import TestClient
    from fdebench2.mcp_bridge import build_server, http_app
    from fdebench2.session import Session

    case = NativeCase(cases_root / NATIVE)
    run_dir = tmp_path / "run"
    v = build_variant(VariantSpec(case.id), case, run_dir / "workspace", Translator(None, tmp_path / "c"))
    session = Session(v, run_dir, run_dir / "workspace", ScriptedModel(lambda m: ChatResponse(content="ok")),
                      use_steps=False)
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}
    head = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    # On this host, and as a container reaches it (whose Host header is not localhost).
    for host, url in [("127.0.0.1", "http://127.0.0.1:9000"), ("0.0.0.0", "http://host.docker.internal:9000")]:
        with TestClient(http_app(build_server(session), "TOK", host), base_url=url) as client:
            assert client.post("/mcp", json=init, headers=head).status_code == 401
            assert client.post("/mcp", json=init, headers={**head, "Authorization": "Bearer nope"}).status_code == 401
            assert client.post("/mcp", json=init, headers={**head, "Authorization": "Bearer TOK"}).status_code == 200

    env = {k: v for k, v in os.environ.items() if k != "FDEB2_BRIDGE_TOKEN"}
    p = subprocess.run([sys.executable, "-m", "fdebench2.mcp_bridge", "--run-dir", str(run_dir),
                        "--http", "127.0.0.1:0"], capture_output=True, text=True, env=env, cwd=REPO, timeout=60)
    assert p.returncode == 2 and "FDEB2_BRIDGE_TOKEN" in p.stderr


FAKE_CLI = '''import asyncio, json, os, shutil, sys, urllib.error, urllib.request
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

workspace, reference, secret = sys.argv[1:]
cfg = json.load(open(os.path.join(workspace, ".agent", "mcp.json")))["mcpServers"]["client"]
print("WORKSPACE:", workspace)
try:
    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        urllib.request.Request(cfg["url"], data=b"{}", method="POST"))
except urllib.error.HTTPError as e:
    print("NO TOKEN:", e.code)

async def main():
    async with create_mcp_http_client(headers=cfg["headers"]) as http:
        async with streamable_http_client(cfg["url"], http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as s:
                await s.initialize()
                print("TOOL:", (await s.call_tool("check_inbox", {})).content[0].text)
asyncio.run(main())
shutil.copy(reference, os.path.join(workspace, "routes.json"))
os.symlink(secret, os.path.join(workspace, "NOTES.md"))
'''


def test_isolated_cli_run_end_to_end_without_docker(cases_root, tmp_path, monkeypatch):
    """Everything of an isolated CLI run but the container: an opaque staged workspace, the client bridge over
    HTTP behind the run's token, sanitizing before collection, the workspace put back and scored."""
    if not hasattr(pytest.importorskip("mcp.client.streamable_http"), "streamable_http_client"):
        pytest.skip("mcp client API of another version")
    import fdebench2.runner as runner

    case = NativeCase(cases_root / NATIVE)
    (tmp_path / "ref").mkdir()
    case.write_reference(tmp_path / "ref")
    _, secret = _ws(tmp_path)
    (tmp_path / "fake_cli.py").write_text(FAKE_CLI, encoding="utf-8")

    class FakeDocker(DockerSandbox):           # the CLI runs as a host process instead of in a container
        def start(self): pass
        def stop(self): pass
        def gateway(self): return "127.0.0.1"

        def exec_argv(self, argv, env=()):
            if argv[-1] == "--version":
                return [sys.executable, "-c", "print('fake 1.0')"]
            return [sys.executable, str(tmp_path / "fake_cli.py"), str(self.workspace),
                    str(tmp_path / "ref" / "routes.json"), str(secret)]
    monkeypatch.setattr(runner, "DockerSandbox", FakeDocker)
    (tmp_path / "models.yaml").write_text("{}\n", encoding="utf-8")
    bench = Bench(Settings(cases_root=cases_root, models=tmp_path / "models.yaml", out=tmp_path / "runs",
                           sandbox={"kind": "docker", "image": "img"}, isolation="strict"))
    spec, agent = VariantSpec(NATIVE, condition="full"), AgentSpec("claude_code", "m")
    result = bench.run(spec, agent)

    run_dir = bench.run_dir(bench.resolve(spec), agent)
    log = (run_dir / "agent_stdout.log").read_text(encoding="utf-8")
    staged = log.split("WORKSPACE: ", 1)[1].splitlines()[0]
    assert "NO TOKEN: 401" in log and "TOOL: (no new messages)" in log
    assert spec.key() not in staged and "bakery" not in staged and not Path(staged).exists()
    assert result["agent_run"]["sanitized"] == [f"NOTES.md -> {secret}"]
    assert result["status"] == "ok" and result["extraction"]["method"] == "direct"
    assert (run_dir / "workspace" / "routes.json").is_file() and not (run_dir / "workspace" / "NOTES.md").exists()


# ── program runner ───────────────────────────────────────────────────────────

def test_program_timeout_removes_its_docker_container(tmp_path, monkeypatch):
    monkeypatch.delenv("FDEB2_PROGRAM_RUNNER", raising=False)
    program.configure("local")
    d = tmp_path / "program"
    d.mkdir()
    (d / "solution.py").write_text("import time\ndef run(x):\n    time.sleep(5)\n    return x\n")
    real_launch, real_run, removed = program._launch, subprocess.run, []

    def launch(cfg, tmp, has_io):                  # a local process standing in for a named container
        proc, paths, _ = real_launch(cfg, tmp, has_io)
        return proc, paths, "fdeb2-prog-test"

    def run(argv, *a, **kw):
        if argv[0] == "docker":
            removed.append(argv)
            return subprocess.CompletedProcess(argv, 0)
        return real_run(argv, *a, **kw)
    monkeypatch.setattr(program, "_launch", launch)
    monkeypatch.setattr(program.subprocess, "run", run)
    res = program.run_program(d, "solution.py:run", [1, 2], total_timeout=1.0)
    assert res.status == "timeout" and removed == [["docker", "rm", "-f", "fdeb2-prog-test"]]


def test_docker_program_container_is_named_and_unprivileged(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(program.subprocess, "Popen", lambda cmd, **kw: seen.append(cmd) or SimpleNamespace())
    _, _, name = program._launch(program._Config("docker", "img"), tmp_path, False)
    cmd = seen[0]
    assert cmd[cmd.index("--name") + 1] == name and name.startswith("fdeb2-prog-")
    assert "--network" in cmd and cmd[cmd.index("--network") + 1] == "none"
    assert ("--user" in cmd) == (os.getuid() != 0)
