# 작업 지시서 B

## 역할
- 담당 범위: Comparison + SWOT + Report Writer + Reflection
- 목표: 공통 비교 프레임 정렬, SWOT 도출, 보고서 생성, 리플렉션 재검증 루프 완성
- 제약: 현재 저장소 구조와 Supervisor 라우팅을 유지

## 작업 대상 파일
- src/agents/comparison.py
- src/agents/report_writer.py
- src/agents/supervisor.py
- src/graph/workflow.py
- README.md

## 구현 요구사항

### 1) Comparison Agent 구현
입력:
- state["market_background"]
- state["lges_strategy"]
- state["catl_strategy"]
- state["references"]

출력:
- state["comparison_result"]

공통 비교 프레임(최소):
- 기술/제품 포트폴리오
- 원가/수익성
- 공급망/원재료
- 고객/시장 포지션
- 투자/증설/재무 건전성
- 리스크/규제/지정학

규칙:
- 각 축마다 LGES vs CATL 차이점과 근거 source를 함께 기록
- 비교 에이전트 로컬 값은 state["comparison_agent"]만 사용

### 2) SWOT 분석 구현
- comparison_result 기반으로 양사 SWOT 구조화
- 출력: state["swot_result"]
- 각 항목(S/W/O/T)에 근거 source_id 포함
- 근거 없는 주장 생성 금지

### 3) Report Writer 구현
- 출력: state["final_report"] (Markdown)
- 필수 섹션:
  1. Executive Summary (A4 1/2 넘지 않게, 단수 보고서 목차,개요가 아니라 결과에 대한 요약)
  2. 시장 배경
  3. LGES 분석
  4. CATL 분석
  5. 비교 프레임 결과
  6. SWOT
  7. 전략 시사점 및 결론
  8. References
- 섹션별 출처 매핑 누락 금지

### 4) Reflection 품질 점검 루프 구현
점검 항목:
- 필수 섹션 존재 여부
- 섹션별 최소 근거 수
- 기업 간 서술 균형(분량 및 긍/부정 편차)

판정:
- 통과: validation_result.status = PASS, supervisor.status = COMPLETED
- 실패: validation_result.status = REVISE, revision_notes에 구체 사유 기록

재시도:
- REVISE일 때 supervisor가 이전 노드로 되돌아가 재실행
- 재시도 상한/종료 조건 명시
- 무한 루프 방지

### 5) Supervisor 연동 주석 강화
코드 주석으로 반드시 설명:
- 어떤 조건에서 어떤 노드로 되돌아가는지
- 재시도 횟수 관리 방식
- FAILED 전환 기준

## 문서화(README)
README에 다음을 추가:
- Comparison 프레임 정의와 판단 기준
- SWOT 근거 매핑 규칙
- Reflection 실패 시 Retry/Reflect 루프 동작 개요

## 출력 형식(반드시 준수)
작업 결과를 커밋 단위로 순차 출력:
1. 변경 파일 목록
2. 코드
3. 핵심 설명(5줄 이내)
4. 추천 커밋 메시지 1개

내가 "다음"이라고 입력하면 다음 커밋 단위로 진행.
