from src.core.rag import SingletonRAG
from src.core.state import GraphState

# data/raw/market/ 의 PDF를 사용한다.
_rag = SingletonRAG.get_instance("market")


def market_research_node(state: GraphState) -> GraphState:
    pass
