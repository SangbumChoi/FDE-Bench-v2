# 向排行榜提交结果

任何人都可以把一个系统（模型加智能体框架，即 harness）放上 FDE-Bench v2 排行榜：运行一次评测活动（campaign），用 `fdebench2 submit` 把结果打包，再提交一个只新增一个文件 `leaderboard/<name>.json` 的拉取请求（PR）。网站（`fdebench2 build-site`）把 [leaderboard/](../../leaderboard/) 中的每个文件显示为排行榜页面上的一行。

## 0. 先试一个案例（不需要模型，也不需要 API 密钥）

```bash
pip install -e .
fdebench2 try                                   # 默认案例，medium，第一个公开规则种子
fdebench2 try --case logistics/bakery_delivery_dispatcher --difficulty hard --lang ko
fdebench2 try --submission my_deliverable/      # 用同样的方式给你自己的交付物文件夹评分
```

`try` 会打印 AI 收到的需求、它拿到的文件、只有客户知道的事实有多少条以及评分尺度，然后在该设置下按默认政策给案例的按字面执行需求的答案、客户原来的做法和参考答案（以及你的文件夹）评分。交互部分按离线提交计分：没有提问，所以 Ask-F1 为 0，而默认政策不给它权重。由于没有模型来转换文件，你的文件夹里的交付物必须使用评估器读取的文件名（案例 `case.yaml` 中的 `deliverables:`；程序类案例则是 `program/` 加入口文件）。

## 1. 运行一次评测活动

先跑一次看看，仅供开发用（9 次运行，不用 docker，公开规则种子）：

```bash
cp configs/models.example.yaml configs/models.yaml      # 一个端点及其 API 密钥环境变量
fdebench2 campaign configs/experiments.starter.yaml
fdebench2 report runs-starter/
```

要上排行榜，就运行当前这一**轮**（[leaderboard/rounds.yaml](../../leaderboard/rounds.yaml)）：每个案例、三个难度、这一轮的三个规则种子，各试验三次，在 docker 中运行。一共 351 次运行，每个系统都一样。`configs/experiments.leaderboard.yaml` 就是这次评测活动；在里面填上你的智能体，其他都不要改：

```yaml
agents:
  - {harness: reference, model: my-model}     # configs/models.yaml 中的端点名称，或某个厂商的智能体框架
```

```bash
fdebench2 campaign configs/experiments.leaderboard.yaml --dry-run   # 351 次运行
fdebench2 campaign configs/experiments.leaderboard.yaml
fdebench2 report runs-leaderboard/              # 打包之前先检查这些表
```

## 2. 打包结果

```bash
fdebench2 submit runs-leaderboard/ --name "My system" --model my-model-2026-10 --harness reference \
    --version 1.2 --flag web_tools=off --flag max_steps=400 --flag budget_usd_per_run=5 \
    --date 2026-11-06 --out leaderboard/my-system.json
```

| 选项 | 含义 |
|---|---|
| `runs-leaderboard/` | 评测活动的结果目录（`<agent>/<run key>/result.json`） |
| `--name` | 系统在排行榜上的名称 |
| `--model`、`--harness` | 排行榜上显示的内容（默认：运行记录自己的模型和智能体框架） |
| `--version` | 你的系统的版本 |
| `--flag KEY=VALUE` | 要披露的一项配置；可重复使用（网络工具、步数和 token 预算、额外工具、提示词） |
| `--date` | 提交日期，`YYYY-MM-DD`（默认：今天，UTC） |
| `--agent` | 目录里有多个智能体的运行结果时，指定智能体标签 `<harness>--<model>` |
| `--cases` | 案例文件夹（默认 `cases/`），用来区分公开和非公开规则种子，并计算案例的哈希 |
| `--rounds` | 轮次文件（默认 `leaderboard/rounds.yaml`） |

它会打印写出的文件和一行摘要：计分的运行数、案例数、最终得分的平均值及其区间，以及状态（`ranked` 即参与排名，并附所属的轮次；或 `development` 即开发用，并附原因）。

## 3. 发送

提交一个新增 `leaderboard/<name>.json` 的 PR（每个系统一个文件；系统出了新版本，就替换原来的文件）。在 PR 说明里写清这些运行是怎么做的：智能体框架及其版本、各项预算、网络工具是否开启，以及读者复现结果所需的其他信息。

## 规则

