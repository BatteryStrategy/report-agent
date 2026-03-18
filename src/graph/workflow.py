"""
LangGraph 워크플로우 빌더.

노드 구성:
  supervisor          — 중앙 라우터 (허브)
  research_phase      — [Fan-out] T1·T2·T3을 ThreadPoolExecutor로 병렬 실행
  lges_strategy       — REVISE 재시도 진입점 (T2)
  catl_strategy       — REVISE 이후 CATL 재수집 (T3)
  comparison          — T4
  validation          — T5  (PASS → T6 / REVISE → T2 / FAILED → END)
  report_writer       — T6
  reflection          — T7  (품질 점검 후 COMPLETED → END)

Retry / Reflect 루프:
  ┌──────────────────────────────────────────────────────┐
  │  validation (T5)                                     │
  │    REVISE → current_task = T2                        │
  │      → supervisor → lges_strategy → catl_strategy    │
  │      → comparison → validation (재검증)              │
  │    MAX_RETRIES 초과 → status = FAILED → END          │
  │    PASS → report_writer → reflection                 │
  │      reflection 품질 미달 → supervisor.revision_history│
  │      에 기록 후 COMPLETED 처리 (reflection은 1회)    │
  └──────────────────────────────────────────────────────┘

무한루프 방지:
  - validation.MAX_RETRIES = 2 (초과 시 FAILED)
  - supervisor: status = FAILED/COMPLETED 이면 즉시 END 라우팅
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
from src.agents.validation import validation_node
from src.core.state import GraphState

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Fan-out Research Phase 노드
# ─────────────────────────────────────────────────────────────

def research_phase_node(state: GraphState) -> GraphState:
    """
    [Fan-out] T1·T2·T3 Research 노드를 ThreadPoolExecutor로 병렬 실행한다.

    병렬 처리 규칙:
    - 각 노드는 state의 deepcopy를 받아 독립 실행 → 상태 충돌 없음
    - 완료 후 각 노드의 공유 출력 필드만 병합:
        market_background, lges_strategy, catl_strategy,
        market_agent, lges_agent, catl_agent, references
    - 개별 노드가 설정한 supervisor.current_task는 무시하고
      research_phase가 직접 T4로 설정한다 (fan-out 이후 단일 진입점 보장)

    타임아웃: 노드당 120초
    실패 처리: 개별 노드 예외는 로그만 남기고 빈 결과로 대체
    """
    logger.info("[research_phase] T1·T2·T3 병렬 실행 시작")

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

    # ── 공유 출력 필드 병합 ──────────────────────────────
    if results.get("market"):
        state["market_background"] = results["market"].get("market_background")
        state["market_agent"] = results["market"].get("market_agent", {})

    if results.get("lges"):
        state["lges_strategy"] = results["lges"].get("lges_strategy")
        state["lges_agent"] = results["lges"].get("lges_agent", {})

    if results.get("catl"):
        state["catl_strategy"] = results["catl"].get("catl_strategy")
        state["catl_agent"] = results["catl"].get("catl_agent", {})

    # references 통합 (순서: market → lges → catl)
    merged_refs: list = list(state.get("references") or [])
    for key in ("market", "lges", "catl"):
        merged_refs.extend(results.get(key, {}).get("references") or [])
    state["references"] = merged_refs

    # ── Supervisor 진행 신호: research_phase → T4 ────────
    supervisor = dict(state.get("supervisor") or {})
    supervisor["current_task"] = "T4"
    state["supervisor"] = supervisor
    state["current_task"] = "T4"

    logger.info("[research_phase] 완료 → T4 comparison")
    return state


# ─────────────────────────────────────────────────────────────
# 그래프 빌드
# ─────────────────────────────────────────────────────────────

def build_graph():
    """
    Supervisor + Worker 노드를 포함한 StateGraph를 구성한다.

    실행 흐름:
      START
        → supervisor (초기화)
        → research_phase (T1: market·lges·catl 병렬)   ← 최초 실행
        → supervisor → comparison (T4)
        → supervisor → validation (T5)
            ├─ PASS  → report_writer (T6) → reflection (T7) → END
            └─ REVISE → lges_strategy (T2) → catl_strategy (T3)  ← 재시도 루프
                      → comparison (T4) → validation (T5)        ← 최대 2회
                      → FAILED 시 END
    """
    graph_builder = StateGraph(GraphState)

    # 노드 등록
    graph_builder.add_node("supervisor", supervisor_node)
    graph_builder.add_node("research_phase", research_phase_node)   # Fan-out 노드
    graph_builder.add_node("market_research", market_research_node)  # REVISE 시 단독 재실행 가능
    graph_builder.add_node("lges_strategy", lges_strategy_node)     # REVISE 재시도 진입점 (T2)
    graph_builder.add_node("catl_strategy", catl_strategy_node)     # REVISE 이후 (T3)
    graph_builder.add_node("comparison", comparison_node)
    graph_builder.add_node("validation", validation_node)
    graph_builder.add_node("report_writer", report_writer_node)
    graph_builder.add_node("reflection", reflection_node)

    # 시작 엣지
    graph_builder.add_edge(START, "supervisor")

    # Supervisor 조건부 분기
    # route_from_supervisor 반환값 → 노드 매핑
    # T1 → research_phase (fan-out 병렬)
    # T2 → lges_strategy  (REVISE 재시도)
    # T3 → catl_strategy  (REVISE 이후)
    graph_builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "research_phase": "research_phase",
            "market_research": "market_research",
            "lges_strategy": "lges_strategy",
            "catl_strategy": "catl_strategy",
            "comparison": "comparison",
            "validation": "validation",
            "report_writer": "report_writer",
            "reflection": "reflection",
            "END": END,
        },
    )

    # 모든 워커는 실행 후 supervisor로 복귀
    for node in (
        "research_phase",
        "market_research",
        "lges_strategy",
        "catl_strategy",
        "comparison",
        "validation",
        "report_writer",
        "reflection",
    ):
        graph_builder.add_edge(node, "supervisor")

    return graph_builder.compile()
