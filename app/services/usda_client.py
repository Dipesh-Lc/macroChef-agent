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
    return FoodMacros(
        calories=calories,
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fat,
        fiber_g=fiber,
    )


# Page sizes for each fetch tier. Generic stays at 5 (unchanged from item
# 1.4 -- generic dataTypes are a small, curated catalog where the top few
# relevance-ranked hits are enough). Branded's default tier-1 page size also
# stays 5 for now; item 4/P5 widens the Branded fetch specifically (a much
# larger, noisier catalog where a single record's calorie value is not
# reliable enough to trust without corroboration -- see `_select_branded_match`).
_GENERIC_PAGE_SIZE = 5
_BRANDED_PAGE_SIZE = 5

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
    """

    match: FoodMatch | None
    rejections: list[str] = field(default_factory=list)


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
#   - kcal < 5 or kcal > 950: outside any real whole food's per-100g range
#     (950 comfortably covers pure fats/oils at ~884-900; 5 excludes "0 kcal"
#     data defects like the ginger/chili powder case while still allowing a
#     genuinely near-zero-calorie item like plain water or ice).
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
_PLAUSIBLE_MIN_KCAL = 5.0
_PLAUSIBLE_MAX_KCAL = 950.0
_PLAUSIBLE_MAX_MACRO_MASS_G = 105.0
_ATWATER_RATIO_LOW = 0.5
_ATWATER_RATIO_HIGH = 1.7
_ATWATER_ABSOLUTE_ESCAPE_KCAL = 25.0


def _plausibility_reject_reason(macros: FoodMacros) -> str | None:
    """Returns a reason code if `macros` fails the absolute-plausibility
    gate, else `None`. See the gate's module-level comment for the bounds
    and their rationale."""
    if macros.calories < _PLAUSIBLE_MIN_KCAL:
        return "kcal_too_low"
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

        reject_reason = _plausibility_reject_reason(macros)
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
        # Cumulative, diagnostic-only tally of candidate-rejection reasons
        # (see `MatchOutcome.rejections`) across every `search_food` call made
        # through this client instance -- read by `grounding_job.run_grounding`
        # after a full corpus pass to report "N candidates rejected for
        # reason X" corpus-wide. Never consulted by matching logic itself.
        self.rejection_counts: Counter[str] = Counter()

    def search_food(self, name: str, *, preparation: str | None = None) -> FoodMatch | None:
        """Look up macros for `name`, optionally gated to a declared `preparation`
        ("raw" / "cooked" / "canned" -- see `Ingredient.preparation`).

        The cache key includes `preparation` so a raw-gated and cooked-gated
        lookup of the same ingredient are never conflated.
        """
        query = normalize_ingredient(name)
        if not query:
            return None
        if query in _KNOWN_UNRELIABLE_QUERIES:
            return None

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

        generic_payload = self._get_payload(search_query, _GENERIC_DATA_TYPES, _GENERIC_PAGE_SIZE)
        if generic_payload is not None:
            outcome = _best_match(generic_payload, query, preparation)
            self.rejection_counts.update(outcome.rejections)
            if outcome.match is not None:
                return outcome.match

        branded_payload = self._get_payload(search_query, _BRANDED_DATA_TYPES, _BRANDED_PAGE_SIZE)
        if branded_payload is not None:
            branded_outcome = _best_match(branded_payload, query, preparation)
            self.rejection_counts.update(branded_outcome.rejections)
            if branded_outcome.match is not None:
                return branded_outcome.match

        return None

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
