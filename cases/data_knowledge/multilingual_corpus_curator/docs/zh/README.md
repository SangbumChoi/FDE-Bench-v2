# 多语种语料库管理员 — `data_knowledge/multilingual_corpus_curator`

一家小出版社把大约一百本书（中文、英文、韩文、日文、西班牙文）的资料放在一个杂乱的共享盘上：每本书的书名、作者、出版年份和简介分散在一到三个不同格式的文件里，旁边还有扫描件、压缩包、目录导出和垃圾文件。智能体交付一个**程序**——`program/organize.py`，其中定义 `organize(task)`，`task = {"corpus_dir": "$INPUT_DIR", "out_dir": "$OUTPUT_DIR"}`——由它整理出一个规范化的书库：

```
out_dir/library/<抽到的布局>.txt   每本书一个 UTF-8 文件：只有这本书的简介
out_dir/_review/...                无法归档的书的源文件
out_dir/manifest.csv               source,status,path,reason（placed | review | skipped）
```

智能体能看到一个可见样本（`data/corpus/`，100 本书，约 120 个文件），程序则在**评分用语料**（不给 AI）上评分：它按同一配方、换一个种子生成（规模和各类文件的构成相同，但书不同，压缩包、目录表和带编号的文件名也不同），所有设置下都完全相同。所有内容都是合成的：书名、人名和简介由用各语言原生编写的虚构词表生成。读取所有格式只需要标准库。

本案例**已审查**（`audited: true`）：`dataset/audit.json` 保存它的标准答案审查，`GT.md` 是据此生成的五部分标准答案（客户掌握的事实、有效性检查、目标值、参考答案与界限值、直接检查的案例），`CLIENT_REVIEW.md` 按事实列出模拟客户在全部五个语言版本中据以回答的原文段落，供人工审核。两者都由 `gt_report.py` 写出。

## 设置：一份语料，层级 × 规则种子

一个设置由一个层级和一个规则种子组成。世界、可见语料、评分用语料和需求在每个设置下都相同（验证器会检查智能体看到的内容逐字节一致）。层级决定哪些书计分、适用哪些规则，以及规则种子从哪些候选池中抽取；规则种子逐个参数独立抽取客户的书库规则，因此正确的书库随种子而不同。公开规则种子为 **11、18 和 21**（九个设置，保存在 `dataset/answer/` 中，并由验证器检查）；其他任何种子都是非公开抽取，其答案不在任何地方公布。

### 层级（语料相同，范围、严格程度和候选池不同）

