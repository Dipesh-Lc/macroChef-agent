import json
from pathlib import Path

import requests

from app.config import Settings
from app.schemas.ingredient import Ingredient
from app.schemas.nutrition import FoodMacros, FoodMatch
from app.schemas.recipe import Recipe
from app.services.grounding_job import (
    IMPLAUSIBLE_MAX_KCAL_PER_SERVING,
    RAW_COOKED_BLOWUP_RATIO,
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
