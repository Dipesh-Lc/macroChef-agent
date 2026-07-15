"""Idempotent, re-runnable USDA grounding pass over the recipe corpus.

Computes macros for every recipe's structured ingredients via
`compute_recipe_macros` and writes them to a sidecar artifact
(data/processed/grounding.jsonl) that is fully rewritten (sorted by
recipe_id) on each run -- source recipe files (sample_recipes.jsonl,
imported_recipes.jsonl) are never touched, so their self-reported tag macros
stay intact and recoverable for the tag-vs-computed comparison this module
also builds (`GroundingReport`). USDA lookups go through the caller-supplied
`UsdaClient`, which fronts `FdcCache` on disk -- re-running this job hits
cache, not the network, for every ingredient already looked up.

This module is the logic; `scripts/ground_corpus.py` is a thin CLI wrapper
around `run_grounding` + `render_report`, mirroring
`app.services.corpus_import.pipeline` / `scripts/import_corpus.py`.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.rag.loaders import load_corpus, load_recipes
from app.schemas.ingredient import Ingredient
from app.schemas.nutrition import GroundingStatus, IngredientContribution, RecipeNutrition
from app.schemas.recipe import Recipe
from app.services.nutrition_grounding import compute_recipe_macros
from app.services.usda_client import UsdaClient
from app.utils.ingredient_normalizer import normalize_ingredient
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Corpus-wide tag-vs-computed ratio bounds outside of which a recipe is
# surfaced as an outlier in the report -- report-only, never demoting (see
# the phase 1.5 design's "Trust tiers" note: only the ~4200 tag-carrying
# imports have a self-reported number to compare against at all, and that
# self-report is itself unverified, so a wide ratio band here is a "worth a
# human look" signal, not a correctness gate).
RATIO_OUTLIER_MIN = 0.4
RATIO_OUTLIER_MAX = 2.5

# Cap on how many ratio-outlier rows the rendered report prints in full --
# the corpus-wide count is always reported even when the list is truncated.
_RATIO_OUTLIER_TABLE_LIMIT = 100

# A GROUNDED/PARTIAL recipe's per-serving kcal outside this band is flagged
# for manual review -- not auto-corrected, just surfaced (see GroundingReport).
IMPLAUSIBLE_MIN_KCAL_PER_SERVING = 20.0
IMPLAUSIBLE_MAX_KCAL_PER_SERVING = 2000.0

# Empirically, a raw/cooked or raw/canned mismatch inflates computed calories
# by roughly 2-3x (see the Step A analysis); 1.6x is a conservative trigger
# for "this looks like a state mismatch," checked only for recipes that
# declare a preparation on at least one ingredient.
RAW_COOKED_BLOWUP_RATIO = 1.6

# Known, deliberately-accepted residuals from the item 1.4 Step B closeout --
# investigated individually, not fixed further, and disclosed here so every
# report generation carries the same explanation rather than relying on
# memory of a one-off conversation. See usda_client.py's
# _KNOWN_UNRELIABLE_QUERIES for the two hard exclusions.
_KNOWN_RESIDUALS = [
    (
        "jasmine rice / basmati rice",
        "No variety-specific Foundation/SR Legacy/Survey record exists for "
        "either (confirmed live, even with the query augmented by the "
        "declared 'cooked' state) -- only generic 'Rice, white, cooked' "
        "entries exist. Rather than silently substitute a different variety, "
        "jasmine rice stays on its Branded match (JASMINE COOKED RICE, "
        "JASMINE, ~225 kcal/100g -- notably above a true ~130 kcal/100g, "
        "likely includes added oil/seasoning) and basmati stays UNGROUNDED. "
        "Not preparation-fixable.",
    ),
    (
        "zucchini",
        "FDC's canonical zucchini record is filed under 'Squash' (e.g. "
        "'Squash, summer, green, zucchini, includes skin, raw'), not "
        "'Zucchini' -- the relevance check's head-noun rule correctly "
        "refuses to treat that as the same food as a bare 'zucchini' query "
        "without a synonym table it doesn't have. Resolves to a Branded "
        "'Zucchini, pickled' (~35 kcal/100g) instead of raw (~21 kcal/100g). "
        "Not preparation-fixable.",
    ),
    (
        "shrimp / tomato sauce / chili powder / ginger",
        "Explicitly excluded via usda_client._KNOWN_UNRELIABLE_QUERIES -- "
        "shrimp and tomato sauce reliably resolve to a wrong-form match with "
        "no preparation declaration able to gate it (a sauce/seafood has no "
        "honest raw/cooked/canned state); chili powder and ginger's only "
        "reachable Branded record reports 0 kcal/100g, a data defect rather "
        "than a matching problem. All four render UNGROUNDED rather than a "
        "confidently wrong number.",
    ),
    (
        "olive oil",
        "Deterministically matches 'Oil, corn, peanut, and olive' (SR "
        "Legacy) instead of pure olive oil -- wrong specific product, but "
        "zero practical calorie impact (~884-900 kcal/100g either way, "
        "consistent with any pure fat). Left as-is.",
    ),
    (
        "general case: undeclared-preparation same-food-wrong-state matches",
        "The `preparation` field and the relevance check only cover "
        "ingredients that declare a state. Any ingredient without one "
        "(i.e. everything outside the seeds' explicitly-audited set) can "
        "still land on a processed/wrong-state USDA record purely by "
        "dataType-tier order -- this was the root cause behind chicken "
        "breast, ground turkey, corn, and tofu before they were "
        "individually audited and fixed for the 25 seeds. Unaudited for the "
        "imported corpus at large -- see docs/ROADMAP.md.",
    ),
]


@dataclass
class IngredientDetail:
    name: str
    grounded: bool
    grams: float | None
    detail: str


@dataclass
class SeedRow:
    """One seed recipe's tag-vs-computed comparison -- the report's core row."""

    recipe_id: str
    title: str
    status: GroundingStatus
    coverage: float
    tag_kcal: float | None
    computed_kcal: float
    ratio: float | None
    has_declared_preparation: bool
    implausible_band: bool
    raw_cooked_blowup: bool
    ingredients: list[IngredientDetail]


@dataclass
class UngroundedFrequency:
    """One row of the corpus-wide "what's not grounding" table -- how many
    distinct recipes have this normalized ingredient name in their
    `ungrounded_ingredients` (deduped per recipe, so an ingredient appearing
    twice in one recipe counts once)."""

    name: str
    recipe_count: int


@dataclass
class RatioOutlier:
    """A corpus (non-seed) recipe whose computed-vs-tag calorie ratio falls
    outside [RATIO_OUTLIER_MIN, RATIO_OUTLIER_MAX] -- report-only, see the
    module docstring on RATIO_OUTLIER_MIN/MAX."""

    recipe_id: str
    title: str
    tag_kcal: float
    computed_kcal: float
    ratio: float


@dataclass
class GroundingReport:
    total_recipes: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    seed_rows: list[SeedRow] = field(default_factory=list)
    # Corpus-wide diagnostics (all of `corpus`, not just the 25 seeds) --
    # every field below is report-only: none of it changes what gets
    # written to the sidecar or trusted downstream. See nutrition_view.py
    # for the actual trust chokepoint.
    ungrounded_frequency: list[UngroundedFrequency] = field(default_factory=list)
    ratio_distribution: list[float] = field(default_factory=list)
    ratio_outliers: list[RatioOutlier] = field(default_factory=list)
    implausible_band_corpus_count: int = 0
    rejection_counts: dict[str, int] = field(default_factory=dict)

    def implausible_band_flags(self) -> list[SeedRow]:
        return [row for row in self.seed_rows if row.implausible_band]

    def raw_cooked_blowup_flags(self) -> list[SeedRow]:
        return [row for row in self.seed_rows if row.raw_cooked_blowup]


def _ingredient_detail(ingredient: Ingredient, contribution: IngredientContribution) -> IngredientDetail:
    if contribution.grounded:
        match = contribution.match
        detail = f"matched: {match.description} ({match.data_type})" if match else "matched"
    elif contribution.grams is None:
        detail = "ungrounded: amount/unit not convertible to grams"
    elif ingredient.preparation is not None:
        detail = f"ungrounded: no USDA match for declared state '{ingredient.preparation}'"
    else:
        detail = "ungrounded: no USDA match"
    return IngredientDetail(
        name=ingredient.name, grounded=contribution.grounded, grams=contribution.grams, detail=detail
    )


def _write_sidecar(path: Path, results: dict[str, RecipeNutrition]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for recipe_id in sorted(results):
            row = {"recipe_id": recipe_id, "nutrition": results[recipe_id].model_dump(mode="json")}
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
    tmp_path.replace(path)


def run_grounding(
    *,
    client: UsdaClient | None = None,
    sidecar_path: str | Path = "data/processed/grounding.jsonl",
    corpus: list[Recipe] | None = None,
    seeds: list[Recipe] | None = None,
) -> GroundingReport:
    """Ground `corpus` (default: seeds ∪ imported via load_corpus()), write the
    sidecar, and build the full report (corpus-wide diagnostics plus the
    seed tag-vs-computed comparison for `seeds`, default: the 25
    hand-authored recipes via load_recipes() -- the only recipes with
    authored quantities to meaningfully compare against a self-reported tag).
    """
    client = client or UsdaClient()
    corpus = corpus if corpus is not None else load_corpus()
    seeds = seeds if seeds is not None else load_recipes()

    results: dict[str, RecipeNutrition] = {}
    for recipe in sorted(corpus, key=lambda r: r.recipe_id):
        results[recipe.recipe_id] = compute_recipe_macros(
            recipe.ingredients, servings=recipe.servings or 1, client=client
        )

    _write_sidecar(Path(sidecar_path), results)

    # `rejection_counts` is a diagnostic-only attribute on `UsdaClient` (see
    # its docstring) -- read defensively via getattr so a caller-supplied
    # test double without it still works, reporting simply nothing rejected.
    rejection_counts = dict(getattr(client, "rejection_counts", {}) or {})
    report = build_report(corpus=corpus, seeds=seeds, results=results, rejection_counts=rejection_counts)

    if report.implausible_band_flags():
        logger.warning(
            "%d seed recipe(s) outside the plausible kcal/serving band",
            len(report.implausible_band_flags()),
        )
    if report.raw_cooked_blowup_flags():
        logger.warning(
            "%d seed recipe(s) show a >%.1fx raw/cooked-scale blowup",
            len(report.raw_cooked_blowup_flags()),
            RAW_COOKED_BLOWUP_RATIO,
        )

    return report


def build_report(
    *,
    corpus: list[Recipe],
    seeds: list[Recipe],
    results: dict[str, RecipeNutrition],
    rejection_counts: dict[str, int] | None = None,
) -> GroundingReport:
    """Build a `GroundingReport` purely from already-computed data -- no
    `UsdaClient`, no network, no re-fetching. This is what lets a report be
    regenerated instantly from an existing sidecar (e.g. `data/processed/
    grounding.jsonl` loaded via `app.rag.loaders.load_corpus`/
    `load_grounding`) to capture a point-in-time baseline before a
    matching-rule change, without spending a single live FDC call.

    `results` must be keyed by `recipe_id`; a `corpus` recipe absent from it
    is simply skipped in every corpus-wide diagnostic (never fabricated).
    """
    seeds_by_id = {recipe.recipe_id: recipe for recipe in seeds}

    report = GroundingReport(total_recipes=len(results))
    for nutrition in results.values():
        key = nutrition.status.value
        report.status_counts[key] = report.status_counts.get(key, 0) + 1

    for recipe_id in sorted(seeds_by_id):
        seed = seeds_by_id[recipe_id]
        nutrition = results.get(recipe_id)
        if nutrition is None:
            # Seed wasn't part of `corpus` (only relevant for isolated tests
            # that pass a partial corpus) -- nothing to compare.
            continue

        # per_serving, not total: recipe.calories is documented/used
        # elsewhere as a single serving's macros, so this is the correct
        # apples-to-apples comparison even if servings != 1.
        computed_kcal = nutrition.per_serving.calories
        tag_kcal = seed.calories
        ratio = (computed_kcal / tag_kcal) if tag_kcal else None
        has_prep = any(ingredient.preparation is not None for ingredient in seed.ingredients)
        is_grounded_ish = nutrition.status != GroundingStatus.UNGROUNDED

        implausible = is_grounded_ish and not (
            IMPLAUSIBLE_MIN_KCAL_PER_SERVING <= computed_kcal <= IMPLAUSIBLE_MAX_KCAL_PER_SERVING
        )
        blowup = has_prep and is_grounded_ish and ratio is not None and ratio > RAW_COOKED_BLOWUP_RATIO

        ingredients_detail = [
            _ingredient_detail(ingredient, contribution)
            for ingredient, contribution in zip(seed.ingredients, nutrition.contributions)
        ]

        report.seed_rows.append(
            SeedRow(
                recipe_id=recipe_id,
                title=seed.title,
                status=nutrition.status,
                coverage=nutrition.coverage,
                tag_kcal=tag_kcal,
                computed_kcal=computed_kcal,
                ratio=ratio,
                has_declared_preparation=has_prep,
                implausible_band=implausible,
                raw_cooked_blowup=blowup,
                ingredients=ingredients_detail,
            )
        )

    # --- Corpus-wide diagnostics (all of `corpus`, report-only) ---

    ingredient_counter: Counter[str] = Counter()
    for recipe in corpus:
        nutrition = results.get(recipe.recipe_id)
        if nutrition is None or not nutrition.ungrounded_ingredients:
            continue
        # Dedupe within a recipe first -- an ingredient appearing twice in
        # one recipe's ungrounded list should count that recipe once, not
        # twice, in "how many recipes does this affect."
        names_this_recipe = {normalize_ingredient(name) or name for name in nutrition.ungrounded_ingredients}
        ingredient_counter.update(names_this_recipe)
    report.ungrounded_frequency = [
        UngroundedFrequency(name=name, recipe_count=count) for name, count in ingredient_counter.most_common(50)
    ]

    implausible_band_corpus_count = 0
    for recipe in corpus:
        nutrition = results.get(recipe.recipe_id)
        if nutrition is None or nutrition.status == GroundingStatus.UNGROUNDED:
            continue

        computed_kcal = nutrition.per_serving.calories
        if not (IMPLAUSIBLE_MIN_KCAL_PER_SERVING <= computed_kcal <= IMPLAUSIBLE_MAX_KCAL_PER_SERVING):
            implausible_band_corpus_count += 1

        if not recipe.calories:
            continue
        ratio = computed_kcal / recipe.calories
        report.ratio_distribution.append(ratio)
        if ratio < RATIO_OUTLIER_MIN or ratio > RATIO_OUTLIER_MAX:
            report.ratio_outliers.append(
                RatioOutlier(
                    recipe_id=recipe.recipe_id,
                    title=recipe.title,
                    tag_kcal=recipe.calories,
                    computed_kcal=computed_kcal,
                    ratio=ratio,
                )
            )
    report.implausible_band_corpus_count = implausible_band_corpus_count
    report.rejection_counts = dict(rejection_counts or {})

    return report


def render_report(report: GroundingReport) -> str:
    lines: list[str] = ["# Grounding report", ""]

    lines.append("## Corpus-wide summary")
    lines.append(f"- total recipes processed: {report.total_recipes}")
    for status in ("grounded", "partial", "ungrounded"):
        count = report.status_counts.get(status, 0)
        pct = (count / report.total_recipes * 100) if report.total_recipes else 0.0
        lines.append(f"- {status}: {count} ({pct:.1f}%)")
    lines.append("")

    lines.append(f"## Top ungrounded ingredients, corpus-wide (top {len(report.ungrounded_frequency)} of up to 50)")
    lines.append("")
    if not report.ungrounded_frequency:
        lines.append("None.")
    else:
        lines.append("| ingredient (normalized) | recipes affected |")
        lines.append("|---|---|")
        for row in report.ungrounded_frequency:
            lines.append(f"| {row.name} | {row.recipe_count} |")
    lines.append("")

    lines.append(
        "## Tag-vs-computed ratio distribution, corpus-wide "
        "(GROUNDED/PARTIAL recipes with a self-reported tag calorie value)"
    )
    lines.append("")
    dist = report.ratio_distribution
    if not dist:
        lines.append("No corpus recipes have both a computed ratio and a self-reported tag calorie value.")
    else:
        lines.append(f"- n: {len(dist)}")
        lines.append(f"- mean: {statistics.mean(dist):.2f}x")
        lines.append(f"- median: {statistics.median(dist):.2f}x")
        if len(dist) > 1:
            lines.append(f"- stdev: {statistics.stdev(dist):.2f}")
        lines.append(f"- min: {min(dist):.2f}x")
        lines.append(f"- max: {max(dist):.2f}x")
    lines.append("")
    lines.append(
        f"### Ratio outliers (outside [{RATIO_OUTLIER_MIN:.1f}x, {RATIO_OUTLIER_MAX:.1f}x]) -- report-only, no demotion"
    )
    lines.append(f"- count: {len(report.ratio_outliers)}")
    if report.ratio_outliers:
        lines.append("")
        lines.append("| recipe_id | title | tag kcal | computed kcal | ratio |")
        lines.append("|---|---|---|---|---|")
        shown = report.ratio_outliers[:_RATIO_OUTLIER_TABLE_LIMIT]
        for row in shown:
            lines.append(f"| {row.recipe_id} | {row.title} | {row.tag_kcal:.0f} | {row.computed_kcal:.0f} | {row.ratio:.2f}x |")
        if len(report.ratio_outliers) > len(shown):
            lines.append(f"| ... | ({len(report.ratio_outliers) - len(shown)} more, see full count above) | | | |")
    lines.append("")

    lines.append(
        f"## Corpus-wide implausible kcal/serving band "
        f"(<{IMPLAUSIBLE_MIN_KCAL_PER_SERVING:.0f} or >{IMPLAUSIBLE_MAX_KCAL_PER_SERVING:.0f}), GROUNDED/PARTIAL only"
    )
    lines.append(f"- count: {report.implausible_band_corpus_count}")
    lines.append("")

    lines.append("## Plausibility rejection counts by reason, corpus-wide (candidates rejected while matching)")
    lines.append("")
    if not report.rejection_counts:
        lines.append("None recorded (either no candidates were rejected, or the report was built without a live client's diagnostics -- see `build_report`'s `rejection_counts` parameter).")
    else:
        lines.append("| reason | count |")
        lines.append("|---|---|")
        for reason, count in sorted(report.rejection_counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {reason} | {count} |")
    lines.append("")

    lines.append(f"## Seed tag-vs-computed comparison ({len(report.seed_rows)} recipes)")
    lines.append("")
    lines.append("| recipe_id | title | status | coverage | tag kcal | computed kcal | ratio |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in report.seed_rows:
        ratio_str = f"{row.ratio:.2f}x" if row.ratio is not None else "n/a"
        tag_str = f"{row.tag_kcal:.0f}" if row.tag_kcal is not None else "n/a"
        flags = []
        if row.raw_cooked_blowup:
            flags.append("RAW/COOKED BLOWUP")
        if row.implausible_band:
            flags.append("IMPLAUSIBLE BAND")
        flag_str = f" **[{', '.join(flags)}]**" if flags else ""
        lines.append(
            f"| {row.recipe_id} | {row.title} | {row.status.value} | {row.coverage:.0%} "
            f"| {tag_str} | {row.computed_kcal:.0f} | {ratio_str}{flag_str} |"
        )
    lines.append("")

    lines.append(f"## Flags: raw/cooked-scale blowup (>{RAW_COOKED_BLOWUP_RATIO:.1f}x)")
    blowups = report.raw_cooked_blowup_flags()
    if not blowups:
        lines.append("None.")
    else:
        for row in blowups:
            lines.append(f"- **{row.recipe_id}** ({row.title}): ratio {row.ratio:.2f}x")
    lines.append("")

    lines.append(
        f"## Flags: implausible kcal/serving band "
        f"(<{IMPLAUSIBLE_MIN_KCAL_PER_SERVING:.0f} or >{IMPLAUSIBLE_MAX_KCAL_PER_SERVING:.0f})"
    )
    implausible = report.implausible_band_flags()
    if not implausible:
        lines.append("None.")
    else:
        for row in implausible:
            lines.append(f"- **{row.recipe_id}** ({row.title}): {row.computed_kcal:.0f} kcal/serving")
    lines.append("")

    lines.append("## Known residuals (investigated, deliberately not fixed further)")
    lines.append("")
    for title, description in _KNOWN_RESIDUALS:
        lines.append(f"- **{title}**: {description}")
    lines.append("")

    lines.append("## Per-ingredient grounding detail")
    lines.append("")
    for row in report.seed_rows:
        lines.append(f"### {row.recipe_id} -- {row.title} ({row.status.value}, coverage {row.coverage:.0%})")
        lines.append("| ingredient | grounded | grams | detail |")
        lines.append("|---|---|---|---|")
        for ing in row.ingredients:
            grams_str = f"{ing.grams:.1f}" if ing.grams is not None else "n/a"
            lines.append(f"| {ing.name} | {ing.grounded} | {grams_str} | {ing.detail} |")
        lines.append("")

    return "\n".join(lines)
