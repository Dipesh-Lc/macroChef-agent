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

# Bake the Chroma vector index into the image at build time, from the
# TRACKED base corpus only (data/processed/sample_recipes.jsonl +
# imported_recipes.jsonl via RecipeIndexingService._collect_recipes,
# include_user=False) -- never from whatever data/chroma happens to be on
# the machine/runner doing the build (that directory is excluded from the
# build context by .dockerignore, so a stale or empty local/CI copy can
# never leak in silently). include_user=False is required here, not just
# preferred: there is no live DATABASE_URL at build time, and baking one
# user's saved recipes into a shared image would be wrong regardless.
# rebuild_index_clean drops and recreates the collection first, so this is
# always a full, reproducible rebuild from the code currently being built,
# not an incremental patch. User-saved recipes are added at runtime via
# upsert (recipe save flow / POST /library/reindex), which is unaffected by
# this step. See docs/DEPLOY.md "Vector index and embeddings" and
# docs/BACKLOG.md for the staleness fix this closes (2026-07-19).
RUN python -c "from app.services.recipe_indexing_service import RecipeIndexingService; n = RecipeIndexingService().rebuild_index_clean(include_base=True, include_user=False); print(f'Baked {n} base recipes into the Chroma index at build time.'); assert n > 0, 'Chroma index build produced 0 recipes -- refusing to ship an empty index'"

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
