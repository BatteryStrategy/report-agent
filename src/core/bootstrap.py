import os

DATA_DIR = "./data"
OUTPUT_DIR = "./output"
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./faiss_index")


def ensure_project_dirs() -> None:
    """프로젝트 실행 시 필수 디렉토리를 보장"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(FAISS_INDEX_PATH, exist_ok=True)
