"""Per-dataset adapters mapping a raw external record into a `RecipeCandidate`.

The import pipeline (`pipeline.py`) is dataset-agnostic: it only calls
`DatasetAdapter.read_raw` / `to_candidate`. Adding a new source dataset means
adding one adapter here, not touching the pipeline.

Safety note: allergens are always *derived* from ingredient names via
`derive_allergen_labels` (app/services/constraint_engine.py), never trusted
from a source-provided allergen/tag field — a dataset's own labeling isn't
something we can verify, and `Recipe.allergens` feeds diet-type checks and
Chroma index metadata downstream.
"""

from __future__ import annotations

import csv
import html
import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator
from uuid import NAMESPACE_URL, uuid5

from app.schemas.recipe_candidate import RecipeCandidate
from app.services.constraint_engine import derive_allergen_labels
from app.services.corpus_import.cuisine_tagger import resolve_cuisine, split_tag_field
from app.utils.quantity_parser import parse_quantity_string


class DatasetAdapter(ABC):
    """Maps one external dataset's raw rows into `RecipeCandidate`s."""

    dataset_name: str

    @abstractmethod
    def read_raw(self, source_path: Path) -> Iterator[dict]:
        """Yield one raw row (source column name -> value) per source record."""

    @abstractmethod
    def to_candidate(self, raw: dict) -> RecipeCandidate | None:
        """Map one raw row to a `RecipeCandidate`, or None if too structurally
        broken to attempt (e.g. no title, no ingredients). This is a cheap
        pre-filter; full contract/quality validation happens afterward via
        `RecipeValidationService`."""


# --- Food.com "Recipes and Reviews" adapter -------------------------------
#
# Column names confirmed against the live Kaggle dataset page (list-columns
# Images/Keywords/RecipeIngredientQuantities/RecipeIngredientParts/
# RecipeInstructions, R-vector-literal encoding, ISO 8601 durations for
# CookTime/PrepTime) -- irkaal/foodcom-recipes-and-reviews, CC0.

_R_VECTOR_ITEM = re.compile(r'"((?:[^"\\]|\\.)*)"')
_BARE_QUOTED_STRING = re.compile(r'^"((?:[^"\\]|\\.)*)"$')
_ISO_DURATION = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
_MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack", "dessert"}

# A meaningful minority of Food.com's RecipeInstructions steps carry personal/
# narrative commentary rather than functional instructions (e.g. "I don't
# actually use teaspoons for this... PATIENCE is the name of the game.").
# Imperative cooking steps ("Add", "Bake", "Whisk") essentially never use
# first person, so its presence is a strong, simple, deterministic signal of
# narrative content. Dropping the whole step (rather than trying to split out
# just the offending sentence, which risks producing garbled text on messy
# scraped input) is a deliberately conservative trade: it sometimes loses a
# step that mixed one aside with real functional content, but never emits
# broken prose. If cleaning drops a recipe below the 2-instruction minimum,
# RecipeValidationService already rejects it -- a reasonable outcome.
_FIRST_PERSON_PATTERN = re.compile(r"\b(i|i'm|i've|i'd|i'll|my|we|we're|we've|our)\b", re.IGNORECASE)
# Some source rows bake a redundant leading step number into the text itself
# (e.g. "2. Place apples..."), which would double up against our own step
# numbering downstream.
_LEADING_NUMBER_PREFIX = re.compile(r"^\s*\d+\.\s*")


def _strip_leading_number_prefix(step: str) -> str:
    return _LEADING_NUMBER_PREFIX.sub("", step, count=1).strip()


def _clean_instructions(steps: list[str]) -> tuple[list[str], int]:
    """Strip redundant leading numerals, then drop first-person (narrative)
    steps. Returns (cleaned_steps, narrative_steps_dropped_count)."""
    cleaned: list[str] = []
    dropped = 0
    for step in steps:
        step = _strip_leading_number_prefix(step)
        if not step:
            continue
        if _FIRST_PERSON_PATTERN.search(step):
            dropped += 1
            continue
        cleaned.append(step)
    return cleaned, dropped


