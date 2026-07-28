import asyncio
import base64
import json
import random
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import requests
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.observability.llm_ledger import record_llm_call
from app.schemas.inventory import InventoryObservation
from app.services import llm_cache
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
    # Previously absent -- `_model_for(settings, "mock", kind)` only ever
    # avoided a `KeyError` here by luck of `usage.model or _model_for(...)`
    # short-circuit evaluation (every mock generator always sets
    # `usage.model = "mock"` first, so the right-hand `_model_for` call was
    # never actually evaluated). ROADMAP 2.3's cache-key computation calls
    # `_model_for` unconditionally (before any provider call has run, so
    # there is no `usage.model` yet to short-circuit on) -- giving mock a
    # real entry here fixes that latent fragility outright rather than
    # continuing to depend on call-site evaluation order.
    "mock": {"chat": "mock", "vision": "mock"},
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


class DetailedInstructions(BaseModel):
    """Structured-output schema for `generate_detailed_instructions_with_
    provider_chain` (ROADMAP 2.1). Replaces the old free-text numbered-list
    scrape (`_parse_numbered_steps`) as the primary path for every provider
    with a native structured-output mechanism; `_parse_numbered_steps` is
    kept as an ADDITIONAL parse-fallback safety net wired in via `generate_
    structured`'s `text_fallback` hook for Ollama/mock (see
    `_detailed_instructions_text_fallback` below), in case a local model
    ignores the JSON-mode instruction and just emits a numbered list like it
    always used to."""

    steps: list[str] = Field(default_factory=list)


class StructuredGenerationError(RuntimeError):
    """Raised by `generate_structured` when both the initial attempt and its
    one-shot repair retry fail to produce a schema-valid response. Callers
    that loop over `provider_chain()` (mirroring `_generate_text`'s existing
    contract) catch this exactly like any other provider failure and move
    on to the next provider."""


class _UsageInfo:
    """Mutable out-parameter each `_generate_text_with_*`/`_generate_
    structured_with_*` function fills in as a side effect (alongside its
    normal return value) when the provider response carries real usage
    metadata -- see `_generate_text`/`generate_structured` below, the two
    choke points that turn this into an `app.observability.llm_ledger.
    record_llm_call` row. `model` is set even on providers with no usage
    metadata (e.g. which of Gemini's per-model fallback list actually
    answered), so the ledger always knows what model served the call even
    when it doesn't know exactly how many tokens it used."""

    __slots__ = ("model", "prompt_tokens", "completion_tokens", "retries")

    def __init__(self) -> None:
        self.model: str | None = None
        self.prompt_tokens: int | None = None
        self.completion_tokens: int | None = None
        # Transient-failure retries consumed by THIS call (ROADMAP.md Phase
        # 2, Step 2.2) -- only ever incremented by the async HTTP choke point
        # (`_async_post_json`) on a 429/5xx/timeout. Always 0 on the sync
        # path (`_generate_text`) and unrelated to `generate_structured`'s
        # own repair-loop `retries` (a schema-validation retry, not a
        # transport retry) -- both land in the SAME `record_llm_call`
        # `retries` column (Step 2.1 already added it) since a caller only
        # ever goes through one path or the other for a given call, never
        # both.
        self.retries: int = 0


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
    `_generate_text`/`generate_structured` when the provider chain lands on
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
            result = generate_structured(
                provider,
                prompt,
                DetailedInstructions,
                settings,
                purpose="detailed_instructions",
                text_fallback=_detailed_instructions_text_fallback,
            )
            if result.steps:
                return result.steps, True
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


def _detailed_instructions_text_fallback(text: str) -> dict[str, Any]:
    """`generate_structured`'s `text_fallback` hook for `DetailedInstructions`
    -- only reached on the Ollama/mock `parse_fallback=True` path, and only
    when `_parse_json_object` can't find a `{...}` object at all (e.g. a
    local model ignores the JSON-mode instruction entirely and returns a
    plain numbered list like this feature used to expect everywhere).
    Recovers that via the same numbered-list parser this module always
    used, rather than treating the response as unusable."""
    return {"steps": _parse_numbered_steps(text)}


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
            if image_path is None:
                raise ValueError(f"{provider} vision requires an uploaded image path.")
            parsed = generate_structured(
                provider,
                VISION_PROMPT,
                _ProviderInventory,
                settings,
                purpose="vision_extract",
                image_path=image_path,
            )
            observations = [_provider_observation(item, settings) for item in parsed.items]
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
_StructuredGenerator = Callable[
    [str, Settings, "_UsageInfo", "type[BaseModel]", "str | Path | None"], str
]

_TEXT_GENERATORS: dict[str, _TextGenerator] = {}
_STRUCTURED_GENERATORS: dict[str, _StructuredGenerator] = {}

