[English](README.md) · [中文](README.zh.md) · [한국어](README.ko.md) · [日本語](README.ja.md) · [Español](README.es.md)

# FDE-Bench v2

一个面向前线部署工程（forward-deployed engineering，FDE）智能体的基准测试，覆盖不同的**客户语言**（zh/en/ko/ja/es）、
**公司政策**和**贴近现实的难度**。开源模型和闭源模型通过同一套 OpenAI 兼容协议进行比较，厂商的智能体框架（harness：
Claude Code、Codex、Gemini CLI、OpenCode）则通过共享的 MCP 客户沟通通道接入。本项目自成一体：不依赖任何其他基准测试的
代码或数据。

设计、评分与当前进展：[DESIGN.md](DESIGN.md)。研究方向、相关工作与评析：[docs/DIRECTION.md](docs/DIRECTION.md)。

**浏览案例：** https://sangbumchoi.github.io/FDE-Bench-v2/ —— 每个案例一页（需求、设置、规则、隐藏需求、应问事项、
保存的数据与答案、评审发现），由 `fdebench2 build-site` 根据 `cases/*/*/explainer.html` 重新生成，并在每次推送时发布到
`gh-pages` 分支（`.github/workflows/pages.yml`）。

## 安装

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## 使用

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

`--difficulty` 选择案例的内容层级，`--ruleset`（A/B/C）选择其规则参数：同一份数据集对应九套标准答案，而智能体在所有设置下
看到的内容完全相同。`--engagement`（full_spec / standard / messy）改变工作的交接方式。见
[cases/README.md](cases/README.md#difficulty-one-dataset-nine-ground-truths)。

每条命令都可用的维度：`--customer-locale {zh,en,ko,ja,es}`、`--agent-locale {zh,en,ko,ja,es}`、`--policy NAME`、
`--difficulty {easy,medium,hard}`、`--ruleset {A,B,C}`、`--engagement {full_spec,standard,messy}`、
`--condition {full,interact,interact_req,hidden}`（消融实验用的覆盖参数）、`--seed N`。

## 目录结构

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
