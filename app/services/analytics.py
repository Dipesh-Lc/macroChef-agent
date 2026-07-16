"""Analytics event capture — PostHog, silent no-op without a key.

Non-negotiable: local dev, tests, and CI must never phone home. Every call
site goes through :func:`get_analytics`, which returns a real PostHog-backed
client only when ``POSTHOG_API_KEY`` is configured, and a :class:`NullAnalytics`
no-op otherwise. Never import ``posthog`` directly anywhere else in the app.

This module is advisory/observational only — it never decides a safety
outcome and is never on the request's critical path (every `capture` call
is best-effort and swallows its own errors).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Protocol

from app.config import get_settings

logger = logging.getLogger(__name__)


class AnalyticsClient(Protocol):
    """Minimal interface every analytics backend (including the no-op) implements."""

    def capture(
        self,
        distinct_id: str,
        event: str,
        properties: dict[str, Any] | None = None,
    ) -> None: ...


class NullAnalytics:
    """No-op analytics client used whenever ``POSTHOG_API_KEY`` is absent.

    This is the default in local dev, tests, and CI, guaranteeing zero
    network calls with no key configured.
    """

    def capture(
        self,
        distinct_id: str,
        event: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        return None


class PostHogAnalytics:
    """Thin wrapper around the `posthog` client.

    Only ever constructed when a real API key is present. Capture failures
    are logged and swallowed — analytics must never break a user request.
    """

    def __init__(self, api_key: str, host: str) -> None:
        from posthog import Posthog  # imported lazily: optional dependency

        self._client = Posthog(project_api_key=api_key, host=host)

    def capture(
        self,
        distinct_id: str,
        event: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        try:
            self._client.capture(event, distinct_id=distinct_id, properties=properties or {})
        except Exception:
            logger.warning("analytics capture failed for event %r", event, exc_info=True)


@lru_cache
def get_analytics() -> AnalyticsClient:
    """Return the process-wide analytics client.

    Cached because the PostHog client owns a background flush thread/queue;
    constructing one per call would leak resources and defeat batching.
    """
    settings = get_settings()
    if not settings.posthog_api_key:
        return NullAnalytics()
    try:
        return PostHogAnalytics(settings.posthog_api_key, settings.posthog_host)
    except Exception:
        logger.warning(
            "Failed to initialize PostHog analytics client; falling back to no-op.",
            exc_info=True,
        )
        return NullAnalytics()