# Whether provider P's `_STRUCTURED_GENERATORS[P]` uses a NATIVE structured-
# output mechanism (Gemini `response_schema`, OpenAI Responses API
# `text.format` json_schema, Anthropic forced tool-use) vs. a JSON-mode
# prompt + regex/brace-scan extraction (`_parse_json_object`) because the
# provider has no native mechanism at all (Ollama, mock). Purely a ledger
# measurability signal (`record_llm_call`'s `parse_fallback` column, ROADMAP
# 2.1's acceptance criterion) -- static per provider, not computed per call
# (a native-mechanism provider that happens to return dirty text on one call
# is still recorded as `parse_fallback=False`; the flag answers "did this
# provider even attempt a schema-constrained call", not "did extraction take
# the easy path this time").
_STRUCTURED_PARSE_FALLBACK: dict[str, bool] = {
    "gemini": False,
    "openai": False,
    "anthropic": False,
    "ollama": True,
    "mock": True,
}


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


def generate_structured(
    provider: ProviderName,
    prompt: str,
    schema: type[BaseModel],
    settings: Settings,
    *,
    purpose: str,
    image_path: str | Path | None = None,
    text_fallback: Callable[[str], dict[str, Any]] | None = None,
) -> BaseModel:
    """The structured-output choke point (ROADMAP.md Phase 2, Step 2.1) --
    the schema-validated sibling of `_generate_text` above (and, since this
    step, the replacement for the old `_extract_inventory` vision
    chokepoint, which duplicated this same JSON-mode-prompt-plus-manual-
    parse pattern for every provider instead of using each one's real
    structured-output mechanism). Same ledger-instrumentation contract as
    `_generate_text`/`_extract_inventory` (timing, `record_llm_call` on both
    the success and failure path, `run_id`/`purpose` threading), plus two
    things those two don't need:

    - a one-shot "repair loop": on a JSON-parse or Pydantic-validation
      failure, retry exactly once with the validation errors appended to
      the prompt, then raise `StructuredGenerationError`. `retries` in the
      ledger row is 0 (succeeded first try) or 1 (needed the repair retry).
    - a `parse_fallback` flag (see `_STRUCTURED_PARSE_FALLBACK` above):
      True for Ollama/mock, which have no native structured-output
      mechanism and fall back to a JSON-mode prompt + `_parse_json_object`'s
      regex/brace-scan extraction; False for Gemini/OpenAI/Anthropic, which
      use their own native mechanism (`response_schema`, `text.format`
      json_schema, forced tool-use respectively) -- see each
      `_generate_structured_with_*` function below.

    `image_path`, when given, routes to the multimodal variant of the
    provider's structured call (mirrors `_extract_inventory`'s old vision
    path) -- `schema` describes the JSON shape either way, chat or vision.

    `text_fallback` is an OPTIONAL caller-supplied JSON extractor, tried
    only on the Ollama/mock `parse_fallback=True` path, only after
    `_parse_json_object`'s generic brace-scan fails to find a `{...}`
    object at all (NOT on a structurally-valid-but-wrong-shape response,
    which the repair loop above handles instead). Lets callers reuse a
    more domain-aware extractor than the generic one here -- e.g.
    `RecipeGenerationService` reuses its own battle-tested `_extract_json`
    (fenced-block + substring scan, already covered by
    tests/test_recipe_library_builder.py) instead of a second, weaker one.

    Response-level cache (ROADMAP.md Phase 2, Step 2.3): before calling any
    provider, checks `app.services.llm_cache` for a prior response to the
    exact same `(provider, model, purpose, prompt, schema)` -- see
    `llm_cache.build_cache_key`. Only attempted when `settings.
    llm_cache_enabled` is True, `image_path` is `None` (a vision call is
    NEVER cached here, structurally, regardless of what `purpose` says --
    see `llm_cache.TTL_BY_PURPOSE`'s `vision_extract` entry for why: the
    cache key does not include image bytes), and `purpose` has a configured
    TTL. A hit skips the real call entirely and records a ledger row with
    `cache_hit=True, success=True, cost_usd=0` (see the `record_llm_call`
    call site below) so `GET /admin/llm-usage` can report cache-hit
    savings; a miss falls through to the normal generate-and-validate flow
    below, then writes a fresh cache entry afterwards (only for purposes
    with a TTL -- `llm_cache.store_response` itself no-ops otherwise).
    """
    generator = _STRUCTURED_GENERATORS.get(provider)
    if generator is None:
        raise ValueError(f"Unsupported provider: {provider}")
    parse_fallback = _STRUCTURED_PARSE_FALLBACK.get(provider, False)
    kind = "vision" if image_path is not None else "chat"
    cache_model = _model_for(settings, provider, kind)

    cache_key: str | None = None
    if (
        settings.llm_cache_enabled
        and image_path is None
        and llm_cache.ttl_for_purpose(purpose) is not None
    ):
        cache_key = llm_cache.build_cache_key(provider, cache_model, purpose, prompt, schema)
        cached = llm_cache.get_cached_response(cache_key, schema)
        if cached is not None:
            record_llm_call(
                provider=provider,
                model=cache_model,
                purpose=purpose,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=0.0,
                success=True,
                fallback_used=_is_fallback_provider(provider, settings),
                cache_hit=True,
            )
            return cached

    usage = _UsageInfo()
    attempt_prompt = prompt
    retries = 0
    last_error: Exception | None = None
    result: BaseModel | None = None

    start = time.perf_counter()
    for attempt in range(2):
        try:
            raw_text = generator(attempt_prompt, settings, usage, schema, image_path)
            result = _validate_structured_payload(raw_text, schema, text_fallback)
            break
        except Exception as exc:  # noqa: BLE001 - repair loop treats JSON and schema failures alike
            last_error = exc
            if attempt == 0:
                retries = 1
                attempt_prompt = _append_repair_instructions(prompt, exc)
                continue
    elapsed_ms = (time.perf_counter() - start) * 1000

    if result is None:
        record_llm_call(
            provider=provider,
            model=usage.model or cache_model,
            purpose=purpose,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency_ms=elapsed_ms,
            success=False,
            fallback_used=_is_fallback_provider(provider, settings),
            prompt_text=prompt,
            retries=retries,
            parse_fallback=parse_fallback,
        )
        raise StructuredGenerationError(
            f"{provider} structured generation for {schema.__name__} failed after "
            f"{retries + 1} attempt(s): {last_error}"
        ) from last_error

    resolved_model = usage.model or cache_model
    record_llm_call(
        provider=provider,
        model=resolved_model,
        purpose=purpose,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        latency_ms=elapsed_ms,
        success=True,
        fallback_used=_is_fallback_provider(provider, settings),
        prompt_text=prompt,
        completion_text=result.model_dump_json(),
        retries=retries,
        parse_fallback=parse_fallback,
    )
    if cache_key is not None:
        llm_cache.store_response(cache_key, provider, resolved_model, purpose, result)
    return result


