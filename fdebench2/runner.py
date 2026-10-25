"""Run one (variant × agent) and score it; expand experiment grids."""

from __future__ import annotations

import itertools
import json
import shutil
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .agents.base import AgentResult, RunContext
from .agents.cli import CLIAgent
from .agents.reference import ReferenceAgent
from .cases import Case, discover
from .llm import ModelRegistry
from .prompts import render_task_prompt
from .sandbox import DockerSandbox, LocalSandbox
from .scoring.clarify import score_clarification
from .scoring.extract import collect
from .scoring.policy_score import apply_policy, facts_from_transcript
from .session import Session, read_transcript
from .transforms.language import Translator
from .transforms.policy import load_policy
from .transforms.variant import Variant, VariantSpec, build_variant

REPO = Path(__file__).resolve().parents[1]
CLI_HARNESSES = ("claude_code", "codex", "gemini", "opencode")


@dataclass
class AgentSpec:
    harness: str            # reference | claude_code | codex | gemini | opencode
    model: str              # endpoint name (reference) or the CLI's model id
    max_steps: int = 400
    extra_args: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.harness}--{self.model.replace('/', '_')}"


@dataclass
class Settings:
    cases_root: Path
    models: Path
    out: Path
    v1_root: Path | None = None       # external FDE-Bench v1 checkout (optional)
    sandbox: dict[str, Any] = field(default_factory=lambda: {"kind": "local"})
    cache: Path = REPO / ".cache"


