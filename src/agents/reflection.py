"""
Reflection Agent (T8).

역할: 최종 보고서(final_report) 품질 점검 후 COMPLETED / REVISE 판정
출력:
  - state["validation_result"] 갱신  (status: PASS → COMPLETED / REVISE)
  - state["supervisor"]["status"]   COMPLETED 또는 재시도 신호

점검 항목:
  1. 필수 섹션 존재 여부 (8개 섹션 모두 포함)
  2. 섹션별 최소 근거 수 (출처 인라인 표기 "(출처:" 기준, 섹션당 최소 1개)
  3. 기업 간 서술 균형 (LGES·CATL 단락 분량 차이 ±40% 이내)

판정:
  - 통과: supervisor.status = COMPLETED
  - 실패: validation_result.status = REVISE, revision_notes에 구체 사유 기록
          → supervisor가 T7(report_writer)로 되돌아가 재생성

재시도 규칙:
  - REVISE 시 MAX_REFLECTION_RETRIES(=1) 횟수 이내 → T7 재실행
  - 초과 시 COMPLETED 강제 처리 (무한루프 방지)

FAILED 전환 기준:
  - Reflection은 FAILED를 발생시키지 않음
  - T4 Validation에서 Research 재시도가 MAX_RETRIES 초과 시만 FAILED

로컬 작업값: state["reflection_agent"]에만 기록
"""

from __future__ import annotations

import logging
import re

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

MIN_CITATIONS_PER_SECTION: int = 1
BALANCE_TOLERANCE: float = 0.40
MAX_REFLECTION_RETRIES: int = 1


def _check_required_sections(report: str) -> list[str]:
    return [s for s in REQUIRED_SECTIONS if s not in report]


def _check_section_citations(report: str) -> list[str]:
    issues: list[str] = []
    section_pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    headers = list(section_pattern.finditer(report))

    for i, match in enumerate(headers):
        section_name = match.group(1).strip()
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(report)
        section_body = report[start:end]

        # 합성·요약 섹션은 인라인 출처 체크 제외
        if section_name in {"References", "Executive Summary", "전략 시사점 및 결론"}:
            continue

        citation_count = len(re.findall(r"\[\d+\]", section_body))
        if citation_count < MIN_CITATIONS_PER_SECTION:
            issues.append(
                f"섹션 '{section_name}' 출처 표기 부족: {citation_count}개 "
                f"(최소 {MIN_CITATIONS_PER_SECTION}개 필요)"
            )
    return issues


def _check_company_balance(report: str) -> list[str]:
    issues: list[str] = []
    paragraphs = report.split("\n\n")

    lges_chars = sum(
        len(p) for p in paragraphs
        if "LGES" in p or "LG에너지솔루션" in p or "LG Energy" in p
    )
    catl_chars = sum(len(p) for p in paragraphs if "CATL" in p)

    total = lges_chars + catl_chars
    if total == 0:
        return []

    lges_ratio = lges_chars / total
    catl_ratio = catl_chars / total
    threshold = 0.5 + BALANCE_TOLERANCE

    if lges_ratio > threshold:
        issues.append(f"LGES 서술 과다: 전체의 {lges_ratio:.0%} (허용 상한 {threshold:.0%})")
    if catl_ratio > threshold:
        issues.append(f"CATL 서술 과다: 전체의 {catl_ratio:.0%} (허용 상한 {threshold:.0%})")
    return issues


def reflection_node(state: GraphState) -> GraphState:
    """
    T8 Reflection 노드.

    점검 흐름:
      1. 필수 섹션 존재 여부 확인
      2. 섹션별 출처 인라인 표기 수 확인
      3. LGES·CATL 서술 분량 균형 확인
      4. 전체 통과 → supervisor.status = COMPLETED
         실패 → REVISE (재시도 횟수 확인)

    재시도 로직:
      - REVISE: reflection_retry_count < MAX_REFLECTION_RETRIES(=1)
          → current_task = T7 (report_writer 재실행)
      - 초과: COMPLETED 강제 처리 (무한루프 방지)
    """
    logger.info("[T8] reflection_node 시작")

    report: str = state.get("final_report") or ""
    supervisor = dict(state.get("supervisor") or {})

    missing_sections = _check_required_sections(report)
    citation_issues = _check_section_citations(report)
    balance_issues = _check_company_balance(report)
    all_issues = missing_sections + citation_issues + balance_issues

    checks = {
        "missing_sections": missing_sections,
        "citation_issues": citation_issues,
        "balance_issues": balance_issues,
    }

    logger.info(
        "[T8] 점검 결과 — 누락 섹션: %d, 출처 문제: %d, 균형 문제: %d",
        len(missing_sections), len(citation_issues), len(balance_issues),
    )

    if not all_issues:
        supervisor["status"] = "COMPLETED"
        state["status"] = "COMPLETED"
        state["validation_result"] = {
            **state.get("validation_result", {}),
            "status": "PASS",
            "revision_notes": [],
        }
        logger.info("[T8] PASS → COMPLETED")
    else:
        reflection_retry_count: int = supervisor.get("reflection_retry_count", 0)

        if reflection_retry_count >= MAX_REFLECTION_RETRIES:
            # 재시도 상한 초과 → COMPLETED 강제 (무한루프 방지)
            supervisor["status"] = "COMPLETED"
            state["status"] = "COMPLETED"
            state["validation_result"] = {
                **state.get("validation_result", {}),
                "status": "PASS",
                "revision_notes": all_issues,
                "forced_complete": True,
            }
            logger.warning(
                "[T8] 재시도 상한(%d회) 초과 → COMPLETED 강제. 미해결: %s",
                MAX_REFLECTION_RETRIES, all_issues,
            )
        else:
            # REVISE → T7(report_writer) 재실행
            supervisor["reflection_retry_count"] = reflection_retry_count + 1
            supervisor["current_task"] = "T7"
            state["current_task"] = "T7"
            state["validation_result"] = {
                **state.get("validation_result", {}),
                "status": "REVISE",
                "revision_notes": all_issues,
            }
            logger.info(
                "[T8] REVISE → T7 재실행 (retry %d/%d). 사유: %s",
                reflection_retry_count + 1, MAX_REFLECTION_RETRIES, all_issues,
            )

    state["reflection_agent"] = {
        **state.get("reflection_agent", {}),
        "checks": checks,
        "output": {
            "issue_count": len(all_issues),
            "issues": all_issues,
            "final_status": supervisor.get("status", "IN_PROGRESS"),
        },
    }

    state["supervisor"] = supervisor
    logger.info("[T8] 완료 — status=%s", supervisor.get("status"))
    return state