def _validate_structured_payload(
    raw_text: str,
    schema: type[BaseModel],
    text_fallback: Callable[[str], dict[str, Any]] | None,
) -> BaseModel:
    """Turn `raw_text` (a provider's raw completion) into a validated
    `schema` instance. Tries the generic brace-scan extractor first
    (`_parse_json_object`, already used by the old vision path); if THAT
    can't find any `{...}` object at all and the caller supplied
    `text_fallback`, tries that instead. Either way, a structurally-valid-
    but-wrong-shape result still raises `pydantic.ValidationError` here,
    which `generate_structured`'s repair loop (not this function) is
    responsible for retrying."""
    try:
        payload = _parse_json_object(raw_text)
    except (json.JSONDecodeError, ValueError):
        if text_fallback is None:
            raise
        payload = text_fallback(raw_text)
    return schema.model_validate(payload)


def _append_repair_instructions(prompt: str, error: Exception) -> str:
    """Build the one-shot "repair loop" retry prompt (ROADMAP 2.1): the
    original prompt plus the validation/parse errors from the first
    attempt, asking for corrected JSON only. Never used more than once per
    `generate_structured` call -- see its `for attempt in range(2)` loop."""
    return (
        f"{prompt}\n\n"
        "Your previous response did not match the required JSON schema. "
        f"Validation errors:\n{error}\n\n"
        "Return ONLY corrected JSON satisfying the schema -- fix these "
        "errors, do not add commentary or markdown fences."
    )


def _model_json_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema for `schema`, in the plain-dict flavor every native
    structured-output mechanism below accepts directly: Gemini's SDK takes
    a raw dict for `response_schema` (see `_gemini_generate_config`),
    OpenAI's Responses API `text.format` takes a JSON Schema dict, and
    Anthropic's tool `input_schema` is JSON Schema too."""
    return schema.model_json_schema()


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


# --- Async provider choke point (ROADMAP.md Phase 2, Step 2.2) ---
#
# Retry/backoff budget for the ASYNC HTTP choke point below -- deliberately
# separate from, and much tighter than, usda_client.py's _MAX_ATTEMPTS/
# _RETRY_BACKOFF_SECONDS (8 attempts, no jitter): that client is only ever
# driven by an offline batch job with no user waiting on it (see its own
# module comment), while this one sits directly on a request a live user IS
# waiting on. 2 retries (3 attempts total), exponential backoff WITH jitter
# (usda_client.py's fixed-tuple backoff has none -- a single offline batch
# job has no "many concurrent retrying clients stampeding in lockstep"
# concern to avoid), and -- unlike usda_client's blanket "any transient
# failure" retry -- ONLY on a 429, a 5xx, or a timeout; any other 4xx (bad
# request, bad auth, ...) will never succeed on retry and fails immediately.
_ASYNC_HTTP_MAX_RETRIES = 2
_ASYNC_HTTP_BASE_BACKOFF_SECONDS = 1.0


