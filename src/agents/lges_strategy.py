"""
LGES Strategy Agent (T2).

역할: LG에너지솔루션 전략·재무·제품 기초 근거 수집
출력: state["lges_strategy"]
검색 정책: RAG 우선 → 부족 시 Tavily Fallback
"""

from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI

from src.core.rag import SingletonRAG
from src.core.rag_policy import (
    docs_to_context,
    docs_to_references,
    is_sufficient,
)
from src.core.state import GraphState
from src.core.tools import get_web_search_tool

logger = logging.getLogger(__name__)

# data/raw/lges/ 의 PDF를 사용한다.
_rag = SingletonRAG.get_instance("lges")
_rag.__init__()  # Singleton 최초 1회 초기화 (이미 됐으면 no-op)

# ─────────────────────────────────────────────
# 검색 쿼리 목록
# ─────────────────────────────────────────────
_RAG_QUERIES = [
    "LGES LG에너지솔루션 배터리 전략 사업 방향",
    "LGES 재무 실적 매출 수익성",
    "LG에너지솔루션 제품 포트폴리오 기술 경쟁력",
    "LG에너지솔루션 리스크 위협 약점 경쟁 위험",
]

# Validation 필수 항목(재무·기술·시장·리스크)과 1:1 대응
_TAVILY_QUERIES = [
    "LG에너지솔루션 LGES 재무 실적 매출 영업이익 2024 2025",   # 재무
    "LG에너지솔루션 배터리 기술 경쟁력 제품 포트폴리오",        # 기술
    "LGES 배터리 시장 점유율 고객사 글로벌 포지셔닝",           # 시장
    "LG에너지솔루션 리스크 위협 약점 경쟁 위험 요인 2024",      # 리스크
]

# ─────────────────────────────────────────────
# LLM 프롬프트
# ─────────────────────────────────────────────
_SYSTEM_PROMPT = """당신은 배터리 산업 전문 기업 분석 애널리스트입니다.
제공된 문서를 바탕으로 LG에너지솔루션(LGES)에 대해 아래 항목을 분석하세요.

[분석 항목]
1. 핵심 사업 전략: 중장기 방향, 주요 투자, 파트너십
2. 재무 현황: 매출, 영업이익, 수익성 추이 및 전망
3. 제품·기술 경쟁력: 주력 배터리 제품, 기술 차별화 포인트
4. 주요 고객·시장: 핵심 고객사, 지역별 포지셔닝
5. 리스크 요인: 주요 위협 및 약점

[출력 지침]
- 반드시 재무·기술·시장·리스크 4개 항목을 모두 포함하세요. 누락 시 검증 실패 처리됩니다.
- 긍정적 근거와 부정적 근거를 모두 균형 있게 서술하세요.
- 수치·주장 뒤에 반드시 (출처: 파일명 또는 URL) 형식으로 인라인 출처를 명시하세요. [1], Web 1 같은 번호 형식은 사용하지 마세요.
- 각 항목을 명확한 소제목으로 구분하세요.
"""


def lges_strategy_node(state: GraphState) -> GraphState:
    """
    T2 LGES Strategy 노드.

    1. RAG(내부 문서) 검색
    2. 부족 판정 → Tavily Fallback
    3. LLM으로 LGES 전략 분석 합성
    4. state["lges_strategy"], state["lges_agent"] 기록
    5. Supervisor에 T3 진행 신호
    """
    logger.info("[T2] lges_strategy_node 시작")

    retriever = _rag.get_retriever()

    # ── 1. RAG 검색 ──────────────────────────────────────
    rag_docs: list = []
    for query in _RAG_QUERIES:
        try:
            docs = retriever.invoke(query)
            rag_docs.extend(docs)
        except Exception as exc:
            logger.warning("[T2] RAG 검색 실패 (query=%s): %s", query, exc)

    # 중복 청크 제거
    seen: set[str] = set()
    unique_rag_docs: list = []
    for d in rag_docs:
        key = getattr(d, "page_content", "")[:100]
        if key not in seen:
            seen.add(key)
            unique_rag_docs.append(d)

    # ── 2. 부족 판정 → Tavily Fallback ───────────────────
    sufficient, reason = is_sufficient(unique_rag_docs, "lges")
    fallback_used = False
    web_results: list[dict] = []

    if not sufficient:
        logger.info("[T2] RAG 부족(%s) → Tavily fallback 사용", reason)
        fallback_used = True
        web_tool = get_web_search_tool()
        if web_tool:
            for query in _TAVILY_QUERIES:
                try:
                    results = web_tool.invoke(query)
                    if isinstance(results, list):
                        web_results.extend(results)
                except Exception as exc:
                    logger.warning("[T2] Tavily 검색 실패 (query=%s): %s", query, exc)
        else:
            logger.warning("[T2] Tavily 툴 미초기화 — fallback 불가")

    # ── 3. 컨텍스트 구성 ─────────────────────────────────
    rag_context = docs_to_context(unique_rag_docs)

    web_context = ""
    if web_results:
        parts = [
            f"(출처: {r.get('url', 'unknown')})\n{str(r.get('content', ''))[:600]}"
            for r in web_results[:6]
        ]
        web_context = "\n\n".join(parts)

    context = f"=== 내부 문서(RAG) ===\n{rag_context}"
    if web_context:
        context += f"\n\n=== 웹 검색 결과(Tavily) ===\n{web_context}"

    # ── 4. LLM 합성 ──────────────────────────────────────
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    topic: str = state.get("report_topic") or ""
    topic_prefix = f"[보고서 주제: {topic}]\n이 주제 관점에서 LGES를 분석하세요.\n\n" if topic else ""

    try:
        response = llm.invoke([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": topic_prefix + "아래 자료를 바탕으로 LG에너지솔루션(LGES) 전략을 분석하세요.\n\n" + context},
        ])
        analysis_text: str = response.content
    except Exception as exc:
        logger.error("[T2] LLM 호출 실패: %s", exc)
        analysis_text = f"[LLM 오류로 분석 생략] RAG 원문:\n{rag_context[:1000]}"

    # ── 5. references 누적 ───────────────────────────────
    references = docs_to_references(unique_rag_docs)
    for r in web_results[:6]:
        references.append({
            "source": r.get("url", "web"),
            "page": None,
            "snippet": str(r.get("content", ""))[:200],
        })

    # ── 6. 상태 기록 ─────────────────────────────────────
    state["lges_agent"] = {
        **state.get("lges_agent", {}),
        "query": _RAG_QUERIES,
        "retrieved_docs": [
            {"page_content": getattr(d, "page_content", ""), "metadata": getattr(d, "metadata", {})}
            for d in unique_rag_docs
        ],
        "fallback_used": fallback_used,
        "output": {"raw": analysis_text},
    }

    state["lges_strategy"] = {
        "content": analysis_text,
        "fallback_used": fallback_used,
        "rag_doc_count": len(unique_rag_docs),
        "web_result_count": len(web_results),
    }

    state["references"] = list(state.get("references") or []) + references

    # ── 7. Supervisor 진행 신호 (T2 → T3) ────────────────
    supervisor = dict(state.get("supervisor") or {})
    supervisor["current_task"] = "T3"
    state["supervisor"] = supervisor
    state["current_task"] = "T3"

    logger.info(
        "[T2] 완료 — fallback=%s, rag_docs=%d, web=%d",
        fallback_used,
        len(unique_rag_docs),
        len(web_results),
    )
    return state
