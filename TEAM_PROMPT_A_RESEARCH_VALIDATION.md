# 작업 지시서 A

## 역할
- 담당 범위: Research Layer + Validation Layer
- 목표: RAG 우선 검색, 부족 시 Tavily Fallback, 편향/누락/출처 검증까지 구현
- 제약: 현재 저장소 구조를 그대로 사용하고 최소 변경으로 확장

## 작업 대상 파일
- src/agents/market_research.py
- src/agents/lges_strategy.py
- src/agents/catl_strategy.py
- src/agents/validation.py
- src/graph/workflow.py
- src/core/rag.py
- README.md

## 구현 요구사항

### 1) Fan-out 병렬 Research 노드 3개 구현
- market_research_node
  - 목적: 전기차 캐즘, ESS 동향, 시장 배경 수집
  - 출력: state["market_background"]
- lges_prefetch_node 또는 lges_strategy_node 내 prefetch 단계
  - 목적: LGES 전략/재무/제품 기초 근거 수집
  - 출력: state["lges_strategy"] 내부 raw_data 또는 state["lges_raw_data"]
- catl_prefetch_node 또는 catl_strategy_node 내 prefetch 단계
  - 목적: CATL 전략/재무/제품 기초 근거 수집
  - 출력: state["catl_strategy"] 내부 raw_data 또는 state["catl_raw_data"]

병렬 처리 규칙:
- 세 노드는 서로 다른 state 키에만 기록
- 상태 충돌 방지를 위해 에이전트 로컬 값은 state["market_agent"], state["lges_agent"], state["catl_agent"]만 사용
- Supervisor 라우팅은 기존 규칙 유지

### 2) RAG 우선 + Tavily Fallback 정책 공통화
각 노드에서 동일한 검색 정책 사용:
1. get_retriever() 또는 SingletonRAG.get_instance(namespace).get_retriever()로 내부 문서 검색
2. 부족하면 Tavily 호출

부족 판정 기준(코드 상수로 관리):
- min_docs 미만
- 평균 관련도(min_relevance) 미만
- 필수 키워드 커버리지 미달
- 최소 출처 수(min_sources) 미달

노드별 필수 키워드:
- market: ["전기차", "ESS"]
- lges: ["LGES", "배터리", "전략", "재무"]
- catl: ["CATL", "배터리", "전략", "재무"]

판정 규칙:
- 위 조건 중 하나라도 실패하면 fallback 사용
- fallback 사용 여부를 state[*_agent]["fallback_used"]에 기록

### 3) VectorDB 초기화(실제 PDF 반영)
- data/raw/{namespace} 아래 PDF를 읽어 임베딩 후 faiss_index/{namespace} 저장
- 재실행 안전:
  - 인덱스가 있으면 load
  - 필요 시 증분 업데이트(옵션) 또는 rebuild 플래그
- 임베딩 모델은 기존 BAAI/bge-m3 재사용
- 초기화 진입점 명확화:
  - 앱 시작 시 또는 명시적 init 함수

### 4) Validation Agent 구현
Validation system prompt에 반드시 포함:
- 데이터 편향성 점검
- 필수 비교 항목 누락 점검
- 출처 매핑 가능성 점검

검증 로직:
- 결과 상태: PASS 또는 REVISE
- REVISE면 revision_notes에 구체 사유 기록

편향성 검증(필수):
- LGES/CATL 각각 긍정/부정 근거를 양방향으로 수집 또는 분류
- 기업별 긍정/부정 비율 계산
- 한쪽 비율이 70% 초과하면 편향 판정
- 내부(RAG)와 외부(Web) 교차 근거 최소 1개 이상 요구
- 미충족 시 REVISE

### 5) Supervisor Retry/Reflect 주석
- Validation이 REVISE일 때 어디로 되돌아가는지 주석 명시
- 재시도 횟수 상한, 종료 조건, 무한루프 방지 방식 명시

## 문서화(README)
README에 다음을 추가:
- RAG 우선 + Tavily fallback 전략
- 부족 판정 기준과 임계값
- 기준 선택 이유(내부근거 우선, 환각 감소, 비용/속도 균형)
- Validation 편향성 점검 방식(긍/부정 비율, 70% 임계값, 교차검증)

## 출력 형식(반드시 준수)
작업 결과를 한 번에 다 내지 말고 커밋 단위로 순차 출력:
1. 변경 파일 목록
2. 코드
3. 핵심 설명(5줄 이내)
4. 추천 커밋 메시지 1개

내가 "다음"이라고 입력하면 다음 커밋 단위로 진행.
