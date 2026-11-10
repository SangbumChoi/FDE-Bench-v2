# FDE-Bench v2

[English](../../README.md) · [中文](../zh/README.md) · [한국어](../ko/README.md) · [日本語](README.md) · [Español](../es/README.md)

フォワードデプロイドエンジニアリング（FDE）を担うエージェントのためのベンチマークです。**顧客の言語**（zh/en/ko/ja/es）、**会社方針**、**現実的な難易度**という軸にまたがって評価します。オープンモデルとクローズドモデルは OpenAI 互換の一つのプロトコルで、ベンダーのハーネス（Claude Code、Codex、Gemini CLI、OpenCode）は共通の MCP 顧客チャネルで比較します。自己完結しており、ほかのベンチマークのコードやデータには一切依存しません。

設計・採点・現状：[DESIGN.md](../../DESIGN.md)。方向性・関連研究・批判的検討：[docs/DIRECTION.md](../DIRECTION.md)。ケース、翻訳、レビューで貢献する方法：[CONTRIBUTING.md](CONTRIBUTING.md)。

**ケースを見る：** https://sangbumchoi.github.io/FDE-Bench-v2/ — ケースごとに1ページ（依頼、設定、ルール、顧客だけが知っている要件、AIが確認すべき事実、保存されたデータと正解、レビュー結果）です。`fdebench2 build-site` が `cases/*/*/docs/<lang>/explainer.html` から組み立て直し、push のたびに `gh-pages` ブランチへ公開します（`.github/workflows/pages.yml`）。

**リーダーボード:** https://sangbumchoi.github.io/FDE-Bench-v2/leaderboard.html（`leaderboard/*.json` から生成）。参加方法は [docs/SUBMITTING.md](../SUBMITTING.md) を参照してください。

## クイックスタート

ケースが何を求め、どう採点されるかは、モデルも API キーもなしですぐに確認できます。

```bash
pip install -e .
fdebench2 try                                         # ケース一つ：依頼、渡されるファイル、点数の尺度、基準となる解答三つの点数
fdebench2 try --lang ko --submission my_deliverable/  # 自分の成果物を採点（5言語から選択）
```

モデルを動かすには、エンドポイントを一つ設定して小さなキャンペーンから始めます（9 回の実行：小さなケース 3 つ、medium、公開ルールシード）。

```bash
cp configs/models.example.yaml configs/models.yaml    # エンドポイント一つと API キーの環境変数
fdebench2 campaign configs/experiments.starter.yaml   # 9 回の実行、docker 不要
fdebench2 report runs-starter/
```

参加の方法は三つあります。**ケースを試す**（上）、リーダーボードに**結果を提出する**（[docs/SUBMITTING.md](../SUBMITTING.md)）、**ケース・翻訳・レビューで貢献する**（[CONTRIBUTING.md](CONTRIBUTING.md)）。

## ほかと何が違うか

FDE-Bench v2 は次の六つをあわせ持っています。どの項目もこのリポジトリのコードが検査しており、ほかのベンチマークが似たことをしている場合は表に記しました。

- **一つの世界と反実仮想の設定。** ケースごとにデータセットも依頼も一つです。難易度の段階 × ルールシードが顧客のルールとパラメータを決め、エージェントに見える内容はすべての設定でバイト単位まで同じです（`validate-case` が検査）。そのため点数は顧客の事実で決まります。非公開のルールシードの正解はどこにも保存されません。
- **二つの軸にまたがる、ネイティブに書かれた五つの言語：** 顧客の言語（依頼、データのラベル、ファイル名、顧客の回答）とエージェントへの指示の言語で、それぞれ zh / en / ko / ja / es。
- **事実ごとの正解の監査**（`audit-case`）：顧客の事実はどれも結果を左右しなければならず、近道は塞がれていなければならず、質問する価値を測り、模範解答を既知の最良解または上限と比べます。どのケースでも、文字どおりの解（依頼を書かれたとおりに実行したもの）は 0.2 以下でなければなりません。
- **事実ごとの「伝えられた → 把握した → 反映した」のファネル：** 顧客が言ったか、エージェントが質問して把握したか、成果物がそれを守っているか。
- **ルールの区分、会社方針、例外の手続き：** 物理的なルールは決して緩めません。それ以外は方針の例外手続きを通したときだけ緩められ、承認一回は指定したルール一つにだけ及びます。同じ実行を再実行せずにほかの方針で採点し直せます。
- **作業中に届く日付つきのイベントと圧力**（規制当局の通知、欠勤、VIP のメモ、インサイダー情報）はルール違反として採点し、**プログラムの成果物**は非公開の期間で一日ずつ実行します。