| | easy | medium | hard |
|---|---|---|---|
| **计分的书**（评分用语料） | 30 本格式规整的书：一个文件，UTF-8，元数据完整，普通的 4 位数年份 | 66 本：+ 所有能读的书 | 100 本：+ 例外情况 |
| **新增内容** | 各种格式、路径布局、命名规则、简介提取、年份依据、罗马字配对 | 旧编码（GB18030、CP949、Shift_JIS、CP1252）；`令和元年`、`昭和50年`、`民國98年`、`단기 4342년`、`二〇〇九年`、`MMIX`；全角书名和分解形式（重音符号与字母分开编码）的书名；路径中不允许的字符；同一作者有多种罗马字写法（正式配对只出现在该作者的其他书里）；跨格式、跨文件夹需要合并的副本；来源优先级（内嵌元数据 > 书名页 > 文件名） | 从另一个文件补回缺失的作者/书名/简介；从有意义的文件名取书名；从 `©` 行取年份；带原因代码送去复核：`NO_TITLE` / `NO_YEAR` / `NO_DESCRIPTION` / `CONFLICT`（同级来源年份不一致）/ `UNREADABLE`（只有图像的扫描件）；客户对无作者书的规定（以 `NO_AUTHOR` 送去复核，或以备用作者名上架）；与可读文件重复的扫描件；垃圾文件（`.DS_Store`、`Thumbs.db`、`desktop.ini`、`~$` 锁定文件、`__MACOSX/._*`、空文件）；zip 压缩包里的书；包含多本书的目录 CSV（英文和日文表头） |
| **名称长度候选池**（`max_len`） | 60、48、40：每个值在不同位置截断带副标题的书名 | 50、40、32：+ 在 32 下还有合著者列表和含长地名的书名 | 40、32、24：+ 中等长度的书名和合著者列表 |
| **无作者书的规定**（`no_author`） | 不抽取（这些书不在范围内） | 不抽取 | 送去复核，或以“Unknown”或“Anonymous”为作者名上架 |
| **规则** | `utf8_output`、`safe_names`（物理约束）；`one_file_per_book`、`review_reason`、`manifest_rows`、`review_copies`（合同约束） | 同上 | + `no_fabrication`、`no_guessing`（合同约束）；在复核规定下有 `missing_author_review`，在上架规定下有 `missing_author_shelved`（业务惯例） |
| **额外计分项** | 范围外的书不予考虑 | 每个不对应任何书的书库文件扣 0.5 | 复核规定：没有作者、在复核区等待的书得 0.7（以“Unknown”上架得 1，但需要批准的例外）；上架规定：这类书和其他上架的书一样计分；文字不出现在任何来源中的书库文件违反 `no_fabrication` |
| **只有客户知道的需求列为范围外的内容** | “共享盘里的其他文件（旧编码、同一本书的多份副本、损坏或不完整的资料、压缩包、目录表、扫描件）这次还不检查，但程序不能因为它们而中断” | “例外情况（缺字段、扫描件、压缩包、目录表、垃圾文件）这次还不计分，但不是书的东西不能进书库” | 无 |

规则种子在每个层级都抽取候选池中的同一个位置（抽取结果不取决于层级），但 `max_len` 每个层级的候选池不同，`no_author` 只在 hard 中有候选值。因此同一个种子在越难的层级给出越紧的名称长度上限，在 hard 中还可能改变无作者书的规定：三个层级的参考答案在每个公开种子下都不同，每个参考答案拿到另一个层级下评分，都低于那个层级自己的参考答案（见下表）。

### 参数

规则种子 s 从每个有 n 个候选值的候选池中抽取位置 `Random("data_knowledge/multilingual_corpus_curator|<name>|s").randrange(n)`，与其他参数无关。前五个候选池在每个层级都相同。每个参数都是某一项应问事实的内容（`locales/en/targets.yaml` 中的 `param:`）。

| 参数 | 候选池 | 改变什么（评分用语料，公开世界，范围内上架的书 easy / medium / hard） | 应问的事实 |
|---|---|---|---|
| `layout` | `library/<年份>/<书名>/<作者>.txt`、`library/<年份>/<作者>/<书名>.txt`、`library/<作者>/<年份>_<书名>.txt` | 每本上架书的路径（30 / 66 / 88–90） | `layout` |
| `year_basis` | 首次出版年份、本版年份（只有一个年份的书两者都用它） | 两个年份不同的书（15 / 37 / 44） | `year_basis` |
| `script` | 原文文字、拉丁字母（元数据中配对的罗马字） | 中文、韩文和日文书（18 / 40 / 58） | `script` |
| `multi_author` | 只写第一作者、全部作者用 `" & "` 连接 | 有两位作者的书（10 / 23 / 30） | `co_authors` |
| `sep` | `_`、`-`、普通空格 | 含空格的名称（原文文字下为 18 / 40 / 53，拉丁字母下为每本书） | `separator` |
| `max_len` | easy 60、48、40；medium 50、40、32；hard 40、32、24 | 超过上限的名称：easy 5–6；medium 13、13、15–17；hard 15、17–19、21–38（范围随文字和合著者规则变化） | `max_len` |
| `no_author` | easy 和 medium 为 `review`；hard 为 `review`、`Unknown`、`Anonymous` | 2 本无作者的书（hard）：`review` 时依可放宽的 `missing_author_review` 以 `NO_AUTHOR` 送去复核（各 0.7）；取一个名字时以该作者名像其他书一样上架（各 1），此时 `missing_author_shelved` 使送去复核或换用别的名字无效 | `missing_author` |

