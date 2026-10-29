from fastapi.testclient import TestClient
from app import main
from app.rag import chunk_text

client = TestClient(main.app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_chunking():
    chunks = chunk_text("a" * 1000)
    assert len(chunks) == 3
    assert all(len(c) <= 500 for c in chunks)


class FakeConn:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def execute(self, *a, **k):
        class R:
            def fetchall(self):
                return [("doc.pdf", 1, "Paris is the capital of France.")]
        return R()


def test_query(monkeypatch):
    monkeypatch.setattr(main, "embed", lambda t: [[0.0] * 384])
    monkeypatch.setattr(main, "get_conn", lambda: FakeConn())
    monkeypatch.setattr(main, "ask_llm", lambda q, r: "Paris [1]")
    r = client.post("/query", json={"question": "Capital of France?"})
    assert r.status_code == 200
    assert r.json()["answer"] == "Paris [1]"
    assert r.json()["sources"][0]["filename"] == "doc.pdf"