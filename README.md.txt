
powershell
& "C:\Program Files\Docker\Docker\Docker Desktop.exe"

로그 확인
docker logs --tail 200 my_ollama-gemma

DB 접속 확인
python -c "from database import engine; from sqlalchemy import text; print(engine.connect().execute(text('select 1')).scalar())"

uvicorn main:app --reload --host 0.0.0.0 --port 80



# 1. Ollama 설치
irm https://ollama.com/install.ps1 | iex

# 2. 모델 다운로드
ollama pull qwen3:8b

# 3. 로컬 실행 확인
ollama run qwen3:8b

# 4. API 확인
curl http://localhost:11434/api/tags

# 5. Open WebUI 실행
docker run -d `
  -p 3000:8080 `
  -v open-webui:/app/backend/data `
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 `
  --name open-webui `
  --restart always `
  ghcr.io/open-webui/open-webui:main