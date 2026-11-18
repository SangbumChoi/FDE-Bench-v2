# リーダーボードへの結果の提出

誰でも、システム（モデルとハーネスの組み合わせ）を FDE-Bench v2 のリーダーボードに載せられます。キャンペーンを実行し、その結果を `fdebench2 submit` でまとめ、`leaderboard/<name>.json` というファイルを一つ追加するプルリクエストを作ります。サイト（`fdebench2 build-site`）は、[leaderboard/](../../leaderboard/) にあるすべてのファイルを、リーダーボードのページの1行として表示します。

## 0. まずケースを試す（モデルも API キーも不要）

```bash
pip install -e .
fdebench2 try                                   # 既定のケース、medium、最初の公開ルールシード
fdebench2 try --case logistics/bakery_delivery_dispatcher --difficulty hard --lang ko
fdebench2 try --submission my_deliverable/      # 自分の成果物フォルダを同じ方法で採点する
```

`try` は、AIへの依頼、AIが受け取るファイル、顧客だけが知っている事実の数、スコアの尺度を表示します。続いて、その設定で、ケースの「依頼を文字どおりに実行した解答」、従来のやり方、模範解答（と、指定したフォルダ）を既定の方針で採点します。やり取りはオフラインの提出と同じように採点します。質問をしていないので Ask-F1 は 0 ですが、既定の方針では Ask-F1 に重みがありません。ファイルを変換するモデルがないので、フォルダには、評価器が読む名前のとおりに成果物を置く必要があります（ケースの `case.yaml` の `deliverables:`。プログラムを納品するケースでは、エントリファイルを入れた `program/`）。

## 1. キャンペーンを実行する

まず様子を見るための、開発用の実行です（9回の実行、docker なし、公開ルールシード）。

```bash
cp configs/models.example.yaml configs/models.yaml      # エンドポイント一つと、その API キーの環境変数
fdebench2 campaign configs/experiments.starter.yaml
fdebench2 report runs-starter/
```

リーダーボードに載せるには、現在の**ラウンド**（[leaderboard/rounds.yaml](../../leaderboard/rounds.yaml)）を実行します。すべてのケースを、3つの難易度で、ラウンドの3つのルールシードについて、それぞれ3回ずつ、docker の中で実行します。合計351回の実行で、どのシステムでも同じです。`configs/experiments.leaderboard.yaml` がそのキャンペーンです。その中で自分のエージェントを指定し、ほかは何も変えないでください。

```yaml
agents:
  - {harness: reference, model: my-model}     # configs/models.yaml のエンドポイント名、またはベンダーのハーネス
```

```bash
fdebench2 campaign configs/experiments.leaderboard.yaml --dry-run   # 351 回の実行
fdebench2 campaign configs/experiments.leaderboard.yaml
fdebench2 report runs-leaderboard/              # まとめる前に表を確認する
```

## 2. 結果をまとめる

```bash
fdebench2 submit runs-leaderboard/ --name "My system" --model my-model-2026-10 --harness reference \
    --version 1.2 --flag web_tools=off --flag max_steps=400 --flag budget_usd_per_run=5 \
    --date 2026-11-06 --out leaderboard/my-system.json
```

| オプション | 意味 |
|---|---|
| `runs-leaderboard/` | キャンペーンの結果のディレクトリ（`<agent>/<run key>/result.json`） |
| `--name` | リーダーボードに表示するシステムの名前 |
| `--model`、`--harness` | リーダーボードに表示する内容（既定：実行に記録されたモデルとハーネス） |
| `--version` | システムのバージョン |
| `--flag KEY=VALUE` | 開示する実行条件。繰り返し指定できます（Web ツール、ステップ数とトークン数の上限、追加のツール、プロンプト） |
| `--date` | 提出日、`YYYY-MM-DD`（既定：UTC での今日） |
| `--agent` | ディレクトリに複数のエージェントの実行がある場合の、エージェントのラベル `<harness>--<model>` |
| `--cases` | ケースのフォルダ（既定は `cases/`）。ルールシードが公開か非公開かを見分け、ケースのハッシュを計算するために使います |
| `--rounds` | ラウンドのファイル（既定は `leaderboard/rounds.yaml`） |

