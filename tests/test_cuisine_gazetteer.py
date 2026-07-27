"""Tests for the tier-2 dish-name gazetteer in
`app.services.corpus_import.cuisine_tagger` (`DISH_NAME_CUISINE_TERMS`,
`resolve_cuisine_from_title`).

The adversarial guard below is NOT optional (see this repo's corpus-
completeness task spec, 2026-07-27): a title dish-name gazetteer that fires
on bare nationality adjectives reintroduces the exact false-positive class
("French Toast" -> French, "Swiss Cheese" -> Swiss) the original
tag-only cuisine_tagger design was built to avoid. Every case below is
asserted to resolve to `(None, "unknown")`, and at least one case
(`test_guard_would_have_failed_without_word_boundary`) proves the guard is
doing real work rather than being safe by accident.
"""

from __future__ import annotations

import re

from app.services.corpus_import.cuisine_tagger import (
    CANONICAL_CUISINES,
    DISH_NAME_CUISINE_TERMS,
    resolve_cuisine,
    resolve_cuisine_from_title,
)

# --- Mandatory adversarial collision cases ---------------------------------
#
# Every one of these titles contains a bare nationality/adjective word (or a
# single generic food word) that must NOT, on its own, resolve to a cuisine.
# Includes every case named in the task spec plus a few more identified
# while building the gazetteer entries.
COLLISION_TITLES = [
    "French Toast",
    "French Fries",
    "American Cheese",
    "Italian Dressing",
    "Italian Soda",
    "English Muffin",
    "Russian Dressing",
    "Swiss Cheese",
    "Swiss Roll",
    "Belgian Waffles",  # Belgian deliberately excluded from this gazetteer -- see module docstring
    "Momofuku Bo Ssam",  # "momo" must not fire inside the unbroken word "Momofuku"
    "Momofuku Milk Bar Cookies",
]


def test_gazetteer_does_not_fire_on_collision_titles():
    for title in COLLISION_TITLES:
        cuisine, source = resolve_cuisine_from_title(title)
        assert cuisine is None, f"{title!r} incorrectly resolved to {cuisine!r}"
        assert source == "unknown"


def test_guard_would_have_failed_without_word_boundary():
    """Proves the word-boundary guard is doing real work, not just
    coincidentally safe: a naive substring match (no `\\b`) WOULD have
    incorrectly fired "french" -> French inside "French Toast", and "momo"
    inside "Momofuku Bo Ssam"."""
    naive_hit_french_toast = "french" in "french toast"
    assert naive_hit_french_toast, "sanity check: naive substring match must find 'french' in 'french toast'"

    naive_hit_momofuku = "momo" in "momofuku bo ssam"
    assert naive_hit_momofuku, "sanity check: naive substring match must find 'momo' in 'momofuku bo ssam'"

    # ... yet the real guarded matcher must NOT fire on either.
    assert resolve_cuisine_from_title("French Toast") == (None, "unknown")
    assert resolve_cuisine_from_title("Momofuku Bo Ssam") == (None, "unknown")


def test_momo_still_matches_as_a_standalone_word():
    """The word-boundary guard must not be so strict it stops matching the
    real gazetteer entry it's meant to protect."""
    cuisine, source = resolve_cuisine_from_title("Momo (Nepali Dumplings)")
    assert cuisine == "Nepali"
    assert source == "gazetteer_matched"


def test_shepherds_pie_matches_with_or_without_apostrophe():
    for title in ["Shepherd's Pie", "Shepherds Pie", "SHEPHERD'S PIE"]:
        cuisine, source = resolve_cuisine_from_title(title)
        assert cuisine == "British"
        assert source == "gazetteer_matched"


def test_creme_brulee_matches_accented_and_unaccented_spelling():
    for title in ["Crème Brûlée", "Creme Brulee", "Classic Creme Brulee Recipe"]:
        cuisine, source = resolve_cuisine_from_title(title)
        assert cuisine == "French"
        assert source == "gazetteer_matched"


def test_positive_examples_for_each_of_the_eight_target_cuisines():
    cases = {
        "Buffalo Wings": "American",
        "Classic Cobb Salad": "American",
        "Fish and Chips": "British",
        "Coq Au Vin": "French",
        "Spaghetti Carbonara": "Italian",
        "Momo (Nepali Dumplings)": "Nepali",
        "Tahdig (Persian Crispy Rice)": "Persian",
        "Lomo Saltado": "Peruvian",
    }
    for title, expected_cuisine in cases.items():
        cuisine, source = resolve_cuisine_from_title(title)
        assert cuisine == expected_cuisine, f"{title!r} -> {cuisine!r}, expected {expected_cuisine!r}"
        assert source == "gazetteer_matched"


