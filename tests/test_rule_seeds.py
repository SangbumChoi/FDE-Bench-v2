"""Rule seeds: a case's hidden rule parameters drawn from candidate pools (DESIGN.md, Settings).

A toy case declares the new contract (params: with a pool per tier and a shared pool with labels, rule_seeds:,
derive_params, admissible, a when-rule, a when-target and a when-block) and is checked end to end: the draw, the
texts, the validator (including the parameter-binding check), the dataset, the explainer, campaigns and the report.
"""

import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from fdebench2.cases import (MAX_REDRAWS, NativeCase, Setting, condition_holds, draw_params, fill_params,
                             filter_when)
from fdebench2.dataset import check_dataset, export_dataset
from fdebench2.explain import build_page, write_page
from fdebench2.runner import Bench, Settings, case_rule_seeds, expand, load_campaign
from fdebench2.scaffold import new_case
from fdebench2.scoring.report import difficulty_table, load_results, report, settings_table
from fdebench2.transforms.language import Translator
from fdebench2.transforms.variant import Variant, VariantSpec, build_variant
from fdebench2.validate import check_binding, check_case

REPO = Path(__file__).resolve().parents[1]
TOY = "logistics/toy_planner"

CASE_YAML = """id: toy_planner
role: Toy Planner
task_type: Toy Optimization
field: logistics
seed: 7
objective: maximize
deliverables: [answer.json]
deliverable_spec: |
  answer.json = {"quantity": <whole number of units>}
tiers:
  easy: The cap only.
  medium: The cap and the minimum order.
  hard: The cap, the minimum order and the premium week.
params:
  cap:
    values: {easy: [10, 12], medium: [14, 16], hard: [18, 20, 22]}
  price:
    values: [3, 4, 5]
    labels:
      3: {zh: 三欧元, en: three euros, ko: 삼 유로, ja: 三ユーロ, es: tres euros}
      4: {zh: 四欧元, en: four euros, ko: 사 유로, ja: 四ユーロ, es: cuatro euros}
      5: {zh: 五欧元, en: five euros, ko: 오 유로, ja: 五ユーロ, es: cinco euros}
rule_seeds: [1, 2, 3]
rules:
  - id: cap
    class: physical
    description: Order at most {{cap}} units.
  - id: min_order
    class: business_policy
    tiers: [medium, hard]
    description: Order at least 2 units.
  - id: even_lots
    class: contractual
    when: {price: [5]}
    description: In the premium week the order is an even number of units.
"""

CASE_PY = '''
import json
from pathlib import Path

HEAD = {"en": "item,stock", "es": "articulo,existencias", "ko": "품목,재고", "ja": "品目,在庫", "zh": "物品,库存"}
FILE = {"en": "stock.csv", "es": "existencias.csv", "ko": "재고.csv", "ja": "在庫.csv", "zh": "库存.csv"}


def build_world(seed):
    return {"factor": 1 + seed % 3}


def write_data(world, data_dir, lang):
    (data_dir / FILE[lang]).write_text(f"{HEAD[lang]}\\nW1,{world['factor'] * 40}\\n", encoding="utf-8")


def derive_params(params, tier):
    return {"budget": params["cap"] * params["price"]}


def admissible(params, tier):
    return params["budget"] <= 100


def _write(out_dir, quantity):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "answer.json").write_text(json.dumps({"quantity": quantity}))


def score(world, submission_dir, setting):
    path = Path(submission_dir) / "answer.json"
    if not path.is_file():
        return {"fatal": "missing answer.json"}
    q = json.loads(path.read_text())["quantity"]
    violations = []
    if q > setting["cap"]:
        violations.append(("cap", f"{q} > {setting['cap']}"))
    if setting.at_least("medium") and q < 2:
        violations.append(("min_order", f"{q} < 2"))
    if setting["price"] == 5 and q % 2:
        violations.append(("even_lots", f"{q} is odd"))
    return {"violations": violations, "objective": q * setting["price"] * world["factor"], "metrics": {"q": q}}


def reference_solution(world, out_dir, setting):
    _write(out_dir, setting["cap"])


def baseline_solution(world, out_dir, setting):
    _write(out_dir, 2)


def violating_examples(world, setting):
    out = {"cap": lambda d: _write(d, setting["cap"] + 2)}
    if setting.at_least("medium"):
        out["min_order"] = lambda d: _write(d, 0)
    if setting["price"] == 5:
        out["even_lots"] = lambda d: _write(d, 3)
    return out
'''

