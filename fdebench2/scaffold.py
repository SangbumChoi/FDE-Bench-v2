"""`fdebench2 new-case <field>/<role>`: the skeleton of a new case with settings.

It writes case.yaml, case.py, README.md and the five locales with every
required part in place and marked TODO, so a new role starts from the same
contract as the built ones. The skeleton does not validate until the TODOs are
filled; then `fdebench2 export-dataset` and `fdebench2 validate-case` finish it.
Built cases to copy patterns from: a batch case with settings is
`manufacturing/procurement_specialist`; daily program cases are
`finance/loan_underwriting_specialist`, `healthcare/hospital_appointment_scheduler`
and `finance/stock_trading_strategist`; a program that processes a folder is
`data_knowledge/multilingual_corpus_curator`.
"""

from __future__ import annotations

from pathlib import Path

from .cases import LOCALES, load_fields

CASE_YAML = """id: {role}
role: {title}
task_type: TODO                 # e.g. Combinatorial Optimization | Decision Program | Forecasting | Data Organization
field: {field}
seed: {seed}
objective: maximize             # or minimize; the quantity score() returns as "objective"
deliverable_type: {kind}
{deliverable}
deliverable_spec: |
  TODO: the exact format the agent must deliver (agent-visible, the same in every setting).
tiers:                          # difficulty -> which rules apply; the data is the same in every tier
  easy: TODO the core problem
  medium: TODO easy + more domain rules
  hard: TODO medium + the uncertain or adversarial parts
rulesets:                       # the client's rule parameters; include at least one non-nested one
  A: {{example_param: 1}}
  B: {{example_param: 2}}
  C: {{example_param: 3}}
rules:                          # class: physical | contractual | business_policy (exactly one bendable rule)
  - id: TODO_rule
    class: physical
    description: TODO, may use {{{{example_param}}}}
  - id: TODO_habit
    class: business_policy
    description: TODO the client's habit an exception may bend
"""

CASE_PY = '''"""{title} (original FDE-Bench v2 case).

TODO: one paragraph on the client, the request and what decides validity and quality; then the tiers and
what the rule sets vary.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, labels, read_csv, write_csv, write_eml, write_sql  # noqa: F401
{program_import}

@dataclass
class World:
    """Everything every setting needs. build_world and write_data never see the setting."""

    _cache: dict = field(default_factory=dict)


def build_world(seed: int) -> World:
    rng = random.Random(seed)  # noqa: F841
    raise NotImplementedError("TODO: generate the world (and any hidden inputs) from the seed")


def write_data(world: World, data_dir: Path, lang: str) -> None:
    """The agent-visible data in the client's own formats (CSV/xlsx, write_sql dumps, write_eml mails)."""
    raise NotImplementedError("TODO")


class _View:
    """The world as one setting sees it: tier flags and the rule set's parameters."""

    def __init__(self, world: World, setting):
        self._w, self.setting = world, setting
        self.medium, self.hard = setting.at_least("medium"), setting.at_least("hard")
        self.example_param = setting["example_param"]

    def __getattr__(self, name):
        return getattr(self._w, name)


def score(world: World, submission_dir: Path, setting) -> dict:
    """{{"violations": [(rule_id, message)], "objective": float, "metrics": {{...}}}} or {{"fatal": message}}."""
    world = _View(world, setting)
    raise NotImplementedError("TODO")


def reference_solution(world: World, out_dir: Path, setting) -> None:
    """A solid deterministic heuristic; it defines quality 1.0. Leave headroom and report it in the README."""
    raise NotImplementedError("TODO")


def violating_examples(world: World, setting) -> dict:
    """{{rule_id: fn(out_dir)}}: for every rule of the setting, a deliverable that breaks exactly that rule."""
    raise NotImplementedError("TODO")


def write_hidden(world: World, hidden_dir: Path) -> None:
    """Optional: inputs the agent never sees (a program's hidden period or corpus), stored in dataset/hidden/."""


def write_ground_truth(world: World, gt_dir: Path, setting) -> None:
    """Optional: answers beyond the reference deliverable (expected tables, expected outputs) in dataset/gt/."""
'''

README = """# {title} — `{case_id}`

TODO: the client, the request, the deliverable, and why it is realistic (sources; flag unverified facts).

## Data (the same in every setting)

TODO: files and formats the agent receives.

## Tiers: which rules apply

| | easy | medium | hard |
|---|---|---|---|
| **Rules in force** | TODO | TODO | TODO |
| **Out of scope this round** | TODO | TODO | – |
| **Quality** | TODO | TODO | TODO |

## Rule sets: the client's parameters

| Parameter | A | B | C |
|---|---|---|---|
| TODO | | | |

## Situations

| Kind | Situation | Correct behaviour |
|---|---|---|
| ① hidden fact | TODO | TODO |
| ② dated event | TODO | TODO |
| ③ pressure | TODO | TODO |

## Reference numbers

TODO: reference objective for all nine settings, how often each rule binds, gain from bending the business
rule, headroom; per-tier means.
"""

REQUEST = "TODO: the client's short, under-specified request in this language (no setting markers).\n"
REQUIREMENTS = """# TODO title

## Background

TODO: the request again, in the client's words.

## Deliverable

TODO

## Data notes

TODO
<!-- tier: easy -->
- TODO: what is out of scope this round.
<!-- /tier -->

## How the work is judged

TODO: hard constraints, then quality. Parameters come from the rule set, e.g. {{example_param}}.
"""
TARGETS_EN = """- id: TODO_target
  kind: missing
  domain: business rule
  text: TODO a fact a good engineer must ask for, may use {{example_param}}.
"""
TARGETS = """- id: TODO_target
  text: TODO (same ids as en/targets.yaml, written in this language)
"""


def new_case(case_id: str, cases_root: Path = Path("cases"), kind: str = "batch", seed: int = 20270101) -> Path:
    field_id, _, role = case_id.partition("/")
    if not role or field_id not in load_fields(cases_root):
        raise ValueError(f"case id must be <field>/<role> with a field from {cases_root}/fields.yaml")
    root = Path(cases_root) / field_id / role
    if root.exists():
        raise FileExistsError(f"{root} already exists")
    title = role.replace("_", " ").title()
    deliverable = ("entrypoint: solution.py:run          # TODO file.py:function" if kind == "program"
                   else "deliverables: [TODO.csv]")
    (root / "locales").mkdir(parents=True)
    (root / "case.yaml").write_text(CASE_YAML.format(role=role, title=title, field=field_id, seed=seed, kind=kind,
                                                     deliverable=deliverable), encoding="utf-8")
    program_import = ("from fdebench2.casekit import program_session, run_program  # noqa: F401\n\n"
                      "ENTRYPOINT = \"solution.py:run\"\n" if kind == "program" else "")
    (root / "case.py").write_text(CASE_PY.format(title=title, program_import=program_import), encoding="utf-8")
    (root / "README.md").write_text(README.format(title=title, case_id=case_id), encoding="utf-8")
    for lang in LOCALES:
        d = root / "locales" / lang
        d.mkdir()
        (d / "request.md").write_text(REQUEST, encoding="utf-8")
        (d / "requirements.md").write_text(REQUIREMENTS, encoding="utf-8")
        (d / "targets.yaml").write_text(TARGETS_EN if lang == "en" else TARGETS, encoding="utf-8")
    return root
