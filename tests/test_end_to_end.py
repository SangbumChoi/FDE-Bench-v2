import json
from pathlib import Path

from fdebench2.cases import V1Case
from fdebench2.llm import ChatResponse, Endpoint, ModelRegistry, ScriptedModel, ToolCall
from fdebench2.runner import AgentSpec, Bench, Settings
from fdebench2.scoring.evaluate import run_evaluator
from fdebench2.scoring.policy_score import RunFacts, apply_policy
from fdebench2.session import Session, read_transcript
from fdebench2.transforms.language import Translator
from fdebench2.transforms.policy import CaseRule, CaseRules, Policy
from fdebench2.transforms.variant import VariantSpec, build_variant

CASE = "toy_001_order_allocation"


def greedy(case_dir: Path, allowed=("W1", "W2")) -> dict:
    import csv
    orders = [(r["订单号"], int(r["数量"])) for r in csv.DictReader(open(case_dir / "data" / "orders.csv", encoding="utf-8"))]
    stock = {"W1": 60, "W2": 80, "W3": 200}
    out = []
    for oid, q in orders:
        for wh in allowed:
            if stock[wh] >= q:
                stock[wh] -= q
                out.append({"order_id": oid, "warehouse": wh})
                break
    return {"assignments": out}


def call(name, **args):
    return ChatResponse(content="", tool_calls=[ToolCall(id=f"c_{name}", name=name, arguments=args)])


def scripted_agent(solution: dict):
    steps = [
        call("list_files", path="data"),
        call("ask_customer", questions="W3 仓库这次能用吗？\n订单可以拆开从多个仓库发吗？"),
        call("bash", command="head -3 data/orders.csv"),
        call("write_file", path="solution.json", content=json.dumps(solution)),
        call("write_file", path="NOTES.md", content="假设：W3 正在盘点不可用；订单不拆单；按成本贪心分配。"),
        call("finish", summary="已按成本最低分配，W3 未使用。"),
    ]
    return ScriptedModel(steps, name="agent")


def registry(agent_model) -> ModelRegistry:
    reg = ModelRegistry({"agent": Endpoint("agent", "scripted", usd_per_mtok_in=1, usd_per_mtok_out=2),
                         "client": Endpoint("client", "scripted"), "judge": Endpoint("judge", "scripted")},
                        {"customer": "client", "judges": ["judge"]})
    reg._cache["agent"] = agent_model
    reg._cache["client"] = ScriptedModel(lambda m: ChatResponse(content="W3 在盘点，不能用。\n不能拆单。"))
    reg._cache["judge"] = ScriptedModel(lambda m: ChatResponse(content='{"covered": true, "questions": [1, 2]}'))
    return reg


def test_reference_run_scores_like_v1(v1_root, tmp_path):
    case_dir = v1_root / "case" / CASE
    bench = Bench(Settings(cases_root=v1_root, models=tmp_path / "none.yaml", out=tmp_path / "runs"),
                  registry=registry(scripted_agent(greedy(case_dir))))
    result = bench.run(VariantSpec(CASE), AgentSpec("reference", "agent"))

    assert result["agent_run"]["status"] == "finished"
    assert result["extraction"]["method"] == "direct"
    assert result["evaluator"]["validity_score"] == 1.0
    assert abs(result["evaluator"]["quality_score"] - 1.0) < 1e-9
    assert result["clarification"]["recall"] == 1.0
    assert result["score"]["final"] == 1.0  # baseline: quality only

    run_dir = bench.run_dir(VariantSpec(CASE), AgentSpec("reference", "agent"))
    kinds = [r["kind"] for r in read_transcript(run_dir)]
    assert "ask" in kinds and "finish" in kinds
    # The agent never saw the hidden requirements.
    assert "盘点" not in (run_dir / "prompt.md").read_text(encoding="utf-8")


