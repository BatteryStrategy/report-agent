from langchain_community.tools.tavily_search import TavilySearchResults

# 공통 Tool - Tavily Web Search
web_search_tool = TavilySearchResults(max_results=5)