書き出したファイルと1行の要約を表示します。要約の内容は、採点された実行の数、ケースの数、最終スコアの平均とその区間、状態（`ranked`（順位対象）とそのラウンド、または `development`（開発用）とその理由）です。

## 3. 送る

`leaderboard/<name>.json` を追加するプルリクエストを作ります（システムごとに1ファイル。システムの新しいバージョンは、そのファイルを置き換えます）。説明欄には、実行の条件を書いてください。ハーネスとそのバージョン、各種の上限、Web ツールが有効だったかどうか、そのほか読み手が再現するのに必要なことです。

## ルール

- **ラウンドを実行する。** 提出が順位対象になるのは、[leaderboard/rounds.yaml](../../leaderboard/rounds.yaml) のラウンド一つをすべて実行した場合だけです。すべてのケースを、ラウンドの各ティアと各ルールシードで、ラウンドの共通条件（顧客もエージェントも英語、`baseline` の方針、`standard` の進め方）のもとで実行します。ラウンドではどのシステムも同じ設定に答えるので、結果を比べることができ、誰も自分でシードを選びません。ラウンドのルールシードは、どのケースの公開ルールシードにも含まれません。その正解はリポジトリのどこにも保存されていません。新しいラウンドには新しいシードを使い、リーダーボードはラウンドごとに分けて表示します。
- **それ以外はすべて `development`（開発用）。** 公開ルールシードでの実行、自分で選んだシードでの実行、一部のケースやティアだけの実行、ほかの言語や方針での実行も歓迎します。これらは理由を添えて、順位なしで表示されます。
- **試行は3回以上。** どの設定も3回以上実行する必要があります（`trials: 3`）。それより少ない提出は `development` です。
- **Web ツールは切るか、ログを残す。** 実行中にケースをオンラインで調べてはいけません。ハーネスに Web ツールがある場合は、切る（`--flag web_tools=off`）か、ログを残してその旨を示します（`--flag web_tools=logged`）。
- **ハーネスと上限を開示する。** ハーネスの名前とバージョン、そしてすべての上限（ステップ数、トークン数、金額、実行時間）をフラグとして示します。
- **公開されたままのベンチマーク。** 変更していないチェックアウトで実行します。提出ファイルにはコミットと各ケースのファイルのハッシュが記録されるので、ほかのバージョンのケースでの結果とは比較されません。
- **手作業で編集しない。** JSON は `fdebench2 submit` が書き出したままのものです。
- **結果は自己申告です。** 採点器と模範解答はこのリポジトリのコードなので、ラウンドの正解は、実行すれば誰でも計算できます。エージェントはそれをしてはいけません。サンドボックスの中のエージェントには、自分のワークスペースしか見えません（`isolation: strict`）。自己申告のリーダーボードがどれもそうであるように、このリーダーボードもそれを前提にしています。説明から再現できない提出は、削除されることがあります。

## 形式

JSON オブジェクト一つで、`"format": "fdebench2-submission/1"` です。

