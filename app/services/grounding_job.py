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
from app.services.usda_client import (
    REASON_ALL_CANDIDATES_REJECTED,
    REASON_GROUNDED,
    REASON_NO_RELEVANT_CANDIDATE,
    UsdaClient,
)
from app.utils.ingredient_normalizer import normalize_ingredient
from app.utils.logging import get_logger
from app.utils.unit_converter import to_grams

logger = get_logger(__name__)

# --- Corpus-wide per-ingredient-occurrence terminal-outcome tally ---
#
# Distinct from `UsdaClient.rejection_counts` (an aggregate, per-CANDIDATE
# tally -- see its docstring, and the retitled table in `render_report`):
# this classifies the FINAL fate of every single ingredient occurrence in
# the corpus into exactly one of five mutually-exclusive buckets, in the
# same two-stage order `compute_recipe_macros` itself uses (unit conversion,
# then USDA matching) so the totals reconcile against the corpus's actual
# ingredient-row count (see `_terminal_outcome_for_ingredient` and the
# assertion in `run_grounding`):
#   - TERMINAL_NO_UNIT: `ingredient.unit` is `None` and `to_grams` could not
#     resolve an amount anyway (no per-piece weight for a bare count either)
#     -- `search_food` is never reached. This is the corpus's dominant
#     failure mode (see the phase 1.5 closeout report: ~35,059/35,183
#     imported ingredient rows have `unit: None`).
#   - TERMINAL_UNIT_UNCONVERTIBLE: `ingredient.unit` IS set, but `to_grams`
#     still returned `None` (most commonly a volume unit with no density
#     entry for this ingredient, or a mass/volume/count unit string
#     `to_grams` doesn't recognize at all) -- `search_food` is never
#     reached either.
#   - TERMINAL_NO_RELEVANT_CANDIDATE / TERMINAL_ALL_CANDIDATES_REJECTED /
#     TERMINAL_GROUNDED: `to_grams` succeeded and `search_food_with_reason`
#     was actually called -- see `UsdaClient.search_food_with_reason`'s
#     docstring for exactly how these three are distinguished. Note a
#     declared-`preparation` candidate that fails the state-classification
#     gate (see `_best_match`) currently falls under
#     TERMINAL_NO_RELEVANT_CANDIDATE, not TERMINAL_ALL_CANDIDATES_REJECTED
#     -- that gate doesn't record a `rejections` entry the way the
#     plausibility/modifier gates do, so it isn't distinguishable from
#     "nothing relevant was found at all" with the data available today.
TERMINAL_NO_UNIT = "no_unit"
TERMINAL_UNIT_UNCONVERTIBLE = "unit_unconvertible"
TERMINAL_NO_RELEVANT_CANDIDATE = REASON_NO_RELEVANT_CANDIDATE
TERMINAL_ALL_CANDIDATES_REJECTED = REASON_ALL_CANDIDATES_REJECTED
TERMINAL_GROUNDED = REASON_GROUNDED

# Rendered table row order (report readability only -- a dict/Counter has no
# guaranteed order worth relying on).
_TERMINAL_OUTCOME_ORDER = [
    TERMINAL_GROUNDED,
    TERMINAL_NO_UNIT,
    TERMINAL_UNIT_UNCONVERTIBLE,
    TERMINAL_NO_RELEVANT_CANDIDATE,
    TERMINAL_ALL_CANDIDATES_REJECTED,
]