REQUEST = {
    "en": "Please tell us how many units we should order for the next delivery. The stock file is attached.",
    "es": "Por favor, díganos cuántas unidades debemos pedir para la próxima entrega. Le enviamos el archivo de "
          "existencias.",
    "ko": "다음 배송에 몇 개를 주문해야 할지 알려 주세요. 재고 파일을 첨부합니다.",
    "ja": "次の配送で何個注文すればよいか教えてください。在庫ファイルを添付します。",
    "zh": "请告诉我们下一次配送应该订购多少件。附上库存文件。",
}
REQUIREMENTS = {
    "en": ("# Order size\n\n- Order at most {{cap}} units.\n- One unit sells at {{price}}, so the order is worth at most "
           "{{budget}}.\n<!-- tier: medium hard -->\n- Order at least 2 units.\n<!-- /tier -->\n"
           "<!-- when: price=5 -->\n- This is the premium week: order an even number of units.\n<!-- /when -->\n"),
    "es": ("# Pedido\n\n- Pida como máximo {{cap}} unidades para el pedido.\n- Cada unidad se vende a {{price}}, así "
           "que el pedido vale como máximo {{budget}}.\n<!-- tier: medium hard -->\n- Pida al menos 2 unidades para "
           "el pedido.\n<!-- /tier -->\n<!-- when: price=5 -->\n- Es la semana premium: pida un número par de "
           "unidades.\n<!-- /when -->\n"),
    "ko": ("# 주문 수량\n\n- 최대 {{cap}}개까지 주문합니다.\n- 한 개에 {{price}}이므로 주문 금액은 최대 {{budget}}입니다.\n"
           "<!-- tier: medium hard -->\n- 최소 2개는 주문합니다.\n<!-- /tier -->\n<!-- when: price=5 -->\n"
           "- 프리미엄 주간이므로 짝수 개를 주문합니다.\n<!-- /when -->\n"),
    "ja": ("# 注文数\n\n- 最大 {{cap}} 個まで注文します。\n- 1 個 {{price}} なので、注文額は最大 {{budget}} です。\n"
           "<!-- tier: medium hard -->\n- 最低 2 個は注文します。\n<!-- /tier -->\n<!-- when: price=5 -->\n"
           "- プレミアム週なので、偶数個を注文します。\n<!-- /when -->\n"),
    "zh": ("# 订购数量\n\n- 最多订购 {{cap}} 件。\n- 每件售价{{price}}，所以订单金额最多为 {{budget}}。\n"
           "<!-- tier: medium hard -->\n- 至少订购 2 件。\n<!-- /tier -->\n<!-- when: price=5 -->\n"
           "- 本周是高级周：订购数量须为偶数。\n<!-- /when -->\n"),
}
TARGETS = {
    "en": ["Order at most {{cap}} units.", "Order at least 2 units.",
           "In the premium week the order is an even number of units."],
    "es": ["Pida como máximo {{cap}} unidades para el pedido.", "Pida al menos 2 unidades para el pedido.",
           "En la semana premium el pedido es un número par de unidades."],
    "ko": ["최대 {{cap}}개까지 주문합니다.", "최소 2개는 주문합니다.", "프리미엄 주간에는 짝수 개를 주문합니다."],
    "ja": ["最大 {{cap}} 個まで注文します。", "最低 2 個は注文します。", "プレミアム週には偶数個を注文します。"],
    "zh": ["最多订购 {{cap}} 件。", "至少订购 2 件。", "高级周的订购数量须为偶数。"],
}
EXPLAINER = {
    "es": {"role": "Planificador de prueba", "task_type": "Optimización de prueba", "deliverable_spec": "answer.json",
           "tiers": {"easy": "Solo el tope.", "medium": "El tope y el pedido mínimo.",
                     "hard": "El tope, el pedido mínimo y la semana premium."},
           "rules": {"cap": "Como máximo el tope.", "min_order": "Al menos 2 unidades.",
                     "even_lots": "Un número par en la semana premium."}},
    "ko": {"role": "테스트 플래너", "task_type": "테스트 최적화", "deliverable_spec": "answer.json",
           "tiers": {"easy": "상한만", "medium": "상한과 최소 주문", "hard": "상한, 최소 주문, 프리미엄 주간"},
           "rules": {"cap": "상한 이하", "min_order": "최소 2개", "even_lots": "프리미엄 주간에는 짝수"}},
    "ja": {"role": "テスト担当", "task_type": "テスト最適化", "deliverable_spec": "answer.json",
           "tiers": {"easy": "上限のみ", "medium": "上限と最低注文", "hard": "上限、最低注文、プレミアム週"},
           "rules": {"cap": "上限以下", "min_order": "最低 2 個", "even_lots": "プレミアム週は偶数"}},
    "zh": {"role": "测试计划员", "task_type": "测试优化", "deliverable_spec": "answer.json",
           "tiers": {"easy": "只有上限", "medium": "上限和最低订购量", "hard": "上限、最低订购量和高级周"},
           "rules": {"cap": "不超过上限", "min_order": "至少 2 件", "even_lots": "高级周为偶数"}},
}


def make_toy(tmp_path: Path, case_yaml: str = CASE_YAML, extra_py: str = "", dataset: bool = True) -> Path:
    """The toy case under tmp_path/cases/logistics/toy_planner, with its dataset and explainer when asked."""
    root = tmp_path / "cases" / TOY
    (root / "locales").mkdir(parents=True)
    shutil.copy2(REPO / "cases" / "fields.yaml", tmp_path / "cases" / "fields.yaml")
    (root / "case.yaml").write_text(case_yaml, encoding="utf-8")
    (root / "case.py").write_text(CASE_PY + extra_py, encoding="utf-8")
    for lang, request in REQUEST.items():
        d = root / "locales" / lang
        d.mkdir()
        (d / "request.md").write_text(request + "\n", encoding="utf-8")
        (d / "requirements.md").write_text(REQUIREMENTS[lang], encoding="utf-8")
        targets = [{"id": "cap", "text": TARGETS[lang][0]}, {"id": "min_order", "text": TARGETS[lang][1]},
                   {"id": "premium_week", "text": TARGETS[lang][2]}]
        if lang == "en":
            for t in targets:
                t.update(kind="missing", domain="business rule")
            targets[1]["tiers"] = ["medium", "hard"]
            targets[2]["when"] = {"price": [5]}
        (d / "targets.yaml").write_text(yaml.safe_dump(targets, allow_unicode=True, sort_keys=False), encoding="utf-8")
        if lang in EXPLAINER:
            (d / "explainer.yaml").write_text(yaml.safe_dump(EXPLAINER[lang], allow_unicode=True), encoding="utf-8")
    if dataset:
        export_dataset(root)
        write_page(root)
    return root


def make_plain(tmp_path: Path) -> str:
    """A case without settings (the toy's case.yaml without tiers, params and rule seeds): one problem at every
    difficulty. Only its case.yaml is needed to expand campaigns and resolve specs."""
    root = tmp_path / "cases" / "logistics" / "plain_planner"
    root.mkdir(parents=True)
    (root / "case.yaml").write_text(CASE_YAML.split("tiers:")[0].replace("toy_planner", "plain_planner")
                                    + "rules: []\n", encoding="utf-8")
    return "logistics/plain_planner"


