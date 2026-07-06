import json
from pathlib import Path

import pytest
import requests

from app.config import Settings
from app.services.nutrition_cache import FdcCache
from app.services.usda_client import UsdaClient

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
    client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    match = client.search_food("chicken breast")

    assert match is None


def test_non_200_response_returns_none_without_raising(tmp_path) -> None:
    session = FakeSession(payload={}, status_code=503)
    client = UsdaClient(
        settings=_settings(fdc_api_key="test-key"),
        session=session,
        cache=FdcCache(tmp_path / "cache.json"),
    )

    match = client.search_food("chicken breast")

    assert match is None


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
    assert unreachable_session.calls == 0
