FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# CPU-only torch keeps the image much smaller; parsing doesn't need a GPU.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Download parser/OCR models and chunker tokenizer now, so runtime can be fully offline.
RUN docling-tools models download && \
    python -c "from docling.chunking import HybridChunker; HybridChunker()"
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
