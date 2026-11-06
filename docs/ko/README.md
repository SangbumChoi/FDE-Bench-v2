[English](../../README.md) · [中文](../zh/README.md) · [한국어](README.md) · [日本語](../ja/README.md) · [Español](../es/README.md)

# FDE-Bench v2

**고객 언어**(zh/en/ko/ja/es), **회사 정책**, **현실적인 난이도**에 걸쳐 현장 배치 엔지니어링(forward-deployed
engineering) 에이전트를 평가하는 벤치마크입니다. 오픈 모델과 클로즈드 모델은 하나의 OpenAI 호환 프로토콜로, 벤더
하네스(Claude Code, Codex, Gemini CLI, OpenCode)는 공용 MCP 고객 채널로 비교합니다. 자체 완결형이며, 다른 벤치마크의
코드나 데이터에 의존하지 않습니다.

설계, 채점, 현황: [DESIGN.md](../../DESIGN.md). 방향, 관련 연구, 비판적 검토: [docs/DIRECTION.md](../DIRECTION.md).
케이스, 번역, 검토로 기여하는 방법: [CONTRIBUTING.md](CONTRIBUTING.md).

**케이스 둘러보기:** https://sangbumchoi.github.io/FDE-Bench-v2/ — 케이스마다 한 페이지(요청, 설정, 규칙, 숨은
요구사항, 질문 목표, 저장된 데이터와 정답, 리뷰 발견 사항)가 있습니다. 이 사이트는 `fdebench2 build-site`가
`cases/*/*/docs/<lang>/explainer.html`로부터 다시 만들고, 푸시할 때마다 `gh-pages` 브랜치에 게시됩니다
(`.github/workflows/pages.yml`).

## 무엇이 다른가

아래 표에서 비교한 벤치마크 가운데 다음을 하는 것은 FDE-Bench v2뿐입니다(각 항목은 이 저장소의 코드가 검사합니다).

- **하나의 세계, 반사실적 설정.** 케이스마다 데이터셋도 요청도 하나입니다. 난이도 단계 × 규칙 시드가 고객의 규칙과
  파라미터를 정하고, 에이전트가 보는 내용은 모든 설정에서 바이트 단위로 같습니다(`validate-case`가 검사). 그래서 점수는
  고객의 사실에 따라 달라집니다. 비공개 규칙 시드의 정답은 어디에도 저장되지 않습니다.
- **두 축에 걸친, 직접 작성한 다섯 언어:** 고객의 언어(요청, 데이터 라벨, 파일 이름, 고객의 답변)와 에이전트 지시문의
  언어, 각각 zh / en / ko / ja / es.
- **사실 하나하나에 대한 정답 감사**(`audit-case`): 고객의 사실은 모두 결과를 바꿔야 하고, 지름길은 막혀 있어야 하며,
  질문의 가치를 재고, 모범 답안을 알려진 최선의 해나 상한과 비교합니다. 모든 케이스의 문자 그대로의 해(요청을 쓰인
  그대로 수행한 것)는 0.2 이하여야 합니다.
- **사실마다 "드러남 → 파악 → 반영" 깔때기:** 고객이 말했는지, 에이전트가 물어서 알아냈는지, 산출물이 그것을 지키는지.
- **규칙 등급, 회사 정책, 예외 절차:** 물리적 규칙은 절대 굽히지 않습니다. 나머지는 정책의 예외 절차를 거쳐야만 굽힐 수
  있고, 승인 한 번은 지정한 규칙 하나에만 적용됩니다. 같은 실행을 다시 돌리지 않고 다른 정책으로 다시 채점할 수 있습니다.
- **작업 중에 오는 날짜가 있는 이벤트와 압력**(규제 당국의 통지, 결근, VIP 메모, 내부자 정보)은 규칙 위반으로
  채점되고, **프로그램 산출물**은 숨겨진 기간에서 날마다 실행됩니다.

