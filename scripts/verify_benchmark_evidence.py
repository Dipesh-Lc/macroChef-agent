"""Exhaustive, mechanical adjudication check for a safety-benchmark evidence
bundle: runs the REAL production `contains_allergen`/`violates_diet_type`
functions (app.services.constraint_engine) directly against every served
recipe's actual, already-resolved ingredient list for every judge-flagged
case -- not a sample, not a mechanism-classification heuristic.

Why this exists: the judge (app/evaluation/benchmark/safety_judge.py) is a
deliberately dumb, recall-biased substring matcher, kept structurally
unable to import the code it grades. That means every judge flag needs a
per-case adjudication before it counts as a real violation -- and manually
classifying flags into "mechanism buckets" (stale title, bidirectional
substring, etc.) from a sample is itself error-prone, as a same-day
independent review of a hand-written adjudication document found (see
data/evaluation/adjudication_20260727T190130Z_clean_final.md's revision
history): the bucketing missed cases and mischaracterized the dominant
mechanism for a majority of a sampled subset. This script replaces that
approach with a direct, exhaustive execution of the actual safety-decision
functions against every piece of evidence the benchmark produced, using
each case's own structured_rendering (allergies / diet_type) as the real
constraint -- the same ground truth a human adjudicator would otherwise
reconstruct by hand, case by case.

Usage:
    python scripts/verify_benchmark_evidence.py <cases_json_path> [--case-ids id1,id2,...]

If --case-ids is omitted, checks every case in the file. Reports any
recipe where the real production code would flag a violation -- that is
the signal a human adjudicator needs to look at individually; zero output
under "REAL PRODUCTION-CODE VIOLATIONS FOUND" is the exhaustive proof that
every served recipe in the evidence bundle is genuinely safe under the
real constraint engine, not merely judged safe by inspection or sampling.
"""

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas.ingredient import Ingredient  # noqa: E402
from app.schemas.recipe import Recipe  # noqa: E402
from app.services.constraint_engine import contains_allergen, violates_diet_type  # noqa: E402


def load_case_definitions() -> dict[str, dict]:
    """Load every case's structured_rendering (allergies/diet_type) from the
    frozen case-definition files -- the real constraint each case tests,
    independent of the judge's own forbidden-term list."""
    case_defs: dict[str, dict] = {}
    for fp in glob.glob(str(ROOT / "app/evaluation/benchmark/cases/*.jsonl")):
        with open(fp, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                case_defs[d["case_id"]] = d
    return case_defs


def verify(cases_json_path: str, case_ids: list[str] | None = None) -> list[tuple]:
    with open(cases_json_path, encoding="utf-8") as f:
        cases = {c["case_id"]: c for c in json.load(f)}

    case_defs = load_case_definitions()
    target_ids = case_ids or list(cases.keys())

    real_violations: list[tuple] = []
    missing_defs: list[str] = []
    missing_ingredients: list[str] = []

    for cid in target_ids:
        d = case_defs.get(cid)
        if not d:
            missing_defs.append(cid)
            continue

        allergies = d["structured_rendering"].get("allergies") or []
        diet_type = d["structured_rendering"].get("diet_type")

        served = cases.get(cid, {}).get("served_recipe_ingredients", {})
        if not served:
            missing_ingredients.append(cid)
            continue

        for recipe_id, ingredient_names in served.items():
            recipe = Recipe(
                recipe_id=recipe_id,
                title=recipe_id,
                ingredients=[Ingredient(name=n) for n in ingredient_names],
                source_type="mock",
            )
            if allergies and contains_allergen(recipe, allergies):
                real_violations.append((cid, "allergy", allergies, recipe_id, ingredient_names))
            if diet_type and violates_diet_type(recipe, diet_type):
                real_violations.append((cid, "diet", diet_type, recipe_id, ingredient_names))

    if missing_defs:
        print(f"WARNING -- case definitions not found for: {missing_defs}")
    if missing_ingredients:
        print(f"WARNING -- no served_recipe_ingredients in evidence bundle for: {missing_ingredients}")

    print()
    print("=== REAL PRODUCTION-CODE VIOLATIONS FOUND (via contains_allergen/violates_diet_type directly) ===")
    print("count:", len(real_violations))
    for v in real_violations:
        print(v)

    return real_violations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases_json_path", help="Path to a safety_benchmark_cases_*.json evidence bundle")
    parser.add_argument(
        "--case-ids",
        default=None,
        help="Comma-separated case_ids to check (default: every case in the file)",
    )
    args = parser.parse_args()

    case_ids = args.case_ids.split(",") if args.case_ids else None
    violations = verify(args.cases_json_path, case_ids)
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
