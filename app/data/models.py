from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.data.db import Base


class RateLimitHit(Base):
    """ROADMAP.md Phase 5, Step 5.2: one row per accepted rate-limit hit,
    backing `app.services.rate_limiter.PostgresRateLimiter` -- the shared,
    cross-replica counterpart to the in-memory `RateLimiter` that module
    docstrings elsewhere (that module, `docs/DEPLOY.md`) previously flagged
    as a `max-replicas=1` blocker. `key` matches the existing
    `"{bucket}:{user_id_or_caller_ip}"` convention `app.dependencies`'
    rate-limit dependencies already build -- unchanged by which backend is
    selected. `get_rate_limiter()` picks this backend only for a
    non-sqlite `DATABASE_URL`; sqlite deployments (today's only shipped
    topology) keep the in-memory limiter and never write here, so this
    table sits unused-but-harmless on sqlite.

    Rows are self-pruning: `PostgresRateLimiter.allow()` deletes every row
    for `key` older than the sliding window on each call, so the table
    never grows unbounded for an actively-used key -- there is no separate
    cleanup job."""

    __tablename__ = "rate_limit_hits"
    __table_args__ = (Index("ix_rate_limit_hits_key_hit_at", "key", "hit_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(256))
    hit_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


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

    `cache_hit` (ROADMAP.md Phase 2, Step 2.3) is True only for a
    `generate_structured` call served from `app.services.llm_cache` instead
    of a real provider call -- same "only ever non-default through
    generate_structured" rule as `retries`/`parse_fallback` above. A
    cache-hit row always has `prompt_tokens=0, completion_tokens=0,
    cost_usd=0.0, success=True` (see `generate_structured`'s cache-hit
    `record_llm_call` call site) -- the row exists so GET /admin/llm-usage
    can report cache-hit savings, not to double-count real usage.
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
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
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


class GraphRun(Base):
    """ROADMAP.md Phase 3, Step 3.2: `thread_id -> owner_user_id` ownership
    mapping for the checkpointed HITL recommend graph
    (`app.graph.builder.get_compiled_macrochef_graph`).

    This table is deliberately separate from LangGraph's own checkpoint
    tables (`checkpoints`, `checkpoint_writes`, ... -- created by
    `SqliteSaver`/`PostgresSaver.setup()`, kept outside Alembic entirely,
    see `app.graph.builder._select_checkpointer`'s docstring for why).
    LangGraph checkpointers key purely by `thread_id`, with no concept of
    an owning user -- `app.api.routes_runs`'s `get_run`/`resume_run` must
    check `owner_user_id` here FIRST, before ever touching the
    checkpointer, so a thread minted by one user can never be read or
    resumed by another (invariant #3: identity for this check comes only
    from the verified session token, never a client-supplied value).

    `id` mirrors `SharedPlan.id`'s pattern -- `secrets.token_urlsafe(16)`,
    minted by `app.api.routes_runs`, NOT a sequential integer -- so a
    thread_id is not enumerable. Cross-user access returns 404 (matching
    `app.services.share_service.get_share`'s existing "exists but isn't
    yours" collapse -- advisor-reviewed decision, ROADMAP 3.2), not 403:
    thread_ids already carry 128 bits of unguessability, so hiding
    existence costs little, and no legitimate client needs to distinguish
    "not found" from "not yours" here.
    """

    __tablename__ = "graph_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    owner_user_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ChatThread(Base):
    """ROADMAP.md Phase 3, Step 3.3: one "Chef" conversational-agent thread.

    `id` mirrors `SharedPlan.id`/`GraphRun.id`'s pattern -- `secrets.
    token_urlsafe(16)`, minted by `app.api.routes_chat`, NOT a sequential
    integer. `id` doubles as the LangGraph `thread_id` for the chef
    checkpointer (`app.agent.chef_agent`), namespaced via `checkpoint_ns=
    "chef"` so it can never collide with a `GraphRun` id used by the
    recommend graph's checkpointer, even though both mint ids the same way
    (see `app.agent.chef_agent`'s module docstring).

    `user_profile` is bound ONCE, at thread-creation time (client-supplied
    in the `POST /chat` body) and stored here as a JSON blob -- advisor-
    reviewed decision (Phase 3.3 design consult addendum): unlike the
    recommend graph (where `UserProfile` is per-request, from
    `RecommendationRequest.user_profile`), a chat thread is multi-turn over
    a persisted conversation, so the profile has nowhere else to live
    between turns. Every tool wrapper that needs it (`check_recipe_safety`,
    `propose_substitutions`, `build_day_plan`) closes over THIS stored
    value -- it is never an LLM-controllable tool-call argument, the same
    invariant-#3-flavored treatment `get_user_context`'s `user_id` needs.

    Cross-user access is 404 (mirrors `GraphRun`'s identical "no oracle for
    exists-but-not-yours" collapse, same rationale: 128 bits of
    unguessability via `secrets.token_urlsafe` already makes hiding
    existence cheap, and no legitimate client needs to tell the two cases
    apart) -- see `app.data.chat_thread_repository.ChatThreadRepository.
    get_owned`.
    """

    __tablename__ = "chat_threads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    owner_user_id: Mapped[str] = mapped_column(String(128), index=True)
    user_profile: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ChatMessage(Base):
    """One turn's worth of persisted chat transcript (ROADMAP.md Phase 3,
    Step 3.3) -- `role="user"` for the human's message, `role="assistant"`
    for the Chef agent's final answer for a turn, `role="tool"` for one row
    per tool call executed during a turn (display/audit trail for the chat
    UI's tool-call chips, ROADMAP Phase 4.3).

    `tool_calls_json` is the JSON-serialized tool-call history for THIS
    message: for an `assistant` row, the full list of `(tool, args, result)`
    entries the response gate (`app.agent.chef_agent.evaluate_response_
    gate`) checked before this message was released -- the durable record
    of what was actually consulted, never re-derived after the fact. For a
    `tool` row, that single call's own entry. `None` for `user` rows.
    """

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    tool_calls_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, default=lambda: datetime.now(UTC)
    )


class AgentNote(Base):
    """Long-term per-user memory the Chef agent can APPEND to via its one
    `remember(note)` tool (ROADMAP.md Phase 3, Step 3.3) -- never edited or
    deleted by the LLM (see `app.data.agent_note_repository.
    AgentNoteRepository`'s docstring: `remember()` is the only LLM-facing
    write; deletion is human-only, via `DELETE /chat/notes/{id}`).

    `is_active` is a soft-delete flag, doing double duty for two DISTINCT
    lifecycle events (advisor-reviewed decision, Q2): (1) a human deleting a
    note via the REST endpoint, and (2) automatic oldest-first eviction when
    a user's 31st active note would be created (hard cap: `AgentNoteRepository.
    MAX_ACTIVE_NOTES`) -- `remember()` never refuses a new note; it evicts the
    oldest active one instead, since the user just explicitly asked to
    remember something. Both cases are indistinguishable from a query's point
    of view (`is_active=False` either way), which is fine: a human viewing
    "my notes" only ever needs to see the currently-active set.
    """

    __tablename__ = "agent_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    note: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, default=lambda: datetime.now(UTC)
    )


