"""OpenTelemetry tracing, exported to a hosted backend (ROADMAP.md Phase 1,
Step 1.3).

Why this exists: Step 1.1's `RunEvent` stream and Step 1.2's LLM ledger
already answer "what ran and what did it cost" via this repo's own
dependency-free event/ledger modules. This module adds the industry-
standard complement -- a real OTLP trace, with node spans nesting under
the HTTP request span and LLM-call spans carrying the ledger's token/cost
attributes -- exportable to any OTLP-compatible backend (Honeycomb is the
recommended one; see docs/HUMAN_INPUTS.md entry H1) without changing a
line of this module if the backend later changes, since OTLP is standard
throughout.

THE NO-OP CONTRACT (this is the part that matters most):
Local dev and CI must never need an OTel backend, so tracing here is
enabled ONLY when `OTEL_EXPORTER_OTLP_ENDPOINT` is set to a non-blank
value (`Settings.otel_exporter_otlp_endpoint`). When it isn't:
  - `init_tracing` returns immediately after one Settings read. No SDK
    `TracerProvider` is constructed, no `BatchSpanProcessor`/exporter
    thread starts, no FastAPI/`requests` instrumentation is installed.
  - `get_tracer()` returns `None`, not an OTel API no-op tracer. Callers
    (`app.observability.events.traced_node`, `app.observability.
    llm_ledger.record_llm_call`) check for `None` and skip straight to
    calling the wrapped function / skip span emission entirely -- they
    never touch the `opentelemetry` API at all in this path. This is a
    deliberately stronger guarantee than relying on the OTel API's own
    built-in no-op behavior (calling `opentelemetry.trace.get_tracer(...)`
    with no provider installed already returns spans that do nothing and
    touch no network -- see `tests/test_tracing_noop.py` for a check of
    that fact too) because it means "tracing is off" is a single cheap
    `is None` check on this module's own state, not a claim about a third-
    party library's internals that could change across versions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.trace import Tracer

# Plain stdlib logger, not app.utils.logging.get_logger: that module reads
# app.observability.events.peek_run_id, and app.observability.events itself
# imports this module's `get_tracer` (for the traced_node span guard) --
# using the request-id-aware logger here would create an import cycle
# (events -> tracing -> utils.logging -> events) that breaks at import
# time, since utils.logging needs a name already defined in events.py
# before events.py has finished importing this module. This logger simply
# won't carry a request_id prefix; that's a fine trade for a module whose
# only log lines are "tracing enabled at boot" / "shutdown error", neither
# of which is ever inside a request.
logger = logging.getLogger(__name__)

# Module-global tracer/provider, set only by a successful `init_tracing`
# call. `None` in both fields is the no-op state and the only state any
# test can observe without OTEL_EXPORTER_OTLP_ENDPOINT set.
_tracer_provider: TracerProvider | None = None
_tracer: Tracer | None = None


def get_tracer() -> Tracer | None:
    """Return the process tracer, or `None` when tracing is disabled.

    Callers MUST treat `None` as "skip span emission, call the wrapped
    code directly" -- never call into the `opentelemetry` API with a
    `None` tracer. This is the guard that keeps the disabled path from
    touching OTel at all (see module docstring)."""
    return _tracer


def is_tracing_enabled() -> bool:
    return _tracer_provider is not None


def init_tracing(app: FastAPI | None = None) -> None:
    """Initialize OTLP tracing if configured; otherwise a true no-op.

    Must be called from `app.main.create_app` BEFORE the FastAPI app
    processes its first ASGI scope (including the `lifespan` scope
    itself) -- not from inside the `lifespan` context manager. Starlette
    caches `app.build_middleware_stack()`'s result on the very first
    `__call__` regardless of scope type, and `FastAPIInstrumentor.
    instrument_app` works by monkeypatching that method on the app
    instance; calling it any later than this would silently fail to wrap
    the app (see app.main.create_app's call site for this exact ordering
    note).

    `app` is optional so this can also be called from a script/test that
    only wants graph-node/LLM-call spans exported without HTTP
    instrumentation (e.g. no FastAPI app involved at all).
    """
    global _tracer_provider, _tracer

    settings = get_settings()
    endpoint = (settings.otel_exporter_otlp_endpoint or "").strip()
    if not endpoint:
        return  # no-op: see module docstring

    # Imports deliberately deferred until we know tracing is actually
    # enabled -- the disabled path above never even imports the SDK/
    # exporter/instrumentation packages, let alone constructs anything
    # that could start a thread or touch the network.
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.util.re import parse_env_headers

    # Built explicitly from Settings (not left to the exporter's own
    # environ.get(...) fallback) so a value that only lives in a local
    # .env file -- which pydantic-settings parses without exporting into
    # the real process environment -- is honored the same way every other
    # setting in this app is. `parse_env_headers` is the same OTel-spec
    # "key1=value1,key2=value2" parser the SDK itself uses internally, just
    # applied to our own already-resolved setting instead of a raw env var.
    traces_endpoint = endpoint.rstrip("/") + "/v1/traces"
    headers = parse_env_headers(settings.otel_exporter_otlp_headers or "", liberal=True)

    resource = Resource.create({"service.name": "macrochef-api"})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=traces_endpoint, headers=headers)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    _tracer_provider = provider
    _tracer = trace.get_tracer("macrochef")

    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    # Global (process-wide, not per-app) instrumentation of outgoing
    # `requests` calls -- covers app.services.model_provider's provider-HTTP
    # choke points and app.services.usda_client. Guarded by the
    # instrumentor's own idempotency flag so re-running `init_tracing`
    # (e.g. across tests that each build a fresh app) doesn't double-wrap
    # or raise.
    requests_instrumentor = RequestsInstrumentor()
    if not requests_instrumentor.is_instrumented_by_opentelemetry:
        requests_instrumentor.instrument(tracer_provider=provider)

    logger.info("OpenTelemetry tracing enabled (traces_endpoint=%s)", traces_endpoint)


def shutdown_tracing() -> None:
    """Flush and shut down the tracer provider. A no-op if tracing was
    never enabled (nothing to flush). Called from `app.main`'s `lifespan`
    context manager, after `yield` -- that function had no shutdown code
    at all before this (see its docstring)."""
    global _tracer_provider, _tracer
    if _tracer_provider is None:
        return
    try:
        _tracer_provider.shutdown()
    except Exception:  # pragma: no cover - shutdown must never crash the process
        logger.exception("Error shutting down OTel tracer provider")
    _tracer_provider = None
    _tracer = None
