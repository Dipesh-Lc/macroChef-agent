import pytest

from app.utils.unit_converter import (
    _density,
    _normalize_for_density_lookup,
    _piece_weight,
    convert,
    to_grams,
    unit_dimension,
)


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


# --- New volume units (task A2): quart, pint, fluid ounce ---------------------


def test_quart_pint_floz_are_volume_dimension() -> None:
    assert unit_dimension("qt") == "volume"
    assert unit_dimension("pt") == "volume"
    assert unit_dimension("floz") == "volume"


def test_quart_pint_floz_convert_exactly_to_ml() -> None:
    assert convert(1, "qt", "ml") == pytest.approx(946.353)
    assert convert(1, "pt", "ml") == pytest.approx(473.176)
    assert convert(1, "floz", "ml") == pytest.approx(29.5735)
    # A US quart is exactly two pints and 32 fluid ounces.
    assert convert(1, "qt", "pt") == pytest.approx(2, rel=1e-3)
    assert convert(1, "qt", "floz") == pytest.approx(32, rel=1e-3)


def test_quart_pint_floz_to_grams_via_density() -> None:
    # water is density 1.0, so volume ml == grams.
    assert to_grams(1, "qt", name="water") == pytest.approx(946.353)
    assert to_grams(1, "pt", name="water") == pytest.approx(473.176)
    assert to_grams(1, "floz", name="water") == pytest.approx(29.5735)


# --- _normalize_for_density_lookup precedence (strict-first, then legacy) ----


def test_normalize_lookup_prefers_raw_exact_match_over_stripped_and_legacy() -> None:
    # "cooked rice" is an explicit table key -- it must win outright, at
    # position 0, before the handling-stripped or legacy variants are tried.
    candidates = _normalize_for_density_lookup("cooked rice")
    assert candidates[0] == "cooked rice"


def test_normalize_lookup_falls_back_to_handling_stripped_variant() -> None:
    # "chopped onion" has no exact table key, but stripping the handling word
    # "chopped" yields "onion", which does.
    candidates = _normalize_for_density_lookup("chopped onion")
    assert "chopped onion" in candidates
    assert "onion" in candidates
    assert candidates.index("chopped onion") < candidates.index("onion")


def test_normalize_lookup_falls_back_to_legacy_normalize_ingredient() -> None:
    # "scallions" has no raw or handling-stripped hit, but the legacy
    # normalize_ingredient() path maps it to "green onion" via SYNONYMS.
    candidates = _normalize_for_density_lookup("scallions")
    assert candidates[-1] == "green onion"


# --- Regression: "1 cup cooked rice" must use the cooked-rice density, not ---
# the uncooked one (legacy path stripped "cooked" as a DESCRIPTOR and hit the
# uncooked entry, ~15% too dense). Strict-first ordering fixes this because
# "cooked rice" is now an explicit exact-match table key. ---------------------


def test_cooked_rice_regression_does_not_use_uncooked_density() -> None:
    cooked = to_grams(1, "cup", name="cooked rice")
    uncooked = to_grams(1, "cup", name="rice")
    assert cooked == pytest.approx(236.588 * 0.67, rel=1e-3)
    assert uncooked == pytest.approx(236.588 * 0.85, rel=1e-3)
    assert cooked != pytest.approx(uncooked)


def test_cooked_white_rice_regression_does_not_use_uncooked_density() -> None:
    # Same bug class as above, natural-word-order variant: without an
    # explicit "cooked white rice" key, the legacy fallback strips "cooked"
    # as a DESCRIPTOR and maps "white rice" -> "rice", leaking to the
    # uncooked 0.85 density. See advisor A2-revision #2.
    assert _density("cooked white rice") == pytest.approx(0.67)
    assert _density("cooked white rice") != pytest.approx(0.85)


# --- Handling-word stripping (never composition/physical-form words) --------