def _parse_r_vector(text: str) -> list[str]:
    """Parse Food.com's R character-vector-literal fields, e.g. `c("a", "b")`.

    R's serialization omits the `c(...)` wrapper for length-1 vectors, writing
    just a bare quoted string (e.g. a single-step recipe's RecipeInstructions
    cell is `"Toast and grind..."`, not `c("Toast and grind...")`) -- handled
    as a dedicated case so the surrounding quote marks aren't left in as
    literal content. Falls back to comma-splitting for plain unquoted
    delimited text (covers simplified test fixtures and any export variant
    that isn't R-vector-encoded).
    """
    text = (text or "").strip()
    if not text:
        return []
    if text.startswith("c("):
        return [item.replace('\\"', '"') for item in _R_VECTOR_ITEM.findall(text)]
    bare_match = _BARE_QUOTED_STRING.match(text)
    if bare_match:
        return [bare_match.group(1).replace('\\"', '"')]
    return [part.strip() for part in text.split(",") if part.strip()]


def _parse_iso8601_duration_minutes(text: str | None) -> int | None:
    if not text:
        return None
    match = _ISO_DURATION.fullmatch(text.strip())
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    total = int(hours or 0) * 60 + int(minutes or 0) + (1 if seconds and int(seconds) >= 30 else 0)
    return total or None


def _safe_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _safe_int(value: str | None) -> int | None:
    parsed = _safe_float(value)
    return int(parsed) if parsed is not None else None


def _combine_ingredients(parts: list[str], quantities: list[str]) -> list[str]:
    """Zip Food.com's parallel quantity/name arrays into ingredient strings.

    Food.com's ingredient-part text almost never carries a unit: in the
    imported corpus, only 122 of 33,732 ingredient rows (verified 2026-07-17)
    parse out any unit at all (all of them "clove") -- the upstream dataset
    strips units from the part text (e.g. part="all-purpose flour",
    quantity="1/2" yields the dimensionless "1/2 all-purpose flour").
    Concatenating "{quantity} {part}" therefore reconstructs what the source
    actually provides -- a quantity with no unit -- not a full
    natural-language line. Imported quantities are dimensionless as a
    result; see README "Limitations" and docs/BACKLOG.md for the scoping
    decision.

    Deliberately does NOT filter out empty/blank parts here: an empty source
    entry becomes an empty-named `Ingredient` that flows through to
    `Recipe._drop_empty_ingredients` -- the single documented chokepoint for
    dropping+tallying empty ingredients (app/schemas/recipe.py). Filtering
    here instead would make that drop invisible to the pipeline's aggregate
    empty-ingredient count.
    """
    combined: list[str] = []
    for index, part in enumerate(parts):
        part = (part or "").strip()
        quantity = quantities[index].strip() if index < len(quantities) else ""
        if part and quantity and quantity.upper() != "NA":
            combined.append(f"{quantity} {part}")
        else:
            combined.append(part)
    return combined


def _map_category_to_meal_type(category: str | None) -> str | None:
    if not category:
        return None
    normalized = category.strip().lower()
    return normalized if normalized in _MEAL_TYPES else None


# Plural alias applied only inside `resolve_meal_type`'s fallback tiers
# (compound-split / keywords) below -- never applied to
# `_map_category_to_meal_type`'s own literal top-level check above, which
# stays exactly as it always was for backward compatibility. Exists because
# Food.com's own compound category value is "Lunch/Snacks" (verified in the
# scraped archive), whose second half is the plural "Snacks", not the
# singular "snack" `_MEAL_TYPES` uses.
_MEAL_TYPE_ALIASES = {"snacks": "snack"}


def _meal_type_token_match(token: str) -> str | None:
    normalized = token.strip().lower()
    if normalized in _MEAL_TYPES:
        return normalized
    return _MEAL_TYPE_ALIASES.get(normalized)


def resolve_meal_type(category: str | None, keywords: str | None) -> tuple[str | None, str]:
    """Returns `(meal_type, meal_type_source)`. Layered fallback, each tier
    only consulted if the previous one found nothing:

      1. `recipeCategory` literal exact match (pre-existing behavior, via
         `_map_category_to_meal_type`) -> "declared".
      2. `recipeCategory` split into "/"-or-","-joined tokens (e.g.
         "Lunch/Snacks" -> "Lunch") -> "recovered_tag".
      3. `keywords` field tokens -> "recovered_tag".

    No match at any tier -> `(None, "unknown")`. Verified against the full
    scraped archive (2026-07-27): Food.com's own taxonomy never carries a
    bare "Dinner"/"Lunch"/"Snack(s)" tag standalone -- only the compound
    "Lunch/Snacks" recipeCategory value and the 5-literal-word set
    `_MEAL_TYPES` already covers (breakfast/lunch/dinner/snack/dessert)."""
    declared = _map_category_to_meal_type(category)
    if declared:
        return declared, "declared"
    for token in split_tag_field(category):
        mapped = _meal_type_token_match(token)
        if mapped:
            return mapped, "recovered_tag"
    for token in split_tag_field(keywords):
        mapped = _meal_type_token_match(token)
        if mapped:
            return mapped, "recovered_tag"
    return None, "unknown"


