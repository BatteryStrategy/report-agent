"""
RAG 부족 판정 정책 공통 유틸.

모든 Research 노드가 동일한 판정 기준을 사용한다:
  1. 최소 문서 수(MIN_DOCS)
  2. 최소 평균 관련도(MIN_RELEVANCE)
  3. 시맨틱 토픽 커버리지 — 임베딩 코사인 유사도 기반 (언어 무관)
  4. 최소 고유 출처 수(MIN_SOURCES)

키워드 문자열 매칭 대신 bge-m3 임베딩 유사도를 사용하므로
한글/영문 PDF 모두 동일하게 동작한다.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from langchain_core.documents import Document

# ─────────────────────────────────────────────────────────────
# 판정 상수
# ─────────────────────────────────────────────────────────────

MIN_DOCS: int = 3
MIN_RELEVANCE: float = 0.4
MIN_SOURCES: int = 1

#: 시맨틱 토픽 커버리지 임계값 (코사인 유사도 0~1)
#: bge-m3 기준 0.45 이상이면 "관련 있음"으로 판정
TOPIC_SIMILARITY_THRESHOLD: float = 0.45

#: 네임스페이스별 필수 토픽 — 자연어 구절로 기술, 언어 무관
#: bge-m3는 다국어 모델이므로 한글/영문 혼용 가능
REQUIRED_TOPICS: dict[str, list[str]] = {
    "market": [
        "전기차 EV 시장 동향 수요",
        "ESS energy storage 에너지저장장치 시장",
    ],
    "lges": [
        "LG에너지솔루션 LG Energy Solution 사업 전략 strategy",
        "배터리 battery 재무 매출 영업이익 financial revenue",
    ],
    "catl": [
        "CATL 배터리 사업 전략 battery strategy",
        "CATL 재무 매출 영업이익 financial revenue",
    ],
}


# ─────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────

def _normalize_docs(
    raw: list[Document | tuple[Document, float] | dict[str, Any]],
) -> list[dict[str, Any]]:
    """다양한 형태의 검색 결과를 통일된 dict 리스트로 변환한다."""
    result: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, tuple):
            doc, score = item
            result.append({
                "page_content": doc.page_content,
                "metadata": doc.metadata,
                "score": float(score),
            })
        elif isinstance(item, Document):
            result.append({
                "page_content": item.page_content,
                "metadata": item.metadata,
                "score": 1.0,
            })
        elif isinstance(item, dict):
            result.append(item)
    return result


def _avg_relevance(docs: list[dict[str, Any]]) -> float:
    """FAISS L2 거리를 0~1 관련도로 변환한 평균을 반환한다."""
    if not docs:
        return 0.0
    scores = []
    for d in docs:
        raw = d.get("score", 1.0)
        scores.append(1.0 / (1.0 + raw) if raw > 1.0 else raw)
    return sum(scores) / len(scores)


def _semantic_topic_coverage(
    docs: list[dict[str, Any]],
    namespace: str,
) -> list[str]:
    """
    bge-m3 임베딩 코사인 유사도로 필수 토픽 커버리지를 검사한다.

    - 문서 청크 각각을 임베딩 → 토픽 구절과 유사도 행렬 계산
    - 토픽별로 가장 유사한 청크 유사도가 TOPIC_SIMILARITY_THRESHOLD 미만이면 미커버
    - 한글/영문/혼용 모두 bge-m3 다국어 공간에서 동일하게 처리

    Returns:
        미커버 토픽 목록 (빈 리스트면 전체 커버)
    """
    topics = REQUIRED_TOPICS.get(namespace, [])
    if not topics:
        return []

    contents = [
        d.get("page_content", "")
        for d in docs
        if d.get("page_content", "").strip()
    ]
    if not contents:
        return list(topics)

    # 임베딩 모델은 이미 메모리에 로드된 싱글턴 재사용 (추가 비용 없음)
    from src.core.rag import _get_embedding_model
    model = _get_embedding_model()

    # 배치 임베딩: 토픽과 문서 청크를 한 번에 처리
    topic_vecs = np.array(model.embed_documents(topics))          # (n_topics, dim)
    doc_vecs   = np.array(model.embed_documents(                  # (n_docs, dim)
        [c[:1000] for c in contents]
    ))

    # L2 정규화 → 코사인 유사도 = 내적
    topic_vecs /= (np.linalg.norm(topic_vecs, axis=1, keepdims=True) + 1e-9)
    doc_vecs   /= (np.linalg.norm(doc_vecs,   axis=1, keepdims=True) + 1e-9)

    # 유사도 행렬 (n_topics × n_docs) → 토픽별 최대 유사도
    sim_matrix = topic_vecs @ doc_vecs.T          # (n_topics, n_docs)
    max_sims   = sim_matrix.max(axis=1)           # (n_topics,)

    return [
        topic
        for topic, sim in zip(topics, max_sims)
        if sim < TOPIC_SIMILARITY_THRESHOLD
    ]


def _unique_sources(docs: list[dict[str, Any]]) -> int:
    """고유 출처(metadata.source) 수를 반환한다."""
    return len({
        d.get("metadata", {}).get("source", "")
        for d in docs
        if d.get("metadata", {}).get("source", "")
    })


# ─────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────

def is_sufficient(
    raw_docs: list[Any],
    namespace: str,
) -> tuple[bool, str]:
    """
    RAG 검색 결과가 충분한지 판정한다.

    조건 순서:
      1. 최소 문서 수
      2. 평균 관련도
      3. 시맨틱 토픽 커버리지 (언어 무관)
      4. 최소 고유 출처 수

    Returns:
        (True, "")           — 충분
        (False, reason_msg)  — 부족 사유 포함
    """
    docs = _normalize_docs(raw_docs)

    if len(docs) < MIN_DOCS:
        return False, f"문서 수 부족: {len(docs)} < {MIN_DOCS}"

    avg_rel = _avg_relevance(docs)
    if avg_rel < MIN_RELEVANCE:
        return False, f"평균 관련도 부족: {avg_rel:.3f} < {MIN_RELEVANCE}"

    uncovered = _semantic_topic_coverage(docs, namespace)
    if uncovered:
        return False, f"토픽 미커버: {uncovered}"

    n_sources = _unique_sources(docs)
    if n_sources < MIN_SOURCES:
        return False, f"출처 수 부족: {n_sources} < {MIN_SOURCES}"

    return True, ""


def docs_to_context(raw_docs: list[Any]) -> str:
    """검색 결과 문서를 LLM 컨텍스트용 문자열로 변환한다.

    출처 표기 형식: (출처: 파일명) — 번호 대신 파일명을 사용해
    LLM이 일관된 형식으로 인라인 출처를 작성하도록 유도한다.
    """
    import os
    docs = _normalize_docs(raw_docs)
    if not docs:
        return "(검색 결과 없음)"
    parts = []
    for d in docs:
        raw_source = d.get("metadata", {}).get("source", "unknown")
        # 파일 경로에서 파일명만 추출 (확장자 포함)
        source_name = os.path.basename(raw_source) if raw_source else "unknown"
        content = d.get("page_content", "").strip()
        parts.append(f"(출처: {source_name})\n{content}")
    return "\n\n".join(parts)


def docs_to_references(raw_docs: list[Any]) -> list[dict[str, Any]]:
    """검색 결과를 state['references'] 누적용 표준 형식으로 변환한다."""
    docs = _normalize_docs(raw_docs)
    return [
        {
            "source": d.get("metadata", {}).get("source", "unknown"),
            "page": d.get("metadata", {}).get("page"),
            "snippet": d.get("page_content", "")[:200],
        }
        for d in docs
    ]
