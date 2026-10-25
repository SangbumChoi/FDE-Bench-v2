import json
from pathlib import Path

from fdebench2.cases import NativeCase, V1Case
from fdebench2.llm import ChatResponse, Endpoint, ModelRegistry, ScriptedModel, ToolCall
from fdebench2.runner import AgentSpec, Bench, Settings
from fdebench2.scoring.policy_score import RunFacts, apply_policy
from fdebench2.session import Session, read_transcript
from fdebench2.transforms.language import Translator
from fdebench2.transforms.policy import CaseRule, CaseRules, Policy, load_policy
from fdebench2.transforms.variant import VariantSpec, build_variant

from conftest import NATIVE, V1_TOY

BEND = Policy(id="bend", title="b", exceptions="justify", soft_rule_penalty=0.05,
              rule_classes={"physical": "hard", "contractual": "hard", "business_policy": "soft"})


def call(name, **args):
    return ChatResponse(content="", tool_calls=[ToolCall(id=f"c_{name}", name=name, arguments=args)])


def scripted_agent(deliverable: dict[str, str], question: str, notes: str):
    steps = [call("list_files", path="data"), call("ask_customer", questions=question),
             *[call("write_file", path=name, content=body) for name, body in deliverable.items()],
             call("write_file", path="NOTES.md", content=notes), call("finish", summary="done")]
    return ScriptedModel(steps, name="agent")


def registry(agent_model, answer="OK") -> ModelRegistry:
    reg = ModelRegistry({"agent": Endpoint("agent", "scripted", usd_per_mtok_in=1, usd_per_mtok_out=2),
                         "client": Endpoint("client", "scripted"), "judge": Endpoint("judge", "scripted")},
                        {"customer": "client", "judges": ["judge"]})
    reg._cache["agent"] = agent_model
    reg._cache["client"] = ScriptedModel(lambda m: ChatResponse(content=answer))
    reg._cache["judge"] = ScriptedModel(lambda m: ChatResponse(content='{"covered": true, "questions": [1]}'))
    return reg


def reference_files(case: NativeCase, tmp_path: Path) -> dict[str, str]:
    out = tmp_path / "ref"
    out.mkdir()
    case.module.reference_solution(case.world, out)
    return {p.name: p.read_text(encoding="utf-8") for p in out.iterdir()}


def test_native_korean_run_scores_reference_as_one(cases_root, tmp_path):
    case = NativeCase(cases_root / NATIVE)
    agent = scripted_agent(reference_files(case, tmp_path), "C11 매장도 배송해야 하나요?",
                           "가정: C11은 휴점, 냉장 상품은 V4로만 배송, 프리미엄 매장을 먼저 방문.")
    bench = Bench(Settings(cases_root=cases_root, models=tmp_path / "none.yaml", out=tmp_path / "runs"),
                  registry=registry(agent, "네, C11은 이번 주 휴점이라 배송하지 않습니다."))
    spec = VariantSpec(NATIVE, customer_locale="ko", agent_locale="ko")
    result = bench.run(spec, AgentSpec("reference", "agent"))

    assert result["agent_run"]["status"] == "finished"
    assert result["extraction"]["method"] == "direct"
    assert result["evaluator"]["validity_score"] == 1.0
    assert abs(result["evaluator"]["quality_score"] - 1.0) < 1e-9
    assert result["clarification"]["recall"] == 1.0
    assert result["score"]["final"] == 1.0

    run_dir = bench.run_dir(spec, AgentSpec("reference", "agent"))
    prompt = (run_dir / "prompt.md").read_text(encoding="utf-8")
    assert "현장 배치 엔지니어" in prompt            # agent instructions in Korean
    assert "리모델링" not in prompt                 # hidden requirements never shown
    kinds = [r["kind"] for r in read_transcript(run_dir)]
    assert "ask" in kinds and "finish" in kinds

    # Re-scoring under other policies needs no agent re-run.
    rescored = bench.score(run_dir, AgentSpec("reference", "agent"), extra_policies=["regulated_strict"])
    assert rescored["rescored"]["regulated_strict"] > 0.9   # Korean questions and notes for a Korean client


