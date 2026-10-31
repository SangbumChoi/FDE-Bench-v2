"""The quality scale (baseline 0, reference 1, capped credit) and the policy scoring around it."""

import json
from pathlib import Path

import pytest

from fdebench2.cases import RATIO_CAP, NativeCase, quality_fields
from fdebench2.dataset import check_dataset, export_dataset
from fdebench2.scoring.policy_score import RunFacts, apply_policy
from fdebench2.transforms.policy import Policy, policy_brief_msgs

CASE_PY = '''
import json

REF, BASE = {ref!r}, {base!r}


def build_world(seed):
    return {{"seed": seed}}


def write_data(world, data_dir, lang):
    (data_dir / "data.txt").write_text(lang)


def _write(out_dir, objective, broken=()):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "answer.json").write_text(json.dumps({{"objective": objective, "break": list(broken)}}))


def reference_solution(world, out_dir, setting=None):
    _write(out_dir, REF * (setting["scale"] if setting else 1))


def score(world, submission_dir, setting=None):
    path = submission_dir / "answer.json"
    if not path.is_file():
        return {{"fatal": "missing answer.json"}}
    doc = json.loads(path.read_text())
    return {{"violations": [(r, "broken") for r in doc["break"]], "objective": doc["objective"], "metrics": {{}}}}
'''
BASELINE_PY = '''

def baseline_solution(world, out_dir, setting=None):
    _write(out_dir, BASE * (setting["scale"] if setting else 1))
'''
SETTINGS_YAML = """tiers: {easy: e, medium: m, hard: h}
params: {scale: {values: [1, 2, 3]}}
rule_seeds: [1, 2, 3]
"""


def make_case(tmp_path: Path, objective: str, ref: float, base=None, cap=None, settings=False) -> NativeCase:
    """A one-number case: the deliverable states its objective and which rules it breaks."""
    root = tmp_path / f"case_{len(list(tmp_path.glob('case_*')))}" / "toy" / "toy_role"
    root.mkdir(parents=True)
    src = CASE_PY.format(ref=ref, base=base) + (BASELINE_PY if base is not None else "")
    (root / "case.py").write_text(src)
    meta = (f"id: toy_role\nfield: toy\nrole: Toy\nobjective: {objective}\nseed: 1\n"
            "deliverables: [answer.json]\nrules:\n"
            "  - {id: habit, class: business_policy}\n  - {id: habit2, class: business_policy}\n")
    meta += (f"quality_cap: {cap}\n" if cap is not None else "") + (SETTINGS_YAML if settings else "")
    (root / "case.yaml").write_text(meta)
    return NativeCase(root)


def submit(tmp_path: Path, objective: float, broken=()) -> Path:
    sub = tmp_path / f"sub_{len(list(tmp_path.glob('sub_*')))}"
    sub.mkdir()
    (sub / "answer.json").write_text(json.dumps({"objective": objective, "break": list(broken)}))
    return sub


def quality(case, tmp_path, objective):
    res = case.evaluate(submit(tmp_path, objective), "en")
    return res["quality_score"], res["quality_ratio"], res["quality_anchor"]


def test_normalized_quality_maximize(tmp_path):
    case = make_case(tmp_path, "maximize", ref=80.0, base=40.0)
    res = case.evaluate(submit(tmp_path, 100.0), "en")
    assert res["validity_score"] == 1.0 and res["quality_anchor"] == "baseline"
    assert (res["objective"], res["reference_objective"], res["baseline_objective"]) == (100.0, 80.0, 40.0)
    assert res["quality_score"] == 1.5 and res["quality_ratio"] == 1.25     # not clipped at the reference
    assert quality(case, tmp_path, 80.0)[0] == 1.0 and quality(case, tmp_path, 40.0)[0] == 0.0
    assert quality(case, tmp_path, 20.0)[:2] == (0.0, 0.25)                    # worse than the baseline: floored


def test_normalized_quality_minimize(tmp_path):
    case = make_case(tmp_path, "minimize", ref=80.0, base=120.0)
    assert quality(case, tmp_path, 60.0) == (1.5, round(80 / 60, 8), "baseline")
    assert quality(case, tmp_path, 80.0)[0] == 1.0 and quality(case, tmp_path, 140.0)[0] == 0.0


def test_a_perfect_zero_cost_submission_is_not_scored_zero(tmp_path):
    no_base = make_case(tmp_path, "minimize", ref=80.0)
    assert quality(no_base, tmp_path, 0.0) == (RATIO_CAP, RATIO_CAP, "ratio")
    assert quality(make_case(tmp_path, "minimize", ref=80.0, base=120.0), tmp_path, 0.0)[:2] == (3.0, RATIO_CAP)
    assert quality_fields(0.0, 0.0, None, maximize=False)["quality_score"] == 1.0     # matches a zero reference
    assert quality_fields(5.0, 0.0, None, maximize=False)["quality_score"] == 0.0


