"""validate-case itself: a copied case passes, and each authoring slip planted in a copy is reported."""

import shutil
from pathlib import Path

import pytest

from fdebench2.explain import write_page
from fdebench2.scaffold import new_case
from fdebench2.validate import check_case, validate_case

REPO = Path(__file__).resolve().parents[1]
FAST = "logistics/bakery_delivery_dispatcher"         # the quickest full validation
SETTINGS = "manufacturing/procurement_specialist"     # rule-set parameters, setting blocks and a README

# The reference with every van leaving 30 minutes earlier: still valid, but the drivers wait at the cafés.
WORSE_BASELINE = '''

def baseline_solution(world, out_dir):
    routes = [{**r, "depart": _hhmm(max(DAY_START, int(r["depart"][:2]) * 60 + int(r["depart"][3:]) - 30))}
              for r in world.plan]
    (out_dir / "routes.json").write_text(json.dumps({"routes": routes}), encoding="utf-8")
'''
SAME_BASELINE = '''

def baseline_solution(world, out_dir):
    reference_solution(world, out_dir)
'''


def _copy(tmp_path: Path, case_id: str) -> Path:
    """A private copy of one case, with an explainer built by this code (the stored one may predate it)."""
    dest = tmp_path / "cases" / case_id
    shutil.copytree(REPO / "cases" / case_id, dest, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(REPO / "cases" / "fields.yaml", tmp_path / "cases" / "fields.yaml")
    write_page(dest)
    return dest


def _append(path: Path, text: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def test_unmodified_copy_passes(tmp_path):
    report = check_case(_copy(tmp_path, FAST))
    assert report.problems == []
    # The texts call C11 the Clock Tower café; the data calls it South Hill.
    assert any(w.startswith("en:") and "C11" in w for w in report.warnings)


def test_setting_marker_in_request(tmp_path):
    root = _copy(tmp_path, SETTINGS)
    _append(root / "locales/en/request.md", "\n<!-- ruleset: A -->\nOnly in rule set A.\n<!-- /ruleset -->\n")
    assert "en/request.md: must be the same in every setting (no markers or parameters)" in validate_case(root)


def test_example_that_does_not_violate(tmp_path):
    root = _copy(tmp_path, FAST)
    _append(root / "case.py", '''

_examples = violating_examples


def violating_examples(world):
    return {**_examples(world), "van_capacity": lambda out: reference_solution(world, out)}
''')
    assert "rule van_capacity: its example does not violate it (got [])" in validate_case(root)


def test_parameter_missing_from_one_locale(tmp_path):
    root = _copy(tmp_path, SETTINGS)
    path = root / "locales/ko/requirements.md"
    path.write_text(path.read_text(encoding="utf-8").replace("{{usd_krw}}", "1,380"), encoding="utf-8")
    assert "ko/requirements.md: parameters differ from en (missing ['usd_krw'])" in validate_case(root)


def test_todo_left_in_readme(tmp_path):
    root = _copy(tmp_path, SETTINGS)
    _append(root / "README.md", "\nTODO: the numbers for world seed 2.\n")
    assert any(p.startswith("README.md: TODO left on line") for p in validate_case(root))


def test_target_missing_in_one_locale(tmp_path):
    root = _copy(tmp_path, SETTINGS)
    path = root / "locales/es/targets.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text[:text.index("- id: expected_cost")], encoding="utf-8")
    assert "es/targets.yaml: target ids differ from en (missing ['expected_cost'])" in validate_case(root)


@pytest.mark.parametrize("baseline, ok", [(WORSE_BASELINE, True), (SAME_BASELINE, False)], ids=["worse", "same"])
def test_baseline_must_be_valid_and_worse(tmp_path, baseline, ok):
    root = _copy(tmp_path, FAST)
    _append(root / "case.py", baseline)
    report = check_case(root)
    if ok:
        assert report.problems == [] and report.notes == ["baseline/reference objective: 1.188"]
    else:
        assert any("is not worse than the reference" in p for p in report.problems)


def test_hash_seed_leaking_into_data(tmp_path):
    root = _copy(tmp_path, FAST)
    _append(root / "case.py", '''

_write_data = write_data


def write_data(world, data_dir, lang):
    _write_data(world, data_dir, lang)
    (data_dir / "batch.txt").write_text(" ".join({"rye", "spelt", "wheat", "oat"}), encoding="utf-8")
''')
    assert any("differs between processes with PYTHONHASHSEED" in p for p in validate_case(root))


def test_new_case_fails_until_filled(tmp_path):
    shutil.copy2(REPO / "cases" / "fields.yaml", tmp_path / "fields.yaml")
    root = new_case("retail/shelf_planner", tmp_path)
    problems = validate_case(root)
    assert {"case.yaml", "case.py", "README.md", "locales/en/request.md"} <= {p.split(":")[0] for p in problems
                                                                            if "TODO left" in p}
