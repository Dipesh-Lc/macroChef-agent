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

    @property
    def chroma_dir(self) -> Path:
        return Path(self.chroma_path)

    @property
    def recipe_path(self) -> Path:
        return Path(self.recipe_data_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
