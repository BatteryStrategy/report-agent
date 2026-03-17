# 로컬 개발 환경 설정 가이드 (uv)

## 1. uv 설치 (없는 경우)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 2. Python 가상환경 생성

```bash
uv venv --python 3.11
```

## 3. 가상환경 활성화

**macOS / Linux**
```bash
source .venv/bin/activate
```

**Windows**
```powershell
.venv\Scripts\activate
```

## 4. 의존성 설치

`pyproject.toml`을 읽어 모든 의존성을 설치합니다.

```bash
uv sync
```

## 5. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 실제 API 키 값을 입력하세요
```

---

## 6. 프로젝트 실행

```bash
python -m src.main
```

첫 실행 시 아래 디렉토리가 자동으로 생성됩니다.

```
report-agent/
├── data/
│   ├── raw/
│   │   ├── market/   # Market Research 에이전트 전용 PDF (시장 배경 분석)
│   │   ├── lges/     # LGES Strategy 에이전트 전용 PDF
│   │   ├── catl/     # CATL Strategy 에이전트 전용 PDF
│   │   └── common/   # Validation / Comparison / Report Writer 공용 PDF
│   └── processed/    # 전처리 결과 저장 (자동)
├── faiss_index/
│   ├── market/       # market 네임스페이스 FAISS 인덱스 (자동)
│   ├── lges/         # lges 네임스페이스 FAISS 인덱스 (자동)
│   ├── catl/         # catl 네임스페이스 FAISS 인덱스 (자동)
│   └── common/       # common 네임스페이스 FAISS 인덱스 (자동)
└── output/
    ├── report/       # 최종 보고서 Markdown/PDF 저장
    ├── logs/         # 에이전트 실행 로그
    └── tmp/          # 중간 산출물
```

## 7. PDF 데이터 준비 및 인덱스 초기화

1. 각 에이전트에 맞는 폴더에 PDF를 넣습니다.

   | 폴더 | 담당 에이전트 | 넣어야 할 PDF 예시 |
   |------|--------------|-------------------|
   | `data/raw/market/` | Market Research | 산업 동향, 배터리 시장 리포트 |
   | `data/raw/lges/` | LGES Strategy | LG에너지솔루션 사업보고서, IR 자료 |
   | `data/raw/catl/` | CATL Strategy | CATL 연차보고서, 전략 문서 |
   | `data/raw/common/` | Validation / Comparison / Report Writer | 공통 참고 문서 |

2. 특정 에이전트 인덱스만 초기화하려면 해당 폴더만 삭제 후 재실행합니다.

```bash
# 예: LGES 인덱스만 초기화
rm -rf faiss_index/lges/
python -m src.main

# 전체 초기화
rm -rf faiss_index/
python -m src.main
```

## 8. 결과 확인

실행 완료 후 `output/report/` 폴더에서 생성된 보고서를 확인합니다.
