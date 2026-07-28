import base64
import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.observability.llm_ledger import record_llm_call
from app.schemas.inventory import InventoryObservation
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
    "gemini": {"chat": "gemini-2.5-flash", "vision": "gemini-2.5-flash"},
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


class _UsageInfo:
    """Mutable out-parameter each `_generate_text_with_*`/`_extract_
    inventory_with_*` function fills in as a side effect (alongside its
    normal return value) when the provider response carries real usage
    metadata -- see `_generate_text`/`_extract_inventory` below, the two
    choke points that turn this into an `app.observability.llm_ledger.
    record_llm_call` row. `model` is set even on providers with no usage
    metadata (e.g. which of Gemini's per-model fallback list actually
    answered), so the ledger always knows what model served the call even
    when it doesn't know exactly how many tokens it used."""

    __slots__ = ("model", "prompt_tokens", "completion_tokens")

    def __init__(self) -> None:
        self.model: str | None = None
        self.prompt_tokens: int | None = None
        self.completion_tokens: int | None = None


def _is_fallback_provider(provider: ProviderName, settings: Settings) -> bool:
    """True when `provider` is not the caller's configured primary provider
    -- i.e. this call only happened because an earlier provider in
    `provider_chain` failed or wasn't configured. Purely a ledger signal
    (ROADMAP 1.2's `fallback_used` column); has no bearing on any safety
    decision."""
    return _canonical_provider(settings.model_provider) != provider


def _record_mock_call(purpose: str, settings: Settings) -> None:
    """Ledger coverage for the mock-provider short-circuit branches in
    `generate_detailed_instructions_with_provider_chain`,
    `extract_inventory_with_provider_chain`, and
    `RecipeGenerationService.generate` -- none of those go through
    `_generate_text`/`_extract_inventory` when the provider chain lands on
    "mock" (no real HTTP call happens), so without this call those calls
    would be invisible to GET /admin/llm-usage entirely."""
    record_llm_call(
        provider="mock",
        model="mock",
        purpose=purpose,
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=0.0,
        success=True,
        fallback_used=_is_fallback_provider("mock", settings),
    )


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


def generate_detailed_instructions_with_provider_chain(
    title: str,
    ingredients: list[str],
    instructions: list[str],
    servings: int | None = None,
    cuisine: str | None = None,
) -> tuple[list[str], bool]:
    """Rewrite `instructions` as detailed, numbered, beginner-friendly steps
    via the same provider chain used elsewhere in this module.

    This is a phrasing/elaboration task ONLY -- see
    `_build_detailed_instructions_prompt` for the exact guardrails given to
    the model (use only the given ingredients/steps; never add, remove, or
    substitute an ingredient or quantity; never state or imply a calorie,
    nutrition, or allergy/diet safety claim). The LLM never decides a safety
    or nutrition outcome here, matching this file's existing pattern.

    Returns `(steps, generated)`. `generated=False` means the fallback (the
    ORIGINAL `instructions`, unmodified) was used -- either because no real
    provider is configured (mock mode) or because every configured provider
    failed / returned unparseable output. Never fabricate detailed content
    in that case; echoing the original terse steps back is the only honest
    fallback, mirroring the "never silently fabricate" principle documented
    on `extract_inventory_with_provider_chain`'s TODO above (simpler here:
    there's no ambiguity to guess at, so the fallback is just the input).
    """
    settings = get_settings()
    fallback = list(instructions)
    prompt = _build_detailed_instructions_prompt(title, ingredients, instructions, servings, cuisine)

    for provider in provider_chain(settings):
        if provider == "mock":
            _record_mock_call("detailed_instructions", settings)
            return fallback, False
        if not _provider_is_configured(provider, settings):
            logger.info(
                "Skipping %s detailed-instructions provider; it is not configured.", provider
            )
            continue
        try:
            text = _generate_text(provider, prompt, settings, purpose="detailed_instructions")
            steps = _parse_numbered_steps(text)
            if steps:
                return steps, True
            logger.warning(
                "%s detailed-instructions response parsed to zero steps, trying fallback provider.",
                provider,
            )
        except Exception as exc:  # pragma: no cover - optional hosted/local provider paths
            logger.warning(
                "%s detailed-instructions generation failed, trying fallback provider: %s",
                provider,
                exc,
            )

    return fallback, False