class FoodComAdapter(DatasetAdapter):
    """Adapter for the Food.com "Recipes and Reviews" CC0-tagged dataset."""

    dataset_name = "foodcom_recipes_and_reviews"

    _COLUMN_ALIASES: dict[str, list[str]] = {
        "title": ["Name"],
        "cook_time": ["CookTime"],
        "servings": ["RecipeServings"],
        "category": ["RecipeCategory"],
        "ingredient_parts": ["RecipeIngredientParts"],
        "ingredient_quantities": ["RecipeIngredientQuantities"],
        "instructions": ["RecipeInstructions"],
        "calories": ["Calories"],
        "protein": ["ProteinContent"],
        "carbs": ["CarbohydrateContent"],
        "fat": ["FatContent"],
        "fiber": ["FiberContent"],
        "url": ["RecipeId"],
    }

    def __init__(self) -> None:
        # Aggregate stats for the instruction-cleaning pass, read by the
        # pipeline/CLI after a run to report the drop rate (per-run counters,
        # not persisted).
        self.narrative_steps_dropped = 0
        self.recipes_with_narrative_steps_dropped = 0
        # Recipes that end up with <2 instructions after cleaning, for ANY
        # reason (includes recipes that only ever had <2 raw steps -- those
        # were always going to fail RecipeValidationService's min-instructions
        # check regardless of this cleaning pass).
        self.recipes_below_min_instructions_after_cleaning = 0
        # The subset of the above that cleaning is actually responsible for:
        # had >=2 raw steps, but dropping narrative ones left <2. This is the
        # number that answers "false-positive collateral from the new
        # mechanism" -- the other case isn't a consequence of this change.
        self.recipes_rejected_because_of_cleaning = 0
        # Capped sample for eyeballing false positives, restricted to the
        # cleaning-caused subset above (not recipes that were always too short).
        self.example_dropped_below_min: list[dict] = []

    def read_raw(self, source_path: Path) -> Iterator[dict]:
        with Path(source_path).open("r", encoding="utf-8-sig", newline="") as handle:
            yield from csv.DictReader(handle)

    def to_candidate(self, raw: dict) -> RecipeCandidate | None:
        title = self._get(raw, "title")
        if not title or not title.strip():
            return None

        parts = _parse_r_vector(self._get(raw, "ingredient_parts") or "")
        quantities = _parse_r_vector(self._get(raw, "ingredient_quantities") or "")
        ingredient_texts = _combine_ingredients(parts, quantities)
        if len(ingredient_texts) < 3:
            return None

        raw_instructions = _parse_r_vector(self._get(raw, "instructions") or "")
        instructions, narrative_dropped = _clean_instructions(raw_instructions)
        self.narrative_steps_dropped += narrative_dropped
        if narrative_dropped:
            self.recipes_with_narrative_steps_dropped += 1
        if len(instructions) < 2:
            self.recipes_below_min_instructions_after_cleaning += 1
            cleaning_caused_it = len(raw_instructions) >= 2
            if cleaning_caused_it:
                self.recipes_rejected_because_of_cleaning += 1
            if cleaning_caused_it and len(self.example_dropped_below_min) < 10:
                self.example_dropped_below_min.append(
                    {
                        "title": title.strip(),
                        "original_instructions": raw_instructions,
                        "cleaned_instructions": instructions,
                    }
                )

        recipe_key = self._get(raw, "url") or title
        candidate_id = f"foodcom_{uuid5(NAMESPACE_URL, str(recipe_key)).hex[:16]}"

        ingredient_names = [parse_quantity_string(text)["name"] for text in ingredient_texts]
        allergens = derive_allergen_labels(ingredient_names)

        return RecipeCandidate(
            candidate_id=candidate_id,
            title=title.strip(),
            meal_type=_map_category_to_meal_type(self._get(raw, "category")),
            ingredients=ingredient_texts,  # bare strings; Ingredient coerces via parse_quantity_string
            instructions=instructions,
            cook_time_min=_parse_iso8601_duration_minutes(self._get(raw, "cook_time")),
            servings=_safe_int(self._get(raw, "servings")) or 1,
            calories=_safe_float(self._get(raw, "calories")),
            protein_g=_safe_float(self._get(raw, "protein")),
            carbs_g=_safe_float(self._get(raw, "carbs")),
            fat_g=_safe_float(self._get(raw, "fat")),
            fiber_g=_safe_float(self._get(raw, "fiber")),
            allergens=allergens,
            source_type="curated",
            source_name="Food.com (Recipes and Reviews)",
            source_url=str(recipe_key) if recipe_key else None,
        )

    def _get(self, raw: dict, key: str) -> str | None:
        for column in self._COLUMN_ALIASES[key]:
            if column in raw and raw[column] not in (None, ""):
                return raw[column]
        return None


