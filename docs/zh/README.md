[English](../../README.md) · [中文](README.md) · [한국어](../ko/README.md) · [日本語](../ja/README.md) · [Español](../es/README.md)

# FDE-Bench v2

一个面向前线部署工程（forward-deployed engineering，FDE）智能体的基准测试，覆盖不同的**客户语言**（zh/en/ko/ja/es）、
**公司政策**和**贴近现实的难度**。开源模型和闭源模型通过同一套 OpenAI 兼容协议进行比较，厂商的智能体框架（harness：
Claude Code、Codex、Gemini CLI、OpenCode）则通过共享的 MCP 客户沟通通道接入。本项目自成一体：不依赖任何其他基准测试的
代码或数据。

设计、评分与当前进展：[DESIGN.md](../../DESIGN.md)。研究方向、相关工作与评析：[docs/DIRECTION.md](../DIRECTION.md)。

**浏览案例：** https://sangbumchoi.github.io/FDE-Bench-v2/ —— 每个案例一页（需求、设置、规则、隐藏需求、应问事项、
保存的数据与答案、评审发现），由 `fdebench2 build-site` 根据 `cases/*/*/docs/<lang>/explainer.html` 重新生成，并在每次推送时发布到
`gh-pages` 分支（`.github/workflows/pages.yml`）。

## 致谢

感谢本基准所借鉴的研究的作者：

- **FDE-Gym**（Yang et al., *FDE-Gym: The Last Mile of AI Delivery*, arXiv 2610.22350；
  [fde-gym.com](https://fde-gym.com/paper/)、[案例](https://huggingface.co/datasets/DeepLethe/FDE-Gym)、
  [测试框架](https://github.com/deeplethe/fde-gym)）。它的四级需求说明、带联系成本的脚本化利益相关方、在未公开的生产流量上
  回放评分，以及准入基准（什么都不做记 0 分，参考答案记 1 分，按字面理解需求的答案和捷径只能得低分），为本仓库的标准答案
  审查提供了参考。
- **Baidu FDE-Bench**（arXiv 2610.14539）：首先提出了前线部署工程师（FDE）的框架，以及 v2 沿用的指标术语（相对参考答案的
  质量、DSR、Ask-F1、pass^k）。
- **τ^τ-Bench**（arXiv 2609.04611）和 **τ-bench**（arXiv 2406.12045）：用未公开的用户评估所构建智能体的设计，以及 pass^k
  估计方法。

v2 与它们不共享任何代码或数据：这里的每个案例都是由种子生成的原创案例，有单独使用条款的 FDE-Gym 案例未被使用。更多相关工作
见 [docs/DIRECTION.md](../DIRECTION.md) 第 2 节和第 9 节。

## 安装

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## 使用

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

`--difficulty` 选择案例的内容层级，`--rule-seed` 为每个规则参数从其候选值中抽取一个值（默认取案例的第一个公开规则种子；
其他任何整数都是非公开种子，其答案不保存在任何地方）。每个层级与规则种子的组合都是同一份数据集的另一套标准答案，而智能体在所有
设置下看到的内容完全相同。`--engagement`（full_spec / standard / messy）改变工作的交接方式。见
[cases/README.md](../../cases/README.md#difficulty-one-dataset-tiers-and-rule-seeds)。

每条命令都可用的维度：`--customer-locale {zh,en,ko,ja,es}`、`--agent-locale {zh,en,ko,ja,es}`、`--policy NAME`、
`--difficulty {easy,medium,hard}`、`--rule-seed N`、`--engagement {full_spec,standard,messy}`、
`--condition {full,interact,interact_req,hidden}`（消融实验用的覆盖参数）、`--seed N`。

## 目录结构

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
