from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def chroma_dir(self) -> Path:
        return Path(self.chroma_path)

    @property
    def recipe_path(self) -> Path:
        return Path(self.recipe_data_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
