"""LLM call ledger: tokens, cost, latency, provider (ROADMAP.md Phase 1,
Step 1.2).

Why this exists: Step 1.1's `RunEvent` stream tells you WHAT graph nodes
ran and HOW LONG they took, but not what they cost. This module is the
single place a provider call (real or mock) gets turned into (a) a
persisted `LLMCall` row keyed by `run_id`/`user_id` and (b) a mirrored
`RunEvent` on the same sink Step 1.1 already wired up, so the event stream
and the durable ledger never drift apart.

The only caller today is `app.services.model_provider` (`_generate_text`
and `_extract_inventory`, the two provider-HTTP choke points, plus their
mock-provider short-circuit branches) -- see that module's `record_llm_call`
call sites for the purpose tags in use (`detailed_instructions`,
`vision_extract`, `recipe_generation`).

Nothing here decides an allergy/diet outcome or computes nutrition -- see
app.services.constraint_engine for that. This module only measures and
prices calls that already happened.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select

from app.data.db import SessionLocal
from app.data.models import LLMCall
from app.observability.events import RunEvent, get_default_sink, get_run_id, peek_user_id
from app.schemas.admin import LLMUsageAggregate, LLMUsageResponse, LLMUsageTotals
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Best-effort $ / 1,000,000 tokens as (prompt_price, completion_price). This
# is NOT billing-accurate -- provider list prices change often and this
# table will drift out of date; it exists to give a rough cost SIGNAL on
# GET /admin/llm-usage, not an invoice. Covers this repo's DEFAULT_MODELS
# (app.services.model_provider) for the three hosted providers; a model not
# listed here costs $0 (logged at debug) rather than raising, since an
# unpriced model must never block the actual LLM call it's attached to.
PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gemini-2.5-flash": (0.30, 2.50),
    "claude-sonnet-4-5": (3.00, 15.00),
}

# Local/no-op providers are always free regardless of model name -- there is
# no list price to look up for a self-hosted Ollama model or the mock
# provider, and guessing one would be worse than a clearly-labeled $0.
FREE_PROVIDERS = {"ollama", "mock"}


def estimate_tokens(text: str) -> int:
    """Crude fallback token estimate (~4 chars/token), used only when a
    provider response doesn't carry real usage metadata. Never used when
    the provider gave us a real count."""
    return max(0, len(text) // 4)


def _price_per_mtok(provider: str, model: str) -> tuple[float, float]:
    if provider in FREE_PROVIDERS:
        return (0.0, 0.0)
    prices = PRICE_PER_MTOK.get(model)
    if prices is None:
        logger.debug(
            "No PRICE_PER_MTOK entry for model %r (provider %r); costing this call as $0.",
            model,
            provider,
        )
        return (0.0, 0.0)
    return prices


def _cost_usd(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prompt_price, completion_price = _price_per_mtok(provider, model)
    prompt_cost = (prompt_tokens / 1_000_000) * prompt_price
    completion_cost = (completion_tokens / 1_000_000) * completion_price
    return prompt_cost + completion_cost


def record_llm_call(
    *,
    provider: str,
    model: str,
    purpose: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: float,
    success: bool,
    fallback_used: bool,
    prompt_text: str = "",
    completion_text: str = "",
) -> None:
    """Persist one `llm_calls` row and mirror it onto the RunEvent sink.

    `prompt_tokens`/`completion_tokens` should be the REAL counts read off
    the provider's response when available; pass `None` for whichever one
    the provider didn't report and this function estimates it from
    `prompt_text`/`completion_text` via `estimate_tokens` instead (never
    the other way around -- a real count is never overridden by the
    estimate).

    `run_id` comes from `app.observability.events.get_run_id()` (minting
    one if this happens outside any traced context, e.g. a script) and
    `user_id` from `peek_user_id()` (may legitimately be `None` -- see that
    function's docstring). Persistence failures are logged and swallowed,
    never raised: a broken ledger write must not take down the real LLM
    call it's instrumenting.
    """
    resolved_prompt_tokens = (
        prompt_tokens if prompt_tokens is not None else estimate_tokens(prompt_text)
    )
    resolved_completion_tokens = (
        completion_tokens if completion_tokens is not None else estimate_tokens(completion_text)
    )
    cost_usd = _cost_usd(provider, model, resolved_prompt_tokens, resolved_completion_tokens)
    run_id = get_run_id()
    user_id = peek_user_id()

    try:
        db = SessionLocal()
        try:
            db.add(
                LLMCall(
                    run_id=run_id,
                    user_id=user_id,
                    provider=provider,
                    model=model,
                    purpose=purpose,
                    prompt_tokens=resolved_prompt_tokens,
                    completion_tokens=resolved_completion_tokens,
                    latency_ms=latency_ms,
                    success=success,
                    fallback_used=fallback_used,
                    cost_usd=cost_usd,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception:  # pragma: no cover - persistence must never break a real LLM call
        logger.exception(
            "Failed to persist LLM ledger row (provider=%s purpose=%s)", provider, purpose
        )

    # Mirrors the durable row onto the same event stream Step 1.1 wired up
    # -- deliberately excludes user_id (see app.observability.events'
    # module docstring: RunEvent.payload must never carry anything
    # PII-shaped; user_id only ever lands in the SQL row above).
    get_default_sink().emit(
        RunEvent(
            run_id=run_id,
            node=f"llm_call:{purpose}",
            status="finished" if success else "failed",
            elapsed_ms=latency_ms,
            summary=(
                f"LLM call ({purpose}) via {provider}/{model}: "
                f"{resolved_prompt_tokens}+{resolved_completion_tokens} tokens, "
                f"${cost_usd:.5f}."
            ),
            payload={
                "provider": provider,
                "model": model,
                "purpose": purpose,
                "prompt_tokens": resolved_prompt_tokens,
                "completion_tokens": resolved_completion_tokens,
                "cost_usd": cost_usd,
                "success": success,
                "fallback_used": fallback_used,
            },
        )
    )


def build_usage_response(days: int) -> LLMUsageResponse:
    """Aggregate `llm_calls` rows from the last `days` days, grouped by
    (day, provider, model, purpose) -- the query GET /admin/llm-usage
    serves. Pulled out of the route so it's directly unit-testable without
    spinning up a TestClient."""
    since = datetime.now(UTC) - timedelta(days=days)

    db = SessionLocal()
    try:
        stmt = (
            select(
                func.date(LLMCall.created_at).label("day"),
                LLMCall.provider,
                LLMCall.model,
                LLMCall.purpose,
                func.count(LLMCall.id).label("calls"),
                func.coalesce(func.sum(LLMCall.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(LLMCall.completion_tokens), 0).label("completion_tokens"),
                func.coalesce(func.sum(LLMCall.cost_usd), 0.0).label("cost_usd"),
                func.sum(case((LLMCall.success.is_(True), 1), else_=0)).label("success_count"),
                func.sum(case((LLMCall.success.is_(False), 1), else_=0)).label("failure_count"),
                func.sum(case((LLMCall.fallback_used.is_(True), 1), else_=0)).label(
                    "fallback_count"
                ),
            )
            .where(LLMCall.created_at >= since)
            .group_by(
                func.date(LLMCall.created_at), LLMCall.provider, LLMCall.model, LLMCall.purpose
            )
            .order_by(func.date(LLMCall.created_at).desc(), LLMCall.provider, LLMCall.purpose)
        )
        result_rows = db.execute(stmt).all()
    finally:
        db.close()

    rows: list[LLMUsageAggregate] = []
    total_calls = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_cost_usd = 0.0
    for row in result_rows:
        prompt_tokens = int(row.prompt_tokens or 0)
        completion_tokens = int(row.completion_tokens or 0)
        cost = float(row.cost_usd or 0.0)
        day_value = row.day if isinstance(row.day, str) else str(row.day)
        rows.append(
            LLMUsageAggregate(
                day=day_value,
                provider=row.provider,
                model=row.model,
                purpose=row.purpose,
                calls=int(row.calls),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cost_usd=cost,
                success_count=int(row.success_count or 0),
                failure_count=int(row.failure_count or 0),
                fallback_count=int(row.fallback_count or 0),
            )
        )
        total_calls += int(row.calls)
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens
        total_cost_usd += cost

    return LLMUsageResponse(
        days=days,
        since=since,
        totals=LLMUsageTotals(
            calls=total_calls,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            total_tokens=total_prompt_tokens + total_completion_tokens,
            cost_usd=total_cost_usd,
        ),
        rows=rows,
    )
