import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def force_mock_model_provider(monkeypatch: pytest.MonkeyPatch):
    """Keep tests deterministic even when a developer has real API keys in `.env`."""

    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    monkeypatch.setenv("MODEL_PROVIDER_FALLBACKS", "mock")
    for key in (
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "CLAUDE_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
