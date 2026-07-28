"""Response-level cache for `app.services.model_provider.generate_
structured` calls (ROADMAP.md Phase 2, Step 2.3).

Why this exists: Step 2.1 gave every structured LLM call a schema-validated
chokepoint; some purposes going through it (e.g. "get detailed
instructions" for the same recipe) are asked with byte-identical prompts
repeatedly and gain nothing from a fresh call each time. This module caches
the exact, already-validated JSON response for those purposes -- never a
post-processed decision -- so a downstream logic change never needs a
cache-invalidation pass (see `app.services.nutrition_cache.FdcCache`'s
docstring for the same "cache facts, not decisions" principle this mirrors).

The LLM never decides a safety or nutrition outcome here or anywhere this
cache is used; a cache hit or miss only changes whether a provider is
re-asked the exact same non-safety-critical phrasing/generation question,
never how a downstream allergy/diet/nutrition decision is made.

Only `app.services.model_provider.generate_structured` calls into this
module; nothing else should read or write `LLMCacheEntry` rows directly.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from app.data.db import SessionLocal
from app.data.models import LLMCacheEntry
from app.utils.logging import get_logger

logger = get_logger(__name__)

# TTL per `purpose` tag -- see the three call sites in
# app.services.model_provider (`detailed_instructions`, `vision_extract`)
# and app.services.recipe_generation_service (`recipe_generation`). `None`
# means "never cache this purpose": `generate_structured` skips both the
# cache read and the cache write entirely for it (see its `ttl_for_purpose`
# call site) -- this is deliberately NOT the same as "TTL of zero seconds",
# which would still pay the cost of a cache lookup/write for no benefit.
#
# - detailed_instructions -> 30 days (ROADMAP-specified). The prompt is a
#   deterministic function of (title, ingredients, instructions, servings,
#   cuisine) with no per-user or per-request variation baked in
#   (`model_provider._build_detailed_instructions_prompt`), so the same
#   recipe really does deserve the same rewritten steps back for a month;
#   nothing about *this* recipe's instructions goes stale that fast.
# - recipe_generation -> no cache, ever (ROADMAP-specified: "keep novelty").
#   This is the one purpose where a repeat call MUST look different --
#   caching it would work directly against the feature's point.
# - vision_extract -> no cache, but for a DIFFERENT reason than novelty:
#   the cache key below (provider, model, purpose, prompt, schema) does not
#   include the uploaded image's bytes -- `VISION_PROMPT` is a fixed
#   constant, byte-identical on every call regardless of which photo was
#   uploaded. Caching this purpose would risk returning one photo's
#   extracted inventory for an entirely different photo uploaded within the
#   TTL window -- a correctness bug feeding into inventory data, not a
#   performance tradeoff. (This alone isn't a safety decision --
#   constraint_engine still runs deterministically downstream of whatever
#   inventory the user confirms -- but it is wrong data, and avoiding it is
#   cheaper than widening the cache key to hash image bytes, which is out
#   of scope for this step.) `generate_structured` also independently
#   refuses to cache ANY call with `image_path` set, regardless of what's
#   in this table, as a second, structural guard against exactly this --
#   see its docstring.
#
# An unrecognized purpose (not a key in this dict at all -- e.g. a future
# call site, or the ad hoc tags a few tests pass) is treated the same as an
# explicit `None` entry by `ttl_for_purpose` below: fail closed to "don't
# cache" rather than assuming a new purpose is safe to cache.
TTL_BY_PURPOSE: dict[str, timedelta | None] = {
    "detailed_instructions": timedelta(days=30),
    "recipe_generation": None,
    "vision_extract": None,
}


def ttl_for_purpose(purpose: str) -> timedelta | None:
    """TTL for `purpose`, or `None` if it must never be cached (either an
    explicit `None` entry in `TTL_BY_PURPOSE`, or a purpose not listed
    there at all -- both fail closed to "don't cache")."""
    return TTL_BY_PURPOSE.get(purpose)


def build_cache_key(
    provider: str, model: str, purpose: str, prompt: str, schema: type[BaseModel]
) -> str:
    """SHA256 hex digest of (provider, model, purpose, canonicalized
    prompt, canonicalized schema) -- the cache key ROADMAP 2.3 specifies.

    "Canonicalized" matters most for the schema half: this hashes
    `schema.model_json_schema()` (a plain dict) re-serialized via
    `json.dumps(..., sort_keys=True)`, deliberately NOT Python's `repr()`
    of the schema class or dict. Dict key order and `repr()` output are not
    guaranteed stable across separate interpreter runs/processes (this
    cache is read back by a LATER process than the one that wrote it, e.g.
    after a redeploy) -- sorted-key JSON is the deterministic, cross-
    process-stable representation this key needs. The prompt itself needs
    no such treatment: it is already a plain string, and byte-for-byte
    equality is exactly what "same title/ingredients/instructions/
    servings/cuisine" prompts already produce via
    `model_provider._build_detailed_instructions_prompt`'s deterministic
    string formatting -- there is no dict/object identity ambiguity to
    canonicalize away for it.
    """
    schema_json = json.dumps(schema.model_json_schema(), sort_keys=True)
    # U+241F (SYMBOL FOR INFORMATION SEPARATOR ONE) as a field delimiter --
    # never appears in a provider name, model name, purpose tag, or JSON
    # Schema dump, so this join is unambiguous without needing a length-
    # prefixed or otherwise escaped encoding.
    payload = "␟".join([provider, model, purpose, prompt, schema_json])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite round-trips a `DateTime(timezone=True)` column as a naive
    datetime (no tzinfo) even though it was written timezone-aware --
    Postgres does not have this quirk, but normalizing defensively here
    keeps this module correct on both backends without a dialect branch."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def get_cached_response(
    cache_key: str, schema: type[BaseModel], *, now: datetime | None = None
) -> BaseModel | None:
    """The cached, schema-validated response for `cache_key`, or `None` on
    a miss -- either no entry exists, or one exists but is past its
    `expires_at` (an expired entry is ALWAYS treated as a miss, never
    served stale; it is left in place on disk for the next `store_response`
    call to overwrite rather than deleted here, keeping this a read-only
    operation on the happy path).

    `now` is test-injectable (mirrors `app.services.rate_limiter.
    RateLimiter.allow`'s injectable `now` parameter) -- defaults to the
    real current time.

    A DB read failure (e.g. no table yet on a fresh install that hasn't run
    `init_db()`) is also treated as a miss, logged and swallowed rather than
    raised -- a broken cache read must never break the real LLM call it's
    trying to short-circuit, same contract as `store_response`/
    `app.observability.llm_ledger.record_llm_call`.
    """
    current = now or datetime.now(UTC)
    try:
        db = SessionLocal()
        try:
            entry = (
                db.query(LLMCacheEntry)
                .filter(LLMCacheEntry.cache_key == cache_key)
                .one_or_none()
            )
        finally:
            db.close()
    except Exception:  # pragma: no cover - a broken cache read must never break the real call
        logger.exception(
            "Failed to read LLM cache entry for key %s; treating as a miss.", cache_key
        )
        return None

    if entry is None:
        return None
    if _as_aware_utc(entry.expires_at) <= current:
        return None

    try:
        payload = json.loads(entry.response_json)
        return schema.model_validate(payload)
    except Exception:
        # A cached row that no longer parses/validates against `schema`
        # (e.g. the schema shape changed) is a miss, not a crash -- the
        # cache key already changes when the schema changes (it's part of
        # the hash), so this branch should be unreachable in practice; it
        # exists as a fail-safe rather than a load-bearing path.
        logger.warning(
            "Cached LLM response for key %s failed to validate against %s; treating as a miss.",
            cache_key,
            schema.__name__,
        )
        return None


def store_response(
    cache_key: str,
    provider: str,
    model: str,
    purpose: str,
    result: BaseModel,
    *,
    now: datetime | None = None,
) -> None:
    """Write (or overwrite) the cache entry for `cache_key` with `result`'s
    validated JSON. Callers must have already confirmed
    `ttl_for_purpose(purpose) is not None`; this function does not re-check
    it (it silently no-ops with no TTL configured) so `generate_structured`
    remains the single place that decides WHETHER to cache a given call --
    this function only decides WHAT gets written once that decision has
    already been made.

    Persistence failures are logged and swallowed, never raised -- a broken
    cache write must not take down the real LLM call whose result it's
    trying to cache, matching `app.observability.llm_ledger.
    record_llm_call`'s same contract.
    """
    ttl = ttl_for_purpose(purpose)
    if ttl is None:
        return

    current = now or datetime.now(UTC)
    expires_at = current + ttl
    response_json = result.model_dump_json()

    try:
        db = SessionLocal()
        try:
            existing = (
                db.query(LLMCacheEntry)
                .filter(LLMCacheEntry.cache_key == cache_key)
                .one_or_none()
            )
            if existing is not None:
                existing.provider = provider
                existing.model = model
                existing.purpose = purpose
                existing.response_json = response_json
                existing.created_at = current
                existing.expires_at = expires_at
            else:
                db.add(
                    LLMCacheEntry(
                        cache_key=cache_key,
                        provider=provider,
                        model=model,
                        purpose=purpose,
                        response_json=response_json,
                        created_at=current,
                        expires_at=expires_at,
                    )
                )
            db.commit()
        finally:
            db.close()
    except Exception:  # pragma: no cover - persistence must never break a real LLM call
        logger.exception("Failed to persist LLM cache entry (purpose=%s)", purpose)
