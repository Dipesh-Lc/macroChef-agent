"""Fail-closed regression tests for `RecipeDiscoveryService`'s diet_type
handling.

Background: `_allowed()` used to recognize only
{vegetarian, vegan, dairy-free, gluten-free} and silently skipped diet
filtering entirely for anything else (e.g. "pescatarian", "kosher", a typo)
-- every mock candidate passed through unfiltered on that axis. The
adversarial safety benchmark's multi_015/multi_025/diet_040 cases (real
diet_type values: "pescatarian", "kosher") demonstrated this concretely: a
shellfish-allergic user asking for a "pescatarian" shrimp scampi, or a
kosher user asking for a seafood paella, were served the forbidden
ingredient through this exact surface. See docs/BACKLOG.md's "Unknown
diet_type fails OPEN in _violates_requested_diet" entry (companion bug,
fixed alongside this one in recipe_validation_service.py).

The fix: an unrecognized diet_type must now raise instead of silently
admitting everything, mirroring constraint_engine.violates_diet_type's own
fail-loud ValueError. `app.graph.library_nodes.discovery_node` already
catches any exception from `RecipeDiscoveryService.discover()` and converts
it into a `RecipeDiscoveryResponse` with zero candidates and a populated
`errors` list -- so at the graph/API level this shows up as "nothing
served", not a crash.
"""

import pytest

from app.schemas.library import RecipeDiscoveryRequest
from app.services.recipe_discovery_service import RecipeDiscoveryService


def test_pescatarian_diet_type_fails_closed_not_open() -> None:
    # Mirrors benchmark case multi_015: shellfish allergy + "pescatarian"
    # diet_type. Before the fix, `_allowed()` didn't recognize "pescatarian"
    # and skipped diet filtering entirely, admitting shrimp recipes.
    request = RecipeDiscoveryRequest(
        cuisines=["Italian"],
        diet_type="pescatarian",
        allergies=["shellfish"],
        count=5,
    )

    with pytest.raises(ValueError, match="pescatarian"):
        RecipeDiscoveryService().discover(request, "discovery_pescatarian_user")


def test_kosher_diet_type_fails_closed_not_open() -> None:
    # Mirrors benchmark case diet_040: "kosher" diet_type, no mechanism to
    # enforce it -- must reject rather than silently serve everything.
    request = RecipeDiscoveryRequest(cuisines=["Mexican"], diet_type="kosher", count=5)

    with pytest.raises(ValueError, match="kosher"):
        RecipeDiscoveryService().discover(request, "discovery_kosher_user")


def test_unknown_diet_type_typo_fails_closed() -> None:
    request = RecipeDiscoveryRequest(cuisines=["Italian"], diet_type="nut-free", count=3)

    with pytest.raises(ValueError, match="nut-free"):
        RecipeDiscoveryService().discover(request, "discovery_typo_user")


def test_high_protein_diet_type_is_not_mistaken_for_unrecognized() -> None:
    # "high-protein" is a real, supported diet_type -- enforced downstream by
    # RecipeValidationService (tag-based), not by this discovery-stage gate.
    # It must not trip the new fail-closed guard.
    request = RecipeDiscoveryRequest(cuisines=["Japanese"], diet_type="high-protein", count=3)

    candidates = RecipeDiscoveryService().discover(request, "discovery_high_protein_user")

    assert len(candidates) == 3


@pytest.mark.parametrize("alias", ["none", "omnivore", "no restriction"])
def test_no_restriction_diet_type_aliases_still_pass_through(alias: str) -> None:
    request = RecipeDiscoveryRequest(cuisines=["Italian"], diet_type=alias, count=2)

    candidates = RecipeDiscoveryService().discover(
        request, f"discovery_{alias.replace(' ', '_')}_user"
    )

    assert len(candidates) == 2


def test_vegan_diet_type_still_filters_correctly() -> None:
    # Regression: the four originally-supported diet types must keep
    # filtering exactly as before -- no over-blocking regression.
    request = RecipeDiscoveryRequest(cuisines=["Italian"], diet_type="vegan", count=3)

    candidates = RecipeDiscoveryService().discover(request, "discovery_vegan_user")

    assert candidates
    assert all("vegan" in candidate.diet_tags for candidate in candidates)


def test_dairy_free_diet_type_still_filters_correctly() -> None:
    request = RecipeDiscoveryRequest(cuisines=["Indian"], diet_type="dairy-free", count=3)

    candidates = RecipeDiscoveryService().discover(request, "discovery_dairy_free_user")

    assert candidates
    assert all(
        "dairy" not in [allergen.lower() for allergen in candidate.allergens]
        for candidate in candidates
    )
