"""Rate limiter: in-memory (sqlite/single-process) or Postgres-backed
(shared across replicas), selected automatically by `get_rate_limiter()`.

Gates `/library/discover`, `/recipes/recommend`, and `/library/reindex` --
the endpoints that drive paid LLM calls or (for reindex) a synchronous
full-corpus re-embed -- keyed on the verified session user id
(`app.dependencies.get_session_user`), never a client-supplied value. See
`app.dependencies` for the FastAPI dependency wiring that calls this.

ROADMAP.md Phase 5, Step 5.2 -- history: this module used to be in-memory
ONLY, correctness-noted as "single process only", and was one of two
documented `max-replicas=1` blockers (the other: the embedded, single-
writer Chroma store, addressed by `app.rag.pgvector_store`). `RateLimiter`
below (the original class, unchanged) stays the default for sqlite/local
dev -- no DB round-trip when nothing needs cross-process sharing.
`PostgresRateLimiter` is the shared alternative, selected automatically
when `DATABASE_URL` is a real Postgres instance (see `get_rate_limiter`).

Clearing this blocker does NOT itself raise `max-replicas` in
`.github/workflows/ci.yml` -- that stays a deliberate, separate,
maintainer-made production-topology change (CLAUDE.md invariant #8; see
`docs/DEPLOY.md`'s "Cost implication" section for the up-to-date status).
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Protocol


class SupportsRateLimiting(Protocol):
    """The interface both `RateLimiter` and `PostgresRateLimiter` satisfy --
    `app.dependencies`' rate-limit dependencies call `.allow()` through
    `get_rate_limiter()` and never care which implementation they got."""

    def allow(
        self, key: str, limit: int, window_seconds: float, *, now: float | None = None
    ) -> bool: ...

    def reset(self) -> None: ...


class RateLimiter:
    """Sliding-window request counter keyed by an arbitrary string.

    `allow(key, limit, window_seconds)` records the current call and returns
    whether it is within the limit. Thread-safe (a single lock guards all
    buckets) since FastAPI/uvicorn may serve requests from a thread pool.

    `now` is `time.monotonic()`-compatible (meaningful only within this
    process) -- fine here since this class is only ever used single-process.
    Contrast `PostgresRateLimiter.allow`'s `now`, which is wall-clock epoch
    seconds (must be comparable across processes/replicas). No production
    call site passes `now=` explicitly either way; only unit tests do.
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


def _current_database_url() -> str:
    """Read `DATABASE_URL` directly from the environment rather than through
    `app.config.get_settings()` / `app.data.db.engine` -- both are
    process-wide `@lru_cache`d or bound at first import, so a value read
    through them can be stale in any process where some *other* module
    already imported `app.data.db` against a different URL (harmless in
    production, where the env var is fixed at process start, but a real
    problem for the test suite -- see `app.rag.pgvector_store`'s module
    docstring, which hit and fixed the identical issue first)."""
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./macrochef.db")
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    return database_url


def _lock_id(key: str) -> int:
    """Deterministic, cross-process-stable bigint for `pg_advisory_xact_lock`
    -- Python's built-in `hash(str)` is salted per-process
    (`PYTHONHASHSEED`), so it CANNOT be used here: two replicas locking the
    same `key` must compute the same lock id, or the lock provides no
    mutual exclusion at all."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, "big", signed=True)


class PostgresRateLimiter:
    """Shared, cross-replica sliding-window limiter backed by
    `rate_limit_hits` (`app.data.models.RateLimitHit`). Same algorithm as
    `RateLimiter` (delete-expired, count, conditionally insert) but against
    a table instead of an in-memory deque, so multiple ACA replicas see the
    same count for the same key.

    Concurrency: `pg_advisory_xact_lock` serializes concurrent `allow()`
    calls for the SAME key (across all processes/replicas, not just
    threads in this one) for the duration of the transaction, closing the
    check-then-insert race an unlocked "SELECT count, then INSERT if under
    limit" would otherwise have under concurrent load. The lock
    auto-releases at transaction end (commit/rollback) -- no explicit
    unlock needed. An occasional hash collision between two *different*
    keys just serializes them against each other unnecessarily (a
    performance cost, not a correctness one -- the row-level WHERE clause
    still scopes everything to the real `key`).

    `now`, when passed explicitly (only unit tests do), is wall-clock epoch
    seconds (`time.time()`-compatible) -- NOT `time.monotonic()`, unlike
    `RateLimiter.allow`'s `now`. Monotonic clocks are only comparable within
    a single process; hit timestamps here must be comparable across
    whichever replica/process reads them next.
    """

    def _engine(self):
        from sqlalchemy import create_engine

        database_url = _current_database_url()
        if database_url not in _POSTGRES_LIMITER_ENGINES:
            _POSTGRES_LIMITER_ENGINES[database_url] = create_engine(
                database_url, pool_pre_ping=True
            )
        return _POSTGRES_LIMITER_ENGINES[database_url]

    def allow(
        self,
        key: str,
        limit: int,
        window_seconds: float,
        *,
        now: float | None = None,
    ) -> bool:
        from sqlalchemy import text

        current = time.time() if now is None else now
        current_dt = datetime.fromtimestamp(current, tz=UTC)
        cutoff_dt = current_dt - timedelta(seconds=window_seconds)

        with self._engine().begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": _lock_id(key)})
            conn.execute(
                text("DELETE FROM rate_limit_hits WHERE key = :key AND hit_at <= :cutoff"),
                {"key": key, "cutoff": cutoff_dt},
            )
            count = conn.execute(
                text("SELECT COUNT(*) FROM rate_limit_hits WHERE key = :key"), {"key": key}
            ).scalar_one()
            if count >= limit:
                return False
            conn.execute(
                text("INSERT INTO rate_limit_hits (key, hit_at) VALUES (:key, :hit_at)"),
                {"key": key, "hit_at": current_dt},
            )
            return True

    def reset(self) -> None:
        """Test-only helper: clear every recorded hit across all keys."""
        from sqlalchemy import text

        with self._engine().begin() as conn:
            conn.execute(text("DELETE FROM rate_limit_hits"))


_POSTGRES_LIMITER_ENGINES: dict[str, object] = {}


@lru_cache
def get_rate_limiter() -> SupportsRateLimiting:
    """Process-wide singleton -- must be a single shared instance so counts
    actually accumulate across requests (a fresh instance per call would
    never rate-limit anything).

    Backend selection (ROADMAP.md Phase 5, Step 5.2): sqlite (today's only
    shipped topology, `min-replicas=1`/`max-replicas=1`) keeps the original
    in-memory `RateLimiter` -- no DB round-trip for the common case. A real
    Postgres `DATABASE_URL` gets the shared `PostgresRateLimiter` instead,
    same dialect-based switch `app.data.db.init_db` already uses for
    `create_all`. This selection alone does not change `max-replicas` in
    `.github/workflows/ci.yml` -- see this module's docstring."""
    if _current_database_url().startswith("sqlite"):
        return RateLimiter()
    return PostgresRateLimiter()
