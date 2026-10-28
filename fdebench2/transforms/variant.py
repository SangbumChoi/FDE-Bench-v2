"""Compose the three axes over one case into a concrete, saved variant."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from .. import i18n
from ..cases import DEFAULT_RULESET, TIERS, Case, NotLocalized, Target
from . import noise as noise_ops
from .events import Event, build_events
from .language import Translator, check_locale
from .policy import Policy, load_policy, policy_brief_msgs

ENGAGEMENT_FILE = Path(__file__).resolve().parents[2] / "configs" / "engagement.yaml"
CONDITIONS = ("full", "interact", "interact_req", "hidden")


@dataclass(frozen=True)
class VariantSpec:
    case_id: str
    customer_locale: str = "en"
    agent_locale: str = "en"
    policy: str = "baseline"
    difficulty: str = "medium"        # content tier of cases that declare settings
    noise_seed: int = 0               # seeds the engagement: its data noise and events
    condition: str | None = None      # override the engagement's condition (ablations)
    ruleset: str = DEFAULT_RULESET    # rule parameters of cases that declare settings (A / B / C)
    engagement: str = "standard"      # how the work is handed over (configs/engagement.yaml)
    world_seed: int | None = None     # generate the case's world from this seed instead of its public one
    trial: int = 0                    # repeat index (pass^k): changes nothing in the variant

    @property
    def seed(self) -> int:
        """The older name of noise_seed."""
        return self.noise_seed

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VariantSpec":
        d = dict(d)
        if "seed" in d:                   # saved before noise_seed and trial were split
            d.setdefault("noise_seed", d.pop("seed"))
        return cls(**d)

    def key(self) -> str:
        """Run-directory name (outside the agent's sandbox: the agent never sees it).

        Trial 0 keeps the name runs had before trials existed.
        """
        parts = [self.case_id, f"c-{self.customer_locale}", f"a-{self.agent_locale}", f"p-{self.policy}",
                 f"d-{self.difficulty}", f"r-{self.ruleset}", f"e-{self.engagement}"]
        if self.condition:
            parts.append(f"x-{self.condition}")
        if self.world_seed is not None:
            parts.append(f"w-{self.world_seed}")
        return "__".join(parts) + f"__s{self.noise_seed}" + (f"__t{self.trial}" if self.trial else "")


@dataclass
class Engagement:
    name: str
    condition: str
    persona: str
    noise: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    time_budget_s: float = 43200
    max_question_rounds: int = 30


def load_engagement(name: str, path: Path = ENGAGEMENT_FILE) -> Engagement:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if name not in doc:
        raise KeyError(f"unknown engagement {name!r}; defined: {sorted(doc)}")
    return Engagement(name=name, **doc[name])


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
    case_tier: str | None = None      # the content tier the case was scored at (None: no settings)
    ruleset: str | None = None        # the rule set the case was scored at (None: no settings)
    world_seed: int | None = None     # the world the case was built from (None: its public seed)
    rules: list[dict[str, str]] = field(default_factory=list)   # the setting's rules {id, class, description};
                                                                 # never shown to the agent: exception requests are
                                                                 # mapped to one of them

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
        doc["spec"] = VariantSpec.from_dict(doc["spec"])
        doc["targets"] = [Target(**t) for t in doc["targets"]]
        doc["policy"] = Policy.from_dict(doc["policy"])
        doc["events"] = [Event(**e) for e in doc["events"]]
        return cls(**doc)


def build_variant(spec: VariantSpec, case: Case, workspace: Path, translator: Translator) -> Variant:
    """Materialize `spec`: write the agent's data into `workspace/data` and return the variant.

    Texts come from the case in the customer locale. Only when a case lacks that
    locale are they machine-translated at run time.
    Nothing in the case directory is modified.
    """
    cust = check_locale(spec.customer_locale)
    agent = check_locale(spec.agent_locale)
    if spec.difficulty not in TIERS:
        raise ValueError(f"unknown difficulty {spec.difficulty!r}; one of {TIERS}")
    eng = load_engagement(spec.engagement)
    condition = spec.condition or eng.condition
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}")
    policy = load_policy(spec.policy)
    case = case.with_world_seed(spec.world_seed).at(spec.difficulty, spec.ruleset)
    # Nothing the agent sees may depend on the difficulty or the rule set: noise and events are
    # seeded by the engagement only.
    rng = random.Random(f"{spec.case_id}|{spec.engagement}|{spec.noise_seed}")
    src = case.source_locale

    def text(getter, kind: str) -> str:
        try:
            return getter(cust)
        except NotLocalized:
            return translator.translate(getter(src), cust, src=src, kind=kind)

    def say(message: Any, lang: str = cust) -> str:
        return i18n.render(message, lang, fallback=lambda t: translator.translate(t, lang, src="en", kind="message"))

    workspace.mkdir(parents=True, exist_ok=True)
    case.materialize_data(cust, workspace / "data")

    # Language: request, hidden requirements, clarification targets.
    instruction = text(case.request, "request")
    information = text(case.requirements, "requirements")
    try:
        targets = case.targets(cust)
    except NotLocalized:
        targets = [replace(t, text=translator.translate(t.source_text, cust, src=src, kind="target"))
                   for t in case.targets(src)]

    # Engagement: data noise (agent's copy only) and the facts that undo it.
    extra_facts: list[Any] = []
    applied: list[dict[str, Any]] = []
    for op in eng.noise:
        result = noise_ops.OPS[op](workspace, rng, cust)
        if result is None:
            continue
        applied.append(asdict(result))
        extra_facts.append(result.knowledge)
        if result.target:
            targets.append(Target(id=f"v2·{op}", text=say(result.target), source_text=say(result.target, "en"),
                                  kind="noise", domain="data quality", origin=op))

    correction = None
    if any(e["kind"] == "data_correction" for e in eng.events):
        held = noise_ops.corrupt_for_correction(workspace, rng)
        if held is not None:
            rel, _ = held
            correction = (rel, f"inbox/{Path(rel).name}")

    events, event_facts = build_events(eng.events, rng, volunteer_facts=[t.text for t in targets if t.origin == "case"],
                                       correction=correction, time_budget_s=eng.time_budget_s)
    for ev in events:
        ev.message = say(ev.payload.pop("msg"))
        if "fact" in ev.payload:
            ev.message = f"{ev.message} {ev.payload['fact']}"
    extra_facts += event_facts

    if extra_facts:
        header = say({"t": "Additional facts (known to the client)"})
        information += f"\n\n## {header}\n\n" + "\n".join(f"- {say(f)}" for f in extra_facts)

    brief = ""
    if policy.agent_visible:
        title, *lines = policy_brief_msgs(policy)
        brief = f"# {say(title, agent)}\n\n" + "\n".join(
            say(m, agent) if i == 0 else f"- {say(m, agent)}" for i, m in enumerate(lines)) + "\n"

    return Variant(
        spec=spec, condition=condition, persona=eng.persona, customer_locale=cust, agent_locale=agent,
        instruction=instruction, information=information, targets=targets, policy=policy, policy_brief=brief,
        events=events, noise=applied, time_budget_s=eng.time_budget_s,
        max_question_rounds=eng.max_question_rounds, submission_files=case.submission_files,
        case_tier=getattr(case, "tier", None), ruleset=getattr(case, "ruleset", None), world_seed=spec.world_seed,
        rules=[{"id": r.id, "class": r.rule_class, "description": r.description}
               for r in (case.rules().rules if case.rules() is not None else [])],
    )
