"""Schema for the adversarial safety benchmark case set (300-500 cases).

Design constraint (advisor methodology ruling, see the Phase-2 benchmark task
spec): MacroChef has **no conversational allergy intake**. Allergies enter as
structured `UserProfile.allergies` fields (see `frontend/components/
profile_form.py`), never through chat -- the LLM here only ever touches
inventory extraction from free text/images and explanation phrasing. That
makes "run the identical conversation through both systems" impossible for a
raw-LLM-vs-MacroChef comparison, and faking a conversational MacroChef to make
the comparison look symmetric would be dishonest.

So every case below carries **both** renderings:

- `conversation` -- the transcript, driven through the raw-LLM comparison
  arm(s) exactly as written.
- `structured_rendering` -- the faithful structured form MacroChef actually
  consumes: profile fields (`allergies`, `diet_type`, `macro_targets`), plus
  any contradiction/injection payload delivered through MacroChef's *real*
  free-text surfaces (`typed_ingredients`, `inventory_text`). A case is not
  well-formed unless both renderings express the same adversarial content in
  the surface each system actually exposes.

This module defines the case shape only. It intentionally does NOT import
from `app.services` or `app.utils` -- ground truth (`forbidden_terms`) must be
derived from an external authority (see `SourceCitation`) and never
reverse-engineered from the implementation under test. That independence is
what lets this benchmark judge the constraint engine rather than just
re-deriving it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Every category the case set must cover. This is a closed set on purpose --
# adding a category is a schema change, not a per-case authoring choice.
CaseCategory = Literal[
    "hidden_allergen",
    "derivative_name",
    "stated_then_contradicted",
    "diet_trap",
    "prompt_injection",
    "safe_control",
    "multi_constraint",
    "morphology",
    "macro_trap",
]

# Stable case_id prefix per category, enforced by BenchmarkCase's validator.
# Kept as an explicit mapping (rather than e.g. truncating the category name)
# so the prefix stays stable even if a category name is ever reworded.
CATEGORY_ID_PREFIXES: dict[str, str] = {
    "hidden_allergen": "hidden",
    "derivative_name": "derivative",
    "stated_then_contradicted": "contradicted",
    "diet_trap": "diet",
    "prompt_injection": "injection",
    "safe_control": "safe",
    "multi_constraint": "multi",
    "morphology": "morphology",
    "macro_trap": "macro",
}

# The one category where "the correct answer is to serve" -- every other
# category asserts that some set of forbidden terms must never reach a
# served recommendation's ingredients.
SAFE_CONTROL_CATEGORY = "safe_control"

ExecutionSurface = Literal["recommendation_graph", "discovery"]


class ConversationTurn(BaseModel):
    """One turn of the transcript rendering, for the raw-LLM comparison arm(s)."""

    role: Literal["user", "assistant"]
    content: str


class StructuredRendering(BaseModel):
    """The faithful MacroChef-native rendering of the same case.

    Every field here maps onto a real MacroChef input surface:
    `allergies` / `diet_type` / `macro_targets` -> `UserProfile` fields
    (structured intake, never chat); `typed_ingredients` /
    `inventory_text` -> the free-text surfaces the LLM inventory-extraction
    step actually parses. A contradiction or injection payload belongs in
    `typed_ingredients` or `inventory_text`, never smuggled into `allergies`
    itself -- that would test something MacroChef doesn't do.
    """

    allergies: list[str] = Field(default_factory=list)
    diet_type: str | None = None
    typed_ingredients: list[str] = Field(default_factory=list)
    inventory_text: str | None = None
    macro_targets: dict | None = None


class SourceCitation(BaseModel):
    """External authority backing this case's `forbidden_terms` ground truth.

    Required for every non-control case so ground truth is auditable against
    something outside this repo (an allergen-derivative reference, an
    ingredient-morphology database, a diet-definition standard, etc.) --
    never reverse-engineered from `app.services.constraint_engine` or
    `app.utils.ingredient_normalizer`.
    """

    source: str
    url: str
    quote: str


class BenchmarkCase(BaseModel):
    case_id: str
    category: CaseCategory
    conversation: list[ConversationTurn]
    structured_rendering: StructuredRendering
    # The externally-sourced derivative/synonym/ingredient list this case
    # asserts must never appear among a served recommendation's ingredients.
    # Empty iff expected_safe is True (see validator below).
    forbidden_terms: list[str] = Field(default_factory=list)
    # True only for safe_control cases: the correct system behavior is to
    # SERVE a recommendation, not to refuse/flag it.
    expected_safe: bool
    surfaces: list[ExecutionSurface]
    source_citation: SourceCitation | None = None
    # Optional: pins real corpus recipe ids for morphology cases that need a
    # specific recipe's ingredient list rather than whatever gets retrieved.
    pinned_recipe_ids: list[str] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_forbidden_terms_matches_expected_safe(self) -> "BenchmarkCase":
        if self.expected_safe and self.forbidden_terms:
            raise ValueError(
                f"{self.case_id}: expected_safe=True but forbidden_terms is "
                f"non-empty ({self.forbidden_terms!r}). A safe-control case "
                "asserts nothing is forbidden."
            )
        if not self.expected_safe and not self.forbidden_terms:
            raise ValueError(
                f"{self.case_id}: expected_safe=False but forbidden_terms is "
                "empty. Every unsafe case must name at least one term that "
                "must never appear in a served recommendation."
            )
        return self

    @model_validator(mode="after")
    def _validate_source_citation_required_for_non_control(self) -> "BenchmarkCase":
        if self.category != SAFE_CONTROL_CATEGORY and self.source_citation is None:
            raise ValueError(
                f"{self.case_id}: category {self.category!r} requires a "
                "source_citation (ground truth must be traceable to an "
                "external authority); only safe_control cases may omit it."
            )
        return self

    @model_validator(mode="after")
    def _validate_case_id_matches_category_prefix(self) -> "BenchmarkCase":
        expected_prefix = CATEGORY_ID_PREFIXES[self.category]
        if not self.case_id.startswith(f"{expected_prefix}_"):
            raise ValueError(
                f"{self.case_id}: case_id must start with {expected_prefix!r}_ "
                f"for category {self.category!r} (got {self.case_id!r})."
            )
        return self

    @model_validator(mode="after")
    def _validate_surfaces_non_empty(self) -> "BenchmarkCase":
        if not self.surfaces:
            raise ValueError(f"{self.case_id}: surfaces must be non-empty.")
        return self
