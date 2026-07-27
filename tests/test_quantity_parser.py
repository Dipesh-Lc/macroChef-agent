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


def test_decimal_range_still_parses_unchanged_after_fraction_range_fix() -> None:
    # Regression guard on the range branch extended to accept fraction
    # operands (2026-07-27): a genuinely correct existing plain-decimal range
    # must still parse exactly as before.
    assert parse_quantity_string("2-3 cups broth") == {
        "name": "broth",
        "amount": 2.5,
        "unit": "cup",
    }


def test_parses_fraction_range_as_midpoint() -> None:
    # 2026-07-27 fraction-range fix: "2/3-3/4 cup..." previously matched only
    # the bare "2/3" as amount, leaving "-3/4 cup brown sugar, packed" as an
    # unparseable, name-polluting fragment (confirmed 375 corpus rows).
    parsed = parse_quantity_string("2/3-3/4 cup brown sugar, packed")
    assert parsed["unit"] == "cup"
    assert parsed["name"] == "brown sugar, packed"
    assert parsed["amount"] == pytest.approx((2 / 3 + 3 / 4) / 2)


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
    "2/3-3/4 cup brown sugar, packed",
    "1 can black beans, drained and rinsed",
    "1 pinch salt",
    "2 dashes Tabasco sauce",
    "1 stalk celery, chopped",
    "1 head cabbage, shredded",
    "1 bunch fresh basil",
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


# --- New volume units (task A2): quart, pint, fluid ounce ---------------------


def test_canonical_unit_quart_aliases() -> None:
    for alias in ("quart", "quarts", "qt", "qts"):
        assert canonical_unit(alias) == "qt"


def test_canonical_unit_pint_aliases() -> None:
    for alias in ("pint", "pints", "pt", "pts"):
        assert canonical_unit(alias) == "pt"


def test_canonical_unit_fluid_ounce_aliases() -> None:
    for alias in ("fluid ounce", "fluid ounces", "fl oz", "fl oz.", "fl. oz.", "floz"):
        assert canonical_unit(alias) == "floz"


def test_canonical_unit_still_returns_none_for_unknown() -> None:
    assert canonical_unit("smidge") is None
    assert canonical_unit("fl") is None


# --- Two-token unit parsing ("1 fl oz milk", "2 fluid ounces water") ---------


def test_parses_two_token_fl_oz_unit() -> None:
    assert parse_quantity_string("1 fl oz milk") == {
        "name": "milk",
        "amount": 1.0,
        "unit": "floz",
    }


def test_parses_two_token_fluid_ounces_unit() -> None:
    assert parse_quantity_string("2 fluid ounces water") == {
        "name": "water",
        "amount": 2.0,
        "unit": "floz",
    }


def test_parses_single_token_quart_unit() -> None:
    # Regression guard: adding the two-token lookahead must not break the
    # ordinary single-token unit path.
    assert parse_quantity_string("1 qt strawberries") == {
        "name": "strawberries",
        "amount": 1.0,
        "unit": "qt",
    }


def test_two_token_lookahead_does_not_consume_ordinary_two_word_names() -> None:
    # "medium egg" is not a unit, so the two-token attempt must fail cleanly
    # and fall through to the pre-existing one-token behavior (no unit found).
    assert parse_quantity_string("1 medium egg") == {
        "name": "medium egg",
        "amount": 1.0,
        "unit": None,
    }
    # A single-token food name with nothing after it must still work (no
    # crash from the two-token regex requiring a second token).
    assert parse_quantity_string("1 egg") == {
        "name": "egg",
        "amount": 1.0,
        "unit": None,
    }


@pytest.mark.parametrize(
    "raw",
    [
        "1 fl oz milk",
        "2 fluid ounces water",
        "1 qt strawberries",
        "3 pints blueberries",
    ],
)
def test_new_unit_cases_also_satisfy_the_no_dropped_food_word_invariant(raw: str) -> None:
    """Extend the safety invariant coverage (see above) to the new units."""
    parsed = parse_quantity_string(raw)
    input_tokens = _alpha_tokens(raw)
    output_tokens = _alpha_tokens(parsed["name"])

    remaining = list(output_tokens)
    removed = []
    for tok in input_tokens:
        if tok in remaining:
            remaining.remove(tok)
        else:
            removed.append(tok)

    # A two-token unit ("fl oz", "fluid ounces") removes up to two tokens;
    # everything else removes at most one.
    assert len(removed) <= 2, (
        f"input={raw!r} name={parsed['name']!r} removed too many tokens: {removed!r}"
    )
    unit = parsed["unit"]
    if removed:
        assert unit is not None
        assert canonical_unit(" ".join(removed)) == unit or canonical_unit(removed[0]) == unit, (
            f"input={raw!r} name={parsed['name']!r} removed a non-unit token: {removed!r}"
        )