def expected_draw(name: str, pool: list, seed: int, salt: int = 0):
    """The contract, spelled out: pool[Random(f"{case id}|{name}|{seed}[|{salt}]").randrange(len(pool))]."""
    key = f"{TOY}|{name}|{seed}" + (f"|{salt}" if salt else "")
    return pool[random.Random(key).randrange(len(pool))]


# The toy with the fixed rule sets A / B / C that params: and rule_seeds: replaced.
RULESETS_YAML = (CASE_YAML[:CASE_YAML.index("params:")]
                 + "rulesets: {A: {cap: 10, price: 3}, B: {cap: 12, price: 4}, C: {cap: 14, price: 5}}\n"
                 + CASE_YAML[CASE_YAML.index("rules:"):])

# A parameter that only the hard tier's scoring reads: it binds in hard and changes nothing in easy and medium.
BONUS_YAML = CASE_YAML.replace("rule_seeds:", "  bonus:\n    values: [0, 1]\nrule_seeds:")
BONUS_PY = '''

_score = score


def score(world, submission_dir, setting):
    res = _score(world, submission_dir, setting)
    if "objective" in res and setting.tier == "hard":
        res["objective"] += 10 * setting["bonus"]
    return res
'''

POOLS = {"cap": {"easy": [10, 12], "medium": [14, 16], "hard": [18, 20, 22]},
         "price": {t: [3, 4, 5] for t in ("easy", "medium", "hard")}}


# ── the draw ─────────────────────────────────────────────────────────────────

def test_draw_follows_the_contract_and_is_deterministic(tmp_path):
    root = make_toy(tmp_path, dataset=False)
    case = NativeCase(root)
    assert case.rule_seeds == (1, 2, 3) and (case.tier, case.rule_seed) == ("medium", 1)
    assert len(case.settings()) == 9 and case.at("hard", 2).world is case.world
    drawn = {}
    for tier in case.tiers:
        for seed in (1, 2, 3, 41, 977):
            c = case.at(tier, seed)
            want = {name: expected_draw(name, POOLS[name][tier], seed) for name in POOLS}
            if want["cap"] * want["price"] > 100:        # admissible() rejects it: the salted redraws decide
                want = next(w for k in range(1, MAX_REDRAWS + 1) for w in
                            [{n: expected_draw(n, POOLS[n][tier], seed, k) for n in POOLS}]
                            if w["cap"] * w["price"] <= 100)
            assert c.drawn_params == want and c.setting.params == {**want, "budget": want["cap"] * want["price"]}
            assert isinstance(c.setting, Setting) and c.setting.label == f"{tier}/s{seed}"
            assert c.setting.folder == f"{tier}_s{seed}" and c.setting["cap"] == want["cap"]
            drawn[f"{tier}/{seed}"] = c.drawn_params
    assert NativeCase(root).at("hard", 977).drawn_params == drawn["hard/977"]      # a fresh case draws the same
    # ... and so does a fresh process with another hash seed
    script = ("import json, sys; from pathlib import Path; from fdebench2.cases import NativeCase\n"
              "c = NativeCase(Path(sys.argv[1]))\n"
              "print(json.dumps({f'{t}/{s}': c.at(t, s).drawn_params for t in c.tiers for s in (1, 2, 3, 41, 977)}))")
    out = subprocess.run([sys.executable, "-c", script, str(root)], capture_output=True, text=True, check=True,
                         env={**os.environ, "PYTHONHASHSEED": "123", "PYTHONPATH": str(REPO)})
    assert json.loads(out.stdout) == drawn


def test_shared_pool_same_value_per_tier_pools_their_own(tmp_path):
    case = NativeCase(make_toy(tmp_path, dataset=False))
    for seed in range(1, 40):
        by_tier = {t: case.at(t, seed) for t in case.tiers}
        caps = {t: c.drawn_params["cap"] for t, c in by_tier.items()}
        assert all(caps[t] in POOLS["cap"][t] for t in caps)
        if all(c.drawn_params == {n: expected_draw(n, POOLS[n][c.tier], seed) for n in POOLS}
               for c in by_tier.values()):        # no redraw: the shared pool gives one value in every tier
            assert len({c.drawn_params["price"] for c in by_tier.values()}) == 1
            # pools of the same size (easy, medium) give the same position
            assert POOLS["cap"]["easy"].index(caps["easy"]) == POOLS["cap"]["medium"].index(caps["medium"])


def test_derive_and_admissible(tmp_path):
    pools = {"cap": {"hard": [22]}, "price": {"hard": [3, 4, 5]}}
    seed = next(s for s in range(1, 500) if expected_draw("price", [3, 4, 5], s) == 5)   # the first draw: 22 x 5
    derive = lambda p, tier: {"budget": p["cap"] * p["price"]}                           # noqa: E731
    drawn, full = draw_params(TOY, pools, "hard", seed, derive, lambda p, tier: p["budget"] <= 100)
    first_ok = next(k for k in range(1, MAX_REDRAWS + 1) if expected_draw("price", [3, 4, 5], seed, k) != 5)
    assert drawn == {"cap": 22, "price": expected_draw("price", [3, 4, 5], seed, first_ok)}
    assert full == {**drawn, "budget": 22 * drawn["price"]}
    with pytest.raises(ValueError, match="no admissible parameters"):
        draw_params(TOY, pools, "hard", seed, derive, lambda p, tier: False)
    with pytest.raises(ValueError, match="may only add keys"):
        draw_params(TOY, pools, "hard", seed, lambda p, tier: {"cap": 1})
    # validate-case: a candidate that admissible() rejects in every combination can never be drawn
    root = make_toy(tmp_path, dataset=False, extra_py="\n\ndef admissible(params, tier):\n"
                                                      "    return params['cap'] != 22\n")
    assert check_case(root).problems == ["params.cap: candidate 22 is never admissible in tier hard "
                                         "(admissible() rejects every combination with it)"]


