from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from .config import TOP_K
from .db import init_db, get_conn
from .rag import extract_pages, chunk_text, embed, ask_llm


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="DocuMind", lifespan=lifespan)


class Query(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/documents")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    items = [(page, c) for page, text in extract_pages(file.filename, data)
             for c in chunk_text(text)]
    if not items:
        raise HTTPException(400, "No text found in file")
    vectors = embed([c for _, c in items])
    with get_conn() as conn:
        for (page, content), vec in zip(items, vectors):
            conn.execute(
                "INSERT INTO chunks (filename, page, content, embedding) VALUES (%s, %s, %s, %s)",
                (file.filename, page, content, vec))
    return {"filename": file.filename, "chunks": len(items)}


@app.get("/documents")
def list_documents():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT filename, COUNT(*) FROM chunks GROUP BY filename").fetchall()
    return [{"filename": r[0], "chunks": r[1]} for r in rows]


@app.post("/query")
def query(q: Query):
    qvec = embed([q.question])[0]
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT filename, page, content FROM chunks ORDER BY embedding <=> %s LIMIT %s",
            (qvec, TOP_K)).fetchall()
    if not rows:
        raise HTTPException(404, "No documents uploaded yet")
    return {
        "answer": ask_llm(q.question, rows),
        "sources": [{"filename": r[0], "page": r[1], "content": r[2]} for r in rows],
    }