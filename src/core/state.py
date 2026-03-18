from typing import Any, TypedDict


class SupervisorState(TypedDict, total=False):
    """Supervisor 전용 제어 상태."""

    current_task: str  # 현재 실행 중인 Task ID (T1~T6)
    status: str  # Workflow 상태 (IN_PROGRESS / COMPLETED / FAILED)
    revision_history: list[dict[str, Any]]  # 재실행 이력


class MarketAgentState(TypedDict, total=False):
    """시장 조사 에이전트 로컬 상태."""

    query: str
    prompt: str
    retrieved_docs: list[dict[str, Any]]
    fallback_used: bool
    output: dict[str, Any]


class CompanyAgentState(TypedDict, total=False):
    """기업 분석 에이전트(LGES/CATL) 로컬 상태."""

    query: str
    prompt: str
    retrieved_docs: list[dict[str, Any]]
    fallback_used: bool
    output: dict[str, Any]


class ComparisonAgentState(TypedDict, total=False):
    """비교 에이전트 로컬 상태."""

    prompt: str
    normalized_frame: dict[str, Any]
    output: dict[str, Any]


class ValidationAgentState(TypedDict, total=False):
    """검증 에이전트 로컬 상태."""

    prompt: str
    checks: dict[str, Any]
    bias_metrics: dict[str, Any]
    output: dict[str, Any]


class ReportAgentState(TypedDict, total=False):
    """보고서 작성 에이전트 로컬 상태."""

    prompt: str
    draft: str
    output: dict[str, Any]


class ReflectionAgentState(TypedDict, total=False):
    """품질 점검(Reflection) 에이전트 로컬 상태."""

    prompt: str
    checks: dict[str, Any]
    output: dict[str, Any]
    output: dict[str, Any]


class GraphState(TypedDict, total=False):
    """
    Supervisor + Worker 공용 그래프 상태 스키마.

    원칙:
    - 에이전트 로컬 작업값은 네임스페이스별 *_agent 아래에서만 갱신한다.
    - Supervisor는 supervisor 아래 제어값만 갱신한다.
    - 파이프라인 산출물만 공유 출력 필드에 기록한다.
    """

    # Namespaced local state (오염 방지)
    supervisor: SupervisorState
    market_agent: MarketAgentState
    lges_agent: CompanyAgentState
    catl_agent: CompanyAgentState
    comparison_agent: ComparisonAgentState
    validation_agent: ValidationAgentState
    report_agent: ReportAgentState
    reflection_agent: ReflectionAgentState

    # Shared outputs (파이프라인 산출물)
    market_background: dict[str, Any]  # T1 완료 산출물
    lges_strategy: dict[str, Any]  # T2 완료 산출물
    catl_strategy: dict[str, Any]  # T3 완료 산출물
    comparison_result: dict[str, Any]  # T4 완료 산출물
    swot_result: dict[str, Any]  # T5 완료 산출물
    validation_result: dict[str, Any]  # PASS/REVISE + 사유
    references: list[dict[str, Any]]  # 실제 활용 출처 누적
    final_report: str  # T6 완료 산출물

    # 보고서 주제 (최초 invoke 시 설정)
    report_topic: str

    # Backward compatibility for existing code paths
    current_task: str
    status: str
    revision_history: list[dict[str, Any]]
