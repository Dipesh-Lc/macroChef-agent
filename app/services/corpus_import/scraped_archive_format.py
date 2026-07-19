"""Render a single scraped Food.com recipe (JSON-LD + fetch metadata) into
a lossless, human-readable Markdown document.

This is the canonical writer for the `data/scraped/foodcom/*.md` archive
format that `FoodComScrapedArchiveAdapter` (app/services/corpus_import/
adapters.py) reads. It lives in `corpus_import` -- not in the (untracked,
local-only) `app.services.recipe_scraping` scraper package -- so that the
tracked import pipeline and its tests never depend on code that isn't part
of the committed tree. `app.services.recipe_scraping.markdown_doc`
re-exports `render_markdown` from here for the scraper's own use; the
dependency arrow points from the scraper to `corpus_import`, never the
reverse.

No corpus/schema coupling beyond that on purpose -- this module only
produces/reproduces the raw archive Markdown text; nothing here writes into
`app/schemas` or the recipe corpus directly.
"""

import json
import re

_DURATION_PATTERN = re.compile(
    r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)


def humanize_duration(iso: str | None) -> str | None:
    """Render an ISO-8601 duration (e.g. "PT1H25M") as "1 h 25 min".

    Returns `None` for `None`/empty/unparseable input. `"PT0S"` renders as
    "0 min" (rather than an empty string) so a genuinely-zero duration is
    still shown, not confused with "absent".
    """
    if not iso:
        return None
    match = _DURATION_PATTERN.match(iso.strip())
    if not match:
        return None

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)

    if hours == 0 and minutes == 0 and seconds == 0:
        return "0 min"

    parts = []
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    if seconds:
        parts.append(f"{seconds} sec")
    return " ".join(parts)


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _format_author(author: object) -> str | None:
    if isinstance(author, dict):
        name = author.get("name")
        return _collapse_whitespace(str(name)) if name else None
    if isinstance(author, str) and author.strip():
        return _collapse_whitespace(author)
    return None


def _format_time_line(label: str, iso: object) -> str | None:
    if not isinstance(iso, str) or not iso.strip():
        return None
    humanized = humanize_duration(iso)
    if humanized is None:
        return f"- **{label}:** {iso}"
    return f"- **{label}:** {iso} ({humanized})"


def _yaml_scalar(value: object) -> str:
    """Render a value as a bare YAML scalar (no quoting) -- callers only
    use this for values already known to be YAML-safe (no leading/trailing
    whitespace, no embedded "': '" sequence)."""
    return "" if value is None else str(value)


def render_markdown(jsonld: dict, meta: dict) -> str:
    """Render the full per-recipe Markdown document.

    `jsonld` is the schema.org Recipe dict (from `foodcom.extract_recipe_
    jsonld`). `meta` carries fetch/provenance fields: `foodcom_id,
    recipe_id, corpus, url, fetched_at_utc, http_status`.
    """
    lines: list[str] = []

    # --- YAML frontmatter ---
    lines.append("---")
    lines.append("source: food.com")
    lines.append(f'foodcom_id: "{meta.get("foodcom_id", "")}"')
    lines.append(f"recipe_id: {_yaml_scalar(meta.get('recipe_id'))}")
    lines.append(f"corpus: {_yaml_scalar(meta.get('corpus'))}")
    lines.append(f"url: {_yaml_scalar(meta.get('url'))}")
    lines.append(f"fetched_at_utc: {_yaml_scalar(meta.get('fetched_at_utc'))}")
    lines.append(f"http_status: {_yaml_scalar(meta.get('http_status'))}")
    lines.append("scraper_version: 1")
    lines.append("---")
    lines.append("")

    # --- Title / description ---
    name = jsonld.get("name") or "(untitled)"
    lines.append(f"# {name}")
    lines.append("")

    description = jsonld.get("description")
    if isinstance(description, str) and description.strip():
        lines.append(f"> {_collapse_whitespace(description)}")
        lines.append("")

    # --- Metadata bullets ---
    meta_lines: list[str] = []
    author = _format_author(jsonld.get("author"))
    if author:
        meta_lines.append(f"- **Author:** {author}")

    published = jsonld.get("datePublished")
    if isinstance(published, str) and published.strip():
        meta_lines.append(f"- **Published:** {published}")

    yield_ = jsonld.get("recipeYield")
    if isinstance(yield_, str) and yield_.strip():
        meta_lines.append(f"- **Yield:** {yield_}")
    elif isinstance(yield_, list) and yield_:
        meta_lines.append(f"- **Yield:** {', '.join(str(item) for item in yield_)}")

    for label, key in (("Prep time", "prepTime"), ("Cook time", "cookTime"), ("Total time", "totalTime")):
        time_line = _format_time_line(label, jsonld.get(key))
        if time_line:
            meta_lines.append(time_line)

    category = jsonld.get("recipeCategory")
    if isinstance(category, str) and category.strip():
        meta_lines.append(f"- **Category:** {category}")
    elif isinstance(category, list) and category:
        meta_lines.append(f"- **Category:** {', '.join(str(item) for item in category)}")

    keywords = jsonld.get("keywords")
    if isinstance(keywords, str) and keywords.strip():
        meta_lines.append(f"- **Keywords:** {keywords}")
    elif isinstance(keywords, list) and keywords:
        meta_lines.append(f"- **Keywords:** {', '.join(str(item) for item in keywords)}")

    if meta_lines:
        lines.extend(meta_lines)
        lines.append("")

    # --- Ingredients ---
    ingredients = jsonld.get("recipeIngredient")
    if isinstance(ingredients, list) and ingredients:
        lines.append("## Ingredients")
        lines.append("")
        for item in ingredients:
            lines.append(f"- {_collapse_whitespace(str(item))}")
        lines.append("")

    # --- Instructions ---
    instructions = jsonld.get("recipeInstructions")
    if isinstance(instructions, list) and instructions:
        lines.append("## Instructions")
        lines.append("")
        for index, step in enumerate(instructions, start=1):
            if isinstance(step, dict):
                text = step.get("text", "")
            else:
                text = str(step)
            lines.append(f"{index}. {_collapse_whitespace(str(text))}")
        lines.append("")

    # --- Nutrition ---
    nutrition = jsonld.get("nutrition")
    if isinstance(nutrition, dict) and nutrition:
        rows = [(key, value) for key, value in nutrition.items() if key != "@type"]
        if rows:
            lines.append("## Nutrition (as displayed, per serving)")
            lines.append("")
            lines.append("| Field | Value |")
            lines.append("| --- | --- |")
            for key, value in rows:
                lines.append(f"| {key} | {value} |")
            lines.append("")

    # --- Raw JSON-LD (lossless record, always present) ---
    lines.append("## Raw JSON-LD")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(jsonld, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)
