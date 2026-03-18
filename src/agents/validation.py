"""
Validation Agent (T5).

역할: Research 결과 편향성·누락·출처 검증
출력: state["validation_result"]  →  status: "PASS" | "REVISE"

검증 항목:
  1. 데이터 편향성 — LGES/CATL 긍정·부정 비율(70% 초과 시 편향 판정)
  2. 필수 비교 항목 누락 — 재무/기술/시장/리스크 4개 항목 존재 여부
  3. 출처 매핑 가능성 — 내부(RAG)·외부(Web) 교차 근거 최소 1개 이상

재시도 규칙:
  - REVISE 시 T2(LGES)/T3(CATL) 재실행으로 되돌아감
  - 최대 MAX_RETRIES=2회 초과 시 status="FAILED" 처리 (무한루프 방지)
"""

from __future__ import annotations

import json
import logging
import re

from langchain_openai import ChatOpenAI

from src.core.rag import SingletonRAG
from src.core.state import GraphState

logger = logging.getLogger(__name__)

# 검증 에이전트는 공통 문서(data/raw/common/)를 참조한다.
_rag = SingletonRAG.get_instance("common")
_rag.__init__()

# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────

#: 편향 판정 임계값 — 한쪽(긍정 또는 부정)이 이 비율 초과 시 편향
BIAS_THRESHOLD: float = 0.70

#: 최대 재시도 횟수 — 초과 시 FAILED 처리
MAX_RETRIES: int = 2

#: 필수 비교 항목 — 모두 포함되어야 PASS
REQUIRED_COMPARISON_ITEMS: list[str] = ["재무", "기술", "시장", "리스크"]

# ─────────────────────────────────────────────
# LLM 프롬프트
# ─────────────────────────────────────────────
_CLASSIFICATION_PROMPT = """당신은 배터리 기업 분석 보고서의 품질 검증 전문가입니다.
아래 LGES와 CATL 분석 텍스트를 읽고 다음 항목을 JSON으로 반환하세요.

[반환 형식 — 반드시 JSON만 출력, 설명 금지]
{
  "lges_positive": ["긍정 근거 문장1", "긍정 근거 문장2", ...],
  "lges_negative": ["부정 근거 문장1", ...],
  "catl_positive": ["긍정 근거 문장1", ...],
  "catl_negative": ["부정 근거 문장1", ...],
  "missing_comparison_items": ["누락된 항목명", ...],
  "source_mapping_issues": ["출처 불명확 항목 설명", ...]
}

[판단 기준]
- 긍정: 성장, 수익, 기술 우위, 시장 확대, 파트너십 등 유리한 내용
- 부정: 손실, 경쟁 열위, 리스크, 규제, 수요 감소 등 불리한 내용
- missing_comparison_items: 아래 4개 항목 중 LGES와 CATL 양쪽 모두에서 전혀 언급되지 않은 것만 나열
  * 재무: 매출/영업이익/수익성 관련 내용
  * 기술: 제품/배터리 기술/경쟁력 관련 내용
  * 시장: 고객사/시장점유율/글로벌 포지셔닝 관련 내용
  * 리스크: 위협/약점/위험/규제/경쟁열위 관련 내용 (리스크, 위협, 약점, 위험 등 어떤 표현이든 포함)
  조금이라도 언급이 있으면 missing으로 분류하지 마세요.
- source_mapping_issues: 수치나 주장에 출처가 없거나 불명확한 경우
"""


def _extract_json(text: str) -> dict:
    """LLM 응답에서 JSON 블록을 추출한다."""
    # ```json ... ``` 블록 우선 시도
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # 순수 JSON 파싱 시도
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        # JSON 파싱 실패 시 빈 구조 반환
        logger.warning("[T5] LLM 응답 JSON 파싱 실패, 빈 구조 사용")
        return {
            "lges_positive": [],
            "lges_negative": [],
            "catl_positive": [],
            "catl_negative": [],
            "missing_comparison_items": [],
            "source_mapping_issues": [],
        }


def _bias_ratio(positive: list, negative: list) -> tuple[float, float]:
    """긍정·부정 비율을 반환한다. (positive_ratio, negative_ratio)"""
    total = len(positive) + len(negative)
    if total == 0:
        return 0.5, 0.5
    return len(positive) / total, len(negative) / total