| フィールド | 内容 |
|---|---|
| `kind` | `"system"`（提出）または `"anchors"`（ケース自身の基準。下記） |
| `example` | 例のファイルでだけ `true` |
| `system` | `name`、`model`、`harness`、`version`、`agent_label`（実行の `<harness>--<model>`）、`max_steps`、`flags`（`{key: value}`）、`date` |
| `benchmark` | `framework_version`、`git_commit`、`git_dirty`（`cases/`、`fdebench2/`、`configs/` の下にコミットしていない変更があるか）、`cases`：`{ケース ID: そのファイルのハッシュ}`（実行のフィンガープリントが使うハッシュ：ドキュメントと保存された監査結果を除く、ケースのファイル） |
| `seeds` | `kind`：`private`、`public`、`mixed`、`none` のいずれか。加えて、使った `public` と `private` のルールシード |
| `trials` | バリアント（試行番号以外が同じ実行の組）ごとの試行回数のうち、最も少ないもの |
| `status` | `ranked`（順位対象：ラウンド一つをすべて実行し、`trials` ≥ 3）または `development`（開発用）。基準のファイルでは `anchor` |
| `round` | 順位対象の提出が実行したラウンドの id。それ以外は null |
| `status_reasons` | 提出が順位対象にならない理由 |
| `aggregate` | 下記の平均。それぞれ `{mean, ci: [low, high], n_cases}`。加えて `n_runs`、`n_scored`、`n_cases`、`statuses`（状態ごとの実行数） |
| `runs` | 実行ごとに1レコード（下記） |

**集計（aggregate）。** `fdebench2 report` が計算するのと同じ、ケース単位のマクロ平均です。ケースの中ではどのルールシードも同じ重みで（一つのシードの実行の平均を取り、次にシードの平均を取ります）、そのうえでどのケースも同じ重みです。`ci` はケースについての 95% ブートストラップ区間です（再標本化 2000 回、固定シード）。ハーネスまたはインフラのエラーで終わった実行（`harness_error`、`infra_error`）は `statuses` に数え、どの平均にも含めません。

| 指標 | 意味 |
|---|---|
| `final` | その実行の方針での総合スコア（必須の条件を一つでも満たさなければ 0） |
| `validity` | 成果物がルールに一つも違反しなかった実行の割合 |
| `quality` | 正規化品質：そのケースの従来のやり方が 0、模範解答が 1（無効なら 0） |
| `ask_f1` | 顧客だけが知っている事実についての Ask-F1（顧客に質問できた実行が対象） |
| `enforced_share` | 顧客だけが知っている事実のうち、成果物に反映された割合。分母は、ケースの直接の検査が測った事実 |
| `cost_usd`、`total_tokens` | 実行ごとの値：ソルバー、顧客、抽出器、判定者の合計（CLI ソルバー自身のトークンはまだ読み取っていません） |

**実行（runs）。** 各レコードの項目：`case`、`tier`、`rule_seed`、`seeds`（`public`、`private`、このバージョンにないケースなら `unknown`、または null）、`trial`、`noise_seed`、`customer_locale`、`agent_locale`、`policy`、`engagement`、`condition`、`world_seed`、`status`、`final`、`valid`、`quality`、`ask_f1`、`targets`（AIが確認すべき事実のファネル：事実の数 `n` と、`revealed`（顧客が述べた）、`learned`（質問で知った）、`enforced`（成果物に反映した）のそれぞれについて、通過した数と測定した数 `<stage>_measured`）、`enforced_share`、`cost_usd`、`total_tokens`、そしてその実行自身の `fingerprint`。

**基準（anchors）。** `kind: "anchors"` のファイルには、各ケースの「依頼を文字どおりに実行した解答」、従来のやり方、模範解答が入ります。`fdebench2 try` と同じようにオフラインで採点したもので、`aggregate` の代わりに `anchors: {literal | baseline | reference: aggregate}` を持ち、各実行に `anchor` フィールドがあります。リーダーボードはこれらを基準行として表示し、順位は付けません。[leaderboard/anchors-2026-11.json](../../leaderboard/anchors-2026-11.json) には、現在のラウンドの基準が入っています。ラウンドのティアとルールシードに対して `fdebench2 anchors --round 2026-11 --out leaderboard/anchors-2026-11.json` で書き出したもので、基準行と順位対象のシステムは同じ設定に答えています。`--round` を付けなければ、このコマンドは公開ルールシードで採点し、ファイルに例の印を付けます。
