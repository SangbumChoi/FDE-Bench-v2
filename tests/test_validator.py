"""validate-case itself: a copied case passes, and each authoring slip planted in a copy is reported."""

import html
import shutil
from pathlib import Path

import pytest

from fdebench2.cli import main
from fdebench2.dataset import export_dataset
from fdebench2.explain import check_page, write_page
from fdebench2.scaffold import new_case
from fdebench2.validate import Report, check_case, check_hash_seed, validate_case

REPO = Path(__file__).resolve().parents[1]
FAST = "logistics/bakery_delivery_dispatcher"         # the quickest full validation
SETTINGS = "manufacturing/procurement_specialist"     # rule parameters, setting blocks and a README

# The reference with every van leaving 30 minutes earlier: still valid, but the drivers wait at the cafés.
WORSE_BASELINE = '''

def baseline_solution(world, out_dir, setting):
    rules = rules_of(setting)
    routes = [{**r, "depart": _hhmm(max(rules.earliest(r["van"]), _minutes(r["depart"]) - 30))}
              for r in _plan(world, rules)]
    (out_dir / "routes.json").write_text(json.dumps({"routes": routes}), encoding="utf-8")
'''
SAME_BASELINE = '''

def baseline_solution(world, out_dir, setting):
    reference_solution(world, out_dir, setting)
'''
EMPTY_BASELINE = '''

def baseline_solution(world, out_dir, setting):
    pass
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
    assert check_case(_copy(tmp_path, FAST)).problems == []


def test_name_that_does_not_match_the_data(tmp_path):
    root = _copy(tmp_path, FAST)
    # C11 is the South Hill café in the data; the text calls it by another café's name.
    _append(root / "locales/en/requirements.md", "\n- The Clock Tower café (C11) is closed on Friday.\n")
    assert any(w.startswith("en:") and "C11" in w for w in check_case(root).warnings)


def test_setting_marker_in_request(tmp_path):
    root = _copy(tmp_path, SETTINGS)
    _append(root / "locales/en/request.md", "\n<!-- tier: hard -->\nOnly in the hard tier.\n<!-- /tier -->\n")
    assert "en/request.md: must be the same in every setting (no markers or parameters)" in validate_case(root)


def test_example_that_does_not_violate(tmp_path):
    root = _copy(tmp_path, FAST)
    _append(root / "case.py", '''

_examples = violating_examples


def violating_examples(world, setting):
    return {**_examples(world, setting), "van_capacity": lambda out: reference_solution(world, out, setting)}
''')
    assert any(p.endswith("rule van_capacity: its example does not violate it (got [])") for p in validate_case(root))


def test_parameter_missing_from_one_locale(tmp_path):
    root = _copy(tmp_path, SETTINGS)
    path = root / "locales/ko/requirements.md"
    path.write_text(path.read_text(encoding="utf-8").replace("{{usd_krw}}", "1,380"), encoding="utf-8")
    assert "ko/requirements.md: parameters differ from en (missing ['usd_krw'])" in validate_case(root)


@pytest.mark.parametrize("name, text", [("README.md", "\nTODO: the numbers for world seed 2.\n"),
                                        ("case.yaml", "# rules:\n#   - id: TODO_rule\n")], ids=["readme", "scaffold-id"])
def test_todo_left(tmp_path, name, text):
    root = _copy(tmp_path, SETTINGS)
    _append(root / name, text)
    assert any(p.startswith(f"{name}: TODO left on line") for p in validate_case(root))


def test_setting_blocks_differ_in_one_locale(tmp_path):
    root = _copy(tmp_path, SETTINGS)
    path = root / "locales/ja/requirements.md"
    path.write_text(path.read_text(encoding="utf-8").replace("<!-- tier: medium hard -->", "<!-- tier: hard -->", 1),
                    encoding="utf-8")
    assert ("ja/requirements.md: setting markers differ from en at block 5: 'tier: hard', en has 'tier: medium hard'"
            in validate_case(root))


def test_target_missing_in_one_locale(tmp_path):
    root = _copy(tmp_path, SETTINGS)
    path = root / "locales/es/targets.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text[:text.index("- id: expected_cost")], encoding="utf-8")
    assert "es/targets.yaml: target ids differ from en (missing ['expected_cost'])" in validate_case(root)


@pytest.mark.parametrize("baseline, problem", [(WORSE_BASELINE, None),
                                               (SAME_BASELINE, "is not worse than the reference"),
                                               (EMPTY_BASELINE, "the baseline is not valid: missing routes.json")],
                         ids=["worse", "same", "invalid"])
def test_baseline_must_be_valid_and_worse(tmp_path, baseline, problem):
    root = _copy(tmp_path, FAST)
    _append(root / "case.py", baseline)
    if problem is None:
        export_dataset(root)  # the stored scores now include the baseline's
        write_page(root)
    report = check_case(root)
    if problem is None:
        assert report.problems == [] and report.notes[0].startswith("baseline/reference objective: easy/s5 ")
    else:
        assert any(problem in p for p in report.problems)


def test_hash_seed_leaking_into_data(tmp_path):
    root = _copy(tmp_path, FAST)
    _append(root / "case.py", '''

