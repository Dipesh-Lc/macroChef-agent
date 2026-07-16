"""Analytics must be a silent no-op whenever POSTHOG_API_KEY is absent — this
is the non-negotiable property from the CI/CD + analytics roadmap item.
Local dev, tests, and CI must never phone home.

Tests that exercise the "key present" path substitute a fake Posthog client
class so no real background flush thread or network socket is ever created,
even when a (fake) key is configured.
"""

import socket

import pytest

from app.config import get_settings
from app.services import analytics as analytics_module
from app.services.analytics import NullAnalytics, get_analytics


class _FakePosthogClient:
    """Stand-in for `posthog.Posthog` — records calls, opens no thread/socket."""

    def __init__(self, project_api_key: str, host: str | None = None) -> None:
        self.project_api_key = project_api_key
        self.host = host
        self.captured: list[tuple[str, object, dict | None]] = []

    def capture(self, event: str, distinct_id=None, properties=None, **kwargs) -> None:
        self.captured.append((event, distinct_id, properties))


@pytest.fixture(autouse=True)
def _clear_caches():
    get_settings.cache_clear()
    get_analytics.cache_clear()
    yield
    get_settings.cache_clear()
    get_analytics.cache_clear()


def test_no_key_returns_null_analytics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    client = get_analytics()
    assert isinstance(client, NullAnalytics)


def test_null_analytics_capture_is_a_true_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """Capture must not raise and must not touch the network when no key is set."""
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    client = get_analytics()

    def _blocked_socket(*args, **kwargs):
        raise AssertionError("NullAnalytics must never open a network socket")

    monkeypatch.setattr(socket, "socket", _blocked_socket)

    # Must not raise despite sockets being blocked -- proves no network call.
    client.capture("demo_user", "request completed", {"had_errors": False})


def test_get_analytics_is_cached_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    assert get_analytics() is get_analytics()


def test_key_present_returns_posthog_backed_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test_key")
    import posthog

    monkeypatch.setattr(posthog, "Posthog", _FakePosthogClient)

    client = get_analytics()
    assert isinstance(client, analytics_module.PostHogAnalytics)

    client.capture("demo_user", "plan generated", {"recommendation_count": 3})
    assert client._client.captured == [
        ("plan generated", "demo_user", {"recommendation_count": 3})
    ]


def test_key_present_capture_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken/unreachable PostHog client must never raise out of `capture` —
    analytics is advisory only and must never break a user request."""
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test_key")
    import posthog

    monkeypatch.setattr(posthog, "Posthog", _FakePosthogClient)

    client = get_analytics()
    assert isinstance(client, analytics_module.PostHogAnalytics)

    def _boom(*args, **kwargs):
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(client._client, "capture", _boom)
    client.capture("demo_user", "plan generated", {"recommendation_count": 3})


def test_client_init_failure_falls_back_to_null(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test_key")

    def _broken_init(self, api_key, host):
        raise RuntimeError("posthog unavailable")

    monkeypatch.setattr(analytics_module.PostHogAnalytics, "__init__", _broken_init)
    client = get_analytics()
    assert isinstance(client, NullAnalytics)