# --- "X to Y" word ranges (addendum): same midpoint convention as the dash
# range, spelled with the word "to". -------------------------------------------


def test_parses_word_range_with_fractions_as_midpoint() -> None:
    assert parse_quantity_string("1/2 to 3/4 cup milk") == {
        "name": "milk",
        "amount": 0.625,
        "unit": "cup",
    }


def test_parses_word_range_with_plain_integers() -> None:
    assert parse_quantity_string("1 to 2 eggs") == {
        "name": "eggs",
        "amount": 1.5,
        "unit": None,
    }


def test_parses_word_range_with_mixed_number_operand() -> None:
    assert parse_quantity_string("1 1/2 to 3 cups flour") == {
        "name": "flour",
        "amount": 2.25,
        "unit": "cup",
    }


def test_parses_word_range_case_insensitive() -> None:
    assert parse_quantity_string("1 TO 2 eggs")["amount"] == 1.5
    assert parse_quantity_string("1 To 2 eggs")["amount"] == 1.5


def test_word_that_starts_with_to_is_not_a_range_guard() -> None:
    # "1 tomato" must never be parsed as a range: "to" is not a standalone
    # word here, it's the start of "tomato".
    assert parse_quantity_string("1 tomato") == {
        "name": "tomato",
        "amount": 1.0,
        "unit": None,
    }
    # Likewise "2 toasted bread slices" -- "toasted" starts with "to" but
    # isn't the word "to", and there's no second amount after it either way.
    assert parse_quantity_string("2 toasted bread slices") == {
        "name": "toasted bread slices",
        "amount": 2.0,
        "unit": None,
    }


def test_to_followed_by_non_amount_is_not_a_range_guard() -> None:
    # A literal " to " that is NOT followed by a second valid amount must not
    # be consumed as a range -- it falls through to the ordinary single-
    # amount parse, leaving "to ..." as part of the (ugly but harmless) name,
    # matching pre-existing behavior for this pattern.
    parsed = parse_quantity_string("1 to go containers")
    assert parsed["amount"] == 1.0
    assert parsed["unit"] is None
    assert "go" in parsed["name"] and "containers" in parsed["name"]


_WORD_RANGE_INVARIANT_CASES = [
    "1/2 to 3/4 cup milk",
    "1 to 2 eggs",
    "1 1/2 to 3 cups flour",
    "1 TO 2 eggs",
]


@pytest.mark.parametrize("raw", _WORD_RANGE_INVARIANT_CASES)
def test_word_range_cases_also_satisfy_the_no_dropped_food_word_invariant(raw: str) -> None:
    """Extend the safety invariant coverage to the new "to" word-range form.

    The word "to" itself is consumed as part of the amount (it is never a
    food word), so it's allowed to disappear from the name in addition to at
    most one recognized unit token -- nothing else may ever be dropped.
    """
    parsed = parse_quantity_string(raw)
    input_tokens = _alpha_tokens(raw)
    output_tokens = _alpha_tokens(parsed["name"])

    remaining = list(output_tokens)
    removed = []
    for tok in input_tokens:
        if tok in remaining:
            remaining.remove(tok)
        else:
            removed.append(tok)

    assert removed.count("to") <= 1, (
        f"input={raw!r} name={parsed['name']!r} removed 'to' more than once: {removed!r}"
    )
    non_to_removed = [tok for tok in removed if tok != "to"]
    assert len(non_to_removed) <= 1, (
        f"input={raw!r} name={parsed['name']!r} removed too many tokens: {removed!r}"
    )
    if non_to_removed:
        unit = parsed["unit"]
        assert unit is not None and canonical_unit(non_to_removed[0]) == unit, (
            f"input={raw!r} name={parsed['name']!r} removed a non-unit token: {removed!r}"
        )


# --- Pack-size lines (addendum, optional): "1 (8 ounce) package cream cheese" -


def test_parses_pack_size_single_word_unit() -> None:
    assert parse_quantity_string("1 (8 ounce) package cream cheese") == {
        "name": "cream cheese",
        "amount": 8.0,
        "unit": "oz",
    }


def test_parses_pack_size_multiplies_n_by_m() -> None:
    assert parse_quantity_string("2 (14.5 ounce) cans diced tomatoes") == {
        "name": "diced tomatoes",
        "amount": 29.0,
        "unit": "oz",
    }


