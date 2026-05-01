import base64
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.schemas.inventory import InventoryObservation
from app.schemas.recipe import Recipe
from app.schemas.recommendation import RecipeScore
from app.utils.ingredient_normalizer import normalize_ingredient
from app.utils.logging import get_logger

logger = get_logger(__name__)

ProviderName = str
MockVisionExtractor = Callable[[str | Path | None], list[InventoryObservation]]

PROVIDER_ALIASES = {
    "google": "gemini",
    "claude": "anthropic",
    "anthropic": "anthropic",
    "local": "ollama",
    "ollama": "ollama",
    "openai": "openai",
    "gemini": "gemini",
    "mock": "mock",
}

DEFAULT_MODELS = {
    "openai": {"chat": "gpt-4.1-mini", "vision": "gpt-4.1-mini"},
    "gemini": {"chat": "gemini-3-flash-preview", "vision": "gemini-3-flash-preview"},
    "anthropic": {"chat": "claude-sonnet-4-5", "vision": "claude-sonnet-4-5"},
    "ollama": {"chat": "llama3.2", "vision": "gemma3"},
}

VISION_PROMPT = """
Extract visible fridge or pantry ingredients from this image.
Return JSON only with this shape:
{
  "items": [
    {
      "raw_name": "ingredient as seen",
      "normalized_name": "common grocery name",
      "quantity": null,
      "confidence": 0.0,
      "needs_confirmation": true
    }
  ]
}
Use confidence between 0 and 1. Mark uncertain or partially visible items as needs_confirmation.
Do not include prepared recipe ideas, nutrition facts, allergens, or safety decisions.
""".strip()


class _ProviderIngredient(BaseModel):
    raw_name: str
    normalized_name: str | None = None
    quantity: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    needs_confirmation: bool = False


class _ProviderInventory(BaseModel):
    items: list[_ProviderIngredient]


def provider_chain(settings: Settings | None = None) -> list[ProviderName]:
    settings = settings or get_settings()
    ordered = [_canonical_provider(settings.model_provider)]
    ordered.extend(
        _canonical_provider(item) for item in _split_csv(settings.model_provider_fallbacks)
    )
    ordered.append("mock")

    chain: list[ProviderName] = []
    for provider in ordered:
        if provider and provider in PROVIDER_ALIASES.values() and provider not in chain:
            chain.append(provider)
    return chain


def generate_explanation_with_provider_chain(
    recipe: Recipe,
    score: RecipeScore,
    allergy_safe: bool = True,
) -> str:
    settings = get_settings()
    fallback = template_explanation(recipe, score, allergy_safe)
    prompt = _build_explanation_prompt(recipe, score, allergy_safe)

    for provider in provider_chain(settings):
        if provider == "mock":
            return fallback
        if not _provider_is_configured(provider, settings):
            logger.info("Skipping %s explanation provider; it is not configured.", provider)
            continue
        try:
            text = _generate_text(provider, prompt, settings)
            if text:
                return text
        except Exception as exc:  # pragma: no cover - optional hosted/local provider paths
            logger.warning("%s explanation failed, trying fallback provider: %s", provider, exc)

    return fallback


def extract_inventory_with_provider_chain(
    image_path: str | Path | None,
    mock_extractor: MockVisionExtractor,
) -> list[InventoryObservation]:
    settings = get_settings()

    for provider in provider_chain(settings):
        if provider == "mock":
            return mock_extractor(image_path)
        if not _provider_is_configured(provider, settings):
            logger.info("Skipping %s vision provider; it is not configured.", provider)
            continue
        try:
            observations = _extract_inventory(provider, image_path, settings)
            if observations:
                return observations
        except Exception as exc:  # pragma: no cover - optional hosted/local provider paths
            logger.warning(
                "%s vision extraction failed, trying fallback provider: %s",
                provider,
                exc,
            )

    return mock_extractor(image_path)


def template_explanation(recipe: Recipe, score: RecipeScore, allergy_safe: bool = True) -> str:
    used = ", ".join(score.used_ingredients) or "your available pantry items"
    missing = ", ".join(score.missing_ingredients) or "nothing essential"
    macro_note = (
        f"Macro fit is {score.macro_fit_score:.0%}, with "
        f"{recipe.calories:.0f} calories, {recipe.protein_g:.0f}g protein, "
        f"{recipe.carbs_g:.0f}g carbs, and {recipe.fat_g:.0f}g fat."
    )
    safety_note = "It passed the deterministic allergy and diet validation." if allergy_safe else ""
    return (
        f"{recipe.title} fits because it uses {used} and keeps the shopping gap to "
        f"{missing}. {macro_note} Pantry match is {score.pantry_match_score:.0%}. {safety_note}"
    )


