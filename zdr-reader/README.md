# Private docs

Local, zero-data-retention document Q&A. Files are parsed, indexed and answered entirely on your machine.

The stack has three parts:
- **Docling** handles parsing and OCR for PDF, DOCX, PPTX, HTML and images.
- **Qdrant** stores the vectors.
- **Ollama** (or vLLM) serves both the chat model and the embedding model.

## Run (Linux + NVIDIA GPU)

```bash
cp .env.example .env            # set LLM_MODEL to an Ollama tag that fits your GPU
docker compose up -d --build
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull <your LLM_MODEL>
open http://localhost:8000
```

## Run (Mac)

Docker on macOS can't use the Apple GPU, so run Ollama natively instead:

1. Install Ollama from ollama.com.
2. Run `ollama pull nomic-embed-text` and `ollama pull <model>`.
3. Delete the `ollama` service from `docker-compose.yml`.
4. In `.env`, set `LLM_BASE_URL` and `EMBED_BASE_URL` to `http://host.docker.internal:11434/v1`.
5. Run `docker compose up -d --build`.

## Bigger models (multi-GPU, vLLM)

Serve the model with vLLM's OpenAI-compatible server, then point `LLM_BASE_URL` at it, e.g. `http://vllm:8000/v1`. You can keep using Ollama for embeddings.

## Model choice

The app turns every file into text first, including OCR on scans, so a text model works.

| Hardware | Model |
|---|---|
| 24 GB GPU | Nemotron 3.5 Bolt |
| 32–64 GB GPU or Mac | Qwen3.8-27B or Gemma 4 31B |
| ~200 GB, vLLM | GLM-5.3-Flash or Nemotron 3.5 Super VL |

Use the exact tag listed on ollama.com/library or Hugging Face.

## Locking it down

- All ports bind to `127.0.0.1`, so nothing is reachable from your network.
- **No outbound calls at runtime.** Parser models are baked in at build time and `HF_HUB_OFFLINE=1` is set. Qdrant telemetry is off. The UI loads no external fonts or scripts.
- **Hard egress block.** After the models are pulled, add `networks: { default: { internal: true } }` to the compose file to cut internet access entirely. Without it, nothing calls out, but nothing is technically stopped from doing so.
- **Where data lives.** Uploaded files are not stored. They are parsed from a temp file that is deleted immediately. Text chunks and vectors persist in the `qdrant` volume.
  - Deleting a document in the UI removes its chunks.
  - `docker compose down -v` wipes everything.
- **Encryption at rest.** Put Docker's data directory on an encrypted disk.
