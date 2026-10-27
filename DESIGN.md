# FDE-Bench v2 — design

FDE-Bench v2 measures how well agent systems (model × harness) do forward-deployed engineering when the
**customer's language**, the **deploying company's policy** and the **realism of the engagement** change.

An FDE task here is: an under-specified customer request plus business data; hidden requirements that a
simulated client reveals only when asked; a deliverable scored by a deterministic evaluator with hard
constraints and a quality score against a reference. The repository is self-contained: harness, case
format, cases, scoring and pipelines. It has no dependency on any other benchmark's code or data.

## 1. Design goals

| Goal | How |
|---|---|
| Languages | Cases authored natively in **zh / en / ko / ja / es**, data rendered in each locale; the agent's own instruction language is a separate variable. |
| Company policies | **Policy profiles** (gates, weights, budgets, question caps, exception process) and rule classes that say which rules may bend. |
| Realistic difficulty | **easy / medium / hard** content tiers, each scored under **three rule sets** (nine ground truths of the same data), plus an engagement axis with recoverable data noise and mid-task events. |
| Fair comparison | The agent's prompt and files are byte-identical in every setting, and runs are isolated so nothing that differs between settings is reachable. |
| Any model, any harness | One **OpenAI-compatible** model protocol plus vendor CLIs over a shared **MCP** client channel. |

## 2. Cases

Cases live in `cases/<field>/<role>/`: grouped by field at the top level (`cases/fields.yaml`, names in all
five locales) and titled by the role the agent plays (e.g. `finance/loan_underwriting_specialist`). The
catalog of planned cases, at most 10 per field, is `cases/README.md`. Cases are written from scratch by the
benchmark owners; one built case per field serves as an example of the format. A case that lacks a locale can still be run in it: its texts are machine-translated at run
time (cached in `.cache/`).

## 3. Native case format

```
cases/<field>/<role>/
  case.yaml                 id (= role dir), role (title), field (= parent dir), task_type, seed,
                            objective (minimize|maximize),
                            deliverables, deliverable_spec, rules [{id, class, description}]
  case.py                   build_world(seed) · write_data(world, dir, lang) · reference_solution(world, dir)
                            · score(world, submission_dir) · violating_examples(world)
                            (cases with settings: the last three also take the setting)
  locales/<zh|en|ko|ja|es>/
    request.md              the client's short, under-specified request (what the agent sees)
    requirements.md         complete requirements (hidden; the simulated client answers from it)
    targets.yaml            clarification targets: the facts a good FDE must ask for
  README.md                 cases with settings: tiers, rule sets and reference numbers per setting
```

Design rules that keep scoring language-independent:

- **The world is built from the seed, never from files.** Ground truth (including any hidden future for
  forecasting cases) lives in the world. The evaluator scores against the world, so noisy or localized data
  copies can never corrupt scoring.
- **Data is rendered per locale.** File names, sheet names, column headers and categorical labels are
  localized; IDs and numbers are not. A Korean client sends `매장목록.csv` with `매장등급 = 프리미엄`; a Spanish
  one sends `cafeterias.csv` with `categoria = premium`.
- **Deliverables use ASCII keys and data IDs**, so one evaluator scores submissions made in any locale.
- **Quality** is `reference_objective / objective` (or the inverse for maximize). The reference is a solid
  deterministic heuristic shipped with the case: quality 1.0 = matches it, > 1.0 = beats it (clipped at 1.0
  in the composite score, reported raw).
- **Rules carry a class** (`physical`, `contractual`, `business_policy`). The evaluator reports violations by
  rule id; relaxing a rule is a scoring parameter (`evaluate(..., relaxed={...})`), so no per-case hooks.

`fdebench2 validate-case <dir>` enforces the contract before a case is used:

- all 5 locales present with the same target ids, in the right script;
- data renders deterministically in every locale with no untranslated labels;
- the reference scores validity 1 / quality 1.0 and an empty submission is invalid;
- every rule has an example that breaks exactly that rule, and that becomes valid when a non-physical rule
  is relaxed.

### Settings: one world, nine ground truths

A case may declare **settings**: three content tiers (`tiers:` easy / medium / hard) times three rule sets
(`rulesets:` A / B / C). Together they give nine ground truths for **one** world:

- **The agent's view never changes.** `build_world(seed)` and `write_data(world, dir, lang)` never see the
  setting, and `request.md` has no setting-specific text, so the data, the request and the prompt are
  byte-identical in all nine settings. Only the hidden requirements (which the simulated client answers
  from) and the evaluator differ: the agent has to find out from the client which rules apply this time.
- **A tier** decides which rules apply and how strictly the deliverable is scored: easy is the core problem,
  medium adds domain rules, hard adds the uncertain or adversarial parts. The data is the same, so a lower
  tier's requirements say which parts of it are out of scope this round.
- **A rule set** gives the rules' hyperparameters (caps, thresholds, which item a rule targets, scoring
  weights), e.g. which clinic is closed on a holiday or how many interpreters there are. Different
  parameters lead to different correct solutions; a solution tuned to one rule set fails or scores worse
  under another.