# ── texts ────────────────────────────────────────────────────────────────────

def test_when_blocks_rules_and_targets(tmp_path):
    text = ("a\n<!-- when: x=1,2 -->\nb\n<!-- when: y=true -->\nc\n<!-- /when -->\n<!-- /when -->\n"
            "<!-- when: x=3 -->\nd\n<!-- /when -->\ne")
    assert filter_when(text, {"x": 2, "y": True}) == "a\nb\nc\ne"
    assert filter_when(text, {"x": 1, "y": False}) == "a\nb\ne"
    assert filter_when(text, {"x": 3, "y": True}) == "a\nd\ne"
    assert condition_holds({"x": [1, 2], "y": True}, {"x": 2, "y": True})
    assert not condition_holds({"x": [1, 2]}, {"x": 3}) and not condition_holds({"z": [1]}, {"x": 1})
    labels = {"price": {5: {"en": "five euros", "es": "cinco euros"}}}
    local = {"en": "April", "zh": "4 月", "ko": "4월", "ja": "4月", "es": "abril"}
    assert fill_params("{{price}} / {{month}}", {"price": 5, "month": local}, "es", labels) == "cinco euros / abril"

    case = NativeCase(make_toy(tmp_path, dataset=False))
    premium = next(case.at("hard", s) for s in range(1, 200) if case.at("hard", s).drawn_params["price"] == 5)
    plain = next(case.at("hard", s) for s in range(1, 200) if case.at("hard", s).drawn_params["price"] == 3)
    assert "even_lots" in {r.id for r in premium.rules().rules} and "premium_week" in {t.id for t in premium.targets("en")}
    assert "even_lots" not in {r.id for r in plain.rules().rules}
    assert "premium_week" not in {t.id for t in plain.targets("ko")}
    assert "premium week" in premium.requirements("en") and "premium week" not in plain.requirements("en")
    assert "five euros" in premium.requirements("en") and "삼 유로" in plain.requirements("ko")
    assert f"at most {plain.setting['budget']}" in plain.requirements("en") and "<!--" not in plain.requirements("ja")
    assert case.shared_target_ids() == ["cap"]                # no when, every tier: the same under any rule seed


# ── validate-case ────────────────────────────────────────────────────────────

def test_toy_case_passes_validation_on_two_worlds(tmp_path):
    report = check_case(make_toy(tmp_path), world_seeds=[2])
    assert report.problems == []
    assert not any(w.startswith("parameter ") for w in report.warnings)     # cap and price bind in every tier
    assert report.notes and report.notes[0].startswith("baseline/reference objective: easy/s1 ")


def test_binding_check_catches_a_parameter_that_changes_nothing(tmp_path):
    unused = CASE_YAML.replace("rule_seeds:", "  colour:\n    values: [red, blue]\nrule_seeds:")
    case = NativeCase(make_toy(tmp_path, unused, dataset=False))
    refs = {}
    for c in case.settings():
        refs[(c.tier, c.rule_seed)] = ref = tmp_path / "refs" / c.setting.folder
        c.write_reference(ref)
    problems, warnings = check_binding(case, refs)
    assert len(problems) == 1 and problems[0].startswith("parameter colour changes nothing: in easy/s1 (colour = ")
    assert "; in medium/s1 (colour = " in problems[0] and "; in hard/s1 (colour = " in problems[0]   # every tier
    assert warnings == []
    # through validate-case as well (cap and price bind: the reference breaks the cap or is worth another amount)
    assert any(p.startswith("parameter colour changes nothing") for p in check_case(case.root).problems)


def _refs(case: NativeCase, where: Path) -> dict:
    refs = {}
    for c in case.settings():
        refs[(c.tier, c.rule_seed)] = ref = where / c.setting.folder
        c.write_reference(ref)
    return refs


