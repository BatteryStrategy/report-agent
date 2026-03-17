import os
from glob import glob
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

# Commit 1: 프로젝트 실행 시 필수 디렉토리를 자동으로 생성한다.
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
