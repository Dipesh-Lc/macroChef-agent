import logging

from pydantic import BaseModel, Field, field_validator

from app.schemas.ingredient import Ingredient
from app.schemas.nutrition import RecipeNutrition

logger = logging.getLogger(__name__)


class Recipe(BaseModel):
    recipe_id: str
    title: str
    cuisine: str | None = None
    meal_type: str | None = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    diet_tags: list[str] = Field(default_factory=list)
    cook_time_min: int | None = Field(default=None, ge=0)
    # Self-reported tag macros (recipe-tag metadata or, for imported recipes,
    # the source dataset's own values). Never overwritten by grounding --
    # `nutrition` below is the computed value; these stay intact so the two
    # can be compared. Nothing should trust these directly for scoring or
    # display once `nutrition` exists; see app.services.nutrition_view.
    calories: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    fiber_g: float | None = Field(default=None, ge=0)
    # USDA-computed macros, attached at load time from the grounding sidecar
    # (app.rag.loaders.attach_grounding) -- None until the grounding job has
    # run for this recipe. This is the one field the scorer/frontend should
    # read through app.services.nutrition_view, never the tag fields above.
    nutrition: RecipeNutrition | None = None
    description: str | None = None
    difficulty: str | None = None
    servings: int | None = Field(default=1, ge=1)
    equipment: list[str] = Field(default_factory=list)
    image_url: str | None = None
    image_path: str | None = None
    source_type: str | None = "base"
    source_name: str | None = None
    source_url: str | None = None
    owner_user_id: str | None = None
    is_user_saved: bool = False
    is_active: bool = True
    # Set at load time (app.rag.loaders.attach_restoration) for recipes that
    # were quarantined by an earlier import and released back to active by a
    # later reimport (bucket == "released" in a
    # data/processed/scraped_archive_reimport_ledger_*.jsonl sidecar) --
    # drives the "Restored from source" display badge (roadmap item B6).
    # Purely a display flag: never read by constraint_engine, scoring, or
    # nutrition, and never set by the LLM.
    restored_from_quarantine: bool = False
    # Deterministic, templated description of a swap this recipe represents
    # (e.g. "Swapped peanut butter -> sunflower seed butter (peanut-safe).
    # macro impact: ..."), set only by app.services.substitution_service.
    # _build_variant_recipe for a recipe whose source_type == "substitution_
    # variant" -- never LLM-authored (see that module's docstring). None for
    # every ordinary (non-variant) recipe.
    substitution_note: str | None = None

    @field_validator("ingredients", mode="after")
    @classmethod
    def _drop_empty_ingredients(
        cls, ingredients: list[Ingredient], info
    ) -> list[Ingredient]:
        # Tolerant, non-destructive cleanup: a stray "" / "   " ingredient (from a
        # loader, DB blob, or candidate conversion) is dropped rather than
        # persisted as name='' or raised over. This is the single chokepoint for
        # every Recipe assembly path (loaders.load_recipes, RecipeCandidate.
        # to_recipe, direct construction). The drop is logged so a loader
        # emitting empties in bulk (e.g. at corpus-scale in item 1.3) is visible.
        kept = [item for item in ingredients if item.name and item.name.strip()]
        dropped = len(ingredients) - len(kept)
        if dropped:
            identifier = info.data.get("recipe_id") or info.data.get("title") or "<unknown>"
            logger.debug(
                "Dropped %d empty-name ingredient(s) while assembling recipe %s",
                dropped,
                identifier,
            )
        return kept
