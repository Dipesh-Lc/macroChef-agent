from app.schemas.recipe import Recipe
from app.schemas.recipe_candidate import RecipeCandidate
from app.services.recipe_dedup_service import RecipeDedupService


def _candidate(
    title: str,
    ingredients: list[str] | None = None,
    cuisine: str = "Italian",
) -> RecipeCandidate:
    return RecipeCandidate(
        candidate_id=f"c_{title.lower().replace(' ', '_')}",
        title=title,
        cuisine=cuisine,
        meal_type="dinner",
        description="Test recipe",
        ingredients=ingredients or ["150 g chicken breast", "100 g rice", "80 g spinach"],
        instructions=["Prep ingredients.", "Cook everything."],
        cook_time_min=25,
        source_type="mock",
    )


def test_identical_titles_are_duplicates() -> None:
    existing = [Recipe(recipe_id="r1", title="Chicken Tomato Pasta", cuisine="Italian")]
    result = RecipeDedupService().deduplicate(
        [_candidate("Chicken Tomato Pasta")],
        existing,
    )

    assert not result.unique_candidates
    assert result.duplicate_candidates


def test_similar_titles_are_near_duplicates() -> None:
    existing = [Recipe(recipe_id="r1", title="Chicken Tomato Basil Pasta", cuisine="Italian")]
    result = RecipeDedupService().deduplicate(
        [_candidate("Chicken Tomato Basil Pasta Bowl")],
        existing,
    )

    assert result.duplicate_candidates


def test_different_recipes_are_not_duplicates() -> None:
    existing = [Recipe(recipe_id="r1", title="Chicken Tomato Pasta", cuisine="Italian")]
    candidate = _candidate(
        "Japanese Salmon Rice Plate",
        ["140 g salmon", "150 g rice", "80 g cucumber"],
        cuisine="Japanese",
    )

    result = RecipeDedupService().deduplicate([candidate], existing)

    assert result.unique_candidates == [candidate]


def test_ingredient_overlap_duplicate_logic() -> None:
    existing = [
        Recipe(
            recipe_id="r1",
            title="Weeknight Chicken Bowl",
            cuisine="Mexican",
            ingredients=["chicken breast", "rice", "bell pepper", "onion"],
        )
    ]
    candidate = _candidate(
        "Chicken Skillet Plate",
        ["150 g chicken breast", "140 g rice", "100 g bell pepper", "80 g onion"],
        cuisine="Mexican",
    )

    result = RecipeDedupService().deduplicate([candidate], existing)

    assert result.duplicate_candidates
