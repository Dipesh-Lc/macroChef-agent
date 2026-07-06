from typing import Any

import requests

from app.config import Settings, get_settings
from app.schemas.nutrition import FoodMacros, FoodMatch
from app.services.nutrition_cache import FdcCache
from app.utils.ingredient_normalizer import normalize_ingredient
from app.utils.logging import get_logger

logger = get_logger(__name__)

# USDA FDC nutrient numbers (stable across dataTypes) for the macros we track.
# https://fdc.nal.usda.gov/
_NUTRIENT_CALORIES = "208"  # Energy, unit KCAL (957 is the kJ duplicate; ignored)
_NUTRIENT_PROTEIN = "203"
_NUTRIENT_FAT = "204"
_NUTRIENT_CARBS = "205"
_NUTRIENT_FIBER = "291"

# Prefer generic, reproducible whole-food data over branded products, whose
# macros vary by manufacturer/formulation and would make grounding unstable.
_DATA_TYPE_PRIORITY = {
    "Foundation": 0,
    "SR Legacy": 1,
    "Survey (FNDDS)": 2,
    "Branded": 3,
}


def _extract_macros(food: dict[str, Any]) -> FoodMacros | None:
    """Pull per-100g macros out of a single FDC `/foods/search` food entry.

    Returns `None` if any of calories/protein/fat/carbs is missing (fiber
    defaults to 0.0 since many foods legitimately omit it) — that food is
    then skipped as a candidate match rather than producing bad numbers.
    """

    by_number: dict[str, float] = {}
    for nutrient in food.get("foodNutrients") or []:
        number = nutrient.get("nutrientNumber")
        value = nutrient.get("value")
        if number is None or value is None:
            continue
        by_number.setdefault(number, value)

    calories = by_number.get(_NUTRIENT_CALORIES)
    protein = by_number.get(_NUTRIENT_PROTEIN)
    fat = by_number.get(_NUTRIENT_FAT)
    carbs = by_number.get(_NUTRIENT_CARBS)
    if calories is None or protein is None or fat is None or carbs is None:
        return None

    fiber = by_number.get(_NUTRIENT_FIBER, 0.0)
    return FoodMacros(
        calories=calories,
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fat,
        fiber_g=fiber,
    )


def _best_match(payload: dict[str, Any], query: str) -> FoodMatch | None:
    foods = payload.get("foods") or []
    ranked = sorted(foods, key=lambda food: _DATA_TYPE_PRIORITY.get(food.get("dataType"), 99))
    for food in ranked:
        macros = _extract_macros(food)
        if macros is None:
            continue
        return FoodMatch(
            fdc_id=food["fdcId"],
            description=food.get("description", ""),
            data_type=food.get("dataType", ""),
            macros=macros,
            query=query,
        )
    return None


class UsdaClient:
    """Client for USDA FoodData Central's `/foods/search` endpoint.

    Degrades gracefully everywhere: with no API key configured, on network
    errors, or on an empty/unusable result, `search_food` returns `None`
    rather than raising. Callers (see `nutrition_grounding.py`) treat `None`
    as "this ingredient could not be grounded," never as "zero calories."

    `session` and `cache` are injectable so tests never touch the network.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        session: requests.Session | None = None,
        cache: FdcCache | None = None,
    ):
        self._settings = settings or get_settings()
        self._session = session or requests.Session()
        self._cache = cache if cache is not None else FdcCache(self._settings.fdc_cache_path)

    def search_food(self, name: str) -> FoodMatch | None:
        query = normalize_ingredient(name)
        if not query:
            return None

        cached = self._cache.get(query)
        if cached is not None:
            return cached

        if not self._settings.fdc_api_key:
            return None

        try:
            response = self._session.get(
                f"{self._settings.fdc_base_url.rstrip('/')}/foods/search",
                params={
                    "api_key": self._settings.fdc_api_key,
                    "query": query,
                    "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)", "Branded"],
                    "pageSize": 5,
                },
                timeout=self._settings.model_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            logger.warning("USDA FDC search failed for %r: %s", query, exc)
            return None
        except ValueError as exc:
            logger.warning("USDA FDC search returned invalid JSON for %r: %s", query, exc)
            return None

        match = _best_match(payload, query)
        if match is None:
            return None

        self._cache.set(query, match)
        return match
