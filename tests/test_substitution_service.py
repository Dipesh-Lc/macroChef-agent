"""Tests for the Phase 3 deterministic substitution engine
(app.services.substitution_service).

Structure mirrors tests/test_constraint_engine.py and, for the curation-
invariant test specifically, test_usda_client.py's `_FDC_QUERY_ALIASES`
invariant test (see that test's docstring for the precedent this one is the
direct mechanical analog of).
"""

import pytest

from app.graph.nodes import safety_filter_node, substitution_node
from app.graph.state import MacroChefState, ensure_state
from app.schemas.ingredient import Ingredient
from app.schemas.recipe import Recipe
from app.schemas.user import UserProfile
from app.services.constraint_engine import derive_allergen_labels, validate_recipe, violates_diet_type
from app.utils.ingredient_normalizer import normalize_ingredient
from app.services.substitution_service import (
    SUBSTITUTION_EDGES,
    SubstitutionEdge,
    _build_variant_recipe,
    _matching_edges,
    compute_macro_delta,
    generate_safe_variants,
)

# Diet keys `constraint_engine.violates_diet_type` recognizes -- everything
# else in SubstitutionEdge.resolves is treated as an ALLERGEN_ALIASES key,
# checked via derive_allergen_labels instead.
_DIET_KEYS = {"vegan", "vegetarian", "dairy-free", "gluten-free"}


def _profile(**kwargs) -> UserProfile:
    return UserProfile(user_id="u", **kwargs)


def _probe_recipe(ingredient_name: str) -> Recipe:
    """Minimal single-ingredient recipe, for probing violates_diet_type
    against one bare ingredient name -- same pattern as test_constraint_
    engine.py's `_recipe` helper."""
    return Recipe(
        recipe_id="probe",
        title="probe",
        ingredients=[Ingredient(name=ingredient_name, amount=1, unit="cup")],
    )


def _edge(substitute_name: str) -> SubstitutionEdge:
    return next(e for e in SUBSTITUTION_EDGES if e.substitute_name == substitute_name)


# ---------------------------------------------------------------------------
# Section 1: the mandatory curation-invariant test, one parametrized case per
# edge in SUBSTITUTION_EDGES.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "edge",
    SUBSTITUTION_EDGES,
    ids=[f"{sorted(e.original_terms)[0]}->{e.substitute_name}" for e in SUBSTITUTION_EDGES],
)
def test_curation_invariant(edge: SubstitutionEdge) -> None:
    for key in edge.resolves:
        if key in _DIET_KEYS:
            for original_term in edge.original_terms:
                assert violates_diet_type(_probe_recipe(original_term), key), (
                    f"{edge.substitute_name}: original term {original_term!r} does not "
                    f"actually violate diet_type {key!r} -- mis-curated resolves claim."
                )
            assert not violates_diet_type(_probe_recipe(edge.substitute_name), key), (
                f"{edge.substitute_name}: substitute still violates diet_type {key!r} -- "
                "mis-curated resolves claim."
            )
        else:
            for original_term in edge.original_terms:
                assert key in derive_allergen_labels([original_term]), (
                    f"{edge.substitute_name}: original term {original_term!r} does not "
                    f"actually carry allergen {key!r} -- mis-curated resolves claim."
                )
            assert key not in derive_allergen_labels([edge.substitute_name]), (
                f"{edge.substitute_name}: substitute still carries resolved allergen "
                f"{key!r} -- mis-curated resolves claim."
            )

    # 3: known_allergens is exactly what derive_allergen_labels says today --
    # if this drifts, the edge's own docstring/citation is stale and must be
    # re-verified against the live constraint_engine vocabulary.
    assert edge.known_allergens == frozenset(derive_allergen_labels([edge.substitute_name])), (
        f"{edge.substitute_name}: known_allergens {sorted(edge.known_allergens)} does not "
        f"match derive_allergen_labels {sorted(derive_allergen_labels([edge.substitute_name]))}"
    )

    # 4: citation is non-empty.
    assert edge.citation and edge.citation.strip()


def test_substitution_edges_table_is_non_empty() -> None:
    assert len(SUBSTITUTION_EDGES) >= 8