`derive_params` 补充 `fallback_author`，即文本中引用的名字：在上架规定下是抽到的名字，在复核规定下是“Unknown”（批准的例外会用的名字）。没有不可行的组合：生成器保证每个书名在两种文字下的前 24 个字符（最紧的上限）都互不相同，所以任何组合下都没有两本上架的书共用一条路径，本案例也不定义 `admissible`。

每个设置都适用的命名规则：NFKC；每个 `\ / : * ? " < > |` 或控制字符换成空格；连续空白换成分隔符；截断到 `max_len` 个字符；去掉两端的空格、句点和分隔符。上限越紧，涉及的名称越多，所以把这些步骤的顺序弄错，失分也越频繁：在 NFKC 之前截断分解形式的西班牙文书名，保留的字母会更少；截断点落在分隔符上，就会留下一个需要去掉的分隔符。

### 公开规则种子

公开规则种子展示了每个候选池的每个候选值：在种子 11、18 和 21 中，每个有三个候选值的候选池给出全部三个值（在每个层级都是），每个有两个候选值的候选池给出两个值。种子 11 排在最前，因为 validate-case 从它开始检查参数是否起约束作用；它在 hard 中抽到把无作者的书上架，所以规定检查是拿一个有效的上架参考答案，去对照它会违反的那些规定。

| 设置 | `layout` | `year_basis` | `script` | `multi_author` | `sep` | `max_len` | `no_author`（→ `fallback_author`） | 参考答案 | 客户原来的做法 | 界限值 |
|---|---|---|---|---|---|---|---|---|---|---|
| easy/s11 | author/year_title | first | latin | all | `" "` | 40 | review (Unknown) | 100.00 | 16.67 | 100.00 |
| easy/s18 | year/title/author | first | latin | first | `-` | 48 | review (Unknown) | 100.00 | 16.67 | 100.00 |
| easy/s21 | year/author/title | edition | original | first | `_` | 60 | review (Unknown) | 100.00 | 16.67 | 100.00 |
| medium/s11 | author/year_title | first | latin | all | `" "` | 32 | review (Unknown) | 100.00 | 13.03 | 100.00 |
| medium/s18 | year/title/author | first | latin | first | `-` | 40 | review (Unknown) | 100.00 | 13.03 | 100.00 |
| medium/s21 | year/author/title | edition | original | first | `_` | 50 | review (Unknown) | 100.00 | 13.03 | 100.00 |
| hard/s11 | author/year_title | first | latin | all | `" "` | 24 | Unknown | 100.00 | 8.60 | 100.00 |
| hard/s18 | year/title/author | first | latin | first | `-` | 32 | review (Unknown) | 99.40 | 8.60 | 99.40（有例外时为 100） |
| hard/s21 | year/author/title | edition | original | first | `_` | 40 | Anonymous | 100.00 | 8.60 | 100.00 |

目标值基于公开世界种子（20261027）下的评分用语料；“界限值”是 `objective_bound`，即有效程序最多能得的分数（`expected_output` 正好得到这个分数）。非公开种子可以抽到任何其他组合，例如种子 101：`author/year_title`、first、original、first、`-`、60 / 50 / 40，每个层级都是 review；种子 102：`year/author/title`、first、original、first、`_`、40 / 32 / 24，hard 中为 `Unknown`。

