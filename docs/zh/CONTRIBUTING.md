[English](../../CONTRIBUTING.md) · [中文](CONTRIBUTING.md) · [한국어](../ko/CONTRIBUTING.md) · [日本語](../ja/CONTRIBUTING.md) · [Español](../es/CONTRIBUTING.md)

# 为 FDE-Bench v2 做贡献

感谢你的帮助。本页说明可以贡献什么、新案例如何构建、案例必须达到的标准，以及拉取请求（PR）需要满足的条件。背景资料：
[README](README.md)、[DESIGN.md](../../DESIGN.md) 第 3 节的案例格式、[cases/README.md](../../cases/README.md) 中的案例目录，
以及 [docs/DIRECTION.md](../DIRECTION.md) 第 5 节中新案例的设计规则。

## 可以贡献什么

| 贡献 | 内容 | 从哪里开始 |
|---|---|---|
| **新案例** | 从目录（[cases/README.md](../../cases/README.md)，规格见 [docs/specs/](../specs/README.md)）中选一个角色，按案例约定构建 | 先用 *Case proposal* 模板开一个 issue，再按下面的流程进行 |
| **翻译或母语审阅** | 修改或审阅某个语言版本的文字：`locales/<lang>/`（request、requirements、targets、summary、explainer.yaml）、`docs/<lang>/README.md` 和 `REVIEW.md`、`fdebench2/prompts/*.yaml`、`docs/<lang>/` | 为你的母语提交 PR，并说明审阅了哪些文件 |
| **客户回答审阅** | 在已审查案例的 `CLIENT_REVIEW.md` 中给出结论：每个语言版本的客户依据的段落，能否正确回答自然会问的问题，且不多答？ | 见下文 |
| **错误报告** | 评分错误、验证器漏洞、崩溃、页面损坏、客户泄露或编造规则 | 用 *Bug report* 模板开 issue |
| **提交结果** | 某个模型或框架（harness）在本基准上的运行结果 | `docs/SUBMITTING.md`（编写中） |

### 客户回答审阅

每个已审查的案例（case.yaml 中 `audited: true`）在 case.yaml 旁边都有一个 `CLIENT_REVIEW.md`。对每条事实，它给出工程师会问的
问题、各语言版本的客户回答时依据的 `requirements.md` 行，以及机器预检。目前所有 `Reviewer verdict:` 行都还是空的。

- 用你的母语阅读对应语言的段落。
- 在 `Reviewer verdict:` 行写上 `OK` 或 `Problem`、你检查过的语言；如有问题，写明是什么：数字错误或缺失、回答含糊，或段落
  回答了没被问到的内容。
- `CLIENT_REVIEW.md` 是生成的文件（`make_client_review.py` 会重写它）。请把审阅结论单独放在一个 PR 中，并且不要在其中重新生成
  该文件。对需求本身的修改另开一个 PR。

## 案例流程

```bash
fdebench2 new-case <field>/<role>             # add --program when the deliverable is code run on hidden inputs
# write case.yaml and case.py, then every text in all five locales (zh, en, ko, ja, es)
fdebench2 export-dataset cases/<field>/<role> # store data and answers in dataset/; also writes the explainer pages
fdebench2 validate-case cases/<field>/<role>  # the case contract, on the public world and world seeds 1-3
fdebench2 audit-case cases/<field>/<role>     # the ground truth audit, stored in dataset/audit.json
python -m pytest -q                           # the repository's tests
```

1. **提议。** 用 *Case proposal* 模板开 issue：角色、客户、交付物、隐藏事实，以及每条事实如何改变答案。从目录中选一个角色，
   或说明它属于哪个领域（`cases/fields.yaml`）。
2. **生成骨架。** `fdebench2 new-case` 会写出 case.yaml、case.py、五个语言版本和各语言的 README，所有必填部分都标为 TODO。
   可参考其文档字符串中列出的已构建案例（`fdebench2/scaffold.py`）。
3. **在 case.py 中编写世界和评分器：** `build_world`、`write_data`、`reference_solution`、`baseline_solution`、
   `literal_solution`、`score`、`violating_examples`；如需审查，还要 `ablations`、`shortcuts`、`robust_solution`、
   `best_known_solution` 或 `objective_bound`（[DESIGN.md](../../DESIGN.md) 第 3 节）。
4. **用五种语言编写文字：** `locales/<lang>/request.md`、`requirements.md`、`targets.yaml`、`summary.yaml`、
   `explainer.yaml`（英文除外）以及 `docs/<lang>/README.md`。每种语言都按母语习惯来写，而不是逐词直译；各语言版本的目标 id、
   `{{param}}` 占位符和设置标记必须一致。
5. 用 `fdebench2 export-dataset` **导出**，再用 `fdebench2 validate-case` **验证**，直到没有问题为止。修复警告，或在案例的
   `docs/en/REVIEW.md` 中说明原因。
6. 用 `fdebench2 audit-case` **审查**（需 10 到 40 分钟）。通过后设置 `audited: true`，并再次运行 `validate-case`：已审查的
   案例如果缺少审查结果或结果已过期，验证会失败。
7. **把案例加入目录**（[cases/README.md](../../cases/README.md)），重新生成首页（`fdebench2 explain-case cases/<field>/<role>`），
   运行测试，然后提交 PR。

## 案例必须达到的标准

- `fdebench2 validate-case` 在公开世界和世界种子 1–3 上都没有报告问题。
- 每个公开设置下评分尺度的宽度至少为 5%：|参考答案 − 基线| / |参考答案| ≥ 0.05。
- 字面解（只根据智能体看到的内容、完全照需求原文去做）在每个公开设置下都无效，或得分不超过 0.2。
- 智能体看到的内容（需求和文件）在所有设置下逐字节相同；不同的只有客户的事实。
- 每条规则都有类别，且恰好有一条业务规则是可以放宽的习惯做法。
- 已审查的案例：每条客户事实都起作用（只理解错这一条，交付物就无效，或在其生效的每个层级损失至少 0.10 的质量），每条捷径都被
  堵住（无效或最多 0.5），每个层级提问的价值至少为 0.10。
- 不含真实个人数据：所有人名、公司、地址和数字都是生成的。
- 只用原创内容：不复制任何条款不允许复制的其他基准、数据集或文档。FDE-Bench v2 不与其他基准共享代码或数据。

## PR 检查清单

- [ ] 每个 PR 只有一个主题（一个案例、一份翻译、一组审阅结论、一个修复）。
- [ ] 所有改动过的案例都通过 `fdebench2 validate-case`。
- [ ] 案例的代码或文字有任何改动后都重新运行了 `fdebench2 export-dataset`，并提交了 `dataset/`。
- [ ] 已审查的案例：源文件改动后重新运行了 `fdebench2 audit-case`，`dataset/audit.json` 是最新的。
- [ ] 新案例：评分尺度 ≥ 5%，字面解 ≤ 0.2，智能体在所有设置下看到的内容相同。
- [ ] 五个语言版本一起更新；尽可能检查了母语表达。
- [ ] 不含真实个人数据；只用原创内容。
- [ ] 新增或改名案例时重新生成了目录和首页（`fdebench2 explain-case`）。
- [ ] `python -m pytest -q` 通过。
- [ ] 提交信息简洁明了：改了什么、为什么改。
