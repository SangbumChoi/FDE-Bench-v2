"""Taking part: `fdebench2 try` (no model), `fdebench2 submit` (a campaign as one submission) and the leaderboard."""

import json
import re
import time
from dataclasses import asdict

import pytest

from fdebench2.cases import NativeCase
from fdebench2.cli import main
from fdebench2.leaderboard import build_page, load_submissions, ordered
from fdebench2.site import build_site
from fdebench2.submit import FORMAT, anchor_submission, build_submission, load_submission, write_submission
from fdebench2.transforms.variant import VariantSpec
from fdebench2.tryout import DEFAULT_CASE

from conftest import REPO

CASES = REPO / "cases"
PUBLIC = NativeCase(CASES / DEFAULT_CASE).rule_seeds        # the default case's public panel


def _try(capsys, *args: str) -> str:
    main(["try", "--cases", str(CASES), *args])
    return capsys.readouterr().out


def _row(text: str, label: str) -> list[str]:
    line = next(line for line in text.splitlines() if line.strip().startswith(label))
    return line.strip()[len(label):].split()


# ── try ──────────────────────────────────────────────────────────────────────

def test_try_explains_the_default_case_and_scores_its_anchors(capsys):
    started = time.time()
    text = _try(capsys)
    assert time.time() - started < 30
    case = NativeCase(CASES / DEFAULT_CASE).at("medium", None)
    assert text.startswith(f"FDE-Bench v2 · {DEFAULT_CASE} · ")
    assert f"Setting: medium, rule seed {PUBLIC[0]} (public) · language: en" in text
    for heading in ("What the AI is asked", "The files it gets (5, in data/)", "What only the client knows",
                    "Score scale", "Scores in this setting"):
        assert f"\n{heading}\n" in text, heading
    assert "data/price_forecast.csv" in text
    flat = " ".join(text.split())                       # the prose is wrapped
    assert f"{len(case.targets('en'))} facts only the client knows" in flat
    assert f"{len(case.rules().rules)} rules" in flat
    assert "quality / 1.5" in flat and "The reference earns 0.667" in flat and "Ask-F1 is 0" in flat
    # valid, normalized quality, final under the default policy
    assert _row(text, "Literal solution (the request done as written)") == ["no", "–", "0.000"]
    assert _row(text, "Baseline (the client's own way)") == ["yes", "0.000", "0.000"]
    assert _row(text, "Reference solution") == ["yes", "1.000", "0.667"]
    assert "fdebench2 try --submission DIR" in flat and "Your submission" not in text


def test_try_in_another_language_tier_and_private_seed(capsys):
    text = _try(capsys, "--lang", "ko", "--difficulty", "hard", "--rule-seed", "4242")
    assert "설정: hard, 규칙 시드 4242 (비공개) · 언어: ko" in text
    assert "\nAI가 받는 요청\n" in text and "\n점수 척도\n" in text and "data/가격예측.csv" in text
    assert _row(text, "모범 답안 (1점 기준)") == ["예", "1.000", "0.667"]
    with pytest.raises(SystemExit):
        main(["try", "--cases", str(CASES), "--case", "no/such_case"])


def test_try_scores_a_submission_folder(capsys, tmp_path):
    case = NativeCase(CASES / DEFAULT_CASE).at("medium", None)
    good, bad, empty = tmp_path / "good", tmp_path / "bad", tmp_path / "empty"
    for folder in (good / "nested", bad, empty):
        folder.mkdir(parents=True)
    case.write_reference(good / "nested")               # found where a run would find it
    (good / "NOTES.md").write_text("How the plan was made, for the client.", encoding="utf-8")
    case.write_literal(bad)

    text = _try(capsys, "--submission", str(good))
    assert _row(text, "Your submission ") == ["yes", "1.000", "0.667"]
    assert f"Your submission: {good}" in text and "Objective " in text and "quality 1.000" in " ".join(text.split())
    assert "Rules broken" not in text

    text = _try(capsys, "--submission", str(bad))
    assert _row(text, "Your submission ") == ["no", "–", "0.000"]
    n = int(re.search(r"Rules broken \((\d+)\):", text).group(1))
    assert n > 0 and "    - " in text

    text = _try(capsys, "--submission", str(empty))
    assert _row(text, "Your submission ") == ["no", "–", "0.000"]
    assert "Missing files: dispatch.csv." in " ".join(text.split())


# ── submit ───────────────────────────────────────────────────────────────────

def _result(seed, trial, final, valid, model="m", status=None, ask=0.5, cost=0.02, enforced=(True, False)):
    spec = VariantSpec(DEFAULT_CASE, rule_seed=seed, trial=trial)
    targets = {f"t{i}": {"revealed": True, "learned": i == 0, "enforced": e} for i, e in enumerate(enforced)}
    score = None if final is None else {"final": final, "gates": {"validity": valid},
                                        "components": {"quality": final}, "quality_raw": final * 1.5}
    return {"spec": asdict(spec), "agent": {"harness": "reference", "model": model, "max_steps": 400},
            "key": spec.key(), "status": status or ("ok" if valid else "invalid"), "tier": "medium",
            "rule_seed": seed, "score": score, "clarification": {"ask_f1": ask}, "targets": targets,
            "usage": {"total_tokens": 1000, "cost_usd": cost}, "fingerprint": "abc", "error": ""}


