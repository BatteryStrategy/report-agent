from src.core.bootstrap import ensure_project_dirs
from src.core.tools import web_search_tool
from src.graph.workflow import build_graph

# 디렉토리 보장 → 그래프 빌드 순서를 지킨다.
ensure_project_dirs()

# RAG 인스턴스는 각 에이전트에서 namespace 별로 직접 호출한다.
# 예: SingletonRAG.get_instance("lges") / "catl" / "market" / "common"
app_graph = build_graph()

__all__ = ["app_graph", "web_search_tool"]