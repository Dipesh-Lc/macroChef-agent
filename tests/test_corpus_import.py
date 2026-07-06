import json
import logging
from pathlib import Path

from app.schemas.recipe import Recipe
from app.services import recipe_indexing_service
from app.services.constraint_engine import derive_allergen_labels
from app.services.corpus_import.adapters import (
    FoodComAdapter,
    _clean_instructions,
    _parse_r_vector,
    _strip_leading_number_prefix,
)
from app.services.corpus_import.pipeline import CorpusImportPipeline
from app.services.recipe_indexing_service import RecipeIndexingService

FIXTURE = Path(__file__).parent / "fixtures" / "corpus_sample.csv"

# Fixture (tests/fixtures/corpus_sample.csv) has 6 rows, deliberately covering:
#   1001 Chicken Rice Bowl   -- valid
#   1002 Peanut Noodles      -- valid
#   1003 (blank Name)        -- rejected by the adapter itself (no title)
#   1004 Quick Snack         -- only 1 instruction step, fails RecipeValidationService (min 2)
#   1005 Chicken Rice Bowl   -- exact-title duplicate of 1001
#   1006 Shrimp Salad        -- valid, but one RecipeIngredientParts entry is
#                               blank -> Recipe._drop_empty_ingredients drops
#                               it, exercising the empty-ingredient tally.


def _run(tmp_path: Path, *, limit: int | None = None):
    pipeline = CorpusImportPipeline(FoodComAdapter())
    output_path = tmp_path / "imported_recipes.jsonl"
    # existing_recipes=[] isolates the test from the real 25-recipe seed
    # corpus -- dedup must only see what this test constructs.
    report = pipeline.run(FIXTURE, output_path, limit=limit, existing_recipes=[])
    return report, output_path


def test_pipeline_survivor_counts_match_fixture(tmp_path: Path) -> None:
    report, output_path = _run(tmp_path)

    assert report.read == 6
    assert report.rejected_by_adapter == 1  # 1003, blank title
    assert report.failed_validation == 1  # 1004, too few instructions
    assert report.duplicates == 1  # 1005, duplicate of 1001
    assert report.survivors == 3  # 1001, 1002, 1006
    assert report.empty_ingredients_dropped == 1  # 1006's blank ingredient entry
    assert report.recipes_with_empty_ingredients == 1

    written = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert len(written) == 3
    titles = {row["title"] for row in written}
    assert titles == {"Chicken Rice Bowl", "Peanut Noodles", "Shrimp Salad"}

    shrimp = next(row for row in written if row["title"] == "Shrimp Salad")
    assert len(shrimp["ingredients"]) == 3  # 4 raw entries minus the dropped blank one
    assert "shellfish" in shrimp["allergens"]

    peanut_noodles = next(row for row in written if row["title"] == "Peanut Noodles")
    assert "peanut" in peanut_noodles["allergens"]
    assert "soy" in peanut_noodles["allergens"]


def test_recipe_ids_are_deterministic_across_runs(tmp_path: Path) -> None:
    report_a, output_a = _run(tmp_path / "run_a")
    report_b, output_b = _run(tmp_path / "run_b")

    ids_a = sorted(json.loads(line)["recipe_id"] for line in output_a.read_text().splitlines())
    ids_b = sorted(json.loads(line)["recipe_id"] for line in output_b.read_text().splitlines())
    assert ids_a == ids_b
    assert report_a.survivors == report_b.survivors == 3


def test_idempotent_rerun_produces_identical_file(tmp_path: Path) -> None:
    _, output_path = _run(tmp_path)
    first = output_path.read_text(encoding="utf-8")

    _, output_path_again = _run(tmp_path)  # same tmp_path -> overwrites the same file
    second = output_path_again.read_text(encoding="utf-8")

    assert first == second


def test_rebuild_index_clean_drops_stale_vectors(monkeypatch) -> None:
    """A re-import with a smaller/corrected corpus must not leave orphaned
    embeddings behind -- rebuild_index_clean drops and recreates the
    collection instead of relying on upsert (which never prunes)."""

    class FakeCollection:
        def __init__(self):
            self.ids: set[str] = set()

        def upsert(self, ids, documents, metadatas):
            self.ids.update(ids)

    store = {"collection": FakeCollection()}

    def fake_get_collection():
        return store["collection"]

    def fake_reset_collection():
        store["collection"] = FakeCollection()
        return store["collection"]

    monkeypatch.setattr(recipe_indexing_service, "get_chroma_collection", fake_get_collection)
    monkeypatch.setattr(recipe_indexing_service, "reset_chroma_collection", fake_reset_collection)

    recipe_a = Recipe(recipe_id="imp_a", title="Recipe A", ingredients=["rice"], instructions=["Cook."])
    recipe_b = Recipe(recipe_id="imp_b", title="Recipe B", ingredients=["beans"], instructions=["Cook."])

    monkeypatch.setattr(recipe_indexing_service, "load_corpus", lambda: [recipe_a, recipe_b])
    service = RecipeIndexingService()
    service.rebuild_index_clean(include_base=True, include_user=False)
    assert store["collection"].ids == {"imp_a", "imp_b"}

    # Re-import with recipe_b dropped from the source (e.g. it failed a later
    # validation pass, or the corrected dataset no longer contains it).
    monkeypatch.setattr(recipe_indexing_service, "load_corpus", lambda: [recipe_a])
    service.rebuild_index_clean(include_base=True, include_user=False)
    assert store["collection"].ids == {"imp_a"}
    assert "imp_b" not in store["collection"].ids


