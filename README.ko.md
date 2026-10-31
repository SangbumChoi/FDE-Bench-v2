[English](README.md) · [中文](README.zh.md) · [한국어](README.ko.md) · [日本語](README.ja.md) · [Español](README.es.md)

# FDE-Bench v2

**고객 언어**(zh/en/ko/ja/es), **회사 정책**, **현실적인 난이도**에 걸쳐 현장 배치 엔지니어링(forward-deployed
engineering) 에이전트를 평가하는 벤치마크입니다. 오픈 모델과 클로즈드 모델은 하나의 OpenAI 호환 프로토콜로, 벤더
하네스(Claude Code, Codex, Gemini CLI, OpenCode)는 공용 MCP 고객 채널로 비교합니다. 자체 완결형이며, 다른 벤치마크의
코드나 데이터에 의존하지 않습니다.

설계, 채점, 현황: [DESIGN.md](DESIGN.md). 방향, 관련 연구, 비판적 검토: [docs/DIRECTION.md](docs/DIRECTION.md).

**케이스 둘러보기:** https://sangbumchoi.github.io/FDE-Bench-v2/ — 케이스마다 한 페이지(요청, 설정, 규칙, 숨은
요구사항, 질문 목표, 저장된 데이터와 정답, 리뷰 발견 사항)가 있습니다. 이 사이트는 `fdebench2 build-site`가
`cases/*/*/explainer.html`로부터 다시 만들고, 푸시할 때마다 `gh-pages` 브랜치에 게시됩니다
(`.github/workflows/pages.yml`).

## 설치

```bash
pip install -e '.[mcp,dev]'
cp configs/models.example.yaml configs/models.yaml   # set endpoints and API-key env vars
```

## 사용법

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

`--difficulty`는 케이스의 콘텐츠 티어를 고르고, `--rule-seed`는 각 규칙 파라미터를 그 후보 중에서 뽑습니다(기본값은
케이스의 첫 번째 공개 규칙 시드이며, 그 밖의 정수는 모두 정답이 어디에도 저장되지 않는 비공개 시드입니다). 티어와 규칙 시드의
조합마다 데이터셋 하나에 대한 정답이 따로 있으며, 에이전트가 보는 내용은 모든 설정에서 같습니다. `--engagement`(full_spec /
standard / messy)는 작업이 에이전트에게 전달되는 방식을 바꿉니다.
[cases/README.md](cases/README.md#difficulty-one-dataset-tiers-and-rule-seeds)를
참조하세요.

모든 명령에 공통인 축: `--customer-locale {zh,en,ko,ja,es}`, `--agent-locale {zh,en,ko,ja,es}`,
`--policy NAME`, `--difficulty {easy,medium,hard}`, `--rule-seed N`, `--engagement {full_spec,standard,messy}`,
`--condition {full,interact,interact_req,hidden}`(어블레이션 실험용 재정의), `--seed N`.

## 디렉터리 구조

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
