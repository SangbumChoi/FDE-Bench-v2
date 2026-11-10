# 리더보드에 결과 제출하기

누구나 시스템(모델과 하네스의 조합)을 FDE-Bench v2 리더보드에 올릴 수 있습니다. 캠페인을 실행하고, 그 결과를
`fdebench2 submit`으로 묶은 뒤, `leaderboard/<name>.json` 파일 하나를 추가하는 풀 리퀘스트(PR)를 열면 됩니다.
사이트(`fdebench2 build-site`)는 [leaderboard/](../../leaderboard/)에 있는 파일마다 리더보드 페이지에 한 행씩 보여 줍니다.

## 0. 먼저 케이스를 체험해 보기 (모델도 API 키도 필요 없음)

```bash
pip install -e .
fdebench2 try                                   # 기본 케이스, medium, 첫 번째 공개 규칙 시드
fdebench2 try --case logistics/bakery_delivery_dispatcher --difficulty hard --lang ko
fdebench2 try --submission my_deliverable/      # 직접 만든 결과물 폴더를 같은 방식으로 채점
```

`try`는 AI가 받는 요청, AI가 받는 파일, 고객만 아는 사실이 몇 개인지, 점수 척도를 출력합니다. 그런 다음 그 설정에서
케이스의 요청을 문자 그대로 수행한 답, 기존 방식, 모범 답안(그리고 여러분의 폴더)을 기본 정책으로 채점합니다. 고객과의
상호작용은 오프라인 제출처럼 채점합니다. 아무것도 묻지 않았으므로 Ask-F1은 0이고, 기본 정책은 여기에 가중치를 두지
않습니다. 파일을 변환해 줄 모델이 없으므로, 폴더에는 평가기가 읽는 이름 그대로 결과물이 들어 있어야 합니다(케이스
`case.yaml`의 `deliverables:`, 프로그램 케이스라면 진입 파일이 든 `program/`).

## 1. 캠페인 실행

먼저 개발용으로 한번 돌려 봅니다(실행 9회, docker 없이, 공개 규칙 시드).

```bash
cp configs/models.example.yaml configs/models.yaml      # 엔드포인트 하나와 그 API 키 환경 변수
fdebench2 campaign configs/experiments.starter.yaml
fdebench2 report runs-starter/
```

리더보드에 올리려면 현재 **라운드**([leaderboard/rounds.yaml](../../leaderboard/rounds.yaml))를 실행합니다. 모든 케이스를 세
가지 난이도에서, 라운드의 규칙 시드 세 개로, 각각 3회씩 docker 안에서 실행하는 것입니다. 모두 351회 실행이며, 어느
시스템이든 같습니다. `configs/experiments.leaderboard.yaml`이 바로 그 캠페인입니다. 여기에 여러분의 에이전트만 적고 다른
것은 바꾸지 마세요.

```yaml
agents:
  - {harness: reference, model: my-model}     # configs/models.yaml의 엔드포인트 이름, 또는 벤더 하네스
```

```bash
fdebench2 campaign configs/experiments.leaderboard.yaml --dry-run   # 실행 351회
fdebench2 campaign configs/experiments.leaderboard.yaml
fdebench2 report runs-leaderboard/              # 묶기 전에 표를 확인
```

## 2. 결과 묶기

```bash
fdebench2 submit runs-leaderboard/ --name "My system" --model my-model-2026-10 --harness reference \
    --version 1.2 --flag web_tools=off --flag max_steps=400 --flag budget_usd_per_run=5 \
    --date 2026-11-06 --out leaderboard/my-system.json
```

| 옵션 | 뜻 |
|---|---|
| `runs-leaderboard/` | 캠페인의 결과 디렉터리(`<agent>/<run key>/result.json`) |
| `--name` | 리더보드에 표시되는 시스템 이름 |
| `--model`, `--harness` | 리더보드에 표시되는 값(기본값: 실행에 기록된 모델과 하네스) |
| `--version` | 시스템의 버전 |
| `--flag KEY=VALUE` | 공개할 실행 조건 하나. 여러 번 쓸 수 있음(웹 도구, 스텝과 토큰 예산, 추가 도구, 프롬프트) |
| `--date` | 제출 날짜, `YYYY-MM-DD`(기본값: UTC 기준 오늘) |
| `--agent` | 디렉터리에 여러 에이전트의 실행이 들어 있을 때 쓰는 에이전트 라벨 `<harness>--<model>` |
| `--cases` | 케이스 폴더(기본값 `cases/`). 공개 규칙 시드와 비공개 규칙 시드를 구분하고 케이스의 해시를 계산하는 데 씀 |
| `--rounds` | 라운드 파일(기본값 `leaderboard/rounds.yaml`) |

