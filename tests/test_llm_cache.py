"""ROADMAP.md Phase 2, Step 2.3 -- response-level cache for `generate_
structured` calls.

Covers:
- `llm_cache.build_cache_key` determinism and sensitivity to each input
  (provider, model, purpose, prompt, schema);
- `llm_cache.ttl_for_purpose`'s policy (`detailed_instructions` = 30 days,
  `recipe_generation`/`vision_extract` = never cached, unknown purposes =
  never cached);
- `get_cached_response`/`store_response` round-trip, miss, and TTL-expiry
  behavior directly against the cache table;
- `generate_structured`'s wiring: a cache hit skips the real provider call
  entirely and records a `cache_hit=True, cost_usd=0` ledger row; a miss
  falls through and populates the cache; `recipe_generation` and a vision
  call (`image_path` set) are never cached even when otherwise eligible;
- the `LLM_CACHE_ENABLED=False` kill switch disables both the read AND the
  write side, not just reads.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.observability.llm_ledger as llm_ledger_module
from app.config import Settings
from app.data.db import Base
from app.data.models import LLMCacheEntry, LLMCall
from app.services import llm_cache, model_provider
from app.services.model_provider import (
    DetailedInstructions,
    _build_detailed_instructions_prompt,
    _model_for,
    generate_structured,
)


class _SampleStructured(BaseModel):
    """A minimal schema for exercising the cache independent of any real
    production schema -- mirrors tests/test_model_provider.py's schema of
    the same name/purpose."""

    name: str
    count: int = 0


@pytest.fixture()
def isolated_llm_db(monkeypatch: pytest.MonkeyPatch):
    """Fresh in-memory SQLite DB shared by both the LLM ledger
    (`app.observability.llm_ledger`) and the LLM cache
    (`app.services.llm_cache`) -- mirrors tests/test_model_provider.py's
    `isolated_ledger_db` fixture, extended to also isolate the cache table
    so these tests never read or write the developer's real macrochef.db.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(llm_ledger_module, "SessionLocal", test_session_local)
    monkeypatch.setattr(llm_cache, "SessionLocal", test_session_local)
    return test_session_local


def _all_calls(session_factory) -> list[LLMCall]:
    session = session_factory()
    try:
        return list(session.scalars(select(LLMCall)).all())
    finally:
        session.close()


def _all_cache_entries(session_factory) -> list[LLMCacheEntry]:
    session = session_factory()
    try:
        return list(session.scalars(select(LLMCacheEntry)).all())
    finally:
        session.close()


# ---------------------------------------------------------------------------
# build_cache_key
# ---------------------------------------------------------------------------


def test_build_cache_key_is_deterministic_across_calls() -> None:
    key1 = llm_cache.build_cache_key(
        "gemini", "gemini-2.5-flash", "detailed_instructions", "same prompt", _SampleStructured
    )
    key2 = llm_cache.build_cache_key(
        "gemini", "gemini-2.5-flash", "detailed_instructions", "same prompt", _SampleStructured
    )

    assert key1 == key2
    assert len(key1) == 64  # sha256 hex digest length


def test_build_cache_key_differs_when_any_input_differs() -> None:
    base_key = llm_cache.build_cache_key(
        "gemini", "gemini-2.5-flash", "detailed_instructions", "prompt text", _SampleStructured
    )

    class _OtherSchema(BaseModel):
        other_field: str

    assert (
        llm_cache.build_cache_key(
            "openai", "gemini-2.5-flash", "detailed_instructions", "prompt text", _SampleStructured
        )
        != base_key
    )
    assert (
        llm_cache.build_cache_key(
            "gemini", "gemini-3-flash", "detailed_instructions", "prompt text", _SampleStructured
        )
        != base_key
    )
    assert (
        llm_cache.build_cache_key(
            "gemini", "gemini-2.5-flash", "recipe_generation", "prompt text", _SampleStructured
        )
        != base_key
    )
    assert (
        llm_cache.build_cache_key(
            "gemini",
            "gemini-2.5-flash",
            "detailed_instructions",
            "different prompt",
            _SampleStructured,
        )
        != base_key
    )
    assert (
        llm_cache.build_cache_key(
            "gemini", "gemini-2.5-flash", "detailed_instructions", "prompt text", _OtherSchema
        )
        != base_key
    )


# ---------------------------------------------------------------------------
# ttl_for_purpose policy
# ---------------------------------------------------------------------------


def test_ttl_for_purpose_matches_the_roadmap_policy() -> None:
    assert llm_cache.ttl_for_purpose("detailed_instructions") == timedelta(days=30)
    assert llm_cache.ttl_for_purpose("recipe_generation") is None
    assert llm_cache.ttl_for_purpose("vision_extract") is None
    # An unrecognized purpose fails closed to "don't cache", same as an
    # explicit None entry.
    assert llm_cache.ttl_for_purpose("some_future_purpose_not_yet_listed") is None


# ---------------------------------------------------------------------------
# get_cached_response / store_response -- direct against the cache table.
# ---------------------------------------------------------------------------


