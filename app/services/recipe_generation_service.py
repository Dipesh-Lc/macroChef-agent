import json
import re
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.config import get_settings
from app.observability.llm_ledger import record_llm_call
from app.schemas.library import RecipeDiscoveryRequest
from app.schemas.recipe_candidate import RecipeCandidate
from app.services.model_provider import (  # type: ignore[attr-defined]
    _is_fallback_provider,
    generate_structured,
)
from app.utils.quantity_parser import parse_quantity_string


class _RecipeCandidatePayload(BaseModel):
    """Structured-output schema for `RecipeGenerationService`'s prompt
    (ROADMAP 2.1) -- a plain, loosely-typed mirror of the prompt's field
    list in `_prompt` below, deliberately NOT `RecipeCandidate` itself:
    `RecipeCandidate` has a `derived_allergens` computed field the model
    must never be asked to fill in (it's deterministically derived, see
    that field's docstring), and its `ingredients` field is the fully-typed
    `Ingredient` model, while this LLM-facing schema keeps ingredients as
    loose strings (e.g. "150 g chicken breast") so the existing, already-
    tested `_sanitize_candidate_payload` -> `RecipeCandidate.model_validate`
    pipeline (which already parses that shape via
    `app.utils.quantity_parser`) stays the single place ingredient strings
    get turned into {name, amount, unit}."""

    candidate_id: str | None = None
    title: str
    cuisine: str | None = None
    meal_type: str | None = None
    description: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    cook_time_min: int | None = None
    difficulty: str | None = None
    servings: int | None = None
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    allergens: list[str] = Field(default_factory=list)
    diet_tags: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    image_url: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    home_cookable_score: float | None = None
    validation_warnings: list[str] = Field(default_factory=list)


class _RecipeCandidateBatch(BaseModel):
    """Root object every provider is asked to return -- an OBJECT, not a
    bare JSON array, since `model_provider._parse_json_object`'s brace-scan
    (reused by `generate_structured` for the Ollama/mock fallback path)
    only recognizes `{...}`, and every native structured-output mechanism
    (Gemini/OpenAI/Anthropic) requires an object-shaped JSON Schema root
    too."""

    candidates: list[_RecipeCandidatePayload] = Field(default_factory=list)


