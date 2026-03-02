from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from database import engine, get_db
import httpx
import uuid

app = FastAPI()

db_posts = []

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "posts": db_posts})

@app.post("/post")
async def create_post(title: str = Form(...), content: str = Form(...)):
    # 1. 사용자의 글 저장
    post_id = str(uuid.uuid4())[:8]
    user_post = {"id": post_id, "author": "User", "title": title, "content": content}
    db_posts.insert(0, user_post)

    # 2. Ollama(Gemma 3 4B)에게 피드백 요청
    async with httpx.AsyncClient() as client:
        try:
            # 도커로 실행 중인 Ollama API 주소
            response = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "gemma3:4b",
                    "prompt": f"너는 게시판 관리자 AI야. 다음 글에 대해 친절한 댓글을 달아줘: {content}",
                    "stream": False
                },
                timeout=30.0 # CPU 연산이므로 타임아웃을 넉넉히 잡습니다.
            )
            ai_reply = response.json().get("response")
        except Exception as e:
            ai_reply = f"AI 답변을 가져오는 중 오류가 발생했습니다: {str(e)}"

    # 3. AI의 댓글 저장
    db_posts.insert(0, {"id": f"ai-{post_id}", "author": "Gemma_AI", "title": f"Re: {title}", "content": ai_reply})

    return RedirectResponse(url="/", status_code=303)