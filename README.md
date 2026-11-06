# FDE-Bench v2

[English](README.md) · [中文](docs/zh/README.md) · [한국어](docs/ko/README.md) · [日本語](docs/ja/README.md) · [Español](docs/es/README.md)

A benchmark for forward-deployed-engineering agents across **customer languages** (zh/en/ko/ja/es),
**company policies** and **realistic difficulty**. Open and closed models are compared through one
OpenAI-compatible protocol, and vendor harnesses (Claude Code, Codex, Gemini CLI, OpenCode) through a
shared MCP client channel. Self-contained: no dependency on any other benchmark's code or data.

Design, scoring and status: [DESIGN.md](DESIGN.md). Direction, related work and critique:
[docs/DIRECTION.md](docs/DIRECTION.md).

**Browse the cases:** https://sangbumchoi.github.io/FDE-Bench-v2/ — one page per case (request, settings,
rules, hidden requirements, targets, stored data and answers, review findings), rebuilt from
`cases/*/*/docs/<lang>/explainer.html` by `fdebench2 build-site` and published to the `gh-pages` branch on
every push (`.github/workflows/pages.yml`).

## Acknowledgements

We thank the authors of the work this benchmark learned from:

- **FDE-Gym** (Yang et al., *FDE-Gym: The Last Mile of AI Delivery*, arXiv 2610.22350;
  [fde-gym.com](https://fde-gym.com/paper/), [cases](https://huggingface.co/datasets/DeepLethe/FDE-Gym),
  [harness](https://github.com/deeplethe/fde-gym)). Its four brief levels, scripted stakeholders with a contact
  cost, replay on held-out production traffic and admission anchors (do-nothing 0, reference 1, a literal
  reading and shortcuts scored low) informed the ground truth audit here.
- **Baidu FDE-Bench** (arXiv 2610.14539), which introduced the forward-deployed-engineer framing and the metric
  vocabulary (quality against a reference, DSR, Ask-F1, pass^k) that v2 keeps.
- **τ^τ-Bench** (arXiv 2609.04611) and **τ-bench** (arXiv 2406.12045), for the built-agent-on-held-out-users
  design and the pass^k estimator.

v2 shares no code or data with them: every case here is original and generated from a seed, and the FDE-Gym
cases, which have their own terms, were not used. Further related work: [docs/DIRECTION.md](docs/DIRECTION.md)
§2 and §9.

## Setup

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## Use

```bash
fdebench2 cases                                   # <field>/<role>, role title, task type, locales
fdebench2 validate-case cases/*/*/                # contract checks for every case
fdebench2 export-dataset cases/<field>/<role>     # store a case's data and answers in dataset/
fdebench2 audit-case cases/<field>/<role>         # measure its ground truth, stored in dataset/audit.json
fdebench2 policies
# What an agent would get, without running one (Korean client, Japanese agent instructions, messy engagement):
fdebench2 prepare --case logistics/bakery_delivery_dispatcher --customer-locale ko --agent-locale ja \
    --policy startup_velocity --engagement messy
# A case with settings: hard tier, public rule seed 10 (same prompt and files as any other setting):
fdebench2 prepare --case healthcare/hospital_appointment_scheduler --difficulty hard --rule-seed 10
# The same tier with a private rule seed: a fresh draw of the same candidates, whose answer is stored nowhere:
fdebench2 prepare --case healthcare/hospital_appointment_scheduler --difficulty hard --rule-seed 4242
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

`--difficulty` picks a case's content tier and `--rule-seed` draws its rule parameters, each from its own
candidates (default: the case's first public rule seed; any other int is a private seed, a draw whose answer is
stored nowhere). Each pair of tier and rule seed is a ground truth of the same dataset, with the agent's view
identical in all of them. `--engagement` (full_spec / standard / messy) changes how the work is handed over. See
[cases/README.md](cases/README.md#difficulty-one-dataset-tiers-and-rule-seeds).

Axes on every command: `--customer-locale {zh,en,ko,ja,es}`, `--agent-locale {zh,en,ko,ja,es}`,
`--policy NAME`, `--difficulty {easy,medium,hard}`, `--rule-seed N`, `--engagement {full_spec,standard,messy}`,
`--condition {full,interact,interact_req,hidden}`
(ablation override), `--seed N`.

## Layout

```
cases/<field>/<role>/  case.yaml, case.py, locales/<lang>/{request.md, requirements.md, targets.yaml},
                       dataset/ (data per locale, hidden inputs, answer/answers.csv: one row per setting),
                       docs/<lang>/{README.md (tiers, rule parameters, numbers per setting), REVIEW.md,
                       explainer.html}, README.md (generated index of docs/ and answer/), GT.md (audited cases)
cases/README.md        catalog of cases by field   cases/fields.yaml  field names in 5 locales
cases/docs/<lang>/     index.html: the catalog's page in each language (the site's home page)
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
docs/                DIRECTION.md · specs/ (unbuilt cases) · <lang>/README.md (this README in zh, ko, ja, es)
tests/
```
