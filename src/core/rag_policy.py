"""
RAG 부족 판정 정책 공통 유틸.

모든 Research 노드가 동일한 판정 기준을 사용한다:
  1. 최소 문서 수(MIN_DOCS)
  2. 최소 평균 관련도(MIN_RELEVANCE) — FAISS similarity_search_with_score 점수 기반
  3. 필수 키워드 커버리지(REQUIRED_KEYWORDS)
  4. 최소 고유 출처 수(MIN_SOURCES)

위 조건 중 하나라도 실패하면 Tavily Fallback을 사용한다.
"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document

# ─────────────────────────────────────────────────────────────
# 판정 상수 — 임계값 조정 시 이 블록만 수정한다
# ─────────────────────────────────────────────────────────────

#: 최소 문서 수. 내부 근거가 너무 적으면 신뢰도가 낮다.
MIN_DOCS: int = 3

#: 평균 관련도 하한 (0 = 완전 무관, 1 = 완전 일치).
#: FAISS L2 거리를 1 / (1 + dist) 로 정규화한 값 기준.
MIN_RELEVANCE: float = 0.4

#: 최소 고유 출처 수. 단일 문서에만 의존하면 편향 위험.
MIN_SOURCES: int = 2

#: 노드별 필수 키워드 — 모두 커버되어야 PASS.
REQUIRED_KEYWORDS: dict[str, list[str]] = {
    "market": ["전기차", "ESS"],
    "lges": ["LGES", "배터리", "전략", "재무"],
    "catl": ["CATL", "배터리", "전략", "재무"],
}


# ─────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────

def _normalize_docs(
    raw: list[Document | tuple[Document, float] | dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    다양한 형태의 검색 결과를 통일된 dict 리스트로 변환한다.

    지원 형태:
    - LangChain Document 객체
    - (Document, score) 튜플 (similarity_search_with_score 반환값)
    - 이미 dict인 경우
    """
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
                "score": 1.0,  # score 없으면 충분하다고 가정
            })
        elif isinstance(item, dict):
            result.append(item)
        else:
            # 예상치 못한 타입은 무시
            pass
    return result


def _avg_relevance(docs: list[dict[str, Any]]) -> float:
    """FAISS score는 L2 거리 → 낮을수록 유사. 0~1 사이 관련도로 변환."""
    if not docs:
        return 0.0
    scores = []
    for d in docs:
        raw_score = d.get("score", 1.0)
        # similarity_search_with_score 반환값이 거리(distance)일 경우 정규화
        # 거리가 크면(> 1) 유사도 변환; 이미 0~1이면 그대로 사용
        if raw_score > 1.0:
            normalized = 1.0 / (1.0 + raw_score)
        else:
            normalized = raw_score
        scores.append(normalized)
    return sum(scores) / len(scores)


def _keyword_coverage(docs: list[dict[str, Any]], keywords: list[str]) -> list[str]:
    """필수 키워드 중 문서에 없는 것(누락 목록)을 반환한다."""
    if not keywords:
        return []
    combined = " ".join(d.get("page_content", "") for d in docs)
    return [kw for kw in keywords if kw not in combined]


def _unique_sources(docs: list[dict[str, Any]]) -> int:
    """고유 출처(metadata.source) 수를 반환한다."""
    sources = {
        d.get("metadata", {}).get("source", "")
        for d in docs
        if d.get("metadata", {}).get("source", "")
    }
    return len(sources)


# ─────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────

def is_sufficient(
    raw_docs: list[Any],
    namespace: str,
) -> tuple[bool, str]:
    """
    RAG 검색 결과가 fallback 없이 충분한지 판정한다.

    Args:
        raw_docs: retriever 또는 similarity_search_with_score 반환값.
        namespace: "market" | "lges" | "catl" | "common"

    Returns:
        (True, "")            — 충분
        (False, reason_msg)   — 부족 사유 포함
    """
    docs = _normalize_docs(raw_docs)
    keywords = REQUIRED_KEYWORDS.get(namespace, [])

    # 조건 1: 최소 문서 수
    if len(docs) < MIN_DOCS:
        return False, f"문서 수 부족: {len(docs)} < {MIN_DOCS}"

    # 조건 2: 평균 관련도
    avg_rel = _avg_relevance(docs)
    if avg_rel < MIN_RELEVANCE:
        return False, f"평균 관련도 부족: {avg_rel:.3f} < {MIN_RELEVANCE}"

    # 조건 3: 필수 키워드 커버리지
    missing_kws = _keyword_coverage(docs, keywords)
    if missing_kws:
        return False, f"필수 키워드 누락: {missing_kws}"

    # 조건 4: 최소 고유 출처 수
    n_sources = _unique_sources(docs)
    if n_sources < MIN_SOURCES:
        return False, f"출처 수 부족: {n_sources} < {MIN_SOURCES}"

    return True, ""


def docs_to_context(raw_docs: list[Any]) -> str:
    """
    검색 결과 문서를 LLM 컨텍스트용 문자열로 변환한다.
    에이전트 프롬프트에 삽입하는 용도.
    """
    docs = _normalize_docs(raw_docs)
    if not docs:
        return "(검색 결과 없음)"
    parts = []
    for i, d in enumerate(docs, 1):
        source = d.get("metadata", {}).get("source", "unknown")
        content = d.get("page_content", "").strip()
        parts.append(f"[{i}] 출처: {source}\n{content}")
    return "\n\n".join(parts)


def docs_to_references(raw_docs: list[Any]) -> list[dict[str, Any]]:
    """
    검색 결과를 state['references'] 누적용 표준 형식으로 변환한다.
    """
    docs = _normalize_docs(raw_docs)
    refs = []
    for d in docs:
        meta = d.get("metadata", {})
        refs.append({
            "source": meta.get("source", "unknown"),
            "page": meta.get("page", None),
            "snippet": d.get("page_content", "")[:200],
        })
    return refs
