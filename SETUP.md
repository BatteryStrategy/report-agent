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
