# FDE-Bench v2

[English](../../README.md) · [中文](../zh/README.md) · [한국어](../ko/README.md) · [日本語](README.md) · [Español](../es/README.md)

フォワードデプロイドエンジニアリング（FDE）を担うエージェントのためのベンチマークです。**顧客の言語**（zh/en/ko/ja/es）、**会社方針**、**現実的な難易度**という軸にまたがって評価します。オープンモデルとクローズドモデルは OpenAI 互換の一つのプロトコルで、ベンダーのハーネス（Claude Code、Codex、Gemini CLI、OpenCode）は共通の MCP 顧客チャネルで比較します。自己完結しており、ほかのベンチマークのコードやデータには一切依存しません。

設計・採点・現状：[DESIGN.md](../../DESIGN.md)。方向性・関連研究・批判的検討：[docs/DIRECTION.md](../DIRECTION.md)。

**ケースを見る：** https://sangbumchoi.github.io/FDE-Bench-v2/ — ケースごとに1ページ（依頼、設定、ルール、隠れた要件、確認すべき事項、保存されたデータと正解、レビュー結果）です。`fdebench2 build-site` が `cases/*/*/docs/<lang>/explainer.html` から組み立て直し、push のたびに `gh-pages` ブランチへ公開します（`.github/workflows/pages.yml`）。

## 謝辞

このベンチマークが学んだ研究の著者の皆さまに感謝します。

- **FDE-Gym**（Yang et al., *FDE-Gym: The Last Mile of AI Delivery*, arXiv 2610.22350;
  [fde-gym.com](https://fde-gym.com/paper/)、[ケース](https://huggingface.co/datasets/DeepLethe/FDE-Gym)、
  [ハーネス](https://github.com/deeplethe/fde-gym)）。4段階の依頼レベル、連絡コストのある台本付きの関係者、
  非公開の本番トラフィックでの再生による採点、採択基準（何もしなければ0、模範解答が1、依頼を文字どおりに読んだ解答と
  近道は低い点数）が、このリポジトリの正解の監査の参考になりました。
- **Baidu FDE-Bench**（arXiv 2610.14539）：フォワードデプロイドエンジニア（FDE）という枠組みと、v2 が引き継ぐ指標の
  用語（模範解答に対する品質、DSR、Ask-F1、pass^k）を最初に示しました。
- **τ^τ-Bench**（arXiv 2609.04611）と **τ-bench**（arXiv 2406.12045）：作ったエージェントを非公開のユーザーで採点する
  設計と pass^k の推定法。

v2 はこれらとコードもデータも共有していません。すべてのケースはシードから生成した独自のもので、独自の利用条件がある
FDE-Gym のケースは使っていません。関連研究は [docs/DIRECTION.md](../DIRECTION.md) の §2 と §9 にあります。

## セットアップ

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## 使い方

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

`--difficulty` はケースの内容のティアを選び、`--rule-seed` は各ルールのパラメータをそれぞれの候補から抽選します（既定はケースの最初の公開ルールシード。それ以外の整数はすべて非公開シードで、その正解はどこにも保存されません）。ティアとルールシードの組み合わせごとに、一つのデータセットに対する別の正解があり、エージェントから見えるものはそのすべてで同じです。`--engagement`（full_spec / standard / messy）は仕事の渡し方（進め方）を変えます。[cases/README.md](../../cases/README.md#difficulty-one-dataset-tiers-and-rule-seeds) を参照してください。

すべてのコマンドに共通の軸：`--customer-locale {zh,en,ko,ja,es}`、`--agent-locale {zh,en,ko,ja,es}`、`--policy NAME`、`--difficulty {easy,medium,hard}`、`--rule-seed N`、`--engagement {full_spec,standard,messy}`、`--condition {full,interact,interact_req,hidden}`（アブレーション用の上書き）、`--seed N`。

## 構成

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