def _is_retryable_async_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def _async_backoff_seconds(attempt: int) -> float:
    """Exponential backoff with full jitter for (0-indexed) `attempt`:
    doubles the base delay each retry, then returns a uniformly random value
    in `[0, that delay]` -- the "full jitter" shape (AWS's architecture-blog
    recommendation for a fleet of independently-retrying clients) that keeps
    many concurrent failed requests from retrying in lockstep."""
    max_delay = _ASYNC_HTTP_BASE_BACKOFF_SECONDS * (2**attempt)
    return random.uniform(0, max_delay)


async def _async_post_json(
    async_client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    json_payload: dict[str, Any],
    timeout: float,
    usage: "_UsageInfo",
) -> dict[str, Any]:
    """The single async HTTP choke point in this module -- every async
    provider call that speaks raw HTTP directly (Anthropic, Ollama; Gemini/
    OpenAI's async SDK clients manage their own transport/retries, so they
    never route through here -- see `_generate_text_with_gemini_async`/
    `_generate_text_with_openai_async`) goes through this one function.
    Retries up to `_ASYNC_HTTP_MAX_RETRIES` times with backoff + jitter (see
    the module comment above `_ASYNC_HTTP_MAX_RETRIES`), ONLY on a 429, a
    5xx, or a timeout. Every retry increments `usage.retries` so `record_
    llm_call`'s existing `retries` column (Step 2.1) captures it -- see
    `_UsageInfo.retries`; no parallel field.

    Raises `httpx.TimeoutException`/`httpx.HTTPStatusError` (unwrapped) once
    the retry budget is exhausted -- callers (the `_generate_text_with_*_
    async` functions) let this propagate; `agenerate_text`/`agenerate_text_
    batch` are what turn it into a ledger `success=False` row / a collected
    error string, matching how the sync `_generate_text` choke point already
    treats any provider exception (see its `except Exception` block).
    """
    last_exc: Exception | None = None
    for attempt in range(_ASYNC_HTTP_MAX_RETRIES + 1):
        try:
            response = await async_client.post(
                url, headers=headers, json=json_payload, timeout=timeout
            )
        except httpx.TimeoutException as exc:
            last_exc = exc
            if attempt >= _ASYNC_HTTP_MAX_RETRIES:
                raise
            usage.retries += 1
            await asyncio.sleep(_async_backoff_seconds(attempt))
            continue

        if _is_retryable_async_status(response.status_code):
            if attempt >= _ASYNC_HTTP_MAX_RETRIES:
                response.raise_for_status()
            usage.retries += 1
            await asyncio.sleep(_async_backoff_seconds(attempt))
            continue

        response.raise_for_status()
        return response.json()

    # Unreachable in practice: every loop iteration either returns, raises
    # directly, or -- on the final attempt -- calls raise_for_status()/
    # re-raises, which always raises for a still-retryable outcome. Kept as
    # an explicit fail-loud fallback rather than letting the function fall
    # off the end and return None.
    raise last_exc or RuntimeError(
        f"Async provider request to {url} failed with no captured error."
    )