def test_store_and_get_cached_response_round_trips(isolated_llm_db) -> None:
    key = llm_cache.build_cache_key(
        "gemini", "gemini-2.5-flash", "detailed_instructions", "p", DetailedInstructions
    )
    llm_cache.store_response(
        key,
        "gemini",
        "gemini-2.5-flash",
        "detailed_instructions",
        DetailedInstructions(steps=["a", "b"]),
    )

    cached = llm_cache.get_cached_response(key, DetailedInstructions)

    assert cached == DetailedInstructions(steps=["a", "b"])


def test_get_cached_response_returns_none_on_a_true_miss(isolated_llm_db) -> None:
    missing_key = "a-key-that-was-never-written"
    assert llm_cache.get_cached_response(missing_key, DetailedInstructions) is None


def test_store_response_no_ops_for_a_purpose_with_no_ttl(isolated_llm_db) -> None:
    key = llm_cache.build_cache_key(
        "gemini", "gemini-2.5-flash", "recipe_generation", "p", _SampleStructured
    )
    llm_cache.store_response(
        key, "gemini", "gemini-2.5-flash", "recipe_generation", _SampleStructured(name="a")
    )

    assert llm_cache.get_cached_response(key, _SampleStructured) is None
    assert _all_cache_entries(isolated_llm_db) == []


def test_get_cached_response_treats_an_expired_entry_as_a_miss_not_stale(isolated_llm_db) -> None:
    """TTL expiry, using `store_response`/`get_cached_response`'s injectable
    `now` (mirrors app.services.rate_limiter.RateLimiter.allow's injectable
    `now` convention) rather than a real sleep."""
    key = llm_cache.build_cache_key(
        "gemini", "gemini-2.5-flash", "detailed_instructions", "p", DetailedInstructions
    )
    written_at = datetime(2020, 1, 1, tzinfo=UTC)
    llm_cache.store_response(
        key,
        "gemini",
        "gemini-2.5-flash",
        "detailed_instructions",
        DetailedInstructions(steps=["old step"]),
        now=written_at,
    )

    # Still valid a day later -- well within the 30-day TTL.
    assert (
        llm_cache.get_cached_response(key, DetailedInstructions, now=written_at + timedelta(days=1))
        is not None
    )
    # Expired once 31 days have passed.
    expired_now = written_at + timedelta(days=31)
    assert llm_cache.get_cached_response(key, DetailedInstructions, now=expired_now) is None


# ---------------------------------------------------------------------------
# generate_structured wiring: hit avoids the real provider call, miss
# populates the cache, recipe_generation/vision are never cached, and the
# LLM_CACHE_ENABLED kill switch disables both directions.
# ---------------------------------------------------------------------------


def test_generate_structured_second_identical_call_serves_from_cache(
    isolated_llm_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance criterion: a second identical "detailed instructions"
    request serves from cache -- the real provider is called exactly once,
    the second call's ledger row has cache_hit=True and cost_usd=0."""
    settings = Settings(MODEL_PROVIDER="ollama")
    call_count = {"n": 0}

    def _fake_post(url, headers=None, json=None, timeout=None):
        call_count["n"] += 1
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": '{"steps": ["Preheat oven.", "Roast."]}'}},
        )

    monkeypatch.setattr(model_provider.requests, "post", _fake_post)

    prompt = _build_detailed_instructions_prompt(
        title="Toast",
        ingredients=["bread"],
        instructions=["Toast it."],
        servings=None,
        cuisine=None,
    )

    first = generate_structured(
        "ollama", prompt, DetailedInstructions, settings, purpose="detailed_instructions"
    )
    assert call_count["n"] == 1
    assert first.steps == ["Preheat oven.", "Roast."]
    assert len(_all_cache_entries(isolated_llm_db)) == 1

    second = generate_structured(
        "ollama", prompt, DetailedInstructions, settings, purpose="detailed_instructions"
    )
    assert call_count["n"] == 1  # NOT called again -- served from cache
    assert second == first

    rows = _all_calls(isolated_llm_db)
    assert len(rows) == 2
    assert rows[0].cache_hit is False
    assert rows[1].cache_hit is True
    assert rows[1].success is True
    assert rows[1].cost_usd == 0.0
    assert rows[1].prompt_tokens == 0
    assert rows[1].completion_tokens == 0
    assert rows[1].provider == "ollama"
    assert rows[1].purpose == "detailed_instructions"