def _terminal_outcome_for_ingredient(ingredient: Ingredient, client: UsdaClient) -> str:
    """Classify one ingredient occurrence's terminal outcome -- see the
    module comment above for the five buckets and their precedence.

    Calls `client.search_food_with_reason` a second time for occurrences
    that clear unit conversion (the same query `compute_recipe_macros`
    already issued for this exact ingredient during the main grounding
    pass) -- this is a cache hit against the SAME `UsdaClient`/`FdcCache`
    instance (no additional network I/O), re-running only the deterministic
    Python-side matching logic to recover the terminal reason for the
    report.
    """
    grams = to_grams(ingredient.amount, ingredient.unit, name=ingredient.name)
    if grams is None:
        return TERMINAL_NO_UNIT if ingredient.unit is None else TERMINAL_UNIT_UNCONVERTIBLE

    search_with_reason = getattr(client, "search_food_with_reason", None)
    if search_with_reason is not None:
        # `record_diagnostics=False`: this call re-classifies a query the
        # main `compute_recipe_macros` pass already issued once through
        # this same method for this same ingredient occurrence -- without
        # this, the cumulative `rejection_counts`/`branded_dispersion_
        # events` diagnostics would double-count every occurrence that
        # reaches the matching stage (see `search_food_with_reason`'s
        # docstring).
        _match, reason = search_with_reason(
            ingredient.name, preparation=ingredient.preparation, record_diagnostics=False
        )
        return reason

    # Fallback for a caller-supplied test double that only implements the
    # bare `search_food(name, *, preparation=None) -> FoodMatch | None`
    # contract (see many test doubles in test_grounding_job.py/test_
    # nutrition_grounding.py) -- can still tell grounded from not-grounded,
    # but can't distinguish the two failure sub-reasons without the richer
    # method, so it reports the coarser TERMINAL_NO_RELEVANT_CANDIDATE
    # rather than raising `AttributeError`. Never hit by the real
    # `UsdaClient`, which always has `search_food_with_reason`.
    match = client.search_food(ingredient.name, preparation=ingredient.preparation)
    return TERMINAL_GROUNDED if match is not None else TERMINAL_NO_RELEVANT_CANDIDATE

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
# for manual review -- not auto-corrected. Originally (item 1.4) checked only
# for the 25 seeds and report-only; phase 1.5 item 4/P3 extends this
# corpus-wide AND writes it into the sidecar as a trust-DEMOTING flag (see
# DEMOTING_FLAG_IMPLAUSIBLE_KCAL / `_apply_trust_flags`) -- an implausible
# computed value must not be silently trusted just because every ingredient
# happened to ground. See app.services.nutrition_view for the chokepoint
# that enforces the demotion.
IMPLAUSIBLE_MIN_KCAL_PER_SERVING = 20.0
IMPLAUSIBLE_MAX_KCAL_PER_SERVING = 2000.0

