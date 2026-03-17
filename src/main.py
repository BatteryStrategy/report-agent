import os
from glob import glob
from typing import Any, Optional, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.vectorstores import FAISS

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
    market_background: dict[str, Any] # 시장 배경 분석 결과
    lges_strategy: dict[str, Any] # LGES 전략/경쟁력/리스크 분석 결과
    catl_strategy: dict[str, Any] # CATL 전략/경쟁력/리스크 분석 결과
    comparison_result: dict[str, Any] # 공통 비교 프레임 정렬 결과
    swot_result: dict[str, Any] # 양사 SWOT 분석 결과
    validation_result: dict[str, Any] # 검증 판정 (PASS/REVISE) + 사유 목록
    revision_history: list[dict[str, Any]] # 재실행 이력 (어떤 Task가 왜 재실행되었는지)
    references: list[dict[str, Any]] # 실제 활용된 출처 목록
    final_report: str # 최종 보고서 Markdown 텍스트
    status: str # Workflow 상태 (IN_PROGRESS / COMPLETED / FAILED)