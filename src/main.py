import os
from glob import glob
from typing import Any, Optional, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.vectorstores import FAISS
from langgraph.graph import END, START, StateGraph

# 프로젝트 실행 시 필수 디렉토리를 자동으로 생성한다.
DATA_DIR = "./data"
OUTPUT_DIR = "./output"
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./faiss_index")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(FAISS_INDEX_PATH, exist_ok=True)


class SingletonRAG:
    """PDF -> FAISS 인덱스를 1회만 구성하는 싱글톤 RAG 클래스."""

    _instance: Optional["SingletonRAG"] = None

    def __new__(cls) -> "SingletonRAG":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self.embedding_model = HuggingFaceEmbeddings(
            model_name="BAAI/bge-m3",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=150,
        )
        self.vectorstore = self._build_or_load_vectorstore()
        self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 5})

        self._initialized = True

    def _build_or_load_vectorstore(self) -> FAISS:
        # 기존 인덱스가 있으면 재사용한다.
        index_file = os.path.join(FAISS_INDEX_PATH, "index.faiss")
        if os.path.exists(index_file):
            return FAISS.load_local(
                FAISS_INDEX_PATH,
                self.embedding_model,
                allow_dangerous_deserialization=True,
            )

        pdf_files = glob(os.path.join(DATA_DIR, "*.pdf"))
        documents = []

        for pdf_path in pdf_files:
            loader = PyPDFLoader(pdf_path)
            documents.extend(loader.load())

        split_docs = self.text_splitter.split_documents(documents)

        if not split_docs:
            # 데이터가 없어도 기본 인덱스를 생성해 retriever 호출을 안전하게 유지한다.
            vectorstore = FAISS.from_texts(
                texts=["No PDF data available yet."],
                embedding=self.embedding_model,
                metadatas=[{"source": "bootstrap"}],
            )
        else:
            vectorstore = FAISS.from_documents(split_docs, self.embedding_model)

        vectorstore.save_local(FAISS_INDEX_PATH)
        return vectorstore

    def get_retriever(self):
        """다른 에이전트에서 공통으로 사용할 retriever를 반환한다."""
        return self.retriever


# 어디서든 import 해서 동일 인스턴스 재사용
rag = SingletonRAG()


# 공통 Tool - Tavily Web Search
web_search_tool = TavilySearchResults(max_results=5)


class GraphState(TypedDict, total=False):
    """Supervisor/Worker가 공유하는 그래프 상태 스키마."""

    current_task: str  # 현재 실행 중인 Task ID (T1~T6)
    market_background: dict[str, Any]  # 시장 배경 분석 결과
    lges_strategy: dict[str, Any]  # LGES 전략/경쟁력/리스크 분석 결과
    catl_strategy: dict[str, Any]  # CATL 전략/경쟁력/리스크 분석 결과
    comparison_result: dict[str, Any]  # 공통 비교 프레임 정렬 결과
    swot_result: dict[str, Any]  # 양사 SWOT 분석 결과
    validation_result: dict[str, Any]  # 검증 판정 (PASS/REVISE) + 사유 목록
    revision_history: list[dict[str, Any]]  # 재실행 이력
    references: list[dict[str, Any]]  # 실제 활용된 출처 목록
    final_report: str  # 최종 보고서 Markdown 텍스트
    status: str  # Workflow 상태 (IN_PROGRESS / COMPLETED / FAILED)


def supervisor_node(state: GraphState) -> GraphState:
    """중앙 관리자: 현재 상태를 점검하고 다음 Task 결정을 위한 상태를 유지한다."""
    if "status" not in state:
        state["status"] = "IN_PROGRESS"
    if "current_task" not in state:
        state["current_task"] = "T1"
    return state


def route_from_supervisor(state: GraphState) -> str:
    """
    Supervisor Pattern 분기 기준
    - status가 COMPLETED/FAILED이면 종료(END)
    - 그렇지 않으면 current_task(T1~T6)에 맞는 워커로 라우팅
    """
    status = state.get("status", "IN_PROGRESS")
    if status in {"COMPLETED", "FAILED"}:
        return "END"

    task = state.get("current_task", "T1")
    task_to_node = {
        "T1": "market_research",
        "T2": "lges_strategy",
        "T3": "catl_strategy",
        "T4": "comparison",
        "T5": "validation",
        "T6": "report_writer",
    }
    return task_to_node.get(task, "validation")


def market_research_node(state: GraphState) -> GraphState:
    # TODO: Commit 범위 외 - 워커 구현 예정
    pass


def lges_strategy_node(state: GraphState) -> GraphState:
    # TODO: Commit 범위 외 - 워커 구현 예정
    pass


def catl_strategy_node(state: GraphState) -> GraphState:
    # TODO: Commit 범위 외 - 워커 구현 예정
    pass


def validation_node(state: GraphState) -> GraphState:
    # TODO: Commit 범위 외 - 워커 구현 예정
    pass


def comparison_node(state: GraphState) -> GraphState:
    # TODO: Commit 범위 외 - 워커 구현 예정
    pass


def report_writer_node(state: GraphState) -> GraphState:
    # TODO: Commit 범위 외 - 워커 구현 예정
    pass


def build_graph():
    """Supervisor + 6 Worker 노드를 포함한 StateGraph 뼈대를 구성한다."""
    graph_builder = StateGraph(GraphState)

    graph_builder.add_node("supervisor", supervisor_node)
    graph_builder.add_node("market_research", market_research_node)
    graph_builder.add_node("lges_strategy", lges_strategy_node)
    graph_builder.add_node("catl_strategy", catl_strategy_node)
    graph_builder.add_node("validation", validation_node)
    graph_builder.add_node("comparison", comparison_node)
    graph_builder.add_node("report_writer", report_writer_node)

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
            "END": END,
        },
    )

    # Worker 완료 후 다음 의사결정은 항상 Supervisor가 담당한다.
    graph_builder.add_edge("market_research", "supervisor")
    graph_builder.add_edge("lges_strategy", "supervisor")
    graph_builder.add_edge("catl_strategy", "supervisor")
    graph_builder.add_edge("comparison", "supervisor")
    graph_builder.add_edge("validation", "supervisor")
    graph_builder.add_edge("report_writer", "supervisor")

    return graph_builder.compile()


app_graph = build_graph()