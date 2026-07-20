"""scripts/evaluate_day_planner.py -- quality eval for the B3 day-plan solver.

THIS IS A QUALITY EVAL, NOT A SAFETY GATE. It measures how well
app.services.day_planner assembles a macro-targeted plan out of the CURRENT
trusted (fully-GROUNDED, flag-free) recipe pool. It has no allergy/diet
awareness and proves nothing about safety -- it must NEVER be wired into
scripts/run_safety_benchmark.py, whose adjudicated-true `inherent`
violation rate is the actual release gate (see CLAUDE.md "Honest scope").

PRE-REGISTERED (fixed before this script was ever run, per the B3 design
consult -- do not tune anything below after seeing a result):
  - Tolerance: +/-10% kcal AND +/-15% protein
    (app.services.day_planner.MacroTolerance defaults, unchanged here).
  - Random seed: EVAL_SEED below, fixed.
  - Bucket 1 ("planted-feasible", a correctness proof): random K-subsets
    (K in 2..4, multiplicity <= MAX_PER_RECIPE) of the CURRENT trusted
    pool are drawn, and their REAL summed macros become the target.
    Expected result: ~0 relative error, ~100% feasibility -- because the
    optimum is planted by construction, this proves the enumerator finds
    the true optimum. It is NOT a claim about real-world usefulness.
  - Bucket 2 ("realistic-round", honest real-world numbers): a small fixed
    list of human-plausible macro targets (2200/160, 1800/120, 2500/180,
    plus a K=1 "remaining macros" 780/52 case). Measured honestly -- the
    trusted pool is currently only ~15 recipes (see
    app.services.day_planner's module docstring, "THE CRUX FINDING"), so
    some or all of these may legitimately come back infeasible. That is
    an expected, correctly-reported consequence of small grounding
    coverage, not a bug in the enumerator -- do not tune the bucket
    contents or the tolerance to hide a low feasibility rate here.

Reports, for each bucket: feasibility_rate (fraction of targets with an
in-tolerance solution) and median absolute relative error computed ONLY
over the feasible subset, kcal and protein reported separately (kcal is
primary, per the B3 eval design).
"""

from __future__ import annotations

import random
import statistics
import sys
from itertools import combinations_with_replacement
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rag.loaders import load_corpus  # noqa: E402
from app.schemas.recipe import Recipe  # noqa: E402
from app.schemas.user import MacroTargets  # noqa: E402
from app.services.day_planner import assemble_day_plan, assemble_plan  # noqa: E402
from app.services.nutrition_view import trusted_per_serving  # noqa: E402

EVAL_SEED = 20260720  # fixed, pre-registered -- never changed after a run
PLANTED_SAMPLE_COUNT = 20  # number of random planted-feasible targets to draw
MAX_PER_RECIPE = 2


def _trusted_pool() -> list[Recipe]:
    """The exact same trust boundary app.services.day_planner uses
    internally (app.services.nutrition_view.trusted_per_serving) --
    reimplemented at the top level here only so this script can print the
    pool size and sample targets from it; assembly itself always goes
    through assemble_plan/assemble_day_plan's own (re-applied) filtering."""
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


def _valid_combos(pool: list[Recipe], k: int, max_per_recipe: int) -> list[tuple[int, ...]]:
    """Every multiset (as a sorted index tuple) of size k from pool, with any
    index appearing at most max_per_recipe times. Deliberately reimplemented
    locally (rather than importing day_planner's private
    `_enumerate_multisets`) so this eval script only ever exercises
    day_planner's PUBLIC surface (assemble_plan / assemble_day_plan)."""
    combos = []
    for combo in combinations_with_replacement(range(len(pool)), k):
        counts: dict[int, int] = {}
        for idx in combo:
            counts[idx] = counts.get(idx, 0) + 1
        if all(count <= max_per_recipe for count in counts.values()):
            combos.append(combo)
    return combos