def test_a_non_finite_objective_is_never_valid(tmp_path):
    for objective in ("minimize", "maximize"):       # NaN fails every comparison: it must not earn credit
        case = make_case(tmp_path, objective, ref=80.0)
        sub = submit(tmp_path, float("nan"))
        res = case.evaluate(sub, "en")
        assert res["validity_score"] == 0.0 and "not a finite number" in res["error_info"]["fatal"]
        assert _score(case, sub, Policy(id="p", title="p"))["final"] == 0.0
    case = make_case(tmp_path, "minimize", ref=80.0)
    case.module.REF = float("nan")
    with pytest.raises(AssertionError, match="reference solution is not valid"):
        case.reference_objective


def test_degenerate_baseline_falls_back_to_the_ratio(tmp_path):
    for base in (80.0, 70.0):            # as good as, or better than, the reference
        case = make_case(tmp_path, "minimize", ref=80.0, base=base)
        assert quality(case, tmp_path, 100.0) == (0.8, 0.8, "ratio")
    case = make_case(tmp_path, "maximize", ref=80.0)
    assert case.baseline_objective is None and quality(case, tmp_path, 100.0) == (1.25, 1.25, "ratio")


def test_baseline_follows_the_setting_and_must_be_valid(tmp_path):
    case = make_case(tmp_path, "maximize", ref=80.0, base=40.0, settings=True)
    seed_of = {}                                    # the first rule seed that draws each scale
    for seed in range(1, 100):
        seed_of.setdefault(case.at("hard", seed).setting["scale"], seed)
    assert {k: case.at("hard", r).baseline_objective for k, r in seed_of.items()} == {1: 40.0, 2: 80.0, 3: 120.0}
    # a shared pool draws the same scale in every tier: reference 160, baseline 80
    assert case.at("easy", seed_of[2]).evaluate(submit(tmp_path, 200.0), "en")["quality_score"] == 1.5
    broken = make_case(tmp_path, "maximize", ref=80.0, base=40.0)
    broken.module.baseline_solution = lambda world, out_dir: broken.module._write(out_dir, 40.0, ["habit"])
    with pytest.raises(AssertionError, match="baseline solution is not valid"):
        broken.baseline_objective


def _score(case, sub, policy, **facts):
    facts.setdefault("notes", "Assumptions are written down here.")
    return apply_policy(policy, case.evaluate(sub, "en"), RunFacts(**facts), case=case, submission_dir=sub,
                        clarification_f1=None, can_ask=False, customer_locale="en", agent_locale="en")


def test_quality_credit_is_capped_at_the_policy_or_case_cap(tmp_path):
    policy = Policy(id="p", title="p")
    case = make_case(tmp_path, "maximize", ref=80.0, base=40.0)
    for obj, credit in ((70.0, 0.5), (100.0, 1.0), (200.0, 1.0)):
        out = _score(case, submit(tmp_path, obj), policy)
        assert abs(out["components"]["quality"] - credit) < 1e-9 and out["quality_cap"] == 1.5
    out = _score(case, submit(tmp_path, 200.0), policy)
    assert (out["quality_raw"], out["quality_ratio"], out["quality_anchor"]) == (4.0, 2.5, "baseline")
    capped = make_case(tmp_path, "maximize", ref=80.0, base=40.0, cap=2.0)
    out = _score(capped, submit(tmp_path, 100.0), policy)
    assert out["quality_cap"] == 2.0 and out["components"]["quality"] == 0.75
    out = _score(case, submit(tmp_path, 100.0, ["habit"]), policy)
    assert out["final"] == 0.0 and out["components"]["quality"] == 0.0 and out["quality_anchor"] is None
    for bad in (0, 12):                  # full credit must be reachable: 0 < cap <= RATIO_CAP
        with pytest.raises(ValueError, match="quality_cap"):
            make_case(tmp_path, "maximize", ref=80.0, cap=bad).quality_cap
    with pytest.raises(ValueError, match="quality_cap"):
        Policy(id="p", title="p", quality_cap=0)


def test_the_first_exception_decision_on_a_rule_binds(tmp_path):
    bend = Policy(id="b", title="b", exceptions="escalate", soft_rule_penalty=0.1,
                  rule_classes={"physical": "hard", "contractual": "hard", "business_policy": "soft"})
    case = make_case(tmp_path, "maximize", ref=80.0, base=40.0)
    sub = submit(tmp_path, 100.0, ["habit"])
    deny = {"rule_id": "habit", "decision": "deny", "reason_given": False}
    approve = {"rule_id": "habit", "decision": "approve", "reason_given": True}
    assert _score(case, sub, bend, exceptions=[deny, approve])["final"] == 0.0   # asking again does not overturn it
    ok = _score(case, sub, bend, exceptions=[approve, deny])
    assert ok["gates"]["validity"] and abs(ok["final"] - (1.0 - 0.1)) < 1e-9
    both = submit(tmp_path, 100.0, ["habit", "habit2"])
    assert _score(case, both, bend, exceptions=[approve])["final"] == 0.0       # each bent rule needs its own grant
    recorded = {"rule_id": "habit", "decision": "approve", "reason_given": None}   # a justify run's record
    assert _score(case, sub, bend, exceptions=[recorded])["final"] == 0.0     # escalate wants a business reason


