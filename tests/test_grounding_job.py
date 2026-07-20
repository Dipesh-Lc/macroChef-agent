import json
from pathlib import Path

import pytest
import requests

from app.config import Settings
from app.schemas.ingredient import Ingredient
from app.schemas.nutrition import FoodMacros, FoodMatch, GroundingStatus, RecipeNutrition
from app.schemas.recipe import Recipe
from app.services.grounding_job import (
    DEMOTING_FLAG_IMPLAUSIBLE_KCAL,
    IMPLAUSIBLE_MAX_KCAL_PER_SERVING,
    RATIO_OUTLIER_MAX,
    RAW_COOKED_BLOWUP_RATIO,
    build_report,
    compute_seed_macro_accuracy,
    render_report,
    run_grounding,
)
from app.services.nutrition_cache import FdcCache
from app.services.usda_client import UsdaClient


def _match(name: str, *, calories: float, protein_g=0.0, carbs_g=0.0, fat_g=0.0, fiber_g=0.0) -> FoodMatch:
    return FoodMatch(
        fdc_id=1,
        description=name,
        data_type="SR Legacy",
        macros=FoodMacros(calories=calories, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g, fiber_g=fiber_g),
        query=name,
    )


class FakeUsdaClient:
    """Deliberately dumb: returns a fixed match per name regardless of
    `preparation` -- gating itself is covered in test_usda_client.py. This
    suite only exercises grounding_job's aggregation/report math given
    whatever `compute_recipe_macros` produces."""

    def __init__(self, matches: dict[str, FoodMatch | None]):
        self._matches = matches

    def search_food(self, name: str, *, preparation: str | None = None) -> FoodMatch | None:
        return self._matches.get(name)


def _recipe(recipe_id, title, ingredients, calories, servings=1) -> Recipe:
    return Recipe(
        recipe_id=recipe_id,
        title=title,
        ingredients=ingredients,
        instructions=["Cook."],
        calories=calories,
        servings=servings,
    )


def test_plausible_grounded_recipe_has_no_flags(tmp_path) -> None:
    recipe = _recipe(
        "r_1", "Chicken Bowl",
        [Ingredient(name="chicken breast", amount=200, unit="g")],
        calories=330,
    )
    client = FakeUsdaClient({"chicken breast": _match("chicken breast", calories=165, protein_g=31)})

    report = run_grounding(
        client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=[recipe], seeds=[recipe]
    )

    row = report.seed_rows[0]
    assert row.status.value == "grounded"
    assert row.computed_kcal == 330
    assert row.tag_kcal == 330
    assert row.ratio == 1.0
    assert row.raw_cooked_blowup is False
    assert row.implausible_band is False


def test_fully_ungrounded_recipe_skips_flags_but_reports_status(tmp_path) -> None:
    recipe = _recipe(
        "r_2", "Mystery Dish",
        [Ingredient(name="mystery sauce", amount=50, unit="g")],
        calories=200,
    )
    client = FakeUsdaClient({"mystery sauce": None})

    report = run_grounding(
        client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=[recipe], seeds=[recipe]
    )

    row = report.seed_rows[0]
    assert row.status.value == "ungrounded"
    assert row.raw_cooked_blowup is False
    assert row.implausible_band is False
    assert report.status_counts == {"ungrounded": 1}
    assert row.ingredients[0].detail == "ungrounded: no USDA match"


def test_raw_cooked_blowup_flag_triggers_independently_of_the_usda_gate(tmp_path) -> None:
    # Simulates the failure mode the gate exists to prevent: a "cooked"
    # declaration ends up matched against a raw-magnitude value anyway.
    # grounding_job doesn't know *why* -- it just flags the resulting ratio.
    recipe = _recipe(
        "r_3", "Rice Bowl",
        [Ingredient(name="brown rice", amount=200, unit="g", preparation="cooked")],
        calories=300,
    )
    client = FakeUsdaClient({"brown rice": _match("brown rice", calories=370)})  # raw-magnitude

    report = run_grounding(
        client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=[recipe], seeds=[recipe]
    )

    row = report.seed_rows[0]
    assert row.computed_kcal == 740
    assert row.ratio == 740 / 300
    assert row.ratio > RAW_COOKED_BLOWUP_RATIO
    assert row.has_declared_preparation is True
    assert row.raw_cooked_blowup is True
    assert row in report.raw_cooked_blowup_flags()


