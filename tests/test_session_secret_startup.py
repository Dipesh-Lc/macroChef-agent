"""Tests for the SESSION_SECRET fail-closed behavior (see
app.dependencies._resolve_session_secret / validate_session_secret_at_startup).

Design: the secure default is "no secret configured -> raise", never
inferred from DATABASE_URL or any other unrelated setting. Insecurity is
only ever entered via an explicit, human opt-in flag,
ALLOW_INSECURE_SESSION_SECRET. Both validate_session_secret_at_startup
(called once at FastAPI boot, so a broken container never serves a single
request) and _resolve_session_secret (called on every token mint/verify, in
both the FastAPI and Streamlit processes) enforce the exact same rule via
the same code path -- there is only one place this decision is made.

- secret set                                   -> proceeds silently
- secret unset + ALLOW_INSECURE_SESSION_SECRET -> proceeds, warns, returns
                                                   the hardcoded dev constant
- secret unset + no flag                       -> raises RuntimeError naming
                                                   SESSION_SECRET

All tests here construct `Settings` directly with explicit overrides rather
than relying on `get_settings()` / the ambient environment, so this suite
can never pass "by accident" because a developer's local `.env` happens to
have SESSION_SECRET set.
"""

import logging

import pytest

from app.config import Settings
from app.dependencies import (
    _DEV_INSECURE_SESSION_SECRET,
    _resolve_session_secret,
    validate_session_secret_at_startup,
)


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


# ---------------------------------------------------------------------------
# secret set -> resolves silently, no raise
# ---------------------------------------------------------------------------


def test_set_secret_resolves_directly_and_does_not_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(SESSION_SECRET="a-real-configured-secret")

    with caplog.at_level(logging.WARNING):
        resolved = _resolve_session_secret(settings)

    assert resolved == "a-real-configured-secret"
    assert caplog.records == []


def test_set_secret_startup_check_proceeds_silently(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(SESSION_SECRET="a-real-configured-secret")

    with caplog.at_level(logging.WARNING):
        validate_session_secret_at_startup(settings)  # must not raise

    assert caplog.records == []


# ---------------------------------------------------------------------------
# unset + no flag -> raises, naming SESSION_SECRET
# ---------------------------------------------------------------------------


def test_unset_secret_without_flag_raises_on_resolve() -> None:
    settings = _settings(SESSION_SECRET=None, ALLOW_INSECURE_SESSION_SECRET=False)

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        _resolve_session_secret(settings)


def test_unset_secret_without_flag_raises_at_startup() -> None:
    settings = _settings(SESSION_SECRET=None, ALLOW_INSECURE_SESSION_SECRET=False)

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        validate_session_secret_at_startup(settings)


# ---------------------------------------------------------------------------
# unset + flag True -> returns the dev constant, warns, no raise
# ---------------------------------------------------------------------------


def test_unset_secret_with_flag_returns_dev_default_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(SESSION_SECRET=None, ALLOW_INSECURE_SESSION_SECRET=True)

    with caplog.at_level(logging.WARNING):
        resolved = _resolve_session_secret(settings)

    assert resolved == _DEV_INSECURE_SESSION_SECRET
    assert any("SESSION_SECRET" in record.message for record in caplog.records)


def test_unset_secret_with_flag_startup_check_proceeds_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(SESSION_SECRET=None, ALLOW_INSECURE_SESSION_SECRET=True)

    with caplog.at_level(logging.WARNING):
        validate_session_secret_at_startup(settings)  # must not raise

    assert any("SESSION_SECRET" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Regression test for the database_url-coupling bug. A prod-shaped config
# that simply never set DATABASE_URL (so it silently defaults to the local
# sqlite path) must NOT be treated as "local dev" and must NOT silently
# accept the insecure default. Before this fix, `_is_local_dev` keyed
# enforcement on `database_url.startswith("sqlite")`, so this exact
# configuration -- SESSION_SECRET unset, DATABASE_URL simply absent/
# defaulted -- passed validation with only a warning. This test fails
# against that old implementation; it is the reason `_is_local_dev` no
# longer exists, and enforcement now depends only on
# ALLOW_INSECURE_SESSION_SECRET, never on DATABASE_URL.
# ---------------------------------------------------------------------------


def test_defaulted_sqlite_database_url_does_not_imply_local_dev() -> None:
    settings = _settings(SESSION_SECRET=None, ALLOW_INSECURE_SESSION_SECRET=False)
    assert settings.database_url.startswith("sqlite")  # confirms the default is in play

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        validate_session_secret_at_startup(settings)


# ---------------------------------------------------------------------------
# End-to-end: the FastAPI app itself, via its real startup event -- not just
# the helper function in isolation.
# ---------------------------------------------------------------------------


def test_app_startup_raises_when_secret_unset_and_flag_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Patches `app.dependencies.get_app_settings` directly (rather than env
    vars) so this is immune to whatever a developer's real `.env` happens to
    contain -- monkeypatching `os.environ` alone is not reliable here, since
    pydantic-settings still reads `.env` for any var absent from the process
    environment.

    Uses `with TestClient(app) as client:` deliberately: that
    context-manager form is what actually triggers
    `@app.on_event("startup")` -- a plain, non-context-managed
    `TestClient(app)` request does NOT run it."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    fake_settings = _settings(SESSION_SECRET=None, ALLOW_INSECURE_SESSION_SECRET=False)
    monkeypatch.setattr("app.dependencies.get_app_settings", lambda: fake_settings)

    app = create_app()
    with pytest.raises(RuntimeError, match="SESSION_SECRET"), TestClient(app):
        pass


def test_app_startup_succeeds_when_secret_unset_and_flag_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    fake_settings = _settings(SESSION_SECRET=None, ALLOW_INSECURE_SESSION_SECRET=True)
    monkeypatch.setattr("app.dependencies.get_app_settings", lambda: fake_settings)

    app = create_app()
    with TestClient(app):
        pass  # must not raise
