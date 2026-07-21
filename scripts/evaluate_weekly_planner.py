"""scripts/evaluate_weekly_planner.py -- quality eval for the full weekly
meal-plan solver (roadmap Phase 4 item 2, app.services.weekly_planner).

THIS IS A QUALITY EVAL, NOT A SAFETY GATE. It measures how well
app.services.weekly_planner assembles a week of macro-targeted day-plans out
of the CURRENT trusted (fully-GROUNDED, flag-free) recipe pool. It has no
allergy/diet awareness and proves nothing about safety -- it must NEVER be
wired into scripts/run_safety_benchmark.py, whose adjudicated-true
`inherent` violation rate is the actual release gate (see CLAUDE.md "Honest
scope").

`app.services.weekly_planner.assemble_week` is a THIN COMPOSITION of B3
(`app.services.day_planner.assemble_day_plan`, called `days` times, same
target every time -- see that module's own docstring) plus a reported-only
pantry-utilization metric; it is not a new solver, so this eval mostly
re-proves B3's own correctness at the week level, then reports the honest,
documented "all days identical" limitation explicitly rather than hiding it.

PRE-REGISTERED (fixed before this script was ever run -- do not tune
anything below after seeing a result):
  - Tolerance: +/-10% kcal AND +/-15% protein
    (`app.services.day_planner.DEFAULT_TOLERANCE`, reused verbatim by
    `app.services.weekly_planner` -- unchanged here).
  - Random seed: EVAL_SEED below (reserved for reproducibility bookkeeping
    only; bucket 1 deterministically sweeps every trusted recipe, no
    sampling needed at today's ~15-recipe pool size -- mirrors
    `scripts/evaluate_batch_planner.py`'s own bucket-1 approach).
  - Days per week: EVAL_DAYS = 7 (the roadmap's canonical week length).
  - Bucket 1 ("planted-feasible", a correctness proof): for EVERY trusted
    recipe, its OWN per-serving macros become the DAILY target, assembled
    with `meals_range=(1,)` so the target is reachable at exactly K=1
    serving/day (the day-planner's "remaining macros" mode -- see
    `app.services.day_planner.assemble_remaining_meal`) -- by construction
    every day of every week must come back `within_tolerance=True`.
    Expected result: ~100% feasibility, both at the week level (every day
    of a given recipe's week hits) and the day level (every day across
    every recipe's week hits).
  - Bucket 2 ("realistic-round", honest real-world numbers): reuses B3's
    own realistic-round daily targets for direct comparability (2200
    kcal/160 g protein, 1800/120, 2500/180 -- see
    `scripts/evaluate_day_planner.py`'s own bucket 2), assembled with
    `meals_range=app.services.day_planner.DEFAULT_MEALS_RANGE` (2,3,4 --
    "day plan" mode, the default `assemble_week` uses). Since every day of
    the week calls the exact same B3 primitive with the exact same target
    against the exact same trusted pool, results are expected to be
    IDENTICAL to `scripts/evaluate_day_planner.py`'s own day-level bucket 2
    numbers (same tolerance, same targets, same pool) -- reported
    honestly, not tuned to look better. `pantry_utilization` is reported
    here for VISIBILITY ONLY, never as a gating/feasibility criterion (see
    `app.services.weekly_planner`'s module docstring for why); with no
    inventory supplied it is 0.0 by definition, which is the expected,
    non-fabricated value for an empty pantry, not a bug.

  Because recipe selection is deterministic and pantry-independent (see
  `app.services.weekly_planner`'s own module docstring, "THE HONEST
  LIMITATION"), EVERY day within a single assembled week is expected to
  come back structurally identical in this eval -- reported explicitly
  below as `all_days_identical`, never hidden.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas.day_plan import DayPlan  # noqa: E402
from app.rag.loaders import load_corpus  # noqa: E402
from app.schemas.recipe import Recipe  # noqa: E402
from app.schemas.user import MacroTargets  # noqa: E402
from app.services.day_planner import DEFAULT_MEALS_RANGE, DEFAULT_TOLERANCE  # noqa: E402
from app.services.nutrition_view import trusted_per_serving  # noqa: E402
from app.services.weekly_planner import assemble_week  # noqa: E402

EVAL_SEED = 20260721  # fixed, pre-registered -- reserved for reproducibility bookkeeping
EVAL_DAYS = 7  # the roadmap's canonical week length


def _trusted_pool() -> list[Recipe]:
    """The exact same trust boundary app.services.weekly_planner /
    app.services.day_planner use internally
    (app.services.nutrition_view.trusted_per_serving) -- reimplemented at
    the top level here only so this script can print the pool size and
    build planted targets from it; assembly itself always goes through
    assemble_week's own (re-applied) filtering."""
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