def test_binding_is_checked_in_every_tier_where_a_parameter_varies(tmp_path, monkeypatch):
    import fdebench2.validate as validate
    found = {}
    for stated, text in ((False, "<!-- tier: hard -->\n- A bonus of {{bonus}}.\n<!-- /tier -->\n"),
                         (True, "- A bonus of {{bonus}}.\n")):
        root = make_toy(tmp_path / str(stated), BONUS_YAML, extra_py=BONUS_PY, dataset=False)
        path = root / "locales" / "en" / "requirements.md"
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")
        case = NativeCase(root)
        found[stated] = (case, _refs(case, tmp_path / f"refs_{stated}"))
    # only the hard tier states the bonus: easy and medium vary it, but nothing in force there uses it
    problems, warnings = check_binding(*found[False])
    assert problems == [] and len(warnings) == 2
    assert warnings[0].startswith("parameter bonus varies in tier easy but changes nothing there, and nothing in "
                                  "force in easy uses it")
    assert warnings[1].startswith("parameter bonus varies in tier medium but changes nothing there")
    # the client states the bonus in every tier: where it changes nothing, that fails, with the numbers compared
    case, refs = found[True]
    problems, warnings = check_binding(case, refs)
    assert warnings == [] and len(problems) == 2
    assert problems[0].startswith("parameter bonus changes nothing in tier easy, where the client states it: in "
                                  "easy/s1 (bonus = ")
    obj = case.at("easy", 1).reference_objective
    assert f"{obj:.6g} -> {obj:.6g}, its own reference {obj:.6g}" in problems[0]
    # a known and open finding is a warning until the case changes
    monkeypatch.setitem(validate.OPEN_BINDING_FINDINGS, (TOY, "bonus", "easy"), (None, "the owner decides"))
    problems, warnings = check_binding(case, refs)
    assert [p.split(" in tier ")[1][:6] for p in problems] == ["medium"]
    assert len(warnings) == 1 and warnings[0].endswith("(known and open: the owner decides)")
    # ... only on the worlds it was found on: listed for world seed 2, it still fails on the public world
    monkeypatch.setitem(validate.OPEN_BINDING_FINDINGS, (TOY, "bonus", "easy"), ((2,), "the owner decides"))
    problems, warnings = check_binding(case, refs)
    assert [p.split(" in tier ")[1].split(",")[0] for p in problems] == ["easy", "medium"] and warnings == []
    other = case.with_world_seed(2)
    problems, warnings = check_binding(other, _refs(other, tmp_path / "refs_world_2"), "[seed 2] ")
    assert [p.split(" in tier ")[1][:6] for p in problems] == ["medium"]
    assert len(warnings) == 1 and warnings[0].startswith("[seed 2] parameter bonus changes nothing in tier easy")
    assert warnings[0].endswith("(known and open on world seed 2: the owner decides)")
    # the highest tier where a parameter varies must bind, whether anything there uses it or not
    root = make_toy(tmp_path / "top", BONUS_YAML, extra_py=BONUS_PY.replace('"hard"', '"easy"'), dataset=False)
    path = root / "locales" / "en" / "requirements.md"
    path.write_text(path.read_text(encoding="utf-8") + "<!-- tier: easy -->\n- A bonus of {{bonus}}.\n<!-- /tier -->\n",
                    encoding="utf-8")
    case = NativeCase(root)
    problems, warnings = check_binding(case, _refs(case, tmp_path / "refs_top"))
    assert len(problems) == 1 and problems[0].startswith("parameter bonus changes nothing in tier hard, the highest "
                                                         "tier where it varies: in hard/s1 (bonus = ")
    assert len(warnings) == 1 and warnings[0].startswith("parameter bonus varies in tier medium but changes nothing")
    # the highest tier is the highest where the pool varies, even when no candidate could be tried there: then a
    # lower tier where nothing uses the parameter is only a warning, not the highest tier's error
    root = make_toy(tmp_path / "unchecked", BONUS_YAML, dataset=False,
                    extra_py=BONUS_PY + "\n\ndef admissible(params, tier):\n"
                                        "    return tier != 'hard' or params['bonus'] == 0\n")
    case = NativeCase(root)
    problems, warnings = check_binding(case, _refs(case, tmp_path / "refs_unchecked"))
    assert problems == [] and len(warnings) == 3
    assert warnings[0] == ("parameter bonus: no other candidate is admissible in hard/s1, so whether it binds in hard "
                           "was not checked")
    assert warnings[1].startswith("parameter bonus varies in tier easy but changes nothing there")
    assert warnings[2].startswith("parameter bonus varies in tier medium but changes nothing there")


BONUS_LINE = {"en": "- A bonus of {{bonus}}.\n", "es": "- Una prima de {{bonus}}.\n", "ko": "- 보너스 {{bonus}}.\n",
              "ja": "- ボーナス {{bonus}}。\n", "zh": "- 奖金 {{bonus}}。\n"}


def test_validate_case_reports_lower_tier_findings_per_world(tmp_path, monkeypatch):
    """Through validate-case with a world-seed panel: the client states the bonus in every tier, but only hard
    scores it. A known and open finding is a warning on the worlds it lists and a problem elsewhere."""
    import fdebench2.validate as validate
    root = make_toy(tmp_path, BONUS_YAML, extra_py=BONUS_PY, dataset=False)
    for lang, line in BONUS_LINE.items():
        path = root / "locales" / lang / "requirements.md"
        path.write_text(path.read_text(encoding="utf-8") + line, encoding="utf-8")
    export_dataset(root)
    write_page(root)
    report = check_case(root, world_seeds=[2])
    assert sorted(p.split(" in tier ")[1].split(",")[0] for p in report.problems) == ["easy", "easy", "medium", "medium"]
    assert sum(p.startswith("[seed 2] parameter bonus changes nothing") for p in report.problems) == 2
    monkeypatch.setitem(validate.OPEN_BINDING_FINDINGS, (TOY, "bonus", "easy"), (None, "every world"))
    monkeypatch.setitem(validate.OPEN_BINDING_FINDINGS, (TOY, "bonus", "medium"), ((2,), "world 2 only"))
    report = check_case(root, world_seeds=[2])
    assert report.problems == [p for p in report.problems if p.startswith("parameter bonus changes nothing in tier "
                                                                          "medium, where the client states it")]
    assert len(report.problems) == 1                     # the public world is not listed for medium
    known = [w for w in report.warnings if "(known and open" in w]
    assert len(known) == 3
    assert known[0].startswith("parameter bonus changes nothing in tier easy") and known[0].endswith("(known and "
                                                                                                     "open: every world)")
    assert known[1].startswith("[seed 2] parameter bonus changes nothing in tier easy")
    assert known[2].startswith("[seed 2] parameter bonus changes nothing in tier medium")
    assert known[2].endswith("(known and open on world seed 2: world 2 only)")


def test_contract_slips_are_reported(tmp_path):
    bad = (CASE_YAML.replace("rule_seeds: [1, 2, 3]", "rule_seeds: [1, 1]")
           .replace("      5: {zh: 五欧元, en: five euros, ko: 오 유로, ja: 五ユーロ, es: cinco euros}\n", "")
           .replace("when: {price: [5]}", "when: {price: [6]}"))
    problems = check_case(make_toy(tmp_path, bad, dataset=False)).problems
    assert "case.yaml: rule_seeds: must be distinct ints, got [1, 1]" in problems
    assert "case.yaml params.price.labels: no wording of candidate 5" in problems
    root = make_toy(tmp_path / "b", CASE_YAML.replace("when: {price: [5]}", "when: {price: [6]}"), dataset=False)
    path = root / "locales" / "ja" / "requirements.md"
    path.write_text(path.read_text(encoding="utf-8").replace("<!-- when: price=5 -->", "<!-- when: price=4 -->"),
                    encoding="utf-8")
    problems = check_case(root).problems
    assert "rule even_lots: when price = 6, which is never a candidate of price" in problems
    assert ("ja/requirements.md: setting markers differ from en at block 2: 'when: price=4', en has 'when: price=5'"
            in problems)


