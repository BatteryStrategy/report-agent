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

- T1: market_research

- T2: lges_strategy

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

## 구현 참고

- Supervisor 라우팅 로직: `src/agents/supervisor.py`
- 그래프 빌드: `src/graph/workflow.py`
- 상태 타입 정의: `src/core/state.py`
