import re
import time
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


def _best_match(payload: dict[str, Any], query: str, preparation: str | None = None) -> FoodMatch | None:
    """Pick the top-ranked food with usable macros, gated by relevance and by
    `preparation` when given.

    Every candidate must pass `_is_relevant_match` against `query` -- a
    candidate that is a different or derived food (see its docstring) is
    skipped regardless of rank. When `preparation` is set, a candidate is
    additionally only eligible if its description classifies to that exact
    state (see `_classify_preparation`) -- an unclassifiable or
    differently-stated candidate is skipped even if it would otherwise rank
    first, so a declared-cooked ingredient can never resolve to a raw record
    (or vice versa). If nothing in the ranked list matches, this returns None
    (ungrounded) rather than falling back to the best unrelated candidate.
    """
    foods = payload.get("foods") or []
    ranked = sorted(foods, key=lambda food: _DATA_TYPE_PRIORITY.get(food.get("dataType"), 99))
    for food in ranked:
        description = food.get("description", "")
        if not _is_relevant_match(query, description, preparation):
            continue
        if preparation is not None and _classify_preparation(description) != preparation:
            continue
        macros = _extract_macros(food)
        if macros is None:
            continue
        return FoodMatch(
            fdc_id=food["fdcId"],
            description=description,
            data_type=food.get("dataType", ""),
            macros=macros,
            query=query,
        )
    return None


# Queries where the general mechanism (relevance check + preparation gate)
# reliably lands on a wrong-form or untrustworthy record, confirmed by manual
# review against real-world reference values (item 1.4 Step B closeout) --
# and where no honest `preparation` declaration fixes it, unlike the
# grain/legume/meat cases the field was built for:
#   - "shrimp": no relevant Foundation/SR Legacy/Survey record exists even
#     with preparation="raw"; the best available match is a Branded "RAW
#     SHRIMP" at 71 kcal/100g against a true range of ~85-99 kcal/100g --
#     not accurate enough to trust.
#   - "tomato sauce": matches a Branded "chili sauce" variant (92 kcal/100g)
#     instead of plain tomato sauce (~24-35 kcal/100g). A sauce has no
#     raw/cooked/canned state to declare, so this mismatch can't be gated the
#     way grain/legume/meat state ambiguity is.
#   - "chili powder" / "ginger": the only reachable Branded record for each
#     reports 0 kcal/100g -- a data defect (no real spice is calorie-free),
#     not a wrong-form match, so `preparation` gating doesn't apply. A
#     confidently-wrong zero is worse than an honest unknown.
# Deliberately narrow and disclosed rather than a general rule change with
# unclear corpus-wide blast radius -- an honest "we checked, don't trust
# this" list, not an attempt to force a match either way. Keyed by the exact
# normalized query (see `normalize_ingredient`).
_KNOWN_UNRELIABLE_QUERIES = {"shrimp", "tomato sauce", "chili powder", "ginger"}


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

        cache_key = query if preparation is None else f"{query}::{preparation}"

        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        if self._cache.is_confirmed_no_match(cache_key):
            return None

        if not self._settings.fdc_api_key:
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
        # bean soup) rather than accepting anything state-tagged.
        search_query = f"{query} {preparation}" if preparation else query

        generic_payload = self._fetch_with_retry(search_query, _GENERIC_DATA_TYPES)
        match = _best_match(generic_payload, query, preparation) if generic_payload is not None else None

        branded_payload = None
        if match is None:
            branded_payload = self._fetch_with_retry(search_query, _BRANDED_DATA_TYPES)
            match = _best_match(branded_payload, query, preparation) if branded_payload is not None else None

        if match is not None:
            self._cache.set(cache_key, match)
            return match

        # A confirmed negative requires BOTH tiers to have actually completed
        # (not a retry-exhausted transient failure) and found nothing --
        # otherwise a momentary outage on either tier would get permanently
        # cached as "no match" for an ingredient that was never really looked
        # at. If either tier's fetch failed outright, this stays uncached so
        # a future run gets a fresh attempt.
        if generic_payload is not None and branded_payload is not None:
            self._cache.set_no_match(cache_key)
        return None

    def _fetch_with_retry(self, query: str, data_types: list[str]) -> dict[str, Any] | None:
        last_error: str | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = self._session.get(
                    f"{self._settings.fdc_base_url.rstrip('/')}/foods/search",
                    params={
                        "api_key": self._settings.fdc_api_key,
                        "query": query,
                        "dataType": data_types,
                        "pageSize": 5,
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