def test_handling_words_stripped_for_density_lookup() -> None:
    # "melted"/"softened" are preparation words -- butter's density doesn't
    # change, so these should resolve to the plain "butter" entry.
    assert _density("melted butter") == pytest.approx(0.96)
    assert _density("softened butter") == pytest.approx(0.96)
    # "sifted" is a handling word too; normalize_ingredient() does NOT strip
    # it (it's not in DESCRIPTORS), so this only resolves via the new
    # handling-stripped tier, not the legacy fallback.
    assert _density("sifted flour") == pytest.approx(0.53)


def test_handling_words_stripped_for_piece_lookup() -> None:
    # normalize_ingredient() does not strip "chopped" either -- this only
    # resolves via the handling-stripped tier.
    assert _piece_weight("chopped onion") == pytest.approx(110.0)


def test_composition_words_are_never_stripped_guard() -> None:
    # "almond" is a composition word, not a handling word -- "almond flour"
    # must NOT collapse to plain "flour"'s density. No "almond flour" entry
    # exists, so this must stay unresolved (None), never guess.
    assert _density("almond flour") is None
    # "brown" is a composition word too -- "brown sugar" must resolve to its
    # own explicit, differently-sourced entry, not plain "sugar".
    assert _density("brown sugar") == pytest.approx(0.90)
    assert _density("brown sugar") != pytest.approx(_density("sugar"))


# --- Grated parmesan: regression on natural word order (advisor A2-revision
# #1). The table key was previously "parmesan grated", which no recipe
# actually writes -- "grated parmesan" / "grated parmesan cheese" (natural
# word order) both resolved to None. Both natural-order strings must now hit
# the table directly (raw exact-match tier), and the old inverted-order key
# is no longer expected to resolve (it was dead code). ------------------------


def test_grated_parmesan_natural_word_order_resolves() -> None:
    assert _density("grated parmesan") == pytest.approx(0.42)
    assert _density("grated parmesan cheese") == pytest.approx(0.42)


# --- New density table entries (task A2), spot-checked -----------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("butter", 0.96),
        ("brown sugar", 0.90),
        ("powdered sugar", 0.48),
        ("cooked rice", 0.67),
        ("cooked white rice", 0.67),
        ("oats", 0.38),
        ("cornstarch", 0.54),
        ("cocoa powder", 0.36),
        ("peanut butter", 1.09),
        ("maple syrup", 1.35),
        ("heavy cream", 1.01),
        ("sour cream", 0.97),
        ("grated parmesan", 0.42),
        ("grated parmesan cheese", 0.42),
        ("breadcrumbs", 0.46),
    ],
)
def test_new_density_entries_resolve(name: str, expected: float) -> None:
    assert _density(name) == pytest.approx(expected)


# --- New piece-weight table entries (task A2), spot-checked -------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("potato", 213.0),
        ("apple", 182.0),
        ("celery stalk", 40.0),
        ("cucumber", 301.0),
        ("zucchini", 196.0),
        ("green onion", 15.0),
        ("scallion", 15.0),  # legacy synonym path -> "green onion"
    ],
)
def test_new_piece_weight_entries_resolve(name: str, expected: float) -> None:
    assert _piece_weight(name) == pytest.approx(expected)


def test_shallot_has_no_piece_weight_entry() -> None:
    # Removed per advisor A2-revision #4b: USDA FoodData Central has no
    # whole-bulb shallot portion (only "1 tbsp chopped = 10 g", not a piece
    # weight), and no other citable whole-shallot reference is available
    # without web access -- cite-or-remove, so it's removed.
    assert _piece_weight("shallot") is None


# --- Regression: comma-stripping bug (grounding-coverage-common-staples fix).
# `_strip_handling_words` substituted handling words like "minced"/"chopped"
# with a space but never removed the resulting trailing comma, so e.g.
# "garlic, minced" normalized to "garlic," and never exact-matched the
# existing "garlic" piece-weight entry. Fixed by also converting commas/
# semicolons to spaces at the `stripped` candidate stage. Cases below are the
# four highest-volume comma'd ingredient strings from
# data/processed/grounding_report.md's top-50 ungrounded-ingredient table. ---


