"""Private document Q&A. Parses files locally, stores chunks in local Qdrant,
answers with a locally served model. No external network calls."""
import os
import tempfile
import uuid
from pathlib import Path

import httpx
from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import (Distance, FieldCondition, Filter, FilterSelector,
                                  MatchValue, PointStruct, VectorParams)

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://ollama:11434/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "")
EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", LLM_BASE_URL).rstrip("/")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
TOP_K = int(os.getenv("TOP_K", "6"))
COLLECTION = "documents"

app = FastAPI(title="Private docs")
qdrant = QdrantClient(url=os.getenv("QDRANT_URL", "http://qdrant:6333"))
converter = DocumentConverter()
chunker = HybridChunker()
http = httpx.Client(timeout=600)

SYSTEM_PROMPT = (
    "You answer questions using only the provided excerpts from the user's documents. "
    "Cite sources inline as [n]. If the excerpts don't contain the answer, say so plainly."
)


def embed(texts: list[str]) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), 32):
        r = http.post(f"{EMBED_BASE_URL}/embeddings",
                      json={"model": EMBED_MODEL, "input": texts[i:i + 32]})
        r.raise_for_status()
        out += [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
    return out


def ensure_collection(dim: int) -> None:
    if not qdrant.collection_exists(COLLECTION):
        qdrant.create_collection(COLLECTION, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))


@app.post("/api/documents")
async def upload(file: UploadFile = File(...)):
    suffix = Path(file.filename or "upload").suffix
    # Temp copy only for parsing; deleted immediately after.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(await file.read())
        tmp.flush()
        try:
            doc = converter.convert(tmp.name).document
        except Exception as e:
            raise HTTPException(400, f"Couldn't read {file.filename}: {e}")

    chunks = [chunker.contextualize(chunk=c) for c in chunker.chunk(dl_doc=doc)]
    chunks = [c for c in chunks if c.strip()]
    if not chunks:
        raise HTTPException(400, f"No text found in {file.filename}.")

    vectors = embed(chunks)
    ensure_collection(len(vectors[0]))
    doc_id = str(uuid.uuid4())
    qdrant.upsert(COLLECTION, points=[
        PointStruct(id=str(uuid.uuid4()), vector=v,
                    payload={"doc_id": doc_id, "filename": file.filename, "chunk": i, "text": t})
        for i, (t, v) in enumerate(zip(chunks, vectors))
    ])
    return {"doc_id": doc_id, "filename": file.filename, "chunks": len(chunks)}


@app.get("/api/documents")
def list_documents():
    if not qdrant.collection_exists(COLLECTION):
        return []
    docs, offset = {}, None
    while True:
        points, offset = qdrant.scroll(COLLECTION, limit=1000, offset=offset,
                                       with_payload=["doc_id", "filename"], with_vectors=False)
        for p in points:
            d = docs.setdefault(p.payload["doc_id"], {"doc_id": p.payload["doc_id"],
                                                       "filename": p.payload["filename"], "chunks": 0})
            d["chunks"] += 1
        if offset is None:
            break
    return sorted(docs.values(), key=lambda d: d["filename"].lower())


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    if qdrant.collection_exists(COLLECTION):
        qdrant.delete(COLLECTION, points_selector=FilterSelector(filter=Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])))
    return {"deleted": doc_id}


class Question(BaseModel):
    question: str
    doc_ids: list[str] | None = None


@app.post("/api/ask")
def ask(q: Question):
    if not LLM_MODEL:
        raise HTTPException(500, "Set LLM_MODEL in .env, then restart the app.")
    if not qdrant.collection_exists(COLLECTION):
        raise HTTPException(400, "Add a document first.")

    flt = None
    if q.doc_ids:
        flt = Filter(should=[FieldCondition(key="doc_id", match=MatchValue(value=d)) for d in q.doc_ids])
    hits = qdrant.query_points(COLLECTION, query=embed([q.question])[0],
                               query_filter=flt, limit=TOP_K, with_payload=True).points

    context = "\n\n".join(f"[{i + 1}] ({h.payload['filename']})\n{h.payload['text']}"
                          for i, h in enumerate(hits))
    r = http.post(f"{LLM_BASE_URL}/chat/completions", json={
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Excerpts:\n{context}\n\nQuestion: {q.question}"},
        ],
        "temperature": 0.2,
    })
    if r.status_code != 200:
        raise HTTPException(502, f"Model server error: {r.text[:300]}")
    return {
        "answer": r.json()["choices"][0]["message"]["content"],
        "sources": [{"n": i + 1, "filename": h.payload["filename"], "text": h.payload["text"][:400]}
                    for i, h in enumerate(hits)],
    }


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
