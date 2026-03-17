from src.core.bootstrap import ensure_project_dirs
from src.core.rag import rag
from src.core.tools import web_search_tool
from src.graph.workflow import build_graph

ensure_project_dirs()

# 전역 접근 포인트: 앱 실행 시 공통 자원을 미리 초기화
app_graph = build_graph()

__all__ = ["app_graph", "rag", "web_search_tool"]