def _target_from_combo(pool: list[Recipe], combo: tuple[int, ...]) -> MacroTargets:
    total_calories = 0.0
    total_protein = 0.0
    for idx in combo:
        macros = trusted_per_serving(pool[idx])
        assert macros is not None  # pool is pre-filtered to trusted recipes
        total_calories += macros.calories
        total_protein += macros.protein_g
    # MacroTargets.calories is `int | None` (app/schemas/user.py) -- rounding
    # to the nearest whole calorie is the source of the "~0" (not exactly 0)
    # error the planted bucket's docstring above pre-registers.
    return MacroTargets(calories=round(total_calories), protein_g=round(total_protein, 4))


def planted_feasible_targets(pool: list[Recipe], rng: random.Random) -> list[tuple[int, MacroTargets]]:
    """(K, target) pairs built by summing the REAL macros of a random valid
    K-combo -- the true optimum is planted by construction, so a correct
    enumerator must find it (near-)exactly at that same K."""
    candidates: list[tuple[int, tuple[int, ...]]] = []
    for k in (2, 3, 4):
        for combo in _valid_combos(pool, k, MAX_PER_RECIPE):
            candidates.append((k, combo))
    if not candidates:
        return []
    sample_size = min(PLANTED_SAMPLE_COUNT, len(candidates))
    sampled = rng.sample(candidates, sample_size)
    return [(k, _target_from_combo(pool, combo)) for k, combo in sampled]


def realistic_round_targets() -> list[tuple[int | None, MacroTargets]]:
    """meals=None means "day plan" mode (sweeps 2-4); meals=1 is explicitly
    the "remaining macros" case (see
    app.services.day_planner.assemble_remaining_meal)."""
    return [
        (None, MacroTargets(calories=2200, protein_g=160)),
        (None, MacroTargets(calories=1800, protein_g=120)),
        (None, MacroTargets(calories=2500, protein_g=180)),
        (1, MacroTargets(calories=780, protein_g=52)),
    ]


def _run_bucket(pool: list[Recipe], targets: list[tuple[int | None, MacroTargets]]) -> dict[str, float]:
    feasible_kcal_errors: list[float] = []
    feasible_protein_errors: list[float] = []
    hits = 0
    for meals, target in targets:
        if meals is None:
            plan = assemble_day_plan(pool, target, max_per_recipe=MAX_PER_RECIPE)
        else:
            plan = assemble_plan(pool, target, meals, max_per_recipe=MAX_PER_RECIPE)
        if plan.within_tolerance:
            hits += 1
            feasible_kcal_errors.append(plan.calories_relative_error)
            feasible_protein_errors.append(plan.protein_relative_error)

    feasibility_rate = hits / len(targets) if targets else 0.0
    return {
        "n": len(targets),
        "feasibility_rate": feasibility_rate,
        "median_kcal_relative_error_feasible": (
            statistics.median(feasible_kcal_errors) if feasible_kcal_errors else float("nan")
        ),
        "median_protein_relative_error_feasible": (
            statistics.median(feasible_protein_errors) if feasible_protein_errors else float("nan")
        ),
    }


def main() -> None:
    print(__doc__)
    pool = _trusted_pool()
    print(f"Trusted pool size (fully-GROUNDED, flag-free recipes): {len(pool)}")
    if not pool:
        print("Trusted pool is empty -- nothing to evaluate.")
        return

    rng = random.Random(EVAL_SEED)

    print("\n=== Bucket 1: planted-feasible (correctness proof) ===")
    planted = planted_feasible_targets(pool, rng)
    if not planted:
        print("No valid K=2..4 combos exist at the current pool size/cap -- skipped.")
    else:
        report = _run_bucket(pool, planted)
        for key, value in report.items():
            print(f"  {key}: {value}")

    print("\n=== Bucket 2: realistic-round (honest real-world numbers) ===")
    realistic = realistic_round_targets()
    report = _run_bucket(pool, realistic)
    for key, value in report.items():
        print(f"  {key}: {value}")

    print(
        "\nThis is a quality eval, not a safety gate -- never wire this "
        "script into scripts/run_safety_benchmark.py. It measures how "
        "close assemble_plan/assemble_day_plan get to a macro target given "
        "the CURRENT trusted (fully-GROUNDED, flag-free) recipe pool; it "
        "has no allergy/diet awareness and proves nothing about safety."
    )


if __name__ == "__main__":
    main()
