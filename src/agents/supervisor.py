"""
Supervisor Agent.

역할: 워크플로우 전체 제어 — 태스크 라우팅, 재시도 횟수 관리, 종료 조건 판정

[태스크 순서]
  T1 → research_phase   : market·lges·catl 병렬 fan-out
  T2 → lges_strategy    : validation(T4) REVISE 시 재시도 진입점
  T3 → catl_strategy    : T2 재실행 후 순차 진행
  T4 → validation       : Research 품질 검증 (편향·누락·출처)
                          PASS   → T5(comparison)
                          REVISE → T2 (최대 MAX_RETRIES=2회)
                          초과   → FAILED
  T5 → comparison       : 검증된 데이터로 6축 비교 프레임 생성
  T6 → swot             : comparison_result 기반 SWOT 생성
  T7 → report_writer    : 8개 필수 섹션 Markdown 보고서 생성
  T8 → reflection       : 보고서 품질 점검
                          PASS   → COMPLETED
                          REVISE → T7 (최대 MAX_REFLECTION_RETRIES=1회)
                          초과   → COMPLETED 강제

[재시도 횟수 관리]
  - T4(validation) 재시도: supervisor["revision_history"] 리스트 길이로 카운트
      MAX_RETRIES=2 초과 시 status="FAILED"
  - T8(reflection) 재시도: supervisor["reflection_retry_count"] 정수로 카운트
      MAX_REFLECTION_RETRIES=1 초과 시 COMPLETED 강제

[FAILED 전환 기준]
  - T4에서 REVISE 횟수가 MAX_RETRIES(2)를 초과할 때만 발생
  - T8(reflection)은 FAILED를 발생시키지 않음

[무한루프 방지]
  - route_from_supervisor: status ∈ {COMPLETED, FAILED} → 즉시 END
  - validation_node: revision_history >= MAX_RETRIES → FAILED
  - reflection_node: reflection_retry_count >= MAX_REFLECTION_RETRIES → COMPLETED 강제
"""

from src.core.state import GraphState


def supervisor_node(state: GraphState) -> GraphState:
    """
    중앙 관리자: 제어 상태를 supervisor 네임스페이스에만 기록한다.

    초기화 시 설정:
      - status = "IN_PROGRESS"
      - current_task = "T1"
      - revision_history = []        (T4 validation 재시도 이력)
      - reflection_retry_count = 0   (T8 reflection 재시도 카운터)
    """
    supervisor_state = state.get("supervisor", {})

    if "status" not in supervisor_state:
        supervisor_state["status"] = "IN_PROGRESS"
    if "current_task" not in supervisor_state:
        supervisor_state["current_task"] = "T1"
    if "revision_history" not in supervisor_state:
        supervisor_state["revision_history"] = []
    if "reflection_retry_count" not in supervisor_state:
        supervisor_state["reflection_retry_count"] = 0

    state["supervisor"] = supervisor_state

    # 하위 호환 미러링
    state["status"] = supervisor_state["status"]
    state["current_task"] = supervisor_state["current_task"]
    state["revision_history"] = supervisor_state["revision_history"]

    # 에이전트 로컬 네임스페이스 초기화 (오염 방지)
    state.setdefault("market_agent", {})
    state.setdefault("lges_agent", {})
    state.setdefault("catl_agent", {})
    state.setdefault("comparison_agent", {})
    state.setdefault("validation_agent", {})
    state.setdefault("report_agent", {})
    state.setdefault("reflection_agent", {})

    return state


def route_from_supervisor(state: GraphState) -> str:
    """
    Supervisor Pattern 분기 기준.

    [종료 조건 — 최우선]
      status ∈ {COMPLETED, FAILED} → "END"

    [태스크 라우팅]
      T1 → "research_phase"  : 병렬 fan-out (최초 실행)
      T2 → "lges_strategy"   : validation REVISE 재시도 진입점
      T3 → "catl_strategy"   : T2 직후 순차 실행
      T4 → "validation"      : Research 결과 검증
      T5 → "comparison"      : 검증 통과 후 비교 프레임 생성
      T6 → "swot"            : comparison 후 SWOT 생성
      T7 → "report_writer"   : SWOT 후 보고서 생성
                               reflection REVISE 시 재진입점
      T8 → "reflection"      : 보고서 품질 점검
    """
    supervisor_state = state.get("supervisor", {})
    status = supervisor_state.get("status", state.get("status", "IN_PROGRESS"))

    if status in {"COMPLETED", "FAILED"}:
        return "END"

    task = supervisor_state.get("current_task", state.get("current_task", "T1"))
    task_to_node = {
        "T1": "research_phase",
        "T2": "lges_strategy",
        "T3": "catl_strategy",
        "T4": "validation",
        "T5": "comparison",
        "T6": "swot",
        "T7": "report_writer",
        "T8": "reflection",
    }
    return task_to_node.get(task, "validation")
