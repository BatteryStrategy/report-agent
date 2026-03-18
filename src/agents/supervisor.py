from src.core.state import GraphState


def supervisor_node(state: GraphState) -> GraphState:
    """중앙 관리자: 제어 상태를 supervisor 네임스페이스에만 기록한다."""
    supervisor_state = state.get("supervisor", {})

    if "status" not in supervisor_state:
        supervisor_state["status"] = "IN_PROGRESS"
    if "current_task" not in supervisor_state:
        supervisor_state["current_task"] = "T1"
    if "revision_history" not in supervisor_state:
        supervisor_state["revision_history"] = []

    state["supervisor"] = supervisor_state

    # 하위 호환: 기존 top-level 키를 읽는 코드가 깨지지 않도록 미러링
    state["status"] = supervisor_state["status"]
    state["current_task"] = supervisor_state["current_task"]
    state["revision_history"] = supervisor_state["revision_history"]

    # 에이전트 로컬 네임스페이스 기본값 초기화 (오염 방지)
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

    종료 조건:
    - status == "COMPLETED" or "FAILED"  → END  (무한루프 방지)

    태스크 라우팅:
    - T1 → research_phase  : market·lges·catl 병렬 fan-out (최초 실행)
    - T2 → lges_strategy   : validation REVISE 시 재시도 진입점
    - T3 → catl_strategy   : T2 재실행 후 순차 진행
    - T4 → comparison
    - T5 → validation      : PASS → T6 / REVISE → T2(최대 2회) / 초과 → FAILED
    - T6 → report_writer
    - T7 → reflection      : 품질 점검 후 COMPLETED 설정
    """
    supervisor_state = state.get("supervisor", {})
    status = supervisor_state.get("status", state.get("status", "IN_PROGRESS"))
    if status in {"COMPLETED", "FAILED"}:
        return "END"

    task = supervisor_state.get("current_task", state.get("current_task", "T1"))
    task_to_node = {
        "T1": "research_phase",   # Fan-out: T1·T2·T3 병렬 실행
        "T2": "lges_strategy",    # REVISE 재시도 진입점 (T2 → T3 → T4 → T5 순차)
        "T3": "catl_strategy",
        "T4": "comparison",
        "T5": "validation",
        "T6": "report_writer",
        "T7": "reflection",
    }
    return task_to_node.get(task, "validation")
