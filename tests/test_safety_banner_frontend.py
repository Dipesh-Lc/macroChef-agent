"""C2: "make safety visible" -- frontend display-only safety-filter status.

Exercises the real production functions
(`components.safety_banner.safety_banner_markup` /
`components.safety_banner.excluded_recipe_lines`) rather than a
reimplementation, mirroring the pattern in `test_restored_badge_frontend.py`
/ `test_grounding_badge_frontend.py` / `test_taste_profile_frontend.py`.

The underlying data (`rejected_recipes`, shaped like
`app.schemas.recommendation.RejectedRecipe`) is computed deterministically by
`app.services.constraint_engine.validate_recipe` -- the LLM never sees or
decides this value, and `components.safety_banner` only ever counts/labels
and renders it, never computes it. See that module's docstring for the exact
`RejectedRecipe.reason` strings this test data is modeled on.
"""

import inspect
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

import components.safety_banner as safety_banner_module  # noqa: E402
from components.safety_banner import (  # noqa: E402
    excluded_recipe_lines,
    safety_banner_markup,
)

MALICIOUS_TITLE = "<script>alert(1)</script>"


def _rejected(recipe_id: str, title: str, reason: str) -> dict:
    return {"recipe_id": recipe_id, "title": title, "reason": reason}


def test_groups_and_counts_multiple_reason_types() -> None:
    rejected = [
        _rejected("r1", "Peanut Noodles", "Contains a user allergen"),
        _rejected("r2", "Shrimp Curry", "Contains a user allergen"),
        _rejected("r3", "Bacon Salad", "Violates diet type: vegetarian"),
        _rejected("r4", "Beef Stew", "Violates diet type: vegetarian"),
        _rejected("r5", "Beef Chili", "Violates diet type: vegetarian"),
    ]

    markup = safety_banner_markup(rejected)

    assert markup.startswith("Filtered deterministically: ")
    assert "2 recipes excluded for an allergy" in markup
    assert "3 excluded for not being vegetarian" in markup
    # Only one "recipes" appears -- the second clause drops the repeated noun
    # (matches the roadmap's illustrative "N recipes excluded for X, M
    # excluded for Y" shape).
    assert markup.count(" recipes excluded for") == 1


def test_singular_recipe_uses_singular_noun_in_first_clause() -> None:
    # Single recipe excluded should render "1 recipe excluded..." not "1 recipes excluded..."
    rejected = [_rejected("r1", "Peanut Noodles", "Contains a user allergen")]

    markup = safety_banner_markup(rejected)

    assert "1 recipe excluded for an allergy" in markup
    # Ensure plural form is NOT used for count of 1
    assert "1 recipes excluded" not in markup


def test_all_four_known_reason_categories_are_labeled_distinctly() -> None:
    rejected = [
        _rejected("r1", "A", "Contains a user allergen"),
        _rejected("r2", "B", "Contains a disliked ingredient"),
        _rejected("r3", "C", "Violates diet type: vegan"),
        _rejected("r4", "D", "Exceeds maximum cooking time"),
    ]

    markup = safety_banner_markup(rejected)

    assert "an allergy" in markup
    assert "a disliked ingredient" in markup
    assert "not being vegan" in markup
    assert "exceeding your time limit" in markup


def test_unknown_reason_is_echoed_honestly_not_dropped_or_fabricated() -> None:
    rejected = [_rejected("r1", "Mystery Dish", "Some future reason constraint_engine might add")]

    markup = safety_banner_markup(rejected)

    assert "Some future reason constraint_engine might add" in markup


def test_zero_rejections_renders_an_honest_zero_count() -> None:
    markup = safety_banner_markup([])

    assert markup == "Filtered deterministically: 0 recipes excluded by your allergy, diet, and time filters."


def test_never_shows_a_zero_count_for_a_category_that_did_not_occur() -> None:
    # Only "Contains a user allergen" occurred -- the summary must never
    # mention "0 excluded for not being vegetarian" or any other category
    # that had zero occurrences.
    rejected = [_rejected("r1", "A", "Contains a user allergen")]

    markup = safety_banner_markup(rejected)

    assert "0 " not in markup
    assert "vegetarian" not in markup
    assert "vegan" not in markup
    assert "time limit" not in markup
    assert "disliked ingredient" not in markup


def test_recipe_titles_are_html_escaped_in_the_detail_lines() -> None:
    rejected = [_rejected("r1", MALICIOUS_TITLE, "Contains a user allergen")]

    lines = excluded_recipe_lines(rejected)

    assert "<script>alert(1)</script>" not in lines
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in lines


def test_unrecognized_reason_text_is_html_escaped_too() -> None:
    rejected = [_rejected("r1", "Fine Title", MALICIOUS_TITLE)]

    markup = safety_banner_markup(rejected)
    lines = excluded_recipe_lines(rejected)

    assert "<script>alert(1)</script>" not in markup
    assert "<script>alert(1)</script>" not in lines


def test_signature_takes_only_a_structured_list_never_a_string_or_llm_object() -> None:
    """Proves this function's only possible input is the structured
    `RejectedRecipe`-shaped list -- never a bare string or an LLM response
    object -- so an LLM can never influence this text's content, only the
    deterministic `constraint_engine.validate_recipe` output can.
    """
    signature = inspect.signature(safety_banner_markup)
    (only_param,) = signature.parameters.values()

    annotation = str(only_param.annotation)
    assert "list" in annotation
    assert annotation != "str"
    assert "str" != only_param.annotation

    # A bare string is deliberately the wrong shape: iterating a string
    # yields characters, and `.get` (used on every item inside the
    # function) does not exist on `str` -- so passing a string blows up
    # immediately rather than silently rendering LLM-authored free text.
    import pytest

    with pytest.raises(AttributeError):
        safety_banner_markup("not a structured list, e.g. raw LLM output")


def test_module_imports_no_llm_client() -> None:
    # Structural guard: this module must never gain a path to an LLM
    # provider. If this ever fails, whatever new import triggered it needs
    # its own safety review before landing.
    source = Path(safety_banner_module.__file__).read_text(encoding="utf-8")
    forbidden = ["openai", "google.genai", "google_genai", "anthropic"]
    for name in forbidden:
        assert name not in source, f"safety_banner.py must not import {name!r}"
