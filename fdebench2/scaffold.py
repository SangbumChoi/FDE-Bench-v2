"""`fdebench2 new-case <field>/<role>`: the skeleton of a new case with settings.

It writes case.yaml, case.py, README.md and the five locales with every
required part in place and marked TODO, so a new role starts from the same
contract as the built ones. validate-case fails while any TODO is left; once
they are filled, `fdebench2 export-dataset` and `fdebench2 validate-case` finish it.
Built cases to copy patterns from: a batch case with settings is
`manufacturing/procurement_specialist`; daily program cases are
`finance/loan_underwriting_specialist`, `healthcare/hospital_appointment_scheduler`
and `finance/stock_trading_strategist`; a program that processes a folder is
`data_knowledge/multilingual_corpus_curator`. (Until they are converted, these
still declare the deprecated `rulesets:`; a new case draws its parameters with
`params:` and `rule_seeds:` as DESIGN.md, Settings, describes.)
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
  TODO: the exact format of the deliverable, the same in every setting (the agent never sees it; a batch case's
  extractor reshapes the agent's files into it, a program case's entry function follows it).
tiers:                          # difficulty -> which rules apply; the data is the same in every tier
  easy: TODO the core problem
  medium: TODO easy + more domain rules
  hard: TODO medium + the uncertain or adversarial parts
params:                         # the client's rule parameters: a rule seed draws each one from its candidates
  example_param:
    values: [1, 2, 3]           # one pool for every tier, or {{easy: [..], medium: [..], hard: [..]}}
    # labels: {{1: {{zh: .., en: .., ko: .., ja: .., es: ..}}}}   # optional: a value's wording per locale
rule_seeds: [1, 2, 3]           # the public panel (dataset/, explainer); any other int is a private seed
rules:                          # class: physical | contractual | business_policy (exactly one bendable rule)
  - id: TODO_rule
    class: physical
    description: TODO, may use {{{{example_param}}}}
  - id: TODO_habit
    class: business_policy
    description: TODO the client's habit an exception may bend
    # when: {{example_param: [2, 3]}}   # optional: the rule applies only for these drawn values
"""

CASE_PY = '''"""{title} (original FDE-Bench v2 case).

TODO: one paragraph on the client, the request and what decides validity and quality; then the tiers and
what the rule parameters vary (case.yaml params: holds their candidates).
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


def derive_params(params: dict, tier: str) -> dict:
    """Optional: values computed from the drawn parameters (e.g. period dates from a fiscal-year start), usable
    as setting["name"] and {{{{name}}}}. A value may be {{zh: .., en: .., ko: .., ja: .., es: ..}} to read per locale.
    Delete this hook if nothing is derived."""
    return {{}}


def admissible(params: dict, tier: str) -> bool:
    """Optional: False rejects a combination of drawn (and derived) values, e.g. a cap below what the data
    allows; the rule seed then draws every parameter again. Delete this hook if every combination works."""
    return True


class _View:
    """The world as one setting sees it: tier flags and the parameters its rule seed drew."""

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
    """A solid deterministic heuristic; it defines quality 1.0 (the baseline is 0). Report the headroom above it."""
    raise NotImplementedError("TODO")


def baseline_solution(world: World, out_dir: Path, setting) -> None:
    """The simplest sensible valid deliverable (e.g. the client's own habit, no optimization). validate-case checks
    it is valid and worse than the reference in every setting and prints baseline/reference per setting."""
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

## Rule parameters: candidates and the public rule seeds

| Parameter | easy | medium | hard | What it changes |
|---|---|---|---|---|
| TODO | | | | |

The public rule seeds (case.yaml `rule_seeds`) and the values they draw are in the explainer and in
`dataset/gt/<tier>_s<seed>/setting.json`.

## Situations

| Kind | Situation | Correct behaviour |
|---|---|---|
| ① hidden fact | TODO | TODO |
| ② dated event | TODO | TODO |
| ③ pressure | TODO | TODO |

## Reference numbers

TODO: reference objective for every public setting (tier x public rule seed), how often each rule binds, gain
from bending the business rule, headroom; per-tier means.

TODO: baseline objective and baseline/reference for every public setting (validate-case prints the ratios).
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

TODO: hard constraints, then quality. Parameters come from the rule seed's draw, e.g. {{example_param}}.
<!-- when: example_param=2,3 -->
- TODO (optional): a passage only for these drawn values.
<!-- /when -->
"""
TARGETS_EN = """- id: TODO_target
  kind: missing
  domain: business rule
  text: TODO a fact a good engineer must ask for, may use {{example_param}}.
"""
TARGETS = """- id: TODO_target
  text: TODO (same ids and parameters as en/targets.yaml, e.g. {{example_param}}, written in this language)
"""
EXPLAINER = """# The explainer's case texts in this language (English comes from case.yaml).
role: TODO the role title
task_type: TODO
deliverable_spec: |
  TODO a reading translation of case.yaml's deliverable_spec (the agent and the extractor get the English)
tiers:
  easy: TODO
  medium: TODO
  hard: TODO
rules:
  TODO_rule: TODO
  TODO_habit: TODO
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
        if lang != "en":    # the explainer and the README in every language
            (d / "explainer.yaml").write_text(EXPLAINER, encoding="utf-8")
            (root / f"README.{lang}.md").write_text(f"TODO: README.md in {lang}.\n", encoding="utf-8")
    return root
