from langgraph.graph import END, START, StateGraph

from src.agents.catl_strategy import catl_strategy_node
from src.agents.comparison import comparison_node
from src.agents.lges_strategy import lges_strategy_node
from src.agents.market_research import market_research_node
from src.agents.reflection import reflection_node
from src.agents.report_writer import report_writer_node
from src.agents.supervisor import route_from_supervisor, supervisor_node
from src.agents.validation import validation_node
from src.core.state import GraphState


def build_graph():
    """Supervisor + 7 Worker 노드를 포함한 StateGraph 뼈대를 구성한다."""
    graph_builder = StateGraph(GraphState)

    graph_builder.add_node("supervisor", supervisor_node)
    graph_builder.add_node("market_research", market_research_node)
    graph_builder.add_node("lges_strategy", lges_strategy_node)
    graph_builder.add_node("catl_strategy", catl_strategy_node)
    graph_builder.add_node("validation", validation_node)
    graph_builder.add_node("comparison", comparison_node)
    graph_builder.add_node("report_writer", report_writer_node)
    graph_builder.add_node("reflection", reflection_node)

    graph_builder.add_edge(START, "supervisor")

    graph_builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "market_research": "market_research",
            "lges_strategy": "lges_strategy",
            "catl_strategy": "catl_strategy",
            "comparison": "comparison",
            "validation": "validation",
            "report_writer": "report_writer",
            "reflection": "reflection",
            "END": END,
        },
    )

    graph_builder.add_edge("market_research", "supervisor")
    graph_builder.add_edge("lges_strategy", "supervisor")
    graph_builder.add_edge("catl_strategy", "supervisor")
    graph_builder.add_edge("comparison", "supervisor")
    graph_builder.add_edge("validation", "supervisor")
    graph_builder.add_edge("report_writer", "supervisor")
    graph_builder.add_edge("reflection", "supervisor")

    return graph_builder.compile()
