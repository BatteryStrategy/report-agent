from src.core.rag import SingletonRAG
from src.core.state import GraphState

# 비교 에이전트는 공통 문서(data/raw/common/)를 참조한다.
_rag = SingletonRAG.get_instance("common")


def comparison_node(state: GraphState) -> GraphState:
    pass