def test_native_rule_bending_needs_the_exception_process(cases_root, tmp_path):
    case = NativeCase(cases_root / NATIVE)
    examples = case.module.violating_examples(case.world)
    sub = tmp_path / "sub"
    sub.mkdir()
    examples["premium_first"](sub)
    raw = case.evaluate(sub, "en")
    assert raw["validity_score"] == 0.0 and {v["rule"] for v in raw["violations"]} == {"premium_first"}

    kw = dict(case=case, submission_dir=sub, clarification_f1=None, can_ask=False, customer_locale="en",
              agent_locale="en")
    notes = "Visited one premium café after a standard one to cut driving time; exception recorded."
    assert apply_policy(load_policy("regulated_strict"), raw, RunFacts(notes=notes), **kw)["final"] == 0.0
    assert apply_policy(BEND, raw, RunFacts(notes=notes), **kw)["final"] == 0.0
    ok = apply_policy(BEND, raw, RunFacts(notes=notes, exceptions=[{"decision": "approve"}]), **kw)
    assert ok["bent_rules"] == ["premium_first"] and ok["penalties"] == {"bent_rules": 0.05}
    assert 0 < ok["final"] and abs(ok["final"] - (min(ok["quality_raw"], 1.0) - 0.05)) < 1e-6

    # A physical rule never bends, whatever the process.
    examples["van_capacity"](sub)
    raw = case.evaluate(sub, "en")
    assert apply_policy(BEND, raw, RunFacts(notes=notes, exceptions=[{"decision": "approve"}]), **kw)["final"] == 0.0


def greedy_toy(case_dir: Path, allowed=("W1", "W2")) -> dict:
    import csv
    orders = [(r["订单号"], int(r["数量"])) for r in csv.DictReader(open(case_dir / "data" / "orders.csv", encoding="utf-8"))]
    stock, out = {"W1": 60, "W2": 80, "W3": 200}, []
    for oid, q in orders:
        for wh in allowed:
            if stock[wh] >= q:
                stock[wh] -= q
                out.append({"order_id": oid, "warehouse": wh})
                break
    return {"assignments": out}


def test_external_v1_case_runs_through_the_same_pipeline(v1_root, tmp_path):
    case_dir = v1_root / "case" / V1_TOY
    agent = scripted_agent({"solution.json": json.dumps(greedy_toy(case_dir))}, "W3 仓库这次能用吗？",
                           "假设：W3 正在盘点不可用；订单不拆单；按成本贪心分配。")
    bench = Bench(Settings(cases_root=tmp_path / "none", v1_root=v1_root, models=tmp_path / "none.yaml",
                           out=tmp_path / "runs"), registry=registry(agent, "W3 在盘点，不能用。"))
    result = bench.run(VariantSpec(f"v1-{V1_TOY}", customer_locale="zh"), AgentSpec("reference", "agent"))
    assert result["evaluator"]["validity_score"] == 1.0
    assert abs(result["evaluator"]["quality_score"] - 1.0) < 1e-9
    assert result["score"]["final"] == 1.0


def test_v1_rule_bending_uses_the_case_hook(v1_root, tmp_path):
    case = V1Case(v1_root / "case" / V1_TOY)
    case.rules = lambda: CaseRules(V1_TOY, [CaseRule("valid", "HC0_", "physical"), CaseRule("stock", "HC1_", "physical"),
                                            CaseRule("w3_stocktake", "HC2_", "business_policy")], hook="toy_hook")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "solution.json").write_text(json.dumps(greedy_toy(case.root, allowed=("W3",))))
    raw = case.evaluate(sub, "zh")
    assert raw["validity_score"] == 0.0 and raw["violations"][0]["rule"] == "w3_stocktake"
    kw = dict(case=case, submission_dir=sub, clarification_f1=None, can_ask=False, customer_locale="zh",
              agent_locale="en")
    ok = apply_policy(BEND, raw, RunFacts(notes="W3 cheaper; exception recorded in NOTES.",
                                          exceptions=[{"decision": "approve"}]), **kw)
    assert abs(ok["final"] - 0.95) < 1e-9


def _hard_session(cases_root, tmp_path, answer="答复"):
    case = NativeCase(cases_root / NATIVE)
    run_dir = tmp_path / "run"
    v = build_variant(VariantSpec(NATIVE, customer_locale="zh", difficulty="hard"), case, run_dir / "workspace",
                      Translator(None, tmp_path / "c"))
    return v, run_dir, Session(v, run_dir, run_dir / "workspace", ScriptedModel(lambda m: ChatResponse(content=answer)))


def test_events_fire_and_correction_arrives(cases_root, tmp_path):
    v, run_dir, s = _hard_session(cases_root, tmp_path)
    for _ in range(100):
        s.tick("bash")
        s.poll_events()
    kinds = [r.get("event") for r in read_transcript(run_dir) if r["kind"] == "event"]
    assert {"data_correction", "stakeholder_conflict", "deadline_change", "customer_volunteer"} <= set(kinds)
    assert list((run_dir / "workspace" / "inbox").glob("*.csv")), "corrected file delivered to inbox/"
    assert s.deadline_s < v.time_budget_s


def test_client_unavailable_after_questions(cases_root, tmp_path):
    _, _, s = _hard_session(cases_root, tmp_path)
    answers = [s.ask(f"问题 {i}") for i in range(7)]
    assert answers[:5] == ["答复"] * 5
    assert answers[6].startswith("自动回复")
