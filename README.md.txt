
powershell
& "C:\Program Files\Docker\Docker\Docker Desktop.exe"

로그 확인
docker logs --tail 200 my_ollama-gemma

DB 접속 확인
python -c "from database import engine; from sqlalchemy import text; print(engine.connect().execute(text('select 1')).scalar())"

uvicorn main:app --reload --host 0.0.0.0 --port 80
