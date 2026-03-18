"""
CATL Strategy Agent (T3).

역할: CATL 전략·재무·제품 기초 근거 수집
출력: state["catl_strategy"]
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

# data/raw/catl/ 의 PDF를 사용한다.
_rag = SingletonRAG.get_instance("catl")
_rag.__init__()  # Singleton 최초 1회 초기화 (이미 됐으면 no-op)

# ─────────────────────────────────────────────
# 검색 쿼리 목록
# ─────────────────────────────────────────────
_RAG_QUERIES = [
    "CATL 배터리 전략 사업 방향",
    "CATL 재무 실적 매출 수익성",
    "CATL 제품 포트폴리오 기술 경쟁력",
]

_TAVILY_QUERIES = [
    "CATL 배터리 전략 사업 2024 2025",
    "CATL 재무 실적 영업이익 매출 2024",
    "CATL 기술 제품 포트폴리오 경쟁력 LFP",
]

# ─────────────────────────────────────────────
# LLM 프롬프트
# ─────────────────────────────────────────────
_SYSTEM_PROMPT = """당신은 배터리 산업 전문 기업 분석 애널리스트입니다.
제공된 문서를 바탕으로 CATL(Contemporary Amperex Technology Co., Limited)에 대해 아래 항목을 분석하세요.

[분석 항목]
1. 핵심 사업 전략: 중장기 방향, 주요 투자, 파트너십
2. 재무 현황: 매출, 영업이익, 수익성 추이 및 전망
3. 제품·기술 경쟁력: 주력 배터리 제품(LFP, NCM 등), 기술 차별화 포인트
4. 주요 고객·시장: 핵심 고객사, 지역별 포지셔닝
5. 리스크 요인: 주요 위협 및 약점

[출력 지침]
- 긍정적 근거와 부정적 근거를 모두 균형 있게 서술하세요.
- 수치 데이터는 출처와 함께 명시하세요.
- 각 항목을 명확한 소제목으로 구분하세요.
"""


def catl_strategy_node(state: GraphState) -> GraphState:
    """
    T3 CATL Strategy 노드.

    1. RAG(내부 문서) 검색
    2. 부족 판정 → Tavily Fallback
    3. LLM으로 CATL 전략 분석 합성
    4. state["catl_strategy"], state["catl_agent"] 기록
    5. Supervisor에 T4 진행 신호
    """
    logger.info("[T3] catl_strategy_node 시작")

    retriever = _rag.get_retriever()

    # ── 1. RAG 검색 ──────────────────────────────────────
    rag_docs: list = []
    for query in _RAG_QUERIES:
        try:
            docs = retriever.invoke(query)
            rag_docs.extend(docs)
        except Exception as exc:
            logger.warning("[T3] RAG 검색 실패 (query=%s): %s", query, exc)

    # 중복 청크 제거
    seen: set[str] = set()
    unique_rag_docs: list = []
    for d in rag_docs:
        key = getattr(d, "page_content", "")[:100]
        if key not in seen:
            seen.add(key)
            unique_rag_docs.append(d)

    # ── 2. 부족 판정 → Tavily Fallback ───────────────────
    sufficient, reason = is_sufficient(unique_rag_docs, "catl")
    fallback_used = False
    web_results: list[dict] = []

    if not sufficient:
        logger.info("[T3] RAG 부족(%s) → Tavily fallback 사용", reason)
        fallback_used = True
        web_tool = get_web_search_tool()
        if web_tool:
            for query in _TAVILY_QUERIES:
                try:
                    results = web_tool.invoke(query)
                    if isinstance(results, list):
                        web_results.extend(results)
                except Exception as exc:
                    logger.warning("[T3] Tavily 검색 실패 (query=%s): %s", query, exc)
        else:
            logger.warning("[T3] Tavily 툴 미초기화 — fallback 불가")

    # ── 3. 컨텍스트 구성 ─────────────────────────────────
    rag_context = docs_to_context(unique_rag_docs)

    web_context = ""
    if web_results:
        parts = [
            f"[Web {i + 1}] {r.get('url', 'unknown')}\n{str(r.get('content', ''))[:600]}"
            for i, r in enumerate(web_results[:6])
        ]
        web_context = "\n\n".join(parts)

    context = f"=== 내부 문서(RAG) ===\n{rag_context}"
    if web_context:
        context += f"\n\n=== 웹 검색 결과(Tavily) ===\n{web_context}"

    # ── 4. LLM 합성 ──────────────────────────────────────
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "아래 자료를 바탕으로 CATL 전략을 분석하세요.\n\n"
                f"{context}"
            ),
        },
    ]

    try:
        response = llm.invoke(messages)
        analysis_text: str = response.content
    except Exception as exc:
        logger.error("[T3] LLM 호출 실패: %s", exc)
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
    state["catl_agent"] = {
        **state.get("catl_agent", {}),
        "query": _RAG_QUERIES,
        "retrieved_docs": [
            {"page_content": getattr(d, "page_content", ""), "metadata": getattr(d, "metadata", {})}
            for d in unique_rag_docs
        ],
        "fallback_used": fallback_used,
        "output": {"raw": analysis_text},
    }

    state["catl_strategy"] = {
        "content": analysis_text,
        "fallback_used": fallback_used,
        "rag_doc_count": len(unique_rag_docs),
        "web_result_count": len(web_results),
    }

    state["references"] = list(state.get("references") or []) + references

    # ── 7. Supervisor 진행 신호 (T3 → T4) ────────────────
    supervisor = dict(state.get("supervisor") or {})
    supervisor["current_task"] = "T4"
    state["supervisor"] = supervisor
    state["current_task"] = "T4"

    logger.info(
        "[T3] 완료 — fallback=%s, rag_docs=%d, web=%d",
        fallback_used,
        len(unique_rag_docs),
        len(web_results),
    )
    return state