def test_blowup_flag_never_fires_without_a_declared_preparation(tmp_path) -> None:
    # Same >1.6x ratio, but no ingredient declares a preparation -- this is
    # generic self-report drift, not a raw/cooked-scale mismatch signature.
    recipe = _recipe(
        "r_4", "Generic Dish",
        [Ingredient(name="cheese", amount=300, unit="g")],
        calories=300,
    )
    client = FakeUsdaClient({"cheese": _match("cheese", calories=350)})  # 1050 kcal computed

    report = run_grounding(
        client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=[recipe], seeds=[recipe]
    )

    row = report.seed_rows[0]
    assert row.ratio > RAW_COOKED_BLOWUP_RATIO
    assert row.has_declared_preparation is False
    assert row.raw_cooked_blowup is False


def test_implausible_band_flag_triggers_on_absolute_kcal_per_serving(tmp_path) -> None:
    recipe = _recipe(
        "r_5", "Absurd Dish",
        [Ingredient(name="oil", amount=1000, unit="g")],
        calories=500,
    )
    client = FakeUsdaClient({"oil": _match("oil", calories=884)})  # 8840 kcal, well above the band

    report = run_grounding(
        client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=[recipe], seeds=[recipe]
    )

    row = report.seed_rows[0]
    assert row.computed_kcal > IMPLAUSIBLE_MAX_KCAL_PER_SERVING
    assert row.implausible_band is True
    assert row in report.implausible_band_flags()


def test_partial_grounding_reports_undercounted_computed_kcal(tmp_path) -> None:
    recipe = _recipe(
        "r_6", "Partial Dish",
        [
            Ingredient(name="chicken breast", amount=200, unit="g"),
            Ingredient(name="mystery sauce", amount=50, unit="g"),
        ],
        calories=400,
    )
    client = FakeUsdaClient(
        {"chicken breast": _match("chicken breast", calories=165, protein_g=31), "mystery sauce": None}
    )

    report = run_grounding(
        client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=[recipe], seeds=[recipe]
    )

    row = report.seed_rows[0]
    assert row.status.value == "partial"
    assert row.computed_kcal == 330  # only the grounded ingredient counted
    assert row.ingredients[1].grounded is False
    assert row.ingredients[1].detail == "ungrounded: no USDA match"


def test_sidecar_write_is_idempotent_across_reruns(tmp_path) -> None:
    recipe = _recipe(
        "r_7", "Chicken Bowl",
        [Ingredient(name="chicken breast", amount=200, unit="g")],
        calories=330,
    )
    client = FakeUsdaClient({"chicken breast": _match("chicken breast", calories=165, protein_g=31)})
    sidecar_path = tmp_path / "grounding.jsonl"

    run_grounding(client=client, sidecar_path=sidecar_path, corpus=[recipe], seeds=[recipe])
    first_bytes = sidecar_path.read_bytes()

    run_grounding(client=client, sidecar_path=sidecar_path, corpus=[recipe], seeds=[recipe])
    second_bytes = sidecar_path.read_bytes()

    assert first_bytes == second_bytes
    lines = [json.loads(line) for line in first_bytes.decode("utf-8").splitlines()]
    assert len(lines) == 1
    assert lines[0]["recipe_id"] == "r_7"
    assert lines[0]["nutrition"]["status"] == "grounded"


class _FlakyThenFixedSession:
    """Fails the first `fail_times` calls per unique query (raising, like the
    live FDC 400 flake), then serves `payload` for every call after."""

    def __init__(self, payload: dict, fail_times: int):
        self.payload = payload
        self.fail_times = fail_times
        self._calls_per_query: dict[str, int] = {}
        self.total_calls = 0

    def get(self, url, params=None, timeout=None):
        self.total_calls += 1
        query = params["query"]
        seen = self._calls_per_query.get(query, 0)
        self._calls_per_query[query] = seen + 1
        if seen < self.fail_times:
            raise requests.HTTPError("400 Client Error: Bad Request")

        response_payload = self.payload

        class _Response:
            def raise_for_status(self_inner) -> None:
                pass

            def json(self_inner) -> dict:
                return response_payload

        return _Response()


