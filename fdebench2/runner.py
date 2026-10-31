"""Run one (variant × agent) and score it; expand experiment grids."""

from __future__ import annotations

import hashlib
import importlib.metadata
import itertools
import json
import os
import shutil
import socket
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .agents.base import AgentResult, RunContext
from .agents.cli import CLIAgent
from .agents.reference import ReferenceAgent
from . import program
from .cases import Case, discover
from .llm import ModelRegistry, Usage
from .mcp_bridge import CLIENT_USAGE
from .prompts import render_task_prompt
from .sandbox import DockerSandbox, LocalSandbox, host_user, sanitize, stage, unstage
from .scoring.clarify import score_clarification
from .scoring.extract import collect, read_notes
from .scoring.policy_score import apply_policy, facts_from_transcript
from .session import Session, read_transcript
from .transforms.language import Translator
from .transforms.policy import load_policy
from .transforms.variant import Variant, VariantSpec, build_variant, load_engagement

REPO = Path(__file__).resolve().parents[1]
CLI_HARNESSES = ("claude_code", "codex", "gemini", "opencode")
# How a run ended. The last two say nothing about the agent: reports list them apart from the score means,
# and a campaign runs them again instead of reusing the result.
STATUSES = ("ok", "invalid", "agent_error", "timeout", "extract_failed", "harness_error", "infra_error")
NOT_SCORED = ("harness_error", "infra_error")
CASE_DOCS = {"README.md", "REVIEW.md", "explainer.html"}    # case files that never reach a run


@dataclass
class AgentSpec:
    harness: str            # reference | claude_code | codex | gemini | opencode
    model: str              # endpoint name (reference) or the CLI's model id
    max_steps: int = 400
    extra_args: list[str] = field(default_factory=list)
    env: list[str] | None = None    # CLI harnesses: host variables passed into the container (default: the
                                    # harness's own API key and base URL, agents.cli.HARNESS_ENV)

    @property
    def label(self) -> str:
        return f"{self.harness}--{self.model.replace('/', '_')}"


@dataclass
class Settings:
    cases_root: Path
    models: Path
    out: Path
    # {kind: local} or {kind: docker, image, cpus, memory, user}; user: `docker run --user` (default: this
    # host user, so the host can sanitize and clean up the workspace; "" for rootless docker).
    sandbox: dict[str, Any] = field(default_factory=lambda: {"kind": "local"})
    cache: Path = REPO / ".cache"
    # "strict": every run in a docker sandbox, so the agent can see only /workspace (its request and data,
    # the same in every difficulty and rule seed) and never the cases, other settings or the run directory.
    # "off": local sandbox allowed (development and tests).
    isolation: str = "off"


class RunLocked(RuntimeError):
    """Another worker is running this run right now."""