def test_parses_pack_size_two_word_unit() -> None:
    assert parse_quantity_string("1 (8 fl oz) bottle vanilla extract") == {
        "name": "vanilla extract",
        "amount": 8.0,
        "unit": "floz",
    }


@pytest.mark.parametrize(
    "container_word",
    ["package", "packages", "pkg", "can", "cans", "jar", "jars", "box",
     "boxes", "bag", "bags", "bottle", "bottles", "container", "containers"],
)
def test_pack_size_recognizes_every_container_word(container_word: str) -> None:
    parsed = parse_quantity_string(f"1 (8 oz) {container_word} flour")
    assert parsed == {"name": "flour", "amount": 8.0, "unit": "oz"}


def test_pack_size_container_word_matching_is_case_insensitive() -> None:
    # "Can"/"CAN"/"can" must all be recognized as the container word; the
    # captured food name keeps its original casing (only the container-word
    # match itself is case-insensitive).
    assert parse_quantity_string("1 (8 oz) Can beans") == {
        "name": "beans",
        "amount": 8.0,
        "unit": "oz",
    }
    assert parse_quantity_string("1 (8 OUNCE) PACKAGE Cream Cheese") == {
        "name": "Cream Cheese",
        "amount": 8.0,
        "unit": "oz",
    }


def test_pack_size_container_word_is_never_the_unit_when_a_parenthetical_size_is_present() -> None:
    # When a parenthetical size IS present ("1 (8 ounce) package..."), the
    # pack-size path always wins and the parenthetical unit ("oz") is what
    # surfaces as `unit` -- the container word itself is consumed as a
    # delimiter, never as the reported unit, regardless of it now also being
    # a recognized standalone count unit (see the next test).
    parsed = parse_quantity_string("1 (8 ounce) package cream cheese")
    assert parsed["unit"] == "oz"


def test_container_words_are_recognized_count_units_without_a_parenthetical_size() -> None:
    # 2026-07-27 (container-word name-pollution fix): reversed from the prior
    # "no can/package pseudo-units" rule. Historically a container word with
    # NO preceding parenthetical size (contrast the case above) wasn't
    # recognized as a unit at all, so it leaked into `name` and degraded
    # downstream USDA food-name matching (1,905 corpus rows measured). These
    # are now recognized count-only units -- deliberately never given a
    # gram/piece-weight conversion, so nutrition math for such an ingredient
    # stays honestly ungrounded exactly as before this change (see
    # COUNT_UNITS' inline comment in quantity_parser.py).
    from app.utils.quantity_parser import KNOWN_UNITS

    assert "package" in KNOWN_UNITS
    assert "can" in KNOWN_UNITS
    assert "jar" in KNOWN_UNITS
    assert parse_quantity_string("1 can black beans, drained and rinsed") == {
        "name": "black beans, drained and rinsed",
        "amount": 1.0,
        "unit": "can",
    }


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Parenthetical isn't a number -- not a pack size; ordinary parsing
        # takes over (pre-existing behavior for stray parens, unaffected).
        ("2 (large) eggs", {"name": "(large) eggs", "amount": 2.0, "unit": None}),
        # Missing container word -- falls through; "(8 ounce)" isn't a
        # recognized unit token either, so it stays in the name.
        ("1 (8 ounce) flour", {"name": "(8 ounce) flour", "amount": 1.0, "unit": None}),
        # Parenthetical unit unrecognized.
        ("1 (8 bogus) package flour", {"name": "(8 bogus) package flour", "amount": 1.0, "unit": None}),
        # No name left after the container word -- must not return an empty name.
        ("1 (8 ounce) package", {"name": "(8 ounce) package", "amount": 1.0, "unit": None}),
        # Ordinary line, no parens at all.
        ("150 g chicken breast", {"name": "chicken breast", "amount": 150.0, "unit": "g"}),
        ("1 tomato", {"name": "tomato", "amount": 1.0, "unit": None}),
    ],
)
def test_pack_size_falls_through_unchanged_when_pattern_does_not_fully_match(
    raw: str, expected: dict[str, object]
) -> None:
    """Any failure anywhere in the pack-size pattern must fall through to the
    ordinary parser, byte-for-byte, rather than guess.
    """
    from app.utils.quantity_parser import _parse_pack_size

    assert _parse_pack_size(raw) is None
    assert parse_quantity_string(raw) == expected


# --- Pack-size fraction-gap fix (2026-07-27, docs/BACKLOG.md residual item) --
# `_PACK_SIZE_RE`'s parenthetical-size group ("M") previously only accepted a
# plain decimal, so any fraction inside the parenthetical broke the whole
# pack-size match and the container word leaked into `name` instead.


