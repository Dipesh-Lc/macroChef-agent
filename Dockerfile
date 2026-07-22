# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build the React SPA (SPA rebuild W6 -- single-process cutover).
# Only `web/` is needed here; the Python app is built in stage 2 below and
# never touches Node.
# ---------------------------------------------------------------------------
FROM node:22-alpine AS webbuild

WORKDIR /web

# Copy the lockfile-defining files first so `npm ci` stays cached across
# app-source-only rebuilds, same caching strategy as stage 2's
# requirements.txt copy below.
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: the FastAPI app, now serving the SPA it just built above as the
# ONLY process in the container -- no Streamlit, no docker-entrypoint.sh
# supervisor. See app/spa.py (mount_spa) for how the built `web/dist` is
# served + its client-side-routing fallback.
# ---------------------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ACA injects PORT at runtime; locally `docker run -p 8000:8000` matches
# this default with no extra config.
ENV PORT=8000

# repo root on sys.path -- app/ imports app.config/app.dependencies etc.
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

# The built SPA from stage 1 -- see app/spa.py's mount_spa (settings.web_dist
# defaults to ./web/dist, matching this path). Copied from the `webbuild`
# stage's fresh build output, NEVER from the host's own `web/dist` (excluded
# from the build context by .dockerignore, so a stale local build can never
# be baked in instead of this stage's output).
COPY --from=webbuild /web/dist ./web/dist

# Single public process: FastAPI/uvicorn serves both the JSON API and the
# SPA static files (app/spa.py). No internal-only process, no supervisor.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT}/health || exit 1

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
