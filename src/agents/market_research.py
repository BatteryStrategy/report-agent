"""
Market Research Agent (T1).

역할: 전기차 캐즘, ESS 동향, 배터리 시장 배경 수집
출력: state["market_background"]
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

# data/raw/market/ 의 PDF를 사용한다.
_rag = SingletonRAG.get_instance("market")
_rag.__init__()  # Singleton 최초 1회 초기화 (이미 됐으면 no-op)

# ─────────────────────────────────────────────
# 검색 쿼리 목록
# ─────────────────────────────────────────────
_RAG_QUERIES = [
    "전기차 시장 캐즘 현황 원인",
    "ESS 에너지저장장치 시장 동향 성장",
    "배터리 글로벌 시장 전망",
]

_TAVILY_QUERIES = [
    "전기차 캐즘 2024 2025 시장 현황",
    "ESS 에너지저장장치 성장 전망 2025",
    "글로벌 배터리 시장 규모 동향",
]

# ─────────────────────────────────────────────
# LLM 프롬프트
# ─────────────────────────────────────────────
_SYSTEM_PROMPT = """당신은 배터리·에너지 산업 전문 리서치 애널리스트입니다.
제공된 내부 문서와 웹 검색 자료를 종합하여 아래 항목을 분석하세요.

[분석 항목]
1. 전기차(EV) 시장 캐즘: 현황, 원인, 지속 여부 전망
2. ESS(에너지저장장치) 시장: 성장 배경, 주요 지역·용도, 전망
3. 글로벌 배터리 산업 배경: 공급망, 기술 경쟁, 정책 환경

[출력 지침]
- 수치·주장 뒤에 반드시 (출처: 파일명 또는 URL) 형식으로 인라인 출처를 명시하세요. [1], Web 1 같은 번호 형식은 사용하지 마세요.
- 전체 3~5문단, 각 문단은 분석 항목 하나를 다루세요.
- 불확실한 정보는 "~로 알려졌다", "~추정된다" 등으로 표현하세요.
"""


def market_research_node(state: GraphState) -> GraphState:
    """
    T1 Market Research 노드.

    1. RAG(내부 문서) 검색
    2. 부족 판정 → Tavily Fallback
    3. LLM으로 시장 배경 합성
    4. state["market_background"], state["market_agent"] 기록
    5. Supervisor에 T2 진행 신호
    """
    logger.info("[T1] market_research_node 시작")

    retriever = _rag.get_retriever()

    # ── 1. RAG 검색 ──────────────────────────────────────
    rag_docs: list = []
    for query in _RAG_QUERIES:
        try:
            docs = retriever.invoke(query)
            rag_docs.extend(docs)
        except Exception as exc:
            logger.warning("[T1] RAG 검색 실패 (query=%s): %s", query, exc)

    # 중복 청크 제거 (page_content 앞 100자 기준)
    seen: set[str] = set()
    unique_rag_docs: list = []
    for d in rag_docs:
        key = getattr(d, "page_content", "")[:100]
        if key not in seen:
            seen.add(key)
            unique_rag_docs.append(d)

    # ── 2. 부족 판정 → Tavily Fallback ───────────────────
    sufficient, reason = is_sufficient(unique_rag_docs, "market")
    fallback_used = False
    web_results: list[dict] = []

    if not sufficient:
        logger.info("[T1] RAG 부족(%s) → Tavily fallback 사용", reason)
        fallback_used = True
        web_tool = get_web_search_tool()
        if web_tool:
            for query in _TAVILY_QUERIES:
                try:
                    results = web_tool.invoke(query)
                    if isinstance(results, list):
                        web_results.extend(results)
                except Exception as exc:
                    logger.warning("[T1] Tavily 검색 실패 (query=%s): %s", query, exc)
        else:
            logger.warning("[T1] Tavily 툴 미초기화 — fallback 불가")

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
    topic_prefix = f"[보고서 주제: {topic}]\n이 주제에 맞게 시장 배경을 분석하세요.\n\n" if topic else ""

    try:
        response = llm.invoke([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": topic_prefix + "아래 자료를 바탕으로 배터리·전기차·ESS 시장 배경을 분석하세요.\n\n" + context},
        ])
        analysis_text: str = response.content
    except Exception as exc:
        logger.error("[T1] LLM 호출 실패: %s", exc)
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
    # 에이전트 로컬 네임스페이스
    state["market_agent"] = {
        **state.get("market_agent", {}),
        "query": _RAG_QUERIES,
        "retrieved_docs": [
            {"page_content": getattr(d, "page_content", ""), "metadata": getattr(d, "metadata", {})}
            for d in unique_rag_docs
        ],
        "fallback_used": fallback_used,
        "output": {"raw": analysis_text},
    }

    # 파이프라인 공유 출력
    state["market_background"] = {
        "content": analysis_text,
        "fallback_used": fallback_used,
        "rag_doc_count": len(unique_rag_docs),
        "web_result_count": len(web_results),
    }

    # references 누적
    state["references"] = list(state.get("references") or []) + references

    # ── 7. Supervisor 진행 신호 (T1 → T2) ────────────────
    supervisor = dict(state.get("supervisor") or {})
    supervisor["current_task"] = "T2"
    state["supervisor"] = supervisor
    state["current_task"] = "T2"  # 하위 호환

    logger.info(
        "[T1] 완료 — fallback=%s, rag_docs=%d, web=%d",
        fallback_used,
        len(unique_rag_docs),
        len(web_results),
    )
    return state
