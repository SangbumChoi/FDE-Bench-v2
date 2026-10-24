"""Compose the three axes over one v1 case into a concrete, saved variant."""

from __future__ import annotations

import json
import random
import shutil
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from ..cases import Target, V1Case
from . import noise as noise_ops
from .events import Event, build_events
from .language import Translator, check_locale, resolve
from .policy import Policy, load_policy, render_policy_brief

DIFFICULTY_FILE = Path(__file__).resolve().parents[2] / "configs" / "difficulty.yaml"
CONDITIONS = ("full", "interact", "interact_req", "hidden")


@dataclass(frozen=True)
class VariantSpec:
    case_id: str
    customer_locale: str = "source"   # "source" = the case's own language (zh for v1)
    agent_locale: str = "en"          # v1's agent prompt is English
    policy: str = "v1_default"
    difficulty: str = "medium"
    seed: int = 0
    condition: str | None = None      # override the difficulty's condition (ablations)

    def key(self) -> str:
        """Run-directory name; equal for specs that denote the same variant (e.g. "source" and "zh")."""
        parts = [self.case_id, f"c-{resolve(self.customer_locale)}", f"a-{self.agent_locale}", f"p-{self.policy}",
                 f"d-{self.difficulty}"]
        if self.condition:
            parts.append(f"x-{self.condition}")
        return "__".join(parts) + f"__s{self.seed}"


@dataclass
class Difficulty:
    name: str
    condition: str
    persona: str
    noise: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    time_budget_s: float = 43200
    max_question_rounds: int = 30


def load_difficulty(name: str, path: Path = DIFFICULTY_FILE) -> Difficulty:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if name not in doc:
        raise KeyError(f"unknown difficulty {name!r}; defined: {sorted(doc)}")
    return Difficulty(name=name, **doc[name])


@dataclass
class Variant:
    spec: VariantSpec
    condition: str
    persona: str
    customer_locale: str
    agent_locale: str
    instruction: str
    information: str            # hidden from the agent unless condition == full
    targets: list[Target]
    policy: Policy
    policy_brief: str           # in agent locale; "" when the policy is not agent-visible
    events: list[Event]
    noise: list[dict[str, Any]]
    time_budget_s: float
    max_question_rounds: int
    submission_files: list[str]

    @property
    def can_ask(self) -> bool:
        return self.condition in ("interact", "interact_req")

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        doc = asdict(self)
        doc["spec"] = asdict(self.spec)
        (directory / "variant.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, directory: Path) -> "Variant":
        doc = json.loads((directory / "variant.json").read_text(encoding="utf-8"))
        doc["spec"] = VariantSpec(**doc["spec"])
        doc["targets"] = [Target(**t) for t in doc["targets"]]
        doc["policy"] = Policy.from_dict(doc["policy"])
        doc["events"] = [Event(**e) for e in doc["events"]]
        return cls(**doc)


def _copy_data(case: V1Case, workspace: Path) -> None:
    dest = workspace / "data"
    if dest.exists():
        shutil.rmtree(dest)
    if case.data_dir.is_dir():
        shutil.copytree(case.data_dir, dest)
    else:
        dest.mkdir(parents=True)


def build_variant(spec: VariantSpec, case: V1Case, workspace: Path, translator: Translator) -> Variant:
    """Materialize `spec`: write the agent's data copy into `workspace/data` and return the variant.

    Nothing under the v1 case directory is modified.
    """
    cust = check_locale(spec.customer_locale)
    agent = check_locale(spec.agent_locale)
    diff = load_difficulty(spec.difficulty)
    condition = spec.condition or diff.condition
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}")
    policy = load_policy(spec.policy)
    rng = random.Random(f"{spec.case_id}|{spec.difficulty}|{spec.seed}")

    def tr(text: str, kind: str = "document", src: str = "zh") -> str:
        return translator.translate(text, cust, src=src, kind=kind)

    workspace.mkdir(parents=True, exist_ok=True)
    _copy_data(case, workspace)

    # Language: request, hidden requirements, clarification targets.
    instruction = tr(case.instruction, "request")
    information = tr(case.information, "requirements")
    targets = [replace(t, text=tr(t.source_text, "target")) for t in case.targets]

    # Difficulty: data noise (agent's copy only) and the facts that undo it.
    extra_facts: list[str] = []
    applied: list[dict[str, Any]] = []
    for op in diff.noise:
        result = noise_ops.OPS[op](workspace, rng)
        if result is None:
            continue
        applied.append(asdict(result))
        extra_facts.append(result.knowledge)
        if result.target:
            targets.append(Target(id=f"v2·{op}", text=tr(result.target, "target", src="en"),
                                  source_text=result.target, kind="noise", domain="data quality", origin=op))

    correction = None
    if any(e["kind"] == "data_correction" for e in diff.events):
        held = noise_ops.corrupt_for_correction(workspace, rng)
        if held is not None:
            rel, _ = held
            correction = (rel, f"inbox/{Path(rel).name}")

    events, event_facts = build_events(diff.events, rng, volunteer_facts=[t.text for t in targets if t.origin == "v1"],
                                       correction=correction, time_budget_s=diff.time_budget_s)
    for ev in events:
        ev.message = tr(ev.message, "event", src="en")
        if "fact" in ev.payload:
            ev.message = f"{ev.message} {ev.payload['fact']}"
    extra_facts += event_facts

    if extra_facts:
        header = tr("Additional facts (known to the client)", "heading", src="en")
        information += f"\n\n## {header}\n\n" + "\n".join(f"- {tr(f, 'fact', src='en')}" for f in extra_facts)

    brief = ""
    if policy.agent_visible:
        brief = translator.translate(render_policy_brief(policy), agent, src="en", kind="policy")

    return Variant(
        spec=spec, condition=condition, persona=diff.persona, customer_locale=cust, agent_locale=agent,
        instruction=instruction, information=information, targets=targets, policy=policy, policy_brief=brief,
        events=events, noise=applied, time_budget_s=diff.time_budget_s,
        max_question_rounds=diff.max_question_rounds, submission_files=case.submission_files,
    )
