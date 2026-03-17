import os

DATA_DIR = "./data"
DATA_RAW_DIR = "./data/raw"
DATA_PROCESSED_DIR = "./data/processed"

OUTPUT_DIR = "./output"
OUTPUT_REPORT_DIR = "./output/report"
OUTPUT_LOG_DIR = "./output/logs"
OUTPUT_TMP_DIR = "./output/tmp"

FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./faiss_index")

PROJECT_DIRS = (
    DATA_DIR,
    DATA_RAW_DIR,
    DATA_PROCESSED_DIR,
    OUTPUT_DIR,
    OUTPUT_REPORT_DIR,
    OUTPUT_LOG_DIR,
    OUTPUT_TMP_DIR,
    FAISS_INDEX_PATH,
)


def ensure_project_dirs() -> None:
    """프로젝트 실행 시 필수 디렉토리 구조를 보장한다."""
    for path in PROJECT_DIRS:
        os.makedirs(path, exist_ok=True)