def test_comma_stripping_regression_garlic_minced() -> None:
    # The exact motivating example: "garlic, minced" previously normalized to
    # "garlic," (trailing comma) and failed to match the "garlic" clove
    # piece-weight entry.
    assert _piece_weight("garlic, minced") == pytest.approx(5.0)
    assert to_grams(1.0, "clove", name="garlic, minced") == pytest.approx(5.0)


def test_comma_stripping_regression_onion_chopped() -> None:
    assert _piece_weight("onion, chopped") == pytest.approx(110.0)
    assert to_grams(1.0, None, name="onion, chopped") == pytest.approx(110.0)


def test_comma_stripping_regression_butter_melted() -> None:
    assert _density("butter, melted") == pytest.approx(0.96)
    assert to_grams(1.0, "tbsp", name="butter, melted") == pytest.approx(14.7868 * 0.96, rel=1e-3)


def test_comma_stripping_regression_parsley_chopped_normalizes_but_still_unresolved() -> None:
    # The comma-stripping fix correctly normalizes "parsley, chopped" down to
    # "parsley" (proving the fix applies here too), but there is still no
    # "parsley" entry in `_DENSITY_G_PER_ML` -- adding one is out of scope for
    # this fix (no fresh FDC citation was looked up for it), so this stays
    # unresolved. Guards against silently regressing to a guessed density.
    assert "parsley" in _normalize_for_density_lookup("parsley, chopped")
    assert _density("parsley, chopped") is None
    assert to_grams(1.0, "tbsp", name="parsley, chopped") is None


# --- Additive literal keys for comma'd forms whose trailing handling word
# ("beaten"/"packed"/"grated") is deliberately NOT a _HANDLING_WORDS entry
# (they're composition/physical-form words per that set's own comment), so
# the comma-stripping fix alone can't resolve them -- they resolve via an
# explicit exact-match literal key added alongside the same-value base entry
# instead (grounding-coverage-common-staples fix). --------------------------


def test_eggs_beaten_additive_literal_key_resolves() -> None:
    assert _piece_weight("eggs, beaten") == pytest.approx(50.0)
    assert _piece_weight("egg, beaten") == pytest.approx(50.0)
    assert to_grams(2.0, None, name="eggs, beaten") == pytest.approx(100.0)


def test_brown_sugar_packed_additive_literal_key_resolves() -> None:
    assert _density("brown sugar, packed") == pytest.approx(0.90)


def test_parmesan_cheese_grated_additive_literal_key_resolves() -> None:
    assert _density("parmesan cheese, grated") == pytest.approx(0.42)


# --- New density entries for common tsp/tbsp-measured pantry spices
# (grounding-coverage-common-staples fix). Every value is a live USDA FDC
# "1 tsp" household-measure gram weight / 4.92892 (1 tsp in ml) -- see the
# citation comments in _DENSITY_G_PER_ML for the exact fdcId/food name. -----


@pytest.mark.parametrize(
    "name,expected",
    [
        ("salt", 1.22),
        ("black pepper", 0.47),
        ("cinnamon", 0.53),
        ("baking powder", 1.01),
        ("baking soda", 0.93),
        ("nutmeg", 0.45),
        ("paprika", 0.47),
        ("garlic powder", 0.63),
        ("oregano", 0.20),
        ("dry mustard", 0.41),
        ("bay leaf", 0.12),
    ],
)
def test_new_spice_density_entries_resolve(name: str, expected: float) -> None:
    assert _density(name) == pytest.approx(expected)
    # And a real tsp-measured to_grams call resolves (not None) for each.
    assert to_grams(1.0, "tsp", name=name) is not None


