from src.core.rag import SingletonRAG
from src.core.state import GraphState

# 보고서 작성 에이전트는 공통 문서(data/raw/common/)를 참조한다.
_rag = SingletonRAG.get_instance("common")


def report_writer_node(state: GraphState) -> GraphState:
    """T6 Report Writer — 현재 stub: T7 reflection으로 진행."""
    supervisor = dict(state.get("supervisor") or {})
    supervisor["current_task"] = "T7"
    state["supervisor"] = supervisor
    state["current_task"] = "T7"
    state["final_report"] = "(stub) 보고서 생성 예정"
    return state
