import os
from glob import glob

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.core.bootstrap import (
    ensure_project_dirs,
    get_faiss_index_dir,
    get_raw_data_dir,
)

# 임베딩 모델은 모든 인스턴스가 공유한다. (메모리 중복 로드 방지)
_shared_embedding_model: HuggingFaceEmbeddings | None = None


def _get_embedding_model() -> HuggingFaceEmbeddings:
    global _shared_embedding_model
    if _shared_embedding_model is None:
        _shared_embedding_model = HuggingFaceEmbeddings(
            model_name="BAAI/bge-m3",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _shared_embedding_model


class SingletonRAG:
    """
    네임스페이스별로 독립된 FAISS 인덱스를 1회만 구성하는 RAG 클래스.

    사용 예:
        rag_lges = SingletonRAG.get_instance("lges")   # data/raw/lges/ 의 PDF 사용
        rag_catl = SingletonRAG.get_instance("catl")   # data/raw/catl/ 의 PDF 사용
        rag_market = SingletonRAG.get_instance("market") # data/raw/market/ 의 PDF 사용
    """

    _registry: dict[str, "SingletonRAG"] = {}

    @classmethod
    def get_instance(cls, namespace: str = "common") -> "SingletonRAG":
        """네임스페이스에 해당하는 RAG 인스턴스를 반환한다."""
        if namespace not in cls._registry:
            instance = object.__new__(cls)
            instance._initialized = False
            instance._namespace = namespace
            cls._registry[namespace] = instance
        return cls._registry[namespace]

    def __init__(self) -> None:
        # get_instance()를 통해서만 생성되므로 직접 호출 방지
        if getattr(self, "_initialized", False):
            return

        ensure_project_dirs()

        self.embedding_model = _get_embedding_model()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=150,
        )
        self._data_dir = get_raw_data_dir(self._namespace)
        self._index_dir = get_faiss_index_dir(self._namespace)

        self.vectorstore = self._build_or_load_vectorstore()
        self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 5})

        self._initialized = True

    def _build_or_load_vectorstore(self) -> FAISS:
        index_file = os.path.join(self._index_dir, "index.faiss")
        if os.path.exists(index_file):
            return FAISS.load_local(
                self._index_dir,
                self.embedding_model,
                allow_dangerous_deserialization=True,
            )

        # 네임스페이스 폴더 하위의 모든 PDF를 수집한다.
        pdf_files = sorted(glob(os.path.join(self._data_dir, "**", "*.pdf"), recursive=True))
        documents = []

        for pdf_path in pdf_files:
            loader = PyPDFLoader(pdf_path)
            documents.extend(loader.load())

        split_docs = self.text_splitter.split_documents(documents)

        if not split_docs:
            vectorstore = FAISS.from_texts(
                texts=[f"[{self._namespace}] No PDF data available yet."],
                embedding=self.embedding_model,
                metadatas=[{"source": "bootstrap", "namespace": self._namespace}],
            )
        else:
            vectorstore = FAISS.from_documents(split_docs, self.embedding_model)

        vectorstore.save_local(self._index_dir)
        return vectorstore

    def get_retriever(self):
        """에이전트에서 공통으로 사용할 retriever를 반환한다."""
        return self.retriever