**参数的约束作用**（validate-case，从每个层级的 s11 设置出发）：每个参数换成其他任何一个值，参考答案的得分都会改变。在公开世界上，hard/s11 的参考答案得 100.00，只改一个参数时：`layout` 46.00（放错位置的书得 0.4；10 本复核书保留各自的得分），`year_basis` → edition 73.60，`script` → original 65.20，`multi_author` → first 82.00，`sep` → `_` 或 `-` 46.00，`max_len` → 40 或 32 77.20，`no_author` → review 无效（`missing_author_review`），→ Anonymous 无效（`missing_author_shelved`）。在 easy 中（从 100.00 出发）：`layout` 40.00，`year_basis` 70.00，`script` 64.00，`multi_author` 80.00，`sep` 40.00，`max_len` 88.00；在 medium 中：40.00、66.36、63.64、79.09、40.00、84.55。在世界种子 1、2、3 上同样的检查也都通过。

**跨设置的参考答案**（公开世界；每一行是一个设置，每一格是另一个设置的参考答案在该设置下的得分；`*` = 无效）：

| 评分所用设置 | easy s11 / s18 / s21 | medium s11 / s18 / s21 | hard s11 / s18 / s21 |
|---|---|---|---|
| easy/s11 | **100.00** / 40.00 / 40.00 | 88.00 / 40.00 / 40.00 | 76.00 / 40.00 / 40.00 |
| easy/s18 | 40.00 / **100.00** / 40.00 | 40.00 / 88.00 / 40.00 | 40.00 / 88.00 / 40.00 |
| easy/s21 | 40.00 / 40.00 / **100.00** | 40.00 / 40.00 / 88.00 | 40.00 / 40.00 / 88.00 |
| medium/s11 | 84.55 / 40.00 / 40.00 | **100.00** / 40.00 / 40.00 | 70.91 / 40.00 / 40.00 |
| medium/s18 | 40.00 / 88.18 / 40.00 | 40.00 / **100.00** / 40.00 | 40.00 / 86.36 / 40.00 |
| medium/s21 | 40.00 / 40.00 / 88.18 | 40.00 / 40.00 / **100.00** | 40.00 / 40.00 / 88.18 |
| hard/s11 | 75.20* / 45.20* / 45.20* | 75.20* / 45.20* / 45.20* | **100.00** / 45.20* / 46.00* |
| hard/s18 | 46.60 / 89.20 / 46.60 | 46.60 / 89.20 / 46.60 | 46.00* / **99.40** / 46.00* |
| hard/s21 | 45.20* / 45.20* / 89.00* | 45.20* / 45.20* / 89.00* | 46.00* / 45.20* / **100.00** |

另一个种子的参考答案保留它自己的布局，所以它上架的每本书都放错了位置（0.4）。同一种子在另一个层级的参考答案，长度上限不同，在 hard 中无作者书的规定也不同：它会少 10–29 分；在 hard 的每种规定下，为另一种规定写的参考答案都无效（`missing_author_review` 或 `missing_author_shelved`）。

### 智能体必须问清的事

十二项应问的事实，每项一个事实（GT.md 第 1 部分表明：只理解错其中任何一项，在它适用的每个测得设置中都会失去至少十分之一的得分）：

- 随规则种子抽取（`param:`）：`layout`、`year_basis`、`script`、`co_authors`、`separator`、`max_len`，以及 hard 中的
  `missing_author`（无作者书的规定及其备用名字）；
- 在任何抽取下都相同：`content`（文件里只放简介）、`review_codes`（六个原因代码），以及 hard 中的
  `no_description`（没有简介：`NO_DESCRIPTION`，绝不写占位文字）、`conflict`（同一级别的年份不一致：`CONFLICT`）和 `generic_titles`（通用文件名不是书名：`NO_TITLE`）。

早先的应问事实 `precedence`、`encodings`、`year_notations`、`author_variants`、`duplicates`、`containers`、`scoring`，以及 `exceptions` 中上面没有列出的部分，都不再是应问的事实：它们是样本里就能看到的数据事实，或者涉及的书太少、无关紧要（GT.md 列出了每一项可能失去分数的上限；见 REVIEW.md 的“标准答案审查”）。它们仍写在 requirements.md 里，客户被问到时也会回答。