# --- Food.com scraped-archive adapter --------------------------------------
#
# Reads `data/scraped/foodcom/*.md` -- one Markdown file per corpus recipe,
# produced by `scripts/scrape_recipe_pages.py` (a local-only, untracked
# scraper; see docs/BACKLOG.md) from the LIVE Food.com page (see
# `app.services.corpus_import.scraped_archive_format.render_markdown` for
# the exact writer). Each file carries a small YAML-style frontmatter block
# (foodcom_id, recipe_id, corpus, url, fetched_at_utc, http_status,
# scraper_version) followed by a fenced ```json block holding the page's raw
# schema.org Recipe JSON-LD -- the ONLY field this adapter reads ingredients/
# instructions/macros/servings from. The rendered Markdown body (Ingredients/
# Instructions/Nutrition sections) is a human-readable duplicate of the same
# JSON-LD and is never parsed here.
#
# This supersedes `FoodComAdapter` (the original Kaggle-CSV adapter) as the
# import path for this dataset: the archive is a per-recipe re-scrape of the
# SAME Food.com pages the CSV rows originally came from, with real
# amount+unit ingredient lines (the CSV's RecipeIngredientParts/Quantities
# columns had already stripped units -- see `_combine_ingredients`'s
# docstring above) and a machine-checkable JSON-LD source instead of R's
# character-vector serialization.


class ScrapedArchiveIntegrityError(RuntimeError):
    """Raised when an archive file fails a hard integrity check (bad HTTP
    status, unrecognized scraper version, unparseable JSON-LD, or an id that
    doesn't match what this adapter deterministically recomputes for it).

    Deliberately a hard abort, not a skip: every one of these conditions
    means the archive file cannot be trusted to represent what
    `scripts/scrape_recipe_pages.py` actually fetched, and importing 4,235
    files unattended must never silently drop or mis-id a recipe -- a
    skipped file would just look like "one fewer survivor" in the run
    report, indistinguishable from an ordinary validation rejection. See
    `docs/` corpus-import task spec (A1) for the pre-registered list of
    conditions this covers.
    """


_FRONTMATTER_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
_JSON_FENCE_RE = re.compile(r"```json\r?\n(.*?)\r?\n```", re.DOTALL)
_LEADING_INT_RE = re.compile(r"^\s*(\d+)")


