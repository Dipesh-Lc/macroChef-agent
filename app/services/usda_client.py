import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

from app.config import Settings, get_settings
from app.schemas.nutrition import FoodMacros, FoodMatch
from app.services.nutrition_cache import FdcCache
from app.utils.ingredient_normalizer import normalize_ingredient
from app.utils.logging import get_logger

logger = get_logger(__name__)

# USDA FDC nutrient numbers (stable across dataTypes) for the macros we track.
# https://fdc.nal.usda.gov/
# Energy is NOT reported under a single stable number across dataTypes: SR
# Legacy/Survey (FNDDS)/Branded records use "208" ("Energy", KCAL), but
# Foundation records (FDC's newer, most-preferred-by-us dataType per
# _DATA_TYPE_PRIORITY) omit "208" entirely and report only "957"/"958"
# ("Energy (Atwater General/Specific Factors)", both KCAL) -- confirmed
# against live FDC responses for bell pepper/avocado/zucchini/oats/carrot,
# all Foundation, all missing 208. Checking 208 first preserves existing
# fixture/test behavior; falling back to 957 then 958 is what lets Foundation
# records actually clear `_extract_macros` instead of being silently skipped
# in favor of a lower-priority, less relevant candidate.
_NUTRIENT_CALORIES_CANDIDATES = ("208", "957", "958")
_NUTRIENT_PROTEIN = "203"
_NUTRIENT_FAT = "204"
_NUTRIENT_CARBS = "205"
_NUTRIENT_FIBER = "291"

# Prefer generic, reproducible whole-food data over branded products, whose
# macros vary by manufacturer/formulation and would make grounding unstable.
_DATA_TYPE_PRIORITY = {
    "Foundation": 0,
    "SR Legacy": 1,
    "Survey (FNDDS)": 2,
    "Branded": 3,
}

# This priority is only as good as what actually reaches `_best_match` --
# confirmed live that a single combined `dataType=[...all 4...]` query at
# pageSize=5 lets Branded's sheer catalog volume crowd generic records out of
# the fetched window entirely for common grocery-item names (e.g. "greek
# yogurt": 5/5 top results Branded despite a real Foundation "Yogurt, Greek,
# plain, nonfat" record existing; "balsamic vinegar": all 25 of the top 25
# results Branded despite a real SR Legacy "Vinegar, balsamic" existing).
# `_DATA_TYPE_PRIORITY` can only sort what's in the payload -- it can't
# rescue a candidate FDC's own relevance ranking never returned. Querying
# generic types in their own request first, and only falling back to a
# separate Branded-only request when nothing generic clears relevance, is
# what actually makes the priority's intent hold.
_GENERIC_DATA_TYPES = ["Foundation", "SR Legacy", "Survey (FNDDS)"]
_BRANDED_DATA_TYPES = ["Branded"]

# Deterministic classification of an FDC food's preparation state from its
# `description`, checked canned -> cooked -> raw (FDC's controlled vocabulary
# states these unambiguously when present, e.g. "Rice, brown, long-grain,
# cooked" / "..., raw"). A description matching none of these returns None
# ("unknown") rather than a guess -- callers that require a specific state
# (see `preparation` gating below) must treat None as a non-match, never as a
# default. This is what prevents a raw grain/legume record (often ranked
# first by `_DATA_TYPE_PRIORITY`, e.g. Foundation) from silently satisfying a
# declared-cooked ingredient and inflating its computed calories ~2-3x.
# Also the shared vocabulary for `_is_relevant_match`'s head-word allowance
# below, so a declared-cooked query is allowed to match a head like "Rice,
# brown, cooked" without treating "cooked" as a suspicious extra word.
_CANNED_WORDS = {"canned"}
_COOKED_WORDS = {"cooked", "boiled", "steamed"}
# "uncooked" is FDC's own term for quinoa's raw state (e.g. "Quinoa,
# uncooked") -- included here, not as a "cooked" match, since as one token it
# never matches \bcooked\b (no word boundary between "un" and "cooked").
_RAW_WORDS = {"raw", "dry", "dried", "uncooked"}
_PREPARATION_WORDS = {"canned": _CANNED_WORDS, "cooked": _COOKED_WORDS, "raw": _RAW_WORDS}

_CANNED_PATTERN = re.compile(r"\b(" + "|".join(_CANNED_WORDS) + r")\b", re.IGNORECASE)
_COOKED_PATTERN = re.compile(r"\b(" + "|".join(_COOKED_WORDS) + r")\b", re.IGNORECASE)
_RAW_PATTERN = re.compile(r"\b(" + "|".join(_RAW_WORDS) + r")\b", re.IGNORECASE)


def _classify_preparation(description: str) -> str | None:
    if _CANNED_PATTERN.search(description):
        return "canned"
    if _COOKED_PATTERN.search(description):
        return "cooked"
    if _RAW_PATTERN.search(description):
        return "raw"
    return None


# Deterministic, token-based guard against a candidate that shares a word
# with the query but is a different food or a manufactured derivative --
# e.g. query "avocado" matching "Oil, avocado", or "bell pepper" matching
# "TACO BELL, Nachos" (confirmed live: both slipped through _DATA_TYPE_
# PRIORITY sorting alone since neither the query nor the gate checked
# semantic relevance to the ingredient's own name).
_TOKEN_PATTERN = re.compile(r"[a-z]+")


def _tokenize(text: str) -> set[str]:
    words = _TOKEN_PATTERN.findall(text.lower())
    # Naive singularization (strip a trailing "s" on longer words) so
    # "peppers"/"pepper", "beans"/"bean" etc. line up between query and
    # description without a real stemmer.
    return {word[:-1] if word.endswith("s") and len(word) > 3 else word for word in words}