def test_cache_hit_never_invokes_the_provider_generator_at_all(
    isolated_llm_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Directly seeds the cache (bypassing generate_structured) and swaps
    in a generator that raises if it's ever called -- the strongest
    possible proof that a hit skips the real call entirely, not just that
    the HTTP mock happens not to have been hit again."""
    settings = Settings(MODEL_PROVIDER="ollama")
    prompt = "a prompt"
    model = _model_for(settings, "ollama", "chat")
    cache_key = llm_cache.build_cache_key(
        "ollama", model, "detailed_instructions", prompt, DetailedInstructions
    )
    llm_cache.store_response(
        cache_key, "ollama", model, "detailed_instructions", DetailedInstructions(steps=["cached"])
    )

    def _raising_generator(*args, **kwargs):
        raise AssertionError("provider generator must not be called on a cache hit")

    monkeypatch.setitem(model_provider._STRUCTURED_GENERATORS, "ollama", _raising_generator)

    result = generate_structured(
        "ollama", prompt, DetailedInstructions, settings, purpose="detailed_instructions"
    )

    assert result.steps == ["cached"]
    rows = _all_calls(isolated_llm_db)
    assert len(rows) == 1
    assert rows[0].cache_hit is True


def test_recipe_generation_purpose_is_never_cached(
    isolated_llm_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ROADMAP-specified: recipe_generation keeps novelty -- never served
    from cache, and never written to it, even for byte-identical prompts."""
    settings = Settings(MODEL_PROVIDER="ollama")
    call_count = {"n": 0}

    def _fake_post(url, headers=None, json=None, timeout=None):
        call_count["n"] += 1
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": '{"name": "a", "count": 1}'}},
        )

    monkeypatch.setattr(model_provider.requests, "post", _fake_post)

    generate_structured(
        "ollama", "same prompt", _SampleStructured, settings, purpose="recipe_generation"
    )
    generate_structured(
        "ollama", "same prompt", _SampleStructured, settings, purpose="recipe_generation"
    )

    assert call_count["n"] == 2  # both calls hit the real provider
    assert _all_cache_entries(isolated_llm_db) == []


def test_vision_calls_are_never_cached_even_if_the_purpose_has_a_ttl(
    isolated_llm_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Structural guard independent of TTL_BY_PURPOSE: generate_structured
    refuses to cache ANY call with `image_path` set, regardless of what a
    purpose's TTL policy says -- proven here by forcing a fake purpose to
    have a TTL and confirming a vision-shaped call still writes nothing."""
    settings = Settings(MODEL_PROVIDER="mock")
    monkeypatch.setitem(llm_cache.TTL_BY_PURPOSE, "fake_vision_purpose", timedelta(days=1))

    generate_structured(
        "mock",
        "a prompt",
        _SampleStructured,
        settings,
        purpose="fake_vision_purpose",
        image_path="not/a/real/path.jpg",
    )

    assert _all_cache_entries(isolated_llm_db) == []


def test_expired_cache_entry_falls_through_to_a_real_call_via_generate_structured(
    isolated_llm_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(MODEL_PROVIDER="ollama")
    call_count = {"n": 0}

    def _fake_post(url, headers=None, json=None, timeout=None):
        call_count["n"] += 1
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": '{"steps": ["Fresh step."]}'}},
        )

    monkeypatch.setattr(model_provider.requests, "post", _fake_post)

    prompt = _build_detailed_instructions_prompt(
        title="Toast",
        ingredients=["bread"],
        instructions=["Toast it."],
        servings=None,
        cuisine=None,
    )
    model = _model_for(settings, "ollama", "chat")
    cache_key = llm_cache.build_cache_key(
        "ollama", model, "detailed_instructions", prompt, DetailedInstructions
    )
    stale_now = datetime.now(UTC) - timedelta(days=40)  # older than the 30-day TTL
    llm_cache.store_response(
        cache_key,
        "ollama",
        model,
        "detailed_instructions",
        DetailedInstructions(steps=["Stale cached step."]),
        now=stale_now,
    )

    result = generate_structured(
        "ollama", prompt, DetailedInstructions, settings, purpose="detailed_instructions"
    )

    assert call_count["n"] == 1  # provider WAS called -- an expired entry is a miss
    assert result.steps == ["Fresh step."]
    rows = _all_calls(isolated_llm_db)
    assert rows[-1].cache_hit is False


def test_llm_cache_enabled_false_disables_both_read_and_write(
    isolated_llm_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The kill switch: with LLM_CACHE_ENABLED=False, generate_structured
    behaves exactly as if the cache didn't exist -- BOTH calls hit the real
    provider (no read), and no cache row is ever written (no write)."""
    settings = Settings(MODEL_PROVIDER="ollama", LLM_CACHE_ENABLED=False)
    call_count = {"n": 0}

    def _fake_post(url, headers=None, json=None, timeout=None):
        call_count["n"] += 1
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": '{"steps": ["Step one."]}'}},
        )

    monkeypatch.setattr(model_provider.requests, "post", _fake_post)

    prompt = _build_detailed_instructions_prompt(
        title="Toast",
        ingredients=["bread"],
        instructions=["Toast it."],
        servings=None,
        cuisine=None,
    )

    generate_structured(
        "ollama", prompt, DetailedInstructions, settings, purpose="detailed_instructions"
    )
    generate_structured(
        "ollama", prompt, DetailedInstructions, settings, purpose="detailed_instructions"
    )

    assert call_count["n"] == 2  # no cache read: both calls hit the provider

    rows = _all_calls(isolated_llm_db)
    assert len(rows) == 2
    assert all(row.cache_hit is False for row in rows)

    # No cache write either -- proves this isn't just a disabled read path.
    assert _all_cache_entries(isolated_llm_db) == []
