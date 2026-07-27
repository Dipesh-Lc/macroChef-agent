"""Measure the real grams-computable rate of the corpus, vs. the surface
"unit field populated" rate.

Background: "unit field populated" (`ingredient.unit is not None`) is a poor
proxy for what actually matters -- whether an ingredient's amount+unit can be
converted to grams for nutrition math via `app.utils.unit_converter.to_grams`.
A populated unit that has no density/piece-weight table entry for its
ingredient name (e.g. "2 cups shallot") still can't be converted. This script
measures the real number directly against the live corpus, broken down by the
unit-dimension categories `unit_converter` itself uses (mass / volume / count
/ no-unit), so the gap between the two numbers is visible.

Usage: python scripts/measure_grams_computable.py [path/to/imported_recipes.jsonl]

The corpus is loaded via `app.rag.loaders.load_corpus`, the same seed +
imported union (deduped by recipe_id) used throughout the app -- passing a
path overrides only the imported-corpus half (mirrors
`audit_title_ingredient_integrity.py`'s single-path CLI convention while
still including the 25 curated seed recipes, since load_corpus is a union of
both files, not a single-file loader).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.loaders import load_corpus  # noqa: E402
from app.schemas.ingredient import Ingredient  # noqa: E402
from app.schemas.recipe import Recipe  # noqa: E402
from app.utils.unit_converter import to_grams, unit_dimension  # noqa: E402

CATEGORIES = ("mass", "volume", "count", "no_unit", "unrecognized_unit")


@dataclass
class CategoryCount:
    total: int = 0
    computable: int = 0


@dataclass
class MeasurementResult:
    total_rows: int = 0
    unit_populated_rows: int = 0
    computable_rows: int = 0
    by_category: dict[str, CategoryCount] = field(
        default_factory=lambda: {cat: CategoryCount() for cat in CATEGORIES}
    )

    @property
    def unit_populated_pct(self) -> float:
        return self.unit_populated_rows / self.total_rows if self.total_rows else 0.0

    @property
    def computable_pct(self) -> float:
        return self.computable_rows / self.total_rows if self.total_rows else 0.0


def categorize(ingredient: Ingredient) -> str:
    """Same bucketing unit_converter itself uses: mass / volume / count units
    (via `unit_dimension`), "no_unit" for a genuinely absent unit, and
    "unrecognized_unit" for a populated-but-unrecognized unit string (not
    expected in the live corpus today, since every stored unit passes through
    the canonical vocabulary, but handled explicitly rather than silently
    folded into "no_unit" so a future drift would be visible)."""
    if not ingredient.unit:
        return "no_unit"
    dimension = unit_dimension(ingredient.unit)
    return dimension if dimension is not None else "unrecognized_unit"


def measure(recipes: list[Recipe]) -> MeasurementResult:
    result = MeasurementResult()
    for recipe in recipes:
        for ingredient in recipe.ingredients:
            result.total_rows += 1
            if ingredient.unit:
                result.unit_populated_rows += 1

            category = categorize(ingredient)
            bucket = result.by_category[category]
            bucket.total += 1

            grams = to_grams(ingredient.amount, ingredient.unit, name=ingredient.name)
            if grams is not None:
                result.computable_rows += 1
                bucket.computable += 1
    return result


def render_report(result: MeasurementResult) -> str:
    lines = [
        f"Total ingredient rows: {result.total_rows}",
        (
            f"Unit field populated: {result.unit_populated_rows}/{result.total_rows} "
            f"({result.unit_populated_pct:.2%}) -- surface metric, does NOT mean "
            f"grams-computable"
        ),
        (
            f"Grams-computable (via unit_converter.to_grams): "
            f"{result.computable_rows}/{result.total_rows} ({result.computable_pct:.2%}) "
            f"-- the real number that matters for nutrition math"
        ),
        "",
        "Breakdown by unit category:",
    ]
    for category in CATEGORIES:
        bucket = result.by_category[category]
        if bucket.total == 0:
            continue
        pct = bucket.computable / bucket.total
        lines.append(
            f"  {category:>17}: {bucket.computable:>6}/{bucket.total:<6} computable ({pct:.2%})"
        )
    return "\n".join(lines)


def main() -> int:
    imported_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    recipes = load_corpus(imported_path=imported_path)
    result = measure(recipes)
    print(render_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
