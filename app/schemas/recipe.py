import logging
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator

from app.schemas.ingredient import Ingredient
from app.schemas.nutrition import RecipeNutrition

logger = logging.getLogger(__name__)


class Recipe(BaseModel):
    recipe_id: str
    title: str
    cuisine: str | None = None
    # Provenance for `cuisine`/`meal_type` -- mirrors the
    # `nutrition_view.macro_display_state` grounded/partial/unknown pattern
    # (see `RecipeCandidate.cuisine_source`'s docstring for the full
    # rationale). "declared" = author/curator/source explicitly set it;
    # "recovered_tag" = deterministically recovered from a source dataset's
    # own structured taxonomy field (never LLM-inferred); "gazetteer_matched"
    # = deterministically recovered from a whole-phrase, word-boundary
    # dish-name match against `title` only (see
    # `app.services.corpus_import.cuisine_tagger.DISH_NAME_CUISINE_TERMS` --
    # also never LLM-inferred, but a distinct, title-based evidence tier
    # from "recovered_tag", so kept separately labeled for future audit);
    # "llm_inferred" = assigned by an LLM's judgment (title + ingredient
    # names only, never allergy/nutrition-relevant) when deterministic
    # mining could not reach a value -- purely a fuzzy, non-safety-critical
    # classification pass; the LLM never decides an allergy or nutrition
    # outcome, only this display-only cuisine/meal_type tag, and only when
    # it judged the signal genuinely clear (see
    # `data/processed/llm_tag_inferences.jsonl` for the batch-classified
    # source and its self-reported abstain rate); "human_corrected" = a
    # human/orchestrator manually overrode a prior automated value found to
    # be wrong during spot-check review (see docs/BACKLOG.md's "100%-
    # completeness push" section for the specific corrections and reasoning
    # -- kept distinct from the automated tiers above so a manual fix never
    # masquerades as e.g. llm_inferred); "unknown" = no signal found.
    # `None` = not tracked by whatever produced this recipe (any
    # pre-2026-07-27 recipe, or a path that doesn't set it) -- display code
    # must treat `None` the same as "unknown". Purely a provenance/display
    # flag: never read by constraint_engine, scoring, or nutrition.
    cuisine_source: (
        Literal[
            "declared",
            "recovered_tag",
            "gazetteer_matched",
            "llm_inferred",
            "human_corrected",
            "unknown",
        ]
        | None
    ) = None
    meal_type: str | None = None
    meal_type_source: (
        Literal["declared", "recovered_tag", "llm_inferred", "human_corrected", "unknown"] | None
    ) = None
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def derived_allergens(self) -> list[str]:
        """Allergen labels derived deterministically from this recipe's
        ingredient names, via `constraint_engine.derive_allergen_labels`.

        DISPLAY-ONLY. This is a separate field from `allergens` (the
        self-reported/union field constraint_engine actually enforces
        against) and exists purely so the frontend can show an
        ingredient-grounded "Contains: ..." label without relying on
        self-reported metadata. Never read by `contains_allergen`,
        `_recipe_safety_terms`, `violates_diet_type`, `_allowed`, or any
        other safety decision path -- do not wire this into one. See
        docs/TO_FIX_AND_UPGRADE.md item 4 and the recipe_id derived-
        allergens task for the design rationale (Option C: additive field,
        `allergens` left untouched).

        Imported here (not at module level) to avoid a circular import:
        `app.services.constraint_engine` itself imports `Recipe` from this
        module.
        """
        from app.services.constraint_engine import derive_allergen_labels

        return derive_allergen_labels([ingredient.name for ingredient in self.ingredients])