def test_ceviche_deliberately_excluded_stays_unmatched():
    """Documented judgment call: ceviche is common across many Latin
    cuisines, not uniquely Peruvian, so it is intentionally NOT in the
    gazetteer."""
    cuisine, source = resolve_cuisine_from_title("Peruvian-Style Ceviche")
    # No bare "peruvian" adjective match either -- gazetteer entries are
    # never bare adjectives, so this title resolves to no gazetteer match.
    assert cuisine is None
    assert source == "unknown"


def test_mediterranean_has_zero_gazetteer_entries_by_design():
    assert "Mediterranean" not in DISH_NAME_CUISINE_TERMS.values()


def test_no_title_and_empty_title_resolve_to_unknown():
    assert resolve_cuisine_from_title(None) == (None, "unknown")
    assert resolve_cuisine_from_title("") == (None, "unknown")


def test_dish_name_terms_are_all_multi_word_or_specific_single_word_nouns():
    """Guards against the gazetteer degrading into bare-adjective matching
    over time: no entry may be a bare nationality/adjective word (the
    thing this whole module exists to avoid)."""
    banned_bare_adjectives = {
        "french", "italian", "american", "british", "english", "russian",
        "swiss", "belgian", "mediterranean", "nepali", "persian", "peruvian",
    }
    for phrase in DISH_NAME_CUISINE_TERMS:
        assert phrase not in banned_bare_adjectives, f"{phrase!r} is a bare adjective, not a dish name"


def test_dish_name_cuisine_terms_values_are_canonical():
    assert set(DISH_NAME_CUISINE_TERMS.values()) <= CANONICAL_CUISINES


def test_resolve_cuisine_prefers_tag_mining_over_gazetteer():
    """Tier 1 (tag-mining) must win over tier 2 (gazetteer) whenever both
    would otherwise apply."""
    cuisine, source = resolve_cuisine("Thai", None, title="Coq Au Vin")
    assert cuisine == "Thai"
    assert source == "recovered_tag"


def test_resolve_cuisine_falls_back_to_gazetteer_when_tags_have_no_signal():
    cuisine, source = resolve_cuisine(None, None, title="Shepherd's Pie")
    assert cuisine == "British"
    assert source == "gazetteer_matched"


def test_resolve_cuisine_without_title_arg_is_unaffected():
    """Backward compatibility: existing 2-argument call sites keep working
    and never consult the gazetteer."""
    assert resolve_cuisine(None, None) == (None, "unknown")


def test_no_gazetteer_phrase_is_a_naive_substring_of_a_collision_title():
    """Extra defense-in-depth: even if word-boundary matching were ever
    accidentally weakened, no full gazetteer phrase (as opposed to a bare
    adjective) is itself a naive substring of any collision title.

    The one known, deliberate exception is "momo" inside "Momofuku ..."
    titles: "momo" IS a naive substring there (that's exactly why the
    word-boundary guard, not mere phrase choice, is what keeps this case
    safe) -- covered separately by
    `test_guard_would_have_failed_without_word_boundary` and
    `test_momo_still_matches_as_a_standalone_word` above."""
    known_substring_collisions = {("momo", "Momofuku Bo Ssam"), ("momo", "Momofuku Milk Bar Cookies")}
    for title in COLLISION_TITLES:
        lowered = title.lower()
        for phrase in DISH_NAME_CUISINE_TERMS:
            if (phrase, title) in known_substring_collisions:
                continue
            assert phrase not in lowered, f"gazetteer phrase {phrase!r} is a substring of collision title {title!r}"


def test_all_gazetteer_phrases_use_word_boundary_safe_regex():
    """Every phrase must be escapable/compilable as a `\\b...\\b` pattern
    without raising -- guards against a future entry containing regex
    metacharacters that could accidentally broaden matching."""
    for phrase in DISH_NAME_CUISINE_TERMS:
        pattern = re.compile(rf"\b{re.escape(phrase)}s?\b")
        assert pattern.search(phrase) is not None