def test_sidecar_is_reproducible_against_a_flaky_live_client(tmp_path) -> None:
    """The earlier fixed-response FakeUsdaClient proof (above) can't fail, so
    it never exercised whether a real, occasionally-flaky USDA client (see
    UsdaClient's retry/no-match-cache handling) produces the same report on
    every re-run. This drives run_grounding through the real UsdaClient with
    a session that fails transiently, and confirms the sidecar is identical
    across two full runs despite that flakiness."""

    recipe = _recipe(
        "r_10", "Chicken Bowl",
        [Ingredient(name="chicken breast", amount=200, unit="g")],
        calories=330,
    )
    payload = {
        "foods": [
            {
                "fdcId": 1,
                "description": "Chicken breast",
                "dataType": "SR Legacy",
                "foodNutrients": [
                    {"nutrientNumber": "208", "value": 165},
                    {"nutrientNumber": "203", "value": 31},
                    {"nutrientNumber": "204", "value": 3.57},
                    {"nutrientNumber": "205", "value": 0},
                ],
            }
        ]
    }
    settings = Settings(FDC_API_KEY="test-key", FDC_BASE_URL="https://api.nal.usda.gov/fdc/v1")
    cache_path = tmp_path / "fdc_cache.json"
    sidecar_path = tmp_path / "grounding.jsonl"

    # Run 1: the session fails twice per query before succeeding -- the
    # client's retry (max 3 attempts) must recover within this run.
    flaky_session = _FlakyThenFixedSession(payload=payload, fail_times=2)
    first_client = UsdaClient(
        settings=settings, session=flaky_session, cache=FdcCache(cache_path), sleep=lambda _: None
    )
    run_grounding(client=first_client, sidecar_path=sidecar_path, corpus=[recipe], seeds=[recipe])
    first_bytes = sidecar_path.read_bytes()

    # Run 2: an unreachable session -- if this run's result differs, it can
    # only be because it silently depended on the network again instead of
    # the confirmed match cached during run 1.
    class _Unreachable:
        def get(self, *args, **kwargs):
            raise AssertionError("run 2 must be served entirely from cache")

    second_client = UsdaClient(
        settings=settings, session=_Unreachable(), cache=FdcCache(cache_path), sleep=lambda _: None
    )
    run_grounding(client=second_client, sidecar_path=sidecar_path, corpus=[recipe], seeds=[recipe])
    second_bytes = sidecar_path.read_bytes()

    assert first_bytes == second_bytes
    lines = [json.loads(line) for line in first_bytes.decode("utf-8").splitlines()]
    assert lines[0]["nutrition"]["status"] == "grounded"
    assert lines[0]["nutrition"]["per_serving"]["calories"] == 330  # 165 kcal/100g * 200g


def test_ungrounded_ingredient_gets_a_fresh_attempt_next_run_not_stuck(tmp_path) -> None:
    """A transient failure that exhausts all retries must not be cached as a
    confirmed no-match -- otherwise an outage during one run would
    permanently undercount a recipe across all future runs."""

    recipe = _recipe(
        "r_11", "Chicken Bowl",
        [Ingredient(name="chicken breast", amount=200, unit="g")],
        calories=330,
    )
    payload = {
        "foods": [
            {
                "fdcId": 1,
                "description": "Chicken breast",
                "dataType": "SR Legacy",
                "foodNutrients": [
                    {"nutrientNumber": "208", "value": 165},
                    {"nutrientNumber": "203", "value": 31},
                    {"nutrientNumber": "204", "value": 3.57},
                    {"nutrientNumber": "205", "value": 0},
                ],
            }
        ]
    }
    settings = Settings(FDC_API_KEY="test-key", FDC_BASE_URL="https://api.nal.usda.gov/fdc/v1")
    cache_path = tmp_path / "fdc_cache.json"
    sidecar_path = tmp_path / "grounding.jsonl"

    # Run 1: every attempt fails -- retries exhaust, recipe stays ungrounded.
    always_fails = _FlakyThenFixedSession(payload=payload, fail_times=99)
    first_client = UsdaClient(
        settings=settings, session=always_fails, cache=FdcCache(cache_path), sleep=lambda _: None
    )
    first_report = run_grounding(client=first_client, sidecar_path=sidecar_path, corpus=[recipe], seeds=[recipe])
    assert first_report.seed_rows[0].status.value == "ungrounded"

    # Run 2: the outage has cleared -- this run must succeed, proving the
    # exhausted failure from run 1 was never cached as a permanent no-match.
    recovered = _FlakyThenFixedSession(payload=payload, fail_times=0)
    second_client = UsdaClient(
        settings=settings, session=recovered, cache=FdcCache(cache_path), sleep=lambda _: None
    )
    second_report = run_grounding(client=second_client, sidecar_path=sidecar_path, corpus=[recipe], seeds=[recipe])

    assert second_report.seed_rows[0].status.value == "grounded"


