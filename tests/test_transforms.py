import hashlib
import json
from pathlib import Path

from fdebench2.cases import V1Case, discover
from fdebench2.llm import ChatResponse, ScriptedModel
from fdebench2.transforms.language import Translator, detect_locale, language_fidelity
from fdebench2.transforms.policy import list_policies, load_policy, render_policy_brief
from fdebench2.transforms.variant import Variant, VariantSpec, build_variant


def _tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def test_load_v1_case(v1_root):
    cases = discover(v1_root)
    case = cases["toy_001_order_allocation"]
    assert case.task_type == "Combinatorial Optimization"
    assert [t.id for t in case.targets] == ["澄清项·不能拆单", "澄清项·W3盘点"]
    assert case.submission_files == ["solution.json"]


def test_detect_locale():
    assert detect_locale("W3 창고는 지금 사용할 수 있나요? orders.csv 기준입니다") == "ko"
    assert detect_locale("W3 倉庫は今回使えますか？注文は分割できますか") == "ja"
    assert detect_locale("W3 仓库这次能用吗？订单可以拆吗") == "zh"
    assert detect_locale("Can warehouse W3 be used, and should orders be split?") == "en"
    assert detect_locale("¿Se puede usar el almacén W3 para los pedidos de la semana?") == "es"
    assert language_fidelity(["W3 창고를 써도 되나요?", "Can I split orders?"], "ko") == 0.5


def test_translator_caches(tmp_path):
    model = ScriptedModel(lambda msgs: ChatResponse(content="[ko] " + msgs[-1]["content"]))
    tr = Translator(model, tmp_path)
    assert tr.translate("你好", "ko") == "[ko] 你好"
    assert tr.translate("你好", "ko") == "[ko] 你好"
    assert len(model.calls) == 1
    assert tr.translate("你好", "zh") == "你好"  # source locale: no call


def test_policies_load_and_render():
    assert {"baseline", "enterprise_balanced", "regulated_strict", "startup_velocity"} <= set(list_policies())
    brief = render_policy_brief(load_policy("startup_velocity"))
    assert "request_exception" in brief and "about 5 questions" in brief
    assert not load_policy("baseline").agent_visible


def test_medium_variant_is_v1_equivalent(v1_root, tmp_path):
    case = V1Case.load(v1_root / "case" / "toy_001_order_allocation")
    v = build_variant(VariantSpec(case.id), case, tmp_path / "ws", Translator(None, tmp_path / "cache"))
    assert v.condition == "interact_req" and v.can_ask
    assert v.instruction == case.instruction and v.events == [] and v.noise == []
    assert v.policy_brief == ""
    assert (tmp_path / "ws" / "data" / "orders.csv").read_bytes() == (case.data_dir / "orders.csv").read_bytes()


def test_hard_variant_noise_events_and_pristine_source(v1_root, tmp_path):
    case_dir = v1_root / "case" / "toy_001_order_allocation"
    before = _tree_hash(case_dir)
    case = V1Case.load(case_dir)
    ws = tmp_path / "run" / "workspace"
    v = build_variant(VariantSpec(case.id, difficulty="hard", policy="enterprise_balanced"), case, ws,
                      Translator(ScriptedModel(lambda m: ChatResponse(content=m[-1]["content"])), tmp_path / "c"))
    ops = {n["op"] for n in v.noise}
    assert {"duplicate_rows", "stale_copy"} <= ops
    assert any(t.origin == "duplicate_rows" for t in v.targets)
    assert {e.kind for e in v.events} == {"stakeholder_conflict", "customer_unavailable", "data_correction",
                                           "customer_volunteer", "deadline_change"}
    assert (tmp_path / "run" / "held_back" / "data").is_dir()
    assert "Additional facts" in v.information
    assert v.policy_brief.startswith("# Engagement policy")
    assert _tree_hash(case_dir) == before  # v1 data untouched

    v.save(tmp_path / "saved")
    again = Variant.load(tmp_path / "saved")
    assert again.targets == v.targets and again.events == v.events and again.policy == v.policy


def test_campaign_dedups_shared_baseline(tmp_path):
    from fdebench2.runner import load_campaign
    cfg = tmp_path / "c.yaml"
    cfg.write_text("""
defaults: {cases_root: cases, models: m.yaml, seeds: [0], cases: [a, b]}
experiments:
  lang: {customer_locale: [zh, ko]}
  proto: {customer_locale: [ko], agent_locale: [en, ko]}
  pol: {policy: [baseline, startup_velocity]}
""")
    _, _, jobs, _ = load_campaign(cfg)
    # cells: zh/en, ko/en, ko/ko, startup_velocity -> 4 cells x 2 cases
    assert len(jobs) == 8
