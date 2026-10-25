import hashlib
from pathlib import Path

from fdebench2 import i18n
from fdebench2.cases import NativeCase, V1Case, discover
from fdebench2.llm import ChatResponse, ScriptedModel
from fdebench2.transforms import events as ev_mod
from fdebench2.transforms import noise as noise_mod
from fdebench2.transforms.events import msg
from fdebench2.transforms.language import Translator, detect_locale, language_fidelity
from fdebench2.transforms.policy import list_policies, load_policy, policy_brief_msgs
from fdebench2.transforms.variant import Variant, VariantSpec, build_variant

from conftest import NATIVE, V1_TOY

NO_TRANSLATOR = None


def _tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def _offline(tmp_path) -> Translator:
    """A translator that fails loudly: native cases must never need run-time translation."""
    return Translator(NO_TRANSLATOR, tmp_path / "no-cache")


def test_discover_native_and_v1(cases_root, v1_root):
    found = discover(cases_root, v1_root)
    assert isinstance(found[NATIVE], NativeCase)
    assert set(found[NATIVE].locales()) == {"zh", "en", "ko", "ja", "es"}
    toy = found[f"v1-{V1_TOY}"]
    assert isinstance(toy, V1Case) and toy.locales() == ("zh",)
    assert [t.id for t in toy.targets("zh")] == ["澄清项·不能拆单", "澄清项·W3盘点"]


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
    assert tr.translate("你好", "ko", src="zh") == "[ko] 你好"
    assert tr.translate("你好", "ko", src="zh") == "[ko] 你好"
    assert len(model.calls) == 1


def test_message_catalog_covers_every_generated_message():
    templates = [ev_mod.STAKEHOLDER_MESSAGE, ev_mod.STAKEHOLDER_TRUTH, ev_mod.UNAVAILABLE_MESSAGE,
                 ev_mod.CORRECTION_MESSAGE, ev_mod.VOLUNTEER_MESSAGE, ev_mod.DEADLINE_MESSAGE,
                 *ev_mod.STAKEHOLDER_DEMANDS, *(d for _, d in ev_mod._NAMES),
                 noise_mod.DUP_FACT, noise_mod.DUP_TARGET, noise_mod.STALE_FACT, noise_mod.STALE_TARGET,
                 noise_mod.ENCODING_FACT, "Additional facts (known to the client)"]
    messages = [msg(t) for t in templates]
    for name in list_policies():
        messages += policy_brief_msgs(load_policy(name))
    for lang in ("zh", "ko", "ja", "es"):
        assert i18n.missing(lang, messages) == [], lang
    out = i18n.render(msg(ev_mod.DEADLINE_MESSAGE, minutes=30), "ko")
    assert "30분" in out


def test_policies_load():
    assert {"baseline", "enterprise_balanced", "regulated_strict", "startup_velocity"} <= set(list_policies())
    assert not load_policy("baseline").agent_visible


def test_native_variant_in_korean_needs_no_translation(cases_root, tmp_path):
    case = NativeCase(cases_root / NATIVE)
    before = _tree_hash(case.root)
    v = build_variant(VariantSpec(NATIVE, customer_locale="ko", agent_locale="ja", policy="startup_velocity"),
                      case, tmp_path / "ws", _offline(tmp_path))
    assert v.instruction == case.request("ko")
    assert [t.id for t in v.targets] == [t.id for t in case.targets("en")]
    assert (tmp_path / "ws" / "data" / "매장목록.csv").is_file()
    assert v.policy_brief.startswith("# 業務遂行ポリシー")  # agent locale ja
    assert _tree_hash(case.root) == before


def test_hard_native_variant(cases_root, tmp_path):
    case = NativeCase(cases_root / NATIVE)
    v = build_variant(VariantSpec(NATIVE, customer_locale="es", difficulty="hard", policy="enterprise_balanced"),
                      case, tmp_path / "run" / "workspace", _offline(tmp_path))
    assert {"duplicate_rows", "stale_copy", "legacy_encoding"} <= {n["op"] for n in v.noise}
    assert any(t.origin == "duplicate_rows" and "duplicadas" in t.text for t in v.targets)
    assert {e.kind for e in v.events} == {"stakeholder_conflict", "customer_unavailable", "data_correction",
                                           "customer_volunteer", "deadline_change"}
    assert all(e.message and "{" not in e.message for e in v.events)
    assert "Hechos adicionales" in v.information
    v.save(tmp_path / "saved")
    again = Variant.load(tmp_path / "saved")
    assert again.targets == v.targets and again.events == v.events and again.policy == v.policy


def test_v1_case_other_locale_uses_translator(v1_root, tmp_path):
    case = V1Case(v1_root / "case" / V1_TOY)
    tr = Translator(ScriptedModel(lambda m: ChatResponse(content="[en] " + m[-1]["content"])), tmp_path / "c")
    v = build_variant(VariantSpec(case.id, customer_locale="en"), case, tmp_path / "ws", tr)
    assert v.instruction.startswith("[en] ")
    assert v.targets[0].source_text.startswith("每个订单")


def test_campaign_dedups_shared_baseline(tmp_path):
    from fdebench2.runner import load_campaign
    cfg = tmp_path / "c.yaml"
    cfg.write_text("""
defaults: {models: m.yaml, seeds: [0], cases: [a, b]}
experiments:
  lang: {customer_locale: [en, ko]}
  proto: {customer_locale: [ko], agent_locale: [en, ko]}
  pol: {policy: [baseline, startup_velocity]}
""")
    _, _, jobs, _ = load_campaign(cfg)
    # cells: en/en, ko/en, ko/ko, startup_velocity -> 4 cells x 2 cases
    assert len(jobs) == 8
