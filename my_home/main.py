from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from database import engine
import httpx
import uuid
import os

app = FastAPI()

# CORS 설정 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 서비스에서는 보안을 위해 도메인을 지정해야 합니다.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 템플릿 경로를 절대 경로로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# =========================
# Ollama 설정
# =========================
OLLAMA_BASE = "http://localhost:11434" # host.docker.internal is for docker-to-host
OLLAMA_GEN_URL = f"{OLLAMA_BASE}/api/generate"
OLLAMA_EMBED_URL = f"{OLLAMA_BASE}/api/embeddings"

# 생성 모델 / 임베딩 모델
OLLAMA_MODEL = "gemma3:4b"
EMBED_MODEL = "nomic-embed-text"

# RAG 검색 문서 개수
TOP_K = 4


# =========================
# 공통 유틸
# =========================
def vec_literal(v: list[float]) -> str:
    """pgvector literal: '[0.1,0.2,...]'"""
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


async def get_embedding(client: httpx.AsyncClient, text_input: str) -> list[float]:
    """Ollama /api/embeddings로 임베딩 생성"""
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


def search_documents(query_vec: list[float], top_k: int = 4) -> list[dict]:
    """pgvector 유사도 검색 (embedding이 NULL이 아니어야 검색됨)"""
    qv = vec_literal(query_vec)

    sql = text("""
        SELECT id, title, content, author, created_dt, view_count,
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
    """검색 문서를 prompt context로 변환"""
    if not docs:
        return "참고 문서 없음."

    parts = []
    for i, d in enumerate(docs, start=1):
        title = d.get("title") or f"doc-{d.get('id')}"
        author = d.get("author") or "-"
        content = (d.get("content") or "").strip()

        # 토큰 폭발 방지 (필요 시 조절)
        if len(content) > 1200:
            content = content[:1200] + "..."

        parts.append(f"[문서 {i}] {title} (작성자: {author})\n{content}")

    return "\n\n".join(parts)


async def ollama_generate(client: httpx.AsyncClient, prompt: str) -> str:
    r = await client.post(
        OLLAMA_GEN_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=120.0,
    )
    r.raise_for_status()
    return (r.json().get("response") or "").strip()


# =========================
# 1) 게시판 목록 페이지
# =========================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        # documents 목록을 DB에서 가져와서 index.html에 넘김
        with engine.connect() as conn:
            posts = conn.execute(text("""
                SELECT id, title, author, created_dt, view_count
                FROM public.documents
                ORDER BY id DESC
                LIMIT 50
            """)).mappings().all()

        return templates.TemplateResponse("index.html", {"request": request, "posts": posts})
    except Exception as e:
        import traceback
        print(f">>> Home page error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# 2) 게시글 상세 조회 API (index.html이 호출)
# =========================
@app.get("/posts/{post_id}")
async def get_post(post_id: int):
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT id, title, content, author, created_dt, view_count
            FROM public.documents
            WHERE id = :id
        """), {"id": post_id}).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Post not found")

        # 조회수 증가
        conn.execute(text("""
            UPDATE public.documents
            SET view_count = COALESCE(view_count, 0) + 1
            WHERE id = :id
        """), {"id": post_id})

        # 증가된 조회수 다시 읽기
        row2 = conn.execute(text("""
            SELECT view_count
            FROM public.documents
            WHERE id = :id
        """), {"id": post_id}).mappings().first()

    data = dict(row)
    if row2:
        data["view_count"] = row2["view_count"]

    # ✅ datetime(timestamptz) 같은 타입을 JSON으로 바꿔줌
    return JSONResponse(content=jsonable_encoder(data))


# =========================
# 3) RAG 챗봇 API
# =========================
@app.post("/chat")
async def chat(message: str = Form(...)):
    msg = message.strip()
    if not msg:
        return JSONResponse({"reply": "메시지를 입력해 주세요."}, status_code=400)

    async with httpx.AsyncClient() as client:
        try:
            # 1) 질문 임베딩
            qvec = await get_embedding(client, msg)

            # 2) DB 유사 문서 검색
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

            # 5) 답변 생성
            bot = await ollama_generate(client, prompt)
            if not bot:
                bot = "답변을 생성하지 못했어요. 다시 질문해 주세요."

        except Exception as e:
            bot = f"오류: {str(e)}"
            docs = []

    return JSONResponse({
        "reply": bot,
        "sources": [{"id": d["id"], "title": d.get("title"), "distance": float(d["distance"])} for d in docs]
    })

 
@app.post("/documents/create")
async def create_document(
    title: str = Form(""),
    content: str = Form(...),
    author: str = Form("hibiznet"),
):
    title = (title or "").strip()
    content = (content or "").strip()
    author = (author or "").strip()

    if not content:
        return JSONResponse({"ok": False, "error": "content is required"}, status_code=400)

    try:
        async with httpx.AsyncClient() as client:
            emb = await get_embedding(client, f"{title}\n\n{content}".strip())

        # pgvector literal
        emb_str = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"

        with engine.begin() as conn:
            row = conn.execute(text("""
                INSERT INTO public.documents (title, content, author, embedding)
                VALUES (:t, :c, :a, CAST(:e AS vector))
                RETURNING id
            """), {
                "t": title,
                "c": content,
                "a": author,
                "e": emb_str,
            }).fetchone()

        return JSONResponse({"ok": True, "id": row[0]})

    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/documents/reembed-missing")
@app.post("/documents/reembed-missing")
async def reembed_missing(limit: int = 200):
    print(">>> reembed_missing called, method=POST")
    async with httpx.AsyncClient() as client:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id, title, content
                FROM public.documents
                WHERE embedding IS NULL AND content IS NOT NULL
                ORDER BY id
                LIMIT :lim
            """), {"lim": limit}).mappings().all()

        updated = 0
        for r in rows:
            txt = f"{r.get('title','')}\n\n{r.get('content','')}".strip()
            emb = await get_embedding(client, txt)
            emb_str = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"

            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE public.documents
                    SET embedding = CAST(:e AS vector)
                    WHERE id = :id
                """), {"e": emb_str, "id": r["id"]})

            updated += 1

    return JSONResponse({"ok": True, "updated": updated})        