"""
Comparison Agent (T5).

역할: 검증된 LGES·CATL 데이터로 공통 비교 프레임 생성
출력: state["comparison_result"]

비교 축(6개):
  1. 기술/제품 포트폴리오
  2. 원가/수익성
  3. 공급망/원재료
  4. 고객/시장 포지션
  5. 투자/증설/재무 건전성
  6. 리스크/규제/지정학

로컬 작업값: state["comparison_agent"]에만 기록
"""

from __future__ import annotations

import json
import logging
import re

from langchain_openai import ChatOpenAI

from src.core.state import GraphState

logger = logging.getLogger(__name__)

_COMPARISON_SYSTEM_PROMPT = """당신은 배터리 산업 전문 전략 컨설턴트입니다.
LGES(LG에너지솔루션)와 CATL 분석 텍스트를 읽고, 아래 6개 비교 축에 따라 두 회사를 체계적으로 비교하세요.

[비교 축]
1. 기술/제품 포트폴리오
2. 원가/수익성
3. 공급망/원재료
4. 고객/시장 포지션
5. 투자/증설/재무 건전성
6. 리스크/규제/지정학

[출력 형식 — 반드시 JSON만 출력, 설명 금지]
{
  "axes": [
    {
      "axis": "축 이름",
      "lges": {
        "summary": "LGES 핵심 포인트 (2~3문장)",
        "evidence": ["근거 문장 1 (출처: 문서명/URL)", "근거 문장 2 (출처: ...)"]
      },
      "catl": {
        "summary": "CATL 핵심 포인트 (2~3문장)",
        "evidence": ["근거 문장 1 (출처: ...)", "근거 문장 2 (출처: ...)"]
      },
      "key_difference": "두 회사의 핵심 차이점 1문장 요약"
    }
  ],
  "overall_summary": "6축 비교 전체 요약 (3~5문장)"
}

[규칙]
- 반드시 6개 축 모두 포함
- 각 근거에는 (출처: 문서명 또는 URL) 형태로 출처 명시
- 근거 없는 주장 생성 금지 — 자료에 없는 내용은 "자료 없음"으로 기재
- LGES와 CATL 서술 분량이 균형을 이루도록 작성
"""


def _extract_json(text: str) -> dict:
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        logger.warning("[T5] JSON 파싱 실패 — 원문 반환")
        return {}


def comparison_node(state: GraphState) -> GraphState:
    """
    T5 Comparison 노드.

    실행 흐름:
      1. validation(T4) 통과 후 lges_strategy·catl_strategy·market_background 수집
      2. LLM으로 6축 비교 프레임 생성 → state["comparison_result"]
      3. 로컬 작업값은 state["comparison_agent"]에만 기록
      4. Supervisor에 T6(swot) 진행 신호
    """
    logger.info("[T5] comparison_node 시작")

    lges_data: dict = state.get("lges_strategy") or {}
    catl_data: dict = state.get("catl_strategy") or {}
    market_data: dict = state.get("market_background") or {}
    references: list = state.get("references") or []

    lges_text: str = lges_data.get("content", "(LGES 분석 없음)")
    catl_text: str = catl_data.get("content", "(CATL 분석 없음)")
    market_text: str = market_data.get("content", "")

    ref_summary = "\n".join(
        f"- {r.get('source', 'unknown')}: {r.get('snippet', '')[:100]}"
        for r in references[:15]
    )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    user_content = (
        f"=== 시장 배경 ===\n{market_text[:1000]}\n\n"
        f"=== LGES 분석 ===\n{lges_text[:3000]}\n\n"
        f"=== CATL 분석 ===\n{catl_text[:3000]}\n\n"
        f"=== 참조 출처 목록 ===\n{ref_summary}"
    )

    comparison_raw: dict = {}
    try:
        response = llm.invoke([
            {"role": "system", "content": _COMPARISON_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ])
        comparison_raw = _extract_json(response.content)
        if not comparison_raw:
            comparison_raw = {"raw_text": response.content}
        logger.info("[T5] 비교 프레임 생성 완료 — 축 수: %d", len(comparison_raw.get("axes", [])))
    except Exception as exc:
        logger.error("[T5] LLM 호출 실패: %s", exc)
        comparison_raw = {"error": str(exc), "axes": []}

    # ── 상태 기록 ─────────────────────────────────────────
    state["comparison_agent"] = {
        **state.get("comparison_agent", {}),
        "normalized_frame": comparison_raw,
        "output": {"comparison_axes_count": len(comparison_raw.get("axes", []))},
    }

    state["comparison_result"] = {
        "axes": comparison_raw.get("axes", []),
        "overall_summary": comparison_raw.get("overall_summary", ""),
        "raw_text": comparison_raw.get("raw_text", ""),
    }

    # ── Supervisor 진행 신호 (T5 → T6) ────────────────────
    supervisor = dict(state.get("supervisor") or {})
    supervisor["current_task"] = "T6"
    state["supervisor"] = supervisor
    state["current_task"] = "T6"

    logger.info("[T5] 완료 → T6 swot")
    return state
