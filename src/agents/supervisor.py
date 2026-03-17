from src.core.state import GraphState


def supervisor_node(state: GraphState) -> GraphState:
    """중앙 관리자: 상태 점검 및 기본 task/status 초기화."""
    if "status" not in state:
        state["status"] = "IN_PROGRESS"
    if "current_task" not in state:
        state["current_task"] = "T1"
    return state


def route_from_supervisor(state: GraphState) -> str:
    """
    Supervisor Pattern 분기 기준
    - status가 COMPLETED/FAILED이면 END
    - 아니면 current_task(T1~T6)에 따라 워커 할당
    """
    status = state.get("status", "IN_PROGRESS")
    if status in {"COMPLETED", "FAILED"}:
        return "END"

    task = state.get("current_task", "T1")
    task_to_node = {
        "T1": "market_research",
        "T2": "lges_strategy",
        "T3": "catl_strategy",
        "T4": "comparison",
        "T5": "validation",
        "T6": "report_writer",
    }
    return task_to_node.get(task, "validation")