def test_panel_that_shows_one_candidate_is_warned(tmp_path):
    one = next(s for s in range(1, 300) if all(expected_draw("price", [3, 4, 5], x) == expected_draw("price", [3, 4, 5], s)
                                              for x in (s, s + 1000)))
    case_yaml = CASE_YAML.replace("rule_seeds: [1, 2, 3]", f"rule_seeds: [{one}, {one + 1000}]")
    from fdebench2.validate import check_params
    _, warnings = check_params(NativeCase(make_toy(tmp_path, case_yaml, dataset=False)))
    assert any(w.startswith("parameter price: every public rule seed draws the same value in easy") for w in warnings)


# ── dataset, explainer, variants, campaigns and the report ──────────────────

def test_dataset_folders_and_setting_json(tmp_path):
    root = make_toy(tmp_path)
    gt = root / "dataset" / "gt"
    assert sorted(p.name for p in gt.iterdir()) == sorted(f"{t}_s{s}" for t in ("easy", "medium", "hard")
                                                          for s in (1, 2, 3))
    case = NativeCase(root).at("hard", 2)
    doc = json.loads((gt / "hard_s2" / "setting.json").read_text())
    assert doc == {"tier": "hard", "rule_seed": 2, "params": case.drawn_params,
                   "derived": {"budget": case.setting["budget"]}}
    assert list(doc["params"]) == ["cap", "price"] and check_dataset(root) == []


def test_explainer_shows_candidates_panel_and_seed_selector(tmp_path):
    root = make_toy(tmp_path)
    en, ko = build_page(root, "en"), build_page(root, "ko")
    case = NativeCase(root)
    assert "Parameter candidates" in en and "Public rule seeds" in en and "3 tiers × 3 public rule seeds" in en
    assert "<code>5</code> five euros" in en and "<code>budget</code>" in en
    assert json.dumps(case.at("easy", 2).drawn_params).replace('"', "&quot;") in en
    assert '<option value="easy_s2">easy / Rule seed 2</option>' in en
    assert "only when price = 5" in en and "규칙 시드" in ko and "<code>5</code> 오 유로" in ko
    assert "rule set" not in en.replace("rule seed", "").lower().replace("rule sets", "")


def test_variant_carries_rule_seed_and_params(tmp_path):
    root = make_toy(tmp_path, dataset=False)
    case = NativeCase(root)
    spec = VariantSpec(TOY, difficulty="hard", rule_seed=4242)            # a private seed
    v = build_variant(spec, case, tmp_path / "ws", Translator(None, tmp_path / "cache"))
    assert (v.case_tier, v.rule_seed, v.params) == ("hard", 4242, case.at("hard", 4242).drawn_params)
    assert "__r-4242__" in spec.key() and "__r-" not in VariantSpec("x/y").key()
    v.save(tmp_path / "saved")
    assert Variant.load(tmp_path / "saved").params == v.params
    old = json.loads((tmp_path / "saved" / "variant.json").read_text())       # saved before rule seeds
    old["ruleset"] = "C"
    del old["rule_seed"], old["params"], old["spec"]["rule_seed"]
    old["spec"]["ruleset"] = "C"
    (tmp_path / "saved" / "variant.json").write_text(json.dumps(old))
    with pytest.raises(ValueError, match="set up with rule set C, before rule seeds replaced rule sets; run it again"):
        Variant.load(tmp_path / "saved")
    del old["spec"]["ruleset"]                          # the rule set named only next to the spec: refused the same
    (tmp_path / "saved" / "variant.json").write_text(json.dumps(old))
    with pytest.raises(ValueError, match="set up with rule set C, before rule seeds replaced rule sets; run it again"):
        Variant.load(tmp_path / "saved")


def test_campaign_runs_the_public_panel_or_private_seeds(tmp_path):
    make_toy(tmp_path, dataset=False)
    plain = make_plain(tmp_path)
    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"""
defaults: {{models: m.yaml, cases: [{TOY}, {plain}]}}
agents: [{{harness: reference, model: a}}]
experiments:
  public: {{difficulty: [easy, hard]}}
  private: {{rule_seeds: [101, 102]}}
""")
    settings, agents, jobs, _ = load_campaign(cfg)
    bench = Bench(Settings(cases_root=tmp_path / "cases", models=tmp_path / "none.yaml", out=tmp_path / "runs"))
    keys = sorted(spec.key() for _, spec in expand(bench, agents, jobs))
    toy = [k for k in keys if k.startswith(TOY)]
    assert len(toy) == 2 * 3 + 2 and {k.split("__r-")[1].split("__")[0] for k in toy} == {"1", "2", "3", "101", "102"}
    assert [k for k in keys if k.startswith(plain)] == [k for k in keys if k.startswith(plain) and "__r-" not in k]
    assert len([k for k in keys if k.startswith(plain)]) == 2 + 1                   # once per difficulty
    toy = NativeCase(tmp_path / "cases" / TOY)
    assert case_rule_seeds(toy, None) == [1, 2, 3] and case_rule_seeds(toy, 7) == [7]
    cfg.write_text("defaults: {models: m.yaml}\nexperiments:\n  old: {ruleset: [A]}\n")
    with pytest.raises(ValueError, match="ruleset is no longer an axis: rule seeds replaced the rule sets"):
        load_campaign(cfg)


def _result(case, tier, seed, final, valid, noise=0, params=None):
    return {"agent": {"harness": "reference", "model": "m"}, "status": "ok" if valid else "invalid",
            "spec": {"case_id": case, "difficulty": tier, "rule_seed": seed, "noise_seed": noise, "trial": 0},
            "rule_seed": seed, "params": params if params is not None else {"cap": seed},
            "score": {"final": final, "gates": {"validity": valid}}}