**提问的价值**（审查，公开世界）：从不提问的程序（`robust_solution`：对每个固定事实采用参考答案的理解，对每条抽取的规则取第一个候选值，取最长的名称长度上限，并且不写复核行，因为它不可能知道这些原因代码）在 easy / medium / hard 中的平均质量分为 0.31 / 0.34 / 0.36，所以提问的价值是质量分的 0.69 / 0.66 / 0.64。

## 文件格式与例外一览

| 类型 | 信息在哪里 |
|---|---|
| JSON | `title`、`title_latin`、`authors[{name, name_latin}]`、`first_published`、`edition_year`、`description`（medium 中年份可能是年号字符串） |
| 类 ONIX 的 XML（命名空间 `ns.editeur.org/onix/3.0`） | `TitleText`（+ `textscript="Latn"`）、`Contributor/PersonName` + `AlternativeName` 或 `PersonNameInverted`、`PublishingDateRole` 01 = 本版，11 = 首次出版、`TextContent/Text` |
| EPUB（zip + OPF） | `dc:title`、带 `alternate-script` / `file-as` 细化信息的 `dc:creator`、`dc:date`（本版）、`first-published` meta、`dc:description`；`dcterms:modified` 是陷阱 |
| DOCX（zip + XML） | `docProps/core.xml` 中的 title 和 creator（`dcterms:created` 是陷阱）；拆成多个 run 的正文段落 = 书名页 + 简介 |
| PDF（未压缩的文本流） | Info 中的 `/Title`、`/Author`（UTF-16 十六进制字符串；`/CreationDate` 是陷阱）；页面文字为 UTF-16 的 `Tj` 字符串，书名页的行保持完整，简介的行有折行 |
| 扫描 PDF | 只有图像的页面，没有文字也没有书名：无法读取 |
| HTML | `<title>`、`<meta name="author">`；正文中的 `h1`、`p.latin`、`p.byline`、`p.edition`、`h2`、简介段落；`<meta charset>`（medium 中为 Shift_JIS / CP949） |
| Markdown | 前置元数据（`title`、`title_latin`、`author`、`author_latin`、`first_published`、`edition`）+ 正文书名页 |
| 纯文本 | 书名页（书名、`(罗马字书名)`、`姓名（罗马字） 著` / `지음` / `by` / `por`、版次行、可选的 `©` 行）、小标题（`内容简介`、`内容紹介`、`책 소개`、`About this book`、`Sinopsis`）、简介（有时有硬换行、CRLF，或用旧编码） |
| 目录 CSV | 每行一本书；英文或日文表头；`source` = `file.csv#row` |
| Zip 压缩包 | 每个装 2 本书，外加一个 AppleDouble `__MACOSX/._*` 条目；`source` = `archive.zip!inner/path`（在评分用语料中多一层文件夹） |

每份语料的构成（数量固定，语言部分随机）：easy 30 本；medium 7 个编码、6 种年份写法、4 个全角/分解形式的书名、5 个禁用字符、5 个罗马字变体、6 组多文件副本、3 个优先级冲突；hard 3 个作者补回、2 个无作者、2 个从文件名取书名、2 个无书名、2 个简介补回、2 个无简介、3 个版权行年份、2 个无年份、2 个同级冲突、2 个只有扫描件、2 个有可读副本的扫描件、4 本 zip 里的书、6 个目录行；另有 8 个垃圾文件。easy 中的英文和西班牙文书每两本有一本、其余的书有 60% 带长副标题（`The Silent Lighthouse — Stories from the Northern Coast and the Keepers Who Stayed Behind`）；30% 的书有两位作者。压缩包和目录表的文件名取自小的候选池，带编号的文件名（`doc_0391`、`scan_0414`）在每份语料中从一个随机偏移量开始：在公开世界上，评分用共享盘与样本只共有 4 个垃圾文件路径（以前是 12 个），在世界种子 1-3 上除这些之外最多再共有一个压缩包名（里面的内容不同）。评分用共享盘里还总有一个昭和年号的年份（那本日本年号的书），压缩包里的条目也多一层文件夹。