def test_derive_allergen_labels_from_ingredient_names() -> None:
    assert "dairy" in derive_allergen_labels(["cheddar", "spinach"])
    assert "shellfish" in derive_allergen_labels(["shrimp", "lettuce", "lemon"])
    assert derive_allergen_labels(["rice", "water"]) == []


def test_strip_leading_number_prefix() -> None:
    assert _strip_leading_number_prefix("2. Place apples in a baking dish.") == (
        "Place apples in a baking dish."
    )
    assert _strip_leading_number_prefix("Cook chicken.") == "Cook chicken."


def test_clean_instructions_drops_first_person_narrative_steps() -> None:
    # Styled on real samples pulled from the Food.com dataset during the
    # license/provenance review: functional steps survive, first-person
    # narrative asides are dropped, redundant leading numerals stripped.
    # Note "PATIENCE is the name of the game." deliberately survives here: it's
    # stylistic/narrative but has no first-person pronoun, an honest, disclosed
    # limitation of this heuristic (it's a strong signal, not perfect detection).
    steps = [
        "Peel and slice apples.",
        "2. Place apples in a 9 x 13 inch baking dish.",
        "I don't actually use teaspoons for this; I just lift a mound of dough.",
        "Bake at 350 for 45 minutes.",
        "PATIENCE is the name of the game.",
        "Once the gnocchi was almost cooked I added it to the main pan.",
    ]
    cleaned, dropped = _clean_instructions(steps)

    assert cleaned == [
        "Peel and slice apples.",
        "Place apples in a 9 x 13 inch baking dish.",
        "Bake at 350 for 45 minutes.",
        "PATIENCE is the name of the game.",
    ]
    assert dropped == 2


def test_clean_instructions_leaves_pure_functional_steps_untouched() -> None:
    steps = ["Cook pasta in boiling water.", "Drain and toss with sauce.", "Serve immediately."]
    cleaned, dropped = _clean_instructions(steps)
    assert cleaned == steps
    assert dropped == 0


def test_parse_r_vector_multi_item() -> None:
    assert _parse_r_vector('c("a", "b", "c")') == ["a", "b", "c"]


def test_parse_r_vector_handles_bare_singleton_string() -> None:
    # R's serialization omits the c(...) wrapper for length-1 vectors -- a
    # single-step recipe's RecipeInstructions cell is a bare quoted string,
    # not c("..."). Found via a real dataset sample during the drop-rate
    # diagnostic: without this case, the surrounding quote marks were left in
    # as literal content (e.g. '"Toast and grind..."' instead of 'Toast and
    # grind...').
    assert _parse_r_vector('"Toast and grind cumin and fennel seeds."') == [
        "Toast and grind cumin and fennel seeds."
    ]


def _raw_row(**overrides) -> dict:
    row = {
        "Name": "Test Recipe",
        "CookTime": "PT10M",
        "RecipeServings": "2",
        "RecipeCategory": "dinner",
        "RecipeIngredientParts": 'c("chicken", "rice", "salt")',
        "RecipeIngredientQuantities": 'c("1", "2", "1")',
        "RecipeInstructions": 'c("Cook chicken.", "Cook rice.")',
        "Calories": "400",
        "ProteinContent": "30",
        "CarbohydrateContent": "30",
        "FatContent": "10",
        "FiberContent": "2",
        "RecipeId": "9001",
    }
    row.update(overrides)
    return row


def test_rejection_attributed_to_cleaning_only_when_cleaning_caused_it() -> None:
    adapter = FoodComAdapter()

    # Case 1: 2 raw steps, one is narrative -> cleaning pushes it below 2.
    # This IS attributable to cleaning.
    adapter.to_candidate(
        _raw_row(
            Name="Cleaning Caused It",
            RecipeInstructions='c("Cook chicken.", "I like to add extra salt here.")',
        )
    )
    # Case 2: only 1 raw step to begin with -- always going to fail the
    # 2-instruction minimum, nothing to do with cleaning.
    adapter.to_candidate(
        _raw_row(Name="Always Too Short", RecipeInstructions='"Cook everything."')
    )
    # Case 3: 2 raw steps, both functional -> both survive, no rejection at all.
    adapter.to_candidate(_raw_row(Name="Fine"))

    assert adapter.recipes_below_min_instructions_after_cleaning == 2
    assert adapter.recipes_rejected_because_of_cleaning == 1
    assert [example["title"] for example in adapter.example_dropped_below_min] == [
        "Cleaning Caused It"
    ]


def test_empty_ingredient_tally_logged_at_info(tmp_path: Path, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="app.services.corpus_import.pipeline"):
        _run(tmp_path)

    assert any(
        "dropped 1 empty ingredients across 1 recipes" in record.getMessage()
        for record in caplog.records
    )
