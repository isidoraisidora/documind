import io
from groq import Groq
from pypdf import PdfReader
from .config import GROQ_API_KEY

_model = None


def extract_pages(filename: str, data: bytes) -> list[tuple[int, str]]:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
    return [(1, data.decode("utf-8", errors="ignore"))]


def chunk_text(text: str, size: int = 500, overlap: int = 50) -> list[str]:
    text = text.replace("\x00", "").strip()
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return chunks


def embed(texts: list[str]):
    global _model
    if _model is None:  # loaded on first use so tests don't download the model
        from fastembed import TextEmbedding
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")  # 384 dimensions
    return list(_model.embed(texts))


def ask_llm(question: str, rows) -> str:
    context = "\n\n".join(
        f"[{i + 1}] ({r[0]}, page {r[1]}) {r[2]}" for i, r in enumerate(rows)
    )
    client = Groq(api_key=GROQ_API_KEY)
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": (
                "Answer using only the provided context. Cite sources like [1]. "
                "If the answer is not in the context, say you don't know.")},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
    )
    return resp.choices[0].message.content