## 评分

每本计分的书：书库路径完全正确且简介正确得 **1**；简介正确但在任何其他路径得 **0.4**（放错了位置：团队得把它找出来再挪过去）；路径正确但内容是别的文字得 **0.2**。应当复核的书：清单中列出它任一文件的每一行都是 `review` 且原因代码正确，得 1（各行一致但为另一个代码得 0.4；在复核规定下，`NO_AUTHOR` 的书在复核区得 0.7）；各行不一致，或这本书同时还有书库文件，得 0。应当上架的书在复核区得 0；在上架规定下，无作者的书也属于这一类，其预期作者是抽到的备用名字。每本书的清单行也要检查（只能有这一行列出这本书的文件，要全部列出且不能有别的；`placed` 加上这本书的书库路径，或 `review` 且其文件逐字节复制到 `_review/` 下；与可读文件重复的扫描件可以写在这一行里、记为 skipped，或者不写）：缺这一行或这一行有错，扣掉这本书得分的五分之一。medium 和 hard 中每个不对应任何书的书库文件扣 0.5。目标值 = 100 × 得分 / 计分的书数（最大化）；质量在客户原来的做法（0）和参考答案（1）之间归一化，`quality_cap` 为 1.0（参考答案就是能达到的最好结果）。比较简介时先做 NFKC 并去掉所有空白，所以折行不影响结果。在 hard 中，一个非空书库文件如果既不包含任何一本书的完整简介段落，也不是某段简介的片段（20 个字符以上），`no_fabrication` 也会触发：占位文字和编造的简介都属于这种情况；多出一个小标题或漏掉一段只会少得分。

让这些输出成为必须交付的输出的规则：`manifest_rows`（每个书库文件恰好是一个 placed 行的 path，每个 placed 行的 path 都是一个书库文件，它的 source 至少写出共享盘上的一个文件、一个压缩包条目或一个目录行，写法是在压缩包或目录表的路径后面接 `!`、`/`、`:`、`#` 或 `|`；任何来源都不出现在两行里）和 `review_copies`（复核行里写到的每个共享盘文件都复制到 `_review/` 下）。`no_guessing`（hard）把需求里的“不要瞎猜”变成硬性关卡：来源定不下书名或年份的书（`NO_TITLE`、`NO_YEAR`、`CONFLICT`）不得上架。

`score()` 还为每项适用的事实报告 `enforced` 和 `evidence`：这就是直接检查，用程序在评分用共享盘上的同一次运行结果计算（GT.md 第 5 部分）。退化的程序（case.py 中的 `shortcuts()`，GT.md 第 2 部分）都无效，或得分不超过 0.42：把所有书都送去复核、刷复核行、在正确的路径上放占位文字或整个文件、只有表头的清单、placed 行的 source 为空或填它自己书库路径的清单、送去复核却不复制文件、每本书按三种布局各放一份、把共享盘原样复制过去，以及扁平的 `library/<书名>.txt`。直接检查也能把这些程序和正确的程序区分开：扁平路径算作没有落实 `layout`，正确路径上的占位文字算作没有落实 `content`，既没上架也没送去复核的无作者书算作没有落实 `missing_author`；在 hard 中，一行复核行都不写的程序在 `review_codes` 上判为未落实（在 easy 和 medium 中没有哪本计分的书应当复核，它仍为 None）。一个零散的书库文件如果包含某本书的完整简介、外加别的内容（放在任何规则都不会给出的路径上的一张目录卡片），在评分时仍不算任何一本书的文件，但直接检查会把它读作那本书的文件，所以一个理解错两个事实的程序会在两个事实上都被标出。审查还在既不是参考答案、也不是只把这一个事实弄错的答案的交付物上试验直接检查（答案表、客户原来的做法、`robust_solution`；见 GT.md 第 5 部分和 REVIEW.md 的“对其他交付物的直接检查”）。本案例没有按需计算的 `diagnose()` 钩子：直接检查开销很小，在 `score()` 中计算。

