import json
from pathlib import Path

from fdebench2.cases import NativeCase
from fdebench2.llm import ChatResponse, Endpoint, ModelRegistry, ScriptedModel, ToolCall
from fdebench2.runner import AgentSpec, Bench, Settings
from fdebench2.scoring.policy_score import RunFacts, apply_policy
from fdebench2.session import Session, read_transcript
from fdebench2.transforms.language import Translator
from fdebench2.transforms.policy import Policy, load_policy
from fdebench2.transforms.variant import VariantSpec, build_variant

from conftest import NATIVE

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
    reg._cache["judge"] = ScriptedModel(lambda m: ChatResponse(content=json.dumps(
        {"covered": True, "questions": [1], "quote": answer})))
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
    assert abs(result["score"]["final"] - 1 / result["score"]["quality_cap"]) < 1e-6   # matching the reference

    run_dir = bench.run_dir(spec, AgentSpec("reference", "agent"))
    prompt = (run_dir / "prompt.md").read_text(encoding="utf-8")
    assert "현장 배치 엔지니어" in prompt            # agent instructions in Korean
    assert "리모델링" not in prompt                 # hidden requirements never shown
    kinds = [r["kind"] for r in read_transcript(run_dir)]
    assert "ask" in kinds and "finish" in kinds

    # Re-scoring under other policies needs no agent re-run.
    rescored = bench.score(run_dir, AgentSpec("reference", "agent"), extra_policies=["regulated_strict"])
    # Reference-level quality (1/1.5 of its credit), full clarification and communication: Korean questions
    # and notes for a Korean client.
    assert abs(rescored["rescored"]["regulated_strict"] - (0.6 / 1.5 + 0.2 + 0.2)) < 1e-6


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
    # An approval covers only the rule it was granted for.
    other = [{"decision": "approve", "rule_id": "some_other_rule"}]
    assert apply_policy(BEND, raw, RunFacts(notes=notes, exceptions=other), **kw)["final"] == 0.0
    granted = [{"decision": "approve", "rule_id": "premium_first"}]
    ok = apply_policy(BEND, raw, RunFacts(notes=notes, exceptions=granted), **kw)
    assert ok["bent_rules"] == ["premium_first"] and ok["penalties"] == {"bent_rules": 0.05}
    cap = ok["quality_cap"]
    assert 0 < ok["final"] and abs(ok["final"] - (min(ok["quality_raw"], cap) / cap - 0.05)) < 1e-6

    # A physical rule never bends, whatever the process.
    examples["van_capacity"](sub)
    raw = case.evaluate(sub, "en")
    granted = [{"decision": "approve", "rule_id": "van_capacity"}]
    assert apply_policy(BEND, raw, RunFacts(notes=notes, exceptions=granted), **kw)["final"] == 0.0


def _hard_session(cases_root, tmp_path, answer="答复"):
    case = NativeCase(cases_root / NATIVE)
    run_dir = tmp_path / "run"
    v = build_variant(VariantSpec(NATIVE, customer_locale="zh", engagement="messy"), case, run_dir / "workspace",
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


def test_exception_requests_are_mapped_to_one_rule(cases_root, tmp_path):
    """A request is mapped to one of the setting's rules; only a bendable rule can be approved."""
    case = NativeCase(cases_root / NATIVE)
    v = build_variant(VariantSpec(NATIVE, policy="enterprise_balanced"), case, tmp_path / "ws",
                      Translator(None, tmp_path / "c"))
    assert {"premium_first", "van_capacity"} <= {r["id"] for r in v.rules}
    replies = iter([json.dumps({"rule_id": "premium_first", "reason_given": True}),
                    json.dumps({"rule_id": "van_capacity", "reason_given": True})])
    s = Session(v, tmp_path / "run", tmp_path / "ws", ScriptedModel(lambda m: ChatResponse(content=next(replies))))
    (tmp_path / "run").mkdir(exist_ok=True)
    assert s.request_exception("premium cafés first", "saves 20 minutes of driving").startswith("[APPROVE]")
    # A physical rule is never approved, whatever the classifier says.
    assert s.request_exception("van capacity", "one extra tray fits").startswith("[DENY]")
    recs = [r for r in read_transcript(tmp_path / "run") if r["kind"] == "exception"]
    assert [(r["rule_id"], r["decision"]) for r in recs] == [("premium_first", "approve"), ("van_capacity", "deny")]


def test_clarification_judges_see_the_answers():
    """With answers, a target counts only if the conversation actually revealed it."""
    from fdebench2.cases import Target
    from fdebench2.scoring.clarify import score_clarification
    seen = []

    def judge(messages):
        seen.append(messages[-1]["content"])
        return ChatResponse(content='{"covered": true, "questions": [1], "quote": "40 trays per van"}')
    t = Target(id="cap", text="Each van carries 40 trays.", source_text="Each van carries 40 trays.")
    res = score_clarification([t], ["How many trays fit in a van?\nWhen do shifts start?"], [ScriptedModel(judge)],
                              answers=["40 trays per van; shifts start at 5:00."])
    assert "Client's answer: 40 trays per van" in seen[0] and "did the client's answer state it" in seen[0]
    assert res.recall == 1.0 and res.precision == 0.5 and res.n_questions == 2
