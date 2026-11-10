"""The command line itself: every command that needs no model starts and prints what it should."""

from pathlib import Path

import pytest

from fdebench2.cli import main

REPO = Path(__file__).resolve().parents[1]


def run(capsys, *argv: str) -> str:
    main(list(argv))
    return capsys.readouterr().out


def test_report_runs_from_the_command_line(tmp_path, capsys, monkeypatch):
    # `report` once crashed here: the audit command's own report() shadowed the campaign report inside main()
    monkeypatch.chdir(REPO)
    assert run(capsys, "report", str(tmp_path)).strip() == "no results"


def test_listing_commands(capsys, monkeypatch):
    monkeypatch.chdir(REPO)
    cases = run(capsys, "cases")
    assert len(cases.strip().splitlines()) == 13 and "manufacturing/procurement_specialist" in cases
    assert "baseline" in run(capsys, "policies")


def test_the_starter_campaign_is_nine_runs(capsys, monkeypatch):
    monkeypatch.chdir(REPO)
    out = run(capsys, "campaign", "configs/experiments.starter.yaml", "--dry-run")
    assert out.strip().splitlines()[-1] == "# 9 runs"
    assert all("__d-medium__" in line for line in out.strip().splitlines()[:-1])


@pytest.mark.parametrize("command", ["validate-case", "export-dataset", "audit-case", "explain-case", "new-case",
                                     "build-site", "prepare", "run", "score", "campaign", "report", "try", "submit",
                                     "anchors"])
def test_every_command_has_help(command, capsys):
    with pytest.raises(SystemExit) as stop:
        main([command, "--help"])
    assert stop.value.code == 0 and "usage:" in capsys.readouterr().out