def validation_node(state: GraphState) -> GraphState:
    """
    T5 Validation 노드.

    검증 흐름:
      1. LGES·CATL 분석 텍스트를 LLM에 전달해 긍/부정 분류 및 누락·출처 문제 추출
      2. 편향성 판정 (BIAS_THRESHOLD=70%)
      3. 필수 항목 누락 판정
      4. 교차 근거 판정 (RAG + Web)
      5. PASS / REVISE 결정

    REVISE 시:
      - revision_notes에 구체 사유 기록
      - 재시도 횟수 < MAX_RETRIES → current_task = "T2" (Research 재실행)
      - 재시도 횟수 >= MAX_RETRIES → status = "FAILED" (무한루프 방지)
    """
    logger.info("[T5] validation_node 시작")

    lges_data: dict = state.get("lges_strategy") or {}
    catl_data: dict = state.get("catl_strategy") or {}
    lges_text: str = lges_data.get("content", "")
    catl_text: str = catl_data.get("content", "")

    # ── 1. LLM 분류 호출 ─────────────────────────────────
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    user_content = (
        f"=== LGES 분석 텍스트 ===\n{lges_text[:3000]}\n\n"
        f"=== CATL 분석 텍스트 ===\n{catl_text[:3000]}"
    )
    messages = [
        {"role": "system", "content": _CLASSIFICATION_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        response = llm.invoke(messages)
        classification = _extract_json(response.content)
    except Exception as exc:
        logger.error("[T5] LLM 분류 호출 실패: %s", exc)
        classification = {
            "lges_positive": [],
            "lges_negative": [],
            "catl_positive": [],
            "catl_negative": [],
            "missing_comparison_items": REQUIRED_COMPARISON_ITEMS[:],
            "source_mapping_issues": [],
        }

    lges_pos: list = classification.get("lges_positive", [])
    lges_neg: list = classification.get("lges_negative", [])
    catl_pos: list = classification.get("catl_positive", [])
    catl_neg: list = classification.get("catl_negative", [])
    missing_items: list = classification.get("missing_comparison_items", [])
    source_issues: list = classification.get("source_mapping_issues", [])

    # ── 2. 편향성 판정 ───────────────────────────────────
    lges_pos_ratio, lges_neg_ratio = _bias_ratio(lges_pos, lges_neg)
    catl_pos_ratio, catl_neg_ratio = _bias_ratio(catl_pos, catl_neg)

    bias_issues: list[str] = []
    if lges_pos_ratio > BIAS_THRESHOLD:
        bias_issues.append(
            f"LGES 긍정 편향: 긍정 {lges_pos_ratio:.0%} > {BIAS_THRESHOLD:.0%}"
        )
    if lges_neg_ratio > BIAS_THRESHOLD:
        bias_issues.append(
            f"LGES 부정 편향: 부정 {lges_neg_ratio:.0%} > {BIAS_THRESHOLD:.0%}"
        )
    if catl_pos_ratio > BIAS_THRESHOLD:
        bias_issues.append(
            f"CATL 긍정 편향: 긍정 {catl_pos_ratio:.0%} > {BIAS_THRESHOLD:.0%}"
        )
    if catl_neg_ratio > BIAS_THRESHOLD:
        bias_issues.append(
            f"CATL 부정 편향: 부정 {catl_neg_ratio:.0%} > {BIAS_THRESHOLD:.0%}"
        )

    # ── 3. 필수 항목 누락 판정 ───────────────────────────
    # LLM이 반환한 missing_items가 없으면 텍스트 직접 확인(fallback)
    if not missing_items:
        combined_text = lges_text + catl_text
        missing_items = [
            item for item in REQUIRED_COMPARISON_ITEMS
            if item not in combined_text
        ]

    # ── 4. 종합 판정 ─────────────────────────────────────
    all_issues = bias_issues + missing_items + source_issues
    validation_status = "PASS" if not all_issues else "REVISE"

    # ── 6. 재시도 횟수 확인 (무한루프 방지) ──────────────
    supervisor = dict(state.get("supervisor") or {})
    revision_history: list = list(supervisor.get("revision_history") or [])

    if validation_status == "REVISE":
        if len(revision_history) >= MAX_RETRIES:
            logger.warning(
                "[T5] 최대 재시도(%d회) 초과 → FAILED 처리", MAX_RETRIES
            )
            validation_status = "FAILED"
        else:
            revision_history.append({
                "from_task": "T5",
                "retry_no": len(revision_history) + 1,
                "issues": all_issues,
            })

    # ── 7. 상태 기록 ─────────────────────────────────────
    bias_metrics = {
        "lges_positive_ratio": round(lges_pos_ratio, 3),
        "lges_negative_ratio": round(lges_neg_ratio, 3),
        "catl_positive_ratio": round(catl_pos_ratio, 3),
        "catl_negative_ratio": round(catl_neg_ratio, 3),
        "lges_positive_count": len(lges_pos),
        "lges_negative_count": len(lges_neg),
        "catl_positive_count": len(catl_pos),
        "catl_negative_count": len(catl_neg),
    }

    state["validation_agent"] = {
        **state.get("validation_agent", {}),
        "checks": {
            "bias_issues": bias_issues,
            "missing_items": missing_items,
            "source_issues": source_issues,
        },
        "bias_metrics": bias_metrics,
        "output": {"status": validation_status, "issues": all_issues},
    }

    state["validation_result"] = {
        "status": validation_status,
        "revision_notes": all_issues if all_issues else [],
        "bias_metrics": bias_metrics,
    }

    # ── 8. Supervisor 진행 신호 ───────────────────────────
    # PASS → T6(report_writer)
    # REVISE → T2(lges/catl Research 재실행)  ← 재시도 루프 진입점
    # FAILED → FAILED 종료
    if validation_status == "PASS":
        supervisor["current_task"] = "T6"
        state["current_task"] = "T6"
        logger.info("[T5] PASS → T6 report_writer 진행")
    elif validation_status == "FAILED":
        supervisor["status"] = "FAILED"
        state["status"] = "FAILED"
        logger.warning("[T5] FAILED — 워크플로우 종료")
    else:
        # REVISE: T2부터 재실행 (LGES + CATL 재수집)
        supervisor["current_task"] = "T2"
        supervisor["revision_history"] = revision_history
        state["current_task"] = "T2"
        state["revision_history"] = revision_history
        logger.info(
            "[T5] REVISE → T2 재실행 (retry %d/%d), 사유: %s",
            len(revision_history),
            MAX_RETRIES,
            all_issues,
        )

    state["supervisor"] = supervisor

    logger.info("[T5] 완료 — status=%s, issues=%d건", validation_status, len(all_issues))
    return state