def test_report_averages_over_rule_seeds_then_cases():
    results = [_result("a/x", "easy", 1, 1.0, True), _result("a/x", "easy", 1, 0.0, False, noise=1),
               _result("a/x", "easy", 2, 0.9, True), _result("a/x", "easy", 2, 0.7, True, noise=1),
               _result("b/y", "easy", 5, 0.2, True), _result("b/y", "easy", 5, 0.4, True, noise=1)]
    table = difficulty_table(results)
    # a/x: seed 1 mean 0.5, seed 2 mean 0.8 -> 0.65; b/y: 0.3 -> case mean 0.475
    # all valid per (case, noise seed): a/x noise 0 yes, a/x noise 1 no (seed 1 failed), b/y 0 and 1 yes -> 0.75
    assert "| reference--m | 0.475 [0.30–0.65] | 0.75 | – | – | – | – |" in table
    rows = settings_table(results).splitlines()
    assert rows[2] == "| agent | case | tier | rule seed | params | runs | final | valid |"
    assert '| reference--m | a/x | easy | 1 | `{"cap": 1}` | 2 | 0.500 | 1/2 |' in rows
    assert '| reference--m | b/y | easy | 5 | `{"cap": 5}` | 2 | 0.300 | 2/2 |' in rows
    assert settings_table([{**results[0], "rule_seed": None, "spec": {"case_id": "c/z", "difficulty": "easy"}}]) is None


def test_report_refuses_a_result_scored_under_a_rule_set(tmp_path):
    run = tmp_path / "runs" / "reference--m" / "a__x"
    run.mkdir(parents=True)
    result = _result("a/x", "easy", 1, 1.0, True)
    (run / "result.json").write_text(json.dumps(result))
    assert load_results(tmp_path / "runs") == [result]
    del result["rule_seed"], result["spec"]["rule_seed"]
    result["spec"]["ruleset"] = "B"                     # scored before rule seeds replaced rule sets
    (run / "result.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="scored under rule set B, before rule seeds replaced rule sets; run it "
                                         "again or report it apart"):
        report(tmp_path / "runs")


def test_rule_sets_are_refused_with_the_rule_seed_form(tmp_path):
    root = make_toy(tmp_path / "a", RULESETS_YAML, dataset=False)
    with pytest.raises(ValueError, match=r"declare params: \(each parameter's candidate pool\) and rule_seeds:"):
        NativeCase(root)
    problems = check_case(root).problems
    assert len(problems) == 1 and problems[0].startswith("case.yaml: logistics/toy_planner: case.yaml declares "
                                                         "rulesets: (fixed rule sets A / B / C)")
    # what is left of rule sets in a case that draws its parameters: each names what to use instead
    leftovers = (CASE_YAML.replace("rule_seeds: [1, 2, 3]", "rule_seeds: [1, 2, 3]\nparam_labels: {cap: {}}")
                 .replace("    when: {price: [5]}\n", "    when: {price: [5]}\n    rulesets: [C]\n"))
    root = make_toy(tmp_path / "b", leftovers, dataset=False)
    path = root / "locales" / "en" / "requirements.md"
    path.write_text(path.read_text(encoding="utf-8") + "<!-- ruleset: A -->\n- Only in A.\n<!-- /ruleset -->\n",
                    encoding="utf-8")
    _edit_targets(root, "en", lambda ts: ts[0].update(rulesets=["A", "B"]))
    problems = check_case(root).problems
    assert any(p.startswith("case.yaml: param_labels: belonged to the rule sets that rule seeds replaced") and
               p.endswith("params.<name>.labels") for p in problems)
    assert any(p.startswith("rule even_lots: rulesets: ['C'] is no longer read") and "when: {name: [values]}" in p
               for p in problems)
    assert any(p.startswith("en/targets.yaml cap: rulesets: ['A', 'B'] is no longer read") for p in problems)
    assert any(p.startswith("en/requirements.md: <!-- ruleset: ... --> blocks are no longer read") and
               p.endswith("use <!-- when: name=v1,v2 --> ... <!-- /when -->") for p in problems)


def test_one_parameter_variation_has_its_own_label(tmp_path):
    case = NativeCase(make_toy(tmp_path, dataset=False)).at("hard", 1)
    other = 5 if case.drawn_params["price"] != 5 else 3
    alt = case.with_params(price=other)
    assert alt.drawn_params == {**case.drawn_params, "price": other} and alt.rule_seed == case.rule_seed
    assert alt.setting.params["budget"] == case.drawn_params["cap"] * other           # derived again
    assert alt.setting.label == f"hard/s1[price={other}]" and alt.setting != case.setting
    assert case.at("hard", 1) is case and alt.at("hard", 1) is not alt                # variations are not cached
    assert alt.with_world_seed(9).drawn_params == alt.drawn_params


def test_scaffold_writes_the_new_contract(tmp_path):
    shutil.copy2(REPO / "cases" / "fields.yaml", tmp_path / "fields.yaml")
    root = new_case("retail/shelf_planner", tmp_path)
    meta = yaml.safe_load((root / "case.yaml").read_text())
    assert "rulesets" not in meta and meta["params"] == {"example_param": {"values": [1, 2, 3]}}
    assert meta["rule_seeds"] == [1, 2, 3]
    case = NativeCase(root)
    assert case.rule_seeds == (1, 2, 3) and case.at("easy", 9).setting["example_param"] in (1, 2, 3)
    assert "<!-- when: example_param=2,3 -->" in (root / "locales" / "ko" / "requirements.md").read_text()


# ── review follow-ups: independence, texts the validator reads, draws beyond the panel, runs and the report ──

