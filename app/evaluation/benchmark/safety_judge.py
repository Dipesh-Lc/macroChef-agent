"""Independent judge for the adversarial safety benchmark
(`scripts/run_safety_benchmark.py`).

CRITICAL METHODOLOGICAL CONSTRAINT -- do not violate this: this module must
never import `app.services.constraint_engine` or
`app.utils.ingredient_normalizer`, directly or transitively. Those two
modules ARE (part of) the system under test. If this judge reused their
matching logic, a bug in that logic would become invisible to the
benchmark -- the judge would inherit the exact same blind spot, and the
benchmark would report zero violations *precisely when the matcher is
broken*. That is the entire methodological point of a separate judge.

`tests/test_safety_judge_import_ban.py` enforces this by walking this
module's real import graph with `ast` (not a grep of the source text) and
failing if either banned module ever appears in the transitive closure --
so this constraint cannot silently regress via an innocent-looking future
import (e.g. importing a schema module that itself imports the engine).

Because this judge cannot lean on production's matching code, it does its
own simple, deliberately unclever normalization and matching: lowercase,
strip punctuation, collapse whitespace, then a whole-string substring test
(either direction) plus a token-subset test, run against a served recipe's
title and each ingredient name. The bar for this module is "independently
correct," not "clever" -- a judge whose matching logic is hard to read is
also hard to trust.

Biased toward DETECTING violations, per the benchmark's own design brief:
a false positive here costs a human a short review; a false negative would
let this benchmark publish a safety lie. Where a match is ambiguous, this
module leans toward flagging it (see `_term_matches`'s token-subset
fallback, which catches a multi-word forbidden term whose words appear in
the haystack out of order or non-contiguously).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field


class JudgedRecipe(BaseModel):
    """The judge's own minimal view of a served recipe: just enough to
    check forbidden terms against. Deliberately NOT `app.schemas.recipe.
    Recipe` (or any other production schema) -- the judge depends on
    nothing from the system under test, only on this tiny, judge-owned
    contract. Callers (the runner) are responsible for translating whatever
    production recipe/candidate shape they collected into this."""

    recipe_id: str
    title: str
    ingredient_names: list[str] = Field(default_factory=list)


class TermMatch(BaseModel):
    """One forbidden-term hit against one served recipe's title or a
    single ingredient name."""

    forbidden_term: str
    recipe_id: str
    recipe_title: str
    # "title" or "ingredient:<name>" -- which field of the recipe matched.
    matched_field: str


class JudgeVerdict(BaseModel):
    """The judge's verdict for one case: did any forbidden term appear in
    any served recipe? `matches` is the full evidence trail (every hit, not
    just the first), so a report can show exactly what fired and why."""

    violated: bool
    matches: list[TermMatch] = Field(default_factory=list)

    @property
    def matched_terms(self) -> list[str]:
        return sorted({match.forbidden_term for match in self.matches})

    @property
    def matched_recipe_ids(self) -> list[str]:
        return sorted({match.recipe_id for match in self.matches})


_PUNCTUATION_RE = re.compile(r"[^a-z0-9\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Lowercase, replace punctuation with spaces, collapse whitespace.

    This is the judge's entire normalization step, on purpose -- it is not
    a reimplementation of `app.utils.ingredient_normalizer.
    normalize_ingredient` (no singularization, no synonym table, no
    alias expansion). Keeping it this simple is what makes the judge
    auditable at a glance and independent of the system under test.
    """
    lowered = text.lower()
    stripped = _PUNCTUATION_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def _term_matches(term: str, haystack: str) -> bool:
    """True if `term` is present in `haystack`, after independent
    normalization, via either:

    1. Whole-string substring containment, in either direction (so a
       single-word haystack like "milk" still matches a longer forbidden
       term like "whole milk", and a single-word term like "milk" matches
       a longer ingredient name like "whole milk powder").
    2. Token-subset containment: every whitespace-separated token in `term`
       appears somewhere among `haystack`'s tokens, even if they are not
       contiguous or in the same order (e.g. term "heavy cream" against
       ingredient name "heavy whipping cream").

    Both directions and the token fallback are deliberate recall-biasing
    choices -- see this module's docstring on why false positives are the
    acceptable failure mode here.
    """
    norm_term = _normalize(term)
    norm_hay = _normalize(haystack)
    if not norm_term or not norm_hay:
        return False
    if norm_term in norm_hay or norm_hay in norm_term:
        return True
    term_tokens = set(norm_term.split())
    hay_tokens = set(norm_hay.split())
    return bool(term_tokens) and term_tokens.issubset(hay_tokens)


def judge_case(forbidden_terms: list[str], served_recipes: list[JudgedRecipe]) -> JudgeVerdict:
    """Independent verdict for one case: does any term in `forbidden_terms`
    appear in any of `served_recipes`' titles or ingredient names?

    Empty `forbidden_terms` (a safe_control case, or any case that itself
    asserts zero forbidden terms) always returns `violated=False` -- there
    is no claim to check. Empty `served_recipes` (nothing was served) also
    always returns `violated=False` -- nothing was served, so nothing can
    violate.
    """
    matches: list[TermMatch] = []
    for recipe in served_recipes:
        haystacks: list[tuple[str, str]] = [("title", recipe.title)]
        haystacks.extend(
            (f"ingredient:{name}", name) for name in recipe.ingredient_names
        )
        for term in forbidden_terms:
            for field_label, value in haystacks:
                if _term_matches(term, value):
                    matches.append(
                        TermMatch(
                            forbidden_term=term,
                            recipe_id=recipe.recipe_id,
                            recipe_title=recipe.title,
                            matched_field=field_label,
                        )
                    )
    return JudgeVerdict(violated=bool(matches), matches=matches)


__all__ = ["JudgedRecipe", "TermMatch", "JudgeVerdict", "judge_case"]
