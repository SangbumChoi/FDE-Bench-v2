# FDE-Bench v2 への貢献

[English](../../CONTRIBUTING.md) · [中文](../zh/CONTRIBUTING.md) · [한국어](../ko/CONTRIBUTING.md) · [日本語](CONTRIBUTING.md) · [Español](../es/CONTRIBUTING.md)

ご協力ありがとうございます。このページでは、何を貢献できるか、新しいケースの作り方、ケースが満たすべき基準、プルリクエスト（PR）に必要なことを説明します。背景：[README](README.md)、[DESIGN.md](../../DESIGN.md) §3 のケース形式、[cases/README.md](../../cases/README.md) のカタログ、[docs/DIRECTION.md](../DIRECTION.md) §5 の新しいケースの設計ルール。

## 貢献できること

| 貢献 | 内容 | 始め方 |
|---|---|---|
| **新しいケース** | カタログ（[cases/README.md](../../cases/README.md)、仕様は [docs/specs/](../specs/README.md)）の役割を一つ、ケースの規約どおりに構築する | *Case proposal* テンプレートで issue を作り、下の手順に進む |
| **翻訳またはネイティブレビュー** | ある言語のテキストの修正やレビュー：`locales/<lang>/`（request、requirements、targets、summary、explainer.yaml）、`docs/<lang>/README.md` と `REVIEW.md`、`fdebench2/prompts/*.yaml`、`docs/<lang>/` | 母語について PR を作り、レビューしたファイルを書く |
| **顧客の回答のレビュー** | 監査済みケースの `CLIENT_REVIEW.md` に判定を書く：各言語の顧客が根拠にする一節は、自然な質問に正しく、過不足なく答えているか | 下の節 |
| **バグ報告** | 誤った採点、検証の抜け、クラッシュ、壊れたページ、ルールを漏らしたり作り出したりする顧客 | *Bug report* テンプレートで issue を作る |
| **結果の提出** | あるモデルやハーネスでこのベンチマークを実行した結果 | [docs/SUBMITTING.md](../SUBMITTING.md) |

### 顧客の回答のレビュー

監査済みのケース（case.yaml に `audited: true`）には、case.yaml の隣に `CLIENT_REVIEW.md` があります。事実ごとに、エンジニアがするはずの質問、各言語の顧客が答えるときに根拠にする `requirements.md` の行、機械による事前チェックが載っています。`Reviewer verdict:` の行はまだすべて空です。

- 母語として読める言語の一節を読みます。
- `Reviewer verdict:` の行に `OK` か `Problem`、確認した言語を書き、問題があれば内容を書きます。数字の誤りや欠け、あいまいな答え、聞かれていないことまで答える一節などです。
- `CLIENT_REVIEW.md` は生成されるファイルです（`make_client_review.py` が書き直します）。判定は単独の PR で送り、その PR ではファイルを生成し直さないでください。要件そのものの修正は別の PR にします。

## ケースの作業手順

```bash
fdebench2 new-case <field>/<role>             # add --program when the deliverable is code run on hidden inputs
# write case.yaml and case.py, then every text in all five locales (zh, en, ko, ja, es)
fdebench2 export-dataset cases/<field>/<role> # store data and answers in dataset/; also writes the explainer pages
fdebench2 validate-case cases/<field>/<role>  # the case contract, on the public world and world seeds 1-3
fdebench2 audit-case cases/<field>/<role>     # the ground truth audit, stored in dataset/audit.json
python -m pytest -q                           # the repository's tests
```