_write_data = write_data


def write_data(world, data_dir, lang):
    _write_data(world, data_dir, lang)
    (data_dir / "batch.txt").write_text(" ".join({"rye", "spelt", "wheat", "oat"}), encoding="utf-8")
''')
    assert any("differs between processes with PYTHONHASHSEED" in p for p in validate_case(root))


def test_hash_seed_check_imports_this_package(tmp_path, monkeypatch):
    """The two processes run this checkout's fdebench2, not one that happens to sit in the working directory."""
    root = _copy(tmp_path, FAST)
    (tmp_path / "fdebench2").mkdir()
    (tmp_path / "fdebench2" / "__init__.py").write_text("raise ImportError('another checkout')\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert check_hash_seed(root) == []


def test_review_findings_in_explainer(tmp_path):
    root = _copy(tmp_path, FAST)
    (root / "REVIEW.md").write_text("# Findings\n\n- C11 is the Clock Tower café in the texts only.\n", encoding="utf-8")
    assert check_page(root) == ["explainer.html is out of date: run `fdebench2 explain-case` (or export-dataset)"]
    page = write_page(root).read_text(encoding="utf-8")
    assert '<section id="review">' in page and "C11 is the Clock Tower café in the texts only." in page
    assert ("Deliverable spec (shown to the extractor that reshapes the agent's files, not to the agent)"
            in html.unescape(page))
    assert check_page(root) == []
    # every language has its own page, its interface and the case's words in that language
    ko = (root / "explainer.ko.html").read_text(encoding="utf-8")
    assert '<html lang="ko">' in ko and "에이전트가 받는 요청" in ko and "베이커리" in ko


@pytest.mark.parametrize("args, seeds", [([], [1, 2, 3]), (["--world-seeds", "7"], [7]), (["--world-seeds", ""], []),
                                         (["--no-world-seeds"], [])], ids=["default", "given", "empty", "none"])
def test_cli_world_seed_panel(monkeypatch, args, seeds):
    asked = []
    monkeypatch.setattr("fdebench2.validate.check_case", lambda path, world_seeds: asked.append(world_seeds) or Report())
    with pytest.raises(SystemExit) as done:
        main(["validate-case", "cases/logistics/bakery_delivery_dispatcher", *args])
    assert done.value.code == 0 and asked == [seeds]


def test_new_case_fails_until_filled(tmp_path):
    shutil.copy2(REPO / "cases" / "fields.yaml", tmp_path / "fields.yaml")
    root = new_case("retail/shelf_planner", tmp_path)
    problems = validate_case(root)
    assert {"case.yaml", "case.py", "README.md", "locales/en/request.md"} <= {p.split(":")[0] for p in problems
                                                                            if "TODO left" in p}
    assert "locales/en/targets.yaml: TODO left on line 1, 4" in problems     # the id TODO_target, then its text


def test_rule_number_the_texts_never_state(tmp_path):
    root = _copy(tmp_path, FAST)
    path = root / "case.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("racks hold 120", "racks hold 93"), encoding="utf-8")
    warnings = check_case(root).warnings
    assert any("van_capacity" in w and "says 93" in w for w in warnings)
    assert not any("says 120" in w for w in check_case(_copy(tmp_path / "b", FAST)).warnings)   # 120 is in vans.csv
