"""fdebench2 command line.

  fdebench2 validate-case cases/<id> ...                  check native cases against the case contract
  fdebench2 export-dataset cases/<id> ...                 write each case's data and ground truth to dataset/
  fdebench2 explain-case cases/<id> ...                   write each case's explainer.html
  fdebench2 new-case <field>/<role> [--program]          skeleton of a new case with settings
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
    ap.add_argument("--difficulty", default="medium", help="content tier: easy | medium | hard")
    ap.add_argument("--ruleset", default="A", help="rule parameters of cases with settings: A | B | C")
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


def _spec(a) -> VariantSpec:
    return VariantSpec(case_id=a.case, customer_locale=a.customer_locale, agent_locale=a.agent_locale,
                       policy=a.policy, difficulty=a.difficulty, noise_seed=a.noise_seed, condition=a.condition,
                       ruleset=a.ruleset, engagement=a.engagement, world_seed=a.world_seed, trial=a.trial)


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
    p = sub.add_parser("export-dataset")
    p.add_argument("paths", type=Path, nargs="+", help="case directories under cases/")
    p = sub.add_parser("new-case")
    p.add_argument("case_id", help="<field>/<role>")
    p.add_argument("--program", action="store_true", help="the deliverable is a program, not files")
    p.add_argument("--cases", dest="cases_root", type=Path, default=Path("cases"))
    p = sub.add_parser("explain-case")
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
    elif a.cmd == "new-case":
        from .scaffold import new_case
        print(new_case(a.case_id, a.cases_root, kind="program" if a.program else "batch"))
    elif a.cmd == "explain-case":
        from .explain import write_index, write_page
        for path in a.paths:
            print(write_page(path))
        print(write_index(a.paths[0].resolve().parent.parent))
    elif a.cmd == "policies":
        print("\n".join(list_policies()))
    elif a.cmd == "cases":
        for cid, case in _bench(a).cases.items():
            print(f"{cid}\t{case.role}\t{case.task_type}\t{','.join(case.locales())}"
                  f"\t{'settings=' + ','.join(case.tiers) + ' x ' + ','.join(case.rulesets) if case.tiers else ''}")
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


if __name__ == "__main__":
    main()
