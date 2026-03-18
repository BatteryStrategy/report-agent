"""
LangGraph 워크플로우 빌더.

노드 구성:
  supervisor     — 중앙 라우터 (허브)
  research_phase — [Fan-out] T1: market·lges·catl 병렬 실행
  lges_strategy  — T2: validation REVISE 재시도 진입점
  catl_strategy  — T3: T2 직후 순차 실행
  validation     — T4: Research 결과 편향·누락·출처 검증
  comparison     — T5: 검증된 데이터로 6축 비교 프레임 생성
  swot           — T6: comparison_result 기반 SWOT 생성
  report_writer  — T7: 8개 필수 섹션 Markdown 보고서 생성
  reflection     — T8: 보고서 품질 점검

실행 흐름:
  START
    → supervisor (초기화)
    → research_phase (T1: market·lges·catl 병렬)
    → supervisor → validation (T4)
        ├─ PASS   → comparison (T5) → swot (T6) → report_writer (T7) → reflection (T8)
        └─ REVISE → lges_strategy (T2) → catl_strategy (T3) → validation (T4)  ← 최대 2회
        └─ FAILED → END

  reflection (T8)
    ├─ PASS   → COMPLETED → END
    └─ REVISE → report_writer (T7) ← 최대 1회
    └─ 초과   → COMPLETED 강제 → END

무한루프 방지:
  - validation.MAX_RETRIES = 2 (초과 시 FAILED)
  - reflection.MAX_REFLECTION_RETRIES = 1 (초과 시 COMPLETED 강제)
  - supervisor: status ∈ {FAILED, COMPLETED} → 즉시 END
"""

from __future__ import annotations

import copy
import logging
from concurrent.futures import ThreadPoolExecutor

from langgraph.graph import END, START, StateGraph

from src.agents.catl_strategy import catl_strategy_node
from src.agents.comparison import comparison_node
from src.agents.lges_strategy import lges_strategy_node
from src.agents.market_research import market_research_node
from src.agents.reflection import reflection_node
from src.agents.report_writer import report_writer_node
from src.agents.supervisor import route_from_supervisor, supervisor_node
from src.agents.swot import swot_node
from src.agents.validation import validation_node
from src.core.state import GraphState

logger = logging.getLogger(__name__)


def research_phase_node(state: GraphState) -> GraphState:
    """
    [Fan-out] T1: market·lges·catl Research 노드를 병렬 실행한다.

    병렬 처리 규칙:
    - 각 노드는 state의 deepcopy를 받아 독립 실행 → 상태 충돌 없음
    - 완료 후 공유 출력 필드만 병합:
        market_background, lges_strategy, catl_strategy,
        market_agent, lges_agent, catl_agent, references
    - research_phase 완료 후 supervisor.current_task = T4(validation) 설정
    """
    logger.info("[research_phase] T1 병렬 실행 시작")

    with ThreadPoolExecutor(max_workers=3) as executor:
        f_market = executor.submit(market_research_node, copy.deepcopy(state))
        f_lges = executor.submit(lges_strategy_node, copy.deepcopy(state))
        f_catl = executor.submit(catl_strategy_node, copy.deepcopy(state))

        results: dict[str, GraphState] = {}
        for future, key in [
            (f_market, "market"),
            (f_lges, "lges"),
            (f_catl, "catl"),
        ]:
            try:
                results[key] = future.result(timeout=120)
            except Exception as exc:
                logger.error("[research_phase] %s 노드 실패: %s", key, exc)
                results[key] = {}

    if results.get("market"):
        state["market_background"] = results["market"].get("market_background")
        state["market_agent"] = results["market"].get("market_agent", {})

    if results.get("lges"):
        state["lges_strategy"] = results["lges"].get("lges_strategy")
        state["lges_agent"] = results["lges"].get("lges_agent", {})

    if results.get("catl"):
        state["catl_strategy"] = results["catl"].get("catl_strategy")
        state["catl_agent"] = results["catl"].get("catl_agent", {})

    merged_refs: list = list(state.get("references") or [])
    for key in ("market", "lges", "catl"):
        merged_refs.extend(results.get(key, {}).get("references") or [])
    state["references"] = merged_refs

    # research_phase 완료 → T4(validation)으로 진행
    supervisor = dict(state.get("supervisor") or {})
    supervisor["current_task"] = "T4"
    state["supervisor"] = supervisor
    state["current_task"] = "T4"

    logger.info("[research_phase] 완료 → T4 validation")
    return state


def build_graph():
    """
    Supervisor + Worker 노드를 포함한 StateGraph를 구성한다.
    """
    graph_builder = StateGraph(GraphState)

    # 노드 등록
    graph_builder.add_node("supervisor", supervisor_node)
    graph_builder.add_node("research_phase", research_phase_node)
    graph_builder.add_node("lges_strategy", lges_strategy_node)
    graph_builder.add_node("catl_strategy", catl_strategy_node)
    graph_builder.add_node("validation", validation_node)
    graph_builder.add_node("comparison", comparison_node)
    graph_builder.add_node("swot", swot_node)
    graph_builder.add_node("report_writer", report_writer_node)
    graph_builder.add_node("reflection", reflection_node)

    # 시작 엣지
    graph_builder.add_edge(START, "supervisor")

    # Supervisor 조건부 분기
    graph_builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "research_phase": "research_phase",
            "lges_strategy": "lges_strategy",
            "catl_strategy": "catl_strategy",
            "validation": "validation",
            "comparison": "comparison",
            "swot": "swot",
            "report_writer": "report_writer",
            "reflection": "reflection",
            "END": END,
        },
    )

    # 모든 워커 → supervisor 복귀
    for node in (
        "research_phase",
        "lges_strategy",
        "catl_strategy",
        "validation",
        "comparison",
        "swot",
        "report_writer",
        "reflection",
    ):
        graph_builder.add_edge(node, "supervisor")

    return graph_builder.compile()