def test_cinnamon_ground_composes_fix1_and_fix3() -> None:
    # "cinnamon, ground" (116 occurrences per grounding_report.md's top-50
    # table) does NOT resolve via Fix 1's comma-stripping alone, because
    # "ground" is deliberately not a _HANDLING_WORDS entry (physical-form
    # word) -- it resolves via its own additive literal key instead, with
    # the same density as the plain "cinnamon" entry.
    assert _density("cinnamon, ground") == pytest.approx(_density("cinnamon"))
    assert to_grams(1.0, "tsp", name="cinnamon, ground") == pytest.approx(
        to_grams(1.0, "tsp", name="cinnamon")
    )


# --- New density entries (grams-computable coverage pass, 2026-07-27) -------
# Spot-checked sample of the new base density entries and their aliases.


@pytest.mark.parametrize(
    "name,expected",
    [
        ("onion", 0.68),
        ("celery", 0.43),
        ("garlic", 0.61),
        ("green pepper", 0.63),
        ("green bell pepper", 0.63),
        ("mushroom", 0.30),
        ("vanilla extract", 0.85),
        ("vanilla", 0.85),
        ("lemon juice", 1.03),
        ("lime juice", 1.04),
        ("orange juice", 1.05),
        ("margarine", 0.96),
        ("mayonnaise", 0.95),
        ("ketchup", 1.15),
        ("catsup", 1.15),
        ("molasses", 1.39),
        ("half-and-half", 1.02),
        ("evaporated milk", 1.06),
        ("cottage cheese", 0.96),
        ("buttermilk", 1.04),
        ("pecans", 0.42),
        ("walnuts", 0.51),
        ("almonds", 0.60),
        ("slivered almonds", 0.46),
        ("coconut", 0.39),
        ("raisins", 0.70),
        ("sesame seeds", 0.61),
        ("cornmeal", 0.58),
        ("corn syrup", 1.39),
        ("applesauce", 1.03),
        ("chocolate chips", 0.71),
        ("cream of tartar", 0.61),
        ("onion powder", 0.49),
        ("shortening", 0.87),
        ("ground ginger", 0.37),
        ("ground cumin", 0.43),
        ("turmeric", 0.45),
        ("ground cloves", 0.43),
        ("ground coriander", 0.41),
        ("cayenne pepper", 0.37),
        ("white pepper", 0.49),
        ("mustard", 1.01),
        ("shredded cheddar cheese", 0.48),
        ("vinegar", 1.01),
        ("chicken broth", 1.01),
    ],
)
def test_new_grams_coverage_density_entries_resolve(name: str, expected: float) -> None:
    assert _density(name) == pytest.approx(expected)


def test_new_density_aliases_reuse_existing_citation() -> None:
    # All-purpose/unbleached/plain flour are genuinely the same product as
    # the base "flour" entry -- same density, no new citation needed.
    assert _density("all-purpose flour") == pytest.approx(_density("flour"))
    assert _density("unbleached flour") == pytest.approx(_density("flour"))
    assert _density("plain flour") == pytest.approx(_density("flour"))
    # Granulated/white sugar are the base "sugar" entry under another name.
    assert _density("granulated sugar") == pytest.approx(_density("sugar"))
    assert _density("white sugar") == pytest.approx(_density("sugar"))
    # Confectioners'/icing sugar are "powdered sugar" under regional names.
    assert _density("confectioners' sugar") == pytest.approx(_density("powdered sugar"))
    assert _density("icing sugar") == pytest.approx(_density("powdered sugar"))
    # "cornflour" is the British name for cornstarch.
    assert _density("cornflour") == pytest.approx(_density("cornstarch"))
    # Temperature/handling literal-comma variants of plain water.
    assert _density("boiling water") == pytest.approx(_density("water"))
    assert _density("cold water") == pytest.approx(_density("water"))
    assert _density("water, cold") == pytest.approx(_density("water"))


def test_butter_or_margarine_artifact_strings_resolve() -> None:
    # Corpus parsing artifacts ("N butter or margarine" recipe lines) are
    # safe to resolve regardless of which ingredient was meant, since butter
    # and margarine share the same citation value in this table.
    assert _density("butter or 1/2 cup margarine") == pytest.approx(0.96)
    assert _density("butter or 2 tablespoons margarine") == pytest.approx(0.96)