async def _generate_text_with_anthropic_async(
    prompt: str, settings: Settings, usage: _UsageInfo, async_client: httpx.AsyncClient
) -> str:
    """Async sibling of `_generate_text_with_anthropic` -- routes through
    `_async_post_json` (this module's async HTTP choke point) instead of
    `requests.post`/`_post_anthropic`."""
    model = _model_for(settings, "anthropic", "chat")
    payload = {
        "model": model,
        "max_tokens": 240,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = await _async_post_json(
        async_client,
        f"{settings.anthropic_base_url.rstrip('/')}/messages",
        headers={
            "x-api-key": settings.anthropic_api_key or "",
            "anthropic-version": settings.anthropic_api_version,
            "content-type": "application/json",
        },
        json_payload=payload,
        timeout=settings.model_timeout_seconds,
        usage=usage,
    )
    usage.model = model
    call_usage = data.get("usage") or {}
    usage.prompt_tokens = call_usage.get("input_tokens")
    usage.completion_tokens = call_usage.get("output_tokens")
    return _require_text(_anthropic_text(data), "Anthropic")


async def _generate_text_with_ollama_async(
    prompt: str, settings: Settings, usage: _UsageInfo, async_client: httpx.AsyncClient
) -> str:
    """Async sibling of `_generate_text_with_ollama` -- routes through
    `_async_post_json` instead of `requests.post`/`_post_ollama`."""
    model = _model_for(settings, "ollama", "chat")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    data = await _async_post_json(
        async_client,
        f"{settings.ollama_base_url.rstrip('/')}/api/chat",
        headers={},
        json_payload=payload,
        timeout=settings.model_timeout_seconds,
        usage=usage,
    )
    usage.model = model
    usage.prompt_tokens = data.get("prompt_eval_count")
    usage.completion_tokens = data.get("eval_count")
    return _require_text(data.get("message", {}).get("content"), "Ollama")


async def _generate_text_with_gemini_async(
    prompt: str, settings: Settings, usage: _UsageInfo, async_client: httpx.AsyncClient | None
) -> str:
    """Async sibling of `_generate_text_with_gemini` -- uses Gemini's own
    async SDK client (`google.genai.Client.aio`), NOT the `_async_post_json`
    choke point above (`async_client` is accepted only so every entry in
    `_ASYNC_TEXT_GENERATORS` shares one call signature; unused here since
    the SDK manages its own transport/retries for the hosted Gemini API).
    Otherwise mirrors the sync version's per-model fallback loop exactly."""
    del async_client
    from google.genai import types

    client = _gemini_client(settings)
    last_error: Exception | None = None
    for model in _models_for(settings, "gemini", "chat"):
        try:
            response = await client.aio.models.generate_content(
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
            logger.warning("Gemini async chat model %s failed, trying next model: %s", model, exc)
    raise last_error or ValueError("No Gemini chat models were configured.")


async def _generate_text_with_openai_async(
    prompt: str, settings: Settings, usage: _UsageInfo, async_client: httpx.AsyncClient | None
) -> str:
    """Async sibling of `_generate_text_with_openai` -- uses OpenAI's own
    async SDK client (`openai.AsyncOpenAI`), NOT the `_async_post_json`
    choke point (same reasoning as `_generate_text_with_gemini_async`)."""
    del async_client
    from openai import AsyncOpenAI

    client_kwargs = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = AsyncOpenAI(**client_kwargs)
    model = _model_for(settings, "openai", "chat")
    response = await client.responses.create(model=model, input=prompt, temperature=0.2)
    usage.model = model
    response_usage = getattr(response, "usage", None)
    if response_usage is not None:
        usage.prompt_tokens = getattr(response_usage, "input_tokens", None)
        usage.completion_tokens = getattr(response_usage, "output_tokens", None)
    return _require_text(response.output_text, "OpenAI")


_AsyncTextGenerator = Callable[
    [str, Settings, "_UsageInfo", "httpx.AsyncClient | None"], Awaitable[str]
]

_ASYNC_TEXT_GENERATORS: dict[str, _AsyncTextGenerator] = {
    "gemini": _generate_text_with_gemini_async,
    "openai": _generate_text_with_openai_async,
    "anthropic": _generate_text_with_anthropic_async,
    "ollama": _generate_text_with_ollama_async,
}


async def agenerate_text(
    provider: ProviderName,
    prompt: str,
    settings: Settings,
    *,
    purpose: str = "unspecified",
    async_client: httpx.AsyncClient | None = None,
) -> str:
    """Async sibling of `_generate_text` (ROADMAP.md Phase 2, Step 2.2) --
    same `record_llm_call` ledger instrumentation contract (timing,
    success/failure, `retries`), just awaited instead of blocking. `async_
    client` is the injectable `httpx.AsyncClient` used by the Anthropic/
    Ollama async generators' `_async_post_json` calls (tests inject one
    backed by `httpx.MockTransport`); Gemini/OpenAI ignore it (see their
    async generators' docstrings). A caller that doesn't inject one gets a
    fresh `httpx.AsyncClient()` per call -- fine for a single call, but a
    caller making many concurrent calls (see `agenerate_text_batch`) should
    inject one shared client so connections are pooled."""
    generator = _ASYNC_TEXT_GENERATORS.get(provider)
    if generator is None:
        raise ValueError(f"Unsupported provider: {provider}")

    usage = _UsageInfo()
    start = time.perf_counter()
    owns_client = async_client is None
    client = async_client if async_client is not None else httpx.AsyncClient()
    try:
        text = await generator(prompt, settings, usage, client)
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
            retries=usage.retries,
        )
        raise
    finally:
        if owns_client:
            await client.aclose()

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
        retries=usage.retries,
    )
    return text


