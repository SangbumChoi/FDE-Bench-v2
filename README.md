# FDE-Bench v2

[English](README.md) · [中文](docs/zh/README.md) · [한국어](docs/ko/README.md) · [日本語](docs/ja/README.md) · [Español](docs/es/README.md)

A benchmark for forward-deployed-engineering agents across **customer languages** (zh/en/ko/ja/es),
**company policies** and **realistic difficulty**. Open and closed models are compared through one
OpenAI-compatible protocol, and vendor harnesses (Claude Code, Codex, Gemini CLI, OpenCode) through a
shared MCP client channel. Self-contained: no dependency on any other benchmark's code or data.

Design, scoring and status: [DESIGN.md](DESIGN.md). Direction, related work and critique:
[docs/DIRECTION.md](docs/DIRECTION.md). To add a case, a translation or a review: [CONTRIBUTING.md](CONTRIBUTING.md).

**Browse the cases:** https://sangbumchoi.github.io/FDE-Bench-v2/ — one page per case (request, settings,
rules, what only the client knows, the facts to ask about, stored data and answers, review findings), rebuilt from
`cases/*/*/docs/<lang>/explainer.html` by `fdebench2 build-site` and published to the `gh-pages` branch on
every push (`.github/workflows/pages.yml`).

**Leaderboard:** https://sangbumchoi.github.io/FDE-Bench-v2/leaderboard.html (from `leaderboard/*.json`). To take part, see [docs/SUBMITTING.md](docs/SUBMITTING.md).

## Quick start

No model and no API key are needed to see what a case asks and how it is scored:

```bash
pip install -e .
fdebench2 try                                         # one case: the request, its files, the score scale, three anchor solutions scored
fdebench2 try --lang ko --submission my_deliverable/  # score your own deliverable (any of the five languages)
```

To run a model, set one endpoint and start with the small campaign (9 runs: three small cases, medium difficulty, public rule seeds):

```bash
cp configs/models.example.yaml configs/models.yaml    # one endpoint and its API-key env var
fdebench2 campaign configs/experiments.starter.yaml   # 9 runs, no docker
fdebench2 report runs-starter/
```

Three ways to take part: **try a case** (above), **submit results** to the leaderboard ([docs/SUBMITTING.md](docs/SUBMITTING.md)), or **add a case, a translation or a review** ([CONTRIBUTING.md](CONTRIBUTING.md)).

## What is different here

FDE-Bench v2 combines the six points below. Each is checked by code in this repository; where another benchmark
does something similar, the table says so:

- **One world, counterfactual settings.** Each case has one dataset and one request. Difficulty tier × rule seed
  draws the client's rules and parameters, and the agent's view is byte-identical in every setting
  (`validate-case` checks it). The score depends on the client's facts; a private rule seed has an answer stored
  nowhere.
- **Five natively authored languages on two axes:** the customer's language (request, data labels, file names,
  the client's answers) and the agent's instruction language, each zh / en / ko / ja / es.
- **A ground truth audit per fact** (`audit-case`): every client fact must bite, shortcuts must be closed, the
  value of asking is measured, and the reference is placed against the best known solution or a bound. Every case's
  literal solution (the request done as written) must score ≤ 0.2.
- **A revealed → learned → enforced funnel** per fact: did the client say it, did the agent ask for it, does the
  deliverable apply it.
- **Rule classes, company policies and an exception process:** physical rules never bend; others bend only
  through the policy's exception process, an approval covers one named rule, and a run can be re-scored under
  other policies without re-running.
- **Dated events and pressure inside the work** (regulator notices, absences, VIP notes, an insider tip),
  scored as rule violations; **program deliverables** are run day by day on a dated period the agent never sees.