def framework_version() -> str:
    try:
        return importlib.metadata.version("fdebench2")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def tree_hash(root: Path, skip: set[str] = frozenset()) -> str:
    """sha256 over every file under root (relative path, size, content), except __pycache__ and `skip`."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and "__pycache__" not in rel.parts and rel.as_posix() not in skip:
            h.update(f"{rel.as_posix()}\0{p.stat().st_size}\0".encode())
            h.update(p.read_bytes())
    return h.hexdigest()


@contextmanager
def claim(run_dir: Path):
    """Hold an exclusive lock on `<run_dir>.lock` while a run is in progress, so that no two workers, threads
    or processes, run the same key at once. The lock is the OS's (flock): it ends with the process holding it,
    so a worker that died never leaves a lock behind that someone would have to judge stale."""
    import fcntl

    lock = run_dir.with_name(run_dir.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    while True:
        fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise RunLocked(f"{run_dir.name} is being run by another worker (lock: {lock})") from None
        try:
            if os.path.samestat(os.fstat(fd), os.stat(lock)):
                break
        except FileNotFoundError:
            pass
        os.close(fd)                        # the last holder removed the file as we opened it: lock the new one
    os.ftruncate(fd, 0)                     # who holds it, for people
    os.write(fd, json.dumps({"host": socket.gethostname(), "pid": os.getpid(), "started_at": time.time()}).encode())
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)
        os.close(fd)


def run_status(agent_status: str, extraction: dict[str, Any], valid: bool) -> str:
    """One of STATUSES for a run that was scored."""
    if agent_status in NOT_SCORED:
        return agent_status
    if agent_status == "error":
        return "agent_error"
    if agent_status == "out_of_time":
        return "timeout"
    if extraction.get("method") == "none" or (extraction.get("method") == "extractor" and not extraction.get("files")):
        return "extract_failed"
    return "ok" if valid else "invalid"


def _names(role: Any) -> list[str]:
    return [] if role is None else [role] if isinstance(role, str) else list(role)


class Bench:
    def __init__(self, settings: Settings, registry: ModelRegistry | None = None):
        self.s = settings
        self.cases: dict[str, Case] = discover(settings.cases_root)
        if registry is None:
            registry = ModelRegistry.load(settings.models) if settings.models.is_file() else ModelRegistry({}, {})
        self.registry = registry
        self._case_hashes: dict[str, str] = {}

    # ── preparation ─────────────────────────────────────────────────────────
    def translator(self) -> Translator:
        model = self.registry.role("translator") if "translator" in self.registry.roles else None
        return Translator(model, self.s.cache / "translations")

    def run_dir(self, spec: VariantSpec, agent: AgentSpec) -> Path:
        return self.s.out / agent.label / spec.key()

    def resolve(self, spec: VariantSpec) -> VariantSpec:
        """The spec with the rule seed it runs on: the case's first public rule seed when it names none, and none
        for a case without settings, so that a run key always says which ground truth was scored."""
        case = self.cases.get(spec.case_id)
        if case is None:
            return spec
        seed = (case.rule_seeds[0] if spec.rule_seed is None else spec.rule_seed) if case.tiers else None
        return spec if seed == spec.rule_seed else VariantSpec(**{**asdict(spec), "rule_seed": seed})

    def prepare(self, spec: VariantSpec, run_dir: Path) -> Variant:
        spec = self.resolve(spec)
        case = self.cases[spec.case_id]
        workspace = run_dir / "workspace"
        variant = build_variant(spec, case, workspace, self.translator())
        variant.save(run_dir / "variant")
        return variant

    def fingerprint(self, spec: VariantSpec, agent: AgentSpec) -> str:
        """What a stored result depends on besides its run key: the case's files, the policy and engagement,
        the model configurations, the agent and sandbox settings and the framework version."""
        if spec.case_id not in self._case_hashes:
            self._case_hashes[spec.case_id] = tree_hash(self.cases[spec.case_id].root, CASE_DOCS)
        reg = self.registry
        names = {n for role in reg.roles.values() for n in _names(role)}
        if agent.harness == "reference":
            names.add(agent.model)
        endpoints = {n: {k: v for k, v in asdict(reg.endpoints[n]).items() if not k.startswith("usd_")}
                     for n in sorted(names) if n in reg.endpoints}       # prices change costs, not runs
        doc = {"case": self._case_hashes[spec.case_id], "policy": asdict(load_policy(spec.policy)),
               "engagement": asdict(load_engagement(spec.engagement)), "roles": reg.roles, "endpoints": endpoints,
               "agent": asdict(agent), "sandbox": self.s.sandbox, "isolation": self.s.isolation,
               "framework": framework_version()}
        return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def _image(self, case_id: str) -> str:
        return self.s.sandbox["image"].format(case=case_id.replace("/", "-"))

    def _sandbox(self, case_id: str, workspace: Path):
        sb = self.s.sandbox
        if sb.get("kind", "local") == "docker":
            # The container mounts a copy at a random path: a bind mount's host path is visible inside it
            # (/proc/self/mountinfo), and the run directory's name encodes the setting.
            return DockerSandbox(stage(workspace), image=self._image(case_id), cpus=sb.get("cpus"),
                                 memory=sb.get("memory"), user=sb.get("user", host_user()))
        if self.s.isolation == "strict":
            raise RuntimeError("isolation: strict needs a docker sandbox (sandbox: {kind: docker, image: ...})")
        return LocalSandbox(workspace)

    def _configure_programs(self, case_id: str) -> None:
        """Program deliverables run where the agent ran: in the same image under a docker sandbox."""
        if self.s.sandbox.get("kind", "local") == "docker":
            program.configure("docker", self._image(case_id))
        else:
            program.configure("local")

    def _agent(self, agent: AgentSpec):
        if agent.harness == "reference":
            return ReferenceAgent(self.registry.get(agent.model), max_steps=agent.max_steps)
        if agent.harness in CLI_HARNESSES:
            return CLIAgent(agent.harness, agent.model, agent.extra_args, env=agent.env)
        raise ValueError(f"unknown harness {agent.harness!r}")

    # ── one run ─────────────────────────────────────────────────────────────
    def run(self, spec: VariantSpec, agent: AgentSpec, force: bool = False) -> dict[str, Any]:
        """Run and score, or return the stored result if it is current. Raises RunLocked if another worker
        is running the same key."""
        spec = self.resolve(spec)
        run_dir = self.run_dir(spec, agent)
        fp = self.fingerprint(spec, agent)
        if not force and (done := self._cached(run_dir, fp)) is not None:
            return done
        with claim(run_dir):
            if not force and (done := self._cached(run_dir, fp)) is not None:
                return done                 # finished by another worker in the meantime
            if run_dir.exists():
                shutil.rmtree(run_dir)
            run_dir.mkdir(parents=True)
            try:
                rec = self._run_agent(spec, agent, run_dir, fp)
                if rec["status"] in NOT_SCORED:
                    return self._unscored(run_dir, spec, agent, fp, rec["status"], rec["detail"], rec)
                return self.score(run_dir, agent)
            except Exception as e:
                detail = {"error": repr(e), "traceback": traceback.format_exc()[-4000:]}
                return self._unscored(run_dir, spec, agent, fp, "infra_error", detail)

    def _cached(self, run_dir: Path, fp: str) -> dict[str, Any] | None:
        """The stored result, unless it is missing, stale (another fingerprint) or an error worth retrying."""
        try:
            result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if result.get("fingerprint") != fp or result.get("status") in NOT_SCORED:
            return None
        return result

    def _run_agent(self, spec: VariantSpec, agent: AgentSpec, run_dir: Path, fp: str) -> dict[str, Any]:
        """Prepare the variant, run the agent in its sandbox, sanitize what it left; returns agent_result.json."""
        variant = self.prepare(spec, run_dir)
        workspace = run_dir / "workspace"
        data_files = sorted(p.relative_to(workspace).as_posix() for p in (workspace / "data").rglob("*") if p.is_file())
        needs_client = variant.can_ask or variant.can_request_exceptions
        customer = self.registry.role("customer") if needs_client else None
        sandbox = self._sandbox(spec.case_id, workspace)
        live = sandbox.workspace            # what the agent and the client channel work on during the run
        started = time.time()
        session = Session(variant, run_dir, live, customer, use_steps=agent.harness == "reference",
                          started_at=started)
        try:                                # from here on, a staged copy always goes back in place
            (run_dir / "session.json").write_text(json.dumps({
                "workspace": str(live.resolve()), "models_config": str(self.s.models.resolve()),
                "started_at": started, "agent": asdict(agent), "fingerprint": fp}), encoding="utf-8")
            system, user = render_task_prompt(variant, sandbox.workdir_label, data_files)
            (run_dir / "prompt.md").write_text(f"{system}\n\n---\n\n{user}", encoding="utf-8")
            sandbox.start()
            result = self._agent(agent).run(RunContext(variant, session, sandbox, live, run_dir, system, user))
        except Exception as e:
            result = AgentResult("infra_error", detail={"error": repr(e), "traceback": traceback.format_exc()[-4000:]})
        finally:
            sandbox.stop()
            removed = sanitize(live)        # before anything reads what the agent left
            if live != workspace:
                unstage(live, workspace)
        wall = time.time() - started
        endpoint = self.registry.endpoints.get(agent.model) if agent.harness == "reference" else None
        client_usage = run_dir / CLIENT_USAGE       # written by the bridge process (CLI harnesses)
        agent_record = {"status": result.status, "summary": result.summary, "steps": result.steps,
                        "usage": result.usage.to_dict() if agent.harness == "reference" else None,
                        "cost_usd": endpoint.cost_usd(result.usage) if endpoint else None,
                        "wall_seconds": round(wall, 1), "detail": result.detail,
                        "customer_usage": (json.loads(client_usage.read_text(encoding="utf-8"))
                                           if client_usage.is_file() else
                                           session.customer.usage.to_dict() if session.customer else None),
                        "sanitized": removed[:200]}
        (run_dir / "agent_result.json").write_text(json.dumps(agent_record, ensure_ascii=False, indent=2),
                                                   encoding="utf-8")
        return agent_record

    def _unscored(self, run_dir: Path, spec: VariantSpec, agent: AgentSpec, fp: str, status: str,
                  detail: dict[str, Any], rec: dict[str, Any] | None = None) -> dict[str, Any]:
        """result.json of a run that could not be scored (a harness or infrastructure failure)."""
        result = {"spec": asdict(spec), "agent": asdict(agent), "key": spec.key(), "status": status,
                  **self._setting_fields(spec), "error": str(detail.get("error", ""))[:2000], "detail": detail,
                  "agent_run": rec, "score": None, "fingerprint": fp}
        (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                                             encoding="utf-8")
        return result

    def _setting_fields(self, spec: VariantSpec) -> dict[str, Any]:
        """{tier, rule_seed, params} of the setting a spec runs in (params: the drawn values); {} when the case
        has no settings or cannot be set up (the run's error says why)."""
        try:
            case = self.cases[spec.case_id].at(spec.difficulty, spec.rule_seed)
        except Exception:
            return {}
        if case.setting is None:
            return {}
        return {"tier": case.tier, "rule_seed": case.rule_seed, "params": case.drawn_params}

    # ── scoring (re-runnable, and re-scorable under other policies) ─────────
    def score(self, run_dir: Path, agent: AgentSpec, extra_policies: list[str] = ()) -> dict[str, Any]:
        variant = Variant.load(run_dir / "variant")
        case = (self.cases[variant.spec.case_id].with_world_seed(getattr(variant, "world_seed", None))
                .at(variant.case_tier, variant.rule_seed))
        if variant.params and variant.params != case.drawn_params:
            # The case's candidates changed since the run (or it was converted from rule sets): the client
            # answered from other parameters than the ones the evaluator would use now.
            raise ValueError(f"{case.id}: rule seed {variant.rule_seed} now draws {case.drawn_params}, but the run "
                             f"was set up with {variant.params}; run it again instead of re-scoring it")
        workspace = run_dir / "workspace"
        rec = json.loads((run_dir / "agent_result.json").read_text(encoding="utf-8"))
        meta = json.loads((run_dir / "session.json").read_text(encoding="utf-8"))
        self._configure_programs(case.id)

        sub_dir = run_dir / "submission"
        ext_path = run_dir / "extraction.json"
        if ext_path.is_file():
            extraction = json.loads(ext_path.read_text(encoding="utf-8"))
        else:
            extractor = self.registry.role("extractor") if "extractor" in self.registry.roles else None
            try:
                extraction = collect(case, workspace, sub_dir, extractor)
            except OSError as e:            # the agent's files could not be read: its own failure
                extraction = {"method": "none", "error": repr(e)}
            ext_path.write_text(json.dumps(extraction, ensure_ascii=False, indent=2), encoding="utf-8")
        raw = case.evaluate(sub_dir, variant.customer_locale)

        transcript = read_transcript(run_dir)
        asks = [r["questions"] for r in transcript if r["kind"] == "ask"]
        answers = [r.get("answer", "") for r in transcript if r["kind"] == "ask"]
        clar_path = run_dir / "clarify.json"
        if clar_path.is_file():
            clar = json.loads(clar_path.read_text(encoding="utf-8"))
        elif variant.can_ask:
            clar = score_clarification(variant.targets, asks, self.registry.judges(), answers=answers).to_dict()
            clar_path.write_text(json.dumps(clar, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            clar = None

        notes = read_notes(workspace)
        usage = rec.get("usage") or {}
        facts = facts_from_transcript(transcript, notes, usage.get("total_tokens"), rec.get("cost_usd"),
                                      rec["wall_seconds"], observable_writes=agent.harness == "reference")

        def under(policy):
            return apply_policy(policy, raw, facts, case=case, submission_dir=sub_dir,
                                clarification_f1=clar["ask_f1"] if clar else None, can_ask=variant.can_ask,
                                customer_locale=variant.customer_locale, agent_locale=variant.agent_locale)

        score = under(variant.policy)
        result = {
            "spec": asdict(variant.spec),
            "agent": asdict(agent),
            "key": variant.spec.key(),
            "status": run_status(rec["status"], extraction, score["gates"]["validity"]),
            # the setting scored: its tier, rule seed and the parameters that seed drew (absent without settings)
            **({"tier": case.tier, "rule_seed": case.rule_seed, "params": case.drawn_params}
               if case.setting is not None else {}),
            "condition": variant.condition,
            "agent_run": rec,
            "extraction": extraction,
            "evaluator": raw,
            "clarification": clar,
            "events_fired": [r["id"] for r in transcript if r["kind"] == "event"],
            "score": score,
            "rescored": {p: under(load_policy(p))["final"] for p in extra_policies},
            "usage": self._usage(rec, extraction, clar),
            "eval_models": self.registry.fingerprint(),
            "fingerprint": meta.get("fingerprint"),
        }
        (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                                             encoding="utf-8")
        return result

    def _usage(self, rec: dict[str, Any], extraction: dict[str, Any], clar: dict[str, Any] | None) -> dict[str, Any]:
        """Tokens and dollars of the run's model calls: solver, client, extractor and judges."""
        roles = self.registry.roles
        parts = {"agent": rec.get("usage"), "client": rec.get("customer_usage"),
                 "extractor": extraction.get("usage"), "judges": (clar or {}).get("usage")}
        cost = {"agent": rec.get("cost_usd"),
                "client": self._price(_names(roles.get("customer")), parts["client"]),
                "extractor": self._price(_names(roles.get("extractor")), parts["extractor"]),
                "judges": self._price(_names(roles.get("judges")), parts["judges"])}
        known = [c for c in cost.values() if c is not None]
        return {**parts, "cost_usd_by_role": cost,
                "total_tokens": sum(u.get("total_tokens", 0) for u in parts.values() if u),
                "cost_usd": sum(known) if known else None,
                "unpriced": [k for k, u in parts.items() if u and u.get("total_tokens") and cost[k] is None],
                "unmeasured": [] if parts["agent"] is not None else ["agent"]}   # CLI logs are not parsed yet

    def _price(self, names: list[str], usage: dict[str, Any] | None) -> float | None:
        """Cost of `usage` shared evenly by the endpoints `names` (a judge panel sees the same prompts)."""
        endpoints = [self.registry.endpoints.get(n) for n in names]
        if not usage or not endpoints or None in endpoints:
            return None
        share = Usage(usage["prompt_tokens"] / len(endpoints), usage["completion_tokens"] / len(endpoints))
        costs = [e.cost_usd(share) for e in endpoints]
        return None if None in costs else sum(costs)


# ── experiment grids ─────────────────────────────────────────────────────────

AXES = ("customer_locale", "agent_locale", "policy", "difficulty", "engagement", "condition", "world_seed")
BASELINE = {"customer_locale": "en", "agent_locale": "en", "policy": "baseline", "difficulty": "medium",
            "engagement": "standard", "condition": None, "world_seed": None}
PUBLIC = "public"       # rule_seeds: public = each case's public panel (case.yaml rule_seeds)


def rule_seed_list(value: Any, where: str) -> list[int | None]:
    """A campaign's `rule_seeds:` as grid values: "public" -> [None] (expand() runs each case's public panel),
    a list of ints (or one int) -> those rule seeds (private seeds: any int not in a case's panel)."""
    from .cases import as_rule_seed
    if value is None or value == PUBLIC:
        return [None]
    values = value if isinstance(value, list) else [value]
    try:
        seeds = [as_rule_seed(v) for v in values]
    except TypeError as e:
        raise ValueError(f"{where}: rule_seeds must be 'public' or a list of ints ({e})") from None
    if not seeds:
        raise ValueError(f"{where}: rule_seeds is empty")
    return list(dict.fromkeys(seeds))


def load_campaign(path: Path) -> tuple[Settings, list[AgentSpec], list[tuple[str, VariantSpec]], dict[str, Any]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    d = doc.get("defaults", {})
    settings = Settings(cases_root=Path(d.get("cases_root", "cases")),
                        models=Path(d["models"]), out=Path(d.get("out", "runs")),
                        sandbox=d.get("sandbox", {"kind": "local"}), isolation=d.get("isolation", "strict"))
    if "env" in settings.sandbox:
        print("note: sandbox.env is no longer read: a CLI harness gets only its own API key and base URL "
              "(agents.cli.HARNESS_ENV); set env on the agent to pass others", file=sys.stderr)
    agents = [AgentSpec(**a) for a in doc.get("agents", [])]
    labels = [a.label for a in agents]
    if len(set(labels)) < len(labels):
        raise ValueError(f"agents must differ in harness or model, they would share run directories: {labels}")
    subsets = doc.get("subsets", {})
    # noise_seeds seed the engagement (data noise, events); "seeds" is their older name. trials repeat every
    # variant unchanged, for pass^k.
    noise_seeds = d.get("noise_seeds", d.get("seeds", [0]))
    trials = int(d.get("trials", 1))
    if "ruleset" in d or any("ruleset" in (exp or {}) for exp in (doc.get("experiments") or {}).values()):
        raise ValueError("ruleset is replaced by rule_seeds: 'public' (each case's public panel, the default) or a "
                         "list of ints (private rule seeds)")
    # rule_seeds: "public" (default) runs every rule seed of each case's public panel, so a (case, difficulty)
    # cell is the mean over its ground truths; a list of ints runs those seeds instead (private draws).
    default_rule_seeds = rule_seed_list(d.get("rule_seeds", PUBLIC), "defaults")
    jobs: list[tuple[str, VariantSpec]] = []
    seen: set[str] = set()
    for exp_name, exp in (doc.get("experiments") or {}).items():
        exp = dict(exp or {})
        cases = exp.pop("cases", d.get("cases", "all"))
        rule_seeds = (rule_seed_list(exp.pop("rule_seeds"), f"experiment {exp_name}") if "rule_seeds" in exp
                      else default_rule_seeds)
        unknown = set(exp) - set(AXES)
        if unknown:
            raise ValueError(f"experiment {exp_name}: unknown axes {unknown}")
        # defaults.world_seeds: run every experiment on these generated worlds (private seeds keep scores
        # independent of the public dataset/); None = the case's own seed.
        grid = {ax: exp.get(ax, d.get("world_seeds", [None]) if ax == "world_seed" else [BASELINE[ax]])
                for ax in AXES}
        grid["rule_seed"] = rule_seeds
        for combo in itertools.product(*grid.values()):
            values = dict(zip(grid, combo))
            for case_id in _case_list(cases, subsets):
                for noise_seed in noise_seeds:
                    for trial in range(trials):
                        spec = VariantSpec(case_id=case_id, noise_seed=noise_seed, trial=trial, **values)
                        if spec.key() not in seen:
                            seen.add(spec.key())
                            jobs.append((exp_name, spec))
    return settings, agents, jobs, doc


def _case_list(cases: Any, subsets: dict[str, list[str]]) -> list[str]:
    """"all", "field:<field>", a subset name, or a list of "<field>/<role>" ids (expanded per run)."""
    if cases == "all":
        return ["__ALL__"]
    if isinstance(cases, str) and cases.startswith("field:"):
        return [f"__FIELD__:{cases.split(':', 1)[1]}"]
    if isinstance(cases, str):
        return subsets[cases]
    return list(cases)


def expand(bench: Bench, agents: list[AgentSpec],
           jobs: list[tuple[str, VariantSpec]]) -> list[tuple[AgentSpec, VariantSpec]]:
    """Every (agent, run) of a campaign, each scheduled once even if several experiments contain it."""
    runs: dict[tuple[str, str], tuple[AgentSpec, VariantSpec]] = {}
    for agent in agents:
        for _, spec in jobs:
            if spec.case_id == "__ALL__":
                ids = list(bench.cases)
            elif spec.case_id.startswith("__FIELD__:"):
                field = spec.case_id.split(":", 1)[1]
                ids = [cid for cid in bench.cases if cid.startswith(field + "/")]
            else:
                ids = [spec.case_id]
            for cid in ids:
                for seed in case_rule_seeds(bench.cases[cid], spec.rule_seed):
                    run = VariantSpec(**{**asdict(spec), "case_id": cid, "rule_seed": seed})
                    runs.setdefault((agent.label, run.key()), (agent, run))
    return list(runs.values())


def case_rule_seeds(case: Case, rule_seed: int | None) -> list[int | None]:
    """The rule seeds a job runs on one case: its public panel for None ("public"), else that seed; [None] for a
    case without settings (it runs once)."""
    if not case.tiers:
        return [None]
    if rule_seed is None:
        return list(case.rule_seeds)
    try:
        case.at(None, rule_seed)
    except KeyError as e:          # a case that still declares the deprecated rulesets: has no private seeds
        raise ValueError(f"rule seed {rule_seed}: {e.args[0] if e.args else e}") from None
    return [rule_seed]


def run_campaign(path: Path, dry_run: bool = False, concurrency: int = 4) -> list[dict[str, Any]]:
    settings, agents, jobs, _ = load_campaign(path)
    bench = Bench(settings)
    expanded = expand(bench, agents, jobs)
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
                final = f" final={r['score']['final']:.3f}" if r.get("score") else ""
                print(f"done {agent.label} {spec.key()} {r['status']}{final}")
                results.append(r)
            except RunLocked as e:
                print(f"SKIPPED {agent.label} {spec.key()}: {e}")
            except Exception as e:
                print(f"FAILED {agent.label} {spec.key()}: {e!r}")
    return results