async def agenerate_text_batch(
    provider: ProviderName,
    prompts: list[str],
    settings: Settings,
    *,
    purpose: str = "unspecified",
    max_concurrency: int | None = None,
    async_client: httpx.AsyncClient | None = None,
) -> tuple[list[str | None], list[str]]:
    """Bounded-concurrency fan-out over `agenerate_text` (ROADMAP.md Phase 2,
    Step 2.2) -- issues every prompt in `prompts` concurrently, gated by an
    `asyncio.Semaphore` sized from `max_concurrency` (default: `Settings.
    llm_max_concurrency`, env `LLM_MAX_CONCURRENCY`).

    Returns `(results, errors)`: `results[i]` is `prompts[i]`'s completion,
    or `None` if that one call failed after its retry budget (a timeout or
    any other exception) -- one bad prompt never takes down the whole batch.
    `errors` collects one human-readable message per failure (empty-list
    convention matches `RecommendationResponse.errors`/`DiscoveryResponse.
    errors`, i.e. "readable partial-failure message, not a raised
    exception/500" -- see app/schemas/recommendation.py and app/schemas/
    library.py). Every completed call (success or failure) is still recorded
    to the LLM ledger individually by the underlying `agenerate_text` call.
    """
    semaphore = asyncio.Semaphore(max_concurrency or settings.llm_max_concurrency)
    owns_client = async_client is None
    client = async_client if async_client is not None else httpx.AsyncClient()

    async def _one(index: int, prompt: str) -> tuple[int, str | None, str | None]:
        async with semaphore:
            try:
                text = await agenerate_text(
                    provider, prompt, settings, purpose=purpose, async_client=client
                )
                return index, text, None
            except Exception as exc:  # noqa: BLE001 - collected as a readable error, not raised
                return index, None, f"prompt {index}: {provider} generation failed: {exc}"

    try:
        outcomes = await asyncio.gather(*(_one(i, p) for i, p in enumerate(prompts)))
    finally:
        if owns_client:
            await client.aclose()

    results: list[str | None] = [None] * len(prompts)
    errors: list[str] = []
    for index, text, error in sorted(outcomes, key=lambda item: item[0]):
        results[index] = text
        if error is not None:
            errors.append(error)
    return results, errors


def _generate_structured_with_gemini(
    prompt: str,
    settings: Settings,
    usage: _UsageInfo,
    schema: type[BaseModel],
    image_path: str | Path | None,
) -> str:
    """Gemini's native structured-output mechanism: `response_mime_type=
    "application/json"` + an explicit `response_schema` (ROADMAP 2.1 --
    previously only the mime-type half of this was set, for vision only;
    every call through here now also passes the target JSON Schema, for
    both chat and vision)."""
    from google.genai import types

    client = _gemini_client(settings)
    kind = "vision" if image_path is not None else "chat"
    contents: Any
    if image_path is not None:
        path = Path(image_path)
        image_part = types.Part.from_bytes(
            data=path.read_bytes(), mime_type=_guess_image_mime_type(path)
        )
        contents = [image_part, prompt]
    else:
        contents = prompt

    last_error: Exception | None = None
    for model in _models_for(settings, "gemini", kind):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=_gemini_generate_config(
                    types,
                    settings,
                    model=model,
                    temperature=0 if image_path is not None else 0.2,
                    response_mime_type="application/json",
                    response_schema=_model_json_schema(schema),
                ),
            )
            usage.model = model
            usage_metadata = getattr(response, "usage_metadata", None)
            if usage_metadata is not None:
                usage.prompt_tokens = getattr(usage_metadata, "prompt_token_count", None)
                usage.completion_tokens = getattr(usage_metadata, "candidates_token_count", None)
            return _require_text(response.text, f"Gemini model {model}")
        except Exception as exc:  # pragma: no cover - optional hosted provider path
            last_error = exc
            logger.warning("Gemini structured model %s failed, trying next model: %s", model, exc)
    raise last_error or ValueError("No Gemini models were configured.")


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
    response_schema: dict[str, Any] | None = None,
):
    config_kwargs: dict[str, Any] = {"temperature": temperature}
    if response_mime_type:
        config_kwargs["response_mime_type"] = response_mime_type
    if response_schema is not None:
        # The SDK accepts a plain JSON-Schema dict directly for
        # `response_schema` (see `google.genai.types.GenerateContentConfig`
        # -- verified against the installed google-genai 2.x signature,
        # which types this as `dict[Any, Any] | type | types.Schema | ...`).
        config_kwargs["response_schema"] = response_schema

    thinking_kwargs: dict[str, Any] = {}
    if settings.gemini_thinking_level and model.startswith("gemini-3"):
        thinking_kwargs["thinking_level"] = settings.gemini_thinking_level
    if settings.gemini_thinking_budget is not None:
        thinking_kwargs["thinking_budget"] = settings.gemini_thinking_budget
    if thinking_kwargs:
        config_kwargs["thinking_config"] = types_module.ThinkingConfig(**thinking_kwargs)

    return types_module.GenerateContentConfig(**config_kwargs)


# OpenAI's Responses API structured-output tool names / max_tokens for
# Anthropic's forced tool-use are separate constants from the plain-chat
# path's -- see ANTHROPIC_STRUCTURED_MAX_TOKENS below for why.