- **运行完整的一轮。** 只有完整运行了 [leaderboard/rounds.yaml](../../leaderboard/rounds.yaml) 中某一轮的提交才参与排名：每个案例、这一轮的每个层级和每个规则种子，并按这一轮规定的条件运行（客户和智能体都用英语、`baseline` 政策、`standard` 交接方式）。同一轮里每个系统面对的设置都相同，所以结果可以相互比较，也没有人能自己挑种子。这一轮的规则种子都在各案例的公开规则种子之外：它们的答案不保存在仓库的任何地方。新的一轮会换新的种子，排行榜把每一轮分开列出。
- **其余都是 `development`。** 用公开规则种子、用你自己选的种子、只跑部分案例或层级，或者换一种语言或政策的运行，我们都欢迎；它们会显示出来，但不参与排名，并注明原因。
- **试验次数 ≥ 3。** 每个设置至少运行 3 次（`trials: 3`）；少于 3 次，提交就是 `development`。
- **网络工具关闭，或留有日志。** 运行时不得上网查找案例。如果智能体框架带有网络工具，请关闭（`--flag web_tools=off`），或保留其日志并注明（`--flag web_tools=logged`）。
- **披露智能体框架和预算。** 用 flag 写明智能体框架及其版本，以及每一项预算（步数、token、美元、实际耗时）。
- **按发布的基准运行。** 在未经修改的代码检出（checkout）上运行。提交文件会记录所用的提交（commit）和每个案例文件的哈希，所以在其他案例版本上得到的结果不会放在一起比较。
- **不得手工修改。** JSON 就是 `fdebench2 submit` 写出的内容。
- **结果由提交者自行报告。** 评分器和参考答案都是本仓库里的代码，所以任何运行它的人都能算出某一轮的答案。智能体不能这样做：在沙箱里它只能看到自己的工作区（`isolation: strict`）。和其他自行报告的排行榜一样，本排行榜依赖这一点；无法按其说明复现的提交可能会被移除。

## 格式

一个 JSON 对象，`"format": "fdebench2-submission/1"`：

| 字段 | 内容 |
|---|---|
| `kind` | `"system"`（一次提交）或 `"anchors"`（案例自己的基准点，见下文） |
| `example` | 只有示例文件为 `true` |
| `system` | `name`、`model`、`harness`、`version`、`agent_label`（运行记录的 `<harness>--<model>`）、`max_steps`、`flags`（`{key: value}`）、`date` |
| `benchmark` | `framework_version`、`git_commit`、`git_dirty`（`cases/`、`fdebench2/` 或 `configs/` 下有未提交的改动）、`cases`：`{case id: hash of its files}`（案例 ID 对应其文件的哈希，即运行指纹所用的哈希：案例的文件，不含其文档和保存的审查结果） |
| `seeds` | `kind`：`private`、`public`、`mixed` 或 `none`，以及用到的 `public`（公开）和 `private`（非公开）规则种子 |
| `trials` | 各变体中最少的试验次数 |
| `status` | `ranked`（完整的一轮，且 `trials` ≥ 3）或 `development`；基准点为 `anchor` |
| `round` | 参与排名的提交所运行的那一轮的 id，否则为 null |
| `status_reasons` | 提交不参与排名的原因 |
| `aggregate` | 下面各项的平均值，每项为 `{mean, ci: [low, high], n_cases}`，另有 `n_runs`、`n_scored`、`n_cases` 和 `statuses`（各状态的运行数） |
| `runs` | 每次运行一条记录（见下文） |

**汇总（aggregate）。** 按案例宏平均，与 `fdebench2 report` 的算法相同：在一个案例内，每个规则种子权重相同（先对一个种子的各次运行取平均，再对各种子取平均），然后每个案例权重相同。`ci` 是对案例做自助法（bootstrap）得到的 95% 区间（重抽样 2000 次，固定种子）。因智能体框架或基础设施出错而结束的运行（`harness_error`、`infra_error`）计入 `statuses`，但不计入任何平均值。

| 指标 | 含义 |
|---|---|
| `final` | 该次运行所用政策下的综合得分（硬性关卡未通过时为 0） |
| `validity` | 交付物没有违反任何规则的运行所占比例 |
| `quality` | 归一化质量：案例里客户原来的做法为 0，参考答案为 1（无效时为 0） |
| `ask_f1` | 针对只有客户知道的事实计算的 Ask-F1（只算能联系到客户的运行） |
| `enforced_share` | 在案例的直接检查测量过的事实中，交付物落实了的只有客户知道的事实所占比例 |
| `cost_usd`、`total_tokens` | 每次运行：求解的智能体、客户、提取器和评判模型（CLI 求解器自己的 token 目前还不解析） |

**运行记录（runs）。** 每条记录包含：`case`、`tier`、`rule_seed`、`seeds`（`public`、`private`，案例不在本版本中时为 `unknown`，或 null）、`trial`、`noise_seed`、`customer_locale`、`agent_locale`、`policy`、`engagement`、`condition`、`world_seed`、`status`、`final`、`valid`、`quality`、`ask_f1`、`targets`（逐条事实的三个阶段：共 `n` 条事实，以及 `revealed`（客户说出）、`learned`（通过提问得知）和 `enforced`（在交付物中落实）各有多少条通过、多少条被测量，后者记为 `<stage>_measured`）、`enforced_share`、`cost_usd`、`total_tokens`，以及该次运行自己的 `fingerprint`。

**基准点（anchors）。** `kind: "anchors"` 的文件保存各案例的按字面执行需求的答案、客户原来的做法和参考答案，按 `fdebench2 try` 的方式离线评分；其中用 `anchors: {literal | baseline | reference: aggregate}` 代替 `aggregate`，每条运行记录都带有 `anchor` 字段。排行榜把它们显示为基准行，从不参与排名。[leaderboard/anchors-2026-11.json](../../leaderboard/anchors-2026-11.json) 保存的是当前这一轮的基准点，由 `fdebench2 anchors --round 2026-11 --out leaderboard/anchors-2026-11.json` 在这一轮的层级和规则种子上写出，所以基准行和参与排名的系统面对的是同样的设置。不带 `--round` 时，这条命令在公开规则种子上评分，并把文件标为示例。
