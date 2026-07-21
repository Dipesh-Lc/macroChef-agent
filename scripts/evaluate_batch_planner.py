"""scripts/evaluate_batch_planner.py -- quality eval for the meal-prep
batch solver (roadmap Phase 4 item 1, app.services.batch_planner).

THIS IS A QUALITY EVAL, NOT A SAFETY GATE. It measures how well
app.services.batch_planner assembles a per-container macro-targeted batch
plan out of the CURRENT trusted (fully-GROUNDED, flag-free) recipe pool. It
has no allergy/diet awareness and proves nothing about safety -- it must
NEVER be wired into scripts/run_safety_benchmark.py, whose adjudicated-true
`inherent` violation rate is the actual release gate (see CLAUDE.md
"Honest scope").

PRE-REGISTERED (fixed before this script was ever run, per the meal-prep
batch solver design consult -- do not tune anything below after seeing a
result):
  - Tolerance: +/-10% kcal AND +/-15% protein, applied PER CONTAINER
    (app.services.day_planner.DEFAULT_TOLERANCE, reused verbatim by
    app.services.batch_planner -- unchanged here).
  - Random seed: EVAL_SEED below, fixed (used only for reproducibility
    bookkeeping; bucket 1 deterministically sweeps every trusted recipe,
    no sampling is actually needed at today's ~15-recipe pool size).
  - Bucket 1 ("planted-feasible", a correctness proof): for EVERY trusted
    recipe, its OWN per-serving macros become the per-container target --
    by construction that recipe is eligible with ~0 error, so the solver
    MUST return a non-empty, within_tolerance=True batch that includes it.
    Expected result: ~100% feasibility, ~0 median per-container error
    (exact 0 unlikely due to floating point / rounding in
    grounding_job's computed macros -- that is fine, noted, not a bug).
  - Bucket 2 ("realistic-round", honest real-world numbers): a small FIXED
    list of human-plausible per-container macro targets: (500 kcal, 40 g),
    (600 kcal, 45 g), (450 kcal, 35 g), (700 kcal, 50 g). Measured
    honestly -- the trusted pool is currently only ~15 recipes (see
    app.services.day_planner's module docstring, "THE CRUX FINDING", and
    app.services.batch_planner's own docstring), and the PER-CONTAINER band
    this solver applies is a HARDER constraint than B3's summed band (every
    selected recipe's own per-serving macros must individually fit, not
    just the sum) -- so LOW feasibility here is EXPECTED and is a correctly
    reported consequence of small grounding coverage plus the stricter
    per-container semantics, not a bug in the solver. Do NOT tune the
    bucket contents or the tolerance to inflate this number.

Reports, for each bucket: feasibility_rate (fraction of targets that
produced a within_tolerance=True plan), mean eligible-recipe count, and
(for bucket 2 only, since bucket 1's target IS a produced container's own
macros by construction) median per-container kcal/protein relative error
over every PRODUCED CONTAINER in the feasible subset (each selected
recipe's fit error counted once per container it fills, i.e. weighted by
container_count -- not averaged per-recipe).
"""

from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rag.loaders import load_corpus  # noqa: E402
from app.schemas.recipe import Recipe  # noqa: E402
from app.services.batch_planner import (  # noqa: E402
    DEFAULT_CONTAINERS,
    DEFAULT_MAX_RECIPES,
    DEFAULT_MIN_RECIPES,
    DEFAULT_TOLERANCE,
    assemble_batch_plan,
)
from app.services.nutrition_view import trusted_per_serving  # noqa: E402

EVAL_SEED = 20260720  # fixed, pre-registered -- never changed after a run


def _trusted_pool() -> list[Recipe]:
    """The exact same trust boundary app.services.batch_planner uses
    internally (app.services.nutrition_view.trusted_per_serving) --
    reimplemented at the top level here only so this script can print the
    pool size and build planted targets from it; assembly itself always
    goes through assemble_batch_plan's own (re-applied) filtering."""
    corpus = load_corpus()
    seen: set[str] = set()
    pool: list[Recipe] = []
    for recipe in corpus:
        if recipe.recipe_id in seen:
            continue
        if trusted_per_serving(recipe) is None:
            continue
        seen.add(recipe.recipe_id)
        pool.append(recipe)
    return pool


def _eligible_count(pool: list[Recipe], target_kcal: float, target_protein: float) -> int:
    """Reimplemented locally (never imports batch_planner's private
    `_container_eligible`) purely for the "eligible-recipe count" reporting
    column -- assembly itself only ever goes through assemble_batch_plan's
    own public surface."""
    count = 0
    for recipe in pool:
        macros = trusted_per_serving(recipe)
        assert macros is not None  # pool is pre-filtered trusted
        kcal_error = abs(macros.calories - target_kcal) / target_kcal if target_kcal else 0.0
        protein_error = abs(macros.protein_g - target_protein) / target_protein if target_protein else 0.0
        if kcal_error <= DEFAULT_TOLERANCE.kcal_pct and protein_error <= DEFAULT_TOLERANCE.protein_pct:
            count += 1
    return count


def planted_feasible_targets(pool: list[Recipe]) -> list[tuple[str, float, float]]:
    """(recipe_id, target_kcal, target_protein) for EVERY trusted recipe --
    its own per-serving macros become the target, so it is eligible with
    ~0 error by construction. No sampling needed at today's ~15-recipe pool
    size; if the pool ever grows past PLANTED_SAMPLE_COUNT-scale, this can
    switch to a random.Random(EVAL_SEED).sample(...) draw the same way
    scripts/evaluate_day_planner.py does -- not needed today."""
    targets = []
    for recipe in pool:
        macros = trusted_per_serving(recipe)
        assert macros is not None
        targets.append((recipe.recipe_id, macros.calories, macros.protein_g))
    return targets