| | FDE-Bench v2 | τ-bench | τ^τ-Bench | Baidu FDE-Bench | FDE-Gym |
|---|---|---|---|---|---|
| Deliverable | Files, or a program run on inputs the agent never sees | A conversational tool-calling agent, judged in the dialogue | A customer-service agent, scored on held-out simulated users | Solutions to 49 real customer projects (optimization, ML) | A delivery in a copy of the customer's production system, replayed on held-out traffic |
| Facts only the client knows | A simulated client answers from requirements the agent is not given; one target per fact | A simulated user holds the task's goal and reveals it in conversation | Client with requirements the agent is not given (fixed fact IDs) | Revealed by a simulated customer | 130+ scripted stakeholders; briefs at four levels |
| Counterfactual settings on one fixed view | Tier × rule seed, private seeds | Fixed tasks (115 retail, 50 airline) | – | No (fixed data, a stated limit) | Fixed tasks plus held-out variants |
| Languages | 5, customer × agent | 1 (English) | – | – | 1 |
| Company policies, exception process | 4 policies; one approval per named rule | A domain policy document (Markdown); no exception process | – | – | – |
| Ground truth audit / admission anchors | Per-fact audit (3 cases); literal ≤ 0.2 and scale ≥ 5% for all | – | – | – | Reference ≥ 0.95, do-nothing 0, literal ≤ 0.2, shortcuts ≤ 0.8 |
| Fact funnel revealed → learned → enforced | Per fact, in the report | – | – | – (notes agents asking about a rule, then not enforcing it) | – (reports key facts obtained against uplift) |
| Harness comparison | Reference loop + 4 vendor CLIs on one MCP client channel | Models in one tool-calling loop | Claude Code, Codex, Kimi Code, OpenCode | – | 13 configurations |
| Scoring | Validity gate; quality from baseline 0 to reference 1, above 1 counts; Ask-F1; pass^k; policy-weighted | 0/1 per task: final database state and required answers; pass^k | Built agent on held-out users vs an oracle reference (one trial, no CIs) | Quality vs accepted solution, DSR, pass^3, Ask-F1, bootstrap CIs | Normalized uplift, ≤ 0 on an incident, minus a hidden contact cost |

"–": not stated in [docs/DIRECTION.md](docs/DIRECTION.md) §2, the source for the other benchmarks; not a claim
that the feature is absent. τ-bench is used here for its pass^k estimator. No live campaign has run on v2 yet, so
the funnel and harness comparison have no numbers so far.

## Setup

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## Use

```bash
fdebench2 cases                                   # <field>/<role>, role title, task type, locales
# Try a case without a model or API key (the request, its files, the facts only the client knows, the
# score scale, and the literal solution, baseline and reference scored; --submission DIR scores your own):
fdebench2 try
fdebench2 try --case logistics/bakery_delivery_dispatcher --difficulty hard --lang ko --submission my_deliverable/
# Package a campaign's results for the leaderboard (docs/SUBMITTING.md):
fdebench2 campaign configs/experiments.leaderboard.yaml       # 351 runs
fdebench2 submit runs-leaderboard/ --name "My system" --flag web_tools=off --out leaderboard/my-system.json
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
  dataset.py         stored data and answers         audit.py      ground truth audit (audit-case)
  explain.py         case pages and indexes          site.py       the static site (build-site)
  tryout.py          `try`: a case without a model   submit.py     `submit`: a leaderboard file
  leaderboard.py     the leaderboard page
  llm.py             OpenAI-compatible client, model registry, scripted model for tests
  transforms/        language · policy · engagement (noise, events) · variant composition (setting)
  prompts/           agent instructions per locale · messages.yaml (all generated messages, 5 locales)
  customer.py        simulated client               session.py    client channel, events, transcript
  agents/            reference tool-calling harness · vendor CLI adapters
  mcp_bridge.py      MCP server giving CLI agents the client channel
  program.py         runs Program deliverables on hidden inputs, isolated (program_host.py inside)
  scoring/           extraction · clarification judges · policy score · report
configs/             policies/ engagement.yaml models.example.yaml experiments.starter.yaml (9 runs)
                     experiments.leaderboard.yaml (the current round) experiments.example.yaml (the full grid)
docker/              Dockerfile.agent: the image for isolated runs (tools and vendor CLIs only)
docs/                DIRECTION.md · SUBMITTING.md · specs/ (unbuilt cases) · <lang>/ (README, CONTRIBUTING and
                     SUBMITTING in zh, ko, ja, es)
leaderboard/         rounds.yaml (the rounds' rule seeds) · one JSON per submitted system (fdebench2 submit)
CONTRIBUTING.md      how to add a case, a translation, a review or a result
tests/
```

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
