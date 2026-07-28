from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.data.db import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    recipe_id: Mapped[str] = mapped_column(String(128), index=True)
    feedback_type: Mapped[str] = mapped_column(String(32), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class SessionMemory(Base):
    __tablename__ = "session_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    summary: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class UserSavedRecipe(Base):
    __tablename__ = "user_saved_recipes"
    # recipe_id is unique per user, NOT globally unique -- a global unique
    # constraint here previously meant a second user saving a recipe_id
    # already claimed by another user silently reassigned (stole) that row
    # (see RecipeLibraryRepository.save_recipe). Two different users are now
    # free to each have their own row for the "same" recipe_id.
    __table_args__ = (
        UniqueConstraint("user_id", "recipe_id", name="uq_user_saved_recipes_user_recipe"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    recipe_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(256), index=True)
    cuisine: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    meal_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    recipe_json: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class LLMCall(Base):
    """Append-only LLM call ledger (ROADMAP.md Phase 1, Step 1.2).

    One row per provider HTTP call made through
    `app.services.model_provider`'s `_generate_text`/`_extract_inventory`
    choke points -- including the mock-provider short-circuit branches
    (`provider="mock"`, zero tokens/cost), so ledger coverage is complete
    even when no real provider is configured. The single writer is
    `app.observability.llm_ledger.record_llm_call`; never hand-write to
    this table elsewhere.

    `run_id` correlates a row back to the `RunEvent` stream (Step 1.1);
    `user_id` is nullable because some call paths are genuinely
    unauthenticated (e.g. POST /inventory/extract) -- see
    `app.observability.events`'s user_id contextvar docstring. `cost_usd`
    is a best-effort estimate from the static `PRICE_PER_MTOK` table in
    `app.observability.llm_ledger`, not billing-accurate.

    `retries` and `parse_fallback` (ROADMAP.md Phase 2, Step 2.1) are only
    ever non-default for calls made through `app.services.model_provider.
    generate_structured` -- the plain `_generate_text` chokepoint always
    writes `retries=0, parse_fallback=False` (it has no repair loop and no
    JSON-mode fallback concept). `retries` is 0 (succeeded first try) or 1
    (needed the one-shot "repair loop" retry with validation errors
    appended to the prompt). `parse_fallback` is True only for Ollama/mock,
    which have no native structured-output mechanism and fall back to a
    JSON-mode prompt + regex/brace-scan extraction -- see
    `generate_structured`'s docstring and `_STRUCTURED_PARSE_FALLBACK`.
    """

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(128), index=True)
    purpose: Mapped[str] = mapped_column(String(64), index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[float] = mapped_column(Float)
    success: Mapped[bool] = mapped_column(Boolean)
    fallback_used: Mapped[bool] = mapped_column(Boolean)
    cost_usd: Mapped[float] = mapped_column(Float)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    parse_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, default=lambda: datetime.now(UTC)
    )


class SharedPlan(Base):
    """Roadmap item "Shareable plan URLs" (Phase 4 item 4, docs/ROADMAP.md).

    `id` is the opaque public share id (`secrets.token_urlsafe(16)`, minted
    by `app.services.share_service.create_share` -- NOT a sequential
    integer, NOT UUID4; matches the house pattern in
    `frontend/session_client.py`'s `secrets.token_urlsafe(32)` anonymous
    session id). `content` holds the server-BUILT public JSON (one of
    `app.schemas.share.PublicRecipe`/`PublicDayPlan`/`PublicBatchPlan`/
    `PublicWeeklyPlan`, serialized) -- never raw client bytes; see
    `app.services.share_service` for the allowlist mapping that produces it.

    `owner_user_id` mirrors `Feedback.user_id`/`SessionMemory.user_id`
    above: a private column that enables a FUTURE revoke-my-share-links
    feature (v1 ships create + anonymous view only, see docs/BACKLOG.md)
    without a migration. It is NEVER serialized into any GET response --
    `app.schemas.share.SharedPlanView` has no such field, and
    `app.api.routes_share.get_share` builds its response from `content` +
    `plan_type` only, never from the ORM row directly.
    """

    __tablename__ = "shared_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    plan_type: Mapped[str] = mapped_column(String(16), index=True)
    content: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[str] = mapped_column(String(128), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