def _parse_scraped_frontmatter(text: str, path: Path) -> dict[str, str]:
    """Parse the small, flat `key: value` frontmatter block written by
    `render_markdown` (see its module docstring) -- deliberately a
    hand-rolled parser rather than a PyYAML dependency, since the format is
    fully known and fixed (no nesting, no multi-line values, no lists)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ScrapedArchiveIntegrityError(f"{path}: missing opening '---' frontmatter delimiter")
    frontmatter: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return frontmatter
        match = _FRONTMATTER_LINE_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        frontmatter[key] = value
    raise ScrapedArchiveIntegrityError(f"{path}: missing closing '---' frontmatter delimiter")


def _extract_jsonld_block(text: str, path: Path) -> dict:
    match = _JSON_FENCE_RE.search(text)
    if not match:
        raise ScrapedArchiveIntegrityError(f"{path}: no fenced ```json Raw JSON-LD block found")
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ScrapedArchiveIntegrityError(f"{path}: unparseable JSON-LD block ({exc})") from exc
    if not isinstance(data, dict):
        raise ScrapedArchiveIntegrityError(f"{path}: JSON-LD block did not decode to a JSON object")
    return data


def _expected_scraped_recipe_id(dataset_name: str, foodcom_id: str) -> str:
    """Reproduces `pipeline._deterministic_import_id`'s seed for this
    dataset (`f"{dataset_name}:{source_url}:"` with `source_url=str(
    foodcom_id)`; `cuisine` is deliberately excluded from the seed, see
    `pipeline._deterministic_import_id`'s docstring) -- this is the id every
    archive file's own `recipe_id` frontmatter field must already equal,
    since these ids were originally minted by the CSV-adapter import that
    first produced the current corpus. Kept in lockstep with the pipeline's
    formula deliberately; see `FoodComScrapedArchiveAdapter`'s docstring."""
    seed = f"{dataset_name}:{foodcom_id}:"
    return f"imp_{uuid5(NAMESPACE_URL, seed).hex[:16]}"


def _read_scraped_archive_file(path: Path, dataset_name: str) -> dict:
    text = path.read_text(encoding="utf-8")
    frontmatter = _parse_scraped_frontmatter(text, path)

    foodcom_id = frontmatter.get("foodcom_id")
    if not foodcom_id:
        raise ScrapedArchiveIntegrityError(f"{path}: missing foodcom_id in frontmatter")

    http_status = frontmatter.get("http_status")
    if http_status != "200":
        raise ScrapedArchiveIntegrityError(
            f"{path}: http_status={http_status!r} (expected \"200\") -- refusing to import "
            "a non-ok scrape result"
        )

    scraper_version = frontmatter.get("scraper_version")
    if scraper_version != "1":
        raise ScrapedArchiveIntegrityError(
            f"{path}: scraper_version={scraper_version!r} (expected \"1\") -- unrecognized "
            "archive format, refusing to guess at its shape"
        )

    expected_id = _expected_scraped_recipe_id(dataset_name, foodcom_id)
    actual_id = frontmatter.get("recipe_id")
    if actual_id != expected_id:
        raise ScrapedArchiveIntegrityError(
            f"{path}: recipe_id mismatch for foodcom_id={foodcom_id!r} -- frontmatter says "
            f"{actual_id!r}, adapter computes {expected_id!r}. This id is the recipe's stable "
            "corpus identity; silently accepting either value risks minting a duplicate or "
            "orphaning an existing quarantine/index record."
        )

    jsonld = _extract_jsonld_block(text, path)

    return {
        "foodcom_id": foodcom_id,
        "recipe_id": actual_id,
        "corpus": frontmatter.get("corpus"),
        "jsonld": jsonld,
        "source_path": str(path),
    }


def _clean_scraped_ingredient(raw: object) -> str:
    """html.unescape + whitespace-collapse, and NOTHING else: the string
    stored on the resulting `Ingredient` (via `parse_quantity_string`, run
    automatically by `Ingredient`'s pydantic coercion) and the string fed to
    `derive_allergen_labels` below must be byte-identical, including any
    parenthetical descriptor text -- see `FoodComScrapedArchiveAdapter.
    to_candidate`'s docstring for why that matters for allergen safety."""
    return " ".join(html.unescape(str(raw)).split())


def _extract_instruction_texts(steps: list) -> tuple[list[str], int]:
    """Pulls step text out of a JSON-LD `recipeInstructions` list. Accepts
    both `HowToStep` dicts (`{"@type": "HowToStep", "text": "..."}`) and
    bare strings (schema.org allows either). A dict step with no `text` key
    is skipped (not coerced to `""`, which `_clean_instructions` would then
    also drop, but silently -- this way the drop is counted and visible).
    Each surviving step is `html.unescape`d before `_clean_instructions`
    ever sees it (advisor ruling, 2026-07-19 A1 revise round: the original
    ruling covered instructions too, not just title/ingredients -- an
    earlier pass of this adapter missed it). Returns
    (texts, missing_text_count)."""
    texts: list[str] = []
    missing = 0
    for step in steps:
        if isinstance(step, dict):
            text = step.get("text")
            if text is None:
                missing += 1
                continue
            texts.append(html.unescape(str(text)))
        else:
            texts.append(html.unescape(str(step)))
    return texts, missing


class FoodComScrapedArchiveAdapter(DatasetAdapter):
    """Adapter for the scraped Food.com archive (`data/scraped/foodcom/*.md`)
    -- see this module's "Food.com scraped-archive adapter" section comment
    above for the file format this reads.

    `dataset_name` is kept identical to `FoodComAdapter.dataset_name`
    ("foodcom_recipes_and_reviews") ON PURPOSE, even though the actual
    source is now the raw-page scrape rather than the original Kaggle CSV: a
    comment, not a bug. `pipeline._deterministic_import_id` seeds its uuid5
    on `f"{dataset_name}:{candidate.source_url or candidate.title}:"` (this
    adapter sets `source_url=str(foodcom_id)`) -- so reusing this exact
    string reproduces the EXISTING `imp_...` ids already in the
    corpus/quarantine sidecar/Chroma index, rather than minting a fresh id
    namespace that would orphan every existing reference. `candidate.cuisine`
    is deliberately EXCLUDED from that seed (2026-07-27, when cuisine
    recovery via `cuisine_tagger.resolve_cuisine` started letting this
    adapter emit a non-None cuisine): if cuisine were still part of the
    seed, a recipe's id would silently change every time its recovered
    cuisine value changed between reimport runs -- see
    `pipeline._deterministic_import_id`'s docstring for the full rationale.
    `read_raw` hard-verifies this per file (see
    `_expected_scraped_recipe_id`): if a file's own `recipe_id` frontmatter
    doesn't match what this formula recomputes, the import aborts rather
    than silently drifting the id space.

    Ingredient strings are used completely unmodified beyond
    html.unescape + whitespace-collapse (`_clean_scraped_ingredient`) --
    deliberately NOT the CSV adapter's amount/name-array zip
    (`_combine_ingredients`), and deliberately keeping parenthetical
    descriptor text (e.g. "butter (cut into pieces)") -- because the exact
    same string that ends up stored on the `Ingredient` (via
    `parse_quantity_string`, through pydantic's automatic coercion) is also
    what's fed to `derive_allergen_labels` below. Cleaning the two
    differently would open a gap where the stored ingredient name and the
    name used for allergen derivation silently diverge -- the LLM never
    enforces allergies and this adapter must not either, by parsing twice
    inconsistently.
    """

    dataset_name = "foodcom_recipes_and_reviews"

    def __init__(self) -> None:
        # Per-run counters, read by the CLI/report after a run (same idiom
        # as FoodComAdapter's narrative_steps_dropped etc. above).
        self.instructions_missing_text_dropped = 0
        self.recipes_with_missing_text_steps = 0
        self.servings_no_leading_digit = 0
        self.servings_coerced_from_zero = 0
        self.narrative_steps_dropped = 0
        self.recipes_with_narrative_steps_dropped = 0

    def read_raw(self, source_path: Path) -> Iterator[dict]:
        directory = Path(source_path)
        # Sort numerically by foodcom_id (every archive filename is a bare
        # numeric id, e.g. "100.md") so read order -- and therefore dedup's
        # order-sensitive first-seen-wins behavior -- is deterministic and
        # reproducible across re-runs, independent of filesystem iteration
        # order. `*.md` already excludes manifest.jsonl/scrape.log (neither
        # has a .md extension), so no separate skip is needed for those.
        paths = sorted(directory.glob("*.md"), key=lambda p: (not p.stem.isdigit(), p.stem.zfill(20)))
        for path in paths:
            yield _read_scraped_archive_file(path, self.dataset_name)

    def to_candidate(self, raw: dict) -> RecipeCandidate | None:
        jsonld = raw["jsonld"]
        foodcom_id = raw["foodcom_id"]

        name = jsonld.get("name")
        if not name or not str(name).strip():
            return None
        title = html.unescape(str(name)).strip()

        raw_ingredients = jsonld.get("recipeIngredient")
        ingredient_texts = [
            _clean_scraped_ingredient(item) for item in raw_ingredients if isinstance(raw_ingredients, list)
        ]

        raw_steps = jsonld.get("recipeInstructions") or []
        step_texts, missing_text = _extract_instruction_texts(raw_steps if isinstance(raw_steps, list) else [])
        if missing_text:
            self.instructions_missing_text_dropped += missing_text
            self.recipes_with_missing_text_steps += 1
        instructions, narrative_dropped = _clean_instructions(step_texts)
        self.narrative_steps_dropped += narrative_dropped
        if narrative_dropped:
            self.recipes_with_narrative_steps_dropped += 1

        nutrition = jsonld.get("nutrition") if isinstance(jsonld.get("nutrition"), dict) else {}

        # NEVER read description, review, or author fields -- none of those
        # are safety- or nutrition-relevant, and pulling from them risks
        # leaking review/author free text into the corpus. `keywords` IS
        # read (below): unlike description/review/author, it's Food.com's
        # own structured site-taxonomy tag field (comma-delimited category
        # tokens), not free text -- see cuisine_tagger.py's module
        # docstring for the cuisine/meal-type recovery this enables.
        ingredient_names = [parse_quantity_string(text)["name"] for text in ingredient_texts]
        allergens = derive_allergen_labels(ingredient_names)

        # meal_type/cuisine recovery from Food.com's own structured tag
        # fields (advisor revise, 2026-07-19, extended 2026-07-27):
        # meal_type is a Chroma `where` exact-match filter
        # (recipe_retriever.build_metadata_filter), so leaving it None for
        # the whole corpus would silently exclude every imported recipe
        # from any meal_type-filtered retrieval -- a functional regression,
        # not a cosmetic one. `recipeCategory` and `keywords` are bare
        # strings in the archive (verified empirically); defensively also
        # accept the schema.org-legal list form for `recipeCategory`, same
        # idiom as `_parse_servings` for `recipeYield`.
        raw_category = jsonld.get("recipeCategory")
        if isinstance(raw_category, list) and raw_category:
            raw_category = raw_category[0]
        raw_category = raw_category if isinstance(raw_category, str) else None

        raw_keywords = jsonld.get("keywords")
        if isinstance(raw_keywords, list) and raw_keywords:
            raw_keywords = ",".join(str(item) for item in raw_keywords)
        raw_keywords = raw_keywords if isinstance(raw_keywords, str) else None

        meal_type, meal_type_source = resolve_meal_type(raw_category, raw_keywords)
        cuisine, cuisine_source = resolve_cuisine(raw_category, raw_keywords, title)

        return RecipeCandidate(
            candidate_id=f"foodcom_scraped_{foodcom_id}",
            title=title,
            cuisine=cuisine,
            cuisine_source=cuisine_source,
            meal_type=meal_type,
            meal_type_source=meal_type_source,
            ingredients=ingredient_texts,  # bare strings; Ingredient coerces via parse_quantity_string
            instructions=instructions,
            cook_time_min=_parse_iso8601_duration_minutes(jsonld.get("cookTime")),
            servings=self._parse_servings(jsonld.get("recipeYield")),
            calories=_safe_float(nutrition.get("calories")),
            protein_g=_safe_float(nutrition.get("proteinContent")),
            carbs_g=_safe_float(nutrition.get("carbohydrateContent")),
            fat_g=_safe_float(nutrition.get("fatContent")),
            fiber_g=_safe_float(nutrition.get("fiberContent")),
            allergens=allergens,
            source_type="curated",
            source_name="Food.com (Recipes and Reviews)",
            source_url=str(foodcom_id),
        )

    def _parse_servings(self, recipe_yield: object) -> int:
        """Leading integer of `recipeYield` (e.g. "8 serving(s)" -> 8).

        `RecipeCandidate.servings` defaults to 1 and the pre-existing CSV
        adapter's `_safe_int(...) or 1` idiom would silently coerce EVERY
        recipe to servings=1 here (`recipeYield` is a free-text string like
        "8 serving(s)", never a bare int `_safe_int` can parse) -- this
        adapter reads the leading digits explicitly instead. No leading
        digit at all (e.g. a non-numeric yield string) falls back to 1 with
        `servings_no_leading_digit` counted; a leading "0" is coerced to 1
        with `servings_coerced_from_zero` counted (servings=0 would violate
        `RecipeCandidate.servings`'s `ge=1` constraint and is not a
        meaningful serving count regardless).
        """
        if isinstance(recipe_yield, str):
            text = recipe_yield
        elif isinstance(recipe_yield, list) and recipe_yield:
            text = str(recipe_yield[0])
        else:
            text = ""

        match = _LEADING_INT_RE.match(text)
        if not match:
            self.servings_no_leading_digit += 1
            return 1
        value = int(match.group(1))
        if value == 0:
            self.servings_coerced_from_zero += 1
            return 1
        return value
