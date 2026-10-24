# FDE-Bench v2 — design

FDE-Bench v2 measures how well agent systems (model × harness) do forward-deployed engineering when the
**customer's language**, the **deploying company's policy**, and the **realism of the engagement** change.
It is a rewrite of the harness around the 49 cases of
[FDE-Bench v1](https://baidubce.github.io/FM-Agent/FDE-Bench/) (Baidu AI Cloud, arXiv 2610.14539).
v2 adds no new scenarios: every v2 task is a **transform** of a v1 case. The case, its data, and its
evaluator stay exactly as v1 ships them.

## 1. What v1 gives us, and what it lacks

v1 case = `instruction.md` (the customer's original, under-specified request) + `data/` + hidden
`information.md` (complete requirements) + `gt.json` (266 clarification targets in total) + a deterministic
`tests/evaluator.py` (hard constraints → 0; otherwise quality normalized so the accepted FDE solution is 1.0).
The main setting (Interact-Req) lets the agent question an LLM-simulated client before solving.

From reading the v1 code:

| Gap in v1 | Evidence | v2 axis |
|---|---|---|
| One language | Every request, requirement, target and client answer is Chinese; the agent prompt is English. | **Language** |
| One policy | All case rules are hard constraints inside each evaluator; no notion of a company's engagement rules, budgets, or sanctioned rule exceptions. | **Policy** |
| No difficulty signal | All 49 `task.toml` say `difficulty = "hard"`. The paper itself lists "requirements and data are fixed" and a client that never revises expectations as limitations. | **Difficulty** |

## 2. Licensing constraint (shapes the architecture)

v1 code is MIT, but v1 **data** (everything under `case/`: requests, requirements, targets, data files,
evaluators, references) is **CC BY-NC-ND 4.0**: no commercial use, no sharing of modified versions.

Consequences:

- This repository contains **no v1 case material**. Users point `--v1-root` at their own checkout of
  `baidubce/FM-Agent/FDE-Bench` with the data restored.
- Transforms run **locally at run time**. Translations, noisy data copies and variant files are written to
  `.cache/` and `runs/` (both git-ignored) and must not be published.
- v2 code is a clean rewrite; it reads v1 files and calls v1 evaluators unmodified.
- Case annotations that v2 *does* ship (`configs/case_rules/*.yaml`, `fdebench2/case_hooks/`) contain only
  our own classification of rule codes plus code that calls the v1 evaluator's functions. They contain no v1
  text or data.
- **Open question for the team:** NC prohibits commercial use. Running v1 data inside a company may count as
  commercial use. Get a legal read, or ask the FDE-Bench authors for permission, before running campaigns at
  work. Publishing translated cases needs the authors' permission in any case.

## 3. Architecture

```
               v1 case (read-only)                         configs/
   instruction · information · gt · data · evaluator       policies · difficulty · case_rules · models
                       │                                        │
                       ▼                                        ▼
          ┌──────────────── transforms (fdebench2/transforms) ────────────────┐
          │ language: translate request / requirements / targets / events     │
          │ policy:   load profile, render agent-visible brief (agent locale) │
          │ difficulty: condition · persona · data noise · scheduled events   │
          └──────────────────────────────┬────────────────────────────────────┘
                                         ▼
                 run_dir/  variant/variant.json   workspace/ (agent sees only this)
                                         │
       ┌─────────────────────────────────┼──────────────────────────────────┐
       ▼                                 ▼                                  ▼
 reference harness              Session (client, events,           CLI harnesses
 OpenAI Chat Completions        exceptions, transcript.jsonl)       Claude Code · Codex ·
 tool loop, any model  ───────▶  in-process  ◀── MCP bridge ──────  Gemini CLI · OpenCode
                                         │
                                         ▼
     scoring: extract submission → v1 evaluator (unmodified, pristine data)
              → clarification judges → policy composition → result.json → report
```

### One protocol for models: OpenAI Chat Completions

Every model call goes through `fdebench2/llm.py`. This covers the solver under test, the simulated client,
the translator, the judges and the extractor. It uses the official `openai` SDK with a configurable
`base_url`. That one wire format reaches OpenAI, Anthropic's and Gemini's OpenAI-compatible endpoints,
DeepSeek, Qwen/DashScope, OpenRouter, and any open-weights model served by vLLM, SGLang or Ollama (for
example Reflection AI's open models once they are served). Adding a model is a 3-line entry in
`configs/models.yaml`.

### Two kinds of harness

- **Reference harness** (`agents/reference.py`): a plain function-calling loop with `bash`, `read_file`,
  `write_file`, `list_files`, `ask_customer`, `request_exception` and `finish`. Every model gets identical
  tools, prompts and budgets, so rows differ only by model.
- **Vendor CLIs** (`agents/cli.py`): Claude Code, Codex, Gemini CLI and OpenCode, run headless. They get
  the same prompt. They reach the client through an **MCP server** (`mcp_bridge.py`) that exposes the same
  `ask_customer` / `request_exception` / `check_inbox` tools backed by the same Session. Events reach CLI
  agents through tool responses and `inbox/` files.

Comparing model M in the reference harness against M inside its vendor CLI isolates the **harness effect**.

### Improvements over the v1 harness

- Client interaction is a structured tool (`ask_customer`), not a parsed "## Questions" heading. It is the
  same tool across all harnesses.
- Every interaction (questions, answers, events, exceptions, steps) goes to one `transcript.jsonl` per run.
  All process scoring reads from it.
- Scoring is re-runnable and **re-scorable under any policy** without re-running the agent.
- Evaluation-side models (client, translator, extractor, judges) are recorded with every result
  (`eval_models`), because changing them changes the benchmark.

## 4. The three axes

### 4.1 Language

| Variable | Values | Meaning |
|---|---|---|
| `customer_locale` | `source` (zh), `en`, `ko`, `ja`, `es` | Language of the request, the hidden requirements, the client's answers, and event messages. |
| `agent_locale` | `en`, `zh`, `ko`, `ja`, `es` | **Protocol language**: the language of the agent's own instructions. Hand-written templates in `fdebench2/prompts/agent/*.yaml`, not machine translated. |

- The client simulator answers in the customer's language and register: business-polite Korean (합니다/해요체),
  Japanese です/ます with light 敬語, Spanish *usted*.
- Data files are never translated. Translations keep file, sheet, column and code names verbatim, with an
  optional gloss in parentheses, because the agent has to match them to the data.
- Measured: delivery quality and Ask-F1 per locale relative to that agent's `zh` baseline. **Language
  fidelity** is the share of the agent's questions and of `NOTES.md` written in the required locale. It
  uses a script-based detector for these five languages.
- Clarification judges see each target both as annotated (zh) and in the customer locale. The judge panel
  must read every locale in the campaign.
- Translation quality is a threat to validity. Machine translation is the default, and translations are
  cached per model. For any locale we publish numbers on, a native speaker should review the cached
  translations; corrections are written straight into the cache.

**Two experiments**
1. *Customer language*: vary `customer_locale` with `agent_locale = en` fixed.
2. *Protocol language*: fix the customer (e.g. `ko`) and vary `agent_locale` over {en, ko, zh}. This answers
   which language to deploy the FDE agent's instructions in for a given market.

### 4.2 Policy

A policy (`configs/policies/*.yaml`) states how a company wants FDE work done. It can be shown to the agent
(`agent_visible`) and it is also the scoring profile.

| Field | Effect |
|---|---|
| `statement`, `agent_visible` | Policy brief added to the agent prompt, translated to the agent locale. |
| `confirm_before_build` | Penalty if solution code is written before the first client question (reference harness). |
| `question_budget`, `over_budget_penalty` | Soft cap on clarification questions. |
| `exceptions`: `forbidden` / `escalate` / `justify` | Whether and how the agent may break a client business rule. |
| `rule_classes` | Which classes of case rules may bend: `physical` (never), `contractual`, `business_policy`. |
| `soft_rule_penalty` | Cost per case rule that was legitimately bent. |
| `notes_required`, `communication_locale` | Documentation and reporting-language duties. |
| `budgets`, `hard_budgets` | Wall-clock, token and USD budgets; either cost points or are hard gates. |
| `hard_gates`, `weights` | Score composition (§5). |

Shipped profiles: `v1_default` (reproduces v1 scoring), `enterprise_balanced`, `regulated_strict`,
`startup_velocity`.

**Rule bending.** v1 evaluators report hard-constraint violations as coded messages (e.g. `HC2_HC3_…`).
`configs/case_rules/<case>.yaml` classifies those codes. A violation is forgiven only when all of these hold:

- the policy makes that rule's class soft;
- the agent went through the prescribed process: `request_exception` approved by the client under
  `escalate`, or recorded under `justify`;
- a case hook (`fdebench2/case_hooks/`) can re-score the plan with that rule switched off. v1 evaluators
  stop at the first violation and report no quality.

Shipped annotation: case 010. Here "use same-city stock before buying from suppliers" is a
`business_policy` rule; stock limits are `physical`; DSD designated suppliers are `contractual`.
Annotating more cases is ongoing work. Each annotation is small: a YAML file plus a hook of about 30 lines.

### 4.3 Difficulty

Difficulty is a preset over concrete knobs (`configs/difficulty.yaml`). Case, data and evaluator never
change across tiers.

| Knob | easy | medium (= v1 main setting) | hard |
|---|---|---|---|
| Condition | `full`: complete requirements given | `interact_req`: must clarify first | `interact_req` |
| Client persona | cooperative | default (v1 style) | busy: terse, vague questions get vague answers |
| Question rounds | 30 | 30 | 15 |
| Data noise | none | none | duplicate rows, stale backup file, legacy GB18030 encoding |
| Events | none | none | stakeholder conflict, client unavailable, data correction, late-remembered requirement, deadline pulled in |

All noise and events are **recoverable**, so the hard tier tests diligence, not luck:

- **Noise** touches only the agent's copy of the data. The evaluator scores against pristine v1 data.
  The client knows the fact that undoes each op (e.g. "exact duplicate rows are export errors"), and that
  fact becomes a new clarification target (`origin` = the op), reported apart from v1 targets.
- **Data correction**: the agent first receives a 5%-perturbed version of one file; the correct file arrives
  in `inbox/` mid-task. A solution built on the wrong file scores worse against the pristine data.
- **Stakeholder conflict**: a non-owner asks for a different priority. The client knows this person is not
  the project owner, so an agent that checks with the client gets the right answer.
- **Late requirement**: the client volunteers one v1 target mid-task, which forces rework for agents that
  didn't ask.
- **Deadline**: the remaining time budget is halved.
- Triggers count agent steps (reference harness) or elapsed seconds (CLI harnesses, whose steps the bridge
  can't see), plus "after N questions".

Verified on all 49 real cases: every hard variant builds in ≤ 40 s. Noise coverage depends on the data
format. Four cases have no tabular or JSON file the ops can safely edit (npz arrays, solver code, an 11 MB
workbook, and case 001's 2.6 GB archive, which wasn't downloaded), so their hard tier is events + persona
only. Seven cases have no data-correction event. The variant records which ops applied, so the report can
stratify.

## 5. Scoring

```
final = 0                                          if a hard gate fails (always: validity)
      = clip( Σ wᵢ·cᵢ / Σ wᵢ − penalties, 0, 1 )   over the components that apply
```

| Component | Definition |
|---|---|
| quality | v1 quality, clipped at the FDE reference (1.0); 0 if invalid |
| clarification | Ask-F1 over v1 + v2 targets (majority vote of a judge panel); only if the client was reachable |
| communication | mean of language fidelity (questions, NOTES.md) and NOTES.md presence |
| efficiency | per budget: 1 − ½·used/budget, 0 once over budget |

Also reported per cell: validity rate, **DSR** (quality ≥ reference), **pass^k** (all seeds valid),
Ask-F1, v1-only recall. Cells are case-macro averaged. Deltas are taken within one agent against its
baseline cell, never across agents.

`v1_default` uses quality only. The headline number is policy-conditioned (the agent saw the policy it is
scored under); `fdebench2 score RUN --policy X` also gives the counterfactual.

## 6. Experiment design and cost

The full grid (49 cases × 5 customer locales × 5 agent locales × 4 policies × 3 tiers × 3 seeds) is about
44k runs per agent, with runs of up to 12 h each, so it isn't run in full. Instead, one axis is varied at a
time against a shared baseline cell (customer zh, agent en, `v1_default`, medium) on `subset20`.
`configs/experiments.example.yaml` gives about 20 × 3 × (5 + 3 + 4 + 3 − 3 shared) ≈ 720 runs per agent.
Shared cells are deduplicated automatically.

## 7. Status

Implemented and tested (`pytest`, 13 tests on a synthetic fixture case in v1 format):
transforms, the reference harness, the Session (client, events, exceptions), the MCP bridge, extraction,
the evaluator shim, clarification judging, policy composition, the campaign runner and the report.

Verified against real v1 material:
- 49 cases and 266 targets load.
- The evaluator shim scores the FDE reference solution of all 48 cases with data at validity 1.0 and
  quality 1.0 (± 2e-5), i.e. it reproduces v1. Evaluators need lightgbm, shapely, scipy, scikit-learn and
  networkx on the scoring host.
- Hard variants build for all 49 cases.
- The case-010 relaxation hook was checked on a real plan with an injected sourcing-order violation.

**Not yet verified:**
- **No live model run yet:** this environment has no API keys.
- **The vendor CLI command lines are unchecked** against installed versions.
- **`DockerSandbox` is unexercised:** no Docker daemon in the build environment. Tests use `LocalSandbox`.

Open items, in priority order:
1. First live smoke run (one case, reference harness + one CLI) to calibrate step-based event triggers and
   budgets.
2. Native-speaker review of the cached ko / ja / es translations for `subset20`.
3. Run CLI agents in a container that mounts only the workspace, with the MCP bridge on the host over
   HTTP (`--http`). Stdio mode lets the agent's user read the run directory.
4. Parse token usage from each CLI's log so efficiency applies to CLI harnesses too. A `deadline_change`
   event is announced to CLI agents but does not yet shorten their subprocess timeout.
5. `case_rules` annotations and hooks beyond case 010. Requirement-*change* events (beyond the five
   evaluator-neutral kinds) need the same per-case hooks.
6. Docker images: v1's `env-runner` image and per-case Dockerfiles can be reused; the reference harness
   only needs `docker exec`.
