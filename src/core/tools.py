from langchain_community.tools.tavily_search import TavilySearchResults

# Tavily API 키가 있을 때만 초기화한다 (지연 초기화).
_web_search_tool = None


def get_web_search_tool():
    """Tavily Web Search 툴을 지연 초기화해서 반환한다."""
    global _web_search_tool
    if _web_search_tool is None:
        try:
            _web_search_tool = TavilySearchResults(max_results=5)
        except Exception as e:
            print(f"[Warning] Tavily API 초기화 실패: {e}")
            _web_search_tool = None
    return _web_search_tool
