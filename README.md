# FDE-Bench v2

A benchmark for forward-deployed-engineering agents across **customer languages** (zh/en/ko/ja/es),
**company policies** and **realistic difficulty**, with its own original cases. Open and closed models are
compared through one OpenAI-compatible protocol, and vendor harnesses (Claude Code, Codex, Gemini CLI,
OpenCode) through a shared MCP client channel. Fully independent of the FM-Agent repository; inspired by
[FDE-Bench v1](https://baidubce.github.io/FM-Agent/FDE-Bench/).

Design, scoring and status: [DESIGN.md](DESIGN.md).

## Setup

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## Use

```bash
fdebench2 cases                                   # cases, task type, domain, locales
fdebench2 validate-case cases/*/                  # contract checks for native cases
fdebench2 policies
# What an agent would get, without running one (Korean client, Japanese agent instructions, hard tier):
fdebench2 prepare --case logistics_bakery_routing --customer-locale ko --agent-locale ja \
    --policy startup_velocity --difficulty hard
# One run with the reference harness and any OpenAI-compatible model from models.yaml:
fdebench2 run --case logistics_bakery_routing --model qwen --customer-locale es
# Same with a vendor CLI:
fdebench2 run --case logistics_bakery_routing --harness claude_code --model claude-opus-5-5
# Re-score an existing run under other policies (no agent re-run):
fdebench2 score runs/reference--qwen/<variant> --policy regulated_strict --policy startup_velocity
# Campaigns and reports:
fdebench2 campaign configs/experiments.example.yaml --dry-run
fdebench2 report runs/
```

Axes on every command: `--customer-locale {zh,en,ko,ja,es}`, `--agent-locale {zh,en,ko,ja,es}`,
`--policy NAME`, `--difficulty {easy,medium,hard}`, `--condition {full,interact,interact_req,hidden}`
(ablation override), `--seed N`.

### Optional: FDE-Bench v1 as an external benchmark

```bash
fdebench2 fetch-v1                                 # pinned commit + data release, checksum-verified, into external/
fdebench2 cases --v1 external/fde-bench-v1         # v1 cases appear as v1-<id>
```

v1 material is CC BY-NC-ND 4.0: it stays in `external/` (git-ignored) and is never modified or committed.

## Layout

```
cases/<id>/          original cases: case.yaml, case.py, locales/<lang>/{request.md, requirements.md, targets.yaml}
fdebench2/
  cases.py           Case interface: NativeCase (cases/) and V1Case (external)
  casekit.py         helpers for case authors        validate.py   case contract checks
  llm.py             OpenAI-compatible client, model registry, scripted model for tests
  transforms/        language · policy · difficulty (noise, events) · variant composition
  prompts/           agent instructions per locale · messages.yaml (all generated messages, 5 locales)
  customer.py        simulated client               session.py    client channel, events, transcript
  agents/            reference tool-calling harness · vendor CLI adapters
  mcp_bridge.py      MCP server giving CLI agents the client channel
  scoring/           extraction · clarification judges · policy score · report · v1 evaluator shim
  v1_fetch.py        optional external v1 fetcher
configs/             policies/ difficulty.yaml models.example.yaml experiments.example.yaml case_rules/ (v1 only)
tests/
```
