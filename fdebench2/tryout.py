"""`fdebench2 try`: one case in plain words and its anchors scored, with no model and no API key.

It prints, in the chosen language (the UI catalog prompts/explainer.yaml, keys try_*): what the AI is asked, the
files it gets, how many facts only the client knows, and the score scale; then it scores the case's literal
solution, baseline and reference in that setting (and, with --submission, the user's own deliverable folder) the
way a run is scored under the default policy. Interaction is scored as in an offline submission: the client was
reachable (the standard engagement) but nothing was asked, so Ask-F1 is 0; NOTES.md counts when the folder has
one; no budget was measured. The default policy weighs quality only, so the final score is quality / cap.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import program
from .cases import NativeCase
from .dataset import DATASET_DIR
from .explain import UI, case_summary, case_texts
from .scoring.extract import collect, read_notes
from .scoring.policy_score import RunFacts, apply_policy
from .transforms.policy import Policy, load_policy

DEFAULT_CASE = "energy_utilities/battery_dispatch_operator"   # the smallest data and the fastest to score
DEFAULT_POLICY = "baseline"
ANCHORS = ("literal", "baseline", "reference")
WIDTH = 100
NO_LINE_START = "，。、；：！？）」』】》,.;:!?)"     # punctuation that stays at the end of the line before


def say(_lang: str, key: str, **values: Any) -> str:
    """Interface text (prompts/explainer.yaml) as plain text, `{name}` filled in."""
    text = UI[_lang][key]
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


@dataclass
class Scored:
    """One deliverable scored offline in a setting."""

    valid: bool
    quality: float | None             # normalized quality (baseline 0, reference 1), None when invalid
    final: float                      # composite score under the policy
    score: dict[str, Any]             # apply_policy's result
    evaluation: dict[str, Any]        # the case's evaluate() result
    collected: dict[str, Any] = field(default_factory=dict)   # how the files were found (a user's folder)

    @property
    def violations(self) -> list[dict[str, str]]:
        return self.evaluation.get("violations") or []


def score_offline(case: NativeCase, sub_dir: Path, lang: str, policy: Policy, diagnose: bool = False,
                  notes: str = "") -> Scored:
    """Score the deliverable in `sub_dir` (already in the evaluator's format) as an offline submission."""
    raw = case.evaluate(sub_dir, lang, diagnose=diagnose)
    score = apply_policy(policy, raw, RunFacts(notes=notes), case=case, submission_dir=sub_dir,
                         clarification_f1=0.0, can_ask=True, customer_locale=lang, agent_locale=lang)
    valid = bool(score["gates"]["validity"])
    return Scored(valid, score["quality_raw"] if valid else None, score["final"], score, raw)


def anchor_writers(case: NativeCase) -> dict[str, Callable[[Path], None]]:
    """The case's anchors that exist: literal solution, baseline and reference."""
    have = {"literal": hasattr(case.module, "literal_solution"),
            "baseline": hasattr(case.module, "baseline_solution"), "reference": True}
    write = {"literal": case.write_literal, "baseline": case.write_baseline, "reference": case.write_reference}
    return {name: write[name] for name in ANCHORS if have[name]}


def score_anchor(case: NativeCase, name: str, lang: str, policy: Policy, diagnose: bool = False) -> Scored:
    with tempfile.TemporaryDirectory() as tmp:
        anchor_writers(case)[name](Path(tmp))
        return score_offline(case, Path(tmp), lang, policy, diagnose=diagnose)


def score_folder(case: NativeCase, folder: Path, lang: str, policy: Policy) -> Scored:
    """A user's deliverable folder: its files are collected as a run's would be (without an extractor model, so
    they must carry the names the evaluator reads), then scored offline."""
    with tempfile.TemporaryDirectory() as tmp:
        sub = Path(tmp) / "submission"
        collected = collect(case, folder, sub, None)
        scored = score_offline(case, sub, lang, policy, notes=read_notes(folder))
        scored.collected = collected
        return scored


def _size(n: int) -> str:
    return f"{n} B" if n < 1024 else f"{n / 1024:.1f} KB" if n < 1024 ** 2 else f"{n / 1024 ** 2:.1f} MB"


def agent_files(case: NativeCase, lang: str) -> list[tuple[str, int]]:
    """(name, bytes) of every data file the agent gets in `lang`: the stored dataset/agent_view/<lang>/, else
    generated."""
    stored = case.root / DATASET_DIR / "agent_view" / lang
    if stored.is_dir():
        return [(p.relative_to(stored).as_posix(), p.stat().st_size) for p in sorted(stored.rglob("*")) if p.is_file()]
    with tempfile.TemporaryDirectory() as tmp:
        case.materialize_data(lang, Path(tmp))
        return [(p.relative_to(tmp).as_posix(), p.stat().st_size) for p in sorted(Path(tmp).rglob("*")) if p.is_file()]


def _wrap(text: str, indent: str = "  ", hang: str = "") -> str:
    """`text` wrapped at WIDTH terminal columns, every line indented; `hang` indents the lines after the first some
    more. Lines break at spaces, and also between wide Chinese and Japanese characters."""
    out = []
    for par in str(text).split("\n"):
        words = " ".join(par.split())
        if not words:
            continue
        line, room = indent, WIDTH - _width(indent)
        cut = -1                                    # where the current line may break: after a space or wide char
        for ch in words:
            w = _width(ch)
            if w > room and line.strip() and ch not in NO_LINE_START:
                head, tail = (line[:cut], line[cut:]) if cut > len(indent) else (line, "")
                out.append(head.rstrip())
                line = indent + hang + tail.lstrip()
                room = WIDTH - _width(line)
                cut = -1
                if ch == " " and not tail.strip():
                    continue
            line += ch
            room -= w
            if ch == " " or (w == 2 and not _hangul(ch)):     # Korean breaks between words only
                cut = len(line)
        out.append(line.rstrip())
    return "\n".join(out)


def _hangul(ch: str) -> bool:
    return "\uac00" <= ch <= "\ud7a3" or "\u1100" <= ch <= "\u11ff" or "\u3130" <= ch <= "\u318f"


def _num(x: float | None) -> str:
    return "–" if x is None else f"{x:.3f}"


def _table(rows: list[list[str]]) -> str:
    widths = [max(_width(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = ["  " + "  ".join(c + " " * (w - _width(c)) for c, w in zip(r, widths)).rstrip() for r in rows]
    lines.insert(1, "  " + "  ".join("-" * w for w in widths))
    return "\n".join(lines)


def _width(text: str) -> int:
    """Display width in a terminal: East Asian wide characters take two columns."""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def try_case(cases_root: Path, case_id: str = DEFAULT_CASE, difficulty: str = "medium", rule_seed: int | None = None,
             lang: str = "en", submission: Path | None = None, policy_name: str = DEFAULT_POLICY) -> str:
    """The text `fdebench2 try` prints."""
    root = Path(cases_root) / case_id
    if not (root / "case.yaml").is_file():
        raise SystemExit(f"no case {case_id!r} under {cases_root} (fdebench2 cases lists them)")
    base = NativeCase(root)
    case = base.at(difficulty, rule_seed) if base.tiers else base
    program.configure("local")
    policy = load_policy(policy_name)
    t = lambda key, **kw: say(lang, key, **kw)  # noqa: E731
    out: list[str] = []

    role = case_texts(root, lang).get("role") or case.role
    out.append(f"FDE-Bench v2 · {case.id} · {role}")
    if case.tiers:
        kind = t("try_public") if case.rule_seed in case.rule_seeds else t("try_private")
        out.append(t("try_setting", tier=case.tier, seed=case.rule_seed, kind=kind, lang=lang))
    else:
        out.append(t("try_no_settings", lang=lang))

    summary = case_summary(root, lang) or {}
    out += ["", t("try_asked"), _wrap(summary.get("task") or case.request(lang))]

    files = agent_files(case, lang)
    out += ["", t("try_files", n=len(files))]
    width = max((_width(name) for name, _ in files), default=0)
    out += [f"  data/{name}{' ' * (width - _width(name))}  {_size(size):>9}" for name, size in files]

    out += ["", t("try_facts_title"), _wrap(t("try_facts", n=len(case.targets(lang)))),
            _wrap(t("try_rules", n=len(case.rules().rules)))]

    cap = case.quality_cap if case.quality_cap is not None else policy.quality_cap
    out += ["", t("try_scale")] + [_wrap("- " + line, hang="  ") for line in (
        t("try_scale_invalid"), t("try_scale_quality"),
        t("try_scale_final", policy=policy.id, cap=f"{cap:g}", ref=f"{min(1.0, 1 / cap):.3f}"),
        t("try_scale_offline"))]

    rows = [[t("try_col_deliverable"), t("try_col_valid"), t("try_col_quality"), t("try_col_final")]]
    scored: dict[str, Scored] = {name: score_anchor(case, name, lang, policy) for name in anchor_writers(case)}
    mine = score_folder(case, Path(submission), lang, policy) if submission is not None else None
    for name, s in [*scored.items(), *([("yours", mine)] if mine else [])]:
        rows.append([t(f"try_{name}"), t("answer_yes") if s.valid else t("answer_no"), _num(s.quality),
                     f"{s.final:.3f}"])
    out += ["", t("try_scores"), _table(rows)]

    if mine is not None:
        out += ["", t("try_yours_title", path=submission)]
        if mine.collected.get("method") == "none":
            out.append(_wrap(t("try_missing", files=", ".join(mine.collected.get("missing") or []),
                               expected=", ".join(case.submission_files))))
        if "fatal" in mine.evaluation.get("error_info", {}):
            out.append(_wrap(t("try_fatal", error=mine.evaluation["error_info"]["fatal"][:300])))
        if mine.violations:
            out.append("  " + t("try_violations", n=len(mine.violations)))
            out += [_wrap(f"- {v['rule']}: {v['message']}", "    ", "  ") for v in mine.violations[:12]]
            if len(mine.violations) > 12:
                out.append("    " + t("try_more", n=len(mine.violations) - 12))
        if mine.valid:
            ev = mine.evaluation
            out.append(_wrap(t("try_objective", obj=_g(ev.get("objective")), ref=_g(ev.get("reference_objective")),
                               base=_g(ev.get("baseline_objective")), quality=_num(mine.quality))))
    else:
        out += ["", _wrap(t("try_next"), "")]
    return "\n".join(out) + "\n"


def _g(x: Any) -> str:
    return "–" if x is None else f"{x:,.6g}" if isinstance(x, (int, float)) else str(x)