def realistic_round_targets() -> list[tuple[float, float]]:
    return [
        (500.0, 40.0),
        (600.0, 45.0),
        (450.0, 35.0),
        (700.0, 50.0),
    ]


def _container_errors(plan) -> tuple[list[float], list[float]]:
    """Per-produced-container relative errors -- each selected recipe's fit
    error counted once PER CONTAINER it fills (weighted by
    container_count), not averaged per-recipe. Aligns with
    `plan.recipe_fits`, which carries one entry per selected recipe with
    its own `container_count`."""
    kcal_errors: list[float] = []
    protein_errors: list[float] = []
    for fit in plan.recipe_fits:
        kcal_errors.extend([fit.kcal_relative_error] * fit.container_count)
        protein_errors.extend([fit.protein_relative_error] * fit.container_count)
    return kcal_errors, protein_errors


def _run_planted_bucket(pool: list[Recipe], targets: list[tuple[str, float, float]]) -> dict[str, float]:
    hits = 0
    kcal_errors: list[float] = []
    protein_errors: list[float] = []
    eligible_counts: list[int] = []
    for recipe_id, target_kcal, target_protein in targets:
        plan = assemble_batch_plan(
            pool,
            per_container_target_calories=target_kcal,
            per_container_target_protein_g=target_protein,
            containers=DEFAULT_CONTAINERS,
            min_recipes=DEFAULT_MIN_RECIPES,
            max_recipes=DEFAULT_MAX_RECIPES,
        )
        eligible_counts.append(_eligible_count(pool, target_kcal, target_protein))
        selected_ids = {item.recipe_id for item in plan.items}
        if plan.within_tolerance and recipe_id in selected_ids:
            hits += 1
            k_errs, p_errs = _container_errors(plan)
            kcal_errors.extend(k_errs)
            protein_errors.extend(p_errs)

    n = len(targets)
    return {
        "n": n,
        "feasibility_rate": hits / n if n else 0.0,
        "mean_eligible_recipe_count": statistics.mean(eligible_counts) if eligible_counts else float("nan"),
        "median_per_container_kcal_relative_error_feasible": (
            statistics.median(kcal_errors) if kcal_errors else float("nan")
        ),
        "median_per_container_protein_relative_error_feasible": (
            statistics.median(protein_errors) if protein_errors else float("nan")
        ),
    }


def _run_realistic_bucket(pool: list[Recipe], targets: list[tuple[float, float]]) -> dict[str, float]:
    hits = 0
    eligible_counts: list[int] = []
    feasible_kcal_errors: list[float] = []
    feasible_protein_errors: list[float] = []
    for target_kcal, target_protein in targets:
        plan = assemble_batch_plan(
            pool,
            per_container_target_calories=target_kcal,
            per_container_target_protein_g=target_protein,
            containers=DEFAULT_CONTAINERS,
            min_recipes=DEFAULT_MIN_RECIPES,
            max_recipes=DEFAULT_MAX_RECIPES,
        )
        eligible = _eligible_count(pool, target_kcal, target_protein)
        eligible_counts.append(eligible)
        k_errs, p_errs = _container_errors(plan)
        median_kcal = statistics.median(k_errs) if k_errs else float("nan")
        median_protein = statistics.median(p_errs) if p_errs else float("nan")
        print(f"  target={target_kcal} kcal / {target_protein} g protein:")
        print(f"    eligible_recipe_count: {eligible}")
        print(f"    within_tolerance: {plan.within_tolerance}")
        print(f"    recipes_selected: {plan.recipes_selected}")
        print(f"    median_per_container_kcal_relative_error: {median_kcal}")
        print(f"    median_per_container_protein_relative_error: {median_protein}")
        if plan.within_tolerance:
            hits += 1
            feasible_kcal_errors.extend(k_errs)
            feasible_protein_errors.extend(p_errs)

    n = len(targets)
    return {
        "n": n,
        "feasibility_rate": hits / n if n else 0.0,
        "mean_eligible_recipe_count": statistics.mean(eligible_counts) if eligible_counts else float("nan"),
        "median_per_container_kcal_relative_error_feasible": (
            statistics.median(feasible_kcal_errors) if feasible_kcal_errors else float("nan")
        ),
        "median_per_container_protein_relative_error_feasible": (
            statistics.median(feasible_protein_errors) if feasible_protein_errors else float("nan")
        ),
    }


def main() -> None:
    print(__doc__)
    random.Random(EVAL_SEED)  # reserved for reproducibility bookkeeping (see docstring)

    pool = _trusted_pool()
    print(f"Trusted pool size (fully-GROUNDED, flag-free recipes): {len(pool)}")
    if not pool:
        print("Trusted pool is empty -- nothing to evaluate.")
        return

    print("\n=== Bucket 1: planted-feasible (correctness proof) ===")
    planted = planted_feasible_targets(pool)
    report = _run_planted_bucket(pool, planted)
    for key, value in report.items():
        print(f"  {key}: {value}")

    print("\n=== Bucket 2: realistic-round (honest real-world numbers) ===")
    realistic = realistic_round_targets()
    realistic_report = _run_realistic_bucket(pool, realistic)
    print("  --- bucket 2 aggregate ---")
    for key, value in realistic_report.items():
        print(f"  {key}: {value}")

    print(
        "\nThis is a quality eval, not a safety gate -- never wire this "
        "script into scripts/run_safety_benchmark.py. It measures how "
        "close assemble_batch_plan gets to a PER-CONTAINER macro target "
        "given the CURRENT trusted (fully-GROUNDED, flag-free) recipe "
        "pool; it has no allergy/diet awareness and proves nothing about "
        "safety."
    )


if __name__ == "__main__":
    main()