程序在评分用语料上的输出按程序的摘要缓存，因此各个设置、违规示例以及约束检查和跨层级检查对每个不同的程序只运行一次（使用默认世界种子 1–3 时，`validate-case` 约需三分钟；`audit-case` 约需 8 到 10 分钟）。

## 参考答案与验证过的数字（种子 20261027，评分用语料）

客户原来的做法（`reference/baseline.py` + 同一个 `config.json`）是客户不靠工程师也能写出的脚本：只把有完整 UTF-8 JSON 导出（书名、作者、普通的四位数年份和简介）的书按编目规则上架；一条 JSON 记录的 ISBN 如果另有一份 ONIX 导出，就把它留给团队（它分辨不出两者哪个对）；其余文件都留给团队（不处理其他格式、旧编码或年号年份，不合并副本，没有复核区）。它在每个设置下都有效。

参考答案（`reference/organize.py` + 该设置的 `config.json`）是完整的整理程序：支持所有格式和 zip 压缩包里的条目，借助语料自身的 UTF-8 字符统计识别旧编码，处理每一种年份写法（年号、民国纪年、檀君纪年、汉字数字、罗马数字、`©` 行），按 NFKC 规范化生成路径名（slug），按规范化书名分组，在一本书的所有文件上逐字段取优先级，从共享盘的任何地方找出每位作者的正式名称配对，检测同级年份冲突，处理扫描件、垃圾文件和目录，并遵循抽到的无作者书规定。它对评分用语料中每本书的归档都与 `expected_output` 完全一样：在每个设置中都达到 `objective_bound`，`quality_cap` 为 1.0。目前已知的最好答案（`best_known_solution`，供审查使用）是由程序写出的答案表本身，也是一个达到界限值的 oracle：除参考答案之外的第二个知道全部事实的交付物，直接检查绝不能把它判为未落实。

| 层级 | 计分的书 | 客户原来的做法的目标值 | 参考答案的目标值 = 界限值 |
|---|---|---|---|
| easy（s11、s18、s21） | 30 | 16.67 | 100.00 |
| medium（s11、s18、s21） | 66 | 13.03 | 100.00 |
| hard，复核规定（s18） | 100 | 8.60 | 99.40（有例外时为 100） |
| hard，上架规定（s11、s21） | 100 | 8.60 | 100.00 |

客户原来的做法完全正确地上架 5 / 9 / 9 本；在 medium 和 hard 中，其中 2 本（副本）因为这本书还有其他文件、而它的清单行只列了 JSON，被扣掉五分之一。在世界种子 1、2、3 上，客户原来的做法得 3.33–20.00（easy）、2.73–19.70（medium）和 3.80–14.00（hard），对应的参考答案为 100.00（复核规定下为 99.40）。在复核规定下放宽 `missing_author_review`（把两本没有作者的书以“Unknown”上架）在该规则被放宽时有效，在 hard/s18 中得 100.00（归一化质量 1.007）。

### 按字面执行需求的答案

