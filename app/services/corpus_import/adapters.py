"""Per-dataset adapters mapping a raw external record into a `RecipeCandidate`.

The import pipeline (`pipeline.py`) is dataset-agnostic: it only calls
`DatasetAdapter.read_raw` / `to_candidate`. Adding a new source dataset means
adding one adapter here, not touching the pipeline.

Safety note: allergens are always *derived* from ingredient names via
`derive_allergen_labels` (app/services/constraint_engine.py), never trusted
from a source-provided allergen/tag field — a dataset's own labeling isn't
something we can verify, and `Recipe.allergens` feeds diet-type checks and
Chroma index metadata downstream.
"""

from __future__ import annotations

import csv
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator
from uuid import NAMESPACE_URL, uuid5

from app.schemas.recipe_candidate import RecipeCandidate
from app.services.constraint_engine import derive_allergen_labels
from app.utils.quantity_parser import parse_quantity_string


class DatasetAdapter(ABC):
    """Maps one external dataset's raw rows into `RecipeCandidate`s."""

    dataset_name: str

    @abstractmethod
    def read_raw(self, source_path: Path) -> Iterator[dict]:
        """Yield one raw row (source column name -> value) per source record."""

    @abstractmethod
    def to_candidate(self, raw: dict) -> RecipeCandidate | None:
        """Map one raw row to a `RecipeCandidate`, or None if too structurally
        broken to attempt (e.g. no title, no ingredients). This is a cheap
        pre-filter; full contract/quality validation happens afterward via
        `RecipeValidationService`."""


# --- Food.com "Recipes and Reviews" adapter -------------------------------
#
# Column names confirmed against the live Kaggle dataset page (list-columns
# Images/Keywords/RecipeIngredientQuantities/RecipeIngredientParts/
# RecipeInstructions, R-vector-literal encoding, ISO 8601 durations for
# CookTime/PrepTime) -- irkaal/foodcom-recipes-and-reviews, CC0.

_R_VECTOR_ITEM = re.compile(r'"((?:[^"\\]|\\.)*)"')
_BARE_QUOTED_STRING = re.compile(r'^"((?:[^"\\]|\\.)*)"$')
_ISO_DURATION = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
_MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack", "dessert"}

# A meaningful minority of Food.com's RecipeInstructions steps carry personal/
# narrative commentary rather than functional instructions (e.g. "I don't
# actually use teaspoons for this... PATIENCE is the name of the game.").
# Imperative cooking steps ("Add", "Bake", "Whisk") essentially never use
# first person, so its presence is a strong, simple, deterministic signal of
# narrative content. Dropping the whole step (rather than trying to split out
# just the offending sentence, which risks producing garbled text on messy
# scraped input) is a deliberately conservative trade: it sometimes loses a
# step that mixed one aside with real functional content, but never emits
# broken prose. If cleaning drops a recipe below the 2-instruction minimum,
# RecipeValidationService already rejects it -- a reasonable outcome.
_FIRST_PERSON_PATTERN = re.compile(r"\b(i|i'm|i've|i'd|i'll|my|we|we're|we've|our)\b", re.IGNORECASE)
# Some source rows bake a redundant leading step number into the text itself
# (e.g. "2. Place apples..."), which would double up against our own step
# numbering downstream.
_LEADING_NUMBER_PREFIX = re.compile(r"^\s*\d+\.\s*")


def _strip_leading_number_prefix(step: str) -> str:
    return _LEADING_NUMBER_PREFIX.sub("", step, count=1).strip()


def _clean_instructions(steps: list[str]) -> tuple[list[str], int]:
    """Strip redundant leading numerals, then drop first-person (narrative)
    steps. Returns (cleaned_steps, narrative_steps_dropped_count)."""
    cleaned: list[str] = []
    dropped = 0
    for step in steps:
        step = _strip_leading_number_prefix(step)
        if not step:
            continue
        if _FIRST_PERSON_PATTERN.search(step):
            dropped += 1
            continue
        cleaned.append(step)
    return cleaned, dropped


def _parse_r_vector(text: str) -> list[str]:
    """Parse Food.com's R character-vector-literal fields, e.g. `c("a", "b")`.

    R's serialization omits the `c(...)` wrapper for length-1 vectors, writing
    just a bare quoted string (e.g. a single-step recipe's RecipeInstructions
    cell is `"Toast and grind..."`, not `c("Toast and grind...")`) -- handled
    as a dedicated case so the surrounding quote marks aren't left in as
    literal content. Falls back to comma-splitting for plain unquoted
    delimited text (covers simplified test fixtures and any export variant
    that isn't R-vector-encoded).
    """
    text = (text or "").strip()
    if not text:
        return []
    if text.startswith("c("):
        return [item.replace('\\"', '"') for item in _R_VECTOR_ITEM.findall(text)]
    bare_match = _BARE_QUOTED_STRING.match(text)
    if bare_match:
        return [bare_match.group(1).replace('\\"', '"')]
    return [part.strip() for part in text.split(",") if part.strip()]


def _parse_iso8601_duration_minutes(text: str | None) -> int | None:
    if not text:
        return None
    match = _ISO_DURATION.fullmatch(text.strip())
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    total = int(hours or 0) * 60 + int(minutes or 0) + (1 if seconds and int(seconds) >= 30 else 0)
    return total or None


def _safe_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _safe_int(value: str | None) -> int | None:
    parsed = _safe_float(value)
    return int(parsed) if parsed is not None else None