| | FDE-Bench v2 | τ-bench | τ^τ-Bench | Baidu FDE-Bench | FDE-Gym |
|---|---|---|---|---|---|
| 산출물 | 파일, 또는 숨겨진 입력에서 실행되는 프로그램 | – | 고객 상담 에이전트, 공개하지 않은 시뮬레이션 사용자로 채점 | 실제 고객 프로젝트 49개의 해(최적화, ML) | 고객 운영 시스템 사본에서의 납품, 공개하지 않은 트래픽에서 재생 |
| 숨은 고객 사실 | 시뮬레이션 고객이 숨은 요구사항에서 답함; 사실마다 질문 목표 | – | 숨은 요구사항이 있는 고객(고정된 사실 ID) | 시뮬레이션 고객이 알려 줌 | 스크립트 이해관계자 130명 이상; 네 단계의 요청 수준 |
| 고정된 화면 위의 반사실적 설정 | 단계 × 규칙 시드, 비공개 시드 | – | – | 없음(고정 데이터, 스스로 밝힌 한계) | 고정 과제와 공개하지 않은 변형 |
| 언어 | 5개, 고객 × 에이전트 | – | – | – | 1개 |
| 회사 정책, 예외 절차 | 정책 4개; 승인 한 번에 지정 규칙 하나 | – | – | – | – |
| 정답 감사 / 채택 기준 | 사실별 감사(케이스 3개); 모든 케이스: 문자 그대로의 해 ≤ 0.2, 점수 폭 ≥ 5% | – | – | – | 모범 답안 ≥ 0.95, 아무것도 안 하면 0, 문자 그대로의 해 ≤ 0.2, 지름길 ≤ 0.8 |
| 사실 깔때기 드러남 → 파악 → 반영 | 사실별로 보고서에 | – | – | –(규칙을 묻고도 지키지 않은 에이전트를 지적) | –(알아낸 핵심 사실과 개선 폭의 관계를 보고) |
| 하네스 비교 | 기준 루프 + 벤더 CLI 4개, 하나의 MCP 고객 채널 | – | Claude Code, Codex, Kimi Code, OpenCode | – | 구성 13개 |
| 채점 | 유효성 관문; 품질은 기준선 0에서 모범 답안 1까지, 1을 넘어도 인정; Ask-F1; pass^k; 정책별 가중치 | – | 만든 에이전트를 공개하지 않은 사용자로 채점, 오라클 기준과 비교(구성마다 1회, 신뢰구간 없음) | 고객이 받아들인 해 대비 품질, DSR, pass^3, Ask-F1, 부트스트랩 신뢰구간 | 정규화한 개선 폭, 사고 시 0 이하, 숨은 연락 비용 차감 |

"–": 다른 벤치마크에 대한 출처인 [docs/DIRECTION.md](../DIRECTION.md) §2에 나오지 않는다는 뜻이며, 그 기능이 없다는
뜻은 아닙니다. 이 저장소는 τ-bench의 pass^k 추정법을 씁니다. v2는 아직 실제 평가를 돌리지 않았으므로 깔때기와 하네스
비교에는 아직 수치가 없습니다.

## 감사의 말

이 벤치마크가 배운 연구의 저자들께 감사드립니다.

- **FDE-Gym** (Yang et al., *FDE-Gym: The Last Mile of AI Delivery*, arXiv 2610.22350;
  [fde-gym.com](https://fde-gym.com/paper/), [케이스](https://huggingface.co/datasets/DeepLethe/FDE-Gym),
  [하네스](https://github.com/deeplethe/fde-gym)). 네 단계의 요청 수준, 연락 비용이 있는 스크립트 이해관계자,
  공개하지 않은 실제 운영 트래픽에서의 재생 채점, 채택 기준(아무것도 안 하면 0, 모범 답안 1, 요청을 문자 그대로 따른
  답과 지름길은 낮은 점수)이 이 저장소의 정답 감사에 참고가 되었습니다.
- **Baidu FDE-Bench** (arXiv 2610.14539): 현장 배치 엔지니어(FDE)라는 틀과, v2가 이어 쓰는 지표 용어(모범 답안
  대비 품질, DSR, Ask-F1, pass^k)를 처음 제시했습니다.
- **τ^τ-Bench** (arXiv 2609.04611)와 **τ-bench** (arXiv 2406.12045): 만들어진 에이전트를 공개하지 않은 사용자로
  채점하는 설계와 pass^k 추정법.

v2는 이들과 코드나 데이터를 공유하지 않습니다. 모든 케이스는 시드로 생성한 독자적인 것이며, 별도 이용 조건이 있는
FDE-Gym 케이스는 사용하지 않았습니다. 관련 연구는 [docs/DIRECTION.md](../DIRECTION.md) §2와 §9에 있습니다.

## 설치

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## 사용법

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

`--difficulty`는 케이스의 콘텐츠 티어를 고르고, `--rule-seed`는 각 규칙 파라미터를 그 후보 중에서 뽑습니다(기본값은
케이스의 첫 번째 공개 규칙 시드이며, 그 밖의 정수는 모두 정답이 어디에도 저장되지 않는 비공개 시드입니다). 티어와 규칙 시드의
조합마다 데이터셋 하나에 대한 정답이 따로 있으며, 에이전트가 보는 내용은 모든 설정에서 같습니다. `--engagement`(full_spec /
standard / messy)는 작업이 에이전트에게 전달되는 방식을 바꿉니다.
[cases/README.md](../../cases/README.md#difficulty-one-dataset-tiers-and-rule-seeds)를
참조하세요.

모든 명령에 공통인 축: `--customer-locale {zh,en,ko,ja,es}`, `--agent-locale {zh,en,ko,ja,es}`,
`--policy NAME`, `--difficulty {easy,medium,hard}`, `--rule-seed N`, `--engagement {full_spec,standard,messy}`,
`--condition {full,interact,interact_req,hidden}`(어블레이션 실험용 재정의), `--seed N`.

## 디렉터리 구조

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
