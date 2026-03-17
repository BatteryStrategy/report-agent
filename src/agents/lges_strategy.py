from src.core.rag import SingletonRAG
from src.core.state import GraphState

# data/raw/lges/ 의 PDF를 사용한다.
_rag = SingletonRAG.get_instance("lges")


def lges_strategy_node(state: GraphState) -> GraphState:
    pass
