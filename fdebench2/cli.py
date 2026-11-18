"""fdebench2 command line.

  fdebench2 validate-case cases/<id> ...                  check native cases against the case contract
  fdebench2 export-dataset cases/<id> ...                 write each case's data and answers to dataset/
                                                         (dataset/answer/<tier>/s<seed>/ per public setting)
  fdebench2 audit-case cases/<id> [--world-seed N]        the ground truth audit (dataset/audit.json)
  fdebench2 explain-case cases/<id> ...                   write each case's docs/<lang>/explainer.html, its index
                                                         README.md and the catalog's cases/docs/<lang>/index.html
  fdebench2 new-case <field>/<role> [--program]          skeleton of a new case with settings
  fdebench2 cases                                        list cases
  fdebench2 prepare   --case ID [axes]                   materialize a variant, print the agent prompt
  fdebench2 run       --case ID --harness reference --model gpt [axes]
  fdebench2 score     RUN_DIR [--policy P ...]           (re)score a run, optionally under more policies
  fdebench2 campaign  configs/experiments.yaml [--dry-run]
  fdebench2 report    runs/
  fdebench2 try       [--case ID] [--difficulty T] [--rule-seed N] [--lang L] [--submission DIR]
                                                         a case in plain words and its anchors scored (no model)
  fdebench2 submit    RUNS_DIR --name NAME --out submission.json   package a campaign for the leaderboard
  fdebench2 anchors   --out FILE                         the anchors (literal, baseline, reference) as a submission
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from .runner import AgentSpec, Bench, Settings, run_campaign
from .scoring.report import report
from .transforms.policy import list_policies
from .transforms.variant import VariantSpec


def _count(text: str) -> int:
    """A whole number of 0 or more (argparse type)."""
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {text!r}") from None
    if n < 0:
        raise argparse.ArgumentTypeError(f"must be 0 or more, got {n}")
    return n


def _case_paths(paths: list[Path]) -> list[Path]:
    """The case directories among `paths`. The shell's cases/*/*/ also matches the catalog's page folders
    cases/docs/<lang>/ (no case.yaml): those are skipped, with a note on stderr."""
    from .explain import DOCS_DIR
    keep = []
    for path in paths:
        if not (path / "case.yaml").is_file() and path.resolve().parent.name == DOCS_DIR:
            print(f"{path}: skipped, the catalog's pages (not a case)", file=sys.stderr)
        else:
            keep.append(path)
    return keep


def _cases_root(given: Path | None) -> Path:
    """--cases, else ./cases, else the repository's cases/ (a command run from another folder)."""
    if given is not None:
        return given
    from .runner import REPO
    return Path("cases") if Path("cases").is_dir() else REPO / "cases"


