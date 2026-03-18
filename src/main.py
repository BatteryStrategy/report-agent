import os

from dotenv import load_dotenv

# .env 파일을 가장 먼저 로드한다. (Tavily, OpenAI 등 API 키 필요)
load_dotenv(override=True)  # OS 환경변수보다 .env 파일을 우선 적용

from src.core.bootstrap import ensure_project_dirs
from src.core.tools import get_web_search_tool
from src.graph.workflow import build_graph

# 디렉토리 보장 → 그래프 빌드 순서를 지킨다.
ensure_project_dirs()

# RAG 인스턴스는 각 에이전트에서 namespace 별로 직접 호출한다.
# 예: SingletonRAG.get_instance("lges") / "catl" / "market" / "common"
app_graph = build_graph()

__all__ = ["app_graph", "get_web_search_tool"]


if __name__ == "__main__":
    import json
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("\n" + "="*60)
    print("  report-agent 실행 시작")
    print("="*60 + "\n")

    result = app_graph.invoke({})

    print("\n" + "="*60)
    print("  실행 완료")
    print("="*60)
    print(f"\nstatus     : {result.get('status')}")
    print(f"final_task : {result.get('current_task')}")

    print("\n--- market_background ---")
    mb = result.get("market_background") or {}
    print(mb.get("content", "(없음)")[:500])
    print(f"  fallback_used={mb.get('fallback_used')}, rag_docs={mb.get('rag_doc_count')}, web={mb.get('web_result_count')}")

    print("\n--- lges_strategy ---")
    ls = result.get("lges_strategy") or {}
    print(ls.get("content", "(없음)")[:500])
    print(f"  fallback_used={ls.get('fallback_used')}, rag_docs={ls.get('rag_doc_count')}, web={ls.get('web_result_count')}")

    print("\n--- catl_strategy ---")
    cs = result.get("catl_strategy") or {}
    print(cs.get("content", "(없음)")[:500])
    print(f"  fallback_used={cs.get('fallback_used')}, rag_docs={cs.get('rag_doc_count')}, web={cs.get('web_result_count')}")

    print("\n--- validation_result ---")
    vr = result.get("validation_result") or {}
    print(f"  status : {vr.get('status')}")
    print(f"  notes  : {vr.get('revision_notes')}")
    bm = vr.get("bias_metrics") or {}
    print(f"  bias   : LGES 긍정={bm.get('lges_positive_ratio','?'):.0%} / CATL 긍정={bm.get('catl_positive_ratio','?'):.0%}" if bm else "  bias   : (없음)")

    print("\n--- references (상위 3개) ---")
    for ref in (result.get("references") or [])[:3]:
        print(f"  {ref.get('source')} | {ref.get('snippet','')[:80]}")

    print("\n--- revision_history ---")
    print(result.get("revision_history") or [])