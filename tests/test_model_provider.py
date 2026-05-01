from app.config import Settings
from app.services.model_provider import _models_for, provider_chain


def test_provider_chain_uses_default_then_configured_fallbacks() -> None:
    settings = Settings(MODEL_PROVIDER="gemini", MODEL_PROVIDER_FALLBACKS="openai,claude,local")

    assert provider_chain(settings) == ["gemini", "openai", "anthropic", "ollama", "mock"]


def test_provider_chain_deduplicates_and_keeps_mock_available() -> None:
    settings = Settings(MODEL_PROVIDER="openai", MODEL_PROVIDER_FALLBACKS="openai,mock")

    assert provider_chain(settings) == ["openai", "mock"]


def test_gemini_31_preview_settings_are_configurable() -> None:
    settings = Settings(
        MODEL_PROVIDER="google",
        GEMINI_CHAT_MODEL="gemini-3.1-flash-lite-preview",
        GEMINI_VISION_MODEL="gemini-3.1-flash-lite-preview",
        GEMINI_CHAT_MODEL_FALLBACKS="gemini-2.5-flash",
        GEMINI_VISION_MODEL_FALLBACKS="gemini-2.5-flash",
        GEMINI_API_VERSION="v1beta",
        GEMINI_THINKING_LEVEL="low",
    )

    assert provider_chain(settings)[0] == "gemini"
    assert settings.gemini_chat_model == "gemini-3.1-flash-lite-preview"
    assert settings.gemini_vision_model == "gemini-3.1-flash-lite-preview"
    assert _models_for(settings, "gemini", "chat") == [
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-flash",
    ]
    assert _models_for(settings, "gemini", "vision") == [
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-flash",
    ]
    assert settings.gemini_api_version == "v1beta"
    assert settings.gemini_thinking_level == "low"