명령은 작성한 파일과 한 줄 요약을 출력합니다. 요약에는 채점된 실행 수, 케이스 수, 최종 점수의 평균과 그 구간, 그리고
상태(`ranked`(순위 대상)이면 그 라운드, `development`(개발용)이면 그 이유)가 나옵니다.

## 3. 보내기

`leaderboard/<name>.json`을 추가하는 풀 리퀘스트를 엽니다(시스템마다 파일 하나이며, 시스템의 새 버전은 기존 파일을
대체합니다). 설명란에 실행을 어떻게 했는지 적습니다. 하네스와 그 버전, 예산, 웹 도구를 켰는지, 그 밖에 읽는 사람이 실행을
재현하는 데 필요한 것을 모두 적습니다.

## 규칙

- **라운드를 실행합니다.** 제출은 [leaderboard/rounds.yaml](../../leaderboard/rounds.yaml)의 라운드 하나를 빠짐없이 실행했을
  때만 순위에 오릅니다. 모든 케이스를, 라운드의 티어와 규칙 시드마다, 라운드의 트랙(영어 고객과 영어 에이전트, `baseline`
  정책, `standard` 진행 방식)에서 실행하는 것입니다. 한 라운드의 모든 시스템이 같은 설정을 풀기 때문에 결과를 서로 비교할
  수 있고, 아무도 시드를 직접 고르지 않습니다. 라운드의 규칙 시드는 어느 케이스의 공개 규칙 시드에도 들어 있지 않으며, 그
  정답은 저장소 어디에도 저장되어 있지 않습니다. 새 라운드에는 새 시드를 쓰고, 리더보드는 라운드별로 따로 보여 줍니다.
- **그 밖의 것은 모두 `development`입니다.** 공개 규칙 시드로 한 실행, 직접 고른 시드로 한 실행, 케이스나 티어의 일부만 한
  실행, 다른 언어나 정책으로 한 실행도 환영하며, 순위 없이 그 이유와 함께 표시됩니다.
- **시도 3회 이상.** 모든 설정을 3회 이상 실행해야 합니다(`trials: 3`). 그보다 적으면 제출은 `development`입니다.
- **웹 도구는 끄거나, 로그를 남깁니다.** 실행 중에 케이스를 온라인에서 찾아보면 안 됩니다. 하네스에 웹 도구가 있으면
  끄거나(`--flag web_tools=off`), 로그를 보관하고 그렇게 밝힙니다(`--flag web_tools=logged`).
- **하네스와 예산을 공개합니다.** 하네스의 이름과 버전, 그리고 모든 예산(스텝, 토큰, 비용, 실제 소요 시간)을 플래그로
  밝힙니다.
- **공개된 그대로의 벤치마크.** 수정하지 않은 체크아웃에서 실행합니다. 제출에는 커밋과 모든 케이스 파일의 해시가
  기록되므로, 다른 버전의 케이스에서 나온 결과와는 비교하지 않습니다.
- **손으로 고치지 않습니다.** JSON은 `fdebench2 submit`이 쓴 그대로여야 합니다.
- **결과는 제출자가 스스로 보고합니다.** 채점기와 모범 답안은 이 저장소에 있는 코드이므로, 라운드를 실행하는 사람은 누구나
  그 라운드의 정답을 계산할 수 있습니다. 에이전트는 계산할 수 없어야 합니다. 샌드박스 안에서 에이전트는 자기 작업 공간만
  봅니다(`isolation: strict`). 스스로 보고하는 리더보드가 다 그렇듯 이 리더보드도 그 점을 믿고 운영됩니다. 설명만으로
  재현할 수 없는 제출은 삭제될 수 있습니다.

## 형식

JSON 객체 하나이며, `"format": "fdebench2-submission/1"`입니다.

