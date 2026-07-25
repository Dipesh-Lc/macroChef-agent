"""Unit tests for app.schemas.user -- specifically validate_diet_type_value,
extracted from UserProfile's own field_validator so app.schemas.
recipe_search.RecipeSearchRequest can reuse the exact same intake-time check
(see that schema's docstring) instead of a second, independently-drifting
diet_type validator.

test_user_profile_diet_type_validation_unchanged_after_extraction is the
regression test proving the extraction was behavior-preserving: UserProfile
must still accept/reject diet_type values exactly as it did before
validate_diet_type_value existed as a standalone function (see
tests/test_constraint_engine.py's pre-existing
test_unsupported_diet_type_rejected_at_profile_intake, which continues to
pass unchanged and is not duplicated here).
"""

import pytest
from pydantic import ValidationError

from app.schemas.user import (
    NO_RESTRICTION_DIET_TYPES,
    SUPPORTED_DIET_TYPES,
    MacroTargets,
    UserProfile,
    validate_diet_type_value,
)


# ---------------------------------------------------------------------------
# validate_diet_type_value, standalone.
# ---------------------------------------------------------------------------


def test_validate_diet_type_value_returns_none_for_none() -> None:
    assert validate_diet_type_value(None) is None


@pytest.mark.parametrize("diet_type", sorted(SUPPORTED_DIET_TYPES))
def test_validate_diet_type_value_accepts_every_supported_diet_type(diet_type: str) -> None:
    assert validate_diet_type_value(diet_type) == diet_type


@pytest.mark.parametrize("diet_type", sorted(NO_RESTRICTION_DIET_TYPES))
def test_validate_diet_type_value_accepts_every_no_restriction_alias(diet_type: str) -> None:
    assert validate_diet_type_value(diet_type) == diet_type


def test_validate_diet_type_value_is_case_and_whitespace_insensitive() -> None:
    assert validate_diet_type_value("  VeGaN  ") == "  VeGaN  "


@pytest.mark.parametrize("diet_type", ["halal", "keto", "paleo", "pescatarian"])
def test_validate_diet_type_value_rejects_unsupported_diet_type(diet_type: str) -> None:
    with pytest.raises(ValueError):
        validate_diet_type_value(diet_type)


# ---------------------------------------------------------------------------
# UserProfile still validates identically after the extraction.
# ---------------------------------------------------------------------------


def test_user_profile_accepts_every_supported_diet_type() -> None:
    for diet_type in sorted(SUPPORTED_DIET_TYPES):
        profile = UserProfile(user_id="u", macro_targets=MacroTargets(), diet_type=diet_type)
        assert profile.diet_type == diet_type


def test_user_profile_diet_type_validation_unchanged_after_extraction() -> None:
    # Same assertion as tests/test_constraint_engine.py's
    # test_unsupported_diet_type_rejected_at_profile_intake -- repeated here,
    # colocated with the schema's own test module, to prove UserProfile's
    # field_validator delegating to validate_diet_type_value is a pure
    # refactor with no behavior change.
    with pytest.raises(ValidationError):
        UserProfile(user_id="u", macro_targets=MacroTargets(), diet_type="halal")


def test_user_profile_accepts_none_diet_type() -> None:
    profile = UserProfile(user_id="u", macro_targets=MacroTargets(), diet_type=None)
    assert profile.diet_type is None
