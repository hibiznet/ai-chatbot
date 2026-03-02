python -m venv .venv

# 2. 가상환경 활성화 (PowerShell 보안 정책 때문에 에러가 나면 아래 실행)
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\Activate.ps1

# 3. 필수 패키지 설치
pip install fastapi uvicorn jinja2 httpx python-multipart
uvicorn main:app --reload --host 0.0.0.0 --port 80

# 학습
python .\embed_documents.py