# ---------------------------------------------------------------------------
# Section 5: matching logic.
# ---------------------------------------------------------------------------


def test_edge_matches_messy_real_ingredient_string() -> None:
    edges = _matching_edges(normalize_ingredient("creamy peanut butter, softened"))
    assert "sunflower seed butter" in {e.substitute_name for e in edges}


def test_bare_word_does_not_reverse_match_a_compound_edge_key() -> None:
    # A bare "butter" ingredient must never match the edge keyed on the
    # compound term "peanut butter" (one-directional substring matching --
    # see constraint_engine._any_term_matches's own docstring).
    edges = _matching_edges(normalize_ingredient("butter"))
    substitute_names = {e.substitute_name for e in edges}
    assert "sunflower seed butter" not in substitute_names
    # It SHOULD, however, match the edge that is actually keyed on bare
    # "butter" itself.
    assert "olive oil" in substitute_names


def test_non_applicable_edge_produces_no_candidate() -> None:
    assert _matching_edges(normalize_ingredient("broccoli")) == []


# ---------------------------------------------------------------------------
# Section 3: the hard safety constraint.
# ---------------------------------------------------------------------------


def test_variant_with_allergen_clean_ingredient_list_passes_validation() -> None:
    parent = Recipe(
        recipe_id="r_peanut",
        title="Butterfingers",
        ingredients=[
            Ingredient(name="peanut butter", amount=1, unit="cup"),
            Ingredient(name="white corn syrup", amount=0.5, unit="cup"),
            Ingredient(name="sugar", amount=1, unit="cup"),
        ],
        allergens=derive_allergen_labels(["peanut butter", "white corn syrup", "sugar"]),
    )
    edge = _edge("sunflower seed butter")
    variant = _build_variant_recipe(parent, 0, edge)

    result = validate_recipe(variant, _profile(allergies=["peanut"]))
    assert result.is_valid


