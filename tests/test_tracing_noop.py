"""ROADMAP.md Phase 1, Step 1.3 -- OpenTelemetry traces exported to a
hosted backend.

This file's job is narrow but load-bearing: prove the NO-OP path (no
`OTEL_EXPORTER_OTLP_ENDPOINT` configured -- the default for local dev and
CI) never constructs a tracer provider, never starts an exporter thread,
and never touches the `opentelemetry` API from the two call sites that
were wired in this step (`app.observability.events.traced_node` and
`app.observability.llm_ledger.record_llm_call`). The "app boots and serves
with no OTEL env set" acceptance criterion is also covered here.

The enabled path (real spans exported to a real backend, e.g. Honeycomb)
is a human-gated live-trace check per this step's task brief -- not
something a unit test can or should exercise. What IS unit-testable about
the enabled path -- that `init_tracing` actually constructs a provider and
exporter when configured, without hitting the network (a stub exporter
class is substituted) -- is covered too, since the no-op/enabled split is
literally the design this file exists to pin.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.observability.llm_ledger as llm_ledger_module
import app.observability.tracing as tracing_module
from app.config import get_settings
from app.data.db import Base
from app.main import create_app
from app.observability.events import (
    InMemorySink,
    new_run_id,
    reset_run_id,
    set_run_id,
    traced_node,
)
from app.observability.llm_ledger import record_llm_call
from app.observability.tracing import get_tracer, init_tracing, is_tracing_enabled, shutdown_tracing


@pytest.fixture(autouse=True)
def _clear_tracing_state(monkeypatch: pytest.MonkeyPatch):
    """Every test starts from the true disabled state: no OTEL env var, no
    tracer provider installed, Settings cache cleared so a prior test's
    `monkeypatch.setenv` can't leak in via `lru_cache`. Restored after each
    test too, so a test that enables tracing never leaks into the next
    one -- including uninstrumenting `requests`, which
    `test_init_tracing_constructs_a_provider_when_endpoint_configured` below
    installs process-globally (RequestsInstrumentor wraps the `requests`
    library itself, not a per-app object), unlike the FastAPI
    instrumentation, which is scoped to one app instance and never touched
    by that test."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_HEADERS", raising=False)
    get_settings.cache_clear()
    tracing_module._tracer_provider = None
    tracing_module._tracer = None
    yield
    shutdown_tracing()
    get_settings.cache_clear()

    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    requests_instrumentor = RequestsInstrumentor()
    if requests_instrumentor.is_instrumented_by_opentelemetry:
        requests_instrumentor.uninstrument()


@pytest.fixture()
def isolated_ledger_db(monkeypatch: pytest.MonkeyPatch):
    """Mirrors tests/test_llm_ledger.py's fixture of the same name -- points
    the ledger at a throwaway in-memory DB instead of the developer's real
    macrochef.db."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(llm_ledger_module, "SessionLocal", test_session_local)
    return test_session_local


# ---------------------------------------------------------------------------
# Acceptance criterion: the app boots and serves with no OTEL env set.
# ---------------------------------------------------------------------------


def test_app_boots_and_serves_with_no_otel_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    # SESSION_SECRET: unrelated to tracing, but required for the full
    # lifespan (validate_session_secret_at_startup) to succeed under
    # `with TestClient(...)` -- see tests/test_session_secret_startup.py.
    monkeypatch.setenv("SESSION_SECRET", "test-only-secret-for-tracing-noop-test")
    get_settings.cache_clear()

    # `with TestClient(...)` runs the full lifespan (startup AND shutdown,
    # including shutdown_tracing()) -- not just create_app()'s synchronous
    # init_tracing() call -- so this covers both halves of the wiring
    # described in app.main's comments.
    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200
    assert not is_tracing_enabled()


# ---------------------------------------------------------------------------
# get_tracer() / init_tracing(): the core no-op contract.
# ---------------------------------------------------------------------------


def test_get_tracer_returns_none_without_endpoint_configured() -> None:
    assert get_tracer() is None
    assert not is_tracing_enabled()


def test_init_tracing_never_constructs_an_exporter_without_endpoint_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The strongest form of the no-op guarantee: even if we didn't trust
    our own `if not endpoint: return` guard, proving the OTLP exporter
    class itself is never instantiated rules out any accidental network
    setup."""

    def _boom(*args, **kwargs):
        raise AssertionError("OTLPSpanExporter must never be constructed when tracing is disabled")

    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
        _boom,
    )

    init_tracing()  # no app; no endpoint configured -> must return immediately

    assert get_tracer() is None
    assert not is_tracing_enabled()


