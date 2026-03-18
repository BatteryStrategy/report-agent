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
    from datetime import datetime
    from pathlib import Path
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("\n" + "="*60)
    print("  report-agent 실행 시작")
    print("="*60 + "\n")

    result = app_graph.invoke({
        "report_topic": "전기차 캐즘 여파 속 LGES·CATL 포트폴리오 다각화 전략 비교",
    })

    print("\n" + "="*60)
    print("  실행 완료")
    print("="*60)
    print(f"\nstatus     : {result.get('status')}")
    print(f"final_task : {result.get('current_task')}")

    # ── 최종 보고서 파일 저장 ──────────────────────────────
    final_report: str = result.get("final_report") or ""
    if final_report:
        import markdown
        from weasyprint import HTML

        report_dir = Path(__file__).parent.parent / "output" / "report"
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Markdown 저장
        md_path = report_dir / f"battery_strategy_report_{timestamp}.md"
        md_path.write_text(final_report, encoding="utf-8")
        print(f"\n📄 Markdown 저장: {md_path}")

        # PDF 저장
        body_html = markdown.markdown(
            final_report,
            extensions=["tables", "fenced_code", "nl2br"],
        )
        full_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR&display=swap');
  body {{ font-family: 'Noto Sans KR', sans-serif; font-size: 11pt;
         margin: 2.5cm 2cm; color: #1a1a1a; line-height: 1.7; }}
  h1 {{ font-size: 18pt; border-bottom: 2px solid #333; padding-bottom: 6px; }}
  h2 {{ font-size: 14pt; border-left: 4px solid #4a90d9; padding-left: 8px; margin-top: 24px; }}
  h3 {{ font-size: 12pt; color: #333; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10pt; }}
  th {{ background: #4a90d9; color: #fff; padding: 6px 10px; }}
  td {{ border: 1px solid #ccc; padding: 5px 10px; }}
  tr:nth-child(even) td {{ background: #f5f8fc; }}
  code {{ background: #f0f0f0; padding: 1px 4px; border-radius: 3px; font-size: 10pt; }}
  pre  {{ background: #f0f0f0; padding: 10px; border-radius: 4px; overflow-x: auto; }}
  blockquote {{ border-left: 3px solid #aaa; margin: 0; padding-left: 12px; color: #555; }}
</style>
</head>
<body>{body_html}</body>
</html>"""

        pdf_path = report_dir / f"battery_strategy_report_{timestamp}.pdf"
        HTML(string=full_html).write_pdf(str(pdf_path))
        print(f"📄 PDF 저장: {pdf_path}")
    else:
        print("\n⚠️  final_report 없음 — 파일 저장 생략")

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