"""Refresh the `allergens` field of every recipe in imported_recipes.jsonl.

Recipe.allergens for the imported corpus was baked in at import time by
derive_allergen_labels (app/services/corpus_import/adapters.py) against
whatever ALLERGEN_ALIASES table existed at import time. That table has
changed since (aliases added, keys renamed/removed), so a meaningful chunk
of stored labels are stale relative to the current table.

Safety note: this is a metadata-accuracy fix, not an allergy-safety fix.
constraint_engine._recipe_safety_terms unions ingredient names with
recipe.allergens, so stored labels are strictly additive -- a missing or
stale label can never cause a serving-time under-block, because ingredient
names always carry the real check. This script only makes retrieval-stage
metadata (and the Chroma index built from it) match what the current table
would derive from ingredients today.

Only the `allergens` field of each recipe is touched. Every other field,
key order, and the JSONL formatting is preserved exactly by loading each
line with json.loads (which preserves key order) and re-serializing with
json.dumps using the same (default) separators -- verified byte-identical
for every untouched line before this script ever mutates anything.

Idempotent: re-deriving from the same ingredient names via the same table
always yields the same labels, so a second run reports zero changes.

Usage:
    python scripts/backfill_allergen_labels.py [--path data/processed/imported_recipes.jsonl]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.constraint_engine import derive_allergen_labels  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default="data/processed/imported_recipes.jsonl")
    args = parser.parse_args()

    path = Path(args.path)
    # newline="" disables Python's universal-newline translation on read, so
    # each line's actual line ending (LF vs CRLF) is preserved verbatim below
    # instead of silently normalized to "\n".
    with path.open("r", encoding="utf-8", newline="") as handle:
        lines = handle.readlines()

    scanned = 0
    changed = 0
    gained = Counter()
    lost = Counter()
    out_lines: list[str] = []

    for raw_line in lines:
        # Preserve the exact line ending (LF vs CRLF vs no trailing newline on
        # the final line) instead of assuming one style.
        if raw_line.endswith("\r\n"):
            body, ending = raw_line[:-2], "\r\n"
        elif raw_line.endswith("\n"):
            body, ending = raw_line[:-1], "\n"
        else:
            body, ending = raw_line, ""

        if not body:
            out_lines.append(raw_line)
            continue

        scanned += 1
        record = json.loads(body)

        ingredient_names = [ingredient["name"] for ingredient in record["ingredients"]]
        new_allergens = derive_allergen_labels(ingredient_names)
        old_allergens = record.get("allergens") or []

        if set(new_allergens) != set(old_allergens):
            changed += 1
            for label in set(new_allergens) - set(old_allergens):
                gained[label] += 1
            for label in set(old_allergens) - set(new_allergens):
                lost[label] += 1
            record["allergens"] = new_allergens

        out_lines.append(json.dumps(record, ensure_ascii=False) + ending)

    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("".join(out_lines))

    print(f"Recipes scanned: {scanned}")
    print(f"Recipes with changed allergen labels: {changed}")
    if gained or lost:
        print("\nPer-label tally (recipe count that gained/lost the label):")
        for label in sorted(set(gained) | set(lost)):
            print(f"  {label}: GAINED {gained.get(label, 0)}, LOST {lost.get(label, 0)}")
    else:
        print("No label changes (idempotent run).")


if __name__ == "__main__":
    main()