| 필드 | 내용 |
|---|---|
| `kind` | `"system"`(제출) 또는 `"anchors"`(케이스 자체의 기준점, 아래 참조) |
| `example` | 예시 파일일 때만 `true` |
| `system` | `name`, `model`, `harness`, `version`, `agent_label`(실행의 `<harness>--<model>`), `max_steps`, `flags`(`{key: value}`), `date` |
| `benchmark` | `framework_version`, `git_commit`, `git_dirty`(`cases/`, `fdebench2/`, `configs/` 아래에 커밋하지 않은 변경이 있는지), `cases`: `{case id: hash of its files}`(케이스 ID마다 그 케이스 파일들의 해시. 실행의 지문(fingerprint)이 쓰는 해시로, 문서와 저장된 감사 결과를 뺀 케이스 파일로 계산) |
| `seeds` | `kind`: `private`, `public`, `mixed` 또는 `none`, 그리고 사용한 `public`과 `private` 규칙 시드 |
| `trials` | 변형 가운데 가장 적게 실행한 것의 시도 횟수 |
| `status` | `ranked`(라운드 하나를 빠짐없이 실행하고 `trials` ≥ 3) 또는 `development`. 기준점 파일은 `anchor` |
| `round` | 순위 대상 제출이 실행한 라운드의 id. 그렇지 않으면 null |
| `status_reasons` | 제출이 순위 대상이 아닌 이유 |
| `aggregate` | 아래의 평균들. 각각 `{mean, ci: [low, high], n_cases}`이며, 여기에 `n_runs`, `n_scored`, `n_cases`, `statuses`(상태별 실행 수)가 더해짐 |
| `runs` | 실행마다 기록 하나(아래) |

**집계(aggregate).** `fdebench2 report`가 계산하는 것과 같은 케이스 매크로 평균입니다. 한 케이스 안에서는 모든 규칙 시드의
비중이 같고(시드별로 실행의 평균을 낸 뒤 시드들의 평균을 냄), 그다음 모든 케이스의 비중이 같습니다. `ci`는 케이스에 대한
95% 부트스트랩 구간입니다(재표본 2000회, 고정 시드). 하네스 오류나 인프라 오류로 끝난 실행(`harness_error`,
`infra_error`)은 `statuses`에는 세지만 어떤 평균에도 넣지 않습니다.

| 지표 | 뜻 |
|---|---|
| `final` | 실행에 적용된 정책에서의 종합 점수(필수 관문을 하나라도 통과하지 못하면 0) |
| `validity` | 결과물이 규칙을 하나도 어기지 않은 실행의 비율 |
| `quality` | 정규화 품질: 케이스의 기존 방식이 0, 모범 답안이 1(무효이면 0) |
| `ask_f1` | 고객만 아는 사실에 대한 Ask-F1(고객에게 물을 수 있었던 실행 기준) |
| `enforced_share` | 고객만 아는 사실 가운데 결과물에 반영된 비율. 케이스의 직접 검사가 잰 사실을 분모로 함 |
| `cost_usd`, `total_tokens` | 실행당 값: 솔버, 고객, 추출기, 판정자를 합침(CLI 솔버 자체의 토큰은 아직 읽어 오지 않음) |

**실행(runs).** 기록마다 다음이 들어 있습니다. `case`, `tier`, `rule_seed`, `seeds`(`public`, `private`, 이 버전에 없는
케이스이면 `unknown`, 또는 null), `trial`, `noise_seed`, `customer_locale`, `agent_locale`, `policy`, `engagement`, `condition`,
`world_seed`, `status`, `final`, `valid`, `quality`, `ask_f1`, `targets`(물어봐야 할 사실의 단계별 집계: 사실 `n`개, 그리고
`revealed`(고객이 말함), `learned`(질문으로 알아냄), `enforced`(결과물에 반영됨) 단계마다 통과한 수와 잰 수
`<stage>_measured`), `enforced_share`, `cost_usd`, `total_tokens`, 그리고 실행 자체의 `fingerprint`.

**기준점(anchors).** `kind: "anchors"`인 파일에는 케이스의 요청을 문자 그대로 수행한 답, 기존 방식, 모범 답안을
`fdebench2 try`와 같은 방식으로 오프라인에서 채점한 결과가 들어 있습니다. `aggregate` 대신
`anchors: {literal | baseline | reference: aggregate}`가 있고, 실행마다 `anchor` 필드가 있습니다. 리더보드는 이들을 기준 행으로
보여 주며 순위에는 넣지 않습니다. [leaderboard/anchors-2026-11.json](../../leaderboard/anchors-2026-11.json)에 현재 라운드의
기준점이 들어 있습니다. 라운드의 티어와 규칙 시드에서
`fdebench2 anchors --round 2026-11 --out leaderboard/anchors-2026-11.json`으로 만든 파일이므로, 기준 행과 순위 대상 시스템이
같은 설정을 풉니다. `--round` 없이 실행하면 이 명령은 공개 규칙 시드를 채점하고 파일을 예시로 표시합니다.
