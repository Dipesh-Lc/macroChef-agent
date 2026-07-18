FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Default public port for the Streamlit UI (the only public ingress -- see
# docker-entrypoint.sh). ACA overrides this by setting PORT on the container;
# locally `docker run -p 8501:8501` matches this default with no extra config.
ENV PORT=8501

# repo root on sys.path: Streamlit only adds the script dir (frontend/), but frontend imports app.config/app.dependencies — first caught in-container 2026-07-18
ENV PYTHONPATH=/app

# Pin the HF cache to a known, predictable path so the model baked in below
# (RUN ... SentenceTransformer(...)) and the runtime load in
# app/rag/embeddings.py resolve to the exact same on-disk cache. The image
# never switches to a non-root USER, so this directory stays owned by and
# readable by whichever user runs the container (root, by default).
ENV HF_HOME=/app/.cache/huggingface

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the MiniLM embedding model into the image at build time so there is
# NO runtime download. app/rag/embeddings.py's get_embedding_function()
# raises EmbeddingModelUnavailableError when EMBEDDING_PROVIDER=local can't
# load the model -- that's an intentional loud startup failure (it used to
# silently fall back to hash embeddings that don't match the MiniLM-built
# Chroma index), so the model MUST already be present in the image.
# This step only depends on requirements.txt, so it stays cached across
# app-code-only rebuilds.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY . .

RUN chmod +x docker-entrypoint.sh

# Only the Streamlit port is exposed/public. FastAPI/uvicorn binds
# 127.0.0.1:8000 inside docker-entrypoint.sh and is never reachable from
# outside the container.
EXPOSE 8501

# ACA's ingress probe hits the public Streamlit port, not the internal API,
# so it can't be used to detect an API-only crash. This HEALTHCHECK covers
# that gap by curling the internal API directly from inside the container.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
