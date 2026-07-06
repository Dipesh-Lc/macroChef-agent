import pytest

from app.utils.unit_converter import convert, to_grams, unit_dimension


def test_mass_same_dimension_exact() -> None:
    assert convert(500, "g", "kg") == pytest.approx(0.5)
    assert convert(1, "lb", "oz") == pytest.approx(16, rel=1e-3)


def test_volume_same_dimension_exact() -> None:
    assert convert(1, "l", "ml") == pytest.approx(1000)
    assert convert(1, "tbsp", "tsp") == pytest.approx(3, rel=1e-3)


def test_cross_dimension_incomparable_returns_none() -> None:
    # cup (volume) <-> g (mass) needs a density; convert() never crosses dimensions.
    assert convert(1, "cup", "g") is None


def test_volume_to_grams_via_density() -> None:
    # 2 cups rice ~ 2 * 236.588 ml * 0.85 g/ml.
    grams = to_grams(2, "cups", name="rice")
    assert grams == pytest.approx(2 * 236.588 * 0.85, rel=1e-3)
    # Unknown-density ingredient in a volume unit stays incomparable.
    assert to_grams(1, "cup", name="dragonfruit") is None


def test_piece_to_grams_via_piece_weight() -> None:
    # Bare count with no unit resolves via per-piece weight (egg ~ 50 g).
    assert to_grams(2, None, name="eggs") == pytest.approx(100)
    assert to_grams(3, "clove", name="garlic") == pytest.approx(15)
    # Unknown piece weight -> None.
    assert to_grams(2, None, name="dragonfruit") is None


def test_unknown_unit_returns_none() -> None:
    assert to_grams(1, "smidge", name="salt") is None
    assert unit_dimension("smidge") is None
    assert to_grams(None, "g", name="rice") is None


def test_to_grams_matches_legacy_mass_table() -> None:
    # Values the interim nutrition_grounding table used, now sourced from the converter.
    assert to_grams(1, "kg") == pytest.approx(1000)
    assert to_grams(1, "oz") == pytest.approx(28.3495)
    assert to_grams(1, "lb") == pytest.approx(453.592)
    assert unit_dimension("mg") == "mass"