# --- New piece-weight entries (grams-computable coverage pass, 2026-07-27) --


@pytest.mark.parametrize(
    "name,expected",
    [
        ("egg white", 33.0),
        ("egg whites", 33.0),
        ("egg yolk", 17.0),
        ("egg yolks", 17.0),
        ("orange", 131.0),
        ("mushroom", 18.0),
        ("chicken breast", 172.0),
        ("boneless skinless chicken breasts", 172.0),
        ("onions", 110.0),
        ("tomatoes", 123.0),
        ("potatoes", 213.0),
        ("carrots", 61.0),
        ("green onions", 15.0),
        ("scallions", 15.0),
        ("celery", 40.0),
        ("garlic cloves", 5.0),
        ("garlic clove", 5.0),
    ],
)
def test_new_grams_coverage_piece_weight_entries_resolve(name: str, expected: float) -> None:
    assert _piece_weight(name) == pytest.approx(expected)


def test_egg_white_and_yolk_distinct_from_whole_egg() -> None:
    # Egg white/yolk are genuinely different weights from a whole egg --
    # must NOT collapse to the "egg" 50 g entry.
    assert _piece_weight("egg white") != pytest.approx(_piece_weight("egg"))
    assert _piece_weight("egg yolk") != pytest.approx(_piece_weight("egg"))


def test_finely_is_a_handling_word_for_piece_and_density_lookup() -> None:
    # "finely" is a degree adverb on an already-handled verb ("finely
    # chopped"/"finely minced"), not a composition word -- adding it to
    # _HANDLING_WORDS lets these resolve via their existing base entries.
    assert _piece_weight("garlic, finely chopped") == pytest.approx(5.0)
    assert _piece_weight("onion, finely chopped") == pytest.approx(110.0)
    assert _piece_weight("celery, finely chopped") == pytest.approx(40.0)


def test_size_descriptor_comma_handling_word_onion_literal_keys_resolve() -> None:
    # "medium"/"large"/"small" + comma + handling word defeats both the
    # stripped tier (doesn't strip size descriptors) and the legacy fallback
    # (its cleanup doesn't strip commas before descriptor-removal runs) --
    # covered by explicit literal keys instead.
    assert to_grams(1.0, None, name="medium onion, chopped") == pytest.approx(110.0)
    assert to_grams(1.0, None, name="large onion, sliced") == pytest.approx(110.0)
    assert to_grams(1.0, None, name="small onion, diced") == pytest.approx(110.0)


def test_garlic_crushed_pressed_smashed_literal_keys_resolve() -> None:
    # "crushed"/"pressed"/"smashed" are deliberately NOT generic
    # _HANDLING_WORDS entries (they can denote a distinct product for other
    # ingredients, e.g. "crushed tomatoes") -- covered via literal keys
    # scoped to garlic specifically instead.
    assert _piece_weight("garlic, crushed") == pytest.approx(5.0)
    assert _piece_weight("crushed garlic") == pytest.approx(5.0)
    assert _piece_weight("garlic, pressed") == pytest.approx(5.0)
    assert _piece_weight("garlic cloves, smashed") == pytest.approx(5.0)


def test_onion_has_both_density_and_piece_weight_entries_no_conflict() -> None:
    # "onion" is a legitimate key in BOTH tables -- density for volume-
    # measured chopped onion ("1 cup chopped onion"), piece weight for a
    # whole-onion count ("1 onion"/"1 medium onion"). to_grams picks the
    # right table based on the row's actual unit dimension, so there's no
    # collision between the two citations.
    assert to_grams(1.0, "cup", name="onion") == pytest.approx(236.588 * 0.68, rel=1e-3)
    assert to_grams(1.0, None, name="onion") == pytest.approx(110.0)