def _is_relevant_match(query: str, description: str, preparation: str | None = None) -> bool:
    """True if `description` is plausibly the same food as `query`.

    Two checks, both required:
    1. Every query token must appear somewhere in the description -- a
       candidate missing a query word outright (e.g. "pepper") is never the
       same food.
    2. The description's head segment (its leading, comma-delimited food
       name, per FDC's "Noun, modifier, modifier..." convention) must
       consist entirely of query tokens (plus the declared preparation's own
       vocabulary, e.g. "cooked" for a cooked-declared query, so "Rice,
       brown, cooked" isn't rejected for stating the very state we asked
       for). A head introducing any other word (Oil, Soup, Bread, Milk,
       Nachos...) signals a different or derived product, not a modifier on
       the queried food.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return False
    description_tokens = _tokenize(description)
    if not query_tokens <= description_tokens:
        return False

    allowed_head_tokens = query_tokens | _PREPARATION_WORDS.get(preparation, set())
    head_tokens = _tokenize(description.split(",", 1)[0])
    if not head_tokens or not head_tokens <= allowed_head_tokens:
        return False
    return True


def _extract_macros(food: dict[str, Any]) -> FoodMacros | None:
    """Pull per-100g macros out of a single FDC `/foods/search` food entry.

    Returns `None` if any of calories/protein/fat/carbs is missing (fiber
    defaults to 0.0 since many foods legitimately omit it) — that food is
    then skipped as a candidate match rather than producing bad numbers.

    Also returns `None` if any of the five is negative -- confirmed live
    against real FDC data (a "Carbohydrate, by difference" value can come
    out marginally negative, e.g. -0.428, from that nutrient's own
    subtraction-based calculation methodology upstream at USDA, not a bug
    in this reader). `FoodMacros` enforces `ge=0` on every field precisely
    because a negative macro is never physically meaningful, so silently
    passing one through would crash the whole grounding run on Pydantic
    validation instead of degrading to "skip this candidate" like every
    other unusable-data case here.
    """

    by_number: dict[str, float] = {}
    for nutrient in food.get("foodNutrients") or []:
        number = nutrient.get("nutrientNumber")
        value = nutrient.get("value")
        if number is None or value is None:
            continue
        by_number.setdefault(number, value)

    calories = next((by_number[number] for number in _NUTRIENT_CALORIES_CANDIDATES if number in by_number), None)
    protein = by_number.get(_NUTRIENT_PROTEIN)
    fat = by_number.get(_NUTRIENT_FAT)
    carbs = by_number.get(_NUTRIENT_CARBS)
    if calories is None or protein is None or fat is None or carbs is None:
        return None

    fiber = by_number.get(_NUTRIENT_FIBER, 0.0)
    if any(value < 0 for value in (calories, protein, fat, carbs, fiber)):
        return None

    return FoodMacros(
        calories=calories,
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fat,
        fiber_g=fiber,
    )


# Page sizes for each fetch tier. Generic stays at 5 (unchanged from item
# 1.4 -- generic dataTypes are a small, curated catalog where the top few
# relevance-ranked hits are enough). Branded is widened to 25 (item 4/P5): a
# much larger, noisier catalog where a single record's calorie value is not
# reliable enough to trust on rank alone -- `_select_branded_match` collects
# every eligible candidate across this wider page and picks by median
# calories (or declines entirely on high dispersion) instead.
_GENERIC_PAGE_SIZE = 5
_BRANDED_PAGE_SIZE = 25

# Retries for transient FDC failures: confirmed live that identical,
# well-formed requests intermittently 400 (a bare nginx error page, not an
# FDC-generated error body, with ample rate-limit quota remaining) --
# infrastructure-level flakiness, not a malformed request. Measured live: a
# ~40% per-request failure rate (10/25 failed for a single repeated query),
# far higher than initially assumed. At 3 attempts, all-attempts-fail
# probability is 0.4^3 ~= 6.4%, which is exactly what produced ~30 grounding
# discrepancies across two otherwise-identical corpus runs (item 1.4 Step B
# reproducibility check) -- a transient failure on the generic tier was
# silently falling back to a worse Branded match often enough to make the
# "grounded" set untrustworthy. 8 attempts brings that down to 0.4^8 ~=
# 0.065%. `UsdaClient` is only ever driven by the offline batch grounding
# job (never a live request path), so the added worst-case latency here has
# no user-facing cost. Retrying a genuinely bad request just costs a bit
# more time before it still fails closed.
_MAX_ATTEMPTS = 8
_RETRY_BACKOFF_SECONDS = (0.5, 1.0, 1.5, 2.0, 2.0, 2.5, 2.5)

# --- Rate-limit handling (A3 prep) ---
#
# FDC signals its per-key hourly quota being exceeded via HTTP 429, or --
# confirmed against FDC's own docs -- occasionally HTTP 403 with a JSON
# error body whose `error.code` is "OVER_RATE_LIMIT" (as opposed to a 403
# for a genuinely bad/missing key, which reports a different code and must
# NOT be treated as a transient rate-limit condition). This is handled as
# its OWN path, deliberately separate from `_MAX_ATTEMPTS`'s ordinary
# transient-failure retry below:
#
#   - A rate-limited response is NEVER treated like an ordinary transient
#     failure (400/503/connection-reset/etc, which -- after exhausting
#     `_MAX_ATTEMPTS` -- degrades to returning `None`, which
#     `search_food_with_reason` then classifies as a terminal
#     REASON_NO_RELEVANT_CANDIDATE "ungrounded" outcome). Doing that for a
#     rate-limited call would silently misclassify a real ingredient as
#     "no USDA match" purely because the hourly quota ran out mid-run --
#     corrupting the corpus-wide grounding report with no signal that
#     anything went wrong.
#   - It is also never written to `FdcCache` -- `_get_payload` only calls
#     `cache.set_payload` on an actual returned payload (see its
#     docstring), and the path below never returns one for a rate-limited
#     response, so this is already structurally guaranteed, not something
#     this addition has to separately enforce.
#   - Instead: retry a SHORT, bounded number of times with a longer backoff
#     (in case it's a brief burst rather than a genuinely exhausted hourly
#     window), then raise `UsdaRateLimitError` -- a fail-loud, fail-CLEAN
#     stop. The caller (the offline batch job, `grounding_job.run_grounding`
#     via `scripts/ground_corpus.py`) is expected to let this propagate and
#     crash the run rather than catch and continue: every payload
#     successfully fetched earlier in the same run is already durably
#     persisted to `FdcCache` (written incrementally, see `_get_payload`),
#     so a re-run after the quota window resets resumes from exactly where
#     this one stopped, re-fetching only what was never cached, at zero
#     extra API cost for anything already grounded.
_RATE_LIMIT_MAX_ATTEMPTS = 3
_RATE_LIMIT_BACKOFF_SECONDS = (5.0, 30.0)


class UsdaRateLimitError(RuntimeError):
    """Raised by `UsdaClient._fetch_with_retry` when FDC keeps signaling its
    rate limit (HTTP 429, or HTTP 403 with error code OVER_RATE_LIMIT) past
    `_RATE_LIMIT_MAX_ATTEMPTS` bounded retries. See the module comment above
    `_RATE_LIMIT_MAX_ATTEMPTS` for why this is a distinct, fail-loud path
    rather than degrading to `None`/"ungrounded" like an ordinary transient
    failure."""


def _rate_limit_error_code(response: Any) -> str | None:
    """Returns the FDC `error.code` string (uppercased) from `response`'s
    JSON body, or `None` if the body isn't JSON or has no such field. Used
    only to distinguish a rate-limited 403 (`OVER_RATE_LIMIT`) from a 403
    for an invalid/missing API key, which must NOT be treated as transient
    rate-limiting."""
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code.upper() if isinstance(code, str) else None


def _is_rate_limited_response(response: Any) -> bool:
    """True if `response` is FDC signaling its hourly rate limit has been
    exceeded -- HTTP 429 unconditionally, or HTTP 403 specifically carrying
    `error.code == "OVER_RATE_LIMIT"` in its JSON body (a bare 403 with any
    other/no code, e.g. a bad API key, is NOT rate-limiting and falls
    through to the ordinary transient-failure handling instead)."""
    status_code = getattr(response, "status_code", None)
    if status_code == 429:
        return True
    if status_code == 403:
        return _rate_limit_error_code(response) == "OVER_RATE_LIMIT"
    return False


@dataclass
class MatchOutcome:
    """Result of scanning one FDC payload for a match.

    `rejections` is a list of reason codes for every candidate that was
    excluded *after* the relevance/preparation gate (i.e. by the
    plausibility gate or the undeclared-preparation modifier blocklist) --
    not every relevance failure, which would be noise (most candidates in a
    5-25 item page are simply unrelated foods). Purely diagnostic: consumed
    by `UsdaClient` to build corpus-wide report counts, never used to change
    matching behavior itself.

    `dispersion` is set only by `_select_branded_match` (never `_best_match`)
    when 3+ otherwise-eligible Branded candidates disagree by more than a
    3x calorie ratio -- `(min_kcal, max_kcal, candidate_count)`, `match` is
    `None` in that case. Also purely diagnostic (see `UsdaClient.
    branded_dispersion_events`).
    """

    match: FoodMatch | None
    rejections: list[str] = field(default_factory=list)
    dispersion: tuple[float, float, int] | None = None


# Absolute-plausibility gate applied to EVERY candidate's per-100g macros,
# regardless of dataType tier -- a bad number should never win just because
# it's Foundation-ranked. This exists because relevance/preparation alone
# only checks that a candidate is *the same food*, never that its reported
# values are physically sane; live FDC data has both unit-scale defects
# (e.g. a record reporting kilojoules under the "208"/kcal nutrient number)
# and flat data-entry defects (e.g. a spice reporting 0 kcal/100g, or a sum
# of macronutrient grams exceeding what fits in 100g of food).
#
# Bounds:
#   - kcal < 5 (Branded only -- see the tier-aware note below) or kcal > 950
#     (every tier): outside any real whole food's per-100g range (950
#     comfortably covers pure fats/oils at ~884-900; 5 excludes a "0 kcal"
#     data defect like the ginger/chili powder case).
#   - protein_g + carbs_g + fat_g > 105: 100g of food cannot contain more
#     than ~100g of macronutrient mass; 105 gives a small tolerance for
#     independently-rounded USDA values without opening the door to a
#     genuinely impossible record.
#   - Atwater mismatch: reported kcal should be explainable by the reported
#     macros via the standard Atwater factors (4 kcal/g protein, 4 kcal/g
#     carbs, 9 kcal/g fat) -- catches a kJ-scale defect (reported kcal ~4x
#     too high relative to its own macros) even when it's still under the
#     950 absolute ceiling. A candidate passes if EITHER its kcal is within
#     [0.5x, 1.7x] of its own Atwater estimate (generous enough for real
#     dietary-fiber/sugar-alcohol/rounding variance) OR its absolute
#     difference from the Atwater estimate is <=25 kcal -- the second,
#     absolute escape is what lets a genuinely low-calorie, low-macro food
#     (e.g. vinegar: ~18 kcal/100g against a near-zero Atwater estimate from
#     its trace protein/carbs/fat) pass without being penalized by a ratio
#     computed against a near-zero denominator.
#
# --- Tier-aware near-zero admission (phase 1.5 closeout P2) ---
#
# The kcal floor used to apply unconditionally, BEFORE the Atwater check
# ever ran -- which meant it also rejected a genuinely all-zero real food
# (salt, water, baking soda: true near-0 kcal/100g, internally consistent
# with their all-zero macros) exactly like it rejects an actual data defect
# (ginger/chili powder's Branded records, which also report 0 kcal but are
# NOT physically meaningful). Confirmed live and pinned as a regression
# fixture: for query "water", this floor rejected the correct record
# ('Water, tap', Survey (FNDDS), 0 kcal) and the matcher fell through to
# 'Water, tonic' (34 kcal/100g, a plausible-looking but WRONG record) --
# the gate built to prevent a confidently-wrong number was manufacturing
# one. Atwater consistency alone can't distinguish the two cases either
# (both are 0 kcal against 0 macros -- internally consistent), so dataType
# tier is the deterministic signal used instead: the floor now applies ONLY
# to Branded candidates (the distrusted, last-resort, uncurated tier this
# codebase already treats as the least-trusted -- see `_DATA_TYPE_PRIORITY`/
# `_select_branded_match`), while Foundation/SR Legacy/Survey candidates
# skip the floor and fall through to the mass + Atwater checks, which
# correctly pass a genuine all-zero record and still reject an internally
# INCONSISTENT one (0 kcal but nonzero macros -- `atwater_mismatch`).
#
# Disclosed blind spot: a genuine-tier (Foundation/SR Legacy/Survey) all-
# ZERO defect record (0 kcal AND all-zero macros, so Atwater can't catch it
# either) would now be admitted where it previously wasn't. Accepted
# tradeoff: both documented zero-kcal defects on record (ginger, chili
# powder -- see _KNOWN_RESIDUALS) are Branded, and the generic tiers are
# USDA-curated (Foundation/SR Legacy/Survey are USDA's own maintained
# datasets, not third-party-submitted like Branded), so an all-zero defect
# surviving curation into one of them is a materially rarer failure mode
# than a manufacturer-submitted Branded record being wrong -- and the
# dispersion check (`_select_branded_match`) and the implausible-band net
# (`grounding_job.IMPLAUSIBLE_MIN_KCAL_PER_SERVING`) remain behind it either
# way.
_PLAUSIBLE_MIN_KCAL = 5.0
_PLAUSIBLE_MAX_KCAL = 950.0
_PLAUSIBLE_MAX_MACRO_MASS_G = 105.0
_ATWATER_RATIO_LOW = 0.5
_ATWATER_RATIO_HIGH = 1.7
_ATWATER_ABSOLUTE_ESCAPE_KCAL = 25.0

# The only dataType tiers EXEMPT from the kcal floor -- i.e. FDC's own
# curated, generic datasets (same set as `_GENERIC_DATA_TYPES`, restated
# here as its own name so this gate's meaning reads standalone). Every other
# tier -- Branded, or an unrecognized/absent dataType -- still gets the
# floor: fail CLOSED (apply the stricter check) on anything that isn't
# affirmatively known to be a curated generic record, consistent with
# `_DATA_TYPE_PRIORITY` already treating Branded as the least-trusted,
# last-resort tier.
_PLAUSIBLE_FLOOR_EXEMPT_TIERS = frozenset(_GENERIC_DATA_TYPES)


def _plausibility_reject_reason(macros: FoodMacros, data_type: str | None = None) -> str | None:
    """Returns a reason code if `macros` fails the absolute-plausibility
    gate, else `None`. See the gate's module-level comment for the bounds
    and their rationale, including why the kcal floor is now conditional on
    `data_type`.

    `data_type` is the candidate's FDC `dataType` string (e.g. "Foundation",
    "Branded"). The floor is skipped ONLY when `data_type` is one of the
    recognized generic tiers (`_PLAUSIBLE_FLOOR_EXEMPT_TIERS`); `None` (the
    default, e.g. an older caller/test that doesn't pass a tier) or any
    other value keeps the floor applied -- the conservative, fail-closed
    default.
    """
    if data_type not in _PLAUSIBLE_FLOOR_EXEMPT_TIERS and macros.calories < _PLAUSIBLE_MIN_KCAL:
        return "kcal_too_low_branded"
    if macros.calories > _PLAUSIBLE_MAX_KCAL:
        return "kcal_too_high"

    macro_mass = macros.protein_g + macros.carbs_g + macros.fat_g
    if macro_mass > _PLAUSIBLE_MAX_MACRO_MASS_G:
        return "mass_over_105g"

    atwater = 4 * macros.protein_g + 4 * macros.carbs_g + 9 * macros.fat_g
    within_ratio = (_ATWATER_RATIO_LOW * atwater) <= macros.calories <= (_ATWATER_RATIO_HIGH * atwater)
    within_absolute = abs(macros.calories - atwater) <= _ATWATER_ABSOLUTE_ESCAPE_KCAL
    if not (within_ratio or within_absolute):
        return "atwater_mismatch"

    return None


# --- Undeclared-preparation handling ---
#
# `preparation` gating (above) only covers ingredients that declare a state.
# For everything else (the vast majority of the imported corpus, which has
# no per-ingredient `preparation` field authored at all), a candidate can
# still silently be a processed/derived form of the right food purely
# because of dataType-tier order -- e.g. "zucchini" landing on a Branded
# "Zucchini, pickled" record. Two independent, narrower mechanisms address
# this without needing every ingredient in the corpus to declare a state:
#
# 1. A processed-state modifier BLOCKLIST (a gate, applied only when
#    `preparation is None`): reject a candidate whose description's
#    NON-head segments (everything after the first comma -- the head itself
#    is already constrained by `_is_relevant_match`) mention a processing
#    method that changes the food's macro profile in a way no honest
#    raw/cooked/canned declaration would predict -- pickling, breading,
#    sweetening, smoking, juicing, turning it into a sauce/soup, etc.
#    Deliberately excludes "dried"/"dry": those are FDC's own raw-state
#    vocabulary for grains/legumes/produce (see `_RAW_WORDS`), not a
#    processing method in this sense -- blocking them would wrongly reject
#    the correct raw record for e.g. lentils or oats.
# 2. A within-tier state PREFERENCE (a tie-break, never a gate, and only
#    consulted when `preparation is None`): among candidates that already
#    survive every gate above, prefer raw < unclassified(None) < cooked <
#    canned, i.e. a bare raw record wins over an equally-relevant cooked or
#    canned one at the same dataType-priority tier. Raw is the safer
#    deterministic prior for an undeclared ingredient -- cooked/canned
#    records systematically read as lower-calorie-per-100g than their raw
#    form (water/fat loss or addition during processing), so preferring raw
#    is the conservative choice that avoids silently picking a processed
#    record's altered macros for what the recipe almost certainly means as
#    a plain ingredient.
_PROCESSED_STATE_MODIFIERS = {
    "pickled", "fried", "breaded", "battered", "candied", "sweetened", "syrup",
    "brined", "cured", "smoked", "glazed", "creamed", "marinated", "dehydrated",
    "powdered", "juice", "sauce", "soup",
}
_PROCESSED_STATE_PATTERN = re.compile(r"\b(" + "|".join(_PROCESSED_STATE_MODIFIERS) + r")\b", re.IGNORECASE)

# Preference order for the within-tier tie-break: lower sorts first (wins).
_STATE_PREFERENCE_ORDER = {"raw": 0, None: 1, "cooked": 2, "canned": 3}


def _processed_state_modifier(description: str) -> str | None:
    """Returns the matched blocklist token if any NON-head segment (i.e. any
    comma-delimited segment after the first) of `description` names a
    processed-state modifier, else `None`. Only consulted when `preparation`
    is undeclared -- see the module comment above."""
    non_head = ",".join(description.split(",")[1:])
    match = _PROCESSED_STATE_PATTERN.search(non_head)
    return match.group(1).lower() if match else None


def _best_match(payload: dict[str, Any], query: str, preparation: str | None = None) -> MatchOutcome:
    """Pick the best-ranked, best-stated food with usable, plausible macros,
    gated by relevance, by `preparation` when given, by absolute
    plausibility (see `_plausibility_reject_reason`), and -- when
    `preparation` is undeclared -- by the processed-state modifier blocklist
    (see `_processed_state_modifier`).

    Every candidate must pass `_is_relevant_match` against `query` -- a
    candidate that is a different or derived food (see its docstring) is
    skipped regardless of rank. When `preparation` is set, a candidate is
    additionally only eligible if its description classifies to that exact
    state (see `_classify_preparation`) -- an unclassifiable or
    differently-stated candidate is skipped even if it would otherwise rank
    first, so a declared-cooked ingredient can never resolve to a raw record
    (or vice versa). When `preparation` is `None`, a candidate naming a
    processed-state modifier outside its head segment is skipped instead.
    A candidate whose extracted macros fail the plausibility gate is also
    skipped, with its rejection reason recorded in `MatchOutcome.rejections`
    for the corpus-wide report -- a confidently wrong number is worse than
    an honest unknown.

    Among every candidate surviving all of the above, the pick is ordered by
    (dataType priority, state preference, original payload order) -- state
    preference (see `_STATE_PREFERENCE_ORDER`) only matters as a tie-break
    within the same dataType tier, and only meaningfully varies results when
    `preparation is None` (a declared preparation already constrains every
    survivor to the exact same state). If nothing survives, `match` is
    `None` (ungrounded) rather than falling back to the best unrelated,
    wrong-state, or implausible candidate.
    """
    foods = payload.get("foods") or []
    rejections: list[str] = []
    eligible: list[tuple[int, int, int, dict[str, Any], str, FoodMacros]] = []

    for index, food in enumerate(foods):
        description = food.get("description", "")
        if not _is_relevant_match(query, description, preparation):
            continue

        if preparation is not None:
            if _classify_preparation(description) != preparation:
                continue
        else:
            modifier = _processed_state_modifier(description)
            if modifier is not None:
                rejections.append(f"processed_state_modifier:{modifier}")
                continue

        macros = _extract_macros(food)
        if macros is None:
            continue

        reject_reason = _plausibility_reject_reason(macros, food.get("dataType"))
        if reject_reason is not None:
            rejections.append(reject_reason)
            continue

        data_type_priority = _DATA_TYPE_PRIORITY.get(food.get("dataType"), 99)
        state_priority = _STATE_PREFERENCE_ORDER.get(_classify_preparation(description), 1)
        eligible.append((data_type_priority, state_priority, index, food, description, macros))

    if not eligible:
        return MatchOutcome(match=None, rejections=rejections)

    eligible.sort(key=lambda item: item[:3])
    _, _, _, food, description, macros = eligible[0]
    return MatchOutcome(
        match=FoodMatch(
            fdc_id=food["fdcId"],
            description=description,
            data_type=food.get("dataType", ""),
            macros=macros,
            query=query,
        ),
        rejections=rejections,
    )


# Branded-tier selection thresholds (item 4/P5). Branded's catalog is orders
# of magnitude larger and less curated than the generic dataTypes -- rank
# alone (as `_best_match` uses for the small, curated generic tier) isn't a
# reliable signal of accuracy here, so every eligible candidate across the
# widened page (`_BRANDED_PAGE_SIZE`) is collected and judged as a group.
_BRANDED_DISPERSION_MIN_CANDIDATES = 3
_BRANDED_DISPERSION_MAX_RATIO = 3.0


def _select_branded_match(payload: dict[str, Any], query: str, preparation: str | None = None) -> MatchOutcome:
    """Branded-tier candidate selection: collects every candidate passing
    the same relevance/preparation-or-modifier-blocklist/plausibility gates
    `_best_match` uses (see its docstring), then picks by GROUP agreement
    rather than rank, since Branded's sheer catalog volume and per-
    manufacturer variance make a single top-ranked record's calorie value
    untrustworthy on its own.

    - 0 eligible candidates -> ungrounded (`match=None`), same as `_best_match`.
    - >=3 eligible candidates whose calories span more than a 3x ratio
      (max/min) -> the disagreement itself is evidence no single candidate
      should be trusted; returns ungrounded with the range recorded in
      `MatchOutcome.dispersion` for the corpus-wide report, rather than
      picking one arbitrarily.
    - Otherwise: selects the actual candidate RECORD whose calories is the
      median (for an even candidate count, the lower of the two middle
      values -- ties broken by ascending `fdcId` for full determinism).
      Never synthesizes an average value -- the selected macros and fdc_id
      both come from one real FDC record, preserving provenance.

    No further dataType-based deprioritization is applied here (unlike
    `_best_match`'s `_DATA_TYPE_PRIORITY` sort) -- every candidate reaching
    this function is already Branded; Branded itself is already the
    strict, last-resort fallback tier (see `UsdaClient.search_food`).
    """
    foods = payload.get("foods") or []
    rejections: list[str] = []
    eligible: list[tuple[float, int, dict[str, Any], str, FoodMacros]] = []

    for food in foods:
        description = food.get("description", "")
        if not _is_relevant_match(query, description, preparation):
            continue

        if preparation is not None:
            if _classify_preparation(description) != preparation:
                continue
        else:
            modifier = _processed_state_modifier(description)
            if modifier is not None:
                rejections.append(f"processed_state_modifier:{modifier}")
                continue

        macros = _extract_macros(food)
        if macros is None:
            continue

        reject_reason = _plausibility_reject_reason(macros, food.get("dataType"))
        if reject_reason is not None:
            rejections.append(reject_reason)
            continue

        eligible.append((macros.calories, food["fdcId"], food, description, macros))

    if not eligible:
        return MatchOutcome(match=None, rejections=rejections)

    if len(eligible) >= _BRANDED_DISPERSION_MIN_CANDIDATES:
        calorie_values = [item[0] for item in eligible]
        min_kcal, max_kcal = min(calorie_values), max(calorie_values)
        if min_kcal > 0 and (max_kcal / min_kcal) > _BRANDED_DISPERSION_MAX_RATIO:
            rejections.append("branded_high_dispersion")
            return MatchOutcome(
                match=None,
                rejections=rejections,
                dispersion=(min_kcal, max_kcal, len(eligible)),
            )

    eligible.sort(key=lambda item: (item[0], item[1]))  # calories asc, fdc_id asc tie-break
    median_index = (len(eligible) - 1) // 2  # true median (odd) / lower-of-two-middle (even)
    _, _, food, description, macros = eligible[median_index]
    return MatchOutcome(
        match=FoodMatch(
            fdc_id=food["fdcId"],
            description=description,
            data_type=food.get("dataType", ""),
            macros=macros,
            query=query,
        ),
        rejections=rejections,
    )


# Queries where the general mechanism (relevance check + preparation gate +
# plausibility gate) reliably lands on a wrong-form record with plausible-
# looking macros, confirmed by manual review against real-world reference
# values (item 1.4 Step B closeout) -- and where no honest `preparation`
# declaration fixes it, unlike the grain/legume/meat cases the field was
# built for:
#   - "shrimp": no relevant Foundation/SR Legacy/Survey record exists even
#     with preparation="raw"; the best available match is a Branded "RAW
#     SHRIMP" at 71 kcal/100g against a true range of ~85-99 kcal/100g --
#     plausible-looking (passes the absolute-plausibility gate), but not
#     accurate enough to trust.
#   - "tomato sauce": matches a Branded "chili sauce" variant (92 kcal/100g)
#     instead of plain tomato sauce (~24-35 kcal/100g). A sauce has no
#     raw/cooked/canned state to declare, so this mismatch can't be gated the
#     way grain/legume/meat state ambiguity is, and 92 kcal/100g is itself
#     plausible enough to clear the absolute gate.
# "chili powder" and "ginger" were dropped from this list once the
# plausibility gate landed: both failed solely because their only reachable
# Branded record reported 0 kcal/100g, a data defect `_plausibility_reject_
# reason` ("kcal_too_low") now catches generally -- no ingredient-specific
# exclusion needed for that failure mode anymore.
# Deliberately narrow and disclosed rather than a general rule change with
# unclear corpus-wide blast radius -- an honest "we checked, don't trust
# this" list, not an attempt to force a match either way. Keyed by the exact
# normalized query (see `normalize_ingredient`).
_KNOWN_UNRELIABLE_QUERIES = {"shrimp", "tomato sauce"}


# --- Normalized-query -> FDC-vocabulary query aliases ---
#
# `_is_relevant_match`'s head-noun rule (see its docstring) is intentionally
# strict: a candidate's head segment must consist only of query tokens, so a
# bare "zucchini" query correctly refuses to match FDC's real "Squash,
# summer, green, zucchini, ..." record (filed under its botanical name, not
# "Zucchini") or "Cheese, parmesan, grated" (filed under "Cheese", not
# "Parmesan") -- both are the right food, just not reachable by the bare
# query's own vocabulary. Most spices/seasonings hit the same wall: FDC's
# generic dataTypes (Foundation/SR Legacy/Survey) file virtually every one
# under a "Spices, X, ..." head, not the bare spice name.
#
# This table maps a normalized query (see `normalize_ingredient`, run
# BEFORE this lookup) to the FDC-vocabulary phrase that reaches the real
# record -- applied in `UsdaClient.search_food` for BOTH the string actually
# sent to FDC's search endpoint (materially improves FDC's own relevance
# ranking, e.g. surfacing "Nuts, almonds, whole, raw" over "Almond butter"/
# "Almond oil" for a bare "almond" query) AND the token-matching query
# passed into `_is_relevant_match`/`_best_match` (so the relevance and head-
# noun checks run against the SAME vocabulary that was actually searched).
#
# INVARIANT, enforced by a parametrized test in test_usda_client.py:
# `_tokenize(original) <= _tokenize(alias)` for every entry -- the queried
# food's own identity token(s) must literally appear in the alias. This is
# what structurally prevents an alias from "bridging" to a different food
# (e.g. an alias could never turn "salt" into "butter") -- it can only
# supply the vocabulary FDC files the SAME food under.
#
# Curated by hand from the phase 1.5 baseline's top-50 corpus-wide
# ungrounded-ingredient frequency table (data/processed/
# grounding_report_baseline.md) plus the two design-example/known-residual
# entries (zucchini, per grounding_job._KNOWN_RESIDUALS; almond). Every
# entry below was individually verified against a live FDC lookup (pinned
# as a fixture-backed regression test for the first ten) before being added
# -- this is deliberately NOT a large or automatically-derived table (see
# the phase 1.5 design's "De-scoped" list: "auto synonym derivation" was
# explicitly ruled out). Most of the baseline's top-50 ungrounded entries
# (salt, butter, sugar, water, flour, milk, ...) are NOT here: live
# verification showed the large majority fail for a DIFFERENT reason this
# table can't fix -- the imported corpus's ingredient rows overwhelmingly
# have `unit: None` at the DATA level (35,059 of 35,183 rows in the imported corpus;
# see phase 1.5 closeout), and `app.utils.unit_converter.to_grams` has no
# density/piece-weight fallback for a bare, unit-less amount unless the
# ingredient is in `_PIECE_WEIGHT_G` (e.g. "2 eggs") -- none of salt,
# butter, sugar, water, flour, or milk are. So `search_food` is never even
# reached for most of these occurrences (see `nutrition_grounding.
# compute_recipe_macros`, and `grounding_job`'s `no_unit` terminal-outcome
# bucket) -- this is NOT a missing-density-entry problem: `sugar`, `water`,
# `flour`, and `milk` all already have real entries in `_DENSITY_G_PER_ML`
# (only `salt` and `butter` genuinely lack one), it's that there is no unit
# value at all for these rows to look a density up against. A few
# occurrences DO carry a real unit, genuinely reach FDC, and are STILL
# correctly ungrounded even after an alias would be found: salt/baking
# soda/baking powder's only relevant FDC records report a true, near-zero
# per-100g kcal -- previously excluded by the plausibility gate's kcal floor
# as an indistinguishable-from-a-data-defect case; RESOLVED by phase 1.5
# closeout/P2 (`_plausibility_reject_reason`'s tier-aware floor -- see its
# module comment), which now lets a genuine Foundation/SR Legacy/Survey
# near-zero record through while still rejecting a Branded 0-kcal defect.
# Different table from `app.utils.ingredient_normalizer.SYNONYMS` --
# deliberately NOT merged: that table maps free-form recipe text to a
# canonical pantry name for matching/scoring; this one maps a canonical
# name to FDC's own filing vocabulary. Conflating them would make either
# table's purpose unclear from its own contents.
_FDC_QUERY_ALIASES: dict[str, str] = {
    # Spices/seasonings: FDC's generic dataTypes file these under "Spices, X".
    "coriander": "spices coriander seed",
    "cumin": "spices cumin seed",
    "oregano": "spices oregano dried",
    "nutmeg": "spices nutmeg ground",
    "paprika": "spices paprika",
    "black pepper": "spices pepper black",
    "ginger": "spices ginger ground",
    "garlic powder": "spices garlic powder",
    "turmeric": "spices turmeric ground",
    "cardamom": "spices cardamom",
    "clove": "spices cloves ground",
    "allspice": "spices allspice ground",
    "tarragon": "spices tarragon dried",
    "curry powder": "spices curry powder",
    "bay leaf": "spices bay leaf",
    "cayenne pepper": "spices pepper red or cayenne",
    "cayenne": "spices pepper red or cayenne",
    "sage": "spices sage ground",
    "celery seed": "spices celery seed",
    "white pepper": "spices pepper white",
    "marjoram": "spices marjoram dried",
    "fennel seed": "spices fennel seed",
    # Herbs/other foods FDC files under a different head noun than the bare
    # ingredient name.
    "dill": "dill weed fresh",
    "parmesan": "cheese parmesan grated",
    "vanilla": "vanilla extract",
    # zucchini: the documented residual (see grounding_job._KNOWN_RESIDUALS)
    # -- FDC's real Foundation record is "Squash, summer, green, zucchini,
    # includes skin, raw", filed under "Squash" (its botanical genus), not
    # "Zucchini".
    "zucchini": "squash zucchini",
    # almond: the bare query's own top-5 FDC relevance ranking is dominated
    # by derivatives (almond butter/oil/paste/"flavored") that all outrank
    # the plain "Nuts, almonds, whole, raw" record; searching the alias
    # phrase directly reorders FDC's own ranking to surface it.
    "almond": "nuts almonds",
}


# Terminal per-OCCURRENCE outcome reasons returned by `UsdaClient.
# search_food_with_reason` -- see its docstring for how these differ from
# `rejection_counts` (an aggregate, per-CANDIDATE tally) and for the exact
# rule used to choose between the two failure reasons. Consumed by
# `grounding_job.build_report`'s corpus-wide terminal-outcome tally, which
# also has two unit-conversion-stage reasons of its own (`no_unit`, `unit_
# unconvertible`) for occurrences that never reach `search_food` at all.
REASON_GROUNDED = "grounded"
REASON_NO_RELEVANT_CANDIDATE = "no_relevant_candidate"
REASON_ALL_CANDIDATES_REJECTED = "all_candidates_rejected"


class UsdaClient:
    """Client for USDA FoodData Central's `/foods/search` endpoint.

    Degrades gracefully everywhere: with no API key configured, on network
    errors, or on an empty/unusable result, `search_food` returns `None`
    rather than raising. Callers (see `nutrition_grounding.py`) treat `None`
    as "this ingredient could not be grounded," never as "zero calories."

    `session` and `cache` are injectable so tests never touch the network.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        session: requests.Session | None = None,
        cache: FdcCache | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._settings = settings or get_settings()
        self._session = session or requests.Session()
        self._cache = cache if cache is not None else FdcCache(self._settings.fdc_cache_path)
        self._sleep = sleep
        # Cumulative, diagnostic-only tally of INDIVIDUAL-CANDIDATE rejection
        # reasons (see `MatchOutcome.rejections`), incremented once per
        # candidate skipped during matching -- NOT once per query/occurrence
        # that ended up ungrounded, and NOT a tally of "causes of
        # ungroundedness" (a query whose candidate got skipped here may still
        # go on to ground via a later candidate or the Branded fallback; see
        # `search_food_with_reason`/`REASON_*` for the actual per-occurrence
        # terminal outcome). Read by `grounding_job.run_grounding` after a
        # full corpus pass to report "N *candidates* rejected for reason X"
        # corpus-wide. Never consulted by matching logic itself.
        self.rejection_counts: Counter[str] = Counter()
        # Cumulative, diagnostic-only log of Branded-tier high-dispersion
        # events (see `_select_branded_match`/`MatchOutcome.dispersion`) --
        # (query, min_kcal, max_kcal, candidate_count) per occurrence. Read
        # by `grounding_job.run_grounding` for the report; never consulted
        # by matching logic itself.
        self.branded_dispersion_events: list[tuple[str, float, float, int]] = []

    def search_food(self, name: str, *, preparation: str | None = None) -> FoodMatch | None:
        """Look up macros for `name`, optionally gated to a declared `preparation`
        ("raw" / "cooked" / "canned" -- see `Ingredient.preparation`).

        The cache key includes `preparation` so a raw-gated and cooked-gated
        lookup of the same ingredient are never conflated.

        Thin wrapper around `search_food_with_reason` that discards the
        terminal-outcome reason -- every caller except the corpus-wide
        diagnostic tally in `grounding_job` uses this form.
        """
        match, _reason = self.search_food_with_reason(name, preparation=preparation)
        return match

    def search_food_with_reason(
        self, name: str, *, preparation: str | None = None, record_diagnostics: bool = True
    ) -> tuple[FoodMatch | None, str]:
        """As `search_food`, but also returns the terminal per-OCCURRENCE
        outcome reason for this exact call -- one of `REASON_GROUNDED`,
        `REASON_NO_RELEVANT_CANDIDATE`, `REASON_ALL_CANDIDATES_REJECTED`.

        This is deliberately a DIFFERENT axis from `rejection_counts` (see
        its docstring): `rejection_counts` tallies individual skipped
        candidates across the whole run, while the reason returned here
        classifies how THIS ONE call ended -- grounded, or not, and if not,
        whether any candidate reached the plausibility/modifier gates and
        got rejected there (`REASON_ALL_CANDIDATES_REJECTED`) versus nothing
        relevant/usable ever being found at all (`REASON_NO_RELEVANT_
        CANDIDATE` -- also used for an empty/normalized-away query, a
        `_KNOWN_UNRELIABLE_QUERIES` exclusion, and a fetch failure/no API
        key, none of which produce a candidate-level rejection either).
        Consumed by `grounding_job.build_report`'s corpus-wide terminal-
        outcome tally; never consulted by matching logic itself.

        `record_diagnostics` (default `True`) gates whether this call
        updates the cumulative `self.rejection_counts` / `self.
        branded_dispersion_events` -- pass `False` for a call that re-runs
        the SAME query a caller already issued once through this method
        (e.g. `grounding_job`'s terminal-outcome tally, which re-classifies
        an ingredient already looked up once by `compute_recipe_macros`
        during the same corpus pass) so that occurrence isn't double-
        counted into the cumulative, whole-run diagnostics. Matching
        behavior/the returned match and reason are completely unaffected
        either way -- this only controls bookkeeping.
        """
        query = normalize_ingredient(name)
        if not query:
            return None, REASON_NO_RELEVANT_CANDIDATE
        if query in _KNOWN_UNRELIABLE_QUERIES:
            return None, REASON_NO_RELEVANT_CANDIDATE

        # Alias to FDC's own filing vocabulary (see `_FDC_QUERY_ALIASES`)
        # BEFORE building the search string, so every use of `query` below --
        # the string actually sent to FDC, the relevance/head-noun check, and
        # the returned `FoodMatch.query` -- consistently reflects the SAME
        # vocabulary that was searched. `_KNOWN_UNRELIABLE_QUERIES` is
        # checked first (above) against the un-aliased identity so an
        # exclusion always wins regardless of whether an alias exists.
        query = _FDC_QUERY_ALIASES.get(query, query)

        # Appending the declared preparation word to the search string (not
        # the relevance/gating query, which stays the bare ingredient name)
        # measurably improves recall: confirmed live that FDC's own search
        # relevance for a bare grain/legume name (e.g. "brown rice") returns
        # 5 generic Branded results with no state-qualified record at all,
        # while "brown rice cooked" surfaces "Rice, brown, cooked, as
        # ingredient" within the same page size. `_is_relevant_match` (via
        # `_best_match`) is what keeps this safe -- it still rejects a
        # same-state wrong food (e.g. "black beans canned" surfacing a black
        # bean soup) rather than accepting anything state-tagged. The
        # `preparation` word is also folded into the payload-cache key this
        # way (via `search_query`), so a raw-gated and cooked-gated lookup of
        # the same ingredient are never conflated -- no separate cache-key
        # component is needed for it.
        search_query = f"{query} {preparation}" if preparation else query

        # Rejections seen during THIS call only (as opposed to
        # `self.rejection_counts`, cumulative across the whole run) -- used
        # purely to classify the terminal reason below, never to change
        # matching behavior.
        call_rejections: list[str] = []

        generic_payload = self._get_payload(search_query, _GENERIC_DATA_TYPES, _GENERIC_PAGE_SIZE)
        if generic_payload is not None:
            outcome = _best_match(generic_payload, query, preparation)
            if record_diagnostics:
                self.rejection_counts.update(outcome.rejections)
            call_rejections.extend(outcome.rejections)
            if outcome.match is not None:
                return outcome.match, REASON_GROUNDED

        branded_payload = self._get_payload(search_query, _BRANDED_DATA_TYPES, _BRANDED_PAGE_SIZE)
        if branded_payload is not None:
            branded_outcome = _select_branded_match(branded_payload, query, preparation)
            if record_diagnostics:
                self.rejection_counts.update(branded_outcome.rejections)
            call_rejections.extend(branded_outcome.rejections)
            if branded_outcome.dispersion is not None:
                min_kcal, max_kcal, count = branded_outcome.dispersion
                if record_diagnostics:
                    self.branded_dispersion_events.append((query, min_kcal, max_kcal, count))
            if branded_outcome.match is not None:
                return branded_outcome.match, REASON_GROUNDED

        reason = REASON_ALL_CANDIDATES_REJECTED if call_rejections else REASON_NO_RELEVANT_CANDIDATE
        return None, reason

    def _get_payload(
        self, search_query: str, data_types: list[str], page_size: int
    ) -> dict[str, Any] | None:
        """Payload cache in front of `_fetch_with_retry` -- see `FdcCache`.
        Caches the raw response for this exact request; never caches a
        `None` (fetch failure), so a transient outage gets a fresh attempt
        on the next run rather than being permanently remembered as empty.

        A cache hit is served without ever checking for an API key, so a
        fully-cached run (e.g. across process restarts, or in an environment
        with no live key configured at all) keeps working offline -- the key
        is only required to make an actual network request on a cache miss.
        """
        cached = self._cache.get_payload(search_query, data_types, page_size)
        if cached is not None:
            return cached
        if not self._settings.fdc_api_key:
            return None

        payload = self._fetch_with_retry(search_query, data_types, page_size)
        if payload is not None:
            self._cache.set_payload(search_query, data_types, page_size, payload)
        return payload

    def _fetch_with_retry(
        self, query: str, data_types: list[str], page_size: int = _GENERIC_PAGE_SIZE
    ) -> dict[str, Any] | None:
        last_error: str | None = None
        rate_limit_attempt = 0
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = self._session.get(
                    f"{self._settings.fdc_base_url.rstrip('/')}/foods/search",
                    params={
                        "api_key": self._settings.fdc_api_key,
                        "query": query,
                        "dataType": data_types,
                        "pageSize": page_size,
                    },
                    timeout=self._settings.model_timeout_seconds,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                if attempt < _MAX_ATTEMPTS - 1:
                    self._sleep(_RETRY_BACKOFF_SECONDS[attempt])
                continue

            # Rate-limit responses take their own bounded-retry-then-raise
            # path, entirely separate from the ordinary transient-failure
            # handling below -- see the module comment above
            # `_RATE_LIMIT_MAX_ATTEMPTS` for why a rate-limited call must
            # never degrade to `None`/"ungrounded" the way a genuine
            # transient failure does.
            if _is_rate_limited_response(response):
                if rate_limit_attempt < _RATE_LIMIT_MAX_ATTEMPTS - 1:
                    self._sleep(_RATE_LIMIT_BACKOFF_SECONDS[rate_limit_attempt])
                    rate_limit_attempt += 1
                    continue
                logger.error(
                    "USDA FDC rate limit exceeded for %r (dataType=%s) after %d attempts -- "
                    "stopping so a re-run (served by FdcCache for everything already fetched) "
                    "can resume once the hourly quota resets.",
                    query, data_types, rate_limit_attempt + 1,
                )
                raise UsdaRateLimitError(
                    f"USDA FDC rate limit exceeded for query {query!r} (dataType={data_types}) "
                    f"after {rate_limit_attempt + 1} attempts"
                )

            try:
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = str(exc)
            except ValueError as exc:
                last_error = f"invalid JSON: {exc}"

            if attempt < _MAX_ATTEMPTS - 1:
                self._sleep(_RETRY_BACKOFF_SECONDS[attempt])

        logger.warning(
            "USDA FDC search failed for %r (dataType=%s) after %d attempts: %s",
            query, data_types, _MAX_ATTEMPTS, last_error,
        )
        return None
