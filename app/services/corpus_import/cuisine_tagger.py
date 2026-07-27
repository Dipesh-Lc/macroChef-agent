"""Cuisine recovery from Food.com's own structured tag fields
(`recipeCategory`, `keywords`), plus a small title dish-name gazetteer for
cuisines tag-mining structurally cannot reach.

See `app.services.corpus_import.adapters.FoodComScrapedArchiveAdapter` for
the adapter that calls `resolve_cuisine` below, and this project's
`CLAUDE.md` for why this is a deterministic lookup module, not an LLM call:
cuisine tagging here is a pure, versioned, auditable table match -- never
inferred by a model, and never a factor in any allergy/diet safety
decision.

Background (verified directly against the scraped archive -- ~20,155 files
across `data/scraped/foodcom*` directories, 2026-07-27): `recipeCategory` is
a single string, sometimes a "/"-joined dual value (e.g. "Lunch/Snacks",
"Lamb/Sheep", "Soy/Tofu"); `keywords` is a comma-delimited list of
Food.com's own site-taxonomy tags. Both fields are STRUCTURED source
taxonomy, not free text -- CUISINE_TERMS below (tier 1: `cuisine_source
="recovered_tag"`) matches ONLY against tokens from these two fields, never
against `title`/`instructions` free text (matching bare "French" in a title
like "French Toast" would wrongly tag an American breakfast dish as French
cuisine).

Tier 2 (2026-07-27, corpus-completeness pass): 8 already-canonical cuisines
-- American, British, French, Italian, Mediterranean, Nepali, Persian,
Peruvian -- have ZERO recovered examples from tag-mining, because Food.com's
own users only tag distinctive/exotic cuisines, never the assumed-default
one (nobody tags a recipe "American" on a US recipe site). Tag-mining
structurally cannot reach these classes no matter how thorough the token
table is. `DISH_NAME_CUISINE_TERMS` below is the deterministic way in: a
small, hand-curated table of SPECIFIC, MULTI-WORD, UNAMBIGUOUS dish-name
phrases (e.g. "pad thai", "coq au vin") matched against `title` only, via
`resolve_cuisine_from_title`. This is deliberately NOT the same mechanism as
CUISINE_TERMS above and is never allowed to degrade into it: every entry
must be a specific dish name, never a bare adjective or single common word
(a bare "French" would wrongly tag "French Toast"/"French Fries"; a bare
"Italian" would wrongly tag "Italian Dressing"/"Italian Soda"; a bare
"Swiss" would wrongly tag "Swiss Cheese"/"Swiss Roll" -- see
`tests/test_cuisine_gazetteer.py` for the mandatory adversarial guard
against exactly these collisions). Matches use the same word-boundary regex
idiom already established in
`app.services.corpus_import.title_ingredient_integrity._find_term_spans`
(whole-word/whole-phrase, optional trailing "s", never a naive substring
match) rather than inventing new matching mechanics. `cuisine_source` for a
gazetteer hit is the distinct value `"gazetteer_matched"`, not
`"recovered_tag"` -- a title dish-name match and a structured-taxonomy tag
match are different-strength evidence with different failure modes, and
keeping them distinguishable in the data matters for future auditing even
though both are equally non-negotiable, deterministic, LLM-free lookups.
Tier 2 only runs when tier 1 found nothing (tag-mining, being closer to the
source's own taxonomy, always takes precedence when both are present).

Specificity precedence (tier 1): some recipes carry both a specific cuisine
tag and a generic continental/regional bucket tag in the same `keywords`
value (e.g. "German,European,Weeknight"). CUISINE_TERMS below deliberately
never includes generic buckets (European, Asian, African, South American,
Scandinavian, Southwestern U.S. -- none of which are options in
`web/src/lib/cuisines.ts`'s CUISINE_OPTIONS anyway) -- so a generic-only tag
set naturally resolves to no match (cuisine stays unset) with no extra
bookkeeping needed, and a tag set carrying both a specific and a generic
term always resolves via the specific one, since only the specific term is
in the lookup table at all.

CUISINE_TERMS only maps a token to a value that already exists in
CUISINE_OPTIONS -- this module never invents a new taxonomy value. As of
2026-07-27, the human has approved adding 16 further real, specific
Food.com tags verified present in the archive (Cajun, Creole, Tex Mex,
Filipino, Cuban, Czech, Hungarian, Austrian, Swedish, Belgian, Dutch,
Russian, Norwegian, Polish, Finnish, Swiss) as new CUISINE_OPTIONS entries
(`web/src/lib/cuisines.ts`) -- see that file for the current full list.
Scottish, Welsh, Canadian, Scandinavian, and Southwestern U.S. remain
verified-present-but-unmapped (no CUISINE_OPTIONS entry approved for them
yet). "Tex Mex" is deliberately not folded into "Mexican" -- it is a
distinct, Americanized style Food.com itself tags separately from
"Mexican" (85 occurrences of each in the archive) -- it now maps to its own
"Tex-Mex" CUISINE_OPTIONS entry. See the corpus-cuisine-recovery task
report for the full audit.
"""

