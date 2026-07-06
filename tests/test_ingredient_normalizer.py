"""Regression tests for ingredient-name normalization.

`cleanup_ingredient_name` feeds `normalize_ingredient`, which in turn feeds
allergen matching in `constraint_engine`. The unit-stripping vocabulary is now
sourced from the shared `KNOWN_UNITS` set (single source with the quantity
parser), which is wider than the old hardcoded regex. These tests pin down the
invariant that makes that safe: a unit token is only ever removed when it is a
real quantity (attached to a number) — never a letter or a word that happens to
live inside a food name.
"""

import pytest

from app.utils.ingredient_normalizer import cleanup_ingredient_name, normalize_ingredient
from app.utils.quantity_parser import KNOWN_UNITS


def test_keeps_leading_l_in_lamb() -> None:
    # The leading "l" is a letter inside a word, not a litre unit.
    assert cleanup_ingredient_name("lamb") == "lamb"
    assert normalize_ingredient("lamb") == "lamb"


def test_keeps_vanilla_intact() -> None:
    assert cleanup_ingredient_name("vanilla") == "vanilla"
    assert normalize_ingredient("vanilla") == "vanilla"


@pytest.mark.parametrize(
    "name",
    [
        "special l",       # standalone "l" but no number -> not a quantity
        "pcorn",           # "pc" as a substring
        "caramel",         # "ml"/"l" as substrings
        "almond milk",     # "ml" spans the word boundary, "l" inside "milk"
        "cupcake",         # "cup" as a substring
        "lentil",          # "l" inside a word
        "pickle relish",   # "l"/"pc"-like substrings
        "falafel",
    ],
)
def test_unit_substring_inside_name_is_untouched(name: str) -> None:
    assert cleanup_ingredient_name(name) == name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2 l milk", "milk"),
        ("2l milk", "milk"),
        ("150 g chicken breast", "chicken breast"),
        ("1/2 cup rice", "rice"),
        ("250 ml heavy cream", "heavy cream"),
        ("3 tbsp olive oil", "olive oil"),
    ],
)
def test_leading_quantity_and_unit_is_stripped(raw: str, expected: str) -> None:
    assert cleanup_ingredient_name(raw) == expected


@pytest.mark.parametrize(
    "name",
    ["pound cake", "cheese slice", "ground clove", "cup custard", "piece of cake"],
)
def test_unit_word_not_adjacent_to_number_is_preserved(name: str) -> None:
    # These food names contain unit *words* with no number attached; stripping
    # them would corrupt the name (and, downstream, allergen matching at scale).
    assert cleanup_ingredient_name(name) == name


def test_strips_bare_leading_count() -> None:
    assert cleanup_ingredient_name("3 eggs") == "eggs"
    assert normalize_ingredient("3 eggs") == "egg"


@pytest.mark.parametrize("unit", sorted(KNOWN_UNITS))
def test_every_known_unit_only_strips_when_attached_to_a_number(unit: str) -> None:
    # Attached to a number -> removed as a quantity.
    assert cleanup_ingredient_name(f"2 {unit} milk") == "milk"
    # The same token as a standalone word (no number) -> preserved verbatim.
    assert cleanup_ingredient_name(f"{unit} bread") == f"{unit} bread"


def test_allergen_signal_survives_normalization() -> None:
    # Safety-adjacent: names carrying allergen tokens must not be hollowed out by
    # unit stripping, whether or not they contain unit-like substrings.
    assert "peanut" in normalize_ingredient("peanut butter")
    assert normalize_ingredient("peanut") == "peanut"
    # A quantity prefix is removed but the allergen name is fully retained.
    assert normalize_ingredient("15 g peanut butter") == normalize_ingredient("peanut butter")
