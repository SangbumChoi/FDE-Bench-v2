"""fdebench2 command line.

  fdebench2 fetch-v1  [--case ID ...]                    download FDE-Bench v1 (optional, external) into external/fde-bench-v1
  fdebench2 cases                                        list cases
  fdebench2 prepare   --case ID [axes]                   materialize a variant, print the agent prompt
  fdebench2 run       --case ID --harness reference --model gpt [axes]
  fdebench2 score     RUN_DIR [--policy P ...]           (re)score a run, optionally under more policies
  fdebench2 campaign  configs/experiments.yaml [--dry-run]
  fdebench2 report    runs/
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from .runner import AgentSpec, Bench, Settings, run_campaign
from .scoring.report import report
from .transforms.policy import list_policies
from .transforms.variant import VariantSpec


def _axes(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--case", required=True)
    ap.add_argument("--customer-locale", default="en")
    ap.add_argument("--agent-locale", default="en")
    ap.add_argument("--policy", default="baseline")
    ap.add_argument("--difficulty", default="medium")
    ap.add_argument("--condition", default=None)
    ap.add_argument("--seed", type=int, default=0)


def _common(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--cases", dest="cases_root", type=Path, default=Path("cases"))
    ap.add_argument("--v1", dest="v1_root", type=Path, default=None,
                    help="also load external FDE-Bench v1 cases from here (see fetch-v1)")
    ap.add_argument("--models", type=Path, default=Path("configs/models.yaml"))
    ap.add_argument("--out", type=Path, default=Path("runs"))
    ap.add_argument("--docker-image", help="run commands in this image (use {case} for per-case images)")


def _spec(a) -> VariantSpec:
    return VariantSpec(case_id=a.case, customer_locale=a.customer_locale, agent_locale=a.agent_locale,
                       policy=a.policy, difficulty=a.difficulty, seed=a.seed, condition=a.condition)


def _bench(a) -> Bench:
    sandbox = {"kind": "docker", "image": a.docker_image} if a.docker_image else {"kind": "local"}
    return Bench(Settings(cases_root=a.cases_root, v1_root=a.v1_root, models=a.models, out=a.out, sandbox=sandbox))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="fdebench2")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fetch-v1"); _common(p)
    p.add_argument("--case", action="append", help="only these cases (repeatable); default all")
    p.add_argument("--check", action="store_true", help="only verify checksums")
    p = sub.add_parser("validate-case")
    p.add_argument("paths", type=Path, nargs="+", help="case directories under cases/")
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

    a = ap.parse_args(argv)
    if a.cmd == "fetch-v1":
        from .v1_fetch import check, fetch
        root = a.v1_root or Path("external/fde-bench-v1")
        wanted = set(a.case) if a.case else None
        if not a.check:
            fetch(root, Path(".cache/v1-release"), wanted)
        bad = check(root, wanted)
        print("all data files verified" if not bad else f"{len(bad)} files missing or corrupt, e.g. {bad[:3]}")
        sys.exit(1 if bad else 0)
    elif a.cmd == "validate-case":
        from .validate import validate_case
        failed = 0
        for path in a.paths:
            problems = validate_case(path)
            failed += bool(problems)
            print(f"{path.name}: " + ("OK" if not problems else "\n  - " + "\n  - ".join(problems)))
        sys.exit(1 if failed else 0)
    elif a.cmd == "policies":
        print("\n".join(list_policies()))
    elif a.cmd == "cases":
        for cid, case in _bench(a).cases.items():
            print(f"{cid}\t{case.task_type}\t{case.domain}\t{','.join(case.locales())}")
    elif a.cmd == "prepare":
        bench = _bench(a)
        run_dir = Path(tempfile.mkdtemp(prefix="fdeb2-prepare-"))
        variant = bench.prepare(_spec(a), run_dir)
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
        result = bench.run(_spec(a), agent, force=a.force)
        print(json.dumps(result["score"], ensure_ascii=False, indent=2))
    elif a.cmd == "score":
        bench = _bench(a)
        meta = json.loads((a.run_dir / "session.json").read_text(encoding="utf-8"))
        result = bench.score(a.run_dir, AgentSpec(**meta["agent"]), extra_policies=a.policy)
        print(json.dumps({"score": result["score"], "rescored": result["rescored"]}, ensure_ascii=False, indent=2))
    elif a.cmd == "campaign":
        run_campaign(a.config, dry_run=a.dry_run, concurrency=a.concurrency)
    elif a.cmd == "report":
        print(report(a.out))


if __name__ == "__main__":
    main()
