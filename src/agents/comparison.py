from src.core.rag import SingletonRAG
from src.core.state import GraphState

# 비교 에이전트는 공통 문서(data/raw/common/)를 참조한다.
_rag = SingletonRAG.get_instance("common")


def comparison_node(state: GraphState) -> GraphState:
    """T4 Comparison — 현재 stub: T5 validation으로 진행."""
    supervisor = dict(state.get("supervisor") or {})
    supervisor["current_task"] = "T5"
    state["supervisor"] = supervisor
    state["current_task"] = "T5"
    return state
