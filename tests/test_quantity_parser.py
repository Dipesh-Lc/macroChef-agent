import re

import pytest

from app.utils.quantity_parser import canonical_unit, parse_quantity_string


def test_parses_mass_prefix() -> None:
    assert parse_quantity_string("150 g chicken breast") == {
        "name": "chicken breast",
        "amount": 150.0,
        "unit": "g",
    }


def test_parses_volume_prefix() -> None:
    parsed = parse_quantity_string("2 cups rice")
    assert parsed == {"name": "rice", "amount": 2.0, "unit": "cup"}


def test_parses_count_no_unit() -> None:
    # "medium" is a descriptor, not a unit — amount is the count, unit stays None.
    assert parse_quantity_string("1 medium egg") == {
        "name": "medium egg",
        "amount": 1.0,
        "unit": None,
    }


def test_parses_fraction() -> None:
    assert parse_quantity_string("1 1/2 tbsp olive oil") == {
        "name": "olive oil",
        "amount": 1.5,
        "unit": "tbsp",
    }
    assert parse_quantity_string("1/2 cup milk")["amount"] == 0.5


def test_bare_name_no_quantity() -> None:
    assert parse_quantity_string("chicken breast") == {
        "name": "chicken breast",
        "amount": None,
        "unit": None,
    }


def test_empty_and_garbage_fallback_to_name() -> None:
    assert parse_quantity_string("") == {"name": "", "amount": None, "unit": None}
    # No leading number -> whole string is the name.
    assert parse_quantity_string("a pinch of salt")["name"] == "a pinch of salt"
    # A bare quantity with no food still yields a non-empty name.
    assert parse_quantity_string("500 g")["name"]


# --- Glued unicode mixed fraction ("1½ cup ...") -----------------------------


def test_parses_glued_unicode_mixed_fraction() -> None:
    assert parse_quantity_string("1½ cup heavy whipping cream") == {
        "name": "heavy whipping cream",
        "amount": 1.5,
        "unit": "cup",
    }


def test_parses_spaced_unicode_mixed_fraction() -> None:
    assert parse_quantity_string("1 ½ cups sugar") == {
        "name": "sugar",
        "amount": 1.5,
        "unit": "cup",
    }


def test_bare_unicode_fraction_still_works() -> None:
    # Regression: a lone glyph (no leading whole number) must still parse.
    assert parse_quantity_string("½ cup milk") == {
        "name": "milk",
        "amount": 0.5,
        "unit": "cup",
    }


# --- Numeric range (dash) ----------------------------------------------------


def test_parses_en_dash_range_as_midpoint() -> None:
    assert parse_quantity_string("2–4 tbsp milk") == {
        "name": "milk",
        "amount": 3.0,
        "unit": "tbsp",
    }


def test_parses_ascii_hyphen_range_as_midpoint() -> None:
    assert parse_quantity_string("2-4 tbsp milk") == {
        "name": "milk",
        "amount": 3.0,
        "unit": "tbsp",
    }


def test_parses_em_dash_range_as_midpoint() -> None:
    assert parse_quantity_string("2—4 tbsp milk") == {
        "name": "milk",
        "amount": 3.0,
        "unit": "tbsp",
    }


def test_dash_inside_name_with_no_leading_amount_is_untouched() -> None:
    # No leading digit at all -> the whole string is the name, dash and all.
    # This proves the range fix doesn't over-consume a hyphenated food name.
    assert parse_quantity_string("sun-dried tomatoes") == {
        "name": "sun-dried tomatoes",
        "amount": None,
        "unit": None,
    }


# --- Safety invariant: fixes can only ever remove quantity/unit prefix chars,
# never a food word. See app/services/constraint_engine.py _recipe_safety_terms
# and the task's safety-path rationale for why this matters. ------------------

_INVARIANT_CASES = [
    "150 g chicken breast",
    "2 cups rice",
    "1 medium egg",
    "chicken breast",
    "1 1/2 tbsp olive oil",
    "1/2 cup milk",
    "500 g",
    "1½ cup heavy whipping cream",
    "1 ½ cups sugar",
    "½ cup milk",
    "2–4 tbsp milk",
    "2-4 tbsp milk",
    "2—4 tbsp milk",
    "1½ cup peanut butter",
    "sun-dried tomatoes",
    "a pinch of salt",
]


def _alpha_tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z]+", text.lower())


@pytest.mark.parametrize("raw", _INVARIANT_CASES)
def test_output_name_never_drops_a_food_word(raw: str) -> None:
    """The output `name`'s alphabetic tokens must be exactly the input's
    alphabetic tokens minus at most one recognized unit token. This is the
    property that makes the quantity-parser fix safe on the allergen-matching
    path: it can only ever remove digits/fraction glyphs/dashes/one unit word
    from the front, never delete a food word.
    """
    parsed = parse_quantity_string(raw)
    input_tokens = _alpha_tokens(raw)
    output_tokens = _alpha_tokens(parsed["name"])

    # Multiset difference (order-preserving, one-for-one) so a repeated word
    # in the input isn't miscounted as "removed" just because it also appears
    # once in the output.
    remaining = list(output_tokens)
    removed = []
    for tok in input_tokens:
        if tok in remaining:
            remaining.remove(tok)
        else:
            removed.append(tok)

    assert len(removed) <= 1, (
        f"input={raw!r} name={parsed['name']!r} removed too many tokens: {removed!r}"
    )
    if removed:
        unit = parsed["unit"]
        # The removed token is the raw unit spelling ("cups"); `unit` is its
        # canonical form ("cup"). Compare via canonical_unit so both spellings
        # of the same recognized unit token are accepted.
        assert unit is not None and canonical_unit(removed[0]) == unit, (
            f"input={raw!r} name={parsed['name']!r} removed a non-unit token: {removed!r}"
        )
