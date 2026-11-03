"""The ground truth audit (DESIGN.md, Ground truth audit): ablations, shortcuts, value of asking, bounds, diagnostics,
the stored audit and the validator, the three stages of a target in a run, and the explainer section.

The toy is the rule-seed toy (tests/test_rule_seeds.py): order q units, objective q x price x factor (maximize), the
reference orders the cap and the baseline 2 units, so on every setting quality = (q - 2) / (cap - 2) when valid.
Its targets: cap (param: cap), min_order (medium and hard) and premium_week (param: price, when price = 5).
"""

import json
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml

import fdebench2.audit as audit_module
import fdebench2.validate as validate
from fdebench2.audit import (audit_case, audit_path, findings, fingerprint, load_audit, measured_settings, report,
                             write_audit)
from fdebench2.cases import NativeCase, Target
from fdebench2.cli import main
from fdebench2.dataset import check_dataset, export_dataset
from fdebench2.explain import UI, _t, build_page, check_page
from fdebench2.llm import ChatResponse
from fdebench2.runner import never_in_a_run, tree_hash
from fdebench2.scoring.clarify import score_clarification
from fdebench2.scoring.report import funnel_tables, report as run_report
from fdebench2.transforms.variant import VariantSpec
from fdebench2.validate import check_audit, check_case

from test_rule_seeds import CASE_YAML, TOY, make_toy

# Every audit hook, and a diagnostic that tells a right cap and the minimum order from a wrong one, but cannot tell
# an even order placed for the premium week from one that is even by chance.
HOOKS_PY = '''

_score = score


def score(world, submission_dir, setting):
    res = _score(world, submission_dir, setting)
    if "fatal" not in res:
        q = res["metrics"]["q"]
        res["enforced"] = {"cap": q == setting["cap"], "min_order": q >= 2 if setting.at_least("medium") else None,
                           "premium_week": q % 2 == 0 if setting["price"] == 5 else None}
        res["evidence"] = {"cap": f"ordered {q} of {setting['cap']}"}
    return res


def ablations(world, setting):
    return {"min_order": lambda d: _write(d, 0)} if setting.at_least("medium") else {}


def shortcuts(world, setting):
    def usual(out_dir):
        """Order the client's usual two units."""
        _write(out_dir, 2)

    def one_short(out_dir):
        """Order one unit less than the cap, to be safe."""
        _write(out_dir, setting["cap"] - 1)
    return {"usual": usual, "one_short": one_short}


def robust_solution(world, out_dir, tier, candidates):
    _write(out_dir, min(candidates["cap"]))


def best_known_solution(world, out_dir, setting):
    reference_solution(world, out_dir, setting)


def objective_bound(world, setting):
    return setting["cap"] * setting["price"] * world["factor"]
'''

# The same hooks with weaker parts, each on a threshold the validator enforces: a cap diagnostic that calls any order
# within the cap right, a minimum-order diagnostic that cannot read an empty order and an ablation of it written
# only in medium (where it bites only at cap 14), a shortcut at exactly half of the way, a best known solution that
# is not valid in the premium week, and a bound two units above the reference.
WEAKER_PY = HOOKS_PY + '''

_hooked = score


def score(world, submission_dir, setting):
    res = _hooked(world, submission_dir, setting)
    if "fatal" not in res:
        q = res["metrics"]["q"]
        res["enforced"]["cap"] = q <= setting["cap"]
        if setting.at_least("medium"):
            res["enforced"]["min_order"] = None if q == 0 else q >= 2
    return res


def ablations(world, setting):
    if setting.tier != "medium":
        return {}
    return {"min_order": lambda d: _write(d, 0 if setting["cap"] == 14 else setting["cap"])}


def shortcuts(world, setting):
    def half(out_dir):
        """Order half of the way from the usual two units to the cap."""
        _write(out_dir, setting["cap"] // 2 + 1)
    return {"half": half}


def best_known_solution(world, out_dir, setting):
    _write(out_dir, setting["cap"] + (1 if setting["price"] == 5 else 0))


def objective_bound(world, setting):
    return (setting["cap"] + 2) * setting["price"] * world["factor"]
'''

# The van holds 20 units whatever the cap: under a cap of 22 the reference for a cap of 20 is the reference itself,
# and the (correct) diagnostic calls it enforced.
VAN_PY = HOOKS_PY + '''

def reference_solution(world, out_dir, setting):
    _write(out_dir, min(setting["cap"], 20))


_hooked = score


def score(world, submission_dir, setting):
    res = _hooked(world, submission_dir, setting)
    if "fatal" not in res:
        res["enforced"]["cap"] = res["metrics"]["q"] == min(setting["cap"], 20)
    return res
'''

# Solvers that fail on admissible combinations: the reference raises at hard cap 22 price 3 and is over the cap at
# hard cap 20 price 5; the baseline raises at easy cap 12 price 5.
FAILING_PY = HOOKS_PY + '''

_reference, _baseline = reference_solution, baseline_solution


def reference_solution(world, out_dir, setting):
    at = (setting.tier, setting["cap"], setting["price"])
    if at == ("hard", 22, 3):
        raise AssertionError("no feasible plan")
    _reference(world, out_dir, setting)
    if at == ("hard", 20, 5):
        _write(out_dir, 21)


def baseline_solution(world, out_dir, setting):
    if (setting.tier, setting["cap"], setting["price"]) == ("easy", 12, 5):
        raise AssertionError("baseline plan is not valid")
    _baseline(world, out_dir, setting)
'''


# At hard cap 22 price 4 the reference orders the usual two units: under a cap of 18 at price 4, the wrong cap 20 is
# over the cap and the wrong cap 22 is valid but worth nothing, both a damage of 1.
TIE_PY = HOOKS_PY + '''

_reference = reference_solution


def reference_solution(world, out_dir, setting):
    if (setting.tier, setting["cap"], setting["price"]) == ("hard", 22, 4):
        _write(out_dir, 2)
    else:
        _reference(world, out_dir, setting)
'''


