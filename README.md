# report-agent

배터리 시장 전략 비교 보고서를 생성하는 LangGraph 기반 Multi-Agent 프로젝트입니다.

## Supervisor 기반 워크플로우

이 프로젝트는 중앙 Supervisor가 태스크를 순차적으로 라우팅하는 구조를 사용합니다.

- Supervisor가 `current_task`와 `status`를 확인합니다.

- Task ID(T1~T7)에 맞는 워커 노드로 분기합니다.

- 워커가 자신의 산출물을 공유 출력 필드에 기록합니다.

- 실행이 끝나면 다시 Supervisor로 복귀합니다.

- 검증 결과가 `REVISE`이면 이전 단계 재실행 루프로 돌아갑니다.

- `status`가 `COMPLETED` 또는 `FAILED`가 되면 종료합니다.

현재 기본 Task 흐름은 아래와 같습니다.

- T1: research_phase (market · lges · catl 병렬 fan-out)
- T2: lges_strategy (REVISE 재시도 진입점)
- T3: catl_strategy
- T4: comparison
- T5: validation
- T6: report_writer
- T7: reflection

## Shared State를 사용하는 이유

LangGraph의 기본 실행 모델은 하나의 그래프 상태 객체를 각 노드가 전달받는 방식입니다. 이 프로젝트도 해당 모델을 따릅니다.

Shared State 사용:

- Supervisor가 단일 상태에서 진행률, 태스크, 산출물 유무를 일관되게 판단할 수 있습니다.

- 노드 간 별도 직렬화/역직렬화 레이어 없이 공용 출력 필드만 갱신하면 됩니다.

- `validation_result`, `revision_history`, `status`를 한 상태에서 관리해 재실행 흐름을 명확히 제어할 수 있습니다.

## 쓰기 규약(오염 방지 규칙)

Shared State를 쓰더라도 모든 노드가 아무 키나 수정하면 상태 오염이 발생할 수 있습니다. 이를 막기 위해 "쓰기 규약"을 강제합니다.

핵심 원칙:

- Supervisor는 `supervisor` 네임스페이스만 갱신합니다.

- 각 에이전트는 자신의 로컬 네임스페이스만 갱신합니다.

- 로컬 네임스페이스: `market_agent`, `lges_agent`, `catl_agent`, `comparison_agent`, `validation_agent`, `report_agent`, `reflection_agent`

- 파이프라인 합의 산출물만 공유 출력 필드에 기록합니다.

- 공유 출력 필드: `market_background`, `lges_strategy`, `catl_strategy`, `comparison_result`, `swot_result`, `validation_result`, `final_report`, `references`

- Reflection 에이전트는 `final_report` 품질 점검 결과를 `validation_result`와 `supervisor.revision_history`에 반영합니다.

- 재시도 이력은 Supervisor가 `revision_history`로 일원 관리합니다.

이 방식은 "전달은 공유, 수정은 분리" 원칙으로 정리할 수 있습니다.

## 상태 스키마 개요

현재 상태는 아래 두 계층으로 구성됩니다.

- 제어/로컬 네임스페이스: `supervisor`, `*_agent` 전용 로컬 상태

- 공유 산출물 필드: 태스크 완료 결과와 최종 보고서

상세 타입 정의는 `src/core/state.py`를 참고하세요.

## 검색 전략: RAG 우선 + Tavily Fallback

각 Research 노드는 동일한 2단계 검색 정책을 따릅니다.

**단계 1 — 내부 문서 검색 (RAG)**

`SingletonRAG.get_instance(namespace).get_retriever()` 로 FAISS 인덱스에서 관련 청크를 검색합니다.
PDF는 `data/raw/{namespace}/` 에 넣으면 자동으로 임베딩 및 색인됩니다.

**단계 2 — 부족 판정 (4가지 기준)**

| 기준 | 임계값 | 파일 위치 |
|------|--------|-----------|
| 최소 문서 수 | `MIN_DOCS = 3` | `src/core/rag_policy.py` |
| 평균 관련도 | `MIN_RELEVANCE = 0.4` | `src/core/rag_policy.py` |
| 필수 키워드 커버리지 | 100% (노드별 상이) | `REQUIRED_KEYWORDS` |
| 최소 고유 출처 수 | `MIN_SOURCES = 2` | `src/core/rag_policy.py` |

위 4가지 중 하나라도 실패하면 Tavily 웹 검색으로 fallback합니다.
fallback 여부는 `state[*_agent]["fallback_used"]` 에 기록됩니다.

**노드별 필수 키워드**

| 노드 | 필수 키워드 |
|------|------------|
| market | `전기차`, `ESS` |
| lges | `LGES`, `배터리`, `전략`, `재무` |
| catl | `CATL`, `배터리`, `전략`, `재무` |

**기준 선택 이유**

- **내부 근거 우선**: 검증된 PDF 문서를 먼저 사용해 LLM 환각을 줄입니다.
- **비용/속도 균형**: RAG는 무료이고 빠릅니다. Tavily는 충분하지 않을 때만 호출해 API 비용을 최소화합니다.
- **임계값 근거**: MIN_DOCS=3은 단일 청크 의존 방지, MIN_RELEVANCE=0.4는 FAISS L2 거리 정규화(`1/(1+dist)`) 기준 "관련 있음" 하한, MIN_SOURCES=2는 단일 문서 편향 방지입니다.

---

## Validation 편향성 점검

`validation_node` (T5)는 세 가지 항목을 검증합니다.

### 1. 데이터 편향성 점검

LLM이 LGES·CATL 분석 텍스트를 각각 긍정 문장과 부정 문장으로 분류합니다.

```
긍정 비율 = 긍정 문장 수 / (긍정 + 부정 문장 수)
```

한쪽 비율이 `BIAS_THRESHOLD = 70%` 를 초과하면 편향으로 판정합니다.

| 판정 예시 | 결과 |
|-----------|------|
| LGES 긍정 75%, 부정 25% | REVISE (긍정 편향) |
| CATL 긍정 40%, 부정 60% | PASS (균형) |
| CATL 부정 80%, 긍정 20% | REVISE (부정 편향) |

### 2. 필수 비교 항목 누락 점검

아래 4개 항목이 모두 분석 텍스트에 포함되어야 합니다.

`재무` · `기술` · `시장` · `리스크`

LLM 분류 실패 시 텍스트 직접 키워드 매칭으로 fallback합니다.

### 3. 출처 교차 검증

LGES 또는 CATL 중 하나 이상이 **내부(RAG) + 외부(Web) 양쪽 출처를 모두 사용**했어야 합니다.

```python
cross_validated = (lges.rag_doc_count > 0 AND lges.web_result_count > 0)
               OR (catl.rag_doc_count > 0 AND catl.web_result_count > 0)
```

미충족 시 REVISE로 판정합니다.

### 판정 결과 및 재시도 규칙

| 상태 | 다음 액션 |
|------|-----------|
| `PASS` | T6 report_writer 진행 |
| `REVISE` | `revision_history` 에 사유 기록 후 T2 재실행 |
| `FAILED` | `MAX_RETRIES = 2` 초과 시 워크플로우 종료 |

REVISE 발생 시 `state["validation_result"]["revision_notes"]` 에 구체 사유가 기록됩니다.

---

## 구현 참고

- Supervisor 라우팅 로직: `src/agents/supervisor.py`
- 그래프 빌드 및 Retry 루프: `src/graph/workflow.py`
- RAG 부족 판정 상수·함수: `src/core/rag_policy.py`
- 상태 타입 정의: `src/core/state.py`
- Validation 편향 로직: `src/agents/validation.py`