def extract_inventory_with_provider_chain(
    image_path: str | Path | None,
    mock_extractor: MockVisionExtractor,
) -> list[InventoryObservation]:
    settings = get_settings()

    for provider in provider_chain(settings):
        if provider == "mock":
            _record_mock_call("vision_extract", settings)
            return mock_extractor(image_path)
        if not _provider_is_configured(provider, settings):
            logger.info("Skipping %s vision provider; it is not configured.", provider)
            continue
        try:
            observations = _extract_inventory(
                provider, image_path, settings, purpose="vision_extract"
            )
            if observations:
                return observations
        except Exception as exc:  # pragma: no cover - optional hosted/local provider paths
            logger.warning(
                "%s vision extraction failed, trying fallback provider: %s",
                provider,
                exc,
            )

    # TODO(Phase 5): before real vision providers are enabled, replace this silent
    # fallback with explicit, user-visible degradation: surface to the caller that
    # extraction failed and mock data is being returned rather than quietly
    # substituting canned inventory. Never silently return fake data for a failed call.
    # (Unreachable in practice today -- provider_chain() always appends "mock" as
    # its last entry, so the loop above already returns via that branch and
    # records a ledger row; this defensive record call covers the case where
    # provider_chain's invariant ever changes.)
    _record_mock_call("vision_extract", settings)
    return mock_extractor(image_path)


def _build_detailed_instructions_prompt(
    title: str,
    ingredients: list[str],
    instructions: list[str],
    servings: int | None,
    cuisine: str | None,
) -> str:
    numbered_steps = "\n".join(f"{index}. {step}" for index, step in enumerate(instructions, start=1))
    servings_line = f"- servings: {servings}" if servings else ""
    cuisine_line = f"- cuisine: {cuisine}" if cuisine else ""
    return f"""
You are MacroChef Agent's cooking-instructions layer. Rewrite the given
recipe steps as detailed, clearly numbered instructions for someone cooking
this exact recipe for the first time. Explain technique, timing, and
doneness cues in more depth than the terse original steps.

Use ONLY the ingredients and steps given below. Do NOT add, remove, or
substitute any ingredient. Do NOT invent a quantity that wasn't given.

Do NOT state or imply anything about calories, nutrition, or allergy/diet
safety -- that has already been handled elsewhere by deterministic code and
is out of scope for this rewrite.

Recipe:
- title: {title}
{cuisine_line}
{servings_line}
- ingredients: {", ".join(ingredients) if ingredients else "none given"}
- original steps:
{numbered_steps if numbered_steps else "none given"}

Output ONLY a numbered list of steps (e.g. "1. ...", "2. ..."), nothing else.
""".strip()


def _parse_numbered_steps(text: str) -> list[str]:
    """Parse an LLM's numbered-list response into `list[str]`, one entry per
    step -- strips a leading "1.", "2)", "3 -", etc. marker per line and
    drops blank lines. Returns [] (never a fabricated step) if nothing
    usable is found, so the caller can treat that provider as failed and
    fall through the chain, same as an empty-text response elsewhere in
    this module."""
    steps: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^\d+\s*[.):\-]\s*(.+)$", line)
        cleaned = match.group(1).strip() if match else line
        if cleaned:
            steps.append(cleaned)
    return steps


_TextGenerator = Callable[[str, Settings, "_UsageInfo"], str]
_VisionExtractor = Callable[[str | Path, Settings, "_UsageInfo"], list[InventoryObservation]]

_TEXT_GENERATORS: dict[str, _TextGenerator] = {}
_VISION_EXTRACTORS: dict[str, _VisionExtractor] = {}


