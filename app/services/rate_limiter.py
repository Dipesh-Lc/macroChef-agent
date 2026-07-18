"""In-memory, per-process sliding-window rate limiter.

Gates `/library/discover`, `/recipes/recommend`, and `/library/reindex` --
the endpoints that drive paid LLM calls or (for reindex) a synchronous
full-corpus re-embed -- keyed on the verified session user id
(`app.dependencies.get_session_user`), never a client-supplied value. See
`app.dependencies` for the FastAPI dependency wiring that calls this.

Correctness note -- single process only: state lives in this class instance's
memory, not a shared store (Redis, DB row, etc). That is safe *today* because
`.github/workflows/ci.yml` pins the Azure Container Apps deployment to
`min-replicas=1` / `max-replicas=1` (embedded Chroma is single-writer, so the
whole deployment topology already assumes exactly one process is ever
serving traffic). If replicas ever go above 1, these limits silently become
*per-replica* -- a user could get up to (limit * replica_count) requests by
landing on different replicas -- with no error or warning. Tracked in
docs/BACKLOG.md; must be revisited (shared store, e.g. Redis) before any
multi-replica change.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from functools import lru_cache


class RateLimiter:
    """Sliding-window request counter keyed by an arbitrary string.

    `allow(key, limit, window_seconds)` records the current call and returns
    whether it is within the limit. Thread-safe (a single lock guards all
    buckets) since FastAPI/uvicorn may serve requests from a thread pool.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(
        self,
        key: str,
        limit: int,
        window_seconds: float,
        *,
        now: float | None = None,
    ) -> bool:
        """Return True and record a hit if `key` is under `limit` calls within
        the trailing `window_seconds`; return False (without recording)
        otherwise."""
        current = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            cutoff = current - window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(current)
            return True

    def reset(self) -> None:
        """Test-only helper: clear all recorded hits."""
        with self._lock:
            self._hits.clear()


@lru_cache
def get_rate_limiter() -> RateLimiter:
    """Process-wide singleton -- must be a single shared instance so counts
    actually accumulate across requests (a fresh instance per call would
    never rate-limit anything)."""
    return RateLimiter()
