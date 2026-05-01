from pathlib import Path

from app.config import get_settings
from app.schemas.inventory import InventoryObservation
from app.services.model_provider import extract_inventory_with_provider_chain
from app.utils.ingredient_normalizer import normalize_ingredient
from app.utils.logging import get_logger

logger = get_logger(__name__)


DEFAULT_MOCK_INGREDIENTS = [
    ("chicken breast", 0.92),
    ("spinach", 0.88),
    ("eggs", 0.71),
    ("bell pepper", 0.79),
    ("Greek yogurt", 0.66),
    ("rice", 0.83),
]

FILENAME_MOCK_SCENARIOS = [
    (
        {"vegetarian", "veggie", "tofu", "plantbased", "plant-based"},
        [
            ("tofu", 0.91),
            ("broccoli", 0.86),
            ("bell pepper", 0.82),
            ("rice", 0.78),
            ("ginger", 0.68),
            ("soy sauce", 0.63),
        ],
    ),
    (
        {"fish", "salmon", "seafood"},
        [
            ("salmon", 0.9),
            ("asparagus", 0.84),
            ("potatoes", 0.79),
            ("lemon", 0.76),
            ("spinach", 0.69),
        ],
    ),
    (
        {"mexican", "taco", "burrito", "fajita"},
        [
            ("black beans", 0.88),
            ("corn", 0.84),
            ("bell pepper", 0.82),
            ("avocado", 0.74),
            ("tomato", 0.72),
            ("lime", 0.66),
        ],
    ),
    (
        {"breakfast", "morning", "eggs", "omelet"},
        [
            ("eggs", 0.9),
            ("spinach", 0.84),
            ("mushroom", 0.8),
            ("bell pepper", 0.77),
            ("cheddar cheese", 0.68),
            ("green onion", 0.64),
        ],
    ),
]


def _observation(raw_name: str, confidence: float) -> InventoryObservation:
    settings = get_settings()
    normalized = normalize_ingredient(raw_name)
    return InventoryObservation(
        raw_name=raw_name,
        normalized_name=normalized,
        quantity=None,
        confidence=confidence,
        source="vision",
        needs_confirmation=confidence < settings.low_confidence_threshold,
    )


def _mock_ingredients_for_filename(image_path: str | Path | None) -> list[tuple[str, float]]:
    if image_path is None:
        return DEFAULT_MOCK_INGREDIENTS

    filename = Path(image_path).stem.lower()
    if not filename:
        return DEFAULT_MOCK_INGREDIENTS

    filename_tokens = {
        token
        for token in filename.replace("-", "_").split("_")
        if token
        and token
        not in {"fridge", "pantry", "photo", "image", "upload", "generic", "default"}
    }
    compact_filename = filename.replace("-", "").replace("_", "")

    for scenario_tokens, ingredients in FILENAME_MOCK_SCENARIOS:
        if filename_tokens.intersection(scenario_tokens):
            return ingredients
        if any(token.replace("-", "") in compact_filename for token in scenario_tokens):
            return ingredients

    return DEFAULT_MOCK_INGREDIENTS


def extract_inventory_from_image(image_path: str | Path | None) -> list[InventoryObservation]:
    """Extract ingredients from a fridge image.

    The default implementation is deterministic mock mode. Optional hosted
    vision calls are intentionally isolated so allergy and nutrition logic never
    depends on a model.
    """

    return extract_inventory_with_provider_chain(
        image_path,
        lambda path: [
            _observation(name, confidence)
            for name, confidence in _mock_ingredients_for_filename(path)
        ],
    )