def test_run_grounding_flushes_cache_on_normal_completion(tmp_path) -> None:
    """A3 prep: `FdcCache.set_payload` batches disk writes and no longer
    writes on every call (see its module comment) -- `run_grounding` must
    flush at the end of an ordinary, exception-free run so a corpus small
    enough to never hit the 50-entry auto-flush threshold still ends up
    durably on disk."""
    recipe = _recipe(
        "r_20", "Chicken Bowl",
        [Ingredient(name="chicken breast", amount=200, unit="g")],
        calories=330,
    )
    payload = {
        "foods": [
            {
                "fdcId": 1,
                "description": "Chicken breast",
                "dataType": "SR Legacy",
                "foodNutrients": [
                    {"nutrientNumber": "208", "value": 165},
                    {"nutrientNumber": "203", "value": 31},
                    {"nutrientNumber": "204", "value": 3.57},
                    {"nutrientNumber": "205", "value": 0},
                ],
            }
        ]
    }
    settings = Settings(FDC_API_KEY="test-key", FDC_BASE_URL="https://api.nal.usda.gov/fdc/v1")
    cache_path = tmp_path / "fdc_cache.json"

    session = _FlakyThenFixedSession(payload=payload, fail_times=0)
    client = UsdaClient(
        settings=settings, session=session, cache=FdcCache(cache_path), sleep=lambda _: None
    )

    run_grounding(client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=[recipe], seeds=[recipe])

    # A single grounded ingredient is nowhere near the 50-entry auto-flush
    # threshold -- this only exists on disk because run_grounding's finally
    # block flushed it explicitly.
    assert cache_path.exists()
    reloaded = FdcCache(cache_path)
    assert reloaded.get_payload("chicken breast", ["Foundation", "SR Legacy", "Survey (FNDDS)"], 5) is not None


def test_run_grounding_flushes_cache_in_finally_even_on_unexpected_exception(tmp_path) -> None:
    """The finally block must flush on BOTH ordinary completion (see above)
    AND an unexpected exception mid-loop -- everything fetched before the
    crash must still be durable, or a re-run couldn't resume from where it
    left off."""
    cache_path = tmp_path / "fdc_cache.json"
    cache = FdcCache(cache_path)

    class _CrashingClientWithCache:
        """Minimal test double with a real `_cache` (so run_grounding's
        `getattr(client, "_cache", None)` flush path has something to find)
        and no `search_food_with_reason` (exercises the coarser fallback
        path in `_terminal_outcome_for_ingredient` too)."""

        def __init__(self, cache: FdcCache):
            self._cache = cache

        def search_food(self, name: str, *, preparation: str | None = None):
            self._cache.set_payload(name, ["Foundation"], 5, {"foods": []})
            if name == "boom":
                raise RuntimeError("simulated crash mid-run")
            return None

    client = _CrashingClientWithCache(cache)
    recipe_ok = _recipe(
        "r_a_ok", "OK Recipe", [Ingredient(name="chicken breast", amount=200, unit="g")], calories=200
    )
    recipe_boom = _recipe("r_b_boom", "Boom Recipe", [Ingredient(name="boom", amount=200, unit="g")], calories=200)

    with pytest.raises(RuntimeError, match="simulated crash mid-run"):
        run_grounding(
            client=client,
            sidecar_path=tmp_path / "grounding.jsonl",
            corpus=[recipe_ok, recipe_boom],
            seeds=[],
        )

    # The crash happened well under the 50-entry auto-flush threshold --
    # this is on disk only because of the finally-block flush.
    assert cache_path.exists()
    reloaded = FdcCache(cache_path)
    assert reloaded.get_payload("chicken breast", ["Foundation"], 5) == {"foods": []}