- `reference_solution`, `score` and `violating_examples` take the setting (`Setting.tier`, `.ruleset`,
  `.at_least(tier)`, `setting["param"]`). Rules and targets carry `tiers: [...]` / `rulesets: [...]`;
  requirements and targets use `<!-- tier: medium hard -->` / `<!-- ruleset: B -->` … blocks and
  `{{param}}` placeholders (`param_labels` in case.yaml words a code parameter per locale).
- **Evaluation:** the difficulty picks the tier and campaigns run every rule set (`ruleset: all`), so each
  (case, difficulty) cell is the mean over A, B and C, and the report has one column per difficulty.

`validate-case` checks every setting: reference, determinism, empty submission and one rule-breaking example
per rule, with that setting's rules and parameters. It also checks that each rule set's reference is invalid
or at least 1% worse under every other rule set of its tier, that request.md has no setting markers, and that
the agent's prompt and workspace are byte-identical in all nine settings. Cases without settings are the same
problem at every difficulty.

### Program deliverables

A case with `deliverable_type: program` and `entrypoint: solution.py:decide` asks for code, not a file of
answers: the agent delivers a `program/` directory (entry file plus any helpers or model files), and the
case's `score()` calls `casekit.run_program(submission_dir, ENTRYPOINT, hidden_inputs)`. The function is
called once per hidden input, in order, in one process (so a program may keep state), and returns per-input
outputs or errors. Two variants:

- `casekit.program_session(...)`: one input at a time, each built after seeing the previous output, in the
  same process (a trading strategy whose next day depends on its own orders and fills).
- `run_program(..., input_dir=..., output_to=...)`: the program gets a copy of a hidden folder and an empty
  output folder (`"$INPUT_DIR"` / `"$OUTPUT_DIR"` in the inputs), e.g. `organize(corpus_dir, out_dir)`.

The program never runs inside the scorer. `fdebench2/program.py` starts `program_host.py` in a separate
process that speaks JSON lines over a pipe; whatever the program prints cannot reach the protocol stream.
Each call has a timeout, the whole run has a wall-clock limit and a memory cap, and a crash, a timeout or a
non-JSON output costs only that input (a program that cannot load is fatal). Two runners:

- `local` (development): a private copy of the program directory, minimal environment, `RLIMIT_AS`, and no
  network via `unshare -n` where available. The program can still read the filesystem.
- `docker` (campaigns; chosen automatically under a docker sandbox): `--network none`, memory and CPU limits,
  and only the program directory (read-only) and the host script mounted.

Program deliverables are collected from the workspace as the directory holding the entry file (without
`data/` and `inbox/`) and are never reshaped by the extractor model, since rewriting code would mean
re-solving the task. The validator requires the reference to write `program/`, checks that `ENTRYPOINT`
matches `case.yaml`, and checks that scoring is deterministic.

## 4. Architecture

```
                         cases/<id>  (5 locales)
                                         │
          ┌──────────────── transforms (fdebench2/transforms) ────────────────┐
          │ language: pick the customer locale; agent instructions in agent   │
          │           locale; all generated messages from a 5-locale catalog  │
          │ policy:   profile + agent-visible brief                           │
          │ setting:  difficulty (tier) × rule set → hidden reqs + evaluator  │
          │ engagement: condition · persona · data noise · scheduled events   │
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
     scoring: extract submission → case evaluator (world truth, rules, relaxations)
              → clarification judges → policy composition → result.json → report
```

**One model protocol.** Every model call (solver, simulated client, judges, extractor, and the run-time
translator for cases that lack a locale) goes through `fdebench2/llm.py`: the official `openai` SDK with a
configurable `base_url`. That reaches OpenAI, Anthropic's and Gemini's OpenAI-compatible endpoints, DeepSeek,
Qwen/DashScope, OpenRouter, and any open-weights model behind vLLM, SGLang or Ollama (e.g. Reflection AI's
open models).

**Two kinds of harness.** A neutral reference loop (`bash`, `read_file`, `write_file`, `list_files`,
`ask_customer`, `request_exception`, `finish`) gives every model identical tools and prompts; vendor CLIs
(Claude Code, Codex, Gemini CLI, OpenCode) run headless and reach the same client through an MCP server.
Model M in the reference loop vs M in its vendor CLI isolates the **harness effect**.

**No run-time translation for fully localized cases.** Case texts and data are authored per locale; the agent
instructions (`prompts/agent/*.yaml`) and every message v2 generates itself (events, noise facts, policy
briefs: `prompts/messages.yaml`) are hand-written in all five locales.

## 5. The axes

### 5.1 Language

| Variable | Values | Meaning |
|---|---|---|
| `customer_locale` | `zh`, `en`, `ko`, `ja`, `es` | Language of the request, hidden requirements, data labels, client answers and event messages. |
| `agent_locale` | `zh`, `en`, `ko`, `ja`, `es` | **Protocol language**: the language of the agent's own instructions and policy brief. |

