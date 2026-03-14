# AI 챗봇 게시판 (RAG 기반)

이 프로젝트는 **FastAPI**와 **PostgreSQL (pgvector)**, 그리고 **Ollama (gemma:2b)**를 활용하여 구현된 RAG(Retrieval-Augmented Generation) 기반의 AI 챗봇 게시판입니다.

## 🚀 주요 기능
- **게시판 기능**: 게시글 작성, 목록 조회, 상세 조회 (Jinja2 템플릿 사용)
- **RAG 검색**: 질문에 대해 `pgvector`를 이용한 유사도 검색을 수행하여 관련 문서를 추출합니다.
- **AI 챗봇**: 추출된 문서 내용을 바탕으로 `Ollama (gemma:2b)` 모델이 최적화된 답변을 생성합니다.

---

## 🛠 사전 준비 사항
1. **Docker Desktop**: 데이터베이스와 Ollama 실행을 위해 필요합니다.
2. **Python 3.13**: 애플리케이션 실행을 위해 권장되는 버전입니다. (3.14는 일부 라이브러리 호환성 문제가 있을 수 있음)

---

## 🏗 시스템 실행 방법

### 1. 데이터베이스(PostgreSQL) 실행
`pgvector`가 포함된 PostgreSQL 컨테이너를 실행합니다.
```powershell
cd my_postgres
docker-compose up -d
```

### 2. Ollama(AI 서버) 실행 및 모델 준비
Ollama 서버를 컨테이너로 실행하고 필요한 모델(`gemma:2b`, `nomic-embed-text`)을 다운로드합니다.
```powershell
# 컨테이너 실행
docker run -d --name my_ollama-gemma -p 11434:11434 ollama/ollama

# 모델 다운로드 (완료될 때까지 기다려 주세요)
docker exec my_ollama-gemma ollama pull gemma:2b
docker exec my_ollama-gemma ollama pull nomic-embed-text
```

### 3. Python 가상 환경 설정 및 패키지 설치
`my_home` 디렉토리로 이동하여 가상 환경을 만들고 필수 패키지를 설치합니다.
```powershell
cd my_home
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. FastAPI 애플리케이션 실행
서버를 실행합니다. (기본 포트 80으로 설정되어 있습니다.)
```powershell
cd my_home
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 80
```

---

## ✅ 구동 확인 방법
1. 브라우저에서 [http://localhost/](http://localhost/)에 접속합니다.
2. 게시판 화면이 정상적으로 출력되는지 확인합니다.
3. 하단 검색창에 질문을 입력하여 AI 챗봇의 답변을 확인합니다. (예: "이 프로젝트의 주요 기술 스택은?")

---

## 📂 프로젝트 구조
- `my_home/`: FastAPI 소스 코드 및 템플릿
  - `main.py`: 서버 로직 및 AI 인터페이스
  - `database.py`: DB 연결 설정
  - `templates/`: HTML 템플릿
- `my_postgres/`: DB 설정을 위한 Docker Compose 파일
- `README.md`: 프로젝트 안내서 (본 파일)