| | FDE-Bench v2 | τ-bench | τ^τ-Bench | Baidu FDE-Bench | FDE-Gym |
|---|---|---|---|---|---|
| 成果物 | ファイル、または非公開の入力で実行するプログラム | 対話しながらツールを呼ぶエージェント、対話の中で判定 | 顧客対応エージェント、非公開の模擬ユーザーで採点 | 実際の顧客プロジェクト 49 件の解（最適化、機械学習） | 顧客の本番システムの複製での納品、非公開のトラフィックで再生 |
| 顧客だけが知っている事実 | 模擬顧客が顧客だけが知っている要件から回答；事実ごとの確認事項 | シミュレーションのユーザーがタスクの目標を持ち、会話の中で伝える | 隠れた要件をもつ顧客（固定の事実 ID） | 模擬顧客が明かす | 台本付きの関係者 130 人以上；4 段階の依頼レベル |
| 同じ画面の上の反実仮想の設定 | 段階 × ルールシード、非公開シード | 固定タスク（小売 115、航空 50） | – | なし（固定データ、自ら挙げた限界） | 固定の課題と非公開の変形 |
| 言語 | 5、顧客 × エージェント | 1（英語） | – | – | 1 |
| 会社方針、例外の手続き | 方針 4 つ；承認一回で指定ルール一つ | ドメインのポリシー文書（Markdown）、例外手続きなし | – | – | – |
| 正解の監査 / 採択基準 | 事実ごとの監査（3 ケース）；全ケースで文字どおりの解 ≤ 0.2、点数の幅 ≥ 5% | – | – | – | 模範解答 ≥ 0.95、何もしなければ 0、文字どおりの解 ≤ 0.2、近道 ≤ 0.8 |
| 事実のファネル 伝えられた → 把握した → 反映した | 事実ごとにレポートに | – | – | –（ルールを質問しながら守らなかったエージェントを指摘） | –（得た主要な事実と改善幅の関係を報告） |
| ハーネスの比較 | 基準ループ + ベンダー CLI 4 つ、共通の MCP 顧客チャネル | 一つのツール呼び出しループでモデルを比較 | Claude Code、Codex、Kimi Code、OpenCode | – | 13 構成 |
| 採点 | 有効性の関門；品質は従来のやり方 0 から模範解答 1 まで、1 を超えても加点；Ask-F1；pass^k；方針ごとの重み | タスクごとに 0/1：最終的なDBの状態と必要な回答、pass^k | 作ったエージェントを非公開のユーザーで採点しオラクル基準と比較（構成ごとに 1 回、信頼区間なし） | 顧客が受け入れた解に対する品質、DSR、pass^3、Ask-F1、ブートストラップ信頼区間 | 正規化した改善幅、事故なら 0 以下、隠れた連絡コストを差し引く |

「–」：ほかのベンチマークについての出典である [docs/DIRECTION.md](../DIRECTION.md) の §2 に記載がないという意味で、その機能がないという意味ではありません。このリポジトリは τ-bench の pass^k 推定法を使っています。v2 はまだ実際の評価を一度も実行していないため、ファネルとハーネスの比較にはまだ数値がありません。

## セットアップ

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## 使い方

```bash
fdebench2 cases                                   # <field>/<role>, role title, task type, locales
# モデルやAPIキーなしでケースを試す（依頼、渡されるファイル、顧客だけが知る事実、点数の尺度、literal 解答・
# 従来のやり方・模範解答の点数。--submission DIR で自分の成果物も採点）:
fdebench2 try
fdebench2 try --case logistics/bakery_delivery_dispatcher --difficulty hard --lang ko --submission my_deliverable/
# キャンペーンの結果をリーダーボード用の提出ファイルにまとめる（docs/SUBMITTING.md）:
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
