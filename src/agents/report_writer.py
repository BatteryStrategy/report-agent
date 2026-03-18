"""
Report Writer Agent (T7).

역할: 전 단계 산출물을 종합해 Markdown 형식의 최종 보고서 생성
출력: state["final_report"] (Markdown 문자열)

필수 섹션 (순서 고정):
  1. Executive Summary        — 결과 요약 (A4 1/2 분량 이내)
  2. 시장 배경
  3. LGES 분석
  4. CATL 분석
  5. 비교 프레임 결과
  6. SWOT
  7. 전략 시사점 및 결론
  8. References

출처 표기 방식:
  - 본문: [1], [2] 각주 번호
  - References 섹션: 번호별 출처 목록
  - 로컬 작업값은 state["report_agent"]에만 기록
"""

from __future__ import annotations

import json
import logging
import os

from langchain_openai import ChatOpenAI

from src.core.state import GraphState

logger = logging.getLogger(__name__)

REQUIRED_SECTIONS = [
    "Executive Summary",
    "시장 배경",
    "LGES 분석",
    "CATL 분석",
    "비교 프레임 결과",
    "SWOT",
    "전략 시사점 및 결론",
    "References",
]

_SYSTEM_PROMPT = """당신은 배터리 산업 전문 보고서 작성 애널리스트입니다.
제공된 분석 자료를 바탕으로 전문 보고서를 Markdown 형식으로 작성하세요.

[필수 섹션 — 반드시 아래 순서대로, 모두 포함]
1. ## Executive Summary
   - A4 용지 반 페이지 분량(약 200~300자) 이내
   - 목차·개요가 아니라 핵심 결과와 시사점 요약
2. ## 시장 배경
3. ## LGES 분석
4. ## CATL 분석
5. ## 비교 프레임 결과
6. ## SWOT
   - LGES·CATL 각각 S/W/O/T 표 형식으로 정리
7. ## 전략 시사점 및 결론
8. ## References
   - 본문에서 인용한 번호 순서대로 목록 정리

[출처 표기 규칙 — 반드시 준수]
- 본문의 수치·주장 뒤에는 [1], [2] 형식의 각주 번호를 붙이세요.
- (출처: ...) 형식, [문서명] 형식, Web 1 형식은 절대 사용하지 마세요.
- 각주 번호는 아래 제공된 "출처 번호 목록"의 번호를 사용하세요.
- References 섹션에는 본문에서 실제 인용한 번호만 목록으로 작성하세요.

[기타 작성 지침]
- LGES와 CATL 서술 분량 균형 유지
- 근거 없는 주장·수치 생성 금지
"""


def _build_numbered_refs(references: list) -> tuple[str, list[dict]]:
    """
    references 목록을 중복 제거 후 번호 목록으로 변환한다.

    Returns:
        ref_context: LLM에 전달할 "출처 번호 목록" 문자열
        numbered:    [{no, source, label}, ...] — References 섹션 생성용
    """
    seen: set[str] = set()
    numbered: list[dict] = []

    for ref in references:
        source = ref.get("source", "unknown")
        if source in seen:
            continue
        seen.add(source)
        label = os.path.basename(source) if source.startswith(".") or "/" in source else source
        numbered.append({"no": len(numbered) + 1, "source": source, "label": label})

    ref_context = "\n".join(
        f"[{r['no']}] {r['label']} ({r['source']})"
        for r in numbered[:25]
    )
    return ref_context, numbered


def _build_context(state: GraphState) -> tuple[str, list[dict]]:
    """보고서 작성에 필요한 컨텍스트 문자열과 번호 참조 목록을 반환한다."""
    market: dict = state.get("market_background") or {}
    lges: dict = state.get("lges_strategy") or {}
    catl: dict = state.get("catl_strategy") or {}
    comparison: dict = state.get("comparison_result") or {}
    swot: dict = state.get("swot_result") or {}
    references: list = state.get("references") or []

    ref_context, numbered_refs = _build_numbered_refs(references)
    axes_text = json.dumps(comparison.get("axes", []), ensure_ascii=False, indent=2)
    swot_text = json.dumps(swot, ensure_ascii=False, indent=2)

    context = (
        f"=== 출처 번호 목록 (본문에서 이 번호를 사용하세요) ===\n{ref_context}\n\n"
        f"=== 시장 배경 ===\n{market.get('content', '(없음)')[:1500]}\n\n"
        f"=== LGES 분석 ===\n{lges.get('content', '(없음)')[:3000]}\n\n"
        f"=== CATL 분석 ===\n{catl.get('content', '(없음)')[:3000]}\n\n"
        f"=== 비교 프레임 (6축) ===\n{axes_text[:3000]}\n\n"
        f"=== 비교 전체 요약 ===\n{comparison.get('overall_summary', '(없음)')}\n\n"
        f"=== SWOT ===\n{swot_text[:2000]}"
    )
    return context, numbered_refs


def report_writer_node(state: GraphState) -> GraphState:
    """
    T7 Report Writer 노드.

    실행 흐름:
      1. references를 번호 목록으로 정리 후 LLM 컨텍스트에 포함
      2. LLM이 본문에 [N] 각주 번호 사용, References 섹션에 목록 작성
      3. state["final_report"] 기록
      4. 로컬 작업값은 state["report_agent"]에만 기록
      5. Supervisor에 T8(reflection) 진행 신호
    """
    logger.info("[T7] report_writer_node 시작")

    context, numbered_refs = _build_context(state)

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    topic: str = state.get("report_topic") or "LGES·CATL 배터리 전략 비교"
    try:
        response = llm.invoke([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"보고서 주제: {topic}\n"
                    "위 주제로 LGES·CATL 배터리 전략 비교 보고서를 작성하세요. "
                    "보고서 제목(# 헤더)도 주제를 반영해 작성하세요.\n\n"
                    f"{context}"
                ),
            },
        ])
        report_text: str = response.content
        logger.info("[T7] 보고서 생성 완료 — 길이: %d자", len(report_text))
    except Exception as exc:
        logger.error("[T7] LLM 호출 실패: %s", exc)
        report_text = f"[보고서 생성 오류]\n\n{exc}\n\n컨텍스트 원문:\n{context[:2000]}"

    # ── 상태 기록 ─────────────────────────────────────────
    state["report_agent"] = {
        **state.get("report_agent", {}),
        "draft": report_text,
        "numbered_refs": numbered_refs,
        "output": {
            "char_count": len(report_text),
            "sections_present": [s for s in REQUIRED_SECTIONS if s in report_text],
            "ref_count": len(numbered_refs),
        },
    }

    state["final_report"] = report_text

    # ── Supervisor 진행 신호 (T7 → T8) ───────────────────
    supervisor = dict(state.get("supervisor") or {})
    supervisor["current_task"] = "T8"
    state["supervisor"] = supervisor
    state["current_task"] = "T8"

    logger.info("[T7] 완료 → T8 reflection")
    return state