def test_rescoring_under_other_policies(v1_root, tmp_path):
    case_dir = v1_root / "case" / CASE
    bench = Bench(Settings(cases_root=v1_root, models=tmp_path / "none.yaml", out=tmp_path / "runs"),
                  registry=registry(scripted_agent(greedy(case_dir))))
    agent = AgentSpec("reference", "agent")
    bench.run(VariantSpec(CASE), agent)
    run_dir = bench.run_dir(VariantSpec(CASE), agent)
    result = bench.score(run_dir, agent, extra_policies=["regulated_strict", "enterprise_balanced"])
    # Chinese client, Chinese questions and notes: communication is perfect, and the ask came before any write.
    assert result["rescored"]["regulated_strict"] > 0.9
    assert 0 < result["rescored"]["enterprise_balanced"] <= 1


def _toy_rules() -> CaseRules:
    return CaseRules(CASE, [CaseRule("valid", "HC0_", "physical"), CaseRule("stock", "HC1_", "physical"),
                            CaseRule("w3_stocktake", "HC2_", "business_policy")], hook="toy_hook")


def test_policy_decides_whether_a_business_rule_may_bend(v1_root, tmp_path):
    case = V1Case.load(v1_root / "case" / CASE)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "solution.json").write_text(json.dumps(greedy(case.root, allowed=("W3",))))
    raw = run_evaluator(case, sub)
    assert raw["validity_score"] == 0.0 and raw["error_info"]["constraint"][0].startswith("HC2_")

    strict = Policy(id="strict", title="s", exceptions="forbidden")
    bendable = Policy(id="bend", title="b", exceptions="justify", soft_rule_penalty=0.05,
                      rule_classes={"physical": "hard", "contractual": "hard", "business_policy": "soft"})
    kw = dict(case=case, submission_dir=sub, rules=_toy_rules(), clarification_f1=None, can_ask=False,
              customer_locale="zh", agent_locale="en")
    notes = "W3 is cheaper and the stocktake rule is an internal preference; exception recorded."

    assert apply_policy(strict, raw, RunFacts(notes=notes), **kw)["final"] == 0.0
    # Bending without going through the exception process is still a failure.
    assert apply_policy(bendable, raw, RunFacts(notes=notes), **kw)["final"] == 0.0
    ok = apply_policy(bendable, raw, RunFacts(notes=notes, exceptions=[{"decision": "approve"}]), **kw)
    assert ok["bent_rules"] == ["w3_stocktake"]
    assert abs(ok["final"] - 0.95) < 1e-9  # quality clipped at the reference, minus one bent rule


def test_events_fire_and_correction_arrives(v1_root, tmp_path):
    case = V1Case.load(v1_root / "case" / CASE)
    run_dir = tmp_path / "run"
    ws = run_dir / "workspace"
    v = build_variant(VariantSpec(CASE, difficulty="hard"), case, ws,
                      Translator(ScriptedModel(lambda m: ChatResponse(content=m[-1]["content"])), tmp_path / "c"))
    client = ScriptedModel(lambda m: ChatResponse(content="好的"))
    s = Session(v, run_dir, ws, client)
    fired = []
    for _ in range(100):
        s.tick("bash")
        fired += s.poll_events()
    kinds = [r.get("event") for r in read_transcript(run_dir) if r["kind"] == "event"]
    assert "data_correction" in kinds and "stakeholder_conflict" in kinds and "deadline_change" in kinds
    assert list((ws / "inbox").glob("*.csv")), "corrected file delivered to inbox/"
    assert s.deadline_s < v.time_budget_s


def test_client_unavailable_after_questions(v1_root, tmp_path):
    case = V1Case.load(v1_root / "case" / CASE)
    run_dir = tmp_path / "run"
    v = build_variant(VariantSpec(CASE, difficulty="hard"), case, run_dir / "workspace",
                      Translator(ScriptedModel(lambda m: ChatResponse(content=m[-1]["content"])), tmp_path / "c"))
    s = Session(v, run_dir, run_dir / "workspace", ScriptedModel(lambda m: ChatResponse(content="答复")))
    answers = [s.ask(f"问题 {i}") for i in range(7)]
    assert answers[:5] == ["答复"] * 5
    assert answers[6].startswith("Auto-reply")