def _generate_structured_with_openai(
    prompt: str,
    settings: Settings,
    usage: _UsageInfo,
    schema: type[BaseModel],
    image_path: str | Path | None,
) -> str:
    """OpenAI's native structured-output mechanism on the Responses API
    (`client.responses.create`, NOT Chat Completions -- confirmed against
    the installed `openai` 2.x SDK, `openai.types.responses.response_text_
    config_param.ResponseTextConfigParam`/`response_format_text_json_
    schema_config_param.ResponseFormatTextJSONSchemaConfigParam`): pass
    `text={"format": {"type": "json_schema", "schema": ...}}`, the Responses-
    API equivalent of Chat Completions' `response_format={"type":
    "json_schema", ...}` (the roadmap's suggested shape, which does NOT
    exist on this API). Deliberately NOT `strict: True` -- OpenAI's strict
    mode additionally requires every property be listed as `required` (with
    `null` folded into the type for anything optional) and `additionalProp
    erties: false` on every nested object, which `Pydantic.model_json_
    schema()` does not produce out of the box for models with optional/
    default fields (all three schemas this module passes here have several)
    -- adding a schema-flattening transform to satisfy strict mode was out
    of scope for this pass; non-strict json_schema mode still constrains
    the model's output shape, and `generate_structured`'s own Pydantic
    validation + repair loop catch anything that still doesn't conform.
    """
    from openai import OpenAI

    client_kwargs = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)
    kind = "vision" if image_path is not None else "chat"
    model = _model_for(settings, "openai", kind)

    if image_path is not None:
        data_url = _image_data_url(Path(image_path))
        input_payload: Any = [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ]
        temperature = 0
    else:
        input_payload = prompt
        temperature = 0.2

    response = client.responses.create(
        model=model,
        input=input_payload,
        temperature=temperature,
        text={
            "format": {
                "type": "json_schema",
                "name": schema.__name__.lstrip("_"),
                "schema": _model_json_schema(schema),
                "strict": False,
            }
        },
    )
    usage.model = model
    # Responses API usage shape -- see _generate_text_with_openai's comment.
    response_usage = getattr(response, "usage", None)
    if response_usage is not None:
        usage.prompt_tokens = getattr(response_usage, "input_tokens", None)
        usage.completion_tokens = getattr(response_usage, "output_tokens", None)
    return _require_text(response.output_text, "OpenAI")


# Anthropic's forced tool-use `input` is already a JSON object off the wire
# (not a text blob to scrape) -- this module still json.dumps it back into
# text so `generate_structured` has exactly one parse path
# (`_validate_structured_payload` -> `_parse_json_object`) regardless of
# provider, rather than a special case for Anthropic. Raised well above the
# plain-chat path's 240/700-token caps (see `_generate_text_with_anthropic`
# / `_extract_inventory_with_anthropic`'s history -- git blame shows no
# documented rationale for those two beyond "small enough for a short
# rewrite/short item list"): a forced-tool-use structured call encodes a
# full JSON schema's worth of field names/punctuation per candidate and,
# for recipe generation, can be asked for up to 50 recipes
# (`RecipeDiscoveryRequest.count`, `app/schemas/library.py`) each with a
# full ingredient/instruction list -- 240 tokens would truncate on the
# first candidate.
ANTHROPIC_STRUCTURED_MAX_TOKENS = 4096


def _anthropic_tool_name(schema: type[BaseModel]) -> str:
    return schema.__name__.lstrip("_") or "structured_output"


def _generate_structured_with_anthropic(
    prompt: str,
    settings: Settings,
    usage: _UsageInfo,
    schema: type[BaseModel],
    image_path: str | Path | None,
) -> str:
    """Anthropic's native structured-output mechanism: forced tool-use with
    a single tool whose `input_schema` is `schema`'s JSON Schema and
    `tool_choice` pinned to that one tool by name, so the model has no
    choice but to call it (rather than replying with prose)."""
    kind = "vision" if image_path is not None else "chat"
    model = _model_for(settings, "anthropic", kind)
    tool_name = _anthropic_tool_name(schema)

    content: Any
    if image_path is not None:
        path = Path(image_path)
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _guess_image_mime_type(path),
                    "data": _base64_image(path),
                },
            },
            {"type": "text", "text": prompt},
        ]
        temperature = 0
    else:
        content = prompt
        temperature = 0.2

    payload = {
        "model": model,
        "max_tokens": ANTHROPIC_STRUCTURED_MAX_TOKENS,
        "temperature": temperature,
        "messages": [{"role": "user", "content": content}],
        "tools": [
            {
                "name": tool_name,
                "description": f"Return {schema.__name__} as structured JSON.",
                "input_schema": _model_json_schema(schema),
            }
        ],
        "tool_choice": {"type": "tool", "name": tool_name},
    }
    data = _post_anthropic(payload, settings)
    usage.model = model
    call_usage = data.get("usage") or {}
    usage.prompt_tokens = call_usage.get("input_tokens")
    usage.completion_tokens = call_usage.get("output_tokens")
    return json.dumps(_anthropic_tool_input(data, tool_name))


