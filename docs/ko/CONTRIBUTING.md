[English](../../CONTRIBUTING.md) · [中文](../zh/CONTRIBUTING.md) · [한국어](CONTRIBUTING.md) · [日本語](../ja/CONTRIBUTING.md) · [Español](../es/CONTRIBUTING.md)

# FDE-Bench v2에 기여하기

도와주셔서 감사합니다. 이 문서는 무엇을 기여할 수 있는지, 새 케이스를 어떻게 만드는지, 케이스가 넘어야 할 기준, 풀 리퀘스트(PR)에
필요한 것을 설명합니다. 배경: [README](README.md), [DESIGN.md](../../DESIGN.md) §3의 케이스 형식,
[cases/README.md](../../cases/README.md)의 카탈로그, [docs/DIRECTION.md](../DIRECTION.md) §5의 새 케이스 설계 규칙.

## 기여할 수 있는 것

| 기여 | 내용 | 시작하는 곳 |
|---|---|---|
| **새 케이스** | 카탈로그([cases/README.md](../../cases/README.md), 명세는 [docs/specs/](../specs/README.md))의 역할 하나를 케이스 규약에 맞게 구축 | *Case proposal* 템플릿으로 이슈를 연 뒤 아래 절차대로 |
| **번역 또는 원어민 검토** | 한 언어의 텍스트를 고치거나 검토: `locales/<lang>/`(request, requirements, targets, summary, explainer.yaml), `docs/<lang>/README.md`와 `REVIEW.md`, `fdebench2/prompts/*.yaml`, `docs/<lang>/` | 모국어에 대해 PR을 열고 어떤 파일을 검토했는지 적기 |
| **고객 답변 검토** | 감사를 마친 케이스의 `CLIENT_REVIEW.md`에 판정 쓰기: 각 언어의 고객이 근거로 삼는 구절이 자연스러운 질문에 정확히, 더도 덜도 없이 답하는가? | 아래 절 |
| **버그 신고** | 잘못된 채점, 검증기의 빈틈, 오류로 인한 중단, 깨진 페이지, 규칙을 흘리거나 지어내는 고객 | *Bug report* 템플릿으로 이슈 열기 |
| **결과 제출** | 어떤 모델이나 하네스로 이 벤치마크를 실행한 결과 | [docs/SUBMITTING.md](../SUBMITTING.md) |

### 고객 답변 검토

감사를 마친 케이스(case.yaml에 `audited: true`)에는 case.yaml 옆에 `CLIENT_REVIEW.md`가 있습니다. 사실마다 엔지니어가 물을
질문, 각 언어의 고객이 답할 때 근거로 삼는 `requirements.md`의 줄, 기계 사전 점검이 있습니다. `Reviewer verdict:` 줄은 아직
모두 비어 있습니다.

- 모국어로 읽을 수 있는 언어의 구절을 읽습니다.
- `Reviewer verdict:` 줄에 `OK` 또는 `Problem`, 확인한 언어를 쓰고, 문제가 있으면 무엇이 문제인지 씁니다. 틀리거나 빠진
  숫자, 모호한 답, 묻지 않은 것까지 답하는 구절 등입니다.
- `CLIENT_REVIEW.md`는 생성되는 파일입니다(`make_client_review.py`가 다시 씁니다). 판정은 별도의 PR로 보내고, 그 PR에서는
  파일을 다시 생성하지 마세요. 요구사항 자체를 고치는 것은 다른 PR로 합니다.

## 케이스 작업 절차

```bash
fdebench2 new-case <field>/<role>             # add --program when the deliverable is code run on hidden inputs
# write case.yaml and case.py, then every text in all five locales (zh, en, ko, ja, es)
fdebench2 export-dataset cases/<field>/<role> # store data and answers in dataset/; also writes the explainer pages
fdebench2 validate-case cases/<field>/<role>  # the case contract, on the public world and world seeds 1-3
fdebench2 audit-case cases/<field>/<role>     # the ground truth audit, stored in dataset/audit.json
python -m pytest -q                           # the repository's tests
```

1. **제안.** *Case proposal* 템플릿으로 이슈를 엽니다. 역할, 고객, 산출물, 숨은 사실과 각 사실이 답을 어떻게 바꾸는지 적습니다.
   카탈로그에서 역할을 고르거나 어느 분야(`cases/fields.yaml`)에 속하는지 밝힙니다.
2. **뼈대 만들기.** `fdebench2 new-case`가 case.yaml, case.py, 다섯 언어, 언어별 README를 만들고 필수 부분을 모두 TODO로
   표시합니다. 독스트링에 적힌 구축된 케이스(`fdebench2/scaffold.py`)의 패턴을 참고하세요.
