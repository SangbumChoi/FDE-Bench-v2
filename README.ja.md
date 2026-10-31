# FDE-Bench v2

[English](README.md) · [中文](README.zh.md) · [한국어](README.ko.md) · [日本語](README.ja.md) · [Español](README.es.md)

フォワードデプロイドエンジニアリング（FDE）を担うエージェントのためのベンチマークです。**顧客の言語**（zh/en/ko/ja/es）、**会社方針**、**現実的な難易度**という軸にまたがって評価します。オープンモデルとクローズドモデルは OpenAI 互換の一つのプロトコルで、ベンダーのハーネス（Claude Code、Codex、Gemini CLI、OpenCode）は共通の MCP 顧客チャネルで比較します。自己完結しており、ほかのベンチマークのコードやデータには一切依存しません。

設計・採点・現状：[DESIGN.md](DESIGN.md)。方向性・関連研究・批判的検討：[docs/DIRECTION.md](docs/DIRECTION.md)。

**ケースを見る：** https://sangbumchoi.github.io/FDE-Bench-v2/ — ケースごとに1ページ（依頼、設定、ルール、隠れた要件、確認すべき事項、保存されたデータと正解、レビュー結果）です。`fdebench2 build-site` が `cases/*/*/explainer.html` から組み立て直し、push のたびに `gh-pages` ブランチへ公開します（`.github/workflows/pages.yml`）。

## セットアップ

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## 使い方

```bash
fdebench2 cases                                   # <field>/<role>, role title, task type, locales
fdebench2 validate-case cases/*/*/                # contract checks for every case
fdebench2 export-dataset cases/<field>/<role>     # store a case's data and ground truth in dataset/
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

`--difficulty` はケースの内容のティアを選び、`--rule-seed` は各ルールのパラメータをそれぞれの候補から抽選します（既定はケースの最初の公開ルールシード。それ以外の整数はすべて非公開シードで、その正解はどこにも保存されません）。ティアとルールシードの組み合わせごとに、一つのデータセットに対する別の正解があり、エージェントから見えるものはそのすべてで同じです。`--engagement`（full_spec / standard / messy）は仕事の渡し方（進め方）を変えます。[cases/README.md](cases/README.md#difficulty-one-dataset-tiers-and-rule-seeds) を参照してください。

すべてのコマンドに共通の軸：`--customer-locale {zh,en,ko,ja,es}`、`--agent-locale {zh,en,ko,ja,es}`、`--policy NAME`、`--difficulty {easy,medium,hard}`、`--rule-seed N`、`--engagement {full_spec,standard,messy}`、`--condition {full,interact,interact_req,hidden}`（アブレーション用の上書き）、`--seed N`。

## 構成

```
cases/<field>/<role>/  case.yaml, case.py, locales/<lang>/{request.md, requirements.md, targets.yaml},
                       dataset/ (data per locale, hidden inputs, ground truth per setting),
                       README.md (tiers, rule parameters, numbers per setting)
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
