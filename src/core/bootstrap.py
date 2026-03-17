import os

DATA_DIR = "./data"
DATA_RAW_DIR = "./data/raw"
DATA_PROCESSED_DIR = "./data/processed"

# 에이전트별 PDF 저장 경로
# 각 에이전트는 자신의 네임스페이스 폴더에 PDF를 넣어 독립된 RAG 인덱스를 사용한다.
RAG_NAMESPACES = ("market", "lges", "catl", "common")

OUTPUT_DIR = "./output"
OUTPUT_REPORT_DIR = "./output/report"
OUTPUT_LOG_DIR = "./output/logs"
OUTPUT_TMP_DIR = "./output/tmp"

FAISS_INDEX_BASE = os.getenv("FAISS_INDEX_PATH", "./faiss_index")

# 하위 호환을 위해 FAISS_INDEX_PATH도 유지
FAISS_INDEX_PATH = FAISS_INDEX_BASE

PROJECT_DIRS = (
    DATA_DIR,
    DATA_RAW_DIR,
    DATA_PROCESSED_DIR,
    OUTPUT_DIR,
    OUTPUT_REPORT_DIR,
    OUTPUT_LOG_DIR,
    OUTPUT_TMP_DIR,
)


def ensure_project_dirs() -> None:
    """프로젝트 실행 시 필수 디렉토리 구조를 보장한다."""
    for path in PROJECT_DIRS:
        os.makedirs(path, exist_ok=True)

    # 에이전트별 데이터 및 FAISS 인덱스 디렉토리 생성
    for ns in RAG_NAMESPACES:
        os.makedirs(os.path.join(DATA_RAW_DIR, ns), exist_ok=True)
        os.makedirs(os.path.join(FAISS_INDEX_BASE, ns), exist_ok=True)


def get_raw_data_dir(namespace: str) -> str:
    """에이전트 네임스페이스에 해당하는 PDF 원본 폴더 경로를 반환한다."""
    return os.path.join(DATA_RAW_DIR, namespace)


def get_faiss_index_dir(namespace: str) -> str:
    """에이전트 네임스페이스에 해당하는 FAISS 인덱스 폴더 경로를 반환한다."""
    return os.path.join(FAISS_INDEX_BASE, namespace)