def _days_identical(days: list[DayPlan]) -> bool:
    if not days:
        return True
    first = days[0].items
    return all(day.items == first for day in days[1:])


def _run_planted_bucket(pool: list[Recipe]) -> dict[str, float]:
    week_hits = 0
    days_total = 0
    days_hit = 0
    for recipe in pool:
        macros = trusted_per_serving(recipe)
        assert macros is not None  # pool is pre-filtered trusted
        target = MacroTargets(calories=round(macros.calories), protein_g=round(macros.protein_g, 4))
        plan = assemble_week(pool, target, days=EVAL_DAYS, meals_range=(1,))
        days_total += len(plan.days)
        days_hit += sum(1 for day in plan.days if day.within_tolerance)
        if plan.days and all(day.within_tolerance for day in plan.days):
            week_hits += 1

    n = len(pool)
    return {
        "n_recipes": n,
        "days_per_week": EVAL_DAYS,
        "week_feasibility_rate": week_hits / n if n else 0.0,
        "day_feasibility_rate": days_hit / days_total if days_total else 0.0,
    }


def realistic_round_targets() -> list[MacroTargets]:
    return [
        MacroTargets(calories=2200, protein_g=160),
        MacroTargets(calories=1800, protein_g=120),
        MacroTargets(calories=2500, protein_g=180),
    ]


def _run_realistic_bucket(pool: list[Recipe], targets: list[MacroTargets]) -> dict[str, float]:
    hits = 0
    for target in targets:
        plan = assemble_week(pool, target, days=EVAL_DAYS, meals_range=DEFAULT_MEALS_RANGE)
        identical = _days_identical(plan.days)
        within = plan.days[0].within_tolerance if plan.days else False
        print(f"  target={target.calories} kcal / {target.protein_g} g protein:")
        print(f"    within_tolerance (every day, since all_days_identical): {within}")
        print(f"    all_days_identical: {identical}")
        print(
            "    pantry_utilization (visibility only, no inventory supplied "
            f"-> 0.0 by definition): {plan.pantry_utilization}"
        )
        print(f"    uncompared_ingredient_count: {plan.uncompared_ingredient_count}")
        print(f"    trusted_pool_size: {plan.trusted_pool_size}")
        if within:
            hits += 1

    n = len(targets)
    return {"n": n, "feasibility_rate": hits / n if n else 0.0}


def main() -> None:
    print(__doc__)
    pool = _trusted_pool()
    print(f"Trusted pool size (fully-GROUNDED, flag-free recipes): {len(pool)}")
    if not pool:
        print("Trusted pool is empty -- nothing to evaluate.")
        return

    print("\n=== Bucket 1: planted-feasible (correctness proof) ===")
    report = _run_planted_bucket(pool)
    for key, value in report.items():
        print(f"  {key}: {value}")

    print("\n=== Bucket 2: realistic-round (honest real-world numbers) ===")
    realistic = realistic_round_targets()
    report2 = _run_realistic_bucket(pool, realistic)
    print("  --- bucket 2 aggregate ---")
    for key, value in report2.items():
        print(f"  {key}: {value}")

    print(
        "\nThis is a quality eval, not a safety gate -- never wire this "
        "script into scripts/run_safety_benchmark.py. It measures how "
        "close app.services.weekly_planner.assemble_week gets to a daily "
        "macro target, repeated across a week, given the CURRENT trusted "
        "(fully-GROUNDED, flag-free) recipe pool; it has no allergy/diet "
        "awareness and proves nothing about safety. pantry_utilization is "
        "informational only and is never used to select, gate, or rank "
        "recipes."
    )


if __name__ == "__main__":
    main()
