"""Cuisine recovery from Food.com's own structured tag fields
(`recipeCategory`, `keywords`) in the scraped-archive JSON-LD.

See `app.services.corpus_import.adapters.FoodComScrapedArchiveAdapter` for
the adapter that calls `resolve_cuisine` below, and this project's
`CLAUDE.md` for why this is a deterministic lookup module, not an LLM call:
cuisine tagging here is a pure, versioned, auditable table match against
Food.com's own taxonomy -- never inferred by a model, and never a factor in
any allergy/diet safety decision.

Background (verified directly against the scraped archive -- ~20,155 files
across `data/scraped/foodcom*` directories, 2026-07-27): `recipeCategory` is
a single string, sometimes a "/"-joined dual value (e.g. "Lunch/Snacks",
"Lamb/Sheep", "Soy/Tofu"); `keywords` is a comma-delimited list of
Food.com's own site-taxonomy tags. Both fields are STRUCTURED source
taxonomy, not free text -- this module matches ONLY against tokens from
these two fields, never against `title`/`instructions` free text (matching
bare "French" in a title like "French Toast" would wrongly tag an American
breakfast dish as French cuisine -- a failure mode this module structurally
cannot hit, since it never reads title/instructions at all).

Specificity precedence: some recipes carry both a specific cuisine tag and
a generic continental/regional bucket tag in the same `keywords` value
(e.g. "German,European,Weeknight"). CUISINE_TERMS below deliberately never
includes generic buckets (European, Asian, American, African, South
American, Scandinavian, Southwestern U.S. -- none of which are options in
`web/src/lib/cuisines.ts`'s CUISINE_OPTIONS anyway) -- so a generic-only tag
set naturally resolves to no match (cuisine stays unset) with no extra
bookkeeping needed, and a tag set carrying both a specific and a generic
term always resolves via the specific one, since only the specific term is
in the lookup table at all.

CUISINE_TERMS only maps a token to a value that already exists in
CUISINE_OPTIONS -- this module never invents a new taxonomy value. Many
real, specific Food.com tags verified present in the archive (Cajun,
Creole, Tex Mex, Scottish, Welsh, Filipino, Cuban, Canadian, Scandinavian,
Southwestern U.S., and most of continental Europe outside what's listed
below: Czech, Hungarian, Austrian, Swedish, Belgian, Dutch, Russian,
Norwegian, Polish, Finnish, Swiss...) are consequently left UNMAPPED, not
force-fit onto the nearest canonical value. "Tex Mex" is deliberately not
folded into "Mexican" for the same reason -- it is a distinct, Americanized
style Food.com itself tags separately from "Mexican" (85 occurrences of
each in the archive), and CUISINE_OPTIONS has no "Tex-Mex" entry to map it
to. See the corpus-cuisine-recovery task report for the full audit.
"""

from __future__ import annotations

import re

# Canonical cuisine values this module is allowed to emit -- must exactly
# match web/src/lib/cuisines.ts's CUISINE_OPTIONS (the frontend's single
# source of truth for the cuisine taxonomy, as of 2026-07-27). Kept as a
# literal copy (no existing cross-language config-sharing mechanism in this
# repo) -- if CUISINE_OPTIONS changes, this needs a matching manual update,
# same idiom as adapters.py's `_MEAL_TYPES` literal set.
CANONICAL_CUISINES: frozenset[str] = frozenset(
    {
        "American",
        "British",
        "Caribbean",
        "Chinese",
        "Ethiopian",
        "French",
        "German",
        "Greek",
        "Indian",
        "Indonesian",
        "Italian",
        "Japanese",
        "Korean",
        "Lebanese",
        "Mediterranean",
        "Mexican",
        "Middle Eastern",
        "Moroccan",
        "Nepali",
        "Persian",
        "Peruvian",
        "Portuguese",
        "Spanish",
        "Thai",
        "Turkish",
        "Vietnamese",
    }
)

# Lowercase Food.com tag token -> canonical cuisine value. Only includes
# tokens VERIFIED present (recipeCategory or keywords) in the scraped
# archive whose meaning maps unambiguously to an existing CUISINE_OPTIONS
# value. "Southwest Asia (middle East)" is Food.com's own literal category
# label for Middle Eastern cuisine (its odd internal capitalization --
# lowercase "middle East" -- is exactly how it appears in the source data;
# matching is case-insensitive regardless).
CUISINE_TERMS: dict[str, str] = {
    "caribbean": "Caribbean",
    "chinese": "Chinese",
    "ethiopian": "Ethiopian",
    "german": "German",
    "greek": "Greek",
    "indian": "Indian",
    "indonesian": "Indonesian",
    "japanese": "Japanese",
    "korean": "Korean",
    "lebanese": "Lebanese",
    "mexican": "Mexican",
    "moroccan": "Moroccan",
    "portuguese": "Portuguese",
    "spanish": "Spanish",
    "thai": "Thai",
    "turkish": "Turkish",
    "vietnamese": "Vietnamese",
    "southwest asia (middle east)": "Middle Eastern",
}

assert set(CUISINE_TERMS.values()) <= CANONICAL_CUISINES, (
    "CUISINE_TERMS must only emit values already present in CANONICAL_CUISINES"
)

_SPLIT_RE = re.compile(r"[/,]")


def split_tag_field(value: str | None) -> list[str]:
    """Splits a Food.com tag field into individual candidate tokens.
    `keywords` is always comma-delimited; `recipeCategory` is usually a
    single token but is sometimes a "/"-joined dual value (e.g.
    "Lunch/Snacks"). Splitting on both delimiters for either field is safe:
    neither character was observed inside a single real tag value in the
    full scraped archive (verified 2026-07-27). Shared with
    `adapters.resolve_meal_type`, which reuses this same splitting rule for
    meal-type recovery."""
    if not value:
        return []
    return [part.strip() for part in _SPLIT_RE.split(value) if part.strip()]


def resolve_cuisine(recipe_category: str | None, keywords: str | None) -> tuple[str | None, str]:
    """Returns `(cuisine, cuisine_source)`. `cuisine_source` is one of
    "recovered_tag" (a CUISINE_TERMS token matched) or "unknown" (no
    match). Checks `recipe_category` tokens before `keywords` tokens
    (`recipeCategory` is Food.com's single canonical category field, so it
    takes precedence); within each field, the first token that matches
    CUISINE_TERMS wins. A generic-bucket-only tag set and a no-signal tag
    set both resolve to `(None, "unknown")` -- see this module's docstring
    for why that's correct rather than a gap."""
    for token in split_tag_field(recipe_category) + split_tag_field(keywords):
        mapped = CUISINE_TERMS.get(token.lower())
        if mapped:
            return mapped, "recovered_tag"
    return None, "unknown"
