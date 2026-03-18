from src.core.rag import SingletonRAG
from src.core.state import GraphState

# 리플렉션 에이전트는 공통 문서(data/raw/common/)를 참조한다.
_rag = SingletonRAG.get_instance("common")


def reflection_node(state: GraphState) -> GraphState:
    """T7 Reflection — 현재 stub: COMPLETED 처리."""
    supervisor = dict(state.get("supervisor") or {})
    supervisor["status"] = "COMPLETED"
    state["supervisor"] = supervisor
    state["status"] = "COMPLETED"
    return state
