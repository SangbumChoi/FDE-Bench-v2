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
| Realistic difficulty | **easy / medium / hard** tiers over explicit knobs, including recoverable data noise and mid-task events. |
| Any model, any harness | One **OpenAI-compatible** model protocol plus vendor CLIs over a shared **MCP** client channel. |

## 2. Cases

Cases live in `cases/<id>/` in the native format below and are written from scratch by the benchmark
owners. The three cases in the repository are examples of the format; the benchmark's case set is supplied
by the owners. A case that lacks a locale can still be run in it: its texts are machine-translated at run
time (cached in `.cache/`).

## 3. Native case format

```
cases/<id>/
  case.yaml                 id, title, task_type, domain, seed, objective (minimize|maximize),
                            deliverables, deliverable_spec, rules [{id, class, description}]
  case.py                   build_world(seed) · write_data(world, dir, lang) · reference_solution(world, dir)
                            · score(world, submission_dir) · violating_examples(world)
  locales/<zh|en|ko|ja|es>/
    request.md              the client's short, under-specified request (what the agent sees)
    requirements.md         complete requirements (hidden; the simulated client answers from it)
    targets.yaml            clarification targets: the facts a good FDE must ask for
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

## 4. Architecture

```
                         cases/<id>  (5 locales)
                                         │
          ┌──────────────── transforms (fdebench2/transforms) ────────────────┐
          │ language: pick the customer locale; agent instructions in agent   │
          │           locale; all generated messages from a 5-locale catalog  │
          │ policy:   profile + agent-visible brief                           │
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

## 5. The three axes

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

### 5.3 Difficulty

| Knob | easy | medium | hard |
|---|---|---|---|
| Condition | `full`: complete requirements given | `interact_req`: must clarify first | `interact_req` |
| Client persona | cooperative | default | busy: terse; vague questions get vague answers |
| Question rounds | 30 | 30 | 15 |
| Data noise | none | none | duplicate rows, stale backup file, legacy code-page encoding (GB18030 / CP949 / Shift_JIS / CP1252 by locale) |
| Events | none | none | stakeholder conflict, client unavailable, data correction, late-remembered requirement, deadline pulled in |

Everything in the hard tier is **recoverable**: noise touches only the agent's copy (scoring uses the world),
the client knows the fact that undoes each noise op (it becomes an extra clarification target), a non-owner
stakeholder's conflicting message is resolvable by asking the client, and a corrected file arrives mid-task.

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
Ask-F1. Case-macro averages; deltas within one agent against its baseline cell.

## 7. Status

- Harness, transforms, scoring, MCP bridge, campaign runner and report: implemented, 14 tests passing.
- Case format, `casekit`, validator and 5-locale message catalog: implemented.
- Example cases: `logistics_bakery_routing`, `services_callcenter_rostering`, `retail_grocery_demand_forecast`,
  all passing `validate-case` in all five locales.

Not yet verified: a live model run (no API keys in the build environment), the vendor CLI command lines
against installed versions, `DockerSandbox` (no Docker daemon in the build environment).