from __future__ import annotations

import re
import unicodedata

# Canonical cuisine values this module is allowed to emit -- must exactly
# match web/src/lib/cuisines.ts's CUISINE_OPTIONS (the frontend's single
# source of truth for the cuisine taxonomy, as of 2026-07-27). Kept as a
# literal copy (no existing cross-language config-sharing mechanism in this
# repo) -- if CUISINE_OPTIONS changes, this needs a matching manual update,
# same idiom as adapters.py's `_MEAL_TYPES` literal set.
CANONICAL_CUISINES: frozenset[str] = frozenset(
    {
        "American",
        "Austrian",
        "Belgian",
        "British",
        "Cajun",
        "Caribbean",
        "Chinese",
        "Creole",
        "Cuban",
        "Czech",
        "Dutch",
        "Ethiopian",
        "Filipino",
        "Finnish",
        "French",
        "German",
        "Greek",
        "Hungarian",
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
        "Norwegian",
        "Persian",
        "Peruvian",
        "Polish",
        "Portuguese",
        "Russian",
        "Spanish",
        "Swedish",
        "Swiss",
        "Tex-Mex",
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
    # 2026-07-27 addition: 16 further real Food.com tags, verified present in
    # the scraped archive (see module docstring), now that the human has
    # approved matching CUISINE_OPTIONS entries for each.
    "cajun": "Cajun",
    "creole": "Creole",
    "tex mex": "Tex-Mex",
    "filipino": "Filipino",
    "cuban": "Cuban",
    "czech": "Czech",
    "hungarian": "Hungarian",
    "austrian": "Austrian",
    "swedish": "Swedish",
    "belgian": "Belgian",
    "dutch": "Dutch",
    "russian": "Russian",
    "norwegian": "Norwegian",
    "polish": "Polish",
    "finnish": "Finnish",
    "swiss": "Swiss",
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


def resolve_cuisine(
    recipe_category: str | None, keywords: str | None, title: str | None = None
) -> tuple[str | None, str]:
    """Returns `(cuisine, cuisine_source)`. `cuisine_source` is one of
    "recovered_tag" (a CUISINE_TERMS token matched), "gazetteer_matched" (a
    DISH_NAME_CUISINE_TERMS title match -- only tried if tier 1 found
    nothing, and only if `title` is provided), or "unknown" (no match at
    all). Checks `recipe_category` tokens before `keywords` tokens
    (`recipeCategory` is Food.com's single canonical category field, so it
    takes precedence); within each field, the first token that matches
    CUISINE_TERMS wins. A generic-bucket-only tag set and a no-signal tag
    set both fall through to the title gazetteer (tier 2) rather than
    resolving to `(None, "unknown")` immediately -- see this module's
    docstring for the full tier rationale. `title` defaults to `None` for
    backward compatibility with any caller that only has tag fields."""
    for token in split_tag_field(recipe_category) + split_tag_field(keywords):
        mapped = CUISINE_TERMS.get(token.lower())
        if mapped:
            return mapped, "recovered_tag"
    if title:
        gazetteer_cuisine, gazetteer_source = resolve_cuisine_from_title(title)
        if gazetteer_cuisine:
            return gazetteer_cuisine, gazetteer_source
    return None, "unknown"


# --- Tier 2: dish-name gazetteer (title-only, see module docstring) --------
#
# Targets ONLY the 8 already-canonical cuisines tag-mining cannot reach at
# all (zero recovered examples as of 2026-07-27): American, British, French,
# Italian, Mediterranean, Nepali, Persian, Peruvian. Every entry below is a
# SPECIFIC, real dish name -- never a bare adjective/nationality word, never
# a single generic food-category word. Judgment calls, documented:
#
#   - American: deliberately held to a much higher bar than every other
#     cuisine here. Most "American" dish names are generic (burger,
#     meatloaf) and matching them would risk false-tagging genuinely
#     cuisine-agnostic recipes wholesale -- so only dishes with an
#     unambiguous, specific, single-cuisine identity are included
#     ("buffalo wings", "cheesesteak", "cobb salad", "key lime pie",
#     "sloppy joe", "chicken fried steak", "clam chowder"). Deliberately
#     EXCLUDED: "meatloaf", "burger", "pot roast", "apple pie" -- too
#     generic/globally-cooked to fix American cuisine from the title word
#     alone.
#   - Mediterranean: zero entries, on purpose. "Mediterranean" as used in
#     this taxonomy is a broad regional label, not a national cuisine --
#     every specific dish name a human would first reach for (tzatziki,
#     hummus, falafel, tabbouleh, baba ganoush) is ALSO a real dish of one
#     of this taxonomy's more specific existing cuisines (Greek, Lebanese,
#     Turkish, Moroccan, Middle Eastern), so gazetteer-assigning any of them
#     to the generic "Mediterranean" bucket would arbitrarily override a
#     more specific, already-correct classification. Better to leave this
#     cuisine at 0 gazetteer coverage than force an ambiguous call.
#   - "ceviche" (candidate for Peruvian): deliberately EXCLUDED. Ceviche is
#     a real, common dish across many Latin American cuisines (Mexican,
#     Ecuadorian, Chilean, etc.), not uniquely Peruvian -- the bare word
#     does not fix the cuisine. "lomo saltado", "aji de gallina", and
#     "causa rellena" are used instead: all three are specifically and
#     near-exclusively Peruvian dish names with no equivalent currency in
#     other Latin cuisines.
#   - "momo" (Nepali): included, but genuinely ambiguous -- momo is also a
#     staple of Tibetan cuisine (no "Tibetan" CUISINE_OPTIONS entry exists
#     to route it to instead), so a momo-titled recipe from a Tibetan
#     source would be mislabeled Nepali. Judged an acceptable tradeoff
#     given (a) no better bucket exists for it in this taxonomy, (b) most
#     English-language recipe-site "momo" titles found online are
#     presented as Nepali, and (c) the collision risk is a wrong-but-
#     adjacent regional label, not an unrelated cuisine entirely. Verified
#     word-boundary matching does NOT false-fire on "Momofuku" (a common
#     Food.com title prefix for David Chang recipes) -- "momofuku" is one
#     unbroken word with no boundary after "momo", so `\bmomo\b` cannot
#     match inside it; see tests/test_cuisine_gazetteer.py.
#   - "Belgian waffle": deliberately EXCLUDED from this gazetteer entirely
#     (Belgian is not one of the 8 target cuisines here, and doesn't need
#     to be -- the new "Belgian" CUISINE_OPTIONS entry already gets real,
#     non-zero tag-mining coverage from Food.com's own "Belgian" keyword
#     tag, see CUISINE_TERMS above). Adding a title-based "Belgian waffle"
#     match on top would be pure scope creep carrying real collision risk
#     of its own (Belgian waffles are served/named as such constantly in
#     American recipes with no Belgian provenance at all) for a cuisine
#     that doesn't need the extra recall.
DISH_NAME_CUISINE_TERMS: dict[str, str] = {
    # American (high bar -- see note above)
    "buffalo wings": "American",
    "cheesesteak": "American",
    "cobb salad": "American",
    "key lime pie": "American",
    "sloppy joe": "American",
    "chicken fried steak": "American",
    "clam chowder": "American",
    # British
    "fish and chips": "British",
    "shepherds pie": "British",
    "cottage pie": "British",
    "bangers and mash": "British",
    "toad in the hole": "British",
    "beef wellington": "British",
    "eton mess": "British",
    "bubble and squeak": "British",
    "spotted dick": "British",
    "steak and kidney pie": "British",
    "victoria sponge": "British",
    # French. "french onion soup" is a genuine, specific French dish
    # (soupe a l'oignon gratinee) -- unlike the banned bare-adjective
    # collisions ("French Toast", "French Fries"), this is a full,
    # unambiguous three-word dish name whose origin really is French.
    "coq au vin": "French",
    "ratatouille": "French",
    "quiche lorraine": "French",
    "boeuf bourguignon": "French",
    "beef bourguignon": "French",
    "creme brulee": "French",
    "croque monsieur": "French",
    "moules frites": "French",
    "cassoulet": "French",
    "salade nicoise": "French",
    "tarte tatin": "French",
    "french onion soup": "French",
    # Italian
    "carbonara": "Italian",
    "bolognese": "Italian",
    "risotto": "Italian",
    "tiramisu": "Italian",
    "osso buco": "Italian",
    "minestrone": "Italian",
    "panna cotta": "Italian",
    "bruschetta": "Italian",
    "gnocchi": "Italian",
    "focaccia": "Italian",
    "caprese salad": "Italian",
    "cacciatore": "Italian",
    # Mediterranean: intentionally empty -- see note above.
    # Nepali
    "momo": "Nepali",
    "dal bhat": "Nepali",
    # Persian
    "tahdig": "Persian",
    "fesenjan": "Persian",
    "ghormeh sabzi": "Persian",
    # Peruvian ("ceviche" deliberately excluded -- see note above)
    "lomo saltado": "Peruvian",
    "aji de gallina": "Peruvian",
    "causa rellena": "Peruvian",
}

assert set(DISH_NAME_CUISINE_TERMS.values()) <= CANONICAL_CUISINES, (
    "DISH_NAME_CUISINE_TERMS must only emit values already present in CANONICAL_CUISINES"
)


def _normalize_title_for_gazetteer(title: str) -> str:
    """Lowercases, strips apostrophes (straight and the Unicode curly
    quote), and strips accent diacritics (NFKD-decompose + drop combining
    marks) so gazetteer entries can be authored in plain ASCII (e.g. "creme
    brulee", "shepherds pie") and still match real title spellings that use
    either accented ("Crème Brûlée") or unaccented ("Creme Brulee") French
    orthography, or either apostrophe style ("Shepherd's Pie" / "Shepherds
    Pie")."""
    lowered = title.lower().replace("’", "").replace("'", "")
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def resolve_cuisine_from_title(title: str | None) -> tuple[str | None, str]:
    """Returns `(cuisine, cuisine_source)` from a whole-phrase, word-boundary
    match of `title` against DISH_NAME_CUISINE_TERMS. Mirrors the
    word-boundary-with-optional-plural-"s" regex idiom already established
    in `title_ingredient_integrity._find_term_spans` (never a naive
    substring match) rather than inventing new matching mechanics. Phrases
    are tried longest-first so a shorter phrase can never preempt a longer,
    more specific one that contains it (defensive; no current entry is a
    substring of another, but this keeps that invariant cheap to preserve).
    No match -> `(None, "unknown")`. See the mandatory adversarial guard in
    `tests/test_cuisine_gazetteer.py`."""
    if not title:
        return None, "unknown"
    normalized = _normalize_title_for_gazetteer(title)
    for phrase in sorted(DISH_NAME_CUISINE_TERMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}s?\b", normalized):
            return DISH_NAME_CUISINE_TERMS[phrase], "gazetteer_matched"
    return None, "unknown"