`literal_solution` 是参考程序，按数据本身显示的样子读共享盘（每一种格式、编码、年份写法、副本和例外），每个文件里只放简介，而没人给出的编目规则取最自然的理解：`library/<作者>/<年份>_<书名>.txt`，取首次出版年份，用原文文字，所有作者用 " & " 连接，名称完整保留、连其中的空格也保留；归不了档的放进 `_review/`，原因用平常的话写（“years disagree”、“author missing”），正如需求所要求的，因为那六个原因代码只有客户知道。它在每个设置下都是同一个程序，在全部 9 个公开设置下都无效（质量 0）：它的复核行没有原因代码，而且在上架规定下（hard/s11、hard/s21）无作者的书被送去了复核。同样的程序如果改为把这些书记为 skipped（像 `robust_solution` 那样），就有效，得 0.28–0.42：放错位置的书保留其得分的 0.4，所以简介正确但路径不对，即使在另一种布局下（s18、s21）也能让它保持在 0.2 以上。

## 备注

- 可见语料在每个设置和语言版本下都逐字节相同（`content_dirs: [corpus]`）；只有语料之外的整理说明做了本地化。
- `write only inside out_dir` 和 `never modify the corpus` 由运行器强制执行（程序拿到的是语料的副本，在 docker 下为只读），不计分。

## 保存的数据集（`dataset/`）

由 `python -m fdebench2.cli export-dataset cases/data_knowledge/multilingual_corpus_curator` 写出；`validate-case` 会重新生成它，与生成器不一致时报错（约 2 MB，约 2,100 个小文件）。`audit-case` 写出 `dataset/audit.json`（export-dataset 会保留它）。

```
dataset/
  agent_view/<lang>/corpus/...       智能体的样本盘（各语言版本逐字节相同）+ 整理说明
  hidden/corpus/...                  organize() 收到的评分用共享盘原样（每个设置都相同）
  audit.json                         标准答案审查（公开世界）：只把这一个事实弄错的答案、捷径、提问的价值、
                                       界限值、直接检查；GT.md 由它生成
  answer/                            公开规则种子（easy/s11 ... hard/s21），每个文件都以 difficulty 和 seed 区分设置
    answers.csv                      每个设置一行：抽到的参数（推导出的 fallback_author 不单独保存）、参考答案和
                                       客户原来的做法在评分用语料上的目标值、质量尺度的宽度、生效的规则和应问的事实、
                                       参考答案的指标
    files/reference/program/         参考交付物的 organize.py（各设置相同；各设置的 config.json 在
                                       reference_program.jsonl 中）
    files/baseline/program/          客户原来的做法的 organize.py（各设置的 config.json 在 baseline_program.jsonl 中）
    reference_output_*               参考答案在评分用语料上写出的内容：reference_output_manifest.csv、
                                       reference_output__review_<REASON>.jsonl（_review/ 中的 JSON 文件）、
                                       files/reference_output/ 中的其他 _review/ 文件（各设置相同），以及
                                       files/<difficulty>_s<seed>/reference_output/ 中的 library/
    files/<difficulty>_s<seed>/expected_output/
                                     此设置下计分的书在评分用语料上的正确 out_dir：
                                       library/... 每本上架的书一个简介文件，位于该设置规定的路径
                                       _review/<REASON>/<把 / 换成 __ 的路径>  复核书的源文件
                                       （其中的 JSON 文件在 expected_output__review_<REASON>.jsonl 中）
    expected_output_manifest.csv     它的 manifest.csv：placed / review 行（带原因），hard 中还有 JUNK 的 skipped 行
    books.csv                        答案表（评分用语料）：每本书的类型、层级、是否计分、预期状态、
                                       路径和原因、规范书名/作者/年份及其源文件
    expected_score.jsonl             评估器给 expected_output 的得分：easy 和 medium 为 100；hard 在复核规定下
                                       为 99.4（两本 NO_AUTHOR 书在复核区得 0.7；没有放宽任何规则），在上架
                                       规定下为 100
```

只有评分用语料有答案表：可见样本是智能体用来学习的材料，不在它上面计算分数。预期目录树只包含该层级计分的书（30 / 66 / 100）；层级之外的书不属于该设置的答案。没有加入客户邮件或 SQL 导出：共享盘里已经有客户自己的目录导出，新增旁证材料会改变这个案例考查的内容。
