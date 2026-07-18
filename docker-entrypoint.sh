#!/bin/bash
# Single-container, two-process entrypoint for the ACA image.
#
# Topology (see docs/DEPLOY.md / .github/workflows/ci.yml):
#   - Streamlit is the ONLY public-facing process. It binds 0.0.0.0:$PORT
#     (ACA injects PORT at runtime; defaults to 8501 for local `docker run`).
#   - FastAPI/uvicorn is internal-only. It binds 127.0.0.1:8000 -- loopback,
#     NOT 0.0.0.0 -- so it is unreachable from outside the container. The
#     Streamlit app talks to it over MACROCHEF_API_URL (defaults to
#     http://localhost:8000, see frontend/streamlit_app.py).
#
# Failure semantics: both processes are required for a working app. If
# either one dies, the container must exit non-zero rather than keep
# running degraded -- a container where uvicorn died but Streamlit still
# answers is worse than a crashed one, because ACA/the platform would
# report it healthy while every request that touches the API fails.
set -euo pipefail

PORT="${PORT:-8501}"

uvicorn app.main:app --host 127.0.0.1 --port 8000 &
UVICORN_PID=$!

streamlit run frontend/streamlit_app.py \
    --server.address 0.0.0.0 \
    --server.port "$PORT" \
    --server.headless true &
STREAMLIT_PID=$!

cleanup() {
    trap - TERM INT
    kill "$UVICORN_PID" 2>/dev/null || true
    kill "$STREAMLIT_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
    wait "$STREAMLIT_PID" 2>/dev/null || true
}

# Forward a graceful shutdown (docker stop / ACA revision teardown) to both
# children instead of leaving them running until SIGKILL.
trap 'cleanup; exit 143' TERM INT

# `wait -n` (bash 4.3+) returns as soon as ANY of the listed jobs exits, with
# that job's exit status -- this is how we detect a one-sided crash instead
# of blocking until both processes happen to exit.
set +e
wait -n "$UVICORN_PID" "$STREAMLIT_PID"
EXIT_CODE=$?
set -e

cleanup

# Whichever process exited first, exited when it should have run forever.
# Treat that as a failure even if its own exit code was 0.
if [ "$EXIT_CODE" -eq 0 ]; then
    EXIT_CODE=1
fi

exit "$EXIT_CODE"