# Trust-demoting flag reason code written to `RecipeNutrition.flags` (see
# `_apply_trust_flags`) when per-serving kcal falls outside the band above.
# Computed purely from this recipe's own computed values -- never from its
# self-reported tag macros, and never from an LLM.
DEMOTING_FLAG_IMPLAUSIBLE_KCAL = "implausible_kcal_per_serving"

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
        "zucchini (RESOLVED by phase 1.5/P4)",
        "Previously stuck on a Branded 'Zucchini, pickled' match: FDC's "
        "canonical zucchini record is filed under 'Squash' (e.g. 'Squash, "
        "summer, green, zucchini, includes skin, raw'), not 'Zucchini', so "
        "the relevance check's head-noun rule correctly refused to treat "
        "that as the same food as a bare 'zucchini' query without an "
        "explicit vocabulary mapping. Resolved by adding "
        "usda_client._FDC_QUERY_ALIASES['zucchini'] = 'squash zucchini' -- "
        "now resolves to the real raw Foundation record (~17-21 kcal/100g).",
    ),
    (
        "ginger (RESOLVED by phase 1.5/P4)",
        "Previously the only reachable Branded record reported 0 kcal/100g "
        "(a data defect the P1 plausibility gate correctly rejects as "
        "'kcal_too_low_branded'), leaving it UNGROUNDED. Resolved by adding "
        "usda_client._FDC_QUERY_ALIASES['ginger'] = 'spices ginger ground', "
        "which reaches the real SR Legacy 'Spices, ginger, ground' record "
        "(~335 kcal/100g) at the generic tier, never reaching the defective "
        "Branded record at all.",
    ),
    (
        "shrimp / tomato sauce",
        "Explicitly excluded via usda_client._KNOWN_UNRELIABLE_QUERIES -- "
        "both reliably resolve to a wrong-form match with no preparation "
        "declaration able to gate it (a sauce/seafood has no honest "
        "raw/cooked/canned state), and both wrong-form matches' macros are "
        "plausible-looking enough to clear the P1 plausibility gate too. "
        "Render UNGROUNDED rather than a confidently wrong number.",
    ),
    (
        "chili powder",
        "The only reachable Branded record reports 0 kcal/100g -- a data "
        "defect the P1 plausibility gate correctly rejects as "
        "'kcal_too_low_branded', and no generic-tier 'Spices, chili powder' record "
        "was found to alias to (unlike the other spices resolved in "
        "phase 1.5/P4) -- stays on usda_client._KNOWN_UNRELIABLE_QUERIES "
        "as a disclosed, deliberate exclusion pending that verification.",
    ),
    (
        "salt / baking soda / baking powder (RESOLVED by phase 1.5 closeout/P2 -- was a plausibility-gate tension, "
        "NOT alias-fixable; the corpus-wide cap on these is now the unit problem below, not this)",
        "Live-verified (phase 1.5/P4 investigation): the real, relevant FDC "
        "records for these (e.g. 'Salt, table') report a true, physically "
        "correct near-zero kcal/100g -- not a data defect. The gate's "
        "absolute floor (_PLAUSIBLE_MIN_KCAL = 5, written to catch a 0-kcal "
        "Branded data-entry defect) used to reject them for the same reason "
        "it correctly rejects a genuine defect: it could not distinguish "
        "'this food really is ~calorie-free' from 'this record is wrong.' "
        "RESOLVED by phase 1.5 closeout/P2: the floor is now applied only to "
        "Branded candidates (see usda_client._plausibility_reject_reason's "
        "module comment) -- Foundation/SR Legacy/Survey candidates fall "
        "through to the mass + Atwater checks instead, which correctly pass "
        "a genuine all-zero record. This does NOT mean salt/baking soda/"
        "baking powder now ground corpus-wide, though: the overwhelming "
        "majority of their occurrences never reach `search_food` at all, "
        "because the imported corpus's ingredient rows have `unit: None` "
        "at the data level (see the corpus-wide terminal-outcome tally's "
        "`no_unit` bucket) -- a separate, NOT-fixed-here problem. In "
        "practice these ingredients' calorie contribution to a recipe is "
        "genuinely negligible regardless.",
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
class BrandedDispersionEvent:
    """One Branded-tier query (item 4/P5, `usda_client._select_branded_match`)
    where 3+ otherwise-eligible candidates disagreed by more than a 3x
    calorie ratio, so the query was left ungrounded rather than picking one
    candidate arbitrarily -- report-only, see UsdaClient.branded_dispersion_
    events."""

    query: str
    min_kcal: float
    max_kcal: float
    candidate_count: int


@dataclass
class MacroErrorStat:
    """Aggregate absolute-relative-error stat for one macro, over exactly the
    seeds that had BOTH a real computed value and a usable self-reported tag
    ground truth for it (see `SeedMacroAccuracy` for the missing/excluded
    split). `n == 0` (no seed qualified) renders both error fields `None`
    rather than a misleading 0.0."""

    n: int
    median_abs_relative_error: float | None
    mean_abs_relative_error: float | None


@dataclass
class SeedMacroAccuracy:
    """Pre-registered A3 eval (docs/ROADMAP.md item A3): "macro-computation
    accuracy measured against the 25 hand-authored seed recipes as ground
    truth". These metric definitions are fixed BEFORE the corpus-wide A3
    grounding run and must not be adjusted after seeing results.

    For each macro (kcal, protein_g, carbs_g, fat_g), a seed contributes to
    that macro's `MacroErrorStat` only when BOTH:
      1. the seed's grounding status is GROUNDED or PARTIAL -- an UNGROUNDED
         seed has no real computed value at all (its `per_serving` macros
         are all-zero placeholders from an empty sum, not a measurement --
         see `nutrition_grounding.compute_recipe_macros`), so it can never
         supply a computed value to compare.
      2. the seed has a non-null, non-zero self-reported tag value for that
         macro (a zero or missing tag denominator makes a *relative* error
         undefined, not zero).
    Every seed excluded by either rule is counted in the matching
    `*_missing` field instead of being silently dropped -- "reported
    missing," never invisible. `kcal` is the PRIMARY metric per the
    pre-registered gate; the three per-macro stats are secondary detail.
    """

    n_seeds: int
    n_grounded: int
    n_partial: int
    n_ungrounded: int
    kcal: MacroErrorStat
    kcal_missing: int
    protein_g: MacroErrorStat
    protein_g_missing: int
    carbs_g: MacroErrorStat
    carbs_g_missing: int
    fat_g: MacroErrorStat
    fat_g_missing: int


def _macro_error_stat(errors: list[float]) -> MacroErrorStat:
    if not errors:
        return MacroErrorStat(n=0, median_abs_relative_error=None, mean_abs_relative_error=None)
    return MacroErrorStat(
        n=len(errors),
        median_abs_relative_error=statistics.median(errors),
        mean_abs_relative_error=statistics.mean(errors),
    )


def compute_seed_macro_accuracy(
    seeds_by_id: dict[str, Recipe], results: dict[str, RecipeNutrition]
) -> SeedMacroAccuracy:
    """Build the pre-registered A3 seed-accuracy aggregate -- see
    `SeedMacroAccuracy`'s docstring for the exact, fixed metric definitions.

    A seed in `seeds_by_id` absent from `results` (only possible when the
    caller ran grounding over a corpus that didn't include every seed, e.g.
    an isolated test) is excluded from `n_seeds` entirely, the same
    "nothing to compare" treatment the per-seed `SeedRow` table already
    uses -- there is no computed value at all to classify, not even as
    ungrounded.
    """
    n_grounded = n_partial = n_ungrounded = 0
    kcal_errors: list[float] = []
    protein_errors: list[float] = []
    carbs_errors: list[float] = []
    fat_errors: list[float] = []
    kcal_missing = protein_missing = carbs_missing = fat_missing = 0

    for recipe_id in sorted(seeds_by_id):
        seed = seeds_by_id[recipe_id]
        nutrition = results.get(recipe_id)
        if nutrition is None:
            continue

        if nutrition.status == GroundingStatus.GROUNDED:
            n_grounded += 1
        elif nutrition.status == GroundingStatus.PARTIAL:
            n_partial += 1
        else:
            n_ungrounded += 1

        has_computed_value = nutrition.status != GroundingStatus.UNGROUNDED

        if has_computed_value and seed.calories:
            kcal_errors.append(abs(nutrition.per_serving.calories - seed.calories) / seed.calories)
        else:
            kcal_missing += 1

        if has_computed_value and seed.protein_g:
            protein_errors.append(abs(nutrition.per_serving.protein_g - seed.protein_g) / seed.protein_g)
        else:
            protein_missing += 1

        if has_computed_value and seed.carbs_g:
            carbs_errors.append(abs(nutrition.per_serving.carbs_g - seed.carbs_g) / seed.carbs_g)
        else:
            carbs_missing += 1

        if has_computed_value and seed.fat_g:
            fat_errors.append(abs(nutrition.per_serving.fat_g - seed.fat_g) / seed.fat_g)
        else:
            fat_missing += 1

    return SeedMacroAccuracy(
        n_seeds=n_grounded + n_partial + n_ungrounded,
        n_grounded=n_grounded,
        n_partial=n_partial,
        n_ungrounded=n_ungrounded,
        kcal=_macro_error_stat(kcal_errors),
        kcal_missing=kcal_missing,
        protein_g=_macro_error_stat(protein_errors),
        protein_g_missing=protein_missing,
        carbs_g=_macro_error_stat(carbs_errors),
        carbs_g_missing=carbs_missing,
        fat_g=_macro_error_stat(fat_errors),
        fat_g_missing=fat_missing,
    )


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
    branded_dispersion_events: list[BrandedDispersionEvent] = field(default_factory=list)
    # Corpus-wide per-ingredient-OCCURRENCE terminal-outcome tally -- see the
    # module comment above `_terminal_outcome_for_ingredient` for the five
    # buckets. Unlike `rejection_counts`, these counts are mutually
    # exclusive and sum to the corpus's total ingredient-row count exactly
    # (see the assertion in `run_grounding`).
    terminal_outcome_counts: dict[str, int] = field(default_factory=dict)
    # Pre-registered A3 eval aggregate -- see `SeedMacroAccuracy`/
    # `compute_seed_macro_accuracy`. `None` only for a `GroundingReport`
    # built without going through `build_report` (should not happen in
    # practice; `build_report` always computes it from `seeds`/`results`).
    seed_macro_accuracy: SeedMacroAccuracy | None = None

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


def _is_implausible_kcal(nutrition: RecipeNutrition) -> bool:
    """True if `nutrition`'s own computed per-serving kcal falls outside
    [IMPLAUSIBLE_MIN_KCAL_PER_SERVING, IMPLAUSIBLE_MAX_KCAL_PER_SERVING] --
    only meaningful for a GROUNDED/PARTIAL recipe (UNGROUNDED has no
    computed total to judge, and is never flagged this way)."""
    if nutrition.status == GroundingStatus.UNGROUNDED:
        return False
    kcal = nutrition.per_serving.calories
    return not (IMPLAUSIBLE_MIN_KCAL_PER_SERVING <= kcal <= IMPLAUSIBLE_MAX_KCAL_PER_SERVING)


def _apply_trust_flags(nutrition: RecipeNutrition) -> RecipeNutrition:
    """Sets trust-DEMOTING flags on `nutrition` (mutates `nutrition.flags`
    and returns the same object) based purely on its own already-computed
    values -- never the recipe's self-reported tag macros, never an LLM.
    Currently the only flag is the implausible per-serving-kcal band; see
    `DEMOTING_FLAG_IMPLAUSIBLE_KCAL`. Called by `run_grounding` for every
    corpus recipe before the sidecar is written, so the flag is a durable
    part of the sidecar itself -- not recomputed ad hoc by report code."""
    if _is_implausible_kcal(nutrition) and DEMOTING_FLAG_IMPLAUSIBLE_KCAL not in nutrition.flags:
        nutrition.flags.append(DEMOTING_FLAG_IMPLAUSIBLE_KCAL)
    return nutrition


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
    terminal_outcome_counts: Counter[str] = Counter()
    total_ingredient_occurrences = 0
    for recipe in sorted(corpus, key=lambda r: r.recipe_id):
        nutrition = compute_recipe_macros(recipe.ingredients, servings=recipe.servings or 1, client=client)
        results[recipe.recipe_id] = _apply_trust_flags(nutrition)
        for ingredient in recipe.ingredients:
            total_ingredient_occurrences += 1
            terminal_outcome_counts[_terminal_outcome_for_ingredient(ingredient, client)] += 1

    # The five buckets are constructed to be mutually exclusive and
    # exhaustive over every ingredient occurrence in `corpus` (see the
    # module comment above `_terminal_outcome_for_ingredient`) -- this is
    # what makes the tally trustworthy rather than just another partial
    # count. A mismatch here would mean the classification logic itself is
    # broken (e.g. double-counting or silently skipping an occurrence), not
    # a data quirk, so it fails loudly rather than shipping a report with an
    # unreconciled table.
    assert sum(terminal_outcome_counts.values()) == total_ingredient_occurrences, (
        f"terminal-outcome tally ({sum(terminal_outcome_counts.values())}) does not reconcile "
        f"with total ingredient occurrences ({total_ingredient_occurrences})"
    )

    _write_sidecar(Path(sidecar_path), results)

    # `rejection_counts`/`branded_dispersion_events` are diagnostic-only
    # attributes on `UsdaClient` (see their docstrings) -- read defensively
    # via getattr so a caller-supplied test double without them still
    # works, reporting simply nothing rejected/dispersed.
    rejection_counts = dict(getattr(client, "rejection_counts", {}) or {})
    branded_dispersion_raw = getattr(client, "branded_dispersion_events", []) or []
    branded_dispersion_events = [
        BrandedDispersionEvent(query=query, min_kcal=min_kcal, max_kcal=max_kcal, candidate_count=count)
        for query, min_kcal, max_kcal, count in branded_dispersion_raw
    ]
    report = build_report(
        corpus=corpus,
        seeds=seeds,
        results=results,
        rejection_counts=rejection_counts,
        branded_dispersion_events=branded_dispersion_events,
        terminal_outcome_counts=dict(terminal_outcome_counts),
    )

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
    branded_dispersion_events: list[BrandedDispersionEvent] | None = None,
    terminal_outcome_counts: dict[str, int] | None = None,
) -> GroundingReport:
    """Build a `GroundingReport` purely from already-computed data -- no
    `UsdaClient`, no network, no re-fetching. This is what lets a report be
    regenerated instantly from an existing sidecar (e.g. `data/processed/
    grounding.jsonl` loaded via `app.rag.loaders.load_corpus`/
    `load_grounding`) to capture a point-in-time baseline before a
    matching-rule change, without spending a single live FDC call.

    `results` must be keyed by `recipe_id`; a `corpus` recipe absent from it
    is simply skipped in every corpus-wide diagnostic (never fabricated).

    `terminal_outcome_counts`, like `rejection_counts`/`branded_dispersion_
    events`, must be computed by the caller (see `run_grounding`, the only
    place with a live `client` to classify occurrences against) -- this
    function only stores whatever it's handed, never recomputes it, so a
    report rebuilt from a sidecar without a client still renders (with this
    table simply empty).
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

        # Same underlying band check `_apply_trust_flags` used to set
        # `nutrition.flags` -- kept as a direct check here (not a
        # `DEMOTING_FLAG_IMPLAUSIBLE_KCAL in nutrition.flags` lookup) so this
        # report field works identically whether or not the `results` this
        # function was handed already went through `_apply_trust_flags`
        # (e.g. `build_report` invoked directly on a hand-built RecipeNutrition
        # in a test, or on an older sidecar).
        implausible = _is_implausible_kcal(nutrition)
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
        if _is_implausible_kcal(nutrition):
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
    report.branded_dispersion_events = list(branded_dispersion_events or [])
    report.terminal_outcome_counts = dict(terminal_outcome_counts or {})
    report.seed_macro_accuracy = compute_seed_macro_accuracy(seeds_by_id, results)

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
    lines.append(
        "**Comparability note (A3 prep):** the pre-A3 baseline "
        "(`data/processed/grounding_report_pre_A3_baseline.md`, grounded 0.4% / "
        "partial 59.2%) was computed against the OLD, pre-A1 corpus of 4,263 "
        "recipes (near-zero unit coverage, 0.35%). The A1 corpus rebuild "
        "replaced that corpus with 3,853 active imported recipes + 25 "
        "hand-authored seeds and raised unit coverage to 76.14% -- the "
        "`total recipes processed` count above states THIS run's corpus size "
        "so the before/after grounded/partial/ungrounded percentages are read "
        "against the right denominator, not silently compared across two "
        "different corpora of different sizes. `data/processed/"
        "grounding_report_baseline.md` is a separate, even older snapshot "
        "(also pre-A1, from an earlier point in phase 1.5) -- do not confuse "
        "the two baseline files."
    )
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

    lines.append(
        "## Corpus-wide ingredient-occurrence terminal outcomes "
        "(what actually happens to every ingredient row)"
    )
    lines.append("")
    lines.append(
        "Every ingredient occurrence in the corpus lands in EXACTLY ONE of the buckets below "
        "(mutually exclusive, and reconciled at grounding time to sum to the corpus's total "
        "ingredient-row count -- see `grounding_job._terminal_outcome_for_ingredient`). This is "
        "the table that explains ungroundedness; the rejection-counts table further below does NOT."
    )
    lines.append("")
    if not report.terminal_outcome_counts:
        lines.append(
            "None recorded (the report was built without a live client's diagnostics -- see "
            "`build_report`'s `terminal_outcome_counts` parameter)."
        )
    else:
        total = sum(report.terminal_outcome_counts.values())
        lines.append("| outcome | count | % of occurrences |")
        lines.append("|---|---|---|")
        for outcome in _TERMINAL_OUTCOME_ORDER:
            count = report.terminal_outcome_counts.get(outcome, 0)
            pct = (count / total * 100) if total else 0.0
            lines.append(f"| {outcome} | {count} | {pct:.1f}% |")
        # Defensive: render any bucket name not in the expected order too,
        # rather than silently dropping it (should not happen in practice --
        # `_terminal_outcome_for_ingredient` only ever returns the five known
        # constants -- but a rendered report should never hide data).
        for outcome, count in report.terminal_outcome_counts.items():
            if outcome not in _TERMINAL_OUTCOME_ORDER:
                pct = (count / total * 100) if total else 0.0
                lines.append(f"| {outcome} (unexpected) | {count} | {pct:.1f}% |")
    lines.append("")

    lines.append(
        "## Individual-candidate rejection counts by reason, corpus-wide "
        "(NOT a table of ungroundedness causes)"
    )
    lines.append("")
    lines.append(
        "**Read this table carefully.** Each count is the number of individual FDC CANDIDATES "
        "skipped during matching for the reason shown -- tallied once per candidate, across every "
        "`search_food` call this run made. It is NOT a count of queries/occurrences that failed "
        "to ground, and it is NOT a list of \"why ingredients are ungrounded\" (see the terminal-"
        "outcome table above for that). A query whose candidate was skipped here may still have "
        "gone on to ground successfully via a later candidate or the Branded fallback -- e.g. "
        "`processed_state_modifier:creamed` is almost entirely the imported corpus's egg "
        "occurrences correctly skipping an 'Egg, creamed' candidate while still grounding fine "
        "against a different candidate."
    )
    lines.append("")
    if not report.rejection_counts:
        lines.append("None recorded (either no candidates were rejected, or the report was built without a live client's diagnostics -- see `build_report`'s `rejection_counts` parameter).")
    else:
        lines.append("| reason | candidates skipped |")
        lines.append("|---|---|")
        for reason, count in sorted(report.rejection_counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {reason} | {count} |")
    lines.append("")

    lines.append(
        "## Branded-tier high-dispersion queries, corpus-wide (3+ candidates, >3.0x calorie spread -- left ungrounded)"
    )
    lines.append("")
    lines.append(f"- count: {len(report.branded_dispersion_events)}")
    if report.branded_dispersion_events:
        lines.append("")
        lines.append("| query | min kcal | max kcal | candidates |")
        lines.append("|---|---|---|---|")
        for event in report.branded_dispersion_events:
            lines.append(f"| {event.query} | {event.min_kcal:.0f} | {event.max_kcal:.0f} | {event.candidate_count} |")
    lines.append("")

    lines.append("## Seed macro-computation accuracy (pre-registered A3 eval)")
    lines.append("")
    lines.append(
        "Pre-registered gate (docs/ROADMAP.md item A3): \"macro-computation accuracy measured "
        "against the 25 hand-authored seed recipes as ground truth.\" These metric definitions "
        "(see `SeedMacroAccuracy`/`compute_seed_macro_accuracy` in `app/services/grounding_job.py`) "
        "were fixed BEFORE the corpus-wide A3 grounding run and are not adjusted after seeing "
        "results. A seed contributes to a macro's error only when its status is GROUNDED or "
        "PARTIAL (an UNGROUNDED seed has no real computed value) AND it has a non-null, "
        "non-zero self-reported tag value for that macro -- every seed excluded either way is "
        "counted as \"missing\" below, never silently dropped. **kcal is the PRIMARY metric.**"
    )
    lines.append("")
    accuracy = report.seed_macro_accuracy
    if accuracy is None:
        lines.append(
            "Not computed (this report was built without `seed_macro_accuracy` -- should not "
            "happen via `build_report`)."
        )
    else:
        lines.append(
            f"- seeds: {accuracy.n_seeds} total -- {accuracy.n_grounded} grounded, "
            f"{accuracy.n_partial} partial, {accuracy.n_ungrounded} ungrounded"
        )
        lines.append("")
        lines.append("| macro | n compared | median abs relative error | mean abs relative error | missing (excluded) |")
        lines.append("|---|---|---|---|---|")
        for label, stat, missing in (
            ("**kcal (PRIMARY)**", accuracy.kcal, accuracy.kcal_missing),
            ("protein_g", accuracy.protein_g, accuracy.protein_g_missing),
            ("carbs_g", accuracy.carbs_g, accuracy.carbs_g_missing),
            ("fat_g", accuracy.fat_g, accuracy.fat_g_missing),
        ):
            median_str = f"{stat.median_abs_relative_error:.1%}" if stat.median_abs_relative_error is not None else "n/a"
            mean_str = f"{stat.mean_abs_relative_error:.1%}" if stat.mean_abs_relative_error is not None else "n/a"
            lines.append(f"| {label} | {stat.n} | {median_str} | {mean_str} | {missing} |")
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