def test_pack_size_parenthetical_accepts_mixed_number_fraction() -> None:
    # The exact real-corpus case from the backlog entry.
    assert parse_quantity_string(
        "1 (10 3/4 ounce) can condensed cream of asparagus soup"
    ) == {
        "name": "condensed cream of asparagus soup",
        "amount": 10.75,
        "unit": "oz",
    }


def test_pack_size_parenthetical_accepts_bare_fraction() -> None:
    assert parse_quantity_string("1 (5/8 ounce) package Swiss Miss diet cocoa mix") == {
        "name": "Swiss Miss diet cocoa mix",
        "amount": 0.625,
        "unit": "oz",
    }


def test_pack_size_parenthetical_accepts_mixed_number_with_multiplier() -> None:
    assert parse_quantity_string("2 (1 1/2 ounce) packages spaghetti sauce mix") == {
        "name": "spaghetti sauce mix",
        "amount": 3.0,
        "unit": "oz",
    }


def test_pack_size_parenthetical_plain_decimal_case_still_parses_unchanged() -> None:
    # Regression guard: the pre-existing plain-decimal parenthetical case
    # (no fraction involved) must parse exactly as before the fraction fix.
    assert parse_quantity_string("1 (8 ounce) package cream cheese") == {
        "name": "cream cheese",
        "amount": 8.0,
        "unit": "oz",
    }
    assert parse_quantity_string("2 (14.5 ounce) cans diced tomatoes") == {
        "name": "diced tomatoes",
        "amount": 29.0,
        "unit": "oz",
    }


# --- New count units (task 2, 2026-07-27): pinch, dash, stalk, head, bunch ---


def test_pinch_recognized_as_count_unit() -> None:
    assert parse_quantity_string("1 pinch salt") == {
        "name": "salt",
        "amount": 1.0,
        "unit": "pinch",
    }
    assert parse_quantity_string("2 pinches salt") == {
        "name": "salt",
        "amount": 2.0,
        "unit": "pinch",
    }


def test_dash_recognized_as_count_unit() -> None:
    assert parse_quantity_string("1 dash white pepper") == {
        "name": "white pepper",
        "amount": 1.0,
        "unit": "dash",
    }
    assert parse_quantity_string("2 dashes Tabasco sauce") == {
        "name": "Tabasco sauce",
        "amount": 2.0,
        "unit": "dash",
    }


def test_stalk_recognized_as_count_unit() -> None:
    assert parse_quantity_string("1 stalk celery, chopped") == {
        "name": "celery, chopped",
        "amount": 1.0,
        "unit": "stalk",
    }
    assert parse_quantity_string("2 stalks celery, sliced") == {
        "name": "celery, sliced",
        "amount": 2.0,
        "unit": "stalk",
    }


def test_head_recognized_as_count_unit() -> None:
    assert parse_quantity_string("1 head cabbage, shredded") == {
        "name": "cabbage, shredded",
        "amount": 1.0,
        "unit": "head",
    }
    assert parse_quantity_string("2 heads garlic") == {
        "name": "garlic",
        "amount": 2.0,
        "unit": "head",
    }


def test_bunch_recognized_as_count_unit() -> None:
    assert parse_quantity_string("1 bunch fresh basil") == {
        "name": "fresh basil",
        "amount": 1.0,
        "unit": "bunch",
    }
    assert parse_quantity_string("2 bunches collard greens") == {
        "name": "collard greens",
        "amount": 2.0,
        "unit": "bunch",
    }


def test_head_does_not_falsely_collide_with_head_cheese() -> None:
    # Lookalike check per this file's existing collision-exclusion pattern:
    # corpus-verified no "head cheese"/"garlic head"-shaped collision exists
    # in the current corpus, but the parser's own behavior on such an input
    # is still worth pinning down. "head cheese" here has no leading
    # digit/amount at all, so it is NOT touched by the new "head" unit
    # recognition (that only fires after a leading amount token) -- it falls
    # straight through to the bare-name path, unit=None, exactly like any
    # other no-quantity ingredient line.
    assert parse_quantity_string("head cheese, sliced") == {
        "name": "head cheese, sliced",
        "amount": None,
        "unit": None,
    }
    # With a leading amount, "head" IS consumed as the unit -- this is the
    # correct, intended behavior (a genuine count of heads-of-something), not
    # a collision: "1 head garlic" must parse as unit="head", not leak
    # "head" into the name.
    assert parse_quantity_string("1 head garlic") == {
        "name": "garlic",
        "amount": 1.0,
        "unit": "head",
    }