# A lazy diagnostic: score() reports only the premium week's (and None for the cap) and traces the order under a
# private key; diagnose() reads the trace, records every call and raises on a negative order, which a shortcut
# writes.
LAZY_PY = HOOKS_PY + '''

CALLS = []
_hooked, _shortcuts = score, shortcuts


def score(world, submission_dir, setting):
    res = _hooked(world, submission_dir, setting)
    if "fatal" not in res:
        res["trace"] = {"q": res["metrics"]["q"]}
        res["enforced"] = {"premium_week": res["enforced"]["premium_week"], "cap": None}
        del res["evidence"]
    return res


def diagnose(world, submission_dir, setting, scored):
    q = scored["trace"]["q"]
    CALLS.append((str(submission_dir), setting.label, q))
    if q < 0:
        raise ValueError("a negative order")
    return {"enforced": {"cap": q == setting["cap"], "min_order": q >= 2 if setting.at_least("medium") else None},
            "evidence": {"cap": f"traced {q} of {setting['cap']}"}}


def shortcuts(world, setting):
    def negative(out_dir):
        """Order a negative quantity."""
        _write(out_dir, -1)
    return {**_shortcuts(world, setting), "negative": negative}
'''

# A best known solution that keeps two units in reserve (valid, below the reference) and orders two units over the
# cap at a price of 4 (not valid): the exact-cap diagnostic calls the reserve wrong, though it knows the cap.
RESERVE_PY = HOOKS_PY + '''

def best_known_solution(world, out_dir, setting):
    _write(out_dir, setting["cap"] + (2 if setting["price"] == 4 else -2))
'''