def _combine_ingredients(parts: list[str], quantities: list[str]) -> list[str]:
    """Zip Food.com's parallel quantity/name arrays into ingredient strings.

    Food.com keeps units embedded in the ingredient-part text itself (e.g.
    part="cup all-purpose flour", quantity="1/2"), so concatenating
    "{quantity} {part}" reconstructs a natural line ("1/2 cup all-purpose
    flour") that `parse_quantity_string` already knows how to parse.

    Deliberately does NOT filter out empty/blank parts here: an empty source
    entry becomes an empty-named `Ingredient` that flows through to
    `Recipe._drop_empty_ingredients` -- the single documented chokepoint for
    dropping+tallying empty ingredients (app/schemas/recipe.py). Filtering
    here instead would make that drop invisible to the pipeline's aggregate
    empty-ingredient count.
    """
    combined: list[str] = []
    for index, part in enumerate(parts):
        part = (part or "").strip()
        quantity = quantities[index].strip() if index < len(quantities) else ""
        if part and quantity and quantity.upper() != "NA":
            combined.append(f"{quantity} {part}")
        else:
            combined.append(part)
    return combined


def _map_category_to_meal_type(category: str | None) -> str | None:
    if not category:
        return None
    normalized = category.strip().lower()
    return normalized if normalized in _MEAL_TYPES else None


class FoodComAdapter(DatasetAdapter):
    """Adapter for the Food.com "Recipes and Reviews" CC0-tagged dataset."""

    dataset_name = "foodcom_recipes_and_reviews"

    _COLUMN_ALIASES: dict[str, list[str]] = {
        "title": ["Name"],
        "cook_time": ["CookTime"],
        "servings": ["RecipeServings"],
        "category": ["RecipeCategory"],
        "ingredient_parts": ["RecipeIngredientParts"],
        "ingredient_quantities": ["RecipeIngredientQuantities"],
        "instructions": ["RecipeInstructions"],
        "calories": ["Calories"],
        "protein": ["ProteinContent"],
        "carbs": ["CarbohydrateContent"],
        "fat": ["FatContent"],
        "fiber": ["FiberContent"],
        "url": ["RecipeId"],
    }

    def __init__(self) -> None:
        # Aggregate stats for the instruction-cleaning pass, read by the
        # pipeline/CLI after a run to report the drop rate (per-run counters,
        # not persisted).
        self.narrative_steps_dropped = 0
        self.recipes_with_narrative_steps_dropped = 0
        # Recipes that end up with <2 instructions after cleaning, for ANY
        # reason (includes recipes that only ever had <2 raw steps -- those
        # were always going to fail RecipeValidationService's min-instructions
        # check regardless of this cleaning pass).
        self.recipes_below_min_instructions_after_cleaning = 0
        # The subset of the above that cleaning is actually responsible for:
        # had >=2 raw steps, but dropping narrative ones left <2. This is the
        # number that answers "false-positive collateral from the new
        # mechanism" -- the other case isn't a consequence of this change.
        self.recipes_rejected_because_of_cleaning = 0
        # Capped sample for eyeballing false positives, restricted to the
        # cleaning-caused subset above (not recipes that were always too short).
        self.example_dropped_below_min: list[dict] = []

    def read_raw(self, source_path: Path) -> Iterator[dict]:
        with Path(source_path).open("r", encoding="utf-8-sig", newline="") as handle:
            yield from csv.DictReader(handle)

    def to_candidate(self, raw: dict) -> RecipeCandidate | None:
        title = self._get(raw, "title")
        if not title or not title.strip():
            return None

        parts = _parse_r_vector(self._get(raw, "ingredient_parts") or "")
        quantities = _parse_r_vector(self._get(raw, "ingredient_quantities") or "")
        ingredient_texts = _combine_ingredients(parts, quantities)
        if len(ingredient_texts) < 3:
            return None

        raw_instructions = _parse_r_vector(self._get(raw, "instructions") or "")
        instructions, narrative_dropped = _clean_instructions(raw_instructions)
        self.narrative_steps_dropped += narrative_dropped
        if narrative_dropped:
            self.recipes_with_narrative_steps_dropped += 1
        if len(instructions) < 2:
            self.recipes_below_min_instructions_after_cleaning += 1
            cleaning_caused_it = len(raw_instructions) >= 2
            if cleaning_caused_it:
                self.recipes_rejected_because_of_cleaning += 1
            if cleaning_caused_it and len(self.example_dropped_below_min) < 10:
                self.example_dropped_below_min.append(
                    {
                        "title": title.strip(),
                        "original_instructions": raw_instructions,
                        "cleaned_instructions": instructions,
                    }
                )

        recipe_key = self._get(raw, "url") or title
        candidate_id = f"foodcom_{uuid5(NAMESPACE_URL, str(recipe_key)).hex[:16]}"

        ingredient_names = [parse_quantity_string(text)["name"] for text in ingredient_texts]
        allergens = derive_allergen_labels(ingredient_names)

        return RecipeCandidate(
            candidate_id=candidate_id,
            title=title.strip(),
            meal_type=_map_category_to_meal_type(self._get(raw, "category")),
            ingredients=ingredient_texts,  # bare strings; Ingredient coerces via parse_quantity_string
            instructions=instructions,
            cook_time_min=_parse_iso8601_duration_minutes(self._get(raw, "cook_time")),
            servings=_safe_int(self._get(raw, "servings")) or 1,
            calories=_safe_float(self._get(raw, "calories")),
            protein_g=_safe_float(self._get(raw, "protein")),
            carbs_g=_safe_float(self._get(raw, "carbs")),
            fat_g=_safe_float(self._get(raw, "fat")),
            fiber_g=_safe_float(self._get(raw, "fiber")),
            allergens=allergens,
            source_type="curated",
            source_name="Food.com (Recipes and Reviews)",
            source_url=str(recipe_key) if recipe_key else None,
        )

    def _get(self, raw: dict, key: str) -> str | None:
        for column in self._COLUMN_ALIASES[key]:
            if column in raw and raw[column] not in (None, ""):
                return raw[column]
        return None
