import json
from pathlib import Path

import pytest
import requests

from app.config import Settings
from app.schemas.nutrition import FoodMacros
from app.services.nutrition_cache import FdcCache
from app.services.usda_client import (
    _BRANDED_DATA_TYPES,
    _BRANDED_PAGE_SIZE,
    _FDC_QUERY_ALIASES,
    _GENERIC_DATA_TYPES,
    _GENERIC_PAGE_SIZE,
    UsdaClient,
    _classify_preparation,
    _is_relevant_match,
    _plausibility_reject_reason,
    _select_branded_match,
    _tokenize,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _settings(*, fdc_api_key: str | None = None) -> Settings:
    """A Settings instance built from explicit alias kwargs (the only way
    init args override aliased fields in pydantic-settings) so these tests
    never fall through to a developer's real local .env file."""

    return Settings(
        FDC_API_KEY=fdc_api_key,
        FDC_BASE_URL="https://api.nal.usda.gov/fdc/v1",
        MODEL_TIMEOUT_SECONDS=5.0,
    )


def _client(*, session, cache, fdc_api_key: str | None = "test-key") -> UsdaClient:
    """UsdaClient with retry backoff sleep stubbed out -- these tests exercise
    retry behavior deliberately and must not incur real wall-clock delay."""

    return UsdaClient(settings=_settings(fdc_api_key=fdc_api_key), session=session, cache=cache, sleep=lambda _: None)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, payload: dict | None = None, exc: Exception | None = None, status_code: int = 200):
        self.payload = payload
        self.exc = exc
        self.status_code = status_code
        self.calls = 0
        self.last_params: dict | None = None

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        self.last_params = params
        if self.exc is not None:
            raise self.exc
        return FakeResponse(self.payload or {}, status_code=self.status_code)