class LLMCacheEntry(Base):
    """Response-level cache for `app.services.model_provider.
    generate_structured` calls (ROADMAP.md Phase 2, Step 2.3) -- see
    `app.services.llm_cache` for the read/write API and the TTL-per-purpose
    policy. Stores the exact validated JSON response, never a post-
    processed decision -- same "cache FACTS, not DECISIONS" principle as
    `app.services.nutrition_cache.FdcCache` (a logic change downstream of
    the cached response never needs a cache invalidation pass, since
    nothing decision-shaped lives here).

    `cache_key` is the SHA256 hex digest of (provider, model, purpose,
    canonicalized prompt, canonicalized schema) -- see
    `app.services.llm_cache.build_cache_key`. It is the only thing this
    table is ever looked up by, hence `unique=True`.

    TTL is resolved to a concrete `expires_at` at WRITE time (from
    `app.services.llm_cache.TTL_BY_PURPOSE`) rather than stored as a raw
    `ttl_seconds` re-checked against `created_at` on every read: a future
    change to a purpose's TTL policy then only affects NEWLY written rows,
    never silently reinterprets rows already on disk -- the same "never
    reinterpret old data under new rules" principle as
    `FdcCache`'s `_SCHEMA_VERSION`. The single writer is
    `app.services.llm_cache.store_response`; never hand-write to this table
    elsewhere.
    """

    __tablename__ = "llm_cache_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(128), index=True)
    purpose: Mapped[str] = mapped_column(String(64), index=True)
    response_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
