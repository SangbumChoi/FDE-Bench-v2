# FDE-Bench v2

A benchmark for forward-deployed-engineering agents across **customer languages** (zh/en/ko/ja/es),
**company policies** and **realistic difficulty**. Open and closed models are compared through one
OpenAI-compatible protocol, and vendor harnesses (Claude Code, Codex, Gemini CLI, OpenCode) through a
shared MCP client channel. Self-contained: no dependency on any other benchmark's code or data.

Design, scoring and status: [DESIGN.md](DESIGN.md).

## Setup

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## Use

```bash
fdebench2 cases                                   # <field>/<role>, role title, task type, locales
fdebench2 validate-case cases/*/*/                # contract checks for every case
fdebench2 export-dataset cases/<field>/<role>     # store a case's data and ground truth in dataset/
fdebench2 policies
# What an agent would get, without running one (Korean client, Japanese agent instructions, messy engagement):
fdebench2 prepare --case logistics/bakery_delivery_dispatcher --customer-locale ko --agent-locale ja \
    --policy startup_velocity --engagement messy
# A case with settings: hard tier under rule set B (same prompt and files as any other setting):
fdebench2 prepare --case healthcare/hospital_appointment_scheduler --difficulty hard --ruleset B
# One run with the reference harness and any OpenAI-compatible model from models.yaml:
fdebench2 run --case logistics/bakery_delivery_dispatcher --model qwen --customer-locale es
# Same with a vendor CLI:
fdebench2 run --case logistics/bakery_delivery_dispatcher --harness claude_code --model claude-opus-5-5
# Re-score an existing run under other policies (no agent re-run):
fdebench2 score runs/reference--qwen/<variant> --policy regulated_strict --policy startup_velocity
# Campaigns and reports:
fdebench2 campaign configs/experiments.example.yaml --dry-run
fdebench2 report runs/
```

`--difficulty` picks a case's content tier and `--ruleset` (A/B/C) its rule parameters: nine ground truths of
one dataset, with the agent's view identical in all of them. `--engagement` (full_spec / standard / messy)
changes how the work is handed over. See [cases/README.md](cases/README.md#difficulty-one-dataset-nine-ground-truths).

Axes on every command: `--customer-locale {zh,en,ko,ja,es}`, `--agent-locale {zh,en,ko,ja,es}`,
`--policy NAME`, `--difficulty {easy,medium,hard}`, `--ruleset {A,B,C}`, `--engagement {full_spec,standard,messy}`,
`--condition {full,interact,interact_req,hidden}`
(ablation override), `--seed N`.

## Layout

```
cases/<field>/<role>/  case.yaml, case.py, locales/<lang>/{request.md, requirements.md, targets.yaml},
                       dataset/ (data per locale, hidden inputs, ground truth per setting),
                       README.md for cases with settings (tiers x rule sets)
cases/README.md        catalog of cases by field   cases/fields.yaml  field names in 5 locales
fdebench2/
  cases.py           Case interface and loader
  casekit.py         helpers for case authors        validate.py   case contract checks
  llm.py             OpenAI-compatible client, model registry, scripted model for tests
  transforms/        language · policy · engagement (noise, events) · variant composition (setting)
  prompts/           agent instructions per locale · messages.yaml (all generated messages, 5 locales)
  customer.py        simulated client               session.py    client channel, events, transcript
  agents/            reference tool-calling harness · vendor CLI adapters
  mcp_bridge.py      MCP server giving CLI agents the client channel
  program.py         runs Program deliverables on hidden inputs, isolated (program_host.py inside)
  scoring/           extraction · clarification judges · policy score · report
configs/             policies/ engagement.yaml models.example.yaml experiments.example.yaml
docker/              Dockerfile.agent: the image for isolated runs (tools and vendor CLIs only)
tests/
```