def _runs(tmp_path, results) -> object:
    out = tmp_path / "runs"
    for r in results:
        d = out / f"reference--{r['agent']['model']}" / r["key"]
        d.mkdir(parents=True)
        (d / "result.json").write_text(json.dumps(r), encoding="utf-8")
    return out


def test_submit_packages_a_campaign(tmp_path, capsys):
    seeds = (90001, 90002)
    results = [_result(s, t, final, final > 0) for s, finals in zip(seeds, ((0.6, 0.4, 0.0), (0.5, 0.5, 0.5)))
               for t, final in enumerate(finals)]
    results.append(_result(90001, 3, None, False, status="infra_error"))
    runs = _runs(tmp_path, results)
    out = tmp_path / "submission.json"
    main(["submit", str(runs), "--name", "My system", "--model", "m-2026", "--flag", "web_tools=off",
          "--version", "1.0", "--date", "2026-11-06", "--cases", str(CASES), "--out", str(out)])
    printed = capsys.readouterr().out
    assert str(out) in printed and "My system: 6 scored runs on 1 cases, final 0.417" in printed
    doc = load_submission(out)
    assert doc["format"] == FORMAT and doc["kind"] == "system" and doc["example"] is False
    assert doc["system"] == {"name": "My system", "model": "m-2026", "harness": "reference", "version": "1.0",
                             "agent_label": "reference--m", "max_steps": 400, "flags": {"web_tools": "off"},
                             "date": "2026-11-06"}
    bench = doc["benchmark"]
    assert re.fullmatch(r"[0-9a-f]{40}", bench["git_commit"]) and list(bench["cases"]) == [DEFAULT_CASE]
    assert re.fullmatch(r"[0-9a-f]{64}", bench["cases"][DEFAULT_CASE])
    assert doc["seeds"] == {"kind": "private", "public": [], "private": [90001, 90002]}
    assert doc["trials"] == 3 and doc["status"] == "ranked" and doc["status_reasons"] == []
    agg = doc["aggregate"]
    assert (agg["n_runs"], agg["n_scored"], agg["n_cases"]) == (7, 6, 1)
    assert agg["statuses"] == {"infra_error": 1, "invalid": 1, "ok": 5}
    # case-macro: seed 90001 mean 1/3, seed 90002 mean 0.5 -> 0.41667; one case, so the interval is a point
    assert agg["final"] == {"mean": 0.416667, "ci": [0.416667, 0.416667], "n_cases": 1}
    assert agg["validity"]["mean"] == pytest.approx((2 / 3 + 1) / 2, abs=1e-6)
    assert agg["ask_f1"]["mean"] == 0.5 and agg["enforced_share"]["mean"] == 0.5 and agg["cost_usd"]["mean"] == 0.02
    run = doc["runs"][0]
    assert {k: run[k] for k in ("case", "tier", "rule_seed", "seeds", "trial", "status", "final", "valid")} == \
        {"case": DEFAULT_CASE, "tier": "medium", "rule_seed": 90001, "seeds": "private", "trial": 0,
         "status": "ok", "final": 0.6, "valid": True}
    assert run["targets"] == {"n": 2, "revealed": 2, "revealed_measured": 2, "learned": 1, "learned_measured": 2,
                              "enforced": 1, "enforced_measured": 2}
    unscored = next(x for x in doc["runs"] if x["status"] == "infra_error")
    assert unscored["final"] is None and unscored["cost_usd"] is None


def test_submit_marks_public_seeds_and_few_trials_as_development(tmp_path):
    runs = _runs(tmp_path, [_result(PUBLIC[0], 0, 0.6, True), _result(90001, 0, 0.5, True)])
    doc = build_submission(runs, name="dev", date="2026-11-06", cases_root=CASES)
    assert doc["status"] == "development" and doc["seeds"]["kind"] == "mixed"
    assert doc["seeds"]["public"] == [PUBLIC[0]] and doc["seeds"]["private"] == [90001]
    assert any("public rule seeds" in r for r in doc["status_reasons"])
    assert any("fewer than 3" in r for r in doc["status_reasons"])
    # several agents in one folder: pick one
    two = _runs(tmp_path / "two", [_result(90001, 0, 0.5, True, model="a"), _result(90001, 0, 0.4, True, model="b")])
    with pytest.raises(ValueError, match="several agents"):
        build_submission(two, name="x", cases_root=CASES)
    assert build_submission(two, name="x", agent="reference--b", cases_root=CASES)["aggregate"]["final"]["mean"] == 0.4


# ── leaderboard ──────────────────────────────────────────────────────────────

