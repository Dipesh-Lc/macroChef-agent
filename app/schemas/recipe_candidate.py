from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field, computed_field

from app.schemas.ingredient import Ingredient
from app.schemas.recipe import Recipe
from app.utils.ingredient_normalizer import normalize_ingredient

SourceType = Literal["mock", "ai_generated", "external", "curated", "user_added"]


class RecipeCandidate(BaseModel):
    candidate_id: str
    title: str
    cuisine: str | None = None
    meal_type: str | None = None
    description: str | None = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    cook_time_min: int | None = Field(default=None, ge=0)
    difficulty: str | None = None
    servings: int | None = Field(default=1, ge=1)
    calories: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    fiber_g: float | None = Field(default=None, ge=0)
    allergens: list[str] = Field(default_factory=list)
    diet_tags: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    image_url: str | None = None
    image_path: str | None = None
    source_type: SourceType
    source_name: str | None = None
    source_url: str | None = None
    home_cookable_score: float = Field(default=1.0, ge=0, le=1)
    validation_warnings: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def derived_allergens(self) -> list[str]:
        """Allergen labels derived deterministically from this candidate's
        ingredient names, via `constraint_engine.derive_allergen_labels`.

        DISPLAY-ONLY. This is a separate field from `allergens` (the
        self-reported field that flows into `Recipe.allergens` via
        `to_recipe()` and is unioned into constraint_engine's safety scan)
        and exists purely so the frontend can show an ingredient-grounded
        "Contains: ..." label without relying on self-reported metadata.
        Never read by `contains_allergen`, `_recipe_safety_terms`,
        `violates_diet_type`, `_allowed`, or any other safety decision
        path -- do not wire this into one. See docs/TO_FIX_AND_UPGRADE.md
        item 4 and `Recipe.derived_allergens` for the design rationale
        (Option C: additive field, `allergens`/`to_recipe()` left
        untouched).

        Imported here (not at module level) as a defensive precaution
        matching `Recipe.derived_allergens` (see that docstring for the
        confirmed circular-import reason on the Recipe side).
        """
        from app.services.constraint_engine import derive_allergen_labels

        return derive_allergen_labels([ingredient.name for ingredient in self.ingredients])

    def to_recipe(
        self,
        user_id: str,
        *,
        recipe_id: str | None = None,
        is_user_saved: bool = True,
        owner_user_id: str | None = None,
    ) -> Recipe:
        """Build a corpus `Recipe` from this candidate.

        `user_id` is always used to derive the default stable id (so existing
        callers are unaffected); pass `recipe_id` to override it (e.g. a
        deterministic import id) and `is_user_saved`/`owner_user_id` to build a
        non-user-owned corpus recipe (e.g. an imported one) through the same
        normalization path as user-saved recipes.
        """
        if recipe_id is None:
            stable_id = uuid5(NAMESPACE_URL, f"macrochef:{user_id}:{self.title}:{self.cuisine}")
            recipe_id = f"user_{stable_id.hex[:16]}"
        # Preserve prior behavior for existing (user-saved) callers, who never
        # pass owner_user_id and expect it to default to user_id. Corpus
        # imports pass is_user_saved=False and rely on owner_user_id staying
        # None even though it wasn't explicitly set.
        if owner_user_id is None and is_user_saved:
            owner_user_id = user_id
        return Recipe(
            recipe_id=recipe_id,
            title=self.title,
            cuisine=self.cuisine,
            meal_type=self.meal_type,
            # Empties funnel through Recipe's ingredient validator, which drops
            # and logs them (single observable chokepoint) rather than silently
            # filtering here.
            ingredients=list(self.ingredients),
            instructions=[item.strip() for item in self.instructions if item.strip()],
            # dict.fromkeys dedupes while preserving order: normalize_ingredient
            # can collapse distinct raw labels to the same string (e.g. "egg"
            # and "eggs" both depluralize to "egg"), which derive_allergen_labels
            # deliberately doesn't pre-collapse (see its docstring) -- dedupe
            # here instead, at the display/storage boundary.
            allergens=list(
                dict.fromkeys(normalize_ingredient(item).lower() for item in self.allergens if item)
            ),
            diet_tags=[item.strip().lower() for item in self.diet_tags if item.strip()],
            cook_time_min=self.cook_time_min,
            calories=self.calories,
            protein_g=self.protein_g,
            carbs_g=self.carbs_g,
            fat_g=self.fat_g,
            fiber_g=self.fiber_g,
            description=self.description,
            difficulty=self.difficulty,
            servings=self.servings,
            equipment=[item.strip().lower() for item in self.equipment if item.strip()],
            image_url=self.image_url,
            image_path=self.image_path,
            source_type=self.source_type,
            source_name=self.source_name,
            source_url=self.source_url,
            owner_user_id=owner_user_id,
            is_user_saved=is_user_saved,
            is_active=True,
        )
