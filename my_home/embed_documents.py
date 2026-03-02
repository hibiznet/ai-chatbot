import os
import httpx
from sqlalchemy import text
from database import engine

OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

def vector_literal(vec):
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

def main():
    # 1) embedding이 비어있는 문서 가져오기
    with engine.connect() as conn:
        docs = conn.execute(text("""
            SELECT id, title, content
            FROM public.documents
            WHERE embedding IS NULL AND content IS NOT NULL
            ORDER BY id
        """)).mappings().all()

    if not docs:
        print("✅ 임베딩을 채울 문서가 없습니다.")
        return

    print(f"📄 임베딩 생성 대상 문서 수: {len(docs)}")

    with httpx.Client(timeout=60.0) as client:
        for d in docs:
            doc_id = d["id"]
            title = d.get("title") or ""
            content = d.get("content") or ""

            # 임베딩 입력 텍스트 (원하면 title 포함/제외 조정 가능)
            input_text = f"{title}\n\n{content}".strip()

            # 2) Ollama 임베딩 생성
            r = client.post(
                f"{OLLAMA_BASE}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": input_text},
            )
            r.raise_for_status()
            emb = r.json()["embedding"]

            # 3) DB 업데이트
            emb_str = vector_literal(emb)

            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE public.documents SET embedding = CAST(:v AS vector) WHERE id = :id"),
                    {"v": emb_str, "id": doc_id},
                )

            print(f"✅ updated id={doc_id} (dim={len(emb)})")

    print("🎉 완료!")

if __name__ == "__main__":
    main()