def _axes(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--case", required=True)
    ap.add_argument("--customer-locale", default="en")
    ap.add_argument("--agent-locale", default="en")
    ap.add_argument("--policy", default="baseline")
    ap.add_argument("--difficulty", default="medium", help="content tier: easy | medium | hard")
    ap.add_argument("--rule-seed", type=int, default=None,
                    help="rule seed of a case with settings: draws its rule parameters (default: the case's first "
                         "public rule seed; any other int is a private draw)")
    ap.add_argument("--engagement", default="standard", help="standard | full_spec | messy (configs/engagement.yaml)")
    ap.add_argument("--condition", default=None)
    ap.add_argument("--world-seed", type=int, default=None, help="generate the case world from this seed")
    ap.add_argument("--noise-seed", "--seed", dest="noise_seed", type=int, default=0,
                    help="seed of the engagement's data noise and events")
    ap.add_argument("--trial", type=int, default=0, help="repeat index of the same variant (for pass^k)")


def _common(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--cases", dest="cases_root", type=Path, default=Path("cases"))
    ap.add_argument("--models", type=Path, default=Path("configs/models.yaml"))
    ap.add_argument("--out", type=Path, default=Path("runs"))
    ap.add_argument("--docker-image", help="run commands in this image (use {case} for per-case images)")


def _spec(a, bench: Bench) -> VariantSpec:
    # resolve: the case's first public rule seed when none is given, none for a case without settings
    return bench.resolve(VariantSpec(case_id=a.case, customer_locale=a.customer_locale, agent_locale=a.agent_locale,
                                     policy=a.policy, difficulty=a.difficulty, noise_seed=a.noise_seed,
                                     condition=a.condition, rule_seed=a.rule_seed, engagement=a.engagement,
                                     world_seed=a.world_seed, trial=a.trial))


def _bench(a) -> Bench:
    sandbox = {"kind": "docker", "image": a.docker_image} if a.docker_image else {"kind": "local"}
    return Bench(Settings(cases_root=a.cases_root, models=a.models, out=a.out, sandbox=sandbox))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="fdebench2")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate-case")
    p.add_argument("paths", type=Path, nargs="+", help="case directories under cases/")
    p.add_argument("--world-seeds", default="1,2,3", help="also check the case on these world seeds ('' skips)")
    p.add_argument("--no-world-seeds", action="store_true", help="skip the other-world check")
    p = sub.add_parser("export-dataset", help="store each case's data and answers in dataset/ "
                                              "(dataset/answer/<tier>/s<seed>/ per public setting)")
    p.add_argument("paths", type=Path, nargs="+", help="case directories under cases/")
    p = sub.add_parser("audit-case", help="measure a case's ground truth (ablations, shortcuts, value of asking)")
    p.add_argument("path", type=Path, help="a case directory under cases/")
    p.add_argument("--world-seed", type=int, default=None, help="audit this world instead (printed, never stored)")
    p.add_argument("--combos", type=_count, default=None,
                   help="parameter combinations per tier besides the public panel (0 or more)")
    p.add_argument("--no-write", action="store_true", help="print the report without storing dataset/audit.json")
    p = sub.add_parser("new-case")
    p.add_argument("case_id", help="<field>/<role>")
    p.add_argument("--program", action="store_true", help="the deliverable is a program, not files")
    p.add_argument("--cases", dest="cases_root", type=Path, default=Path("cases"))
    p = sub.add_parser("explain-case", help="the explainer pages, the case index README.md and the catalog pages")
    p.add_argument("paths", type=Path, nargs="+", help="case directories under cases/")
    p = sub.add_parser("build-site", help="the explainers as a static site (GitHub Pages)")
    p.add_argument("--out", type=Path, default=Path("site"))
    p.add_argument("--github", default=None, help="repository URL for links into case files (default: origin)")
    p.add_argument("--ref", default=None, help="branch or tag those links point to (default: current branch)")
    p = sub.add_parser("cases"); _common(p)
    sub.add_parser("policies")
    p = sub.add_parser("prepare"); _common(p); _axes(p)
    p = sub.add_parser("run"); _common(p); _axes(p)
    p.add_argument("--harness", default="reference")
    p.add_argument("--model", required=True)
    p.add_argument("--max-steps", type=int, default=400)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("score"); _common(p)
    p.add_argument("run_dir", type=Path)
    p.add_argument("--policy", action="append", default=[], help="also score under this policy (repeatable)")
    p = sub.add_parser("campaign")
    p.add_argument("config", type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--concurrency", type=int, default=4)
    p = sub.add_parser("report")
    p.add_argument("out", type=Path)
    from .cases import LOCALES
    from .tryout import DEFAULT_CASE
    p = sub.add_parser("try", help="a case in plain words, its anchors scored; no model or API key needed")
    p.add_argument("--case", default=DEFAULT_CASE, help=f"<field>/<role> (default: {DEFAULT_CASE})")
    p.add_argument("--difficulty", default="medium", choices=("easy", "medium", "hard"))
    p.add_argument("--rule-seed", type=int, default=None, help="default: the case's first public rule seed")
    p.add_argument("--lang", default="en", choices=LOCALES)
    p.add_argument("--submission", type=Path, default=None, help="score your own deliverable folder too")
    p.add_argument("--cases", dest="cases_root", type=Path, default=None)
    p = sub.add_parser("submit", help="package a campaign's results into one submission JSON for the leaderboard")
    p.add_argument("results", type=Path, help="the campaign's results directory (runs/)")
    p.add_argument("--name", required=True, help="system name shown on the leaderboard")
    p.add_argument("--model", default=None, help="model id (default: the runs' model)")
    p.add_argument("--harness", default=None, help="harness (default: the runs' harness)")
    p.add_argument("--version", dest="system_version", default="", help="the system's own version")
    p.add_argument("--flag", action="append", default=[], metavar="KEY=VALUE",
                   help="a setting to disclose (web_tools=off, max_steps=400, budget_usd=5, ...); repeatable")
    p.add_argument("--date", default=None, help="submission date, YYYY-MM-DD (default: today, UTC)")
    p.add_argument("--agent", default=None, help="the runs' agent label (<harness>--<model>) when several ran")
    p.add_argument("--cases", dest="cases_root", type=Path, default=None)
    p.add_argument("--rounds", type=Path, default=None,
                   help="the leaderboard rounds file (default: leaderboard/rounds.yaml next to the cases folder)")
    p.add_argument("--out", type=Path, default=Path("submission.json"))
    p = sub.add_parser("anchors", help="the cases' anchors scored offline, as an example submission")
    p.add_argument("--case", action="append", default=[], help="<field>/<role> (repeatable; default: every case)")
    p.add_argument("--difficulty", action="append", default=[], choices=("easy", "medium", "hard"))
    p.add_argument("--round", dest="round_id", default=None,
                   help="score a leaderboard round's tiers and rule seeds (leaderboard/rounds.yaml), not the public ones")
    p.add_argument("--date", default=None)
    p.add_argument("--cases", dest="cases_root", type=Path, default=None)
    p.add_argument("--out", type=Path, required=True)

    a = ap.parse_args(argv)
    if a.cmd in ("validate-case", "export-dataset", "explain-case"):
        a.paths = _case_paths(a.paths)
        if not a.paths:
            ap.error(f"{a.cmd}: no case directory given")
    if a.cmd == "validate-case":
        from .validate import check_case
        failed = 0
        seeds = [] if a.no_world_seeds else [int(x) for x in a.world_seeds.split(",") if x.strip()]
        for path in a.paths:
            rep = check_case(path, world_seeds=seeds)
            failed += bool(rep.problems)
            print(f"{path.parent.name}/{path.name}: " + ("OK" if not rep.problems else "\n  - " + "\n  - ".join(rep.problems)))
            for line in [f"warning: {w}" for w in rep.warnings] + rep.notes:
                print(f"  {line}")
        sys.exit(1 if failed else 0)
    elif a.cmd == "export-dataset":
        from .dataset import export_dataset
        from .explain import write_page
        for path in a.paths:
            dest = export_dataset(path)
            write_page(path)
            n = sum(1 for f in dest.rglob("*") if f.is_file())
            print(f"{path.parent.name}/{path.name}: {n} files in {dest.relative_to(Path.cwd()) if dest.is_relative_to(Path.cwd()) else dest}")
    elif a.cmd == "audit-case":
        from .audit import AUDIT_COMBOS, audit_case, write_audit
        from .audit import report as audit_report
        from .cases import NativeCase
        from .explain import write_page
        started = time.time()
        result = audit_case(NativeCase(a.path), a.world_seed, AUDIT_COMBOS if a.combos is None else a.combos)
        print(audit_report(result))
        print(f"audited in {time.time() - started:.0f} s", file=sys.stderr)
        if a.world_seed is None and not a.no_write:      # only the public world's audit is stored
            print(write_audit(a.path, result))
            write_page(a.path)                           # the explainer shows the stored audit
    elif a.cmd == "new-case":
        from .scaffold import new_case
        print(new_case(a.case_id, a.cases_root, kind="program" if a.program else "batch"))
    elif a.cmd == "explain-case":
        from .explain import write_index, write_page
        for path in a.paths:
            print(write_page(path), "(+ zh, ko, ja, es)")
        print(write_index(a.paths[0].resolve().parent.parent), "(+ zh, ko, ja, es)")
    elif a.cmd == "build-site":
        from .site import build_site
        pages = build_site(Path("."), a.out, github=a.github, ref=a.ref)
        print(f"{len(pages)} pages in {a.out}")
    elif a.cmd == "policies":
        print("\n".join(list_policies()))
    elif a.cmd == "cases":
        for cid, case in _bench(a).cases.items():
            print(f"{cid}\t{case.role}\t{case.task_type}\t{','.join(case.locales())}"
                  f"\t{'settings=' + ','.join(case.tiers) + ' x rule seeds ' + ','.join(map(str, case.rule_seeds)) if case.tiers else ''}")
    elif a.cmd == "prepare":
        bench = _bench(a)
        run_dir = Path(tempfile.mkdtemp(prefix="fdeb2-prepare-"))
        variant = bench.prepare(_spec(a, bench), run_dir)
        from .prompts import render_task_prompt
        files = sorted(p.relative_to(run_dir / "workspace").as_posix()
                       for p in (run_dir / "workspace" / "data").rglob("*") if p.is_file())
        system, user = render_task_prompt(variant, ".", files)
        print(f"{system}\n\n{user}")
        print(f"\n# variant written to {run_dir}; {len(variant.targets)} targets, {len(variant.events)} events, "
              f"noise: {[n['op'] for n in variant.noise]}", file=sys.stderr)
    elif a.cmd == "run":
        bench = _bench(a)
        agent = AgentSpec(harness=a.harness, model=a.model, max_steps=a.max_steps)
        result = bench.run(_spec(a, bench), agent, force=a.force)
        shown = result["score"] if result.get("score") else {"status": result["status"], "error": result.get("error")}
        print(json.dumps(shown, ensure_ascii=False, indent=2))
    elif a.cmd == "score":
        bench = _bench(a)
        meta = json.loads((a.run_dir / "session.json").read_text(encoding="utf-8"))
        result = bench.score(a.run_dir, AgentSpec(**meta["agent"]), extra_policies=a.policy)
        print(json.dumps({"status": result["status"], "score": result["score"], "rescored": result["rescored"]},
                         ensure_ascii=False, indent=2))
    elif a.cmd == "campaign":
        run_campaign(a.config, dry_run=a.dry_run, concurrency=a.concurrency)
    elif a.cmd == "report":
        print(report(a.out))
    elif a.cmd == "try":
        from .tryout import try_case
        sys.stdout.write(try_case(_cases_root(a.cases_root), a.case, a.difficulty, a.rule_seed, a.lang, a.submission))
    elif a.cmd == "submit":
        from .submit import build_submission, write_submission
        doc = build_submission(a.results, name=a.name, model=a.model, harness=a.harness, version=a.system_version,
                               flags=a.flag, date=a.date, agent=a.agent, cases_root=_cases_root(a.cases_root),
                               rounds_file=a.rounds)
        print(write_submission(doc, a.out))
        agg = doc["aggregate"]
        print(f"{doc['system']['name']}: {agg['n_scored']} scored runs on {agg['n_cases']} cases, final "
              f"{agg['final']['mean']:.3f} [{agg['final']['ci'][0]:.2f}-{agg['final']['ci'][1]:.2f}], status "
              f"{doc['status']}" + (f", round {doc['round']}" if doc.get("round") else "")
              + (f" ({'; '.join(doc['status_reasons'])})" if doc["status_reasons"] else ""))
    elif a.cmd == "anchors":
        from .submit import anchor_submission, write_submission
        doc = anchor_submission(_cases_root(a.cases_root), a.case or None, a.difficulty or ["medium"], date=a.date,
                                round_id=a.round_id)
        print(write_submission(doc, a.out))


if __name__ == "__main__":
    main()