def test_parameters_are_drawn_independently(tmp_path):
    """Adding a parameter or changing another parameter's pool leaves a parameter's draw as it was."""
    base = NativeCase(make_toy(tmp_path / "a", dataset=False))
    more = CASE_YAML.replace("rule_seeds:", "  colour:\n    values: [red, blue, green]\nrule_seeds:")
    other = NativeCase(make_toy(tmp_path / "b", more.replace("easy: [10, 12]", "easy: [10, 12, 13]"), dataset=False))
    for tier in ("medium", "hard"):
        for seed in (1, 2, 3, 41, 977):
            a, b = base.at(tier, seed).drawn_params, other.at(tier, seed).drawn_params
            assert {k: b[k] for k in a} == a and b["colour"] in ("red", "blue", "green")


def _edit_targets(root: Path, lang: str, edit) -> None:
    path = root / "locales" / lang / "targets.yaml"
    targets = yaml.safe_load(path.read_text(encoding="utf-8"))
    edit(targets)
    path.write_text(yaml.safe_dump(targets, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_markers_in_target_texts_and_rule_descriptions_are_checked(tmp_path):
    root = make_toy(tmp_path / "a", CASE_YAML.replace(
        "description: Order at most {{cap}} units.",
        "description: 'Order at most {{cap}} units.<!-- when: zzz=1 --> More.<!-- /when -->'"), dataset=False)
    for lang in REQUEST:            # the same marker in every locale, so only the name is wrong
        _edit_targets(root, lang, lambda ts: ts[0].update(text=ts[0]["text"] + "<!-- when: nope=1 --> x<!-- /when -->"))
    _edit_targets(root, "ko", lambda ts: ts[1].update(text=ts[1]["text"] + "<!-- /when -->"))
    problems = check_case(root).problems
    assert "rule cap description: when names 'zzz', which is not a parameter" in problems
    assert "en/targets.yaml cap: when names 'nope', which is not a parameter" in problems
    assert "ko/targets.yaml min_order: unbalanced when markers" in problems


def test_derive_params_must_work_on_every_combination_a_private_seed_can_draw(tmp_path):
    derive = ("\n\ndef derive_params(params, tier):\n    if params['cap'] == 22:\n        raise ValueError('no budget')\n"
              "    return {'budget': params['cap'] * params['price']}\n")
    root = make_toy(tmp_path, extra_py=derive, dataset=False)
    case = NativeCase(root)
    assert 22 not in {case.at("hard", s).drawn_params["cap"] for s in case.rule_seeds}     # the panel never draws it
    assert any(p.startswith("[hard] derive_params fails on {'cap': 22, 'price': ") for p in check_case(root).problems)


def test_a_case_whose_parameters_have_one_candidate_is_warned(tmp_path):
    from fdebench2.validate import check_params
    one = (CASE_YAML.replace("values: {easy: [10, 12], medium: [14, 16], hard: [18, 20, 22]}", "values: [10]")
           .replace("values: [3, 4, 5]", "values: [3]"))
    _, warnings = check_params(NativeCase(make_toy(tmp_path, one, dataset=False)))
    assert any(w.startswith("no parameter has two or more candidates") for w in warnings)


def test_a_run_names_its_rule_seed_and_rescoring_checks_the_draw(tmp_path):
    from fdebench2.runner import AgentSpec
    root = make_toy(tmp_path, dataset=False)
    plain = make_plain(tmp_path)

    def bench():
        return Bench(Settings(cases_root=tmp_path / "cases", models=tmp_path / "none.yaml", out=tmp_path / "runs"))

    spec = bench().resolve(VariantSpec(TOY, difficulty="hard"))
    assert spec.rule_seed == 1 and "__r-1__" in spec.key()
    assert bench().resolve(VariantSpec(plain, rule_seed=7)).rule_seed is None
    assert bench().resolve(VariantSpec(TOY, rule_seed=4242)).rule_seed == 4242
    run_dir = tmp_path / "run"
    variant = bench().prepare(VariantSpec(TOY, difficulty="hard"), run_dir)
    assert variant.spec.rule_seed == 1 and variant.params == NativeCase(root).at("hard", 1).drawn_params
    # the case's candidates change after the run: re-scoring it would use parameters the client never stated
    (root / "case.yaml").write_text(CASE_YAML.replace("hard: [18, 20, 22]", "hard: [30, 31, 32]"), encoding="utf-8")
    with pytest.raises(ValueError, match="run it again instead of re-scoring it"):
        bench().score(run_dir, AgentSpec(harness="reference", model="m"))


def test_other_tables_weigh_rule_seeds_like_the_difficulty_table(tmp_path):
    from fdebench2.scoring.report import report
    rows = [_result("a/x", "medium", 1, 1.0, True), _result("a/x", "medium", 1, 1.0, True, noise=1),
            _result("a/x", "medium", 2, 0.0, False)]          # seed 2 has one scored run, seed 1 two
    for i, r in enumerate(rows):
        r["score"]["components"] = {"quality": r["score"]["final"]}
        r["spec"].update(policy="baseline", customer_locale="en")
        (tmp_path / "out" / "m" / str(i)).mkdir(parents=True)
        (tmp_path / "out" / "m" / str(i) / "result.json").write_text(json.dumps(r), encoding="utf-8")
    text = report(tmp_path / "out")
    # one difficulty, but a case with settings: the per-tier table is there, and both tables give 0.5 (the mean of
    # seed 1's 1.0 and seed 2's 0.0), not the mean over the three runs (0.667); all valid: noise seed 0 failed
    # under rule seed 2, noise seed 1 ran only under rule seed 1
    assert "| reference--m | – | – | 0.500 [0.50–0.50] | 0.50 | – | – |" in text
    policy_row = next(line for line in text.splitlines() if line.startswith("| reference--m | baseline |"))
    assert "| 0.500 [0.50–0.50] | 0.500 |" in policy_row