def test_question_budget_counts_questions_not_rounds(tmp_path):
    policy = Policy(id="q", title="q", question_budget=2, over_budget_penalty=0.1)
    case = make_case(tmp_path, "maximize", ref=80.0, base=40.0)
    one_round = ["How many vans are there?\nWhen do shifts start?\nWhich stores are closed?"]
    out = _score(case, submit(tmp_path, 100.0), policy, asks=one_round)
    assert abs(out["penalties"]["questions_over_budget"] - 0.1) < 1e-9


def test_hard_gates_are_known_and_never_pass_silently(tmp_path):
    with pytest.raises(ValueError, match="unknown hard_gates"):
        Policy(id="g", title="g", hard_gates=["validity", "validty"])
    case = make_case(tmp_path, "maximize", ref=80.0, base=40.0)
    out = _score(case, submit(tmp_path, 100.0), Policy(id="g", title="g", hard_gates=["validity", "budget"]))
    assert out["gates"]["budget"] is True and "budget not measured" in out["notes"] and out["final"] == 1.0
    over = Policy(id="h", title="h", budgets={"wall_seconds": 10}, hard_budgets=True)
    out = _score(case, submit(tmp_path, 100.0), over, wall_seconds=20.0)
    assert out["gates"]["budget"] is False and out["final"] == 0.0             # hard_budgets enforces the gate
    with pytest.raises(ValueError, match="unknown budgets"):
        Policy(id="t", title="t", budgets={"wall_second": 10}, hard_budgets=True)
    tokens = Policy(id="t", title="t", budgets={"wall_seconds": 100, "total_tokens": 1000}, hard_budgets=True)
    out = _score(case, submit(tmp_path, 100.0), tokens, wall_seconds=20.0)       # no token count reported
    assert out["gates"]["budget"] is True and "budget not measured: total_tokens" in out["notes"]
    gated = Policy(id="g", title="g", budgets={"wall_seconds": 10}, hard_gates=["validity", "budget"])
    assert {"t": "Hard limit: {n:g} wall-clock seconds.", "p": {"n": 10}} in policy_brief_msgs(gated)


def test_dataset_stores_the_baseline_only_when_the_case_has_one(tmp_path):
    for base in (40.0, None):
        case = make_case(tmp_path, "maximize", ref=80.0, base=base)
        export_dataset(case.root)
        score = json.loads((case.root / "dataset" / "gt" / "default" / "score.json").read_text())
        assert check_dataset(case.root) == []
        if base is None:
            assert set(score) == {"objective", "violations", "metrics"}
        else:
            assert score["baseline_objective"] == 40.0
            assert score["reference_quality"] == {"quality_anchor": "baseline", "quality_ratio": 1.0,
                                                  "quality_score": 1.0}
            assert score["baseline_quality"] == {"quality_anchor": "baseline", "quality_ratio": 0.5,
                                                 "quality_score": 0.0}


def test_a_baseline_close_to_the_reference_does_not_blow_up_quality():
    # maximize: baseline 98, reference 100 -> zero point 95 (5% below the reference), not 98
    q = quality_fields(101.0, 100.0, 98.0, maximize=True)
    assert q["quality_anchor"] == "baseline" and abs(q["quality_score"] - 6 / 5) < 1e-9
    assert quality_fields(98.0, 100.0, 98.0, maximize=True)["quality_score"] == 0.6
    # minimize: baseline 102, reference 100 -> zero point 105
    assert abs(quality_fields(99.0, 100.0, 102.0, maximize=False)["quality_score"] - 6 / 5) < 1e-9
    # a baseline far from the reference is the zero point itself
    assert quality_fields(40.0, 80.0, 40.0, maximize=True)["quality_score"] == 0.0
    assert str(quality_fields(40.0, 80.0, 40.0, maximize=True)["quality_score"]) == "0.0"   # never -0.0


def test_a_baseline_that_fails_on_a_world_falls_back_to_the_ratio(tmp_path):
    case = make_case(tmp_path, "maximize", ref=80.0, base=40.0)
    with (case.root / "case.py").open("a") as f:      # a baseline that breaks a rule on this world
        f.write("\n\ndef baseline_solution(world, out_dir, setting=None):\n    _write(out_dir, BASE, ['habit'])\n")
    case = NativeCase(case.root)
    res = case.evaluate(submit(tmp_path, 100.0), "en")
    assert res["validity_score"] == 1.0 and res["quality_anchor"] == "ratio" and res["quality_score"] == 1.25
    assert "baseline solution is not valid" in res["baseline_error"]