1. **提案。** *Case proposal* テンプレートで issue を作ります。役割、顧客、成果物、隠れた事実と、それぞれの事実が答えをどう変えるかを書きます。カタログから役割を選ぶか、どの分野（`cases/fields.yaml`）に属するかを書きます。
2. **ひな形を作る。** `fdebench2 new-case` が case.yaml、case.py、五つの言語、言語ごとの README を書き出し、必須の部分をすべて TODO にします。docstring に挙がっている構築済みのケース（`fdebench2/scaffold.py`）のパターンを参考にしてください。
3. case.py に**世界と採点器を書く：** `build_world`、`write_data`、`reference_solution`、`baseline_solution`、`literal_solution`、`score`、`violating_examples`。監査を受けるには `ablations`、`shortcuts`、`robust_solution`、`best_known_solution` または `objective_bound` も必要です（[DESIGN.md](../../DESIGN.md) §3）。
4. **五つの言語でテキストを書く：** `locales/<lang>/request.md`、`requirements.md`、`targets.yaml`、`summary.yaml`、`explainer.yaml`（en 以外）と `docs/<lang>/README.md`。逐語訳ではなく各言語で自然に書き、確認事項の id、`{{param}}` のプレースホルダー、設定のマーカーはすべての言語でそろえます。
5. `fdebench2 export-dataset` で**書き出し**、`fdebench2 validate-case` が問題を報告しなくなるまで**検証**します。警告は直すか、ケースの `docs/en/REVIEW.md` に理由を書きます。
6. `fdebench2 audit-case` で**監査**します（10〜40分）。合格したら `audited: true` にして、`validate-case` をもう一度実行します。監査済みのケースは、監査結果がないか古いと検証に失敗します。
7. **ケースをカタログに加え**（[cases/README.md](../../cases/README.md)）、ホームページを生成し直し（`fdebench2 explain-case cases/<field>/<role>`）、テストを実行してから PR を作ります。

## ケースが満たすべき基準

- `fdebench2 validate-case` が、公開ワールドとワールドシード 1〜3 で問題を報告しない。
- すべての公開設定で品質の尺度の幅が 5% 以上：|模範解答 − 基準解| / |模範解答| ≥ 0.05。
- 文字どおりの解（エージェントに見えるものだけで、依頼を書かれたとおりに実行したもの）は、すべての公開設定で無効か 0.2 以下。
- エージェントに見えるもの（依頼とファイル）はすべての設定でバイト単位まで同じで、違うのは顧客の事実だけ。
- すべてのルールに区分があり、緩めてよい習慣であるビジネスルールはちょうど一つ。
- 監査済みのケース：顧客の事実はどれも結果を左右し（その事実だけを読み違えると成果物が無効になるか、その事実が効く各段階で品質が 0.10 以上下がる）、近道はすべて塞がれ（無効か 0.5 以下）、質問する価値は段階ごとに 0.10 以上。
- 実在の個人情報を含まない：人、会社、住所、数字はすべて生成したもの。
- 独自の内容だけ：利用条件が認めていないほかのベンチマーク、データセット、文書から写したものはない。FDE-Bench v2 はほかのベンチマークとコードもデータも共有しない。

## PR のチェックリスト

- [ ] PR 一つにテーマ一つ（ケース一つ、翻訳一つ、判定のまとまり一つ、修正一つ）。
- [ ] 触れたすべてのケースが `fdebench2 validate-case` に合格する。
- [ ] ケースのコードやテキストを変えたあと `fdebench2 export-dataset` を実行し直し、`dataset/` をコミットした。
- [ ] 監査済みのケース：ソースが変わったら `fdebench2 audit-case` を実行し直し、`dataset/audit.json` が最新である。
- [ ] 新しいケース：品質の尺度の幅 ≥ 5%、文字どおりの解 ≤ 0.2、エージェントに見えるものがすべての設定で同じ。
- [ ] 五つの言語を一緒に更新し、できる範囲でネイティブの表現を確認した。
- [ ] 実在の個人情報なし、独自の内容だけ。
- [ ] ケースを追加または改名したら、カタログとホームページを生成し直した（`fdebench2 explain-case`）。
- [ ] `python -m pytest -q` が通る。
- [ ] コミットメッセージは簡潔に：何を、なぜ変えたか。
