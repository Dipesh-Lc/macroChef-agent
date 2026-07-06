"""Idempotent, re-runnable corpus import: read -> adapt -> validate -> dedupe ->
build -> tally -> write.

Reuses the existing candidate-validation and dedup services rather than
reinventing them, so imported recipes go through the exact same
Pydantic-contract, structural, and dedup checks as any other candidate
(app/services/recipe_validation_service.py, app/services/recipe_dedup_service.py).

Corpus-build scope note: this pipeline does NOT call the USDA grounding
service — that is roadmap item 1.4, deliberately deferred (would mean
thousands of rate-limited API calls at import time). Imported recipes keep
whatever source-provided macros survived the adapter, or None.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.rag.loaders import load_recipes
from app.schemas.recipe import Recipe
from app.schemas.recipe_candidate import RecipeCandidate
from app.services.corpus_import.adapters import DatasetAdapter
from app.services.recipe_dedup_service import RecipeDedupService
from app.services.recipe_validation_service import RecipeValidationService
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ImportReport:
    """Survivor counts for one import run — the headline deliverable."""

    read: int = 0
    rejected_by_adapter: int = 0
    failed_validation: int = 0
    duplicates: int = 0
    survivors: int = 0
    empty_ingredients_dropped: int = 0
    recipes_with_empty_ingredients: int = 0
    # Optional, adapter-specific instruction-cleaning stats (0 for adapters
    # that don't do this, e.g. anything without narrative-commentary risk).
    narrative_steps_dropped: int = 0
    recipes_with_narrative_steps_dropped: int = 0
    recipes_below_min_instructions_after_cleaning: int = 0
    recipes_rejected_because_of_cleaning: int = 0

    def summary(self) -> str:
        return (
            f"read={self.read} "
            f"adapter_rejected={self.rejected_by_adapter} "
            f"failed_validation={self.failed_validation} "
            f"duplicates={self.duplicates} "
            f"survivors={self.survivors} "
            f"empty_ingredients_dropped={self.empty_ingredients_dropped} "
            f"(across {self.recipes_with_empty_ingredients} recipes) "
            f"narrative_steps_dropped={self.narrative_steps_dropped} "
            f"(across {self.recipes_with_narrative_steps_dropped} recipes, "
            f"{self.recipes_below_min_instructions_after_cleaning} pushed below "
            f"the 2-instruction minimum)"
        )


class CorpusImportPipeline:
    def __init__(
        self,
        adapter: DatasetAdapter,
        validation_service: RecipeValidationService | None = None,
        dedup_service: RecipeDedupService | None = None,
    ):
        self.adapter = adapter
        self.validation_service = validation_service or RecipeValidationService()
        self.dedup_service = dedup_service or RecipeDedupService()

    def run(
        self,
        source_path: str | Path,
        output_path: str | Path,
        *,
        limit: int | None = None,
        existing_recipes: list[Recipe] | None = None,
    ) -> ImportReport:
        report = ImportReport()
        candidates: list[RecipeCandidate] = []

        for raw in self.adapter.read_raw(Path(source_path)):
            if limit is not None and report.read >= limit:
                break
            report.read += 1
            candidate = self.adapter.to_candidate(raw)
            if candidate is None:
                report.rejected_by_adapter += 1
                continue
            candidates.append(candidate)

        # No RecipeDiscoveryRequest: corpus-build validation is structural only
        # (contract shape, min ingredients/instructions), not personalized to
        # any one user's allergies/diet — that safety check happens at query
        # time via constraint_engine.contains_allergen, not at corpus-build time.
        validation_result = self.validation_service.validate_candidates(candidates)
        report.failed_validation = len(validation_result.failed_candidates)

        # Dedupe against the curated seeds (and within this batch); defaults to
        # load_recipes() (seed file only) when existing_recipes isn't supplied,
        # which is exactly what we want — imports never dedupe against a stale
        # previous imported_recipes.jsonl, since that file is fully rewritten
        # each run anyway.
        seeds = existing_recipes if existing_recipes is not None else load_recipes()
        dedup_result = self.dedup_service.deduplicate(
            validation_result.valid_candidates, existing_recipes=seeds
        )
        report.duplicates = len(dedup_result.duplicate_candidates)

        recipes: list[Recipe] = []
        for candidate in dedup_result.unique_candidates:
            recipe_id = _deterministic_import_id(self.adapter.dataset_name, candidate)
            recipe = candidate.to_recipe(
                "corpus_import",
                recipe_id=recipe_id,
                is_user_saved=False,
            )
            # Recipe._drop_empty_ingredients is the single chokepoint that
            # drops empty/whitespace ingredient names; tally the difference so
            # systematic empty-production in the source is visible at INFO by
            # default during import, not only under the validator's own DEBUG log.
            dropped = len(candidate.ingredients) - len(recipe.ingredients)
            if dropped > 0:
                report.empty_ingredients_dropped += dropped
                report.recipes_with_empty_ingredients += 1
            recipes.append(recipe)

        # Sort for stable diffs; full rewrite (not append) keeps re-runs idempotent.
        recipes.sort(key=lambda recipe: recipe.recipe_id)
        report.survivors = len(recipes)
        _write_jsonl(Path(output_path), recipes)

        report.narrative_steps_dropped = getattr(self.adapter, "narrative_steps_dropped", 0)
        report.recipes_with_narrative_steps_dropped = getattr(
            self.adapter, "recipes_with_narrative_steps_dropped", 0
        )
        report.recipes_below_min_instructions_after_cleaning = getattr(
            self.adapter, "recipes_below_min_instructions_after_cleaning", 0
        )
        report.recipes_rejected_because_of_cleaning = getattr(
            self.adapter, "recipes_rejected_because_of_cleaning", 0
        )

        if report.empty_ingredients_dropped:
            logger.info(
                "dropped %d empty ingredients across %d recipes during corpus import",
                report.empty_ingredients_dropped,
                report.recipes_with_empty_ingredients,
            )
        logger.info("corpus import complete: %s", report.summary())
        return report


def _deterministic_import_id(dataset_name: str, candidate: RecipeCandidate) -> str:
    """Stable id independent of read order, so re-running the same source
    (even with a different --limit) never produces duplicate rows and always
    lets a shrink-and-rerun cleanly drop the ids that disappeared."""
    seed = f"{dataset_name}:{candidate.source_url or candidate.title}:{candidate.cuisine or ''}"
    return f"imp_{uuid5(NAMESPACE_URL, seed).hex[:16]}"


def _write_jsonl(path: Path, recipes: list[Recipe]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for recipe in recipes:
            handle.write(json.dumps(recipe.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")
