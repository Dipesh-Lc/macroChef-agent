import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.rag.loaders import load_recipes
from app.schemas.recipe import Recipe
from app.schemas.recipe_candidate import RecipeCandidate
from app.utils.ingredient_normalizer import normalize_ingredient


@dataclass
class DeduplicationResult:
    unique_candidates: list[RecipeCandidate] = field(default_factory=list)
    duplicate_candidates: list[RecipeCandidate] = field(default_factory=list)
    duplicate_reasons: dict[str, str] = field(default_factory=dict)


class RecipeDedupService:
    def deduplicate(
        self,
        candidates: list[RecipeCandidate],
        existing_recipes: list[Recipe] | None = None,
    ) -> DeduplicationResult:
        existing = existing_recipes if existing_recipes is not None else load_recipes()
        result = DeduplicationResult()
        seen_recipes = list(existing)
        seen_candidates: list[RecipeCandidate] = []

        for candidate in candidates:
            duplicate, reason = self._find_duplicate(candidate, seen_recipes, seen_candidates)
            if duplicate:
                result.duplicate_candidates.append(candidate)
                result.duplicate_reasons[candidate.candidate_id] = reason
                continue
            result.unique_candidates.append(candidate)
            seen_candidates.append(candidate)
        return result

    def _find_duplicate(
        self,
        candidate: RecipeCandidate,
        recipes: list[Recipe],
        candidates: list[RecipeCandidate],
    ) -> tuple[bool, str]:
        candidate_title = normalize_title(candidate.title)
        candidate_ingredients = normalized_ingredient_set(candidate.ingredients)

        for recipe in recipes:
            if candidate_title == normalize_title(recipe.title):
                return True, f"Duplicate title: {recipe.title}"
            if title_similarity(candidate.title, recipe.title) >= 0.85:
                return True, f"Near-duplicate title: {recipe.title}"
            if self._same_ingredient_profile(candidate, candidate_ingredients, recipe):
                return True, f"High ingredient overlap with: {recipe.title}"

        for other in candidates:
            if candidate_title == normalize_title(other.title):
                return True, f"Duplicate candidate title: {other.title}"
            if title_similarity(candidate.title, other.title) >= 0.85:
                return True, f"Near-duplicate candidate title: {other.title}"
            if self._same_candidate_ingredient_profile(candidate, candidate_ingredients, other):
                return True, f"High ingredient overlap with candidate: {other.title}"

        return False, ""

    def _same_ingredient_profile(
        self, candidate: RecipeCandidate, candidate_ingredients: set[str], recipe: Recipe
    ) -> bool:
        if not candidate.cuisine or not recipe.cuisine:
            return False
        if candidate.cuisine.lower() != recipe.cuisine.lower():
            return False
        overlap = ingredient_overlap(
            candidate_ingredients,
            normalized_ingredient_set(recipe.ingredients),
        )
        return overlap >= 0.8

    def _same_candidate_ingredient_profile(
        self, candidate: RecipeCandidate, candidate_ingredients: set[str], other: RecipeCandidate
    ) -> bool:
        if not candidate.cuisine or not other.cuisine:
            return False
        if candidate.cuisine.lower() != other.cuisine.lower():
            return False
        overlap = ingredient_overlap(
            candidate_ingredients,
            normalized_ingredient_set(other.ingredients),
        )
        return overlap >= 0.8


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_title(left), normalize_title(right)).ratio()


def normalized_ingredient_set(ingredients: list[str]) -> set[str]:
    normalized = [normalize_ingredient(item).lower() for item in ingredients]
    return {item for item in normalized if item}


def ingredient_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left), len(right))
