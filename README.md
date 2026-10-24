# FDE-Bench v2

Benchmark for forward-deployed-engineering agents across **customer languages**, **company policies**
and **realistic difficulty**, built as transforms over the 49 real customer cases of
[FDE-Bench v1](https://baidubce.github.io/FM-Agent/FDE-Bench/). It compares open and closed models
through one OpenAI-compatible protocol, and vendor harnesses (Claude Code, Codex, Gemini CLI, OpenCode)
through a shared MCP client channel.

Design, scoring and status: [DESIGN.md](DESIGN.md).

## Setup

```bash
pip install -e '.[mcp,dev]'
# v1 cases and data (CC BY-NC-ND 4.0 — keep them out of this repo; v1/ is git-ignored)
git clone --depth 1 https://github.com/baidubce/FM-Agent.git /tmp/fm && mv /tmp/fm/FDE-Bench v1/FDE-Bench
python v1/FDE-Bench/scripts/fetch_data.py      # restores case/*/data from the v1 release
# evaluator dependencies used by some v1 cases
pip install numpy pandas openpyxl scipy scikit-learn lightgbm shapely networkx
cp configs/models.example.yaml configs/models.yaml   # then set endpoints and API-key env vars
```

## Use

```bash
fdebench2 cases                                   # 49 cases, targets, data files
fdebench2 policies
# Look at what an agent would get, without running one:
fdebench2 prepare --case 010_retail_replenishment_transfer \
    --customer-locale ko --agent-locale en --policy startup_velocity --difficulty hard
# One run with the reference harness and any OpenAI-compatible model from models.yaml:
fdebench2 run --case 002_city_delivery_route_planning --model qwen --customer-locale ja \
    --docker-image fde-bench-runner:v1
# Same with a vendor CLI:
fdebench2 run --case 002_city_delivery_route_planning --harness claude_code --model claude-opus-5-5
# Re-score an existing run under other policies (no agent re-run):
fdebench2 score runs/reference--qwen/<variant> --policy regulated_strict --policy startup_velocity
# A campaign and its report:
fdebench2 campaign configs/experiments.example.yaml --dry-run
fdebench2 campaign configs/experiments.example.yaml
fdebench2 report runs/
```

Axes on every command: `--customer-locale {source,en,ko,ja,es}`, `--agent-locale {en,zh,ko,ja,es}`,
`--policy NAME`, `--difficulty {easy,medium,hard}`, `--condition {full,interact,interact_req,hidden}`
(ablation override), `--seed N`.

## Layout

```
fdebench2/
  llm.py              OpenAI-compatible client, model registry, scripted model for tests
  cases.py            read-only v1 case loader
  transforms/         language · policy · difficulty (noise, events) · variant composition
  prompts/agent/      agent instructions in en / zh / ko / ja / es (hand-written)
  customer.py         simulated client (persona, locale)
  session.py          client channel, events, exceptions, transcript
  agents/             reference tool-calling harness · vendor CLI adapters
  mcp_bridge.py       MCP server giving CLI agents the client channel
  scoring/            submission extraction · v1 evaluator shim · clarification judges · policy score · report
  case_hooks/         per-case relaxed re-scoring (rule bending)
configs/
  policies/ difficulty.yaml case_rules/ models.example.yaml experiments.example.yaml
tests/                synthetic v1-format fixture case + end-to-end tests
```

## License note

v2 code: to be decided by the repository owner. v1 data is CC BY-NC-ND 4.0. Translations, noisy copies
and run directories derived from it are written to `.cache/` and `runs/`, are git-ignored, and must not be
redistributed. See DESIGN.md §2.
