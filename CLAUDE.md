# CLAUDE.md

Local document Q&A. Upload a file, ask questions, get answers with citations. Nothing leaves the machine.

Flow: upload → Docling parses/OCRs → chunks → embeddings (Ollama) → Qdrant. Ask → embed question → top-K chunks → local LLM answers citing `[n]`.

## Layout

- `zdr-reader` is the full project. The root only has loose copies of `main.py`, `README.md`, `docker-compose.yml`.
- In the real layout, `main.py`, `Dockerfile`, `requirements.txt` and `static/index.html` live in `app/`. Compose builds `./app`, so it fails from the root as-is.
- Backend: `main.py` (FastAPI, one file). Frontend: `static/index.html` (vanilla JS, no build).

## Rules

- **No network egress.** No external APIs, CDNs, fonts, telemetry or runtime model downloads. Anything that needs a download goes in the Dockerfile at build time.
- **Don't store uploads.** Parse from a temp file and delete it. Only chunks and vectors persist, in Qdrant.
- **Bind ports to `127.0.0.1`.** Never `0.0.0.0` on the host side.
- **Model servers are OpenAI-compatible.** Call `/v1/embeddings` and `/v1/chat/completions` over `httpx`. Don't add vendor SDKs.
- **Config comes from env vars** (see `.env.example`). Add new ones there with a comment.
- **Keep it small.** One backend file and one HTML file. Add a module or dependency only when it's clearly needed, and pin its version.
- Deleting a document must remove every chunk with that `doc_id`.

## Run

`cp .env.example .env`, set `LLM_MODEL`, then `docker compose up -d --build`. UI at http://localhost:8000. For Mac, see the README.