The simulated client answers in the customer's register (business-polite Korean, Japanese です/ます with light
敬語, Spanish *usted*). Measured: quality and Ask-F1 per locale relative to the agent's `en` baseline, and
**language fidelity** (share of questions to the client and of `NOTES.md` in the required language).
Clarification judges see each target in English and in the customer locale.

Experiments: *customer language* (vary `customer_locale`, agent `en`) and *protocol language* (fix e.g. a
Korean client, vary `agent_locale` over en/ko/zh) — which instruction language to deploy an FDE agent with.

### 5.2 Policy

A policy (`configs/policies/*.yaml`) is both an agent-visible brief and a scoring profile: `confirm_before_build`,
`question_budget`, `exceptions` (`forbidden` / `escalate` / `justify`), `rule_classes` that may bend,
`soft_rule_penalty`, `notes_required`, `communication_locale`, `budgets` (+ `hard_budgets`), `hard_gates`,
`weights`. Shipped: `baseline` (quality only, hidden), `enterprise_balanced`,
`regulated_strict`, `startup_velocity`.

A violated rule is forgiven only if the policy makes its class soft, the agent went through the prescribed
exception process (`request_exception` approved under `escalate`, recorded under `justify`), and the case
re-scores the deliverable with the rule relaxed. Physical rules never bend.

### 5.3 Difficulty and rule sets

`difficulty` (easy / medium / hard) picks a case's content tier and `ruleset` (A / B / C) its rule
parameters (§3, Settings). Neither changes what the agent sees. Campaigns run all three rule sets per
difficulty and report their mean, so a difficulty column is the average over three ground truths of the
same data. Cases without settings run the same problem at every difficulty.

### 5.4 Engagement

How the work is handed over, kept separate from difficulty so that a difficulty comparison holds the
agent's prompt fixed (`configs/engagement.yaml`):

| Knob | `full_spec` | `standard` (default) | `messy` |
|---|---|---|---|
| Condition | `full`: complete requirements given | `interact_req`: must clarify first | `interact_req` |
| Client persona | cooperative | default | busy: terse; vague questions get vague answers |
| Question rounds | 30 | 30 | 15 |
| Data noise | none | none | duplicate rows, stale backup file, legacy code-page encoding (GB18030 / CP949 / Shift_JIS / CP1252 by locale) |
| Events | none | none | stakeholder conflict, client unavailable, data correction, late-remembered requirement, deadline pulled in |

Everything in `messy` is **recoverable**: noise touches only the agent's copy (scoring uses the world),
the client knows the fact that undoes each noise op (it becomes an extra clarification target), a non-owner
stakeholder's conflicting message is resolvable by asking the client, and a corrected file arrives mid-task.
Noise and events are seeded by the engagement, never by the difficulty or rule set.

### 5.5 Isolation

Comparisons are fair only if the agent cannot see what differs between settings. Campaigns default to
`isolation: strict`: every run uses the docker sandbox, which mounts only the run's workspace at
`/workspace` (the request and data, identical in every setting). Vendor CLIs run inside that container
(`docker/Dockerfile.agent`) and reach the client over HTTP on the host, so the cases, the hidden
requirements, the other settings' ground truths and the run directory's name (which encodes the setting)
are never reachable. Network access stays on (model APIs); only information is isolated. `isolation: off`
allows the local sandbox for development.

## 6. Scoring

```
final = 0                                          if a hard gate fails (always: validity)
      = clip( Σ wᵢ·cᵢ / Σ wᵢ − penalties, 0, 1 )   over the components that apply
```

| Component | Definition |
|---|---|
| quality | case quality vs reference, clipped at 1.0; 0 if invalid |
| clarification | Ask-F1 over case + noise targets (majority vote of a judge panel); only if the client was reachable |
| communication | mean of language fidelity (questions, NOTES.md) and NOTES.md presence |
| efficiency | per budget: 1 − ½·used/budget, 0 once over budget |

Reported per cell: final, quality, validity rate, DSR (quality ≥ reference), pass^k (all seeds valid),
Ask-F1. Case-macro averages; deltas within one agent against its baseline cell. The difficulty table has
one column per difficulty, each the mean over the three rule sets, with "all-3": the share of (case, seed)
cells valid under every rule set.

## 7. Status

- Harness, transforms, scoring, MCP bridge, campaign runner and report: implemented and tested.
- Case format, settings (tiers × rule sets), `casekit`, validator and 5-locale message catalog: implemented.
- Built cases: one or more per field (see `cases/README.md`), all passing `validate-case` in all five
  locales. Cases with settings: loan underwriting, hospital scheduling, procurement, stock trading (program)
  and multilingual corpus curation (program).
- Program deliverables: implemented and tested (state across calls, step-by-step sessions, input/output
  folders, per-call and total timeouts, crashes, non-JSON outputs, environment and network isolation,
  collection, an end-to-end run).

Not yet verified: a live model run (no API keys in the build environment), the vendor CLI command lines
against installed versions, `DockerSandbox` and `docker/Dockerfile.agent` (no Docker daemon in the build
environment).
