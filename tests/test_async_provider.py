"""ROADMAP.md Phase 2, Step 2.2 -- async provider choke point.

Exercises `app.services.model_provider`'s async additions
(`agenerate_text`/`agenerate_text_batch`, and the `_async_post_json` choke
point they share) against `httpx.MockTransport` -- no real network, no real
provider. Three behaviors pinned here, matching the roadmap step's test
list:

1. the concurrency bound (`asyncio.Semaphore`) is actually respected --
   never more than `max_concurrency` requests in flight at once;
2. a 429 response is retried (with backoff) and then succeeds;
3. a timeout surfaces as a clean `errors[]` entry from `agenerate_text_
   batch` -- never an unhandled exception, matching this codebase's
   existing "readable partial-failure message, not a raised exception/500"
   convention (`RecommendationResponse.errors`/`DiscoveryResponse.errors`).

No `pytest-asyncio` dependency: every test drives its own coroutine via a
plain `asyncio.run(...)` call inside an ordinary `def test_...` function.
"""

import asyncio

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.observability.llm_ledger as llm_ledger_module
from app.config import Settings
from app.data.db import Base
from app.data.models import LLMCall
from app.services import model_provider
from app.services.model_provider import agenerate_text, agenerate_text_batch


@pytest.fixture()
def isolated_ledger_db(monkeypatch: pytest.MonkeyPatch):
    """Point the LLM ledger at a fresh in-memory SQLite DB -- mirrors the
    fixture of the same name in tests/test_model_provider.py/test_llm_ledger.py,
    duplicated here rather than imported so this file has no test-module
    cross-dependency."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(llm_ledger_module, "SessionLocal", test_session_local)
    return test_session_local


def _all_calls(session_factory) -> list[LLMCall]:
    session = session_factory()
    try:
        return list(session.scalars(select(LLMCall)).all())
    finally:
        session.close()


def _ollama_response(content: str = "ok") -> httpx.Response:
    return httpx.Response(
        200,
        json={"message": {"content": content}, "prompt_eval_count": 3, "eval_count": 2},
    )


def _no_backoff_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every retry test below exercises real retry *logic*, not real
    wall-clock delay -- mirrors tests/test_usda_client.py's `sleep=lambda _:
    None` pattern for the sync client, just for the async backoff helper."""
    monkeypatch.setattr(model_provider, "_async_backoff_seconds", lambda attempt: 0.0)


# ---------------------------------------------------------------------------
# 1. Concurrency bound is respected.
# ---------------------------------------------------------------------------


def test_agenerate_text_batch_respects_concurrency_bound(isolated_ledger_db) -> None:
    in_flight = {"current": 0, "max": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        in_flight["current"] += 1
        in_flight["max"] = max(in_flight["max"], in_flight["current"])
        # Yield control so other scheduled tasks actually get a chance to
        # start concurrently while this one is "in flight" -- without this,
        # a single-threaded event loop could run every handler to
        # completion one at a time and the bound would never be exercised.
        await asyncio.sleep(0.02)
        in_flight["current"] -= 1
        return _ollama_response()

    async def _run() -> tuple[list[str | None], list[str]]:
        settings = Settings(MODEL_PROVIDER="ollama")
        async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            return await agenerate_text_batch(
                "ollama",
                [f"prompt {i}" for i in range(8)],
                settings,
                purpose="test_concurrency_bound",
                max_concurrency=2,
                async_client=async_client,
            )
        finally:
            await async_client.aclose()

    results, errors = asyncio.run(_run())

    assert errors == []
    assert results == ["ok"] * 8
    assert in_flight["max"] <= 2

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 8
    assert all(row.success for row in rows)


# ---------------------------------------------------------------------------
# 2. A 429 is retried (with backoff) and then succeeds.
# ---------------------------------------------------------------------------


def test_agenerate_text_retries_429_then_succeeds(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_backoff_delay(monkeypatch)
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(429, json={"error": "rate limited"})
        return _ollama_response("recovered")

    async def _run() -> str:
        settings = Settings(MODEL_PROVIDER="ollama")
        async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            return await agenerate_text(
                "ollama", "a prompt", settings, purpose="test_429_retry", async_client=async_client
            )
        finally:
            await async_client.aclose()

    text = asyncio.run(_run())

    assert text == "recovered"
    assert calls["n"] == 2

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].success is True
    assert rows[0].retries == 1


def test_agenerate_text_gives_up_after_retry_budget_on_persistent_429(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_backoff_delay(monkeypatch)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    async def _run() -> None:
        settings = Settings(MODEL_PROVIDER="ollama")
        async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            await agenerate_text(
                "ollama",
                "a prompt",
                settings,
                purpose="test_429_exhausted",
                async_client=async_client,
            )
        finally:
            await async_client.aclose()

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_run())

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].success is False
    # 2 retries (3 attempts total) -- see model_provider._ASYNC_HTTP_MAX_RETRIES.
    assert rows[0].retries == model_provider._ASYNC_HTTP_MAX_RETRIES


# ---------------------------------------------------------------------------
# 3. A timeout surfaces as a clean errors[] entry, not an unhandled crash.
# ---------------------------------------------------------------------------


def test_agenerate_text_batch_timeout_surfaces_as_clean_error_entry(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_backoff_delay(monkeypatch)

    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout", request=request)

    async def _run() -> tuple[list[str | None], list[str]]:
        settings = Settings(MODEL_PROVIDER="ollama")
        async_client = httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler))
        try:
            return await agenerate_text_batch(
                "ollama",
                ["a prompt"],
                settings,
                purpose="test_timeout",
                max_concurrency=2,
                async_client=async_client,
            )
        finally:
            await async_client.aclose()

    results, errors = asyncio.run(_run())

    # A clean, collected error -- never a raised exception out of
    # agenerate_text_batch -- matching this codebase's existing
    # errors:list[str] partial-failure convention.
    assert results == [None]
    assert len(errors) == 1
    assert "ollama" in errors[0]
    assert "timeout" in errors[0].lower()

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].success is False
    assert rows[0].retries == model_provider._ASYNC_HTTP_MAX_RETRIES


def test_agenerate_text_batch_one_failure_does_not_take_down_the_whole_batch(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mix of a good prompt and a permanently-timing-out one -- the good
    one's result must still come back, in the right index position, and the
    bad one must land in `errors` rather than losing the whole batch."""
    _no_backoff_delay(monkeypatch)

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = request.content.decode("utf-8")
        if "boom" in payload:
            raise httpx.TimeoutException("simulated timeout", request=request)
        return _ollama_response("fine")

    async def _run() -> tuple[list[str | None], list[str]]:
        settings = Settings(MODEL_PROVIDER="ollama")
        async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            return await agenerate_text_batch(
                "ollama",
                ["good prompt", "boom prompt", "another good prompt"],
                settings,
                purpose="test_partial_failure",
                max_concurrency=3,
                async_client=async_client,
            )
        finally:
            await async_client.aclose()

    results, errors = asyncio.run(_run())

    assert results[0] == "fine"
    assert results[1] is None
    assert results[2] == "fine"
    assert len(errors) == 1
    assert "prompt 1" in errors[0]