def _generate_text(
    provider: ProviderName, prompt: str, settings: Settings, purpose: str = "unspecified"
) -> str:
    """The single choke point where a real (non-mock) chat/completion
    provider HTTP call happens -- see `app.observability.llm_ledger.
    record_llm_call`, which every call through here (success or failure)
    reports to, keyed by `purpose` (e.g. "detailed_instructions",
    "recipe_generation" -- see each caller for its tag)."""
    generator = _TEXT_GENERATORS.get(provider)
    if generator is None:
        raise ValueError(f"Unsupported provider: {provider}")

    usage = _UsageInfo()
    start = time.perf_counter()
    try:
        text = generator(prompt, settings, usage)
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        record_llm_call(
            provider=provider,
            model=usage.model or _model_for(settings, provider, "chat"),
            purpose=purpose,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency_ms=elapsed_ms,
            success=False,
            fallback_used=_is_fallback_provider(provider, settings),
            prompt_text=prompt,
        )
        raise

    elapsed_ms = (time.perf_counter() - start) * 1000
    record_llm_call(
        provider=provider,
        model=usage.model or _model_for(settings, provider, "chat"),
        purpose=purpose,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        latency_ms=elapsed_ms,
        success=True,
        fallback_used=_is_fallback_provider(provider, settings),
        prompt_text=prompt,
        completion_text=text,
    )
    return text


def _extract_inventory(
    provider: ProviderName,
    image_path: str | Path | None,
    settings: Settings,
    purpose: str = "vision_extract",
) -> list[InventoryObservation]:
    """The single choke point where a real (non-mock) vision provider HTTP
    call happens -- mirrors `_generate_text` above, including ledger
    reporting on both the success and failure paths."""
    if image_path is None:
        raise ValueError(f"{provider} vision requires an uploaded image path.")
    extractor = _VISION_EXTRACTORS.get(provider)
    if extractor is None:
        raise ValueError(f"Unsupported provider: {provider}")

    usage = _UsageInfo()
    start = time.perf_counter()
    try:
        observations = extractor(image_path, settings, usage)
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        record_llm_call(
            provider=provider,
            model=usage.model or _model_for(settings, provider, "vision"),
            purpose=purpose,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency_ms=elapsed_ms,
            success=False,
            fallback_used=_is_fallback_provider(provider, settings),
            prompt_text=VISION_PROMPT,
        )
        raise

    elapsed_ms = (time.perf_counter() - start) * 1000
    record_llm_call(
        provider=provider,
        model=usage.model or _model_for(settings, provider, "vision"),
        purpose=purpose,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        latency_ms=elapsed_ms,
        success=True,
        fallback_used=_is_fallback_provider(provider, settings),
        prompt_text=VISION_PROMPT,
        # Vision responses don't have a single "completion text" the way
        # chat does; token-estimate fallback (only used when the provider
        # doesn't report real usage) has no cheap proxy here, so it's left
        # at 0 rather than guessed at -- real usage data is what actually
        # matters for the hosted providers this counts.
    )
    return observations


def _generate_text_with_gemini(prompt: str, settings: Settings, usage: _UsageInfo) -> str:
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
            usage.model = model
            usage_metadata = getattr(response, "usage_metadata", None)
            if usage_metadata is not None:
                usage.prompt_tokens = getattr(usage_metadata, "prompt_token_count", None)
                usage.completion_tokens = getattr(usage_metadata, "candidates_token_count", None)
            return _require_text(response.text, f"Gemini model {model}")
        except Exception as exc:  # pragma: no cover - optional hosted provider path
            last_error = exc
            logger.warning("Gemini chat model %s failed, trying next model: %s", model, exc)
    raise last_error or ValueError("No Gemini chat models were configured.")


def _generate_text_with_openai(prompt: str, settings: Settings, usage: _UsageInfo) -> str:
    from openai import OpenAI

    client_kwargs = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)
    model = _model_for(settings, "openai", "chat")
    response = client.responses.create(
        model=model,
        input=prompt,
        temperature=0.2,
    )
    usage.model = model
    # This calls the Responses API (client.responses.create), NOT the older
    # Chat Completions API -- its usage object is `ResponseUsage`, with
    # `input_tokens`/`output_tokens`, not Chat Completions' `prompt_tokens`/
    # `completion_tokens`. Verified against the installed `openai` SDK's
    # `openai.types.responses.ResponseUsage`.
    response_usage = getattr(response, "usage", None)
    if response_usage is not None:
        usage.prompt_tokens = getattr(response_usage, "input_tokens", None)
        usage.completion_tokens = getattr(response_usage, "output_tokens", None)
    return _require_text(response.output_text, "OpenAI")


