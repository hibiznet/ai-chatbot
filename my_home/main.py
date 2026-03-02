from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from database import engine
from sqlalchemy import text
import httpx
import uuid

app = FastAPI()

db_posts = []
templates = Jinja2Templates(directory="templates")

# =========================
# Ollama 설정
# =========================
# ✅ 너 환경에서는 브라우저에서도 localhost가 되므로 그대로 유지
OLLAMA_BASE = "http://localhost:11434"
OLLAMA_GEN_URL = f"{OLLAMA_BASE}/api/generate"
OLLAMA_EMBED_URL = f"{OLLAMA_BASE}/api/embeddings"

# 생성 모델
OLLAMA_MODEL = "gemma3:4b"

# ✅ 임베딩 모델 (Ollama에서 미리 pull 필요)
#    예: ollama pull nomic-embed-text
EMBED_MODEL = "nomic-embed-text"

# DB에서 가져올 문서 개수
TOP_K = 4


# =========================
# 유틸: Ollama 임베딩
# =========================
async def get_embedding(client: httpx.AsyncClient, text_input: str) -> list[float]:
    """
    Ollama로부터 텍스트 임베딩 벡터를 얻는다.
    Ollama /api/embeddings는 POST만 지원.
    """
    r = await client.post(
        OLLAMA_EMBED_URL,
        json={"model": EMBED_MODEL, "prompt": text_input},
        timeout=60.0,
    )
    r.raise_for_status()
    data = r.json()
    emb = data.get("embedding")
    if not emb or not isinstance(emb, list):
        raise RuntimeError("임베딩 생성 실패: embedding 필드가 없습니다.")
    return emb


# =========================
# 유틸: pgvector 검색
# =========================
def search_documents(query_vec: list[float], top_k: int = 4) -> list[dict]:
    qv = "[" + ",".join(f"{x:.6f}" for x in query_vec) + "]"

    sql = text("""
        SELECT id, title, content,
               (embedding <-> CAST(:qv AS vector)) AS distance
        FROM public.documents
        WHERE embedding IS NOT NULL
        ORDER BY embedding <-> CAST(:qv AS vector)
        LIMIT :k
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql, {"qv": qv, "k": top_k}).mappings().all()

    return [dict(r) for r in rows]


def build_context(docs: list[dict]) -> str:
    """
    검색된 문서들을 LLM prompt에 넣을 context 문자열로 만든다.
    """
    if not docs:
        return "참고 문서 없음."

    parts = []
    for i, d in enumerate(docs, start=1):
        title = d.get("title") or f"doc-{d.get('id')}"
        content = (d.get("content") or "").strip()

        # 너무 길면 잘라서 토큰 폭발 방지
        if len(content) > 1200:
            content = content[:1200] + "..."

        parts.append(f"[문서 {i}] {title}\n{content}")

    return "\n\n".join(parts)


# =========================
# 라우팅
# =========================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "posts": db_posts})


@app.post("/chat")
async def chat(message: str = Form(...)):
    """
    RAG 채팅:
    1) 질문 임베딩 생성
    2) pgvector에서 유사 문서 검색
    3) 참고문서를 포함해 LLM 생성 호출
    """
    msg = message.strip()
    if not msg:
        return JSONResponse({"reply": "메시지를 입력해 주세요."}, status_code=400)

    async with httpx.AsyncClient() as client:
        try:
            # 1) 질문 임베딩
            qvec = await get_embedding(client, msg)

            # 2) DB 검색
            docs = search_documents(qvec, TOP_K)

            # 3) context 만들기
            context = build_context(docs)

            # 4) 생성 프롬프트
            prompt = f"""너는 하이비즈봇 상담원이야.
아래 '참고 문서' 내용만을 근거로 사용자 질문에 답해줘.
참고 문서에 없는 내용은 추측하지 말고 "자료에 없습니다"라고 말해줘.
답변은 한국어로, 핵심 위주로 짧고 명확하게.

[참고 문서]
{context}

[사용자 질문]
{msg}

[답변]
"""

            # 5) Ollama 생성 호출
            r = await client.post(
                OLLAMA_GEN_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=120.0,
            )
            r.raise_for_status()
            bot = (r.json().get("response") or "").strip()
            if not bot:
                bot = "답변을 생성하지 못했어요. 다시 질문해 주세요."

        except Exception as e:
            bot = f"오류: {str(e)}"

    # 필요하면 sources를 프론트에 숨겨서 디버깅 가능
    return JSONResponse({
        "reply": bot,
        "sources": [{"id": d["id"], "title": d.get("title"), "distance": float(d["distance"])} for d in docs] if 'docs' in locals() else []
    })


@app.post("/post")
async def create_post(title: str = Form(...), content: str = Form(...)):
    """
    기존 게시판 글쓰기 로직은 그대로 유지 (RAG와 별개)
    """
    # 1. 사용자의 글 저장
    post_id = str(uuid.uuid4())[:8]
    user_post = {"id": post_id, "author": "User", "title": title, "content": content}
    db_posts.insert(0, user_post)

    # 2. Ollama에게 피드백 요청
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                OLLAMA_GEN_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": f"너는 게시판 관리자 AI야. 다음 글에 대해 친절한 댓글을 달아줘: {content}",
                    "stream": False,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            ai_reply = response.json().get("response")
        except Exception as e:
            ai_reply = f"AI 답변을 가져오는 중 오류가 발생했습니다: {str(e)}"

    # 3. AI 댓글 저장
    db_posts.insert(
        0,
        {"id": f"ai-{post_id}", "author": "Gemma_AI", "title": f"Re: {title}", "content": ai_reply},
    )

    return RedirectResponse(url="/", status_code=303)