def _submission(name, final, status, ci=(0.0, 1.0)):
    agg = {"n_runs": 9, "n_scored": 9, "n_cases": 3, "statuses": {"ok": 9},
           "final": {"mean": final, "ci": list(ci), "n_cases": 3}, "validity": {"mean": 0.9, "ci": [0, 1]},
           "quality": {"mean": 0.8, "ci": [0, 1]}, "ask_f1": {"mean": 0.55, "ci": [0, 1]},
           "enforced_share": {"mean": 0.7, "ci": [0, 1]}, "cost_usd": {"mean": 1.25, "ci": [0, 1]},
           "total_tokens": {"mean": 1000, "ci": [0, 1]}}
    return {"format": FORMAT, "kind": "system", "example": False, "status": status, "aggregate": agg,
            "system": {"name": name, "model": f"{name}-model", "harness": "reference", "version": ""}}


def test_the_leaderboard_ranks_private_submissions_and_shows_anchors(tmp_path):
    anchors = anchor_submission(CASES, [DEFAULT_CASE], ["medium"], date="2026-11-06")
    assert anchors["kind"] == "anchors" and anchors["example"] is True and anchors["status"] == "anchor"
    assert {k: v["final"]["mean"] for k, v in anchors["anchors"].items()} == \
        {"literal": 0.0, "baseline": 0.0, "reference": 0.666667}
    assert len(anchors["runs"]) == 3 * len(PUBLIC) and anchors["seeds"]["kind"] == "public"
    folder = tmp_path / "leaderboard"
    for name, doc in {"a.json": _submission("alpha", 0.41, "ranked"), "b.json": _submission("beta", 0.52, "ranked"),
                      "c.json": _submission("gamma", 0.90, "development"), "EXAMPLE-anchors.json": anchors}.items():
        write_submission(doc, folder / name)
    (folder / "broken.json").write_text("{}", encoding="utf-8")
    subs = load_submissions(folder)
    assert [f for f, _ in subs] == ["EXAMPLE-anchors.json", "a.json", "b.json", "c.json"]   # broken.json skipped
    assert [(rank, s["system"]["name"]) for rank, _, s in ordered(subs)] == \
        [("1", "beta"), ("2", "alpha"), (None, "gamma")]

    html = build_page("en", subs)
    heads = re.findall(r"<th>(.*?)</th>", html)
    assert heads == ["Rank", "System", "Model", "Harness", "Final [95% CI]", "Validity", "Quality", "Ask-F1",
                     "Enforced share", "Cost/run", "Status"]
    rows = re.findall(r"<tr>(.*?)</tr>", html.split("<tbody>")[1])
    cells = [re.findall(r"<td[^>]*>(.*?)</td>", r) for r in rows]
    assert cells[0][0] == "1" and "beta" in cells[0][1] and cells[0][2:] == [
        "beta-model", "reference", "0.520 [0.00–1.00]", "0.90", "0.800", "0.55", "0.70", "$1.25", "ranked"]
    assert cells[2][0] == "–" and "gamma" in cells[2][1] and cells[2][-1] == "development"
    assert "Reference rows (anchors, not models)" in html
    anchor_rows = cells[3:]                            # after the group row, which has a class
    assert [r[-1] for r in anchor_rows] == ["anchor"] * 3 and all("EXAMPLE" in r[1] for r in anchor_rows)
    assert "Reference solution" in anchor_rows[2][1] and anchor_rows[2][4] == "0.667 [0.67–0.67]"
    ko = build_page("ko", subs)
    assert "<h1>리더보드</h1>" in ko and "<th>순위</th>" in ko and "0.520 [0.00–1.00]" in ko


def test_build_site_writes_the_leaderboard_in_every_language(tmp_path):
    from fdebench2.explain import LANGS
    out = tmp_path / "site"
    build_site(REPO, out, github="https://github.com/example/FDE-Bench-v2", ref="main")
    en = (out / "leaderboard.html").read_text(encoding="utf-8")
    assert "<h1>Leaderboard</h1>" in en and "EXAMPLE" in en and "Reference solution" in en
    assert 'href="https://github.com/example/FDE-Bench-v2/tree/main/docs/SUBMITTING.md"' in en
    assert 'href="https://github.com/example/FDE-Bench-v2/tree/main/leaderboard/EXAMPLE-anchors.json"' in en
    assert 'href="ko/leaderboard.html"' in en                            # the language switcher
    for lang in LANGS[1:]:
        page = (out / lang / "leaderboard.html").read_text(encoding="utf-8")
        assert f'<html lang="{lang}">' in page and 'href="../leaderboard.html"' in page
    # every page's navigation reaches the leaderboard in its language
    home = (out / "index.html").read_text(encoding="utf-8")
    assert '<a href="leaderboard.html">Leaderboard</a>' in home
    assert '<a href="../ko/leaderboard.html">리더보드</a>' in (out / "ko" / "index.html").read_text(encoding="utf-8")