def test_run_grounding_flush_is_a_silent_no_op_for_a_client_without_a_cache(tmp_path) -> None:
    """A caller-supplied test double with no `_cache` attribute at all (e.g.
    `FakeUsdaClient` throughout this file) must not raise -- the flush is
    read defensively, matching how `rejection_counts` already is."""
    recipe = _recipe(
        "r_21", "Chicken Bowl",
        [Ingredient(name="chicken breast", amount=200, unit="g")],
        calories=330,
    )
    client = FakeUsdaClient({"chicken breast": _match("chicken breast", calories=165, protein_g=31)})

    report = run_grounding(
        client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=[recipe], seeds=[recipe]
    )

    assert report.seed_rows[0].status.value == "grounded"


def test_grounding_never_mutates_the_source_recipe_file(tmp_path) -> None:
    seed_path = tmp_path / "sample_recipes.jsonl"
    seed_path.write_text(
        json.dumps(
            {
                "recipe_id": "r_8",
                "title": "Chicken Bowl",
                "ingredients": [{"name": "chicken breast", "amount": 200, "unit": "g"}],
                "instructions": ["Cook."],
                "calories": 330,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = seed_path.read_bytes()

    from app.rag.loaders import load_recipes

    seeds = load_recipes(seed_path)
    client = FakeUsdaClient({"chicken breast": _match("chicken breast", calories=165, protein_g=31)})
    run_grounding(client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=seeds, seeds=seeds)

    assert seed_path.read_bytes() == before


def test_corpus_wide_ungrounded_frequency_dedupes_within_a_recipe(tmp_path) -> None:
    # "mystery sauce" appears twice in r_20 -- must count that recipe once,
    # not twice, and "mystery sauce" itself should be normalized the same
    # way whether it's the ingredient's raw name or not.
    recipe = _recipe(
        "r_20", "Double Trouble",
        [
            Ingredient(name="mystery sauce", amount=50, unit="g"),
            Ingredient(name="mystery sauce", amount=20, unit="g"),
            Ingredient(name="chicken breast", amount=100, unit="g"),
        ],
        calories=300,
    )
    other = _recipe(
        "r_21", "Solo Mystery",
        [Ingredient(name="mystery sauce", amount=30, unit="g")],
        calories=100,
    )
    client = FakeUsdaClient(
        {"mystery sauce": None, "chicken breast": _match("chicken breast", calories=165, protein_g=31)}
    )

    report = run_grounding(
        client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=[recipe, other], seeds=[recipe, other]
    )

    entry = next(row for row in report.ungrounded_frequency if row.name == "mystery sauce")
    assert entry.recipe_count == 2


def test_corpus_wide_ratio_distribution_and_outliers(tmp_path) -> None:
    normal = _recipe(
        "r_22", "Normal Ratio",
        [Ingredient(name="chicken breast", amount=200, unit="g")],
        calories=330,
    )
    outlier = _recipe(
        "r_23", "Wild Outlier",
        [Ingredient(name="chicken breast", amount=200, unit="g")],
        calories=50,  # computed will be 330 -> ratio 6.6x, above RATIO_OUTLIER_MAX
    )
    no_tag = _recipe(
        "r_24", "No Tag",
        [Ingredient(name="chicken breast", amount=200, unit="g")],
        calories=None,
    )
    client = FakeUsdaClient({"chicken breast": _match("chicken breast", calories=165, protein_g=31)})

    report = run_grounding(
        client=client,
        sidecar_path=tmp_path / "grounding.jsonl",
        corpus=[normal, outlier, no_tag],
        seeds=[normal, outlier, no_tag],
    )

    # Only the two tag-carrying recipes contribute to the distribution.
    assert len(report.ratio_distribution) == 2
    assert any(o.recipe_id == "r_23" for o in report.ratio_outliers)
    assert all(o.ratio > RATIO_OUTLIER_MAX for o in report.ratio_outliers if o.recipe_id == "r_23")
    assert not any(o.recipe_id == "r_22" for o in report.ratio_outliers)


def test_implausible_kcal_is_written_to_the_sidecar_as_a_demoting_flag(tmp_path) -> None:
    # Not just a seed: the flag must land on the sidecar's RecipeNutrition
    # itself, corpus-wide, so nutrition_view's chokepoint (which only ever
    # reads recipe.nutrition, never the report) sees it too.
    recipe = _recipe("r_30", "Absurd", [Ingredient(name="oil", amount=1000, unit="g")], calories=500)
    client = FakeUsdaClient({"oil": _match("oil", calories=884)})  # 8840 kcal/serving

    sidecar_path = tmp_path / "grounding.jsonl"
    run_grounding(client=client, sidecar_path=sidecar_path, corpus=[recipe], seeds=[recipe])

    rows = [json.loads(line) for line in sidecar_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["nutrition"]["flags"] == [DEMOTING_FLAG_IMPLAUSIBLE_KCAL]


def test_plausible_recipe_has_no_flags_in_the_sidecar(tmp_path) -> None:
    recipe = _recipe("r_31", "Chicken Bowl", [Ingredient(name="chicken breast", amount=200, unit="g")], calories=330)
    client = FakeUsdaClient({"chicken breast": _match("chicken breast", calories=165, protein_g=31)})

    sidecar_path = tmp_path / "grounding.jsonl"
    run_grounding(client=client, sidecar_path=sidecar_path, corpus=[recipe], seeds=[recipe])

    rows = [json.loads(line) for line in sidecar_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["nutrition"]["flags"] == []


def test_corpus_wide_implausible_band_count_independent_of_seed_set(tmp_path) -> None:
    plausible = _recipe(
        "r_25", "Fine", [Ingredient(name="chicken breast", amount=200, unit="g")], calories=330
    )
    implausible = _recipe(
        "r_26", "Absurd", [Ingredient(name="oil", amount=1000, unit="g")], calories=500
    )
    client = FakeUsdaClient(
        {"chicken breast": _match("chicken breast", calories=165, protein_g=31), "oil": _match("oil", calories=884)}
    )

    # Seeds list only includes the plausible recipe -- the corpus-wide count
    # must still catch the implausible one via `corpus`, not just `seeds`.
    report = run_grounding(
        client=client,
        sidecar_path=tmp_path / "grounding.jsonl",
        corpus=[plausible, implausible],
        seeds=[plausible],
    )

    assert report.implausible_band_corpus_count == 1


def test_rejection_counts_flow_from_client_diagnostics_into_the_report(tmp_path) -> None:
    class _ClientWithDiagnostics(FakeUsdaClient):
        def __init__(self, matches):
            super().__init__(matches)
            self.rejection_counts = {"kcal_too_high": 3, "mass_over_105g": 1}

    recipe = _recipe(
        "r_27", "Whatever", [Ingredient(name="chicken breast", amount=200, unit="g")], calories=330
    )
    client = _ClientWithDiagnostics({"chicken breast": _match("chicken breast", calories=165, protein_g=31)})

    report = run_grounding(client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=[recipe], seeds=[recipe])

    assert report.rejection_counts == {"kcal_too_high": 3, "mass_over_105g": 1}
    markdown = render_report(report)
    assert "kcal_too_high" in markdown
    assert "| 3 |" in markdown


def test_branded_dispersion_events_flow_from_client_diagnostics_into_the_report(tmp_path) -> None:
    class _ClientWithDispersion(FakeUsdaClient):
        def __init__(self, matches):
            super().__init__(matches)
            self.branded_dispersion_events = [("mystery seasoning", 50.0, 400.0, 4)]

    recipe = _recipe(
        "r_29", "Whatever", [Ingredient(name="chicken breast", amount=200, unit="g")], calories=330
    )
    client = _ClientWithDispersion({"chicken breast": _match("chicken breast", calories=165, protein_g=31)})

    report = run_grounding(client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=[recipe], seeds=[recipe])

    assert len(report.branded_dispersion_events) == 1
    event = report.branded_dispersion_events[0]
    assert event.query == "mystery seasoning"
    assert event.min_kcal == 50.0
    assert event.max_kcal == 400.0
    assert event.candidate_count == 4

    markdown = render_report(report)
    assert "mystery seasoning" in markdown


def test_build_report_works_from_precomputed_results_without_any_client(tmp_path) -> None:
    # This is the baseline-capture use case: build the extended report
    # straight from an already-loaded sidecar, with zero network calls and
    # no UsdaClient at all.
    recipe = _recipe(
        "r_28", "Chicken Bowl", [Ingredient(name="chicken breast", amount=200, unit="g")], calories=330
    )
    nutrition = RecipeNutrition(
        status=GroundingStatus.GROUNDED,
        servings=1,
        total=FoodMacros(calories=330, protein_g=62, carbs_g=0, fat_g=7.14, fiber_g=0),
        per_serving=FoodMacros(calories=330, protein_g=62, carbs_g=0, fat_g=7.14, fiber_g=0),
        contributions=[],
        ungrounded_ingredients=[],
        coverage=1.0,
    )

    report = build_report(corpus=[recipe], seeds=[recipe], results={"r_28": nutrition})

    assert report.total_recipes == 1
    assert report.status_counts == {"grounded": 1}
    assert report.seed_rows[0].computed_kcal == 330


def _nutrition(status, calories, protein_g, carbs_g, fat_g) -> RecipeNutrition:
    macros = FoodMacros(calories=calories, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g, fiber_g=0)
    return RecipeNutrition(
        status=status,
        servings=1,
        total=macros,
        per_serving=macros,
        contributions=[],
        ungrounded_ingredients=[],
        coverage=1.0 if status == GroundingStatus.GROUNDED else (0.5 if status == GroundingStatus.PARTIAL else 0.0),
    )


def _seed_recipe(recipe_id, *, calories, protein_g, carbs_g, fat_g) -> Recipe:
    return Recipe(
        recipe_id=recipe_id,
        title=recipe_id,
        ingredients=[Ingredient(name="whatever", amount=1, unit="g")],
        instructions=["Cook."],
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        servings=1,
    )


def test_compute_seed_macro_accuracy_synthetic_fixture() -> None:
    # Seed A: GROUNDED, every tag macro present and nonzero -- contributes to
    # all four error stats.
    seed_a = _seed_recipe("sa1", calories=200, protein_g=20, carbs_g=10, fat_g=5)
    nutrition_a = _nutrition(GroundingStatus.GROUNDED, calories=220, protein_g=18, carbs_g=12, fat_g=5)

    # Seed B: PARTIAL (still has a real computed value), but tag protein_g
    # is None and tag carbs_g is 0 -- both must land in "missing", not be
    # divided into a spurious error.
    seed_b = _seed_recipe("sa2", calories=100, protein_g=None, carbs_g=0, fat_g=10)
    nutrition_b = _nutrition(GroundingStatus.PARTIAL, calories=150, protein_g=99, carbs_g=99, fat_g=8)

    # Seed C: UNGROUNDED -- has real tag values for every macro, but no
    # computed value exists at all, so every macro is "missing" for it.
    seed_c = _seed_recipe("sa3", calories=300, protein_g=30, carbs_g=40, fat_g=10)
    nutrition_c = _nutrition(GroundingStatus.UNGROUNDED, calories=0, protein_g=0, carbs_g=0, fat_g=0)

    seeds_by_id = {"sa1": seed_a, "sa2": seed_b, "sa3": seed_c}
    results = {"sa1": nutrition_a, "sa2": nutrition_b, "sa3": nutrition_c}

    accuracy = compute_seed_macro_accuracy(seeds_by_id, results)

    assert accuracy.n_seeds == 3
    assert accuracy.n_grounded == 1
    assert accuracy.n_partial == 1
    assert accuracy.n_ungrounded == 1

    # kcal: seed A |220-200|/200 = 0.10, seed B |150-100|/100 = 0.50, seed C missing.
    assert accuracy.kcal.n == 2
    assert accuracy.kcal.median_abs_relative_error == pytest.approx(0.30)
    assert accuracy.kcal.mean_abs_relative_error == pytest.approx(0.30)
    assert accuracy.kcal_missing == 1

    # protein_g: only seed A qualifies (B's tag is None, C is ungrounded).
    assert accuracy.protein_g.n == 1
    assert accuracy.protein_g.median_abs_relative_error == pytest.approx(0.10)
    assert accuracy.protein_g_missing == 2

    # carbs_g: only seed A qualifies (B's tag is 0, C is ungrounded).
    assert accuracy.carbs_g.n == 1
    assert accuracy.carbs_g.median_abs_relative_error == pytest.approx(0.20)
    assert accuracy.carbs_g_missing == 2

    # fat_g: seed A |5-5|/5 = 0.0, seed B |8-10|/10 = 0.2, seed C missing.
    assert accuracy.fat_g.n == 2
    assert accuracy.fat_g.median_abs_relative_error == pytest.approx(0.10)
    assert accuracy.fat_g.mean_abs_relative_error == pytest.approx(0.10)
    assert accuracy.fat_g_missing == 1


def test_compute_seed_macro_accuracy_excludes_seed_absent_from_results() -> None:
    seed_a = _seed_recipe("sa1", calories=200, protein_g=20, carbs_g=10, fat_g=5)
    seed_b = _seed_recipe("sa2", calories=100, protein_g=10, carbs_g=10, fat_g=10)
    nutrition_a = _nutrition(GroundingStatus.GROUNDED, calories=200, protein_g=20, carbs_g=10, fat_g=5)

    accuracy = compute_seed_macro_accuracy({"sa1": seed_a, "sa2": seed_b}, {"sa1": nutrition_a})

    # sa2 was never ground (not in `results`) -- excluded from n_seeds entirely,
    # not counted as ungrounded.
    assert accuracy.n_seeds == 1
    assert accuracy.n_grounded == 1
    assert accuracy.n_ungrounded == 0


def test_compute_seed_macro_accuracy_all_missing_renders_none_not_zero() -> None:
    seed_c = _seed_recipe("sa3", calories=300, protein_g=30, carbs_g=40, fat_g=10)
    nutrition_c = _nutrition(GroundingStatus.UNGROUNDED, calories=0, protein_g=0, carbs_g=0, fat_g=0)

    accuracy = compute_seed_macro_accuracy({"sa3": seed_c}, {"sa3": nutrition_c})

    assert accuracy.kcal.n == 0
    assert accuracy.kcal.median_abs_relative_error is None
    assert accuracy.kcal.mean_abs_relative_error is None
    assert accuracy.kcal_missing == 1


def test_seed_macro_accuracy_flows_through_build_report_and_render(tmp_path) -> None:
    seed_a = _seed_recipe("sa1", calories=200, protein_g=20, carbs_g=10, fat_g=5)
    nutrition_a = _nutrition(GroundingStatus.GROUNDED, calories=220, protein_g=18, carbs_g=12, fat_g=5)

    report = build_report(corpus=[seed_a], seeds=[seed_a], results={"sa1": nutrition_a})

    assert report.seed_macro_accuracy is not None
    assert report.seed_macro_accuracy.n_seeds == 1
    assert report.seed_macro_accuracy.kcal.n == 1
    assert report.seed_macro_accuracy.kcal.median_abs_relative_error == pytest.approx(0.10)

    markdown = render_report(report)
    assert "Seed macro-computation accuracy (pre-registered A3 eval)" in markdown
    assert "kcal (PRIMARY)" in markdown
    assert "10.0%" in markdown  # the 0.10 relative error rendered as a percentage


def test_render_report_includes_flags_and_counts(tmp_path) -> None:
    recipe = _recipe(
        "r_9", "Rice Bowl",
        [Ingredient(name="brown rice", amount=200, unit="g", preparation="cooked")],
        calories=300,
    )
    client = FakeUsdaClient({"brown rice": _match("brown rice", calories=370)})

    report = run_grounding(
        client=client, sidecar_path=tmp_path / "grounding.jsonl", corpus=[recipe], seeds=[recipe]
    )
    markdown = render_report(report)

    assert "r_9" in markdown
    assert "RAW/COOKED BLOWUP" in markdown
    assert "grounded: 1 (100.0%)" in markdown