def test_variant_that_still_carries_a_real_allergen_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test double: a deliberately mis-curated edge whose substitute name
    genuinely contains the allergen it claims to remove. Proves the hard
    safety gate (validate_recipe) -- not this module's own bookkeeping --
    is what decides eligibility, so a bad edge can only ever fail to
    rescue, never serve something unsafe."""
    bad_edge = SubstitutionEdge(
        original_terms=frozenset({"peanut butter"}),
        substitute_name="peanut oil spread",  # deliberately still contains "peanut"
        resolves=frozenset({"peanut", "peanuts"}),
        known_allergens=frozenset(derive_allergen_labels(["peanut oil spread"])),
        citation="Test double only -- deliberately mis-curated, never a real edge.",
    )
    monkeypatch.setattr(
        "app.services.substitution_service.SUBSTITUTION_EDGES",
        (bad_edge,),
    )

    parent = Recipe(
        recipe_id="r_peanut2",
        title="Peanut Snack",
        ingredients=[Ingredient(name="peanut butter", amount=1, unit="cup")],
        allergens=derive_allergen_labels(["peanut butter"]),
    )
    variants = generate_safe_variants(parent, _profile(allergies=["peanut"]))
    assert variants == []


def test_allergens_are_re_derived_not_inherited() -> None:
    """Constructs a case where the parent's (correctly, for the PARENT)
    stale allergens field would give a DIFFERENT (wrong) answer than a
    fresh re-derivation off the variant's own post-swap ingredient list --
    and asserts the fresh one is what validate_recipe actually sees."""
    parent = Recipe(
        recipe_id="r_peanut3",
        title="Peanut Snack",
        ingredients=[
            Ingredient(name="peanut butter", amount=1, unit="cup"),
            Ingredient(name="rice cake", amount=1, unit="piece"),
        ],
        allergens=derive_allergen_labels(["peanut butter", "rice cake"]),
    )
    assert "peanut" in parent.allergens  # sanity: the parent's own field does carry it

    edge = _edge("sunflower seed butter")
    variant = _build_variant_recipe(parent, 0, edge)

    # Fresh derivation off the variant's OWN (post-swap) ingredients: no
    # more peanut butter, so no peanut label.
    assert "peanut" not in variant.allergens
    assert "peanuts" not in variant.allergens

    profile = _profile(allergies=["peanut"])
    # The real implementation (fresh allergens) correctly rescues this
    # recipe for a peanut-only allergy.
    assert validate_recipe(variant, profile).is_valid

    # Prove this matters: a variant that INHERITED the parent's stale
    # allergens field instead would still show "peanut" (even though the
    # actual ingredient list no longer contains it) and would be wrongly
    # rejected -- the exact missed-rescue trap this module's docstring
    # calls out. This is what `_build_variant_recipe` must never do.
    stale_variant = variant.model_copy(update={"allergens": parent.allergens})
    assert not validate_recipe(stale_variant, profile).is_valid


# ---------------------------------------------------------------------------
# Section 4: macro-delta trust gate.
# ---------------------------------------------------------------------------


def test_macro_delta_both_grounded_gives_a_real_number() -> None:
    # butter (density 0.96 g/ml) -> olive oil (density 0.91 g/ml): both are
    # present in app.utils.unit_converter's density table, so to_grams
    # resolves for both sides of a volume-unit swap.
    edge = _edge("olive oil")
    ingredient = Ingredient(name="butter", amount=1, unit="cup")
    delta = compute_macro_delta(ingredient, edge)
    assert delta is not None
    assert isinstance(delta.calories, float)
    # Olive oil (884 kcal/100g) is denser in calories than butter (717
    # kcal/100g) gram for gram, but butter has a higher gram density per
    # cup -- just assert the number is finite/sane, not a specific sign.
    assert -2000 < delta.calories < 2000


def test_macro_delta_either_ungrounded_gives_unknown_never_fabricated() -> None:
    # sunflower seed butter has no density/piece-weight entry in
    # app.utils.unit_converter -- to_grams cannot resolve it for a volume
    # unit, so the trust gate must return None, never a fabricated number.
    edge = _edge("sunflower seed butter")
    ingredient = Ingredient(name="peanut butter", amount=2, unit="tbsp")
    delta = compute_macro_delta(ingredient, edge)
    assert delta is None


def test_macro_delta_unresolvable_amount_gives_unknown() -> None:
    edge = _edge("olive oil")
    ingredient = Ingredient(name="butter", amount=None, unit=None)
    assert compute_macro_delta(ingredient, edge) is None


# ---------------------------------------------------------------------------
# Graph integration.
# ---------------------------------------------------------------------------


def _peanut_recipe() -> Recipe:
    return Recipe(
        recipe_id="r_peanut_graph",
        title="Butterfingers",
        ingredients=[
            Ingredient(name="peanut butter", amount=1, unit="cup"),
            Ingredient(name="white corn syrup", amount=0.5, unit="cup"),
            Ingredient(name="sugar", amount=1, unit="cup"),
        ],
        allergens=derive_allergen_labels(["peanut butter", "white corn syrup", "sugar"]),
    )


def test_graph_surfaces_safe_variant_when_rescue_exists() -> None:
    profile = _profile(allergies=["peanut"])
    state = MacroChefState(user_id="u", user_profile=profile, candidate_recipes=[_peanut_recipe()])

    state = ensure_state(safety_filter_node(state))
    assert state.candidate_recipes == []
    assert len(state.rejected_recipes) == 1

    state = ensure_state(substitution_node(state))
    assert len(state.candidate_recipes) == 1
    variant = state.candidate_recipes[0]
    assert variant.source_type == "substitution_variant"
    assert variant.substitution_note is not None
    assert "peanut" not in variant.substitution_note.lower() or "peanut-safe" in variant.substitution_note.lower()
    assert not any("peanut" in item.name.lower() for item in variant.ingredients)


def test_graph_surfaces_nothing_when_no_safe_substitution_exists() -> None:
    # peanut + dairy: the peanut-safe substitute (sunflower seed butter)
    # itself carries a real "dairy"/"milk" flag (see this module's
    # docstring), so full-profile re-validation correctly refuses to
    # rescue this recipe at all.
    profile = _profile(allergies=["peanut", "dairy"])
    state = MacroChefState(user_id="u", user_profile=profile, candidate_recipes=[_peanut_recipe()])

    state = ensure_state(safety_filter_node(state))
    state = ensure_state(substitution_node(state))
    assert state.candidate_recipes == []