def _build_explanation_prompt(recipe: Recipe, score: RecipeScore, allergy_safe: bool) -> str:
    return f"""
You are MacroChef Agent's chef explanation layer.
Write one friendly, concise paragraph for a recipe recommendation.

Use only the structured data below. Do not calculate nutrition. Do not decide allergy safety.
Allergy safety has already been validated by deterministic Python logic.

Recipe:
- title: {recipe.title}
- cuisine: {recipe.cuisine}
- meal type: {recipe.meal_type}
- cook time minutes: {recipe.cook_time_min}
- ingredients: {recipe.ingredients}
- calories: {recipe.calories}
- protein_g: {recipe.protein_g}
- carbs_g: {recipe.carbs_g}
- fat_g: {recipe.fat_g}
- fiber_g: {recipe.fiber_g}

Scores:
- final score: {score.final_score:.0%}
- pantry match: {score.pantry_match_score:.0%}
- macro fit: {score.macro_fit_score:.0%}
- used ingredients: {score.used_ingredients}
- missing ingredients: {score.missing_ingredients}
- deterministic allergy safe: {allergy_safe}

Mention why it fits, used ingredients, missing ingredients, macro fit, and allergy safety.
Keep it under 90 words.
""".strip()


def _generate_text(provider: ProviderName, prompt: str, settings: Settings) -> str:
    if provider == "gemini":
        return _generate_text_with_gemini(prompt, settings)
    if provider == "openai":
        return _generate_text_with_openai(prompt, settings)
    if provider == "anthropic":
        return _generate_text_with_anthropic(prompt, settings)
    if provider == "ollama":
        return _generate_text_with_ollama(prompt, settings)
    raise ValueError(f"Unsupported provider: {provider}")


def _extract_inventory(
    provider: ProviderName,
    image_path: str | Path | None,
    settings: Settings,
) -> list[InventoryObservation]:
    if image_path is None:
        raise ValueError(f"{provider} vision requires an uploaded image path.")
    if provider == "gemini":
        return _extract_inventory_with_gemini(image_path, settings)
    if provider == "openai":
        return _extract_inventory_with_openai(image_path, settings)
    if provider == "anthropic":
        return _extract_inventory_with_anthropic(image_path, settings)
    if provider == "ollama":
        return _extract_inventory_with_ollama(image_path, settings)
    raise ValueError(f"Unsupported provider: {provider}")


def _generate_text_with_gemini(prompt: str, settings: Settings) -> str:
    from google.genai import types

    client = _gemini_client(settings)
    last_error: Exception | None = None
    for model in _models_for(settings, "gemini", "chat"):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=_gemini_generate_config(types, settings, model=model, temperature=0.2),
            )
            return _require_text(response.text, f"Gemini model {model}")
        except Exception as exc:  # pragma: no cover - optional hosted provider path
            last_error = exc
            logger.warning("Gemini chat model %s failed, trying next model: %s", model, exc)
    raise last_error or ValueError("No Gemini chat models were configured.")


def _generate_text_with_openai(prompt: str, settings: Settings) -> str:
    from openai import OpenAI

    client_kwargs = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)
    response = client.responses.create(
        model=_model_for(settings, "openai", "chat"),
        input=prompt,
        temperature=0.2,
    )
    return _require_text(response.output_text, "OpenAI")


def _generate_text_with_anthropic(prompt: str, settings: Settings) -> str:
    payload = {
        "model": _model_for(settings, "anthropic", "chat"),
        "max_tokens": 240,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = _post_anthropic(payload, settings)
    return _require_text(_anthropic_text(data), "Anthropic")


def _generate_text_with_ollama(prompt: str, settings: Settings) -> str:
    payload = {
        "model": _model_for(settings, "ollama", "chat"),
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    data = _post_ollama(payload, settings)
    return _require_text(data.get("message", {}).get("content"), "Ollama")


def _extract_inventory_with_gemini(
    image_path: str | Path,
    settings: Settings,
) -> list[InventoryObservation]:
    from google.genai import types

    path = Path(image_path)
    client = _gemini_client(settings)
    image_part = types.Part.from_bytes(
        data=path.read_bytes(),
        mime_type=_guess_image_mime_type(path),
    )
    last_error: Exception | None = None
    for model in _models_for(settings, "gemini", "vision"):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[image_part, VISION_PROMPT],
                config=_gemini_generate_config(
                    types,
                    settings,
                    model=model,
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
            return _observations_from_json_text(response.text or "", settings)
        except Exception as exc:  # pragma: no cover - optional hosted provider path
            last_error = exc
            logger.warning("Gemini vision model %s failed, trying next model: %s", model, exc)
    raise last_error or ValueError("No Gemini vision models were configured.")


def _gemini_client(settings: Settings):
    from google import genai

    client_kwargs: dict[str, Any] = {"api_key": settings.google_api_key}
    http_options: dict[str, Any] = {}
    if settings.gemini_base_url:
        http_options["base_url"] = settings.gemini_base_url
    elif settings.gemini_api_version:
        http_options["api_version"] = settings.gemini_api_version
    if http_options:
        client_kwargs["http_options"] = http_options
    return genai.Client(**client_kwargs)


def _gemini_generate_config(
    types_module,
    settings: Settings,
    *,
    model: str,
    temperature: float,
    response_mime_type: str | None = None,
):
    config_kwargs: dict[str, Any] = {"temperature": temperature}
    if response_mime_type:
        config_kwargs["response_mime_type"] = response_mime_type

    thinking_kwargs: dict[str, Any] = {}
    if settings.gemini_thinking_level and model.startswith("gemini-3"):
        thinking_kwargs["thinking_level"] = settings.gemini_thinking_level
    if settings.gemini_thinking_budget is not None:
        thinking_kwargs["thinking_budget"] = settings.gemini_thinking_budget
    if thinking_kwargs:
        config_kwargs["thinking_config"] = types_module.ThinkingConfig(**thinking_kwargs)

    return types_module.GenerateContentConfig(**config_kwargs)


def _extract_inventory_with_openai(
    image_path: str | Path,
    settings: Settings,
) -> list[InventoryObservation]:
    from openai import OpenAI

    path = Path(image_path)
    data_url = _image_data_url(path)
    client_kwargs = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)
    response = client.responses.create(
        model=_model_for(settings, "openai", "vision"),
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": VISION_PROMPT},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
        temperature=0,
    )
    return _observations_from_json_text(response.output_text or "", settings)


def _extract_inventory_with_anthropic(
    image_path: str | Path,
    settings: Settings,
) -> list[InventoryObservation]:
    path = Path(image_path)
    payload = {
        "model": _model_for(settings, "anthropic", "vision"),
        "max_tokens": 700,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": _guess_image_mime_type(path),
                            "data": _base64_image(path),
                        },
                    },
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }
        ],
    }
    data = _post_anthropic(payload, settings)
    return _observations_from_json_text(_anthropic_text(data), settings)