def _anthropic_tool_input(data: dict[str, Any], tool_name: str) -> dict[str, Any]:
    for part in data.get("content", []):
        if not isinstance(part, dict):
            continue
        if part.get("type") == "tool_use" and part.get("name") == tool_name:
            return part.get("input") or {}
    raise ValueError(f"Anthropic response did not include a {tool_name!r} tool_use block.")


def _json_mode_prompt(prompt: str, schema: type[BaseModel]) -> str:
    """Ollama has no native structured-output mechanism (ROADMAP 2.1) --
    append the target JSON Schema to the prompt and ask for JSON-only
    output. The `/api/chat` payload's `format: "json"` (below) additionally
    constrains Ollama's decoding to syntactically-valid JSON -- NOT schema
    conformance, which is still enforced afterwards by
    `schema.model_validate` (with `generate_structured`'s repair loop as
    the safety net if it doesn't conform)."""
    return (
        f"{prompt}\n\n"
        "Respond with JSON only, matching this JSON Schema exactly "
        f"(no commentary, no markdown fences):\n{json.dumps(_model_json_schema(schema))}"
    )


def _generate_structured_with_ollama(
    prompt: str,
    settings: Settings,
    usage: _UsageInfo,
    schema: type[BaseModel],
    image_path: str | Path | None,
) -> str:
    kind = "vision" if image_path is not None else "chat"
    model = _model_for(settings, "ollama", kind)
    message: dict[str, Any] = {"role": "user", "content": _json_mode_prompt(prompt, schema)}
    if image_path is not None:
        message["images"] = [_base64_image(Path(image_path))]
    payload = {
        "model": model,
        "messages": [message],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0 if image_path is not None else 0.2},
    }
    data = _post_ollama(payload, settings)
    usage.model = model
    usage.prompt_tokens = data.get("prompt_eval_count")
    usage.completion_tokens = data.get("eval_count")
    return _require_text(data.get("message", {}).get("content"), "Ollama")


def _generate_structured_with_mock(
    prompt: str,
    settings: Settings,
    usage: _UsageInfo,
    schema: type[BaseModel],
    image_path: str | Path | None,
) -> str:
    """Mock provider's structured "response" -- makes no HTTP call (like
    every other mock-mode code path in this module) and deliberately is NOT
    clean JSON (wrapped in a chatty preamble + markdown fence), so
    `generate_structured` is forced through the same `_parse_json_object`
    brace-scan fallback path Ollama uses, rather than a trivial happy-path
    parse. This makes `generate_structured("mock", ...)` directly testable/
    measurable in isolation for ANY schema (see tests/test_model_provider.py)
    -- but note the three higher-level callers in this module
    (`RecipeGenerationService.generate`, `generate_detailed_instructions_
    with_provider_chain`, `extract_inventory_with_provider_chain`) all still
    special-case `provider == "mock"` BEFORE ever reaching this function,
    returning canned/deterministic data via `_record_mock_call` with no LLM
    call at all -- unchanged from before ROADMAP 2.1, and pinned by
    tests/test_llm_ledger.py's mock-path ledger tests.
    """
    del prompt, settings, image_path  # unused: mock never inspects the prompt or calls a network
    usage.model = "mock"
    example = _mock_schema_example(schema)
    return f"Sure! Here is the JSON you asked for:\n```json\n{json.dumps(example)}\n```"


def _mock_schema_example(schema: type[BaseModel]) -> dict[str, Any]:
    """Best-effort placeholder JSON for `schema`'s REQUIRED fields, built
    generically off its JSON Schema (never off domain knowledge of any
    specific schema) -- so `_generate_structured_with_mock` above works for
    any schema passed to `generate_structured`, not just the ones this
    module happens to define today."""
    root = _model_json_schema(schema)
    return _mock_value_for_node(root, root.get("$defs", {}))


def _mock_value_for_node(node: dict[str, Any], defs: dict[str, Any]) -> Any:
    if "$ref" in node:
        ref_name = node["$ref"].rsplit("/", 1)[-1]
        return _mock_value_for_node(defs.get(ref_name, {}), defs)
    node_type = node.get("type")
    if node_type == "object" or "properties" in node:
        properties = node.get("properties", {})
        required = node.get("required", [])
        return {
            name: _mock_value_for_node(prop, defs)
            for name, prop in properties.items()
            if name in required
        }
    if node_type == "array":
        return []
    if node_type == "string":
        return "mock"
    if node_type == "integer":
        return 0
    if node_type == "number":
        return 0.0
    if node_type == "boolean":
        return False
    return None


_STRUCTURED_GENERATORS.update(
    {
        "gemini": _generate_structured_with_gemini,
        "openai": _generate_structured_with_openai,
        "anthropic": _generate_structured_with_anthropic,
        "ollama": _generate_structured_with_ollama,
        "mock": _generate_structured_with_mock,
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