def _generate_text_with_anthropic(prompt: str, settings: Settings, usage: _UsageInfo) -> str:
    model = _model_for(settings, "anthropic", "chat")
    payload = {
        "model": model,
        "max_tokens": 240,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = _post_anthropic(payload, settings)
    usage.model = model
    call_usage = data.get("usage") or {}
    usage.prompt_tokens = call_usage.get("input_tokens")
    usage.completion_tokens = call_usage.get("output_tokens")
    return _require_text(_anthropic_text(data), "Anthropic")


def _generate_text_with_ollama(prompt: str, settings: Settings, usage: _UsageInfo) -> str:
    model = _model_for(settings, "ollama", "chat")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    data = _post_ollama(payload, settings)
    usage.model = model
    usage.prompt_tokens = data.get("prompt_eval_count")
    usage.completion_tokens = data.get("eval_count")
    return _require_text(data.get("message", {}).get("content"), "Ollama")


_TEXT_GENERATORS.update(
    {
        "gemini": _generate_text_with_gemini,
        "openai": _generate_text_with_openai,
        "anthropic": _generate_text_with_anthropic,
        "ollama": _generate_text_with_ollama,
    }
)


def _extract_inventory_with_gemini(
    image_path: str | Path,
    settings: Settings,
    usage: _UsageInfo,
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
            usage.model = model
            usage_metadata = getattr(response, "usage_metadata", None)
            if usage_metadata is not None:
                usage.prompt_tokens = getattr(usage_metadata, "prompt_token_count", None)
                usage.completion_tokens = getattr(usage_metadata, "candidates_token_count", None)
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
    usage: _UsageInfo,
) -> list[InventoryObservation]:
    from openai import OpenAI

    path = Path(image_path)
    data_url = _image_data_url(path)
    client_kwargs = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)
    model = _model_for(settings, "openai", "vision")
    response = client.responses.create(
        model=model,
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
    usage.model = model
    # Responses API usage shape -- see _generate_text_with_openai's comment.
    response_usage = getattr(response, "usage", None)
    if response_usage is not None:
        usage.prompt_tokens = getattr(response_usage, "input_tokens", None)
        usage.completion_tokens = getattr(response_usage, "output_tokens", None)
    return _observations_from_json_text(response.output_text or "", settings)


def _extract_inventory_with_anthropic(
    image_path: str | Path,
    settings: Settings,
    usage: _UsageInfo,
) -> list[InventoryObservation]:
    path = Path(image_path)
    model = _model_for(settings, "anthropic", "vision")
    payload = {
        "model": model,
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
    usage.model = model
    call_usage = data.get("usage") or {}
    usage.prompt_tokens = call_usage.get("input_tokens")
    usage.completion_tokens = call_usage.get("output_tokens")
    return _observations_from_json_text(_anthropic_text(data), settings)


def _extract_inventory_with_ollama(
    image_path: str | Path,
    settings: Settings,
    usage: _UsageInfo,
) -> list[InventoryObservation]:
    path = Path(image_path)
    model = _model_for(settings, "ollama", "vision")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": VISION_PROMPT, "images": [_base64_image(path)]}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    data = _post_ollama(payload, settings)
    usage.model = model
    usage.prompt_tokens = data.get("prompt_eval_count")
    usage.completion_tokens = data.get("eval_count")
    return _observations_from_json_text(data.get("message", {}).get("content", ""), settings)


_VISION_EXTRACTORS.update(
    {
        "gemini": _extract_inventory_with_gemini,
        "openai": _extract_inventory_with_openai,
        "anthropic": _extract_inventory_with_anthropic,
        "ollama": _extract_inventory_with_ollama,
    }
)


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