class RecipeGenerationService:
    """LLM-backed recipe generation behind a strict schema boundary."""

    def generate(self, request: RecipeDiscoveryRequest) -> list[RecipeCandidate]:
        settings = get_settings()
        if settings.model_provider == "mock":
            # This bypasses generate_structured entirely (mock mode makes no
            # HTTP call at all), so record the ledger row here directly --
            # same convention as model_provider._record_mock_call, kept
            # local since this call site is settings.model_provider-driven,
            # not a provider_chain() loop.
            record_llm_call(
                provider="mock",
                model="mock",
                purpose="recipe_generation",
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=0.0,
                success=True,
                fallback_used=_is_fallback_provider("mock", settings),
            )
            return []

        prompt = self._prompt(request)
        # NOTE: this calls model_provider.generate_structured directly
        # rather than going through provider_chain()/generate_detailed_
        # instructions_with_provider_chain's fallback-and-retry pattern --
        # a known pre-existing quirk of this service, not introduced or
        # fixed here (see ROADMAP 1.2 task notes). Ledger purpose tag:
        # "recipe_generation". `text_fallback` reuses this service's own
        # battle-tested `_extract_json` (fenced-block + substring scan) as
        # the Ollama/mock parse_fallback extractor, rather than a second,
        # weaker one -- see `generate_structured`'s `text_fallback` docstring.
        batch = generate_structured(
            settings.model_provider,
            prompt,
            _RecipeCandidateBatch,
            settings,
            purpose="recipe_generation",
            text_fallback=self._text_fallback,
        )
        candidates: list[RecipeCandidate] = []
        for payload_item in batch.candidates:
            item = self._sanitize_candidate_payload(payload_item.model_dump())
            candidates.append(RecipeCandidate.model_validate(item))
        return candidates

    def _text_fallback(self, text: str) -> dict[str, Any]:
        """`generate_structured`'s `text_fallback` hook for
        `_RecipeCandidateBatch` -- only reached on the Ollama/mock
        `parse_fallback=True` path, and only when `_parse_json_object` can't
        find a `{...}` object at all. Reuses `_extract_json` below, which
        already handles a bare JSON array, a markdown-fenced block, or a
        `{"candidates": [...]}`/`{"recipes": [...]}` wrapper -- whichever
        shape a less-compliant model actually returns."""
        return {"candidates": self._extract_json(text)}

    def _prompt(self, request: RecipeDiscoveryRequest) -> str:
        return f"""
Return strict JSON only: an object {{"candidates": [...]}} whose "candidates" array
holds recipe candidate objects compatible with this schema:
candidate_id, title, cuisine, meal_type, description, ingredients, instructions,
cook_time_min, difficulty, servings, calories, protein_g, carbs_g, fat_g, fiber_g,
allergens, diet_tags, equipment, image_url, source_type, source_name, home_cookable_score,
validation_warnings.

Create {request.count} home-cookable recipes.
Cuisines: {request.cuisines or ["Any"]}.
Meal type: {request.meal_type or "any"}.
Diet type: {request.diet_type or "none"}.
Max cook time minutes: {request.max_cook_time_min or "none"}.
Difficulty: {request.difficulty or "any"}.
Avoid allergens: {request.allergies}.
Avoid ingredients: {request.excluded_ingredients}.
Extra preferences: {request.extra_preferences or "none"}.

Use quantified ingredients such as "150 g chicken breast" or "1 medium egg".
Avoid deep frying and restaurant-only equipment. Do not include medical claims.
Set source_type to "ai_generated". Mark nutrition as estimated in validation_warnings.
"""

    def _extract_json(self, text: str) -> list[dict[str, Any]]:
        data = self._decode_json_payload(text)
        if isinstance(data, dict) and "candidates" in data:
            data = data["candidates"]
        if isinstance(data, dict) and "recipes" in data:
            data = data["recipes"]
        if not isinstance(data, list):
            raise ValueError("Recipe generation did not return a JSON array.")
        return [item for item in data if isinstance(item, dict)]

    def _decode_json_payload(self, text: str) -> Any:
        candidates = [text.strip()]
        fenced_blocks = re.finditer(r"```(?:json)?\s*(.*?)```", text, re.S)
        candidates.extend(match.group(1).strip() for match in fenced_blocks)
        candidates.extend(self._json_substrings(text))

        last_error: Exception | None = None
        for candidate in candidates:
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                last_error = exc
        preview = text.strip().replace("\n", " ")[:240]
        raise ValueError(f"Recipe generation returned non-JSON content: {preview}") from last_error

    def _json_substrings(self, text: str) -> list[str]:
        decoder = json.JSONDecoder()
        snippets: list[str] = []
        for index, char in enumerate(text):
            if char not in "[{":
                continue
            try:
                _, end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            snippets.append(text[index : index + end])
        return snippets

    def _sanitize_candidate_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        # `item.get(...)`, not `setdefault`: since `_RecipeCandidatePayload.
        # model_dump()` (ROADMAP 2.1) always includes "candidate_id" as a
        # key (explicitly `None` when the model didn't supply one), a plain
        # `setdefault` would never fire -- it only sets a MISSING key, and
        # this key is always present. A falsy check covers both "missing"
        # (the pre-2.1 raw-dict shape, still exercised directly by
        # tests/test_recipe_library_builder.py) and "present but None"
        # (the new schema-validated shape) identically.
        if not item.get("candidate_id"):
            item["candidate_id"] = f"llm_{uuid4().hex[:12]}"
        item["source_type"] = "ai_generated"
        item["ingredients"] = self._coerce_ingredient_list(item.get("ingredients"))
        item["instructions"] = self._coerce_string_list(item.get("instructions"))
        item["allergens"] = self._coerce_string_list(item.get("allergens"))
        item["diet_tags"] = self._coerce_string_list(item.get("diet_tags"))
        item["equipment"] = self._coerce_string_list(item.get("equipment"))

        for field in [
            "cook_time_min",
            "servings",
            "calories",
            "protein_g",
            "carbs_g",
            "fat_g",
            "fiber_g",
        ]:
            item[field] = self._coerce_number(item.get(field))

        item["home_cookable_score"] = self._coerce_score(item.get("home_cookable_score"))
        warnings = self._coerce_string_list(item.get("validation_warnings"))
        if "Nutrition is an estimate generated by an AI model." not in warnings:
            warnings.append("Nutrition is an estimate generated by an AI model.")
        item["validation_warnings"] = warnings
        return item

    def _coerce_ingredient_list(self, value: Any) -> list[dict[str, Any]]:
        """Coerce LLM ingredient output into {name, amount, unit} dicts.

        Preserves structure rather than flattening back to strings: structured
        dicts keep their amount/unit, and quantified strings ("150 g chicken
        breast") are parsed. Returned dicts are validated into `Ingredient` by
        the `RecipeCandidate` schema.
        """

        def from_string(text: str) -> dict[str, Any]:
            return dict(parse_quantity_string(text))

        if value is None:
            return []
        if isinstance(value, str):
            separators = "\n" if "\n" in value else ","
            parts = [part.strip(" -\t") for part in value.split(separators) if part.strip(" -\t")]
            return [from_string(part) for part in parts]
        if isinstance(value, list):
            result: list[dict[str, Any]] = []
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("ingredient") or item.get("item") or ""
                    amount = item.get("amount", item.get("quantity"))
                    unit = item.get("unit")
                    if isinstance(amount, str):
                        # amount may be "150" or "150 g" — reparse the combined text.
                        combined = " ".join(str(x) for x in [amount, unit, name] if x).strip()
                        result.append(from_string(combined))
                    else:
                        result.append({"name": str(name).strip(), "amount": amount, "unit": unit})
                elif isinstance(item, str) and item.strip():
                    result.append(from_string(item))
                elif item is not None:
                    result.append(from_string(str(item)))
            return [entry for entry in result if entry.get("name")]
        text = str(value).strip()
        return [from_string(text)] if text else []

    def _coerce_string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            separators = "\n" if "\n" in value else ","
            return [item.strip(" -\t") for item in value.split(separators) if item.strip(" -\t")]
        if isinstance(value, list):
            items: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    quantity = item.get("quantity") or item.get("amount") or ""
                    unit = item.get("unit") or ""
                    name = item.get("name") or item.get("ingredient") or item.get("item") or ""
                    text = " ".join(str(part).strip() for part in [quantity, unit, name] if part)
                    if text:
                        items.append(text)
                elif item is not None:
                    items.append(str(item).strip())
            return [item for item in items if item]
        return [str(value).strip()] if str(value).strip() else []

    def _coerce_number(self, value: Any) -> float | int | None:
        if value is None or value == "":
            return None
        if isinstance(value, int | float):
            return value
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        if not match:
            return None
        number = float(match.group())
        return int(number) if number.is_integer() else number

    def _coerce_score(self, value: Any) -> float:
        number = self._coerce_number(1.0 if value is None else value)
        if number is None:
            return 1.0
        score = float(number)
        if score > 1 and score <= 10:
            score = score / 10
        elif score > 10:
            score = score / 100
        return max(0.0, min(1.0, score))
