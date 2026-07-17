"""Title/ingredient integrity audit: does a recipe's OWN TITLE name a food
that never shows up anywhere in its ingredient list or its derived
`allergens` field?

All detection logic lives in
`app.services.corpus_import.title_ingredient_integrity` (shared with the
import-time check in `CorpusImportPipeline` and with
`scripts/quarantine_flagged_recipes.py`) -- see that module's docstring for
the full root-cause explanation and the false-positive-handling design.
This script is a thin CLI: load a corpus file, run the check over every
recipe, print a report grouped by allergen category, and exit nonzero if
anything is flagged.

Usage: python scripts/audit_title_ingredient_integrity.py [path/to/imported_recipes.jsonl]
Exits nonzero if any recipe is flagged, so this can be wired into CI
directly as a release gate (same idiom as audit_diet_leaks.py:159).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.recipe import Recipe  # noqa: E402
from app.services.corpus_import.title_ingredient_integrity import (  # noqa: E402
    Mismatch,
    find_title_ingredient_mismatches,
)

DEFAULT_CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "imported_recipes.jsonl"


@dataclass
class AuditResult:
    corpus_size: int
    mismatches: list[Mismatch] = field(default_factory=list)

    def by_category(self) -> dict[str, list[Mismatch]]:
        grouped: dict[str, list[Mismatch]] = {}
        for mismatch in self.mismatches:
            grouped.setdefault(mismatch.category, []).append(mismatch)
        return grouped

    def flagged_recipe_ids(self) -> set[str]:
        return {mismatch.recipe_id for mismatch in self.mismatches}


def _load_corpus(path: Path) -> list[Recipe]:
    recipes = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            recipes.append(Recipe.model_validate(json.loads(line)))
    return recipes


def audit(corpus: list[Recipe]) -> AuditResult:
    result = AuditResult(corpus_size=len(corpus))
    for recipe in corpus:
        result.mismatches.extend(find_title_ingredient_mismatches(recipe))
    return result


def render_report(result: AuditResult) -> str:
    lines = [
        f"Loaded {result.corpus_size} recipes.",
        (
            f"Flagged recipes (title names an allergen absent from ingredients AND "
            f"allergens): {len(result.flagged_recipe_ids())}"
            f" ({len(result.flagged_recipe_ids()) / result.corpus_size:.2%} of corpus)"
            if result.corpus_size
            else "Empty corpus."
        ),
        f"Total title/allergen mismatch pairs: {len(result.mismatches)}",
        "",
    ]
    for category, mismatches in sorted(result.by_category().items(), key=lambda kv: -len(kv[1])):
        lines.append(f"=== {category} ({len(mismatches)}) ===")
        for mismatch in mismatches[:20]:
            lines.append(f"  - {mismatch.title!r} ({mismatch.recipe_id}) -- title term(s): {mismatch.title_terms}")
        if len(mismatches) > 20:
            lines.append(f"  ... and {len(mismatches) - 20} more")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    corpus_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CORPUS_PATH
    corpus = _load_corpus(corpus_path)

    result = audit(corpus)
    print(render_report(result))

    return 1 if result.mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