class Bench:
    def __init__(self, settings: Settings, registry: ModelRegistry | None = None):
        self.s = settings
        self.cases: dict[str, Case] = discover(settings.cases_root, settings.v1_root)
        if registry is None:
            registry = ModelRegistry.load(settings.models) if settings.models.is_file() else ModelRegistry({}, {})
        self.registry = registry

    # ── preparation ─────────────────────────────────────────────────────────
    def translator(self) -> Translator:
        model = self.registry.role("translator") if "translator" in self.registry.roles else None
        return Translator(model, self.s.cache / "translations")

    def run_dir(self, spec: VariantSpec, agent: AgentSpec) -> Path:
        return self.s.out / agent.label / spec.key()

    def prepare(self, spec: VariantSpec, run_dir: Path) -> Variant:
        case = self.cases[spec.case_id]
        workspace = run_dir / "workspace"
        variant = build_variant(spec, case, workspace, self.translator())
        variant.save(run_dir / "variant")
        return variant

    def _sandbox(self, case_id: str, workspace: Path):
        sb = self.s.sandbox
        if sb.get("kind", "local") == "docker":
            return DockerSandbox(workspace, image=sb["image"].format(case=case_id), cpus=sb.get("cpus"),
                                 memory=sb.get("memory"))
        return LocalSandbox(workspace)

    def _agent(self, agent: AgentSpec):
        if agent.harness == "reference":
            return ReferenceAgent(self.registry.get(agent.model), max_steps=agent.max_steps)
        if agent.harness in CLI_HARNESSES:
            return CLIAgent(agent.harness, agent.model, agent.extra_args)
        raise ValueError(f"unknown harness {agent.harness!r}")

    # ── one run ─────────────────────────────────────────────────────────────
    def run(self, spec: VariantSpec, agent: AgentSpec, force: bool = False) -> dict[str, Any]:
        run_dir = self.run_dir(spec, agent)
        if (run_dir / "result.json").is_file() and not force:
            return json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
        variant = self.prepare(spec, run_dir)
        workspace = run_dir / "workspace"
        started = time.time()
        (run_dir / "session.json").write_text(json.dumps({
            "workspace": str(workspace.resolve()), "models_config": str(self.s.models.resolve()),
            "started_at": started, "agent": asdict(agent)}), encoding="utf-8")

        needs_client = variant.can_ask or variant.policy.agent_visible
        session = Session(variant, run_dir, workspace,
                          self.registry.role("customer") if needs_client else None,
                          use_steps=agent.harness == "reference", started_at=started)
        sandbox = self._sandbox(spec.case_id, workspace)
        data_files = sorted(p.relative_to(workspace).as_posix() for p in (workspace / "data").rglob("*") if p.is_file())
        system, user = render_task_prompt(variant, sandbox.workdir_label, data_files)
        (run_dir / "prompt.md").write_text(f"{system}\n\n---\n\n{user}", encoding="utf-8")
        ctx = RunContext(variant, session, sandbox, workspace, run_dir, system, user)

        try:
            sandbox.start()
            result = self._agent(agent).run(ctx)
        except Exception as e:
            result = AgentResult("error", detail={"error": repr(e), "traceback": traceback.format_exc()[-4000:]})
        finally:
            sandbox.stop()
        wall = time.time() - started
        cost = None
        if agent.harness == "reference":
            cost = self.registry.endpoints[agent.model].cost_usd(result.usage)
        agent_record = {"status": result.status, "summary": result.summary, "steps": result.steps,
                        "usage": result.usage.to_dict() if agent.harness == "reference" else None,
                        "cost_usd": cost, "wall_seconds": round(wall, 1), "detail": result.detail,
                        "customer_usage": session.customer.usage.to_dict() if session.customer else None}
        (run_dir / "agent_result.json").write_text(json.dumps(agent_record, ensure_ascii=False, indent=2),
                                                   encoding="utf-8")
        return self.score(run_dir, agent)

    # ── scoring (re-runnable, and re-scorable under other policies) ─────────
    def score(self, run_dir: Path, agent: AgentSpec, extra_policies: list[str] = ()) -> dict[str, Any]:
        variant = Variant.load(run_dir / "variant")
        case = self.cases[variant.spec.case_id]
        workspace = run_dir / "workspace"
        rec = json.loads((run_dir / "agent_result.json").read_text(encoding="utf-8"))

        sub_dir = run_dir / "submission"
        ext_path = run_dir / "extraction.json"
        if ext_path.is_file():
            extraction = json.loads(ext_path.read_text(encoding="utf-8"))
        else:
            extractor = self.registry.role("extractor") if "extractor" in self.registry.roles else None
            extraction = collect(case, workspace, sub_dir, extractor)
            ext_path.write_text(json.dumps(extraction, ensure_ascii=False, indent=2), encoding="utf-8")
        raw = case.evaluate(sub_dir, variant.customer_locale)

        transcript = read_transcript(run_dir)
        asks = [r["questions"] for r in transcript if r["kind"] == "ask"]
        clar_path = run_dir / "clarify.json"
        if clar_path.is_file():
            clar = json.loads(clar_path.read_text(encoding="utf-8"))
        elif variant.can_ask:
            clar = score_clarification(variant.targets, asks, self.registry.judges()).to_dict()
            clar_path.write_text(json.dumps(clar, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            clar = None

        notes_path = workspace / "NOTES.md"
        notes = notes_path.read_text(encoding="utf-8", errors="replace") if notes_path.is_file() else ""
        usage = rec.get("usage") or {}
        facts = facts_from_transcript(transcript, notes, usage.get("total_tokens"), rec.get("cost_usd"),
                                      rec["wall_seconds"], observable_writes=agent.harness == "reference")

        def under(policy):
            return apply_policy(policy, raw, facts, case=case, submission_dir=sub_dir,
                                clarification_f1=clar["ask_f1"] if clar else None, can_ask=variant.can_ask,
                                customer_locale=variant.customer_locale, agent_locale=variant.agent_locale)

        result = {
            "spec": asdict(variant.spec),
            "agent": asdict(agent),
            "condition": variant.condition,
            "agent_run": rec,
            "extraction": extraction,
            "evaluator": raw,
            "clarification": clar,
            "events_fired": [r["id"] for r in transcript if r["kind"] == "event"],
            "score": under(variant.policy),
            "rescored": {p: under(load_policy(p))["final"] for p in extra_policies},
            "eval_models": self.registry.fingerprint(),
        }
        (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                                             encoding="utf-8")
        return result


# ── experiment grids ─────────────────────────────────────────────────────────

AXES = ("customer_locale", "agent_locale", "policy", "difficulty", "condition")
BASELINE = {"customer_locale": "en", "agent_locale": "en", "policy": "baseline", "difficulty": "medium",
            "condition": None}


def load_campaign(path: Path) -> tuple[Settings, list[AgentSpec], list[tuple[str, VariantSpec]], dict[str, Any]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    d = doc.get("defaults", {})
    settings = Settings(cases_root=Path(d.get("cases_root", "cases")),
                        v1_root=Path(d["v1_root"]) if d.get("v1_root") else None,
                        models=Path(d["models"]), out=Path(d.get("out", "runs")),
                        sandbox=d.get("sandbox", {"kind": "local"}))
    agents = [AgentSpec(**a) for a in doc.get("agents", [])]
    subsets = doc.get("subsets", {})
    seeds = d.get("seeds", [0])
    jobs: list[tuple[str, VariantSpec]] = []
    seen: set[str] = set()
    for exp_name, exp in (doc.get("experiments") or {}).items():
        exp = dict(exp)
        cases = exp.pop("cases", d.get("cases", "all"))
        unknown = set(exp) - set(AXES)
        if unknown:
            raise ValueError(f"experiment {exp_name}: unknown axes {unknown}")
        grid = {ax: exp.get(ax, [BASELINE[ax]]) for ax in AXES}
        for combo in itertools.product(*grid.values()):
            values = dict(zip(AXES, combo))
            for case_id in _case_list(cases, subsets):
                for seed in seeds:
                    spec = VariantSpec(case_id=case_id, seed=seed, **values)
                    if spec.key() not in seen:
                        seen.add(spec.key())
                        jobs.append((exp_name, spec))
    return settings, agents, jobs, doc


def _case_list(cases: Any, subsets: dict[str, list[str]]) -> list[str]:
    if cases == "all":
        return ["__ALL__"]
    if isinstance(cases, str):
        return subsets[cases]
    return list(cases)


def run_campaign(path: Path, dry_run: bool = False, concurrency: int = 4) -> list[dict[str, Any]]:
    settings, agents, jobs, _ = load_campaign(path)
    bench = Bench(settings)
    expanded: list[tuple[AgentSpec, VariantSpec]] = []
    for agent in agents:
        for _, spec in jobs:
            ids = bench.cases if spec.case_id == "__ALL__" else [spec.case_id]
            for cid in ids:
                expanded.append((agent, VariantSpec(**{**asdict(spec), "case_id": cid})))
    if dry_run:
        for agent, spec in expanded:
            print(f"{agent.label}\t{spec.key()}")
        print(f"# {len(expanded)} runs")
        return []
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(bench.run, spec, agent): (agent, spec) for agent, spec in expanded}
        for fut in as_completed(futures):
            agent, spec = futures[fut]
            try:
                r = fut.result()
                print(f"done {agent.label} {spec.key()} final={r['score']['final']:.3f}")
                results.append(r)
            except Exception as e:
                print(f"FAILED {agent.label} {spec.key()}: {e!r}")
    return results
