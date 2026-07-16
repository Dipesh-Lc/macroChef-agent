"""Unit tests for app.dependencies.get_session_user -- the sole source of
truth for "who is this /library request from" (see task: library user-data
isolation). A missing, forged, tampered, or expired token must always be
rejected with 401, never silently treated as a new anonymous session.

Every test here builds `Settings` with an explicit `SESSION_SECRET` rather
than relying on `get_settings()` / the ambient environment or the insecure
dev-fallback default (see app.dependencies._resolve_session_secret, which
now raises instead of silently falling back when SESSION_SECRET is unset).
Depending on the ambient fallback would make this suite pass "by accident"
whenever a developer's local `.env` happens to have SESSION_SECRET set, and
fail outright in any environment (e.g. CI) where it is not -- neither
outcome actually exercises the signing/verification behavior under test.
"""

import time

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.dependencies import (
    SESSION_TOKEN_MAX_AGE_SECONDS,
    get_session_user,
    mint_session_token,
)


def _settings() -> Settings:
    return Settings(SESSION_SECRET="test-suite-session-secret")


def _tamper(token: str) -> str:
    """Flip one character of a signed token in a way that is guaranteed to
    change its decoded bytes.

    Deliberately does NOT touch the very last character: unpadded base64
    (what itsdangerous uses) can have 2-4 "don't care" bits in its final
    symbol, so some replacement characters there decode to the exact same
    bytes as the original -- flipping the last character is a flaky tamper
    that occasionally leaves the signature valid by chance. A middle
    character has no such ambiguity.
    """
    middle = len(token) // 2
    original = token[middle]
    replacement = "A" if original != "A" else "B"
    return token[:middle] + replacement + token[middle + 1 :]


def test_valid_token_resolves_to_the_minted_user_id() -> None:
    settings = _settings()
    token = mint_session_token("session_abc123", settings)

    resolved = get_session_user(x_session_token=token, settings=settings)

    assert resolved == "session_abc123"


def test_missing_token_is_rejected_with_401() -> None:
    settings = _settings()

    with pytest.raises(HTTPException) as exc_info:
        get_session_user(x_session_token=None, settings=settings)

    assert exc_info.value.status_code == 401


def test_empty_token_is_rejected_with_401() -> None:
    settings = _settings()

    with pytest.raises(HTTPException) as exc_info:
        get_session_user(x_session_token="", settings=settings)

    assert exc_info.value.status_code == 401


def test_forged_token_with_no_signature_is_rejected_with_401() -> None:
    settings = _settings()

    with pytest.raises(HTTPException) as exc_info:
        get_session_user(x_session_token="not-a-real-token", settings=settings)

    assert exc_info.value.status_code == 401


def test_tampered_payload_is_rejected_with_401() -> None:
    """Flipping a character in an otherwise-valid token must invalidate the
    signature -- this is the actual forgery-resistance property."""
    settings = _settings()
    token = mint_session_token("victim_user", settings)
    tampered = _tamper(token)

    with pytest.raises(HTTPException) as exc_info:
        get_session_user(x_session_token=tampered, settings=settings)

    assert exc_info.value.status_code == 401


def test_token_signed_with_a_different_secret_is_rejected_with_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token forged by someone who guessed/used a different secret than
    the server's configured SESSION_SECRET must never be accepted."""
    attacker_settings = Settings(SESSION_SECRET="attacker-guessed-secret")
    forged_token = mint_session_token("victim_user", attacker_settings)

    server_settings = Settings(SESSION_SECRET="the-real-server-secret")
    with pytest.raises(HTTPException) as exc_info:
        get_session_user(x_session_token=forged_token, settings=server_settings)

    assert exc_info.value.status_code == 401


def test_expired_token_is_rejected_with_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """A token minted longer ago than SESSION_TOKEN_MAX_AGE_SECONDS must be
    rejected, not silently accepted forever."""
    settings = _settings()

    real_time = time.time
    backdated = real_time() - SESSION_TOKEN_MAX_AGE_SECONDS - 3600
    monkeypatch.setattr(time, "time", lambda: backdated)
    token = mint_session_token("stale_user", settings)
    monkeypatch.setattr(time, "time", real_time)

    with pytest.raises(HTTPException) as exc_info:
        get_session_user(x_session_token=token, settings=settings)

    assert exc_info.value.status_code == 401


def test_token_just_inside_the_ttl_is_still_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check for the expiry test above: a token minted well within the
    TTL window must still be accepted (proves the 401 above is really about
    expiry, not some other break)."""
    settings = _settings()

    real_time = time.time
    recent = real_time() - (SESSION_TOKEN_MAX_AGE_SECONDS // 2)
    monkeypatch.setattr(time, "time", lambda: recent)
    token = mint_session_token("recent_user", settings)
    monkeypatch.setattr(time, "time", real_time)

    resolved = get_session_user(x_session_token=token, settings=settings)

    assert resolved == "recent_user"


def test_two_mints_for_different_users_produce_different_tokens() -> None:
    settings = _settings()
    token_a = mint_session_token("user_a", settings)
    token_b = mint_session_token("user_b", settings)

    assert token_a != token_b
    assert get_session_user(x_session_token=token_a, settings=settings) == "user_a"
    assert get_session_user(x_session_token=token_b, settings=settings) == "user_b"
