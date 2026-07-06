"""Tests that verify MACROCHEF_ENABLE_VISION=false (the default) gates vision
entry points cleanly without returning mock/canned inventory data."""

import io

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings, parse_env_bool
from app.main import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


def test_extract_with_image_returns_403_when_vision_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /inventory/extract with an image must return 403 when vision is
    disabled, and the response body must never contain canned mock ingredients."""
    monkeypatch.setenv("MACROCHEF_ENABLE_VISION", "false")
    get_settings.cache_clear()

    fake_image = io.BytesIO(b"not-a-real-image")
    response = client.post(
        "/inventory/extract",
        data={"typed_ingredients": "rice"},
        files={"image": ("fridge.jpg", fake_image, "image/jpeg")},
    )

    assert response.status_code == 403
    detail = response.json().get("detail", "")
    assert "vision_disabled" in detail

    # Confirm the canned mock ingredient list was never returned
    body_str = response.text
    for canned in ("chicken breast", "spinach", "bell pepper", "Greek yogurt"):
        assert canned not in body_str


def test_extract_typed_only_works_when_vision_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /inventory/extract with only typed ingredients must work normally
    when vision is disabled — no image means no gate check."""
    monkeypatch.setenv("MACROCHEF_ENABLE_VISION", "false")
    get_settings.cache_clear()

    response = client.post(
        "/inventory/extract",
        data={"typed_ingredients": "chicken breast, rice, spinach"},
    )

    assert response.status_code == 200
    names = [item["normalized_name"] for item in response.json()]
    assert "chicken breast" in names
    assert "rice" in names


def test_extract_with_image_allowed_when_vision_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /inventory/extract with an image must not return 403 when vision is
    enabled (it runs mock extraction since MODEL_PROVIDER=mock in CI)."""
    monkeypatch.setenv("MACROCHEF_ENABLE_VISION", "true")
    get_settings.cache_clear()

    fake_image = io.BytesIO(b"not-a-real-image")
    response = client.post(
        "/inventory/extract",
        data={"typed_ingredients": ""},
        files={"image": ("generic_fridge.jpg", fake_image, "image/jpeg")},
    )

    # With MODEL_PROVIDER=mock the mock extractor runs — we get ingredients back,
    # not a 403.
    assert response.status_code == 200
    names = [item["normalized_name"] for item in response.json()]
    assert len(names) > 0


# ---------------------------------------------------------------------------
# Graph (intake_node) tests
# ---------------------------------------------------------------------------


def test_intake_node_ignores_image_when_vision_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """intake_node must produce no vision observations (only typed) and record
    the skip in the debug trace when the flag is off."""
    monkeypatch.setenv("MACROCHEF_ENABLE_VISION", "false")
    get_settings.cache_clear()

    # Import after patching so settings are fresh
    from app.graph.nodes import intake_node
    from app.graph.state import MacroChefState

    state = MacroChefState(
        user_id="test_user",
        input_type="mixed",
        typed_ingredients="rice, spinach",
        image_path="fridge_photo.jpg",
    )

    result = intake_node(state)

    observations = result.get("raw_inventory_observations") or []
    sources = {obs.source for obs in observations}
    assert "vision" not in sources

    trace = " ".join(result.get("debug_trace") or [])
    assert "vision disabled" in trace.lower()


def test_intake_node_calls_vision_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """intake_node must include vision observations when the flag is on
    (mock extractor runs since MODEL_PROVIDER=mock)."""
    monkeypatch.setenv("MACROCHEF_ENABLE_VISION", "true")
    get_settings.cache_clear()

    from app.graph.nodes import intake_node
    from app.graph.state import MacroChefState

    state = MacroChefState(
        user_id="test_user",
        input_type="mixed",
        typed_ingredients="rice",
        image_path="vegetarian_pantry_upload.png",
    )

    result = intake_node(state)

    observations = result.get("raw_inventory_observations") or []
    sources = {obs.source for obs in observations}
    assert "vision" in sources


# ---------------------------------------------------------------------------
# parse_env_bool / backend agreement tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
        ("off", False),
        ("", False),
        (None, False),
    ],
)
def test_parse_env_bool_covers_all_canonical_values(
    raw: str | None, expected: bool
) -> None:
    """parse_env_bool must agree with pydantic-settings bool coercion for every
    canonical truthy/falsy string (and None/empty)."""
    assert parse_env_bool(raw) is expected


@pytest.mark.parametrize("truthy", ["true", "True", "1", "yes", "on"])
def test_parse_env_bool_agrees_with_backend_settings_for_truthy(
    monkeypatch: pytest.MonkeyPatch, truthy: str
) -> None:
    """For every string parse_env_bool says is True, the backend Settings must
    also produce enable_vision=True — no split-brain between frontend and API."""
    monkeypatch.setenv("MACROCHEF_ENABLE_VISION", truthy)
    get_settings.cache_clear()
    assert get_settings().enable_vision is True
    assert parse_env_bool(truthy) is True


@pytest.mark.parametrize("falsy", ["false", "False", "0", "no", "off"])
def test_parse_env_bool_agrees_with_backend_settings_for_falsy(
    monkeypatch: pytest.MonkeyPatch, falsy: str
) -> None:
    """For every string parse_env_bool says is False, the backend Settings must
    also produce enable_vision=False."""
    monkeypatch.setenv("MACROCHEF_ENABLE_VISION", falsy)
    get_settings.cache_clear()
    assert get_settings().enable_vision is False
    assert parse_env_bool(falsy) is False


def test_parse_env_bool_agrees_with_backend_settings_for_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty string must produce False on both sides (env_ignore_empty=True on
    the backend falls through to the field default of False)."""
    monkeypatch.setenv("MACROCHEF_ENABLE_VISION", "")
    get_settings.cache_clear()
    assert get_settings().enable_vision is False
    assert parse_env_bool("") is False