def _with_params(root: Path) -> Path:
    """The toy's cap and premium-week targets marked as the cap and price parameters' values."""
    path = root / "locales" / "en" / "targets.yaml"
    targets = yaml.safe_load(path.read_text(encoding="utf-8"))
    targets[0]["param"], targets[2]["param"] = "cap", "price"
    path.write_text(yaml.safe_dump(targets, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return root


def toy(tmp_path: Path, hooks: bool | str = False, audited: bool = False, dataset: bool = False) -> Path:
    """The toy with param: targets; hooks=True adds HOOKS_PY, a string adds that code instead."""
    extra = HOOKS_PY if hooks is True else hooks or ""
    case_yaml = CASE_YAML + ("audited: true\n" if audited else "") + ("quality_cap: 1.5\n" if hooks else "")
    return _with_params(make_toy(tmp_path, case_yaml, extra_py=extra, dataset=dataset))


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    """(root, audit) of the toy with every hook."""
    root = toy(tmp_path_factory.mktemp("full"), hooks=True, audited=True)
    return root, audit_case(NativeCase(root))


def _rows(audit: dict, key: str, **match) -> list[dict]:
    return [r for r in audit[key] if all(r[k] == v for k, v in match.items())]


def _labels(audit: dict, **params) -> set[str]:
    """The measured settings with these parameters."""
    return {e["label"] for v in audit["settings"].values() for e in v
            if all(e["params"][k] == x for k, x in params.items())}


# ── what is measured ─────────────────────────────────────────────────────────

def test_settings_are_the_panel_and_admissible_combinations(tmp_path):
    case = NativeCase(toy(tmp_path))
    measured = measured_settings(case)
    # easy: cap 10 or 12 x price 3, 4 or 5 (all admissible); hard: 22 x 5 is over the budget of 100
    assert {t: len(v) for t, v in measured.items()} == {"easy": 6, "medium": 6, "hard": 8}
    panel = [s for s in measured["hard"] if s.panel]
    assert [s.label for s in panel] == [f"hard/s{x}" for x in (1, 2, 3)][:len(panel)]
    assert [s.label for s in measured["hard"] if not s.panel] == [f"hard/c{i}" for i in range(1, 9 - len(panel))]
    combos = {json.dumps(s.case.drawn_params, sort_keys=True) for s in measured["hard"]}
    assert len(combos) == 8 and '{"cap": 22, "price": 5}' not in combos
    assert len(measured_settings(case, combos=2)["easy"]) == len([s for s in measured["easy"] if s.panel]) + 2
    assert all(s.panel for v in measured_settings(case, combos=0).values() for s in v)
    # deterministic: the same combinations in the same order every time
    assert [s.case.drawn_params for s in measured_settings(NativeCase(case.root), 2)["easy"]] == [
        s.case.drawn_params for s in measured_settings(case, 2)["easy"]]
    # a negative count is refused (it once meant every combination of the space)
    with pytest.raises(ValueError, match="0 or more"):
        measured_settings(case, -1)
    with pytest.raises(SystemExit):
        main(["audit-case", str(case.root), "--combos", "-1"])


def test_a_param_ablation_that_bites_and_one_that_does_not(full):
    _, audit = full
    # cap 12 with a cap of 10: valid, 8 / 10 of the way -> damage 0.2; cap 10 with 12: over the cap -> invalid
    rows = _rows(audit, "ablations", target="cap", tier="easy")
    assert len(rows) == 6 and all(r["source"] == "param" and r["bites"] for r in rows)
    wrong = {next(iter(r["enforced"])): (r["best_guess"], r["invalid"], tuple(r["rules"])) for r in rows}
    assert wrong == {"cap=10": (0.2, False, ()), "cap=12": (1.0, True, ("cap",))}
    # hard, cap 22 at price 4: the wrong caps 18 and 20 lose 0.2 and 0.1; the sensible guess (20) still bites
    row = next(r for r in _rows(audit, "ablations", target="cap", tier="hard")
               if r["setting"] in _labels(audit, cap=22, price=4))
    assert (row["worst"], row["best_guess"], row["mean"], row["bites"]) == (0.2, 0.1, 0.15, True)
    assert row["damage"] == {"cap=18": 0.2, "cap=20": 0.1} and row["unavailable"] == {}
    # the premium week's even order is the reference's anyway: another price changes nothing, so it never bites
    premium = _rows(audit, "ablations", target="premium_week")
    assert premium and all(r["source"] == "param" and r["best_guess"] == 0.0 and r["bites"] is False for r in premium)
    assert {r["setting"] for r in premium} == _labels(audit, price=5)      # only where it is in force


def test_the_best_guess_is_a_valid_wrong_value_on_a_tie(tmp_path):
    audit = audit_case(NativeCase(toy(tmp_path, hooks=TIE_PY)), combos=0)
    row = next(r for r in _rows(audit, "ablations", target="cap") if r["setting"] in _labels(audit, cap=18, price=4))
    assert row["damage"] == {"cap=20": 1.0, "cap=22": 1.0} and row["best_guess"] == 1.0 and row["bites"]
    assert row["invalid"] is False and row["rules"] == ["cap"]       # the guess is valid; the other breaks the cap


def test_a_hook_ablation(full):
    _, audit = full
    rows = _rows(audit, "ablations", target="min_order")
    assert {r["tier"] for r in rows} == {"medium", "hard"} and len(rows) == 14
    assert all(r["source"] == "hook" and r["worst"] == r["best_guess"] == r["mean"] == 1.0 and r["invalid"]
               and r["rules"] == ["min_order"] and r["bites"] for r in rows)


def test_a_target_with_no_ablation_is_reported(tmp_path):
    audit = audit_case(NativeCase(toy(tmp_path)))
    rows = _rows(audit, "ablations", target="min_order")
    assert rows and all(r["source"] == "none" and r["bites"] is None and r["worst"] is None for r in rows)
    assert any(line.startswith("problem: target min_order has no ablation in 14 setting(s)") for line in audit["summary"])


def test_shortcuts_closed_and_open(full):
    _, audit = full
    usual = _rows(audit, "shortcuts", name="usual")
    assert len(usual) == 20 and all(r["valid"] and r["quality"] == 0.0 and r["closed"] for r in usual)
    assert usual[0]["description"] == "Order the client's usual two units."
    # one short of the cap: 0.9 of the way on easy cap 12, open; odd, so it breaks the premium week's even lots
    short = {r["setting"]: r for r in _rows(audit, "shortcuts", name="one_short")}
    premium = _labels(audit, price=5)
    assert all(r["closed"] and not r["valid"] and r["rules"] == ["even_lots"] for k, r in short.items() if k in premium)
    assert all(not r["closed"] and r["quality"] > 0.5 for k, r in short.items() if k not in premium)


def test_value_of_asking_on_the_easy_tier_by_hand(full):
    _, audit = full
    voi = audit["voi"]["easy"]
    # 6 settings, caps 10 and 12. A cap-10 reference: 1 under cap 10, (10 - 2) / (12 - 2) = 0.8 under cap 12 -> 0.9.
    # A cap-12 reference: invalid under cap 10 -> 0.5. The baseline: 0. robust_solution orders the smallest cap: 0.9.
    assert (voi["never_asks_params"], voi["voi_params"], voi["never_asks"], voi["voi"]) == (0.9, 0.1, 0.9, 0.1)
    by_name = {c["name"]: {k: v for k, v in c.items() if k != "name"} for c in voi["candidates"]}
    caps = {e["label"]: e["params"]["cap"] for e in audit["settings"]["easy"]}
    for label, cap in caps.items():
        assert by_name[f"reference {label}"] == ({"valid_rate": 1.0, "mean_quality": 0.9, "mean_credit": 0.9}
                                                 if cap == 10 else {"valid_rate": 0.5, "mean_quality": 1.0,
                                                                    "mean_credit": 0.5})
    first = audit["settings"]["easy"][0]["label"]
    assert by_name[f"baseline {first}"] == {"valid_rate": 1.0, "mean_quality": 0.0, "mean_credit": 0.0}
    assert by_name["robust_solution"]["mean_credit"] == 0.9
    # medium (caps 14 and 16): the smallest cap earns (1 + 12 / 14) / 2 = 0.928571 without asking
    assert audit["voi"]["medium"]["never_asks"] == 0.928571 and audit["voi"]["medium"]["voi"] == 0.071429


def test_bounds_and_diagnostics(full):
    _, audit = full
    row = audit["bounds"][0]
    assert row["best_known_quality"] == 1.0 and row["best_known_valid"] and row["bound"] == row["reference"]
    assert row["bound_quality"] == 1.0 and row["gap_to_bound"] == 0.0 and row["span"] == round(1 - row["baseline"] / row["reference"], 8)
    # premium_week: no wrong price bites (each gives the reference's own order), so there is nothing to tell apart
    assert audit["diagnostics"] == {"cap": {"has_diagnostic": True, "separates": True},
                                    "min_order": {"has_diagnostic": True, "separates": True},
                                    "premium_week": {"has_diagnostic": True, "separates": None}}
    assert {r["diag_ok"] for r in _rows(audit, "ablations", target="premium_week")} == {None}
    # the best known solution's enforced map (premium_week and min_order not in force in easy/s1)
    assert row["best_known_enforced"] == {"cap": True, "min_order": None, "premium_week": None}
    entry = audit["settings"]["medium"][0]
    assert entry["reference_enforced"] == {"cap": True, "min_order": True, "premium_week": entry["reference_enforced"]
                                           ["premium_week"]} and entry["baseline_enforced"]["cap"] is False


def test_a_harmless_wrong_value_does_not_fail_a_correct_diagnostic(tmp_path):
    audit = audit_case(NativeCase(toy(tmp_path, hooks=VAN_PY)))
    rows = {r["setting"]: r for r in _rows(audit, "ablations", target="cap", tier="hard")}
    # cap 22: the reference for cap 20 is the reference itself (enforced, and rightly so); the one for 18 loses 1/9
    for label in _labels(audit, cap=22):
        assert rows[label]["enforced"] == {"cap=18": False, "cap=20": True}
        assert rows[label]["damage"] == {"cap=18": 0.111111, "cap=20": 0.0}
        assert rows[label]["bites"] is False and rows[label]["diag_ok"] is True
    # cap 20: the wrong cap 22 (where admissible) changes nothing either; cap 18 loses 1/9, called wrong
    for label in _labels(audit, cap=20):
        assert rows[label]["enforced"]["cap=18"] is False and rows[label]["enforced"].get("cap=22", True) is True
        assert rows[label]["damage"]["cap=18"] == 0.111111 and rows[label]["diag_ok"] is True
    assert audit["diagnostics"]["cap"] == {"has_diagnostic": True, "separates": True}
    assert not any("diagnostic of target cap" in line for line in audit["summary"])


def test_a_diagnostic_that_misses_a_biting_ablation_and_the_weaker_thresholds(tmp_path):
    root = toy(tmp_path, hooks=WEAKER_PY, audited=True)
    audit = audit_case(NativeCase(root))
    # cap: "within the cap" calls the reference for a smaller cap enforced, though it loses 1/5 of the way
    row = next(r for r in _rows(audit, "ablations", target="cap") if r["setting"] in _labels(audit, cap=12, price=4))
    assert row["enforced"] == {"cap=10": True} and row["damage"] == {"cap=10": 0.2} and row["diag_ok"] is False
    # min_order: the ablation (an empty order, where the cap is 14) gets None while other orders get a diagnostic
    rows = {r["setting"]: r for r in _rows(audit, "ablations", target="min_order")}
    assert all(rows[s]["enforced"] == {"ablation": None} and rows[s]["diag_ok"] is False
               for s in _labels(audit, cap=14))
    assert all(rows[s]["damage"] == {"ablation": 0.0} and rows[s]["diag_ok"] is None for s in _labels(audit, cap=16))
    assert all(rows[s]["source"] == "none" for s in rows if s.startswith("hard/"))
    assert audit["diagnostics"] == {"cap": {"has_diagnostic": True, "separates": False},
                                    "min_order": {"has_diagnostic": True, "separates": False},
                                    "premium_week": {"has_diagnostic": True, "separates": None}}
    # a shortcut at exactly half of the way is closed
    half = _rows(audit, "shortcuts", name="half")
    assert all(r["closed"] for r in half) and any(r["valid"] and r["quality"] == 0.5 for r in half)
    # the bound two units above the reference: gap 2 / cap, (cap + 2 - 2) / (cap - 2) on the quality scale
    bound = next(b for b in audit["bounds"] if b["setting"] in _labels(audit, cap=10, price=4))
    assert (bound["gap_to_bound"], bound["bound_quality"]) == (0.2, 1.25)
    write_audit(root, audit)
    problems, warnings = check_audit(NativeCase(root))
    assert any(p.startswith("audit: the diagnostic of target cap does not tell") for p in problems)
    assert any(p.startswith("audit: the diagnostic of target min_order does not tell the reference from its "
                            "ablation in 3 setting(s)") for p in problems)
    # min_order bites in 3 of the 14 settings where it is in force (it is not checked in the 8 of hard)
    assert "audit: target min_order bites in only 3 of the 14 settings where it is in force (8 of them not checked)" \
        in warnings
    assert "audit: best_known_solution is not valid in 6 setting(s) (e.g. easy/c2)" in warnings
    # quality_cap against the median best known quality (1.0 where valid)
    caps = {cap: [f.text for f in findings(audit, cap) if f.kind == "quality_cap"] for cap in (0.9, 1.0)}
    assert caps == {0.9: ["quality_cap 0.9 is below the median best known quality 1.000"], 1.0: []}


def test_a_combination_whose_reference_or_baseline_fails_is_reported_and_replaced(tmp_path, monkeypatch):
    root = toy(tmp_path, hooks=FAILING_PY, audited=True)
    audit = audit_case(NativeCase(root), combos=3)          # the audit does not stop at a failing solver
    hard = audit["settings"]["hard"]
    skipped = [(e["label"], e["params"], e["failed"], e["skipped"]) for e in hard if "skipped" in e]
    assert skipped == [("hard/c2", {"cap": 20, "price": 5}, "reference", "the reference is not valid"),
                       ("hard/c3", {"cap": 22, "price": 3}, "reference",
                        "the reference solution fails: AssertionError('no feasible plan')")]
    # skipped combinations do not count: three are measured besides the panel
    assert len([e for e in hard if not e["panel"] and "skipped" not in e]) == 3
    assert [(e["label"], e["failed"]) for e in audit["settings"]["easy"] if "skipped" in e] == [("easy/c2", "baseline")]
    assert {r["setting"] for r in audit["ablations"]}.isdisjoint({"hard/c2", "hard/c3", "easy/c2"})
    # another value of a param: target whose reference raises is unavailable, and the others still measure it
    row = next(r for r in _rows(audit, "ablations", target="cap") if r["setting"] in _labels(audit, cap=20, price=3))
    assert row["source"] == "param" and list(row["enforced"]) == ["cap=18"]
    assert row["unavailable"] == {"hard/cap=22,price=3": "the reference solution fails: AssertionError('no feasible plan')"}
    failed = {(f.kind, f.key) for f in findings(audit, 1.5) if f.kind.startswith("invalid_")}
    assert failed == {("invalid_reference", "hard/cap=20,price=5"), ("invalid_reference", "hard/cap=22,price=3"),
                      ("invalid_baseline", "easy/cap=12,price=5")}
    assert "- hard/c3 (hard/cap=22,price=3): the reference solution fails: AssertionError('no feasible plan')" \
        in report(audit)
    write_audit(root, audit)
    problems, _ = check_audit(NativeCase(root))
    assert "audit: admissible combination easy/cap=12,price=5: the baseline solution fails: AssertionError('baseline " \
           "plan is not valid') (a rule seed can draw it; the audit could not use it)" in problems
    monkeypatch.setitem(validate.OPEN_AUDIT_FINDINGS, (TOY, "invalid_reference", "hard/cap=22,price=3"), "known")
    assert len(check_audit(NativeCase(root))[0]) == len(problems) - 1


def test_evaluate_passes_the_diagnostic_through_unless_fatal(full, tmp_path):
    root, _ = full
    case = NativeCase(root).at("medium", 1)
    (tmp_path / "zero").mkdir()
    (tmp_path / "zero" / "answer.json").write_text('{"quantity": 0}')
    res = case.evaluate(tmp_path / "zero", "en")
    assert res["validity_score"] == 0.0 and res["enforced"]["min_order"] is False
    assert res["evidence"] == {"cap": f"ordered 0 of {case.setting['cap']}"}
    (tmp_path / "empty").mkdir()
    assert "enforced" not in case.evaluate(tmp_path / "empty", "en")


# ── diagnostics on deliverables that are neither the reference nor an ablation ──

def _order(tmp_path: Path, name: str, quantity: int | None = None) -> Path:
    """A deliverable folder with answer.json ordering `quantity` (empty for None)."""
    d = tmp_path / name
    d.mkdir()
    if quantity is not None:
        (d / "answer.json").write_text(json.dumps({"quantity": quantity}))
    return d


def test_a_lazy_diagnostic_runs_only_when_asked_and_the_trace_stays_private(tmp_path):
    case = NativeCase(toy(tmp_path, hooks=LAZY_PY)).at("medium", 1)
    cap = case.setting["cap"]
    ref = _order(tmp_path, "ref", cap)
    plain = case.evaluate(ref, "en")
    premium = plain["enforced"]["premium_week"]
    assert plain["enforced"] == {"premium_week": premium, "cap": None} and "evidence" not in plain
    assert case.module.CALLS == []              # never without diagnose: the validator does not pay for it
    res = case.evaluate(ref, "en", diagnose=True)
    # merged: score()'s premium week, diagnose()'s cap (over score()'s None) and minimum order
    assert res["enforced"] == {"premium_week": premium, "cap": True, "min_order": True}
    assert res["evidence"] == {"cap": f"traced {cap} of {cap}"} and res["quality_score"] == plain["quality_score"] == 1
    assert case.module.CALLS == [(str(ref), "medium/s1", cap)]
    # the order score() traced reaches diagnose(), never the result
    assert "trace" not in plain and "trace" not in res
    # an invalid deliverable is diagnosed, a fatal one is not
    zero = case.evaluate(_order(tmp_path, "zero", 0), "en", diagnose=True)
    assert zero["validity_score"] == 0.0 and zero["enforced"]["min_order"] is False and zero["enforced"]["cap"] is False
    assert "enforced" not in case.evaluate(_order(tmp_path, "empty"), "en", diagnose=True)
    assert len(case.module.CALLS) == 2
    # a hook that raises never stops scoring: the result says why, and score()'s map stands
    broken = case.evaluate(_order(tmp_path, "negative", -1), "en", diagnose=True)
    assert broken["diagnose_error"] == "ValueError('a negative order')" and broken["enforced"]["cap"] is None


def test_the_audit_diagnoses_every_deliverable_but_the_value_of_information_matrix(full, tmp_path):
    case = NativeCase(toy(tmp_path, hooks=LAZY_PY, audited=True))
    audit = audit_case(case)
    _, eager = full
    # the same diagnostics as with score() computing them itself
    assert audit["diagnostics"] == eager["diagnostics"] and audit["diagnostic_profile"] == eager["diagnostic_profile"]
    assert [r["cross_flags"] for r in audit["ablations"]] == [r["cross_flags"] for r in eager["ablations"]]
    assert [b["best_known_enforced"] for b in audit["bounds"]] == [b["best_known_enforced"] for b in eager["bounds"]]
    # the matrix scores each tier's references and first baseline in every setting of the tier without diagnose():
    # robust_solution (the tier's smallest cap) is the only deliverable diagnosed in every setting of its tier (the
    # hook sees the setting's own label: "easy/s1[cap=12,price=5]" for the audit's easy/c1)
    seen: dict[str, tuple[set, int]] = {}
    for path, label, q in case.module.CALLS:
        seen.setdefault(path, (set(), q))[0].add(label)
    for tier, entries in audit["settings"].items():
        everywhere = [q for at, q in seen.values() if len({x for x in at if x.startswith(f"{tier}/")}) == len(entries)]
        assert everywhere == [min(case.param_candidates["cap"][tier])], tier
    # the shortcut that orders a negative quantity breaks diagnose() in every setting: a problem
    error = "ValueError('a negative order')"
    assert audit["diagnose_errors"]["count"] == 20
    assert audit["diagnose_errors"]["examples"][0] == {"deliverable": "shortcut", "setting": "easy/s1", "error": error}
    assert f"problem: case.py diagnose() raised in 20 evaluation(s) (e.g. the shortcut in easy/s1: {error})" \
        in audit["summary"]


def test_a_best_known_solution_the_diagnostic_calls_wrong_is_a_false_negative(tmp_path, monkeypatch):
    root = toy(tmp_path, hooks=RESERVE_PY, audited=True)
    audit = audit_case(NativeCase(root))
    valid = [b["setting"] for b in audit["bounds"] if b["best_known_valid"]]
    assert set(valid) == {b["setting"] for b in audit["bounds"]} - _labels(audit, price=4)
    assert all(b["best_known_enforced"]["cap"] is False for b in audit["bounds"])
    # two units in reserve still order at least two and an even number: only the cap's diagnostic is wrong, and
    # only where the best known solution is valid counts
    found = [f for f in findings(audit, 1.5) if f.kind == "diagnostic_false_negative"]
    assert [(f.problem, f.key) for f in found] == [(True, "cap")]
    assert found[0].text == (f"the diagnostic of target cap calls the best known solution, which knows every fact, not "
                             f"enforced in {len(valid)} of the {len(valid)} settings where it is valid "
                             f"(e.g. {valid[0]})")
    assert f"| cap | {len(valid)}/{len(valid)} |" in report(audit)
    write_audit(root, audit)
    problems, _ = check_audit(NativeCase(root))
    assert f"audit: {found[0].text}" in problems
    monkeypatch.setitem(validate.OPEN_AUDIT_FINDINGS, (TOY, "diagnostic_false_negative", "cap"), "a regret check")
    waived, warnings = check_audit(NativeCase(root))
    assert waived == [p for p in problems if p != f"audit: {found[0].text}"]
    assert f"audit: {found[0].text} (known and open: a regret check)" in warnings
    # an audit stored before the reliability checks (no best known map, cross flags or profile) still reads
    old = {k: v for k, v in audit.items() if k not in ("diagnostic_profile", "diagnose_errors")}
    old["bounds"] = [{k: v for k, v in b.items() if k != "best_known_enforced"} for b in audit["bounds"]]
    old["ablations"] = [{k: v for k, v in r.items() if k != "cross_flags"} for r in audit["ablations"]]
    assert not {f.kind for f in findings(old, 1.5)} & {"diagnostic_false_negative", "cross_flags", "diagnose_error"}
    assert "| cap | – | – | – | – |" in report(old)


def test_cross_flags_name_the_other_targets_an_ablation_is_called_wrong_on(full):
    _, audit = full
    # min_order's ablation (an empty order) is not an order of the cap either, says the cap's exact diagnostic
    rows = _rows(audit, "ablations", target="min_order")
    assert rows and all(r["cross_flags"] == {"ablation": ["cap"]} for r in rows)
    # the cap's ablations bite and flag nothing else; premium_week's never bite, so there is nothing to look at
    assert all(r["cross_flags"] and not any(r["cross_flags"].values()) for r in _rows(audit, "ablations", target="cap"))
    assert all(r["cross_flags"] == {} for r in _rows(audit, "ablations", target="premium_week"))
    found = [f for f in findings(audit, 1.5) if f.kind == "cross_flags"]
    assert [(f.problem, f.key) for f in found] == [(False, "min_order")]       # a warning: facts can interact

    def warned(k: int) -> list[str]:
        """The cross_flags warnings for a target whose ablation bites in 4 settings and flags another in k."""
        rows = [{"target": "u", "setting": f"easy/s{i}", "cross_flags": {"ablation": ["t"] if i < k else []}}
                for i in range(4)]
        return [f.key for f in audit_module._reliability_findings({"ablations": rows, "bounds": []})]
    assert warned(2) == [] and warned(3) == ["u"]       # more than half of the settings where it bites


def test_the_audit_is_deterministic_and_reported(full):
    root, audit = full
    assert audit == audit_case(NativeCase(root)) and json.loads(json.dumps(audit)) == audit
    assert set(audit) == {"case", "world_seed", "fingerprint", "thresholds", "settings", "ablations", "shortcuts", "voi",
                          "bounds", "diagnostics", "diagnostic_profile", "diagnose_errors", "summary"}
    text = report(audit)
    assert "| cap | param | 0.100–1.000 | 1.000 | easy 6/6, medium 6/6, hard 8/8 | 0 | separates |" in text
    # the diagnostic profile: the empty order of min_order's ablation is not the cap, says the cap's diagnostic
    assert "## Diagnostic profile" in text and "| cap | 0/20 | 0/20 | 20/20 | 11/20 |" in text
    assert "| min_order | 0/14 | 14/14 (cap) | 0/14 | 0/14 |" in text
    assert "| premium_week | param | 0.000 | 0.000 | easy 0/2, medium 0/2, hard 0/2 | 0 | untested |" in text
    assert "| one_short | Order one unit less than the cap, to be safe. | 6/20 | 0.950 |" in text
    assert "| easy | 0.900 | 0.100 | " in text and "## Reference and bounds" in text and "## Skipped" not in text
    other = audit_case(NativeCase(root), world_seed=2)
    assert other["world_seed"] == 2 and other["fingerprint"] == audit["fingerprint"]


# ── the stored audit and the validator ───────────────────────────────────────

STALE = "audit: dataset/audit.json is stale (the case changed since it was written): run `fdebench2 audit-case`"


def test_the_fingerprint_covers_what_the_audit_measures(tmp_path, monkeypatch):
    root = toy(tmp_path)
    write_audit(root, audit_case(NativeCase(root), combos=1))
    before = fingerprint(root)
    assert check_audit(NativeCase(root)) == ([], [])

    def changes(rel: str, text: str) -> bool:
        path = root / rel
        old = path.read_bytes() if path.is_file() else None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        after = fingerprint(root)
        path.write_bytes(old) if old is not None else path.unlink()
        return after != before
    # the docs in every language (GT.md and CLIENT_REVIEW.md too: they are written from audit.json), the stored
    # dataset and the keys that decide only what validate-case enforces: no
    assert not any(changes(rel, "notes\n") for rel in ("README.md", "README.ko.md", "REVIEW.ja.md", "explainer.es.html",
                                                       "GT.md", "CLIENT_REVIEW.md", "locales/ko/summary.yaml",
                                                       "locales/zh/explainer.yaml", "dataset/audit.json",
                                                       "dataset/MANIFEST.json"))
    assert never_in_a_run("GT.md") and never_in_a_run("CLIENT_REVIEW.md")    # nor a run's fingerprint
    assert not changes("case.yaml", CASE_YAML + "audited: true\nquality_cap: 1.2\n")
    # everything else: the texts in any locale, case.yaml, a reference program case.py copies or imports
    assert changes("locales/ko/requirements.md", "# x\n") and changes("locales/es/targets.yaml", "[]\n")
    assert changes("case.yaml", CASE_YAML.replace("seed: 7", "seed: 8")) and changes("reference/solver.py", "X = 1\n")
    assert fingerprint(root) == before
    # and the audit module itself
    copy = tmp_path / "audit.py"
    copy.write_text(Path(audit_module.__file__).read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    monkeypatch.setattr(audit_module, "__file__", str(copy))
    assert fingerprint(root) != before


def test_a_stale_audit_and_its_waiver(tmp_path, monkeypatch):
    root = toy(tmp_path)
    write_audit(root, audit_case(NativeCase(root), combos=1))
    path = root / "locales" / "ko" / "requirements.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert check_audit(NativeCase(root)) == ([], [STALE])               # not audited: a warning only
    (root / "case.yaml").write_text(CASE_YAML + "audited: true\n", encoding="utf-8")
    problems, _ = check_audit(NativeCase(root))
    # audited: stale, and the stored audit's own problems (no robust_solution, no bounds, no quality_cap, ...)
    assert problems[0] == STALE and len(problems) >= 4
    assert all(p.startswith("audit: (stale audit) ") for p in problems[1:])
    # waiving the stale audit waives only that
    monkeypatch.setitem(validate.OPEN_AUDIT_FINDINGS, (TOY, "audit", "stale"), "re-run once the texts settle")
    waived, warnings = check_audit(NativeCase(root))
    assert waived == problems[1:] and warnings[0] == STALE + " (known and open: re-run once the texts settle)"


def test_validator_problems_for_an_audited_toy(tmp_path):
    root = toy(tmp_path, audited=True)
    assert check_audit(NativeCase(root)) == (
        ["audit: dataset/audit.json is missing: run `fdebench2 audit-case`"], [])
    write_audit(root, audit_case(NativeCase(root)))
    problems, warnings = check_audit(NativeCase(root))
    # targets in the order the measured settings first meet them: premium_week in an easy setting, min_order in medium
    assert [p.split(":")[1].strip().split(" ")[0:3] for p in problems] == [
        ["target", "premium_week", "bites"], ["target", "premium_week", "bites"], ["target", "premium_week", "bites"],
        ["target", "min_order", "has"], ["case.py", "has", "no"], ["case.py", "has", "neither"],
        ["case.yaml", "sets", "no"]]
    assert [p.rsplit("tier ", 1)[1].split(":")[0] for p in problems[:3]] == ["easy", "medium", "hard"]
    assert warnings == [f"audit: target {t} has no diagnostic (score() reports no enforced[{t}])"
                        for t in ("cap", "premium_week", "min_order")]


def test_validator_with_every_hook_and_a_waiver(full, monkeypatch):
    root, audit = full
    write_audit(root, audit)
    problems, warnings = check_audit(NativeCase(root))
    assert problems == [
        "audit: target premium_week bites in no measured setting of tier easy: misreading it loses less than 10%",
        "audit: target premium_week bites in no measured setting of tier medium: misreading it loses less than 10%",
        "audit: target premium_week bites in no measured setting of tier hard: misreading it loses less than 10%",
        next(p for p in problems if p.startswith("audit: shortcut one_short (Order one unit less than the cap, to be "
                                                  "safe.) is open in 14 of 20 settings")),
        "audit: asking is worth only 0.071 in tier medium (never asks earns 0.929; at least 0.1 is required)",
        "audit: asking is worth only 0.092 in tier hard (never asks earns 0.908; at least 0.1 is required)"]
    assert warnings == ["audit: the ablation of target min_order also calls other targets not enforced in 14 of the 14 "
                        "settings where it bites: cap (14) (e.g. medium/s1)",
                        "audit: asking is worth only 0.100 in tier easy"]
    monkeypatch.setitem(validate.OPEN_AUDIT_FINDINGS, (TOY, "shortcut", "one_short"), "the owner decides")
    monkeypatch.setitem(validate.OPEN_AUDIT_FINDINGS, (TOY, "voi", "hard"), "a later change")
    problems, warnings = check_audit(NativeCase(root))
    assert len(problems) == 4 and len(warnings) == 4 and warnings[1].endswith("(known and open: the owner decides)")
    assert warnings[3].endswith("tier hard (never asks earns 0.908; at least 0.1 is required) (known and open: a later "
                                "change)")


def test_a_target_param_must_name_a_parameter(tmp_path):
    root = toy(tmp_path)
    path = root / "locales" / "en" / "targets.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("param: price", "param: colour"), encoding="utf-8")
    assert "en/targets.yaml premium_week: param 'colour' is not a parameter in case.yaml params:" in check_case(root).problems


def test_audit_case_stores_the_public_world_and_the_case_still_validates(tmp_path, capsys):
    root = toy(tmp_path, dataset=True)
    export_dataset(root)                    # the targets gained param: (a source of the audit, not of the dataset)
    page = (root / "explainer.html").read_text(encoding="utf-8")
    assert 'id="evidence"' not in page and "#evidence" not in page
    main(["audit-case", str(root), "--world-seed", "2"])
    assert "# Ground truth audit: logistics/toy_planner (world seed 2)" in capsys.readouterr().out
    assert load_audit(root) is None                                       # another world is printed, never stored
    ran, ko = tree_hash(root, never_in_a_run), (root / "explainer.ko.html").read_text(encoding="utf-8")
    main(["audit-case", str(root), "--combos", "2"])
    assert load_audit(root)["world_seed"] == 7 and check_page(root) == [] and check_dataset(root) == []
    # the pages in every language and audit.json changed, and none of it reaches a run: stored runs stay fresh
    assert (root / "explainer.ko.html").read_text(encoding="utf-8") != ko and tree_hash(root, never_in_a_run) == ran
    page = (root / "explainer.html").read_text(encoding="utf-8")
    assert '<section id="evidence"><h2>Evidence the facts matter</h2>' in page and 'href="#evidence"' in page
    assert "If the AI gets only this fact wrong" in page and "the reference for another value of <code>cap</code>" in page
    # min_order has no ablation: no "0 of 0 settings" where it matters, a dash
    assert "<td>not checked yet</td><td>–</td><td>–</td>" in page and "0 of 0" not in page
    export_dataset(root)                                                   # the audit is kept, not rerun
    assert audit_path(root).is_file() and check_dataset(root) == [] and check_page(root) == []
    report = check_case(root)
    assert report.problems == [] and not any(w.startswith("audit:") for w in report.warnings)


def test_every_locale_words_the_evidence_section(tmp_path):
    assert all(set(UI[lang]) == set(UI["en"]) for lang in UI)
    assert all(isinstance(UI[lang][k], str) for lang in UI for k in ("answer_yes", "answer_no"))   # never booleans
    root = toy(tmp_path, hooks=True, dataset=True)
    path = root / "locales" / "ko" / "explainer.yaml"
    words = yaml.safe_load(path.read_text(encoding="utf-8"))
    path.write_text(yaml.safe_dump({**words, "shortcuts": {"usual": "고객이 늘 주문하는 두 개를 주문합니다."}},
                                   allow_unicode=True), encoding="utf-8")
    write_audit(root, audit_case(NativeCase(root), combos=1))
    for lang in UI:
        page = build_page(root, lang)
        for key in ("evidence_title", "ablation_title", "shortcuts_title", "voi_title", "bounds_title", "in_force_tiers",
                    "voi_params", "best_known"):
            assert _t(lang, key) in page, (lang, key)
        # the shortcuts in the page's language when the case words them, else in their docstring's English
        usual = "고객이 늘 주문하는 두 개를 주문합니다." if lang == "ko" else "Order the client&#x27;s usual two units."
        assert f"<td><code>usual</code></td><td>{usual}</td>" in page, lang
    # one word for the tier in the whole section
    ko = build_page(root, "ko")
    assert "적용 티어" in ko and "적용 난이도" not in ko and "한 티어의 설정들" in ko


# ── three stages per target in a run ─────────────────────────────────────────

class Judge:
    """A ChatModel that answers each target's question with replies[target id]."""

    name = "judge"

    def __init__(self, replies: dict[str, dict]):
        self.replies = replies

    def chat(self, messages, tools=None, **kwargs):
        target = next(t for t in self.replies if f"[{t}]" in messages[-1]["content"])
        return ChatResponse(content=json.dumps(self.replies[target]))


def test_clarify_tells_revealed_from_covered():
    targets = [Target(id=i, text=f"[{i}] {text}", source_text=f"[{i}] {text}") for i, text in
               (("cap", "Each van carries 40 trays."), ("closed", "Café C3 is closed on Friday."),
                ("rush", "The rush starts at 07:00."))]
    asks = ["How many trays fit in a van?\nWhich vans are there?", "When do shifts start?"]
    answers = ["Each van takes 40 trays. By the way, café C3 is closed on Friday.", "Shifts start at 5:00."]
    # closed: volunteered in round 1's answer; the judge cites question 1 but says no question asked for it
    judge = Judge({"cap": {"revealed": True, "quote": "Each van takes\n40 trays", "asked": True, "questions": [1, 3]},
                   "closed": {"revealed": True, "quote": "café C3 is closed on Friday", "asked": False, "questions": [1]},
                   "rush": {"revealed": True, "quote": "The rush starts at 07:00", "asked": True, "questions": [3]}})
    res = score_clarification(targets, asks, [judge], answers=answers)
    # volunteered (closed) is revealed but not learned through a question; an invented quote (rush) is neither
    assert res.revealed == {"cap": True, "closed": True, "rush": False}
    assert res.covered == {"cap": True, "closed": False, "rush": False}
    assert (res.recall, res.precision) == (1 / 3, 1 / 3)            # only question 1 holds the quote it cites
    assert res.to_dict()["revealed"] == res.revealed
    assert score_clarification(targets, asks, [judge], answers=None).revealed == {t.id: None for t in targets}
    assert score_clarification(targets, [], [judge], answers=[]).revealed == {t.id: False for t in targets}


def _stages(revealed, learned, enforced) -> dict:
    return {"revealed": revealed, "learned": learned, "enforced": enforced}


def test_a_run_is_scored_with_the_lazy_diagnostic(tmp_path):
    from fdebench2.llm import Endpoint, ModelRegistry, ScriptedModel, ToolCall
    from fdebench2.runner import AgentSpec, Bench, Settings
    root = toy(tmp_path, hooks=LAZY_PY)
    cap = NativeCase(root).at("medium", 1).setting["cap"]
    steps = [ChatResponse(content="", tool_calls=[ToolCall(id=f"c{i}", name=name, arguments=args)])
             for i, (name, args) in enumerate([("write_file", {"path": "answer.json",
                                                               "content": json.dumps({"quantity": cap})}),
                                                ("finish", {"summary": "done"})])]
    reg = ModelRegistry({"agent": Endpoint("agent", "scripted")}, {})
    reg._cache["agent"] = ScriptedModel(steps)
    bench = Bench(Settings(cases_root=tmp_path / "cases", models=tmp_path / "none.yaml", out=tmp_path / "runs"),
                  registry=reg)
    result = bench.run(VariantSpec(TOY, condition="full"), AgentSpec("reference", "agent"))
    assert result["evaluator"]["validity_score"] == 1.0 and '"trace"' not in json.dumps(result)
    # the cap and the minimum order are diagnosed only by diagnose(), which only an evaluation with diagnose=True runs
    assert result["targets"]["cap"] == {"revealed": None, "learned": None, "enforced": True}
    assert result["targets"]["min_order"]["enforced"] is True
    assert result["evaluator"]["evidence"] == {"cap": f"traced {cap} of {cap}"}


def test_run_result_targets_and_the_funnel_table():
    from fdebench2.runner import target_stages
    targets = [Target(id="cap", text="", source_text=""), Target(id="v2·dup", text="", source_text="", origin="noise")]
    stages = target_stages(targets, {"covered": {"cap": True, "v2·dup": False}, "revealed": {"cap": True}},
                           {"enforced": {"cap": False}})
    assert stages == {"cap": {"revealed": True, "learned": True, "enforced": False},
                      "v2·dup": {"revealed": None, "learned": False, "enforced": None}}
    assert target_stages(targets, None, {})["cap"] == {"revealed": None, "learned": None, "enforced": None}

    def run(case, **targets):
        return {"spec": {"case_id": case}, "targets": {k: _stages(*v) for k, v in targets.items()}}
    unmeasured = (None, None, None)
    results = [run("a/x", cap=(True, True, True), floor=(True, False, False), idle=unmeasured),
               run("a/x", cap=(True, True, False), floor=unmeasured, idle=unmeasured),
               run("a/x", cap=(False, False, None), floor=(True, False, True)),
               run("a/x", cap=(True, False, True)), {"spec": {"case_id": "b/y"}}, run("c/z", u=unmeasured)]
    table = funnel_tables(results)
    assert table.splitlines()[:4] == ["### target funnel: a/x (share of runs, measured runs in brackets)", "",
                                      "| target | revealed | learned | enforced | enforced if learned "
                                      "| enforced if not learned |", "|---|---|---|---|---|---|"]
    assert "| cap | 0.75 (4) | 0.50 (4) | 0.67 (3) | 0.50 (2) | 1.00 (1) |" in table
    assert "| floor | 1.00 (2) | 0.00 (2) | 0.50 (2) | – | 0.50 (2) |" in table
    # a target no run measured, and a case with only such targets, are noise: left out
    assert "idle" not in table and "b/y" not in table and "c/z" not in table
    assert funnel_tables([{"spec": {"case_id": "b/y"}}]) is None and funnel_tables([run("c/z", u=unmeasured)]) is None


def _result(case: str, trial: int, targets: dict) -> dict:
    spec = VariantSpec(case, trial=trial)
    return {"spec": asdict(spec), "agent": {"harness": "reference", "model": "m"}, "key": spec.key(), "status": "ok",
            "score": {"final": 1.0, "gates": {"validity": True}, "components": {"quality": 1.0}, "quality_raw": 1.0},
            "clarification": None, "error": "", "usage": {"total_tokens": 10, "cost_usd": 0.0}, "targets": targets}


def test_the_report_shows_the_funnel(tmp_path):
    rows = [_result("x/a", 0, {"cap": _stages(True, True, True), "idle": _stages(None, None, None)}),
            _result("x/a", 1, {"cap": _stages(False, False, None), "idle": _stages(None, None, None)}),
            _result("x/b", 0, {"u": _stages(None, None, None)})]
    for i, r in enumerate(rows):
        d = tmp_path / "out" / "m" / str(i)
        d.mkdir(parents=True)
        (d / "result.json").write_text(json.dumps(r), encoding="utf-8")
    text = run_report(tmp_path / "out")
    assert "### target funnel: x/a" in text and "| cap | 0.50 (2) | 0.50 (2) | 1.00 (1) | 1.00 (1) | – |" in text
    assert "| idle |" not in text and "### target funnel: x/b" not in text