3. case.py에 **세계와 채점기 작성:** `build_world`, `write_data`, `reference_solution`, `baseline_solution`,
   `literal_solution`, `score`, `violating_examples`. 감사를 받으려면 `ablations`, `shortcuts`, `robust_solution`,
   `best_known_solution` 또는 `objective_bound`도 필요합니다([DESIGN.md](../../DESIGN.md) §3).
4. **다섯 언어로 텍스트 작성:** `locales/<lang>/request.md`, `requirements.md`, `targets.yaml`, `summary.yaml`,
   `explainer.yaml`(en 제외), `docs/<lang>/README.md`. 단어를 옮기는 번역이 아니라 각 언어로 자연스럽게 쓰되, 목표 id,
   `{{param}}` 자리표시자, 설정 표시는 모든 언어에서 같아야 합니다.
5. `fdebench2 export-dataset`로 **내보내고**, `fdebench2 validate-case`가 문제를 보고하지 않을 때까지 **검증**합니다. 경고는
   고치거나 케이스의 `docs/en/REVIEW.md`에 이유를 적습니다.
6. `fdebench2 audit-case`로 **감사**합니다(10~40분). 통과하면 `audited: true`로 설정하고 `validate-case`를 다시 실행합니다.
   감사 결과가 없거나 오래된 감사 케이스는 검증에 실패합니다.
7. **카탈로그에 케이스 추가**([cases/README.md](../../cases/README.md)), 홈페이지 다시 생성
   (`fdebench2 explain-case cases/<field>/<role>`), 테스트 실행 후 PR을 엽니다.

## 케이스가 넘어야 할 기준

- `fdebench2 validate-case`가 공개 세계와 세계 시드 1~3에서 문제를 보고하지 않습니다.
- 모든 공개 설정에서 품질 척도의 폭이 5% 이상입니다: |모범 답안 − 기준선| / |모범 답안| ≥ 0.05.
- 문자 그대로의 해(에이전트가 보는 것만으로 요청을 쓰인 그대로 수행한 것)는 모든 공개 설정에서 무효이거나 0.2 이하입니다.
- 에이전트가 보는 것(요청과 파일)은 모든 설정에서 바이트 단위로 같고, 다른 것은 고객의 사실뿐입니다.
- 모든 규칙에 등급이 있고, 굽힐 수 있는 관행인 비즈니스 규칙은 정확히 하나입니다.
- 감사 케이스: 고객의 사실은 모두 결과를 바꾸고(그 사실 하나만 잘못 읽어도 산출물이 무효가 되거나, 그 사실이 적용되는 각
  단계에서 품질이 0.10 이상 떨어짐), 지름길은 모두 막혀 있으며(무효 또는 0.5 이하), 질문의 가치는 단계마다 0.10 이상입니다.
- 실제 개인 정보 없음: 사람, 회사, 주소, 숫자는 모두 생성한 것입니다.
- 독자적인 내용만: 이용 조건이 허락하지 않는 다른 벤치마크, 데이터셋, 문서에서 가져온 것이 없습니다. FDE-Bench v2는 다른
  벤치마크와 코드나 데이터를 공유하지 않습니다.

## PR 체크리스트

- [ ] PR 하나에 주제 하나(케이스 하나, 번역 하나, 판정 묶음 하나, 수정 하나).
- [ ] 손댄 모든 케이스가 `fdebench2 validate-case`를 통과합니다.
- [ ] 케이스의 코드나 텍스트를 바꾼 뒤 `fdebench2 export-dataset`를 다시 실행했고 `dataset/`를 커밋했습니다.
- [ ] 감사 케이스: 소스가 바뀌었으면 `fdebench2 audit-case`를 다시 실행했고 `dataset/audit.json`이 최신입니다.
- [ ] 새 케이스: 품질 척도 폭 ≥ 5%, 문자 그대로의 해 ≤ 0.2, 에이전트가 보는 것이 모든 설정에서 같음.
- [ ] 다섯 언어를 함께 고쳤고, 가능한 범위에서 원어민 표현을 확인했습니다.
- [ ] 실제 개인 정보 없음, 독자적인 내용만.
- [ ] 케이스를 추가하거나 이름을 바꿨으면 카탈로그와 홈페이지를 다시 생성했습니다(`fdebench2 explain-case`).
- [ ] `python -m pytest -q`가 통과합니다.
- [ ] 커밋 메시지는 간결하게: 무엇을, 왜 바꿨는지.