def _extract_inventory_with_ollama(
    image_path: str | Path,
    settings: Settings,
) -> list[InventoryObservation]:
    path = Path(image_path)
    payload = {
        "model": _model_for(settings, "ollama", "vision"),
        "messages": [{"role": "user", "content": VISION_PROMPT, "images": [_base64_image(path)]}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    data = _post_ollama(payload, settings)
    return _observations_from_json_text(data.get("message", {}).get("content", ""), settings)


def _post_anthropic(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    response = requests.post(
        f"{settings.anthropic_base_url.rstrip('/')}/messages",
        headers={
            "x-api-key": settings.anthropic_api_key or "",
            "anthropic-version": settings.anthropic_api_version,
            "content-type": "application/json",
        },
        json=payload,
        timeout=settings.model_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def _post_ollama(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    response = requests.post(
        f"{settings.ollama_base_url.rstrip('/')}/api/chat",
        json=payload,
        timeout=settings.model_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def _observations_from_json_text(text: str, settings: Settings) -> list[InventoryObservation]:
    payload = _parse_json_object(text)
    parsed = _ProviderInventory.model_validate(payload)
    observations = [_provider_observation(item, settings) for item in parsed.items]
    if not observations:
        raise ValueError("Provider did not return any ingredients.")
    return observations


def _provider_observation(item: _ProviderIngredient, settings: Settings) -> InventoryObservation:
    raw_name = item.raw_name.strip()
    normalized = normalize_ingredient(item.normalized_name or raw_name)
    confidence = max(0.0, min(1.0, item.confidence))
    return InventoryObservation(
        raw_name=raw_name,
        normalized_name=normalized,
        quantity=item.quantity,
        confidence=confidence,
        source="vision",
        needs_confirmation=(
            item.needs_confirmation or confidence < settings.low_confidence_threshold
        ),
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _anthropic_text(data: dict[str, Any]) -> str:
    return "".join(
        part.get("text", "")
        for part in data.get("content", [])
        if isinstance(part, dict) and part.get("type") == "text"
    )


def _image_data_url(path: Path) -> str:
    return f"data:{_guess_image_mime_type(path)};base64,{_base64_image(path)}"


def _base64_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _guess_image_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".gif":
        return "image/gif"
    return "image/png"


def _model_for(settings: Settings, provider: ProviderName, kind: str) -> str:
    specific = getattr(settings, f"{provider}_{kind}_model", None)
    if specific:
        return specific

    legacy = settings.chat_model if kind == "chat" else settings.vision_model
    if legacy and legacy != "mock":
        return legacy

    return DEFAULT_MODELS[provider][kind]


def _models_for(settings: Settings, provider: ProviderName, kind: str) -> list[str]:
    primary = _model_for(settings, provider, kind)
    fallback_value = getattr(settings, f"{provider}_{kind}_model_fallbacks", "")
    models = [primary, *_split_csv(fallback_value)]

    deduped: list[str] = []
    for model in models:
        if model and model not in deduped:
            deduped.append(model)
    return deduped


def _provider_is_configured(provider: ProviderName, settings: Settings) -> bool:
    if provider == "gemini":
        return bool(settings.google_api_key)
    if provider == "openai":
        return bool(settings.openai_api_key)
    if provider == "anthropic":
        return bool(settings.anthropic_api_key)
    if provider == "ollama":
        return True
    return provider == "mock"


def _canonical_provider(provider: str | None) -> ProviderName:
    return PROVIDER_ALIASES.get((provider or "mock").strip().lower(), "")


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _require_text(text: str | None, provider: str) -> str:
    value = (text or "").strip()
    if not value:
        raise ValueError(f"{provider} returned an empty response.")
    return value