def test_init_tracing_constructs_a_provider_when_endpoint_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity-checks the OTHER half of the split: when configured, a real
    tracer provider IS installed. A stub exporter class is substituted so
    this never actually opens a socket."""
    calls: list[dict] = []

    class _StubExporter:
        def __init__(self, *, endpoint, headers):
            calls.append({"endpoint": endpoint, "headers": headers})

        def export(self, spans):  # pragma: no cover - not exercised here
            from opentelemetry.sdk.trace.export import SpanExportResult

            return SpanExportResult.SUCCESS

        def shutdown(self) -> None:
            pass

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return True

    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
        _StubExporter,
    )
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://api.honeycomb.io")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "x-honeycomb-team=fake-test-key")
    get_settings.cache_clear()

    init_tracing()

    assert is_tracing_enabled()
    assert get_tracer() is not None
    assert calls == [
        {
            "endpoint": "https://api.honeycomb.io/v1/traces",
            "headers": {"x-honeycomb-team": "fake-test-key"},
        }
    ]

    shutdown_tracing()
    assert not is_tracing_enabled()
    assert get_tracer() is None


# ---------------------------------------------------------------------------
# traced_node: span emission must be a true no-op when tracing is disabled
# -- proven by making the real opentelemetry.trace.get_tracer entrypoint
# raise if it's ever reached; traced_node must never get that far.
# ---------------------------------------------------------------------------


def test_traced_node_never_touches_real_otel_api_when_tracing_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import opentelemetry.trace as otel_trace

    def _boom(*args, **kwargs):
        raise AssertionError(
            "opentelemetry.trace.get_tracer must not be called when tracing is disabled"
        )

    monkeypatch.setattr(otel_trace, "get_tracer", _boom)

    sink = InMemorySink()
    run_id = new_run_id()
    token = set_run_id(run_id)
    try:

        @traced_node("dummy_node", sink=sink)
        def dummy_node(state: dict) -> dict:
            return {
                **state,
                "debug_trace": [*state.get("debug_trace", []), "dummy_node: did a thing."],
            }

        result = dummy_node({"debug_trace": []})
        assert result["debug_trace"] == ["dummy_node: did a thing."]

        events = sink.get_events(run_id)
        assert [event.status for event in events] == ["started", "finished"]
    finally:
        reset_run_id(token)


def test_traced_node_failure_path_never_touches_real_otel_api_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same guarantee on the exception path, where a real implementation
    might plausibly reach for `span.record_exception` -- must still never
    happen when tracing is disabled."""
    import opentelemetry.trace as otel_trace

    def _boom(*args, **kwargs):
        raise AssertionError(
            "opentelemetry.trace.get_tracer must not be called when tracing is disabled"
        )

    monkeypatch.setattr(otel_trace, "get_tracer", _boom)

    sink = InMemorySink()
    run_id = new_run_id()
    token = set_run_id(run_id)
    try:

        @traced_node("exploding_node", sink=sink)
        def exploding_node(state: dict) -> dict:
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError, match="kaboom"):
            exploding_node({"debug_trace": []})

        events = sink.get_events(run_id)
        assert [event.status for event in events] == ["started", "failed"]
    finally:
        reset_run_id(token)


# ---------------------------------------------------------------------------
# record_llm_call's span emission: same no-op guarantee.
# ---------------------------------------------------------------------------


def test_record_llm_call_never_touches_real_otel_api_when_tracing_disabled(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    import opentelemetry.trace as otel_trace

    def _boom(*args, **kwargs):
        raise AssertionError(
            "opentelemetry.trace.get_tracer must not be called when tracing is disabled"
        )

    monkeypatch.setattr(otel_trace, "get_tracer", _boom)

    # Must not raise despite the real OTel API being blocked above -- proves
    # _emit_llm_span's `get_tracer() is None` guard returns before ever
    # reaching the opentelemetry API.
    record_llm_call(
        provider="mock",
        model="mock",
        purpose="recipe_generation",
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=12.3,
        success=True,
        fallback_used=False,
    )
