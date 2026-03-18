"""
SWOT Agent (T6).

역할: comparison_result 기반으로 LGES·CATL SWOT 구조화
입력: state["comparison_result"]
출력: state["swot_result"]

규칙:
  - 각 항목(S/W/O/T)에 근거 source_id 포함
  - 비교 결과에 없는 내용 생성 금지
  - S/W는 내부 요인, O/T는 외부 요인

로컬 작업값: state["comparison_agent"]에 추가 기록
"""

from __future__ import annotations

import json
import logging
import re

from langchain_openai import ChatOpenAI

from src.core.state import GraphState

logger = logging.getLogger(__name__)

_SWOT_SYSTEM_PROMPT = """당신은 배터리 산업 전문 전략 컨설턴트입니다.
아래 6축 비교 결과를 바탕으로 LGES와 CATL 각각의 SWOT을 구조화하세요.

[출력 형식 — 반드시 JSON만 출력, 설명 금지]
{
  "lges": {
    "strengths":     [{"point": "강점 내용", "source": "출처 문서명/URL"}],
    "weaknesses":    [{"point": "약점 내용", "source": "출처 문서명/URL"}],
    "opportunities": [{"point": "기회 내용", "source": "출처 문서명/URL"}],
    "threats":       [{"point": "위협 내용", "source": "출처 문서명/URL"}]
  },
  "catl": {
    "strengths":     [{"point": "강점 내용", "source": "출처 문서명/URL"}],
    "weaknesses":    [{"point": "약점 내용", "source": "출처 문서명/URL"}],
    "opportunities": [{"point": "기회 내용", "source": "출처 문서명/URL"}],
    "threats":       [{"point": "위협 내용", "source": "출처 문서명/URL"}]
  }
}

[규칙]
- 각 항목(S/W/O/T)마다 최소 2개 이상 기재
- 반드시 source 필드에 근거 출처 명시
- 비교 결과에 없는 내용은 추가 생성 금지
- S/W는 내부 요인, O/T는 외부 요인 기준으로 분류
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
        logger.warning("[T6] JSON 파싱 실패 — 원문 반환")
        return {}


def swot_node(state: GraphState) -> GraphState:
    """
    T6 SWOT 노드.

    실행 흐름:
      1. comparison_result(T5 산출물) 수집
      2. LLM으로 LGES·CATL SWOT 생성 → state["swot_result"]
      3. Supervisor에 T7(report_writer) 진행 신호
    """
    logger.info("[T6] swot_node 시작")

    comparison: dict = state.get("comparison_result") or {}
    axes_text = json.dumps(comparison.get("axes", []), ensure_ascii=False, indent=2)
    overall_summary = comparison.get("overall_summary", "")

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    swot_raw: dict = {}
    try:
        response = llm.invoke([
            {"role": "system", "content": _SWOT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"=== 6축 비교 결과 ===\n{axes_text[:4000]}\n\n"
                    f"=== 전체 요약 ===\n{overall_summary}"
                ),
            },
        ])
        swot_raw = _extract_json(response.content)
        if not swot_raw:
            swot_raw = {"raw_text": response.content}
        logger.info("[T6] SWOT 생성 완료")
    except Exception as exc:
        logger.error("[T6] LLM 호출 실패: %s", exc)
        swot_raw = {"error": str(exc)}

    # ── 상태 기록 ─────────────────────────────────────────
    state["swot_result"] = {
        "lges": swot_raw.get("lges", {}),
        "catl": swot_raw.get("catl", {}),
        "raw_text": swot_raw.get("raw_text", ""),
    }

    # ── Supervisor 진행 신호 (T6 → T7) ────────────────────
    supervisor = dict(state.get("supervisor") or {})
    supervisor["current_task"] = "T7"
    state["supervisor"] = supervisor
    state["current_task"] = "T7"

    logger.info("[T6] 완료 → T7 report_writer")
    return state
