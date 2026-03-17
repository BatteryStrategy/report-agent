from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    """Supervisor/Worker가 공유하는 그래프 상태 스키마."""

    current_task: str  # 현재 실행 중인 Task ID (T1~T6)
    market_background: dict[str, Any]  # 시장 배경 분석 결과
    lges_strategy: dict[str, Any]  # LGES 전략/경쟁력/리스크 분석 결과
    catl_strategy: dict[str, Any]  # CATL 전략/경쟁력/리스크 분석 결과
    comparison_result: dict[str, Any]  # 공통 비교 프레임 정렬 결과
    swot_result: dict[str, Any]  # 양사 SWOT 분석 결과
    validation_result: dict[str, Any]  # 검증 판정 (PASS/REVISE) + 사유 목록
    revision_history: list[dict[str, Any]]  # 재실행 이력
    references: list[dict[str, Any]]  # 실제 활용된 출처 목록
    final_report: str  # 최종 보고서 Markdown 텍스트
    status: str  # Workflow 상태 (IN_PROGRESS / COMPLETED / FAILED)
