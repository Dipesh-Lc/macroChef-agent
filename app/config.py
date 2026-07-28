from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Strings that pydantic-settings treats as True for bool fields.
# Mirrors pydantic_settings' own bool coercion so any code that cannot import
# Settings (e.g. the Streamlit frontend) can parse env vars consistently.
_TRUE_STRINGS: frozenset[str] = frozenset({"1", "true", "yes", "on"})


def parse_env_bool(value: str | None, *, default: bool = False) -> bool:
    """Return the bool equivalent of an env-var string using the same coercion
    rules as pydantic-settings (with env_ignore_empty=True):
      truthy  → "1" | "true" | "yes" | "on"  (case-insensitive)
      falsy   → "0" | "false" | "no" | "off" | "" | None → default
    """
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in _TRUE_STRINGS


class Settings(BaseSettings):
    """Runtime configuration with mock/local defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
        protected_namespaces=("settings_",),
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    google_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    gemini_base_url: str | None = Field(default=None, alias="GEMINI_BASE_URL")
    gemini_api_version: str | None = Field(default=None, alias="GEMINI_API_VERSION")
    gemini_thinking_level: str | None = Field(default=None, alias="GEMINI_THINKING_LEVEL")
    gemini_thinking_budget: int | None = Field(default=None, alias="GEMINI_THINKING_BUDGET")
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "CLAUDE_API_KEY"),
    )
    anthropic_base_url: str = Field(
        default="https://api.anthropic.com/v1",
        alias="ANTHROPIC_BASE_URL",
    )
    anthropic_api_version: str = Field(
        default="2023-06-01",
        alias="ANTHROPIC_API_VERSION",
    )
    model_provider: str = Field(default="mock", alias="MODEL_PROVIDER")
    model_provider_fallbacks: str = Field(default="mock", alias="MODEL_PROVIDER_FALLBACKS")
    vision_model: str = Field(default="mock", alias="VISION_MODEL")
    chat_model: str = Field(default="mock", alias="CHAT_MODEL")
    openai_chat_model: str | None = Field(default=None, alias="OPENAI_CHAT_MODEL")
    openai_vision_model: str | None = Field(default=None, alias="OPENAI_VISION_MODEL")
    gemini_chat_model: str | None = Field(default=None, alias="GEMINI_CHAT_MODEL")
    gemini_vision_model: str | None = Field(default=None, alias="GEMINI_VISION_MODEL")
    gemini_chat_model_fallbacks: str = Field(default="", alias="GEMINI_CHAT_MODEL_FALLBACKS")
    gemini_vision_model_fallbacks: str = Field(default="", alias="GEMINI_VISION_MODEL_FALLBACKS")
    anthropic_chat_model: str | None = Field(default=None, alias="ANTHROPIC_CHAT_MODEL")
    anthropic_vision_model: str | None = Field(default=None, alias="ANTHROPIC_VISION_MODEL")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_chat_model: str | None = Field(default=None, alias="OLLAMA_CHAT_MODEL")
    ollama_vision_model: str | None = Field(default=None, alias="OLLAMA_VISION_MODEL")
    model_timeout_seconds: float = Field(default=30.0, alias="MODEL_TIMEOUT_SECONDS")
    embedding_provider: str = Field(default="local", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL"
    )
    chroma_path: str = Field(default="./data/chroma", alias="CHROMA_PATH")
    database_url: str = Field(default="sqlite:///./macrochef.db", alias="DATABASE_URL")
    recipe_data_path: str = "./data/processed/sample_recipes.jsonl"
    chroma_collection_name: str = "macrochef_recipes"
    low_confidence_threshold: float = 0.75
    enable_vision: bool = Field(default=False, alias="MACROCHEF_ENABLE_VISION")
    fdc_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FDC_API_KEY", "USDA_API_KEY"),
    )
    fdc_base_url: str = Field(
        default="https://api.nal.usda.gov/fdc/v1", alias="FDC_BASE_URL"
    )
    fdc_cache_path: str = "./data/cache/fdc_cache.json"

    # Signed session cookie secret (anonymous session identity), consumed by
    # app/dependencies.py to sign/verify the session token. The secure
    # default is fail-closed: if this is unset, both
    # app.dependencies._resolve_session_secret (every token mint/verify, in
    # both the FastAPI and Streamlit processes) and
    # app.dependencies.validate_session_secret_at_startup (FastAPI boot)
    # raise a RuntimeError rather than serve traffic. This is NEVER inferred
    # from database_url or any other unrelated setting -- see
    # allow_insecure_session_secret below for the only opt-out. Production
    # must set this via the ACA secret wired up in .github/workflows/ci.yml.
    session_secret: str | None = Field(default=None, alias="SESSION_SECRET")

    # Explicit, localhost-only opt-in to run without a real SESSION_SECRET.
    # When True and session_secret is unset, falls back to a hardcoded,
    # publicly-known dev default (loud warning logged every time). Must
    # never be set in a deployed environment -- there is deliberately no
    # env var or heuristic (like DATABASE_URL) that turns this on
    # automatically; a human must opt in explicitly.
    allow_insecure_session_secret: bool = Field(
        default=False, alias="ALLOW_INSECURE_SESSION_SECRET"
    )

    # Tri-state Secure attribute for the `mc_session` cookie minted by
    # POST /session (app/api/routes_session.py) -- see
    # app.dependencies.resolve_cookie_secure for the resolution logic.
    # "auto" (default): Secure when the request itself is https, or a
    # reverse proxy says the original request was
    # (X-Forwarded-Proto: https). "always": Secure regardless (what
    # production sets -- a spoofed X-Forwarded-Proto: http must never be
    # able to drop Secure). "never": never Secure (plain http local dev).
    session_cookie_secure: str = Field(default="auto", alias="SESSION_COOKIE_SECURE")

    # PostHog analytics. Absent key => silent no-op (see app/services/analytics.py).
    posthog_api_key: str | None = Field(default=None, alias="POSTHOG_API_KEY")
    posthog_host: str = Field(default="https://us.i.posthog.com", alias="POSTHOG_HOST")

    # Per-session in-memory rate limits (see app/services/rate_limiter.py and
    # app/dependencies.py). All three gate an LLM call or heavy synchronous
    # work; defaults are sized for a single-replica public hobby demo, not a
    # multi-tenant product -- tune upward only alongside real usage data.
    rate_limit_discover_max: int = Field(default=20, alias="RATE_LIMIT_DISCOVER_MAX")
    rate_limit_discover_window_seconds: float = Field(
        default=3600.0, alias="RATE_LIMIT_DISCOVER_WINDOW_SECONDS"
    )
    rate_limit_recommend_max: int = Field(default=20, alias="RATE_LIMIT_RECOMMEND_MAX")
    rate_limit_recommend_window_seconds: float = Field(
        default=3600.0, alias="RATE_LIMIT_RECOMMEND_WINDOW_SECONDS"
    )
    # Reindex re-embeds the whole corpus synchronously -- the single most
    # expensive endpoint in the app -- so it gets the tightest cap of the
    # three by a wide margin.
    rate_limit_reindex_max: int = Field(default=2, alias="RATE_LIMIT_REINDEX_MAX")
    rate_limit_reindex_window_seconds: float = Field(
        default=3600.0, alias="RATE_LIMIT_REINDEX_WINDOW_SECONDS"
    )

    # /tools/* safety-tools endpoints (app/api/routes_safety_tools.py,
    # Phase 5) -- keyed by caller IP, not a verified session (see
    # app/dependencies.py require_safety_tools_rate_limit for why). Each
    # call is a single deterministic function call (no LLM, no corpus scan),
    # so the default budget is generous relative to the other three buckets.
    rate_limit_safety_tools_max: int = Field(default=60, alias="RATE_LIMIT_SAFETY_TOOLS_MAX")
    rate_limit_safety_tools_window_seconds: float = Field(
        default=3600.0, alias="RATE_LIMIT_SAFETY_TOOLS_WINDOW_SECONDS"
    )

    # Roadmap item "Shareable plan URLs" (Phase 4 item 4). POST /share is
    # keyed by the verified session user id (same _rate_limit_dependency
    # pattern as rate_limit_discover_max/rate_limit_recommend_max above);
    # GET /share/{id} is unauthenticated by design, so it is keyed by caller
    # IP instead (same pattern as rate_limit_safety_tools_max) -- see
    # app.dependencies.require_share_create_rate_limit /
    # require_share_view_rate_limit.
    rate_limit_share_create_max: int = Field(default=20, alias="RATE_LIMIT_SHARE_CREATE_MAX")
    rate_limit_share_create_window_seconds: float = Field(
        default=3600.0, alias="RATE_LIMIT_SHARE_CREATE_WINDOW_SECONDS"
    )
    # GET /share/{id} is a cheap read (one indexed DB lookup, no LLM, no
    # corpus scan) but is the single most exposed endpoint in the app (no
    # session required at all) -- generous per-IP budget, matching the
    # safety-tools precedent's reasoning.
    rate_limit_share_view_max: int = Field(default=120, alias="RATE_LIMIT_SHARE_VIEW_MAX")
    rate_limit_share_view_window_seconds: float = Field(
        default=3600.0, alias="RATE_LIMIT_SHARE_VIEW_WINDOW_SECONDS"
    )

    # POST /session (app/api/routes_session.py, SPA rebuild W0) -- the
    # anonymous session-mint/validate endpoint. Keyed by caller IP, not a
    # verified session (this endpoint is pre-identity by definition -- see
    # app.api.routes_session.require_session_mint_rate_limit). Every call
    # counts against this bucket uniformly, including the 204-no-mint
    # ("caller already has a valid session") branch.
    rate_limit_session_max: int = Field(default=60, alias="RATE_LIMIT_SESSION_MAX")
    rate_limit_session_window_seconds: float = Field(
        default=3600.0, alias="RATE_LIMIT_SESSION_WINDOW_SECONDS"
    )

    # SPA rebuild W1a (app/spa.py): directory containing the built React SPA
    # (Vite's `index.html` + `assets/`). Defaults to `<repo>/web/dist`,
    # relative to the process's working directory like the other path
    # settings above (chroma_path, recipe_data_path). If `index.html` isn't
    # found there at app-startup mount time, the SPA/static routes are
    # skipped entirely (a warning is logged) -- the API stays fully usable
    # without a Node build, which is the normal case for pytest/CI today.
    web_dist: str = Field(default="./web/dist", alias="MACROCHEF_WEB_DIST")

    # OpenTelemetry hosted-backend tracing (ROADMAP.md Phase 1, Step 1.3) --
    # see app.observability.tracing, whose `init_tracing` is a true no-op
    # (no provider installed, no exporter thread, no FastAPI/requests
    # instrumentation) whenever `otel_exporter_otlp_endpoint` is blank,
    # which is the default for local dev and CI. Read through Settings
    # (like every other env var in this file) rather than raw `os.environ`
    # inside tracing.py, so a value that only lives in a local `.env` file
    # (pydantic-settings parses that itself; it does not export it into the
    # real process environment) is honored consistently instead of only
    # being visible to this class and silently invisible to the OTel SDK's
    # own env-var reads. `otel_exporter_otlp_headers` uses the OTel-spec
    # comma-separated "key1=value1,key2=value2" format -- for Honeycomb
    # (the recommended backend; see docs/HUMAN_INPUTS.md entry H1) that's
    # "x-honeycomb-team=<API_KEY>". Never logged.
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None, alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otel_exporter_otlp_headers: str | None = Field(
        default=None, alias="OTEL_EXPORTER_OTLP_HEADERS"
    )

    # Security-headers hardening (ROADMAP.md Phase 5, Step 5.4) --
    # app.main.SecurityHeadersMiddleware only sends `Strict-Transport-Security`
    # when this is True. HSTS tells a browser "only ever speak HTTPS to this
    # origin for the next `max-age`" -- a promise this app cannot itself
    # verify, since ACA terminates TLS at the ingress and forwards plain HTTP
    # to this container (the request this process sees is never actually
    # "http" vs "https" in a way that's safe to trust without also trusting
    # `X-Forwarded-Proto`, and even then, sending HSTS is a deployment-wide
    # promise, not a per-request one). Defaults off so local `http://
    # localhost` dev (and any HTTP-only deployment) is never told by its own
    # server to distrust HTTP -- see .env.example for how production should
    # enable this.
    enable_hsts: bool = Field(default=False, alias="ENABLE_HSTS")

    # Async fan-out concurrency bound (ROADMAP.md Phase 2, Step 2.2) -- the
    # single shared budget for how many outbound network calls this process
    # makes at once via the async paths added in that step: both `app.
    # services.usda_client.UsdaClient`'s async USDA FDC lookups (see
    # `nutrition_grounding.compute_recipe_macros_async` / `grounding_job.
    # run_grounding_async`) and `app.services.model_provider`'s async
    # provider chat/vision calls share this one knob rather than each having
    # its own, since both are ultimately "how many concurrent HTTP requests
    # is this process allowed to have in flight." Kept low by default (4):
    # USDA FDC has its own hourly rate limit (see usda_client.py's
    # `_RATE_LIMIT_*` constants) that a large corpus fan-out must not run
    # into any harder than the sequential version already risked.
    llm_max_concurrency: int = Field(default=4, alias="LLM_MAX_CONCURRENCY")

    # Response-level LLM cache kill switch (ROADMAP.md Phase 2, Step 2.3) --
    # see app.services.llm_cache (TTL-per-purpose policy, cache key shape)
    # and model_provider.generate_structured's cache wiring. True (default):
    # a `generate_structured` call for a purpose with a configured TTL
    # (app.services.llm_cache.TTL_BY_PURPOSE) checks the cache before
    # calling any provider, and writes a fresh entry on a miss. False:
    # `generate_structured` behaves EXACTLY as it did before this step
    # existed -- no cache read, no cache write, in either direction (see
    # tests/test_llm_cache.py's kill-switch test, which asserts both).
    llm_cache_enabled: bool = Field(default=True, alias="LLM_CACHE_ENABLED")

    @property
    def chroma_dir(self) -> Path:
        return Path(self.chroma_path)

    @property
    def recipe_path(self) -> Path:
        return Path(self.recipe_data_path)

    @property
    def web_dist_path(self) -> Path:
        return Path(self.web_dist)


@lru_cache
def get_settings() -> Settings:
    return Settings()