def test_extracts_known_macros_from_chicken_breast_fixture(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_chicken_breast_search.json"))
    client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    match = client.search_food("chicken breast")

    assert match is not None
    assert match.macros.calories == 165
    assert match.macros.protein_g == 31
    assert match.macros.carbs_g == 0
    assert match.macros.fat_g == 3.57
    assert match.macros.fiber_g == 0


def test_extract_macros_skips_candidate_with_a_negative_nutrient_value(tmp_path) -> None:
    # Confirmed live: a real FDC record's "Carbohydrate, by difference"
    # value can come out marginally negative (e.g. -0.428) from that
    # nutrient's own subtraction-based calculation upstream at USDA. Since
    # FoodMacros enforces ge=0 on every field, silently passing this through
    # would crash the whole grounding run on Pydantic validation instead of
    # degrading to "skip this candidate" -- this must never reach that point.
    payload = {
        "foods": [
            {
                "fdcId": 1,
                "description": "Widget, raw",
                "dataType": "Foundation",
                "foodNutrients": [
                    {"nutrientNumber": "208", "value": 50},
                    {"nutrientNumber": "203", "value": 2},
                    {"nutrientNumber": "204", "value": 1},
                    {"nutrientNumber": "205", "value": -0.428},
                ],
            }
        ]
    }
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("widget")  # must not raise

    assert match is None


def test_extracts_known_macros_from_rice_fixture(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_rice_search.json"))
    client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    match = client.search_food("rice")

    assert match is not None
    assert match.macros.calories == 130
    assert match.macros.protein_g == 2.69
    assert match.macros.carbs_g == 28.17
    assert match.macros.fat_g == 0.28
    assert match.macros.fiber_g == 0.4


def test_query_normalization_before_request_and_cache_key(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_chicken_breast_search.json"))
    client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    match = client.search_food("Chicken Breasts (boneless)")

    assert match is not None
    assert match.query == "chicken breast"
    assert session.last_params["query"] == "chicken breast"


def test_prefers_foundation_or_sr_legacy_over_branded(tmp_path) -> None:
    # The fixture deliberately lists a Branded entry before the SR Legacy one.
    session = FakeSession(payload=_load_fixture("fdc_chicken_breast_search.json"))
    client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    match = client.search_food("chicken breast")

    assert match is not None
    assert match.data_type == "SR Legacy"


def test_no_api_key_returns_none_without_request(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_chicken_breast_search.json"))
    client = UsdaClient(
        settings=_settings(fdc_api_key=None),
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    match = client.search_food("chicken breast")

    assert match is None
    assert session.calls == 0


def test_network_error_returns_none_without_raising(tmp_path) -> None:
    session = FakeSession(exc=requests.ConnectionError("no route to host"))
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("chicken breast")

    assert match is None
    assert session.calls == 16  # exhausted retries on both the generic and Branded tiers


def test_non_200_response_returns_none_without_raising(tmp_path) -> None:
    session = FakeSession(payload={}, status_code=503)
    client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        sleep=lambda _: None,
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    match = client.search_food("chicken breast")

    assert match is None
    assert session.calls == 16  # exhausted retries on both the generic and Branded tiers


class FlakySession:
    """Fails `fail_times` calls (raising the given exception), then serves
    `payload` -- simulates the observed live behavior where an identical FDC
    request intermittently 400s before succeeding on retry."""

    def __init__(self, payload: dict, fail_times: int, exc: Exception | None = None):
        self.payload = payload
        self.fail_times = fail_times
        self.exc = exc or requests.HTTPError("400 Client Error: Bad Request")
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return FakeResponse(self.payload)


def test_transient_failure_recovers_on_retry(tmp_path) -> None:
    session = FlakySession(payload=_load_fixture("fdc_chicken_breast_search.json"), fail_times=2)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("chicken breast")

    assert match is not None
    assert match.macros.calories == 165
    assert session.calls == 3


def test_retry_exhausted_failure_is_not_cached_so_next_run_retries(tmp_path) -> None:
    cache = FdcCache(tmp_path / "cache.json")
    always_fails = FlakySession(payload=_load_fixture("fdc_chicken_breast_search.json"), fail_times=99)
    first_client = _client(session=always_fails, cache=cache)

    first_match = first_client.search_food("chicken breast")
    assert first_match is None
    assert always_fails.calls == 16  # exhausted retries on both the generic and Branded tiers

    # A later run (e.g. after the outage clears) must get a fresh attempt --
    # a persistent failure must never poison the cache as a confirmed no-match.
    recovers_now = FlakySession(payload=_load_fixture("fdc_chicken_breast_search.json"), fail_times=0)
    second_client = _client(session=recovers_now, cache=cache)

    second_match = second_client.search_food("chicken breast")

    assert second_match is not None
    assert second_match.macros.calories == 165


def test_confirmed_empty_payload_is_cached_and_skips_future_network_calls(tmp_path) -> None:
    cache = FdcCache(tmp_path / "cache.json")
    session = FakeSession(payload=_load_fixture("fdc_empty_search.json"))
    first_client = _client(session=session, cache=cache)

    first_match = first_client.search_food("nonexistent ingredient xyz")
    assert first_match is None
    assert session.calls == 2  # both tiers queried (generic, then Branded fallback), both empty
    assert cache.get_payload("nonexistent ingredient xyz", _GENERIC_DATA_TYPES, _GENERIC_PAGE_SIZE) is not None
    assert cache.get_payload("nonexistent ingredient xyz", _BRANDED_DATA_TYPES, _BRANDED_PAGE_SIZE) is not None

    # A cached empty-`foods` payload is a stable fact (the fixture's content
    # is unchanging) -- re-querying must be served from that cached payload,
    # not the network, unlike a retry-exhausted transient failure above.
    unreachable = FakeSession(exc=AssertionError("should not be called"))
    second_client = _client(session=unreachable, cache=cache)

    second_match = second_client.search_food("nonexistent ingredient xyz")

    assert second_match is None
    assert unreachable.calls == 0


def test_empty_results_return_none(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_empty_search.json"))
    client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    match = client.search_food("nonexistent ingredient xyz")

    assert match is None


def test_cache_hit_skips_second_request(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_chicken_breast_search.json"))
    cache = FdcCache(tmp_path / "cache.json")
    client = UsdaClient(settings=_settings(fdc_api_key="test-key"), session=session, cache=cache)

    first = client.search_food("chicken breast")
    second = client.search_food("chicken breast")

    assert session.calls == 1
    assert first == second


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Rice, brown, long-grain, cooked", "cooked"),
        ("Rice, brown, long-grain, raw", "raw"),
        ("Beans, black, mature seeds, canned, solids and liquids", "canned"),
        ("Lentils, raw", "raw"),
        ("Lentils, mature seeds, dry", "raw"),
        ("Quinoa, uncooked", "raw"),
        ("Chicken, broilers or fryers, breast, meat only, boiled", "cooked"),
        ("CHICKEN BREAST NUGGETS, CHICKEN BREAST", None),
        ("Rice, brown, long-grain, COOKED", "cooked"),
        ("Potato, baked, flesh and skin, without salt", None),
        ("Broccoli, frozen, chopped, unprepared", None),
    ],
)
def test_classify_preparation(description, expected) -> None:
    assert _classify_preparation(description) == expected


def test_preparation_gate_selects_cooked_over_higher_ranked_raw_record(tmp_path) -> None:
    # Foundation (raw) outranks SR Legacy (cooked) under _DATA_TYPE_PRIORITY,
    # so an ungated search would return the raw record -- the exact failure
    # mode a declared-cooked ingredient must never fall into.
    session = FakeSession(payload=_load_fixture("fdc_rice_raw_and_cooked_search.json"))
    client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    ungated = client.search_food("brown rice")
    assert ungated is not None
    assert ungated.description.endswith("raw")

    cooked = client.search_food("brown rice", preparation="cooked")
    assert cooked is not None
    assert cooked.description.endswith("cooked")
    assert cooked.macros.calories == 112

    raw = client.search_food("brown rice", preparation="raw")
    assert raw is not None
    assert raw.description.endswith("raw")
    assert raw.macros.calories == 370


def test_preparation_gate_returns_none_when_no_candidate_matches_declared_state(tmp_path) -> None:
    # The rice fixture only has a cooked record -- a raw-declared ingredient
    # must ground to nothing rather than silently accept the cooked one.
    session = FakeSession(payload=_load_fixture("fdc_rice_search.json"))
    client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    match = client.search_food("rice", preparation="raw")

    assert match is None


def test_preparation_gate_accepts_matching_canned_record(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_black_beans_canned_search.json"))
    client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    match = client.search_food("black beans", preparation="canned")

    assert match is not None
    assert match.macros.calories == 132


def test_preparation_gate_rejects_unclassifiable_branded_record(tmp_path) -> None:
    # Neither candidate in the chicken-breast fixture classifies as "cooked"
    # (one is raw, one has no state keyword at all) -- both must be excluded.
    session = FakeSession(payload=_load_fixture("fdc_chicken_breast_search.json"))
    client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    match = client.search_food("chicken breast", preparation="cooked")

    assert match is None


def test_cache_key_distinguishes_by_preparation(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_rice_raw_and_cooked_search.json"))
    cache = FdcCache(tmp_path / "cache.json")
    client = UsdaClient(settings=_settings(fdc_api_key="test-key"), session=session, cache=cache)

    raw_match = client.search_food("rice", preparation="raw")
    cooked_match = client.search_food("rice", preparation="cooked")
    assert session.calls == 2
    assert raw_match.description.endswith("raw")
    assert cooked_match.description.endswith("cooked")

    # Repeating both calls must be served entirely from cache -- a shared
    # cache key would have let the second call's result leak into the first.
    client.search_food("rice", preparation="raw")
    client.search_food("rice", preparation="cooked")
    assert session.calls == 2


def test_disk_cache_round_trips_across_client_instances(tmp_path) -> None:
    cache_path = tmp_path / "cache.json"
    session = FakeSession(payload=_load_fixture("fdc_chicken_breast_search.json"))
    first_client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"), session=session, cache=FdcCache(cache_path)
    )
    first_client.search_food("chicken breast")

    assert cache_path.exists()

    # A fresh client with no session at all must serve the cached match from disk.
    unreachable_session = FakeSession(exc=AssertionError("should not be called"))
    second_client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        session=unreachable_session,
        cache=FdcCache(cache_path),
    )
    match = second_client.search_food("chicken breast")

    assert match is not None
    assert match.macros.calories == 165


# --- Relevance check: regression catalogue from the real live grounding run ---
#
# Before this check existed, `_best_match` picked candidates purely by
# `_DATA_TYPE_PRIORITY`, with no verification that the description was even
# the same food as the query. Running the real corpus through live FDC
# surfaced these exact wrong matches (see the 1.4 Step B checkpoint) --
# each fixture below reproduces the live response shape that caused it.


@pytest.mark.parametrize(
    ("query", "description", "preparation", "expected"),
    [
        ("bell pepper", "Peppers, bell, green, raw", None, True),
        ("bell pepper", "TACO BELL, Nachos", None, False),
        ("avocado", "Avocado, Hass, peeled, raw", None, True),
        ("avocado", "Oil, avocado", None, False),
        ("zucchini", "Bread, zucchini", None, False),
        ("oats", "Oats, whole grain, steel cut", None, True),
        ("oats", "Oat milk, unsweetened, plain, refrigerated", None, False),
        ("carrot", "Carrots, raw", None, True),
        ("black beans", "Beans, black turtle, mature seeds, canned", "canned", True),
        ("black beans", "Soup, black bean, canned, condensed", "canned", False),
        ("brown rice", "Rice, brown, cooked, as ingredient", "cooked", True),
        ("jasmine rice", "JASMINE COOKED RICE, JASMINE", "cooked", True),
        ("quinoa", "Quinoa, uncooked", "raw", True),
        # The one known, accepted exception: FDC files zucchini's Foundation
        # record under "Squash" (its botanical name), not "Zucchini" -- the
        # head-noun check can't know these are the same food without a
        # synonym table, so this correctly-real record is rejected too. Per
        # the project's fail-closed philosophy, an honest UNGROUNDED here is
        # the safe outcome, not a bug to work around with a synonym list.
        ("zucchini", "Squash, summer, green, zucchini, includes skin, raw", None, False),
    ],
)
def test_is_relevant_match(query, description, preparation, expected) -> None:
    assert _is_relevant_match(query, description, preparation) is expected


def test_relevance_check_rejects_wrong_food_end_to_end(tmp_path) -> None:
    # bell pepper -> TACO BELL Nachos, confirmed live before this fix.
    session = FakeSession(payload=_load_fixture("fdc_bell_pepper_relevance_search.json"))
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("bell pepper")

    assert match is not None
    assert match.description == "Peppers, bell, green, raw"
    assert match.macros.calories == 22.9


def test_relevance_check_rejects_avocado_oil_end_to_end(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_avocado_relevance_search.json"))
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("avocado")

    assert match is not None
    assert match.description == "Avocado, Hass, peeled, raw"
    assert match.macros.calories == 167


def test_relevance_check_rejects_zucchini_bread_but_alias_resolves_the_real_record_end_to_end(tmp_path) -> None:
    # "Bread, zucchini" (a derivative product) is still correctly rejected
    # by the bare relevance check -- but the phase 1.5/P4
    # `_FDC_QUERY_ALIASES` entry for "zucchini" now lets the genuinely
    # correct "Squash, summer, green, zucchini, includes skin, raw" record
    # resolve, instead of leaving this UNGROUNDED as before P4 (see the
    # parametrized `_is_relevant_match` case above, which is still true for
    # the UN-aliased bare query -- that check itself didn't change).
    session = FakeSession(payload=_load_fixture("fdc_zucchini_relevance_search.json"))
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("zucchini")

    assert match is not None
    assert match.description == "Squash, summer, green, zucchini, includes skin, raw"
    assert match.macros.calories == 17


def test_relevance_check_accepts_real_oats_rejects_oat_milk_end_to_end(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_oats_relevance_search.json"))
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("oats")

    assert match is not None
    assert match.description == "Oats, whole grain, steel cut"


def test_relevance_check_accepts_real_carrot_over_dehydrated_when_data_type_ties(tmp_path) -> None:
    # Both pass relevance (both are genuinely carrot); the dehydrated-vs-raw
    # state distinction for un-prepped ingredients is a separate, disclosed
    # gap (no `preparation` gate applies here) -- this test only proves
    # relevance doesn't reject the correct one.
    session = FakeSession(payload=_load_fixture("fdc_carrot_relevance_search.json"))
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("carrot")

    assert match is not None
    assert match.description in ("Carrots, raw", "Carrot, dehydrated")


def test_relevance_check_rejects_black_bean_soup_end_to_end(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_black_beans_soup_and_beans_search.json"))
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("black beans", preparation="canned")

    assert match is not None
    assert match.description == "Beans, black turtle, mature seeds, canned"


def test_preparation_word_is_appended_to_the_search_query_sent_to_fdc(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_rice_raw_and_cooked_search.json"))
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    client.search_food("brown rice", preparation="cooked")

    assert session.last_params["query"] == "brown rice cooked"


def test_no_preparation_leaves_search_query_unaugmented(tmp_path) -> None:
    session = FakeSession(payload=_load_fixture("fdc_chicken_breast_search.json"))
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    client.search_food("chicken breast")

    assert session.last_params["query"] == "chicken breast"


def test_known_unreliable_query_returns_none_without_any_network_call(tmp_path) -> None:
    # "shrimp"/"tomato sauce" (wrong-form, no preparation gate applies, and
    # the wrong-form match's macros are plausible-looking enough that the
    # plausibility gate alone wouldn't catch it) are deliberately excluded
    # (see _KNOWN_UNRELIABLE_QUERIES). Must fail closed before ever touching
    # the network or cache. "chili powder"/"ginger" used to be on this list
    # too but were dropped once the plausibility gate could catch their
    # specific failure mode (0 kcal data defect) generally -- see
    # test_plausibility_gate_rejects_zero_kcal_defect below.
    session = FakeSession(exc=AssertionError("must not be called"))
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    assert client.search_food("shrimp") is None
    assert client.search_food("tomato sauce") is None
    assert session.calls == 0


# --- Two-tier fetch: generic dataTypes first, Branded only as a fallback ---
#
# Confirmed live: a single combined `dataType=[...all 4...]` query at
# pageSize=5 lets Branded's catalog volume crowd a real Foundation/SR Legacy
# record out of the fetched window entirely (e.g. "greek yogurt" returns 5/5
# Branded despite a real Foundation "Yogurt, Greek, plain, nonfat" record
# existing). `TieredFakeSession` actually filters by the `dataType` request
# param (unlike `FakeSession`, which ignores it) so these tests can prove the
# client queries generic types in their own request first.


class TieredFakeSession:
    """Routes to a different fixed payload per requested `dataType` list,
    tracking how many distinct (query, dataType) calls were made -- this is
    what a real FDC response would do (filter by dataType), which the
    single-payload FakeSession above deliberately does not simulate."""

    def __init__(self, by_data_types: dict[tuple[str, ...], dict]):
        self._by_data_types = by_data_types
        self.calls: list[tuple[str, ...]] = []

    def get(self, url, params=None, timeout=None):
        data_types = tuple(params["dataType"])
        self.calls.append(data_types)
        payload = self._by_data_types.get(data_types, {"foods": []})
        return FakeResponse(payload)


def test_generic_tier_is_queried_first_and_branded_never_called_when_it_succeeds(tmp_path) -> None:
    session = TieredFakeSession(
        {
            ("Foundation", "SR Legacy", "Survey (FNDDS)"): _load_fixture("fdc_greek_yogurt_foundation_search.json"),
            ("Branded",): _load_fixture("fdc_greek_yogurt_branded_only_search.json"),
        }
    )
    client = UsdaClient(settings=_settings(fdc_api_key="test-key"), session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("greek yogurt")

    assert match is not None
    assert match.description == "Yogurt, Greek, plain, nonfat"
    assert match.macros.calories == 61
    assert session.calls == [("Foundation", "SR Legacy", "Survey (FNDDS)")]  # Branded tier never called


def test_branded_fallback_fires_when_generic_tier_has_nothing_relevant(tmp_path) -> None:
    # Simulates an ingredient that genuinely only exists as Branded data --
    # the generic tier returns real candidates but none relevant/usable, so
    # the Branded fallback must still resolve it rather than leaving it
    # ungrounded just because a generic tier exists in principle.
    session = TieredFakeSession(
        {
            ("Foundation", "SR Legacy", "Survey (FNDDS)"): {"foods": []},
            ("Branded",): _load_fixture("fdc_greek_yogurt_branded_only_search.json"),
        }
    )
    client = UsdaClient(settings=_settings(fdc_api_key="test-key"), session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("greek yogurt")

    assert match is not None
    assert match.data_type == "Branded"
    assert session.calls == [("Foundation", "SR Legacy", "Survey (FNDDS)"), ("Branded",)]


def test_two_tier_fetch_is_deterministic_across_repeated_calls(tmp_path) -> None:
    # Same inputs, same tier order, same result every time -- no order-
    # dependence reintroduced by having two request tiers instead of one.
    session = TieredFakeSession(
        {
            ("Foundation", "SR Legacy", "Survey (FNDDS)"): _load_fixture("fdc_greek_yogurt_foundation_search.json"),
            ("Branded",): _load_fixture("fdc_greek_yogurt_branded_only_search.json"),
        }
    )
    cache = FdcCache(tmp_path / "cache.json")
    first = UsdaClient(settings=_settings(fdc_api_key="test-key"), session=session, cache=cache).search_food("greek yogurt")

    session2 = TieredFakeSession(
        {
            ("Foundation", "SR Legacy", "Survey (FNDDS)"): _load_fixture("fdc_greek_yogurt_foundation_search.json"),
            ("Branded",): _load_fixture("fdc_greek_yogurt_branded_only_search.json"),
        }
    )
    second = UsdaClient(
        settings=_settings(fdc_api_key="test-key"), session=session2, cache=FdcCache(tmp_path / "cache2.json")
    ).search_food("greek yogurt")

    assert first.description == second.description == "Yogurt, Greek, plain, nonfat"
    assert first.macros.calories == second.macros.calories == 61


# --- Payload cache: caches FDC facts, never a decided match ---
#
# The cache generation before this refactor stored the *decided* FoodMatch
# (or a "no match" sentinel) per ingredient query -- so a rule change in
# `_best_match` had no effect on an already-cached ingredient until its
# cache entry was manually busted. These tests prove the replacement: the
# cache stores the raw FDC payload, and `_best_match` is re-run against it
# on every call, so a rule change takes effect on the very next call with no
# cache invalidation and no new network request.


def _macro_food(fdc_id: int, description: str, data_type: str, *, calories, protein_g, fat_g, carbs_g) -> dict:
    return {
        "fdcId": fdc_id,
        "description": description,
        "dataType": data_type,
        "foodNutrients": [
            {"nutrientNumber": "208", "value": calories},
            {"nutrientNumber": "203", "value": protein_g},
            {"nutrientNumber": "204", "value": fat_g},
            {"nutrientNumber": "205", "value": carbs_g},
        ],
    }


def test_payload_cache_reflects_current_matching_rules_not_a_frozen_decision(tmp_path, monkeypatch) -> None:
    from app.services import usda_client as usda_client_module

    payload = {
        "foods": [
            _macro_food(1, "Widget, canned", "Branded", calories=200, protein_g=20, fat_g=5, carbs_g=10),
            _macro_food(2, "Widget, raw", "Foundation", calories=100, protein_g=10, fat_g=2, carbs_g=5),
        ]
    }
    session = FakeSession(payload=payload)
    cache = FdcCache(tmp_path / "cache.json")
    client = UsdaClient(settings=_settings(fdc_api_key="test-key"), session=session, cache=cache)

    first = client.search_food("widget")
    assert first is not None
    assert first.fdc_id == 2  # Foundation (priority 0) outranks Branded (priority 3) today
    assert session.calls == 1  # only the generic tier -- it already found a match

    # Simulate a matching-rule change: Branded now outranks Foundation.
    monkeypatch.setitem(usda_client_module._DATA_TYPE_PRIORITY, "Branded", -1)

    unreachable = FakeSession(exc=AssertionError("must be served from the cached payload, no new request"))
    second_client = UsdaClient(settings=_settings(fdc_api_key="test-key"), session=unreachable, cache=cache)
    second = second_client.search_food("widget")

    assert unreachable.calls == 0  # served entirely from the cached payload
    assert second is not None
    assert second.fdc_id == 1  # new rule takes effect immediately against the same cached payload


def test_old_decision_cache_format_is_discarded_not_misinterpreted(tmp_path) -> None:
    # Simulates a cache file written by the pre-refactor decision-cache
    # generation (bare "query" -> FoodMatch dict, no schema marker).
    cache_path = tmp_path / "cache.json"
    old_format_decision_cache = {
        "chicken breast": {
            "fdc_id": 1,
            "description": "Chicken breast",
            "data_type": "SR Legacy",
            "macros": {"calories": 165, "protein_g": 31, "carbs_g": 0, "fat_g": 3.57, "fiber_g": 0},
            "query": "chicken breast",
        }
    }
    cache_path.write_text(json.dumps(old_format_decision_cache), encoding="utf-8")

    session = FakeSession(payload=_load_fixture("fdc_chicken_breast_search.json"))
    client = _client(session=session, cache=FdcCache(cache_path))

    match = client.search_food("chicken breast")

    # The old-format entries are a different, incompatible shape -- discarded
    # wholesale rather than misread as a payload, so this falls through to a
    # normal fresh fetch.
    assert match is not None
    assert match.data_type == "SR Legacy"
    assert session.calls == 1


@pytest.mark.parametrize(
    ("calories", "protein_g", "fat_g", "carbs_g", "expected"),
    [
        (165, 31, 3.57, 0, None),  # ordinary chicken breast -- passes
        (0, 0, 0, 0, "kcal_too_low"),
        (4.9, 0, 0, 0, "kcal_too_low"),
        (951, 0, 0, 0, "kcal_too_high"),
        (884, 0, 100, 0, None),  # pure fat, at the edge -- still passes
        (500, 50, 40, 40, "mass_over_105g"),  # 130g macro mass in 100g food
        (920, 10, 2, 20, "atwater_mismatch"),  # kJ-scale-looking defect
        (18, 0, 0, 0.9, None),  # vinegar-like: absolute Atwater escape
    ],
)
def test_plausibility_reject_reason(calories, protein_g, fat_g, carbs_g, expected) -> None:
    macros = FoodMacros(calories=calories, protein_g=protein_g, fat_g=fat_g, carbs_g=carbs_g, fiber_g=0)
    assert _plausibility_reject_reason(macros) == expected


# --- Plausibility gate: reject a relevant, correctly-prepped candidate
# whose own reported macros are physically implausible ---


def test_plausibility_gate_rejects_zero_kcal_defect(tmp_path) -> None:
    # The exact defect that used to require "chili powder"/"ginger" on
    # _KNOWN_UNRELIABLE_QUERIES: a real, relevant record reporting 0
    # kcal/100g (no genuine spice is calorie-free).
    payload = {
        "foods": [_macro_food(1, "Ginger, ground", "Branded", calories=0, protein_g=0, fat_g=0, carbs_g=0)]
    }
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("ginger")

    assert match is None


def test_plausibility_gate_rejects_kj_scale_defect(tmp_path) -> None:
    # A record whose "calories" value is actually reported on a kJ scale
    # (roughly 4x a real kcal figure for this macro composition) -- passes
    # the bare <950 absolute ceiling but fails the Atwater cross-check.
    payload = {
        "foods": [
            _macro_food(1, "Widget, raw", "Foundation", calories=920, protein_g=10, fat_g=2, carbs_g=20)
            # Atwater estimate: 4*10 + 4*20 + 9*2 = 138 kcal. 920 kcal is
            # neither within [0.5x, 1.7x] of 138 nor within 25 kcal of it.
        ]
    }
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("widget")

    assert match is None


def test_plausibility_gate_rejects_macro_mass_over_105g(tmp_path) -> None:
    payload = {
        "foods": [
            _macro_food(1, "Widget, raw", "Foundation", calories=500, protein_g=50, fat_g=40, carbs_g=40)
            # 50 + 40 + 40 = 130g of macronutrients in 100g of food.
        ]
    }
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("widget")

    assert match is None


def test_plausibility_gate_allows_low_calorie_low_macro_food_via_absolute_escape(tmp_path) -> None:
    # Vinegar: genuinely low-calorie with near-zero protein/carbs/fat, so its
    # Atwater estimate is near zero too -- the ratio check alone would reject
    # it (dividing by ~0), but the absolute <=25 kcal escape lets it through.
    payload = {
        "foods": [
            _macro_food(1, "Vinegar, cider", "SR Legacy", calories=18, protein_g=0, fat_g=0, carbs_g=0.9)
            # Atwater estimate: 4*0.9 = 3.6 kcal. abs(18 - 3.6) = 14.4 <= 25.
        ]
    }
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("vinegar")

    assert match is not None
    assert match.macros.calories == 18


def test_plausibility_gate_falls_through_to_next_ranked_candidate(tmp_path) -> None:
    # An implausible top-ranked candidate doesn't ground the ingredient to
    # nothing if a lower-ranked candidate is both relevant and plausible.
    payload = {
        "foods": [
            _macro_food(1, "Widget, raw", "Foundation", calories=0, protein_g=0, fat_g=0, carbs_g=0),
            _macro_food(2, "Widget, raw", "SR Legacy", calories=50, protein_g=2, fat_g=1, carbs_g=10),
        ]
    }
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("widget")

    assert match is not None
    assert match.fdc_id == 2
    assert match.macros.calories == 50


# --- Undeclared-preparation handling: processed-state modifier blocklist
# (a gate, preparation=None only) and within-tier state preference
# (a tie-break, preparation=None only) ---


def test_undeclared_preparation_rejects_pickled_record(tmp_path) -> None:
    # The exact failure mode disclosed in _KNOWN_RESIDUALS for zucchini --
    # a bare "zucchini" query landing on a Branded "Zucchini, pickled"
    # record. Reproduced here with a synthetic payload so the fix is
    # provable independent of FDC's real zucchini/squash naming quirk.
    payload = {"foods": [_macro_food(1, "Zucchini, pickled", "Branded", calories=35, protein_g=1, fat_g=0, carbs_g=6)]}
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("zucchini")

    assert match is None


def test_undeclared_preparation_prefers_raw_over_cooked_at_same_tier(tmp_path) -> None:
    payload = {
        "foods": [
            _macro_food(1, "Widget, cooked", "SR Legacy", calories=50, protein_g=2, fat_g=1, carbs_g=8),
            _macro_food(2, "Widget, raw", "SR Legacy", calories=100, protein_g=4, fat_g=2, carbs_g=15),
        ]
    }
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("widget")

    assert match is not None
    assert match.fdc_id == 2
    assert match.description == "Widget, raw"


def test_undeclared_preparation_still_respects_data_type_priority_over_state(tmp_path) -> None:
    # State preference is a same-tier tie-break, never a rank override --
    # a higher-priority dataType (Foundation) wins over a lower-priority one
    # even if the lower-priority candidate is raw and the higher-priority
    # one is cooked.
    payload = {
        "foods": [
            _macro_food(1, "Widget, cooked", "Foundation", calories=50, protein_g=2, fat_g=1, carbs_g=8),
            _macro_food(2, "Widget, raw", "SR Legacy", calories=100, protein_g=4, fat_g=2, carbs_g=15),
        ]
    }
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("widget")

    assert match is not None
    assert match.fdc_id == 1
    assert match.description == "Widget, cooked"


def test_declared_preparation_disables_the_modifier_blocklist(tmp_path) -> None:
    # The processed-state modifier blocklist only applies when `preparation`
    # is undeclared -- a declared-canned search must still be free to match
    # a record whose non-head segment includes wording like "drained" that
    # the blocklist gate doesn't even consult here, because it's off
    # entirely once a preparation is declared.
    payload = {
        "foods": [_macro_food(1, "Beans, black, canned, drained", "SR Legacy", calories=90, protein_g=6, fat_g=0.5, carbs_g=16)]
    }
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("black beans", preparation="canned")

    assert match is not None
    assert match.description == "Beans, black, canned, drained"


def test_payload_cache_key_distinguishes_page_size(tmp_path) -> None:
    cache = FdcCache(tmp_path / "cache.json")
    cache.set_payload("widget", ["Branded"], 5, {"foods": ["five"]})
    cache.set_payload("widget", ["Branded"], 25, {"foods": ["twenty-five"]})

    assert cache.get_payload("widget", ["Branded"], 5) == {"foods": ["five"]}
    assert cache.get_payload("widget", ["Branded"], 25) == {"foods": ["twenty-five"]}
    assert cache.get_payload("widget", ["Branded"], 10) is None


# --- _FDC_QUERY_ALIASES: FDC-vocabulary aliases for a normalized query ---


@pytest.mark.parametrize("original,alias", sorted(_FDC_QUERY_ALIASES.items()))
def test_alias_invariant_original_tokens_are_a_subset_of_alias_tokens(original, alias) -> None:
    # The structural safety property: the queried food's own identity
    # token(s) must literally appear in the alias, so an alias can only
    # supply vocabulary FDC files the SAME food under -- never bridge to a
    # different food (see _FDC_QUERY_ALIASES's module comment).
    assert _tokenize(original) <= _tokenize(alias)


def test_alias_search_query_is_sent_to_fdc_and_used_for_relevance(tmp_path) -> None:
    # "cumin" alone would never match "Spices, cumin seed" (head is
    # "Spices", not a cumin token) -- this only passes if the alias is used
    # for BOTH the string sent to FDC and the relevance/head-noun check.
    payload = {"foods": [_macro_food(170923, "Spices, cumin seed", "SR Legacy", calories=375, protein_g=18, fat_g=22, carbs_g=44)]}
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("cumin")

    assert session.last_params["query"] == "spices cumin seed"
    assert match is not None
    assert match.fdc_id == 170923
    assert match.query == "spices cumin seed"


def test_alias_is_keyed_by_the_normalized_query_not_free_form_text(tmp_path) -> None:
    # normalize_ingredient runs before the alias lookup -- a free-form
    # variant of an aliased ingredient still resolves through it.
    payload = {"foods": [_macro_food(170926, "Spices, ginger, ground", "SR Legacy", calories=335, protein_g=9, fat_g=5, carbs_g=71)]}
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("Fresh Ginger")

    assert match is not None
    assert match.fdc_id == 170926


# Pinned fixture tests (payload -> expected fdc_id) for the top 10
# `_FDC_QUERY_ALIASES` entries, live-verified against real FDC records
# during the phase 1.5/P4 curation pass (fdc_id/description/approximate
# calories are the real live values; protein/fat/carbs are plausible
# stand-ins sized to clear the plausibility gate, not necessarily FDC's
# exact reported values).
@pytest.mark.parametrize(
    ("original", "alias", "fdc_id", "description", "calories"),
    [
        ("coriander", "spices coriander seed", 170922, "Spices, coriander seed", 298),
        ("cumin", "spices cumin seed", 170923, "Spices, cumin seed", 375),
        ("oregano", "spices oregano dried", 171328, "Spices, oregano, dried", 265),
        ("nutmeg", "spices nutmeg ground", 171326, "Spices, nutmeg, ground", 525),
        ("paprika", "spices paprika", 171329, "Spices, paprika", 282),
        ("black pepper", "spices pepper black", 170931, "Spices, pepper, black", 251),
        ("ginger", "spices ginger ground", 170926, "Spices, ginger, ground", 335),
        ("garlic powder", "spices garlic powder", 171325, "Spices, garlic powder", 331),
        ("turmeric", "spices turmeric ground", 172231, "Spices, turmeric, ground", 312),
        ("cardamom", "spices cardamom", 170919, "Spices, cardamom", 311),
    ],
)
def test_pinned_alias_fixtures_resolve_to_the_real_fdc_record(
    tmp_path, original, alias, fdc_id, description, calories
) -> None:
    assert _FDC_QUERY_ALIASES[original] == alias

    payload = {"foods": [_macro_food(fdc_id, description, "SR Legacy", calories=calories, protein_g=10, fat_g=10, carbs_g=50)]}
    session = FakeSession(payload=payload)
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food(original)

    assert match is not None
    assert match.fdc_id == fdc_id
    assert match.description == description
    assert match.macros.calories == calories


def test_known_unreliable_query_still_excluded_even_though_not_aliased(tmp_path) -> None:
    # "chili powder" has no verified alias (see grounding_job._KNOWN_RESIDUALS)
    # and stays on _KNOWN_UNRELIABLE_QUERIES -- confirm it's not accidentally
    # present in _FDC_QUERY_ALIASES (which would be dead code, since the
    # exclusion check runs first and returns before the alias lookup).
    assert "chili powder" not in _FDC_QUERY_ALIASES
    assert "shrimp" not in _FDC_QUERY_ALIASES
    assert "tomato sauce" not in _FDC_QUERY_ALIASES


# --- Branded-tier selection: median-calorie agreement, not first-ranked ---


def _branded_food(fdc_id: int, calories: float, *, description: str = "Widget") -> dict:
    # Pure-fat macros (protein/carbs=0) so calories = 9*fat_g exactly --
    # trivially clears the plausibility gate's Atwater check for any
    # `calories` value used across these tests, regardless of magnitude.
    return _macro_food(fdc_id, description, "Branded", calories=calories, protein_g=0, fat_g=calories / 9, carbs_g=0)


def test_select_branded_match_returns_none_when_no_candidate_is_eligible() -> None:
    payload = {"foods": [{"fdcId": 1, "description": "Unrelated Thing", "dataType": "Branded", "foodNutrients": []}]}
    outcome = _select_branded_match(payload, "widget", None)
    assert outcome.match is None
    assert outcome.dispersion is None


def test_select_branded_match_picks_true_median_for_odd_candidate_count() -> None:
    payload = {"foods": [_branded_food(1, 100), _branded_food(2, 300), _branded_food(3, 200)]}
    outcome = _select_branded_match(payload, "widget", None)
    assert outcome.match is not None
    assert outcome.match.fdc_id == 3  # 200 is the true median of [100, 200, 300]
    assert outcome.match.macros.calories == 200
    assert outcome.dispersion is None


def test_select_branded_match_picks_lower_of_two_middle_for_even_candidate_count() -> None:
    payload = {"foods": [_branded_food(1, 100), _branded_food(2, 200), _branded_food(3, 250), _branded_food(4, 300)]}
    outcome = _select_branded_match(payload, "widget", None)
    assert outcome.match is not None
    # sorted calories: [100, 200, 250, 300] -- two middles are 200 and 250;
    # the LOWER of the two (200, fdc_id=2) is selected, not an average.
    assert outcome.match.fdc_id == 2
    assert outcome.match.macros.calories == 200


def test_select_branded_match_ties_broken_by_ascending_fdc_id() -> None:
    # Two candidates share the same (median) calorie value -- deterministic
    # tie-break picks the lower fdc_id, not payload order.
    payload = {
        "foods": [_branded_food(30, 200), _branded_food(10, 200), _branded_food(20, 100), _branded_food(40, 300)]
    }
    outcome = _select_branded_match(payload, "widget", None)
    assert outcome.match is not None
    assert outcome.match.fdc_id == 10  # lower of the two fdc_ids tied at the median calorie value


def test_select_branded_match_rejects_high_dispersion_with_three_plus_candidates() -> None:
    # max/min = 500/100 = 5.0x > 3.0x -- disagreement is too large to trust
    # any single candidate; ungrounded with the range recorded for the report.
    payload = {"foods": [_branded_food(1, 100), _branded_food(2, 200), _branded_food(3, 500)]}
    outcome = _select_branded_match(payload, "widget", None)
    assert outcome.match is None
    assert outcome.dispersion == (100, 500, 3)
    assert "branded_high_dispersion" in outcome.rejections


def test_select_branded_match_allows_high_dispersion_with_fewer_than_three_candidates() -> None:
    # Same 5x ratio, but only 2 candidates -- the >=3 threshold means this
    # isn't treated as a corroborated disagreement, just picks the median
    # (lower of the two, per the even-count rule).
    payload = {"foods": [_branded_food(1, 100), _branded_food(2, 500)]}
    outcome = _select_branded_match(payload, "widget", None)
    assert outcome.match is not None
    assert outcome.match.fdc_id == 1
    assert outcome.dispersion is None


def test_select_branded_match_allows_within_bound_dispersion() -> None:
    # max/min = 250/100 = 2.5x <= 3.0x -- within bound, proceeds to median
    # selection instead of rejecting.
    payload = {"foods": [_branded_food(1, 100), _branded_food(2, 150), _branded_food(3, 250)]}
    outcome = _select_branded_match(payload, "widget", None)
    assert outcome.match is not None
    assert outcome.match.fdc_id == 2
    assert outcome.dispersion is None


def test_branded_tier_fetch_uses_page_size_25(tmp_path) -> None:
    session = FakeSession(payload={"foods": []})
    client = _client(session=session, cache=FdcCache(tmp_path / "cache.json"))

    client.search_food("nonexistent widget xyz")

    # Two calls: generic tier, then Branded fallback -- the Branded one must
    # request pageSize=25.
    assert session.calls == 2
    assert session.last_params["pageSize"] == 25
    assert session.last_params["dataType"] == ["Branded"]


def test_branded_dispersion_event_recorded_on_client_end_to_end(tmp_path) -> None:
    # TieredFakeSession (not plain FakeSession) so the generic tier
    # genuinely returns nothing, forcing the Branded fallback -- a plain
    # FakeSession would serve the same dispersed payload to BOTH tiers and
    # let the generic-tier `_best_match` (which doesn't restrict by
    # dataType) resolve it first-ranked before ever reaching the Branded
    # selection logic under test.
    branded_payload = {"foods": [_branded_food(1, 100), _branded_food(2, 200), _branded_food(3, 500)]}
    session = TieredFakeSession(
        {
            ("Foundation", "SR Legacy", "Survey (FNDDS)"): {"foods": []},
            ("Branded",): branded_payload,
        }
    )
    client = UsdaClient(settings=_settings(fdc_api_key="test-key"), session=session, cache=FdcCache(tmp_path / "cache.json"))

    match = client.search_food("widget")

    assert match is None
    assert client.branded_dispersion_events == [("widget", 100, 500, 3)]
