"""Deterministic substitution engine (Phase 3 roadmap item: "deterministic
substitution engine").

====================================================================
SAFETY ARCHITECTURE -- READ BEFORE EDITING THIS FILE
====================================================================
This module has **no safety authority**. It only ever proposes a candidate
recipe *variant* -- one ingredient swapped for another, equal measure. The
existing, UNMODIFIED `app.services.constraint_engine.validate_recipe` --
the exact same function `app.graph.nodes.safety_filter_node` already calls
in production -- is the SOLE gate deciding whether a variant is safe to
serve. See `generate_safe_variants` below: every candidate variant has its
`allergens` field RE-DERIVED FROM SCRATCH (never inherited from the parent
recipe -- see `_build_variant_recipe`'s docstring for why an inherited
value would be a silent, fail-*closed*-but-broken trap) and is re-validated
against the user's FULL profile (every allergy, `diet_type`, and dislike --
not just the one constraint the substitution targets) before it is ever
returned.

A wrong or stale entry in `SUBSTITUTION_EDGES` below can therefore only
ever cause a MISSED rescue (over-cautious, still safe) -- never an unsafe
recipe being served -- as long as this file is never changed to skip or
shortcut that re-validation. Do not add a parallel/independent allergy
check anywhere in this module. Do not trust `SubstitutionEdge.resolves` as
proof of safety: it only selects which swaps are worth TRYING. Every
edge's `resolves`/`known_allergens` claim is itself mechanically checked
against `app.services.constraint_engine.derive_allergen_labels`/
`violates_diet_type` by the parametrized curation-invariant test in
`tests/test_substitution_service.py` -- see that test before adding or
editing an edge.

LLM boundary: everything in this module is deterministic. The
`Recipe.substitution_note` a variant carries is a templated string built
from already-decided data -- never phrased or decided by an LLM. No LLM
call sits downstream of this module (the former `chef_explanation_node`
LLM re-phrasing step, and its `app/graph/prompts.py`, were removed) --
choosing, inventing, or validating a swap remains exclusively this
module's `generate_safe_variants` + `constraint_engine.validate_recipe`.

====================================================================
A note on curation, for future editors
====================================================================
Several substitutions that look obviously correct on paper (e.g. "sour
cream -> Greek yogurt", "milk -> oat milk", "regular pasta -> gluten-free
pasta", "soy sauce -> tamari", "egg -> flax egg") turned out to be
IMPOSSIBLE to honestly curate against the CURRENT `constraint_engine.py`
vocabulary, and are deliberately not present below:

  - `ALLERGEN_ALIASES["dairy"]` contains the BARE terms "milk"/"cream"/
    "butter" (by design -- an unqualified ingredient row can't prove it's
    the dairy-free variant, see that file's own comments). This means
    "oat milk", "coconut cream", and "coconut milk" ALL substring-match
    "milk"/"cream" and are themselves (wrongly, for these specific foods)
    flagged dairy -- so they can never pass `validate_recipe` for a
    dairy-allergic/vegan user, no matter what this file claims.
  - `ALLERGEN_ALIASES["gluten"]` contains the bare term "pasta"; any name
    ending in "...pasta" (including "gluten-free pasta") re-matches it.
  - The `SYNONYMS` table (`app.utils.ingredient_normalizer`) maps both
    "tamari" and "gluten free tamari" to "soy sauce" (an intentional,
    documented fail-closed policy -- see `_WHEAT`'s comment in
    `constraint_engine.py`), so tamari can never clear a gluten check
    under any name.
  - "flax egg" contains the literal substring "egg" and self-triggers the
    egg allergen it exists to avoid.
  - "coconut cream"/"coconut milk"/"coconut aminos"/etc. also pick up a
    (real, if arguably over-cautious) tree-nut flag, because the literal
    ALLERGEN_ALIASES key "nut" substring-matches inside "coconut" -- see
    docs/BACKLOG.md.

None of this is a bug introduced here -- it is pre-existing, tested
production behavior of a file this task is not authorized to touch (see
its module comments for the citations behind each choice). Every edge
below was instead individually verified (`derive_allergen_labels` /
`violates_diet_type`, both read-only, both already exercised by
`tests/test_constraint_engine.py`) to confirm the claimed `resolves` keys
actually hold for the ORIGINAL and are actually absent for the SUBSTITUTE
under the live vocabulary, and vocabulary-clean substitute names were
chosen instead of the naive ones where the naive name would have failed.
See docs/BACKLOG.md for the deferred fix (a `_LOOKALIKE_EXCLUSIONS`-style
carve-out for compound "X milk"/"X cream"/"X pasta" terms) and for the
specific edges this excludes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.ingredient import Ingredient
from app.schemas.nutrition import FoodMacros
from app.schemas.recipe import Recipe
from app.schemas.user import UserProfile
from app.services.constraint_engine import (
    _any_term_matches,  # deliberately reused directly, see module docstring + section 5 of the task spec
    derive_allergen_labels,
    validate_recipe,
)
from app.utils.ingredient_normalizer import normalize_ingredient
from app.utils.unit_converter import to_grams


@dataclass(frozen=True)
class SubstitutionEdge:
    """One hand-curated, cited substitution rule.

    `original_terms`: normalized ingredient-name term(s) this edge applies
    to (matched via the SAME one-directional substring rule
    `constraint_engine._any_term_matches`/`_recipe_contains_any_term`
    already use for safety -- see `_matching_edges` below).

    `substitute_name`: canonical, ALLERGEN-TRANSPARENT name for the
    replacement ingredient -- never a brand name that would hide the
    substitute's own real allergen content from substring matching (e.g.
    "sunflower seed butter", not "SunButter").

    `resolves`: the constraint keys (allergen keys from
    `constraint_engine.ALLERGEN_ALIASES`, and/or diet keys `violates_diet_
    type` recognizes: "vegan", "vegetarian", "dairy-free", "gluten-free")
    this edge is DESIGNED to clear. This is metadata for display/edge
    SELECTION only -- see this module's docstring: it is never trusted as
    proof of safety. The mandatory curation-invariant test in
    `tests/test_substitution_service.py` checks every key here actually
    holds.

    `known_allergens`: the substitute's OWN full allergen footprint, as
    literally returned by `derive_allergen_labels([substitute_name])` --
    declared explicitly (not implicit), and mechanically checked to match
    by the same test. A substitute may legitimately show an allergen key
    here that has nothing to do with what this edge resolves (e.g.
    "sunflower seed butter" picks up a "dairy"/"milk" false-positive
    purely because it contains the bare word "butter" -- see this module's
    docstring) -- that is honestly disclosed here, not hidden.

    `citation`: the culinary/nutritional equivalence rationale + source,
    including any known limitation (cooking-only, baking-only, ratio
    approximation, ...).
    """

    original_terms: frozenset[str]
    substitute_name: str
    resolves: frozenset[str]
    known_allergens: frozenset[str]
    citation: str


# ---------------------------------------------------------------------------
# Starting edge set (v1) -- do not go broader than this without re-running
# the verification in this file's module docstring for every new edge.
# ---------------------------------------------------------------------------

SUBSTITUTION_EDGES: tuple[SubstitutionEdge, ...] = (
    SubstitutionEdge(
        original_terms=frozenset({"milk"}),
        substitute_name="oat drink",
        resolves=frozenset({"dairy", "milk", "dairy-free", "vegan"}),
        known_allergens=frozenset(),
        citation=(
            "Cow's milk is a FALCPA/EU 1169/2011 Annex II major allergen. "
            "'Oat drink' is the EU-compliant naming for oat-based milk "
            "alternatives (EU Regulation 1308/2013 reserves 'milk' for "
            "animal products), deliberately used here instead of the more "
            "common US market name 'oat milk': 'oat milk' substring-matches "
            "the bare ALLERGEN_ALIASES['dairy'] term 'milk' and would be "
            "(wrongly) self-flagged dairy by this project's own matcher -- "
            "see this module's docstring. Equal-volume swap; oat drink is "
            "thinner than whole milk in baked goods but functionally "
            "interchangeable in most savory/beverage uses."
        ),
    ),
    SubstitutionEdge(
        original_terms=frozenset({"milk"}),
        substitute_name="soy drink",
        resolves=frozenset({"dairy", "milk", "dairy-free", "vegan"}),
        known_allergens=frozenset({"soy", "soya"}),
        citation=(
            "Cow's milk is a FALCPA/EU 1169/2011 Annex II major allergen; "
            "soy is a separate FALCPA/EU Annex II major allergen, correctly "
            "and honestly declared in `known_allergens` above (this edge "
            "resolves a MILK allergy, not a soy one -- see the cross-"
            "allergen-trap benchmark case for why `resolves` is never "
            "trusted as a full-profile guarantee). 'Soy drink' used instead "
            "of 'soy milk' for the same reason as the oat-drink edge above "
            "(the bare word 'milk' would self-flag dairy)."
        ),
    ),
    SubstitutionEdge(
        original_terms=frozenset({"butter"}),
        substitute_name="olive oil",
        resolves=frozenset({"dairy", "milk", "dairy-free", "vegan"}),
        known_allergens=frozenset(),
        citation=(
            "Butter is a dairy product (FALCPA/EU 1169/2011 Annex II milk "
            "allergen). Olive oil is a standard 1:1-by-volume substitute "
            "for butter in sauteing/cooking and most savory applications. "
            "KNOWN CULINARY LIMITATION, disclosed rather than overclaimed: "
            "this swap does NOT work for laminated pastry (croissants, pie "
            "crust) or creaming-method baking, where butter's solid-fat "
            "structure is load-bearing -- see docs/BACKLOG.md for "
            "context-sensitive substitution (deferred, not built in v1)."
        ),
    ),
    SubstitutionEdge(
        original_terms=frozenset({"peanut butter"}),
        substitute_name="sunflower seed butter",
        resolves=frozenset({"peanut", "peanuts"}),
        known_allergens=frozenset({"dairy", "milk"}),
        citation=(
            "Peanut is a FALCPA/EU 1169/2011 Annex II major allergen. "
            "Sunflower seed butter (e.g. SunButter, WowButter) is FARE "
            "(Food Allergy Research & Education)'s standard recommended "
            "peanut-free alternative for peanut-allergic households. The "
            "'dairy'/'milk' entry in `known_allergens` above is an honest, "
            "disclosed FALSE POSITIVE of this project's own matcher (the "
            "bare word 'butter' is an ALLERGEN_ALIASES['dairy'] term, see "
            "this module's docstring) -- sunflower seed butter contains no "
            "real dairy. This is over-cautious, not unsafe: a user with "
            "BOTH a peanut and a dairy allergy correctly has this variant "
            "rejected anyway (see the cross-allergen-trap benchmark case)."
        ),
    ),
    SubstitutionEdge(
        original_terms=frozenset({"soy sauce"}),
        substitute_name="coconut aminos",
        resolves=frozenset({"gluten", "wheat", "gluten-free"}),
        known_allergens=frozenset({"nut", "nuts"}),
        citation=(
            "Standard brewed soy sauce is wheat-fermented (a FALCPA/EU "
            "1169/2011 Annex II gluten source); this project's own "
            "constraint_engine.py deliberately treats a bare 'soy sauce' "
            "row as gluten-positive (fail-closed -- see _WHEAT's comment). "
            "Coconut aminos is a real, widely sold soy-sauce alternative "
            "made from coconut tree sap and salt -- naturally gluten-free "
            "AND soy-free (unlike tamari/liquid aminos, which remain "
            "soy-derived; this edge is deliberately NOT named 'tamari', "
            "see this module's docstring for why tamari cannot clear this "
            "system's gluten check under any name, and NOT named 'liquid "
            "aminos', which -- while gluten-free -- IS genuinely soy-"
            "derived and this system's vocabulary has no term that would "
            "catch that for a soy-allergic user, which would be a real, "
            "undetected hazard for that different allergy). The 'nut'/"
            "'nuts' entry in `known_allergens` is a disclosed, honest "
            "(if over-cautious) flag from the bare literal substring "
            "'nut' inside 'coconut' -- see this module's docstring."
        ),
    ),
    SubstitutionEdge(
        original_terms=frozenset({"pasta"}),
        substitute_name="rice noodles",
        resolves=frozenset({"gluten", "wheat", "gluten-free"}),
        known_allergens=frozenset(),
        citation=(
            "Wheat pasta is a FALCPA/EU 1169/2011 Annex II gluten source. "
            "Rice noodles are a standard, widely available gluten-free "
            "1:1 pasta substitute. Deliberately not named 'gluten-free "
            "pasta' or 'rice pasta' -- both substring-match the bare "
            "ALLERGEN_ALIASES['wheat'] term 'pasta' and would self-flag "
            "gluten under this system's vocabulary, see this module's "
            "docstring."
        ),
    ),
    SubstitutionEdge(
        original_terms=frozenset({"egg"}),
        substitute_name="ground flaxseed",
        resolves=frozenset({"egg", "eggs", "vegan"}),
        known_allergens=frozenset(),
        citation=(
            "Egg is a FALCPA/EU 1169/2011 Annex II major allergen and is "
            "vegan-excluded (The Vegan Society's definition of veganism). "
            "Ground flaxseed ('flax egg') is a standard baking substitute "
            "for egg as a binder. KNOWN LIMITATIONS, disclosed rather than "
            "overclaimed: (1) baking-context only -- this does not work "
            "for applications relying on egg's structure/leavening in "
            "non-baked preparations (meringue, custard, egg wash); (2) the "
            "real-world ratio is 1 tbsp ground flaxseed + 3 tbsp water per "
            "egg, not an equal-measure swap -- this v1 engine applies the "
            "equal-measure assumption anyway (see docs/BACKLOG.md, "
            "ratio-aware swaps deferred). Deliberately named 'ground "
            "flaxseed', not 'flax egg': the latter contains the literal "
            "substring 'egg' and would self-flag the very allergen it "
            "exists to avoid -- see this module's docstring."
        ),
    ),
    SubstitutionEdge(
        original_terms=frozenset({"gelatin"}),
        substitute_name="agar agar",
        resolves=frozenset({"fish", "seafood", "vegetarian", "vegan"}),
        known_allergens=frozenset(),
        citation=(
            "This project's constraint_engine.py deliberately treats a "
            "bare 'gelatin' row as both a fish allergen (fail-closed: "
            "kosher gelatin is frequently fish-derived, FARE lists "
            "gelatin as a hidden fish source) and as non-vegetarian/non-"
            "vegan (Vegetarian Resource Group's Vegetarian FAQ names "
            "gelatin as a common hidden non-vegetarian ingredient; "
            "standard gelatin is always animal-derived, full stop -- "
            "there is no vegetarian gelatin under that name). Agar agar "
            "is a seaweed-derived gelling agent, the standard vegan/"
            "vegetarian substitute for gelatin. KNOWN LIMITATION: the "
            "true substitution ratio is roughly 1 tsp agar powder per 1 "
            "tbsp gelatin (agar gels more strongly by volume) -- this v1 "
            "engine's equal-measure assumption over-doses agar relative "
            "to a hand-tuned recipe (firmer-than-intended gel, not a "
            "safety concern)."
        ),
    ),
    SubstitutionEdge(
        original_terms=frozenset({"honey"}),
        substitute_name="maple syrup",
        resolves=frozenset({"vegan"}),
        known_allergens=frozenset(),
        citation=(
            "Honey is an animal product and is vegan-excluded (The Vegan "
            "Society's definition of veganism explicitly names honey; "
            "honey is NOT vegetarian-excluded under mainstream definitions, "
            "consistent with this project's own DIET_TYPE_EXCLUDED_TERMS, "
            "which only adds HONEY_ALIASES to the vegan set, not the "
            "vegetarian one). Maple syrup is a standard 1:1-by-volume "
            "vegan liquid-sweetener substitute for honey."
        ),
    ),
    SubstitutionEdge(
        original_terms=frozenset({"chicken broth", "chicken stock"}),
        substitute_name="vegetable broth",
        resolves=frozenset({"vegetarian", "vegan"}),
        known_allergens=frozenset(),
        citation=(
            "Chicken broth/stock is poultry-derived and vegetarian-"
            "excluded under mainstream vegetarian/vegan definitions (the "
            "same 'chicken' term this project's own MEAT_ALIASES already "
            "treats as a vegetarian-exclusion signal). Vegetable broth is "
            "a standard 1:1-by-volume substitute in soups, braises, and "
            "sauces. Scoped to the two compound phrases 'chicken broth'/"
            "'chicken stock' rather than the bare word 'chicken', so this "
            "edge never fires on an actual chicken CUT (e.g. 'chicken "
            "breast') and proposes a nonsensical meat-for-broth swap."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Pre-ground per-100g macros (curation-time only -- see this module's
# docstring / the task spec section 4: "you MAY pre-ground each substitute's
# per-100g macros once ... rather than hitting the network live in the
# recommend path". Nothing in this module ever calls UsdaClient/hits the
# network -- this is a small, hand-curated, cited lookup, in the same spirit
# as app.utils.unit_converter's _DENSITY_G_PER_ML / _PIECE_WEIGHT_G tables
# (which this module also reads from, via `to_grams`, for the SAME density/
# piece-weight entries -- see `compute_macro_delta`'s trust gate below).
#
# Keyed by the exact string passed as `name=` to `to_grams` for that side of
# the swap (see `_representative_original_name`), lowercased -- both the
# representative original term and every `substitute_name` above have an
# entry here so `compute_macro_delta` can look either up directly, with no
# further normalization ambiguity.
#
# Every figure below is a hand-curated, approximate USDA FoodData Central
# per-100g value for a representative record of that food (design-time
# citation, matching this project's existing `unit_converter._DENSITY_G_PER_
# ML` citation style -- not a live API pull). Where no specific USDA record
# is cited, the figure is a typical, published manufacturer-label average
# for that product category.
# ---------------------------------------------------------------------------

_MACROS_PER_100G: dict[str, FoodMacros] = {
    # USDA FDC "Milk, whole, 3.25% milkfat"
    "milk": FoodMacros(calories=61.0, protein_g=3.15, carbs_g=4.8, fat_g=3.25, fiber_g=0.0),
    # Typical unsweetened oat-drink manufacturer label average
    "oat drink": FoodMacros(calories=43.0, protein_g=1.0, carbs_g=7.0, fat_g=1.3, fiber_g=0.8),
    # USDA FDC "Soymilk, unsweetened"
    "soy drink": FoodMacros(calories=54.0, protein_g=3.3, carbs_g=6.3, fat_g=1.8, fiber_g=0.6),
    # USDA FDC "Butter, salted"
    "butter": FoodMacros(calories=717.0, protein_g=0.85, carbs_g=0.06, fat_g=81.1, fiber_g=0.0),
    # USDA FDC "Oil, olive, salad or cooking"
    "olive oil": FoodMacros(calories=884.0, protein_g=0.0, carbs_g=0.0, fat_g=100.0, fiber_g=0.0),
    # USDA FDC "Peanut butter, smooth style, without salt"
    "peanut butter": FoodMacros(calories=588.0, protein_g=25.1, carbs_g=19.6, fat_g=50.4, fiber_g=6.0),
    # USDA FDC "Seeds, sunflower seed butter, without salt"
    "sunflower seed butter": FoodMacros(calories=617.0, protein_g=17.3, carbs_g=18.9, fat_g=55.2, fiber_g=6.1),
    # USDA FDC "Soy sauce made from soy and wheat (shoyu)"
    "soy sauce": FoodMacros(calories=53.0, protein_g=8.1, carbs_g=4.9, fat_g=0.6, fiber_g=0.8),
    # Typical coconut aminos manufacturer label average (e.g. Coconut Secret)
    "coconut aminos": FoodMacros(calories=45.0, protein_g=2.0, carbs_g=9.0, fat_g=0.0, fiber_g=0.0),
    # USDA FDC "Pasta, dry, enriched"
    "pasta": FoodMacros(calories=371.0, protein_g=13.0, carbs_g=74.7, fat_g=1.5, fiber_g=3.2),
    # USDA FDC "Noodles, rice, dry"
    "rice noodles": FoodMacros(calories=364.0, protein_g=5.95, carbs_g=83.2, fat_g=0.56, fiber_g=1.6),
    # USDA FDC "Egg, whole, raw, fresh"
    "egg": FoodMacros(calories=143.0, protein_g=12.6, carbs_g=0.72, fat_g=9.5, fiber_g=0.0),
    # USDA FDC "Seeds, flaxseed"
    "ground flaxseed": FoodMacros(calories=534.0, protein_g=18.3, carbs_g=28.9, fat_g=42.2, fiber_g=27.3),
    # USDA FDC "Gelatins, dry powder, unsweetened"
    "gelatin": FoodMacros(calories=335.0, protein_g=85.6, carbs_g=0.0, fat_g=0.1, fiber_g=0.0),
    # USDA FDC "Seaweed, agar, dried"
    "agar agar": FoodMacros(calories=306.0, protein_g=6.2, carbs_g=80.9, fat_g=0.03, fiber_g=7.4),
    # USDA FDC "Honey"
    "honey": FoodMacros(calories=304.0, protein_g=0.3, carbs_g=82.4, fat_g=0.0, fiber_g=0.2),
    # USDA FDC "Syrups, maple"
    "maple syrup": FoodMacros(calories=260.0, protein_g=0.04, carbs_g=67.0, fat_g=0.06, fiber_g=0.0),
    # USDA FDC "Soup, stock, chicken, home-prepared" (thin broth, not condensed)
    "chicken broth": FoodMacros(calories=4.0, protein_g=0.6, carbs_g=0.2, fat_g=0.1, fiber_g=0.0),
    # USDA FDC "Soup, stock, vegetable, home-prepared"
    "vegetable broth": FoodMacros(calories=3.0, protein_g=0.3, carbs_g=0.4, fat_g=0.1, fiber_g=0.0),
}


@dataclass(frozen=True)
class MacroDelta:
    """Substitute-minus-original per-serving-equivalent macro delta for one
    swap, at the swapped ingredient's own amount/unit. Positive means the
    substitute contributes MORE of that macro than the original did."""

    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float


@dataclass(frozen=True)
class SubstitutionVariant:
    """One safety-validated candidate recipe produced by `generate_safe_
    variants`. `recipe` is the ONLY thing that flows into the candidate set
    (see `app.graph.nodes.substitution_node`) -- `edge`/`original_ingredient_
    name`/`macro_delta` here are for the caller's own bookkeeping/testing;
    the display note itself is already baked into `recipe.substitution_note`
    (see `_build_variant_recipe`) so it survives scoring/ranking without
    needing this wrapper."""

    recipe: Recipe
    edge: SubstitutionEdge
    original_ingredient_name: str
    macro_delta: MacroDelta | None


def _representative_original_name(edge: SubstitutionEdge) -> str:
    """A single, deterministic representative name for `edge.original_
    terms`, used only for the macro-delta lookup/`to_grams` density call
    (never for safety matching, which uses the full `original_terms` set --
    see `_matching_edges`). Sorted so this is stable regardless of set
    iteration order."""
    return sorted(edge.original_terms)[0]


def _scale_macros(macros: FoodMacros, grams: float) -> FoodMacros:
    scale = grams / 100.0
    return FoodMacros(
        calories=macros.calories * scale,
        protein_g=macros.protein_g * scale,
        carbs_g=macros.carbs_g * scale,
        fat_g=macros.fat_g * scale,
        fiber_g=macros.fiber_g * scale,
    )


def compute_macro_delta(ingredient: Ingredient, edge: SubstitutionEdge) -> MacroDelta | None:
    """Trust-gated macro-impact estimate for swapping `ingredient` per
    `edge`, at `ingredient`'s own amount/unit (equal-measure swap
    assumption -- see this module's docstring).

    Returns `None` ("macro impact: unknown") unless BOTH the original and
    the substitute (a) have a known per-100g macro record in `_MACROS_PER_
    100G` AND (b) `app.utils.unit_converter.to_grams` resolves a gram
    weight for the shared amount/unit -- mirroring `app.services.
    nutrition_view.trusted_per_serving`'s honesty discipline: `None` is a
    valid, common, expected outcome here, never a bug, and a numeric
    figure is never fabricated when either side can't be grounded. Never
    calls the live USDA API -- everything here reads the small, pre-
    ground `_MACROS_PER_100G` table above.
    """
    original_name = _representative_original_name(edge)
    original_100g = _MACROS_PER_100G.get(original_name)
    substitute_100g = _MACROS_PER_100G.get(edge.substitute_name)
    if original_100g is None or substitute_100g is None:
        return None

    original_grams = to_grams(ingredient.amount, ingredient.unit, name=original_name)
    substitute_grams = to_grams(ingredient.amount, ingredient.unit, name=edge.substitute_name)
    if original_grams is None or substitute_grams is None:
        return None

    original_scaled = _scale_macros(original_100g, original_grams)
    substitute_scaled = _scale_macros(substitute_100g, substitute_grams)
    return MacroDelta(
        calories=substitute_scaled.calories - original_scaled.calories,
        protein_g=substitute_scaled.protein_g - original_scaled.protein_g,
        carbs_g=substitute_scaled.carbs_g - original_scaled.carbs_g,
        fat_g=substitute_scaled.fat_g - original_scaled.fat_g,
        fiber_g=substitute_scaled.fiber_g - original_scaled.fiber_g,
    )


# ---------------------------------------------------------------------------
# Matching (section 5 of the task spec): reuse the safety matcher's own
# one-directional substring primitive, never re-derive it.
# ---------------------------------------------------------------------------


# Local, substitution-MATCHING-only narrowing -- never touches constraint_
# engine's own safety matcher, tables, or `_any_term_matches` itself. A
# small, explicit, hand-curated set of "X <term> Y" compounds that are a
# genuinely DIFFERENT food from the bare `original_terms` key they'd
# otherwise substring-match under `_any_term_matches`'s plain one-
# directional rule -- e.g. bare "butter" is a literal substring of "peanut
# butter"/"cocoa butter"/"apple butter"/"cashew butter"/"almond butter"/
# "sunflower seed butter", so without this exclusion the "butter" -> "olive
# oil" edge would ALSO fire on a "peanut butter" ingredient row (in
# addition to the intended "peanut butter" -> "sunflower seed butter"
# edge), proposing a nonsensical (if still SAFE) "peanut butter -> olive
# oil" swap. This is a quality/precision narrowing only: per this module's
# safety architecture, skipping a match can only ever cause a MISSED
# rescue, never an unsafe one. Deliberately small and hand-curated, not
# general "X or Y"/compound-name parsing -- see this module's docstring
# ("no fancier matching in v1") and docs/BACKLOG.md for the softer,
# NOT-excluded cases (e.g. "milk" matching "buttermilk") left for a future
# pass.
_EDGE_MATCH_EXCLUSIONS: dict[str, frozenset[str]] = {
    "butter": frozenset(
        {
            "peanut butter",
            "almond butter",
            "cashew butter",
            "cocoa butter",
            "apple butter",
            "sunflower seed butter",
            "sunflower butter",
        }
    ),
}


def _is_edge_excluded_for_ingredient(edge: SubstitutionEdge, normalized_ingredient_name: str) -> bool:
    for term in edge.original_terms:
        if any(excluded in normalized_ingredient_name for excluded in _EDGE_MATCH_EXCLUSIONS.get(term, ())):
            return True
    return False


def _matching_edges(normalized_ingredient_name: str) -> list[SubstitutionEdge]:
    """Edges whose `original_terms` apply to `normalized_ingredient_name`
    (already run through `app.utils.ingredient_normalizer.normalize_
    ingredient` by the caller -- see `generate_safe_variants`).

    Uses `constraint_engine._any_term_matches` directly, in the SAME
    call shape `derive_allergen_labels` uses it (`_any_term_matches
    (candidate_terms=<haystack>, terms=<needles>)`): the haystack is this
    one ingredient's normalized name, the needles are an edge's canonical
    `original_terms`. This is a one-directional substring test -- an edge
    term may match as a substring OF the ingredient name (e.g. "peanut
    butter" matches "creamy peanut butter, softened"), but a bare
    ingredient word never reverse-matches a longer compound edge term
    (e.g. a bare "butter" ingredient row never matches the edge keyed on
    "peanut butter") -- see `tests/test_substitution_service.py`. A match
    is then additionally checked against `_EDGE_MATCH_EXCLUSIONS` above (a
    narrower, MATCHING-only precision filter, independent of the safety
    matcher).
    """
    lowered = normalized_ingredient_name.lower()
    haystack = {lowered}
    return [
        edge
        for edge in SUBSTITUTION_EDGES
        if _any_term_matches(haystack, edge.original_terms) and not _is_edge_excluded_for_ingredient(edge, lowered)
    ]


# ---------------------------------------------------------------------------
# Deterministic, templated display note -- never LLM-authored (see this
# module's docstring's LLM-boundary paragraph).
# ---------------------------------------------------------------------------

_RESOLVES_DISPLAY_LABELS: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"peanut", "peanuts"}), "peanut-safe"),
    (frozenset({"tree nut", "nuts", "nut"}), "tree-nut-safe"),
    (frozenset({"dairy", "milk", "dairy-free"}), "dairy-free"),
    (frozenset({"gluten", "wheat", "gluten-free"}), "gluten-free"),
    (frozenset({"egg", "eggs"}), "egg-free"),
    (frozenset({"soy", "soya"}), "soy-free"),
    (frozenset({"fish", "seafood"}), "fish-free"),
    (frozenset({"shellfish", "crustacean"}), "shellfish-free"),
    (frozenset({"sesame"}), "sesame-free"),
    (frozenset({"vegan"}), "vegan"),
    (frozenset({"vegetarian"}), "vegetarian"),
)


def _resolves_display_tags(resolves: frozenset[str]) -> str:
    tags = [label for keys, label in _RESOLVES_DISPLAY_LABELS if keys & resolves]
    # dict.fromkeys de-dupes while preserving first-seen order (e.g. "dairy"
    # and "dairy-free" both map to "dairy-free" above).
    tags = list(dict.fromkeys(tags))
    return "/".join(tags) if tags else "ingredient swap"


def _format_macro_delta(delta: MacroDelta | None) -> str:
    if delta is None:
        return "macro impact: unknown"
    return (
        "macro impact: "
        f"{delta.calories:+.0f} kcal, {delta.protein_g:+.1f}g protein, "
        f"{delta.carbs_g:+.1f}g carbs, {delta.fat_g:+.1f}g fat, {delta.fiber_g:+.1f}g fiber"
    )


def _build_note(original_ingredient_name: str, edge: SubstitutionEdge, macro_delta: MacroDelta | None) -> str:
    tags = _resolves_display_tags(edge.resolves)
    return (
        f"Swapped {original_ingredient_name} -> {edge.substitute_name} ({tags}). "
        f"{_format_macro_delta(macro_delta)}."
    )


# ---------------------------------------------------------------------------
# The hard safety constraint (section 3 of the task spec).
# ---------------------------------------------------------------------------


def _build_variant_recipe(recipe: Recipe, ingredient_index: int, edge: SubstitutionEdge) -> Recipe:
    """Builds a candidate variant: `recipe` with ingredient `ingredient_
    index` swapped for `edge.substitute_name`, same `amount`/`unit` (equal-
    measure swap).

    SAFETY-CRITICAL: `allergens` is RE-DERIVED from the variant's own full
    (post-swap) ingredient name list via `derive_allergen_labels` --
    NEVER inherited from `recipe.allergens`. This is the load-bearing trap
    the task spec calls out by name: `constraint_engine._recipe_safety_
    terms` feeds `recipe.allergens` into its match haystack ALONGSIDE
    ingredient names, so an inherited, stale `allergens` list (computed for
    the PARENT's original ingredients) would make `validate_recipe`
    permanently reject every variant this module ever produces for an
    allergy this edge was never even trying to touch -- fails closed/safe,
    but silently breaks the whole feature. See `test_allergens_are_re_
    derived_not_inherited` in `tests/test_substitution_service.py`, which
    constructs a case where the stale-vs-fresh answers provably differ and
    asserts the fresh one is what is actually used.

    `nutrition` is explicitly cleared (`None`), not carried over: the
    parent's `RecipeNutrition` was computed for the pre-swap ingredient
    list and would misrepresent the variant's macros. This module's own
    swap-scoped `compute_macro_delta` is the authoritative macro signal for
    a variant, surfaced via `Recipe.substitution_note` instead.
    """
    original = recipe.ingredients[ingredient_index]
    swapped_ingredient = original.model_copy(update={"name": edge.substitute_name})
    new_ingredients = list(recipe.ingredients)
    new_ingredients[ingredient_index] = swapped_ingredient

    fresh_allergens = derive_allergen_labels([item.name for item in new_ingredients])
    macro_delta = compute_macro_delta(original, edge)
    note = _build_note(original.name, edge, macro_delta)

    variant_id = f"{recipe.recipe_id}::subst::{ingredient_index}::{_slugify(edge.substitute_name)}"
    return recipe.model_copy(
        update={
            "recipe_id": variant_id,
            "ingredients": new_ingredients,
            "allergens": fresh_allergens,
            "nutrition": None,
            "source_type": "substitution_variant",
            "substitution_note": note,
        }
    )


def _slugify(text: str) -> str:
    return "-".join(text.lower().split())


def generate_safe_variants(recipe: Recipe, user_profile: UserProfile) -> list[SubstitutionVariant]:
    """For every ingredient in `recipe`, tries every matching edge from
    `SUBSTITUTION_EDGES`, builds a candidate variant, and keeps ONLY the
    ones that pass `constraint_engine.validate_recipe` against `user_
    profile` -- the user's COMPLETE profile (every allergy, `diet_type`,
    and dislike), the exact same function/call shape `app.graph.nodes.
    safety_filter_node` already uses in production.

    NEVER trusts `edge.resolves` as proof of safety -- every matching edge
    is tried and independently re-validated; `resolves` only decided which
    swaps were worth attempting for THIS ingredient. A wrong/stale edge can
    therefore only ever produce zero variants for a case it should have
    rescued (over-cautious, safe), never an unsafe one -- see this module's
    docstring.
    """
    variants: list[SubstitutionVariant] = []
    seen_variant_ids: set[str] = set()

    for index, ingredient in enumerate(recipe.ingredients):
        normalized = normalize_ingredient(ingredient.name)
        if not normalized:
            continue
        for edge in _matching_edges(normalized):
            variant_recipe = _build_variant_recipe(recipe, index, edge)
            if variant_recipe.recipe_id in seen_variant_ids:
                continue

            result = validate_recipe(variant_recipe, user_profile)
            if not result.is_valid:
                continue

            seen_variant_ids.add(variant_recipe.recipe_id)
            macro_delta = compute_macro_delta(ingredient, edge)
            variants.append(
                SubstitutionVariant(
                    recipe=variant_recipe,
                    edge=edge,
                    original_ingredient_name=ingredient.name,
                    macro_delta=macro_delta,
                )
            )

    return variants
