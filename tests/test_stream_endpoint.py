"""Tests for POST /recipes/recommend/stream (ROADMAP.md Phase 3, Step 3.1).

Mirrors tests/test_recommendation_isolation.py's app/session-auth fixture
pattern (isolated in-memory DB, forced deterministic keyword retrieval, an
explicit SESSION_SECRET) -- this endpoint runs `run_recommendation_graph`
end to end (same as the synchronous route), so the same environment control
that suite needs for a stable /recipes/recommend call applies here too.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.data.graph_run_repository as graph_run_repo_module
import app.graph.builder as builder_module
import app.graph.nodes as nodes_module
import app.services.memory_service as memory_service_module
import app.services.recipe_retriever as recipe_retriever_module
from app.config import get_settings
from app.data.db import Base
from app.data.recipe_library_repository import RecipeLibraryRepository
from app.dependencies import SESSION_TOKEN_HEADER, mint_session_token
from app.main import create_app
from app.schemas.inventory import InventoryObservation
from app.schemas.recommendation import RecommendationResponse


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    """Explicit SESSION_SECRET so this suite never depends on ambient
    config -- see the identical fixture in tests/test_recommendation_isolation.py."""
    monkeypatch.setenv("SESSION_SECRET", "stream-endpoint-test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def isolated_session_factory(monkeypatch: pytest.MonkeyPatch):
    """Point every repository the recommendation graph touches at a fresh
    in-memory SQLite DB instead of the developer's real macrochef.db --
    mirrors tests/test_recommendation_isolation.py's fixture of the same
    name."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(RecipeLibraryRepository, "_session", lambda self: test_session_local())
    monkeypatch.setattr(memory_service_module, "SessionLocal", test_session_local)
    monkeypatch.setattr(memory_service_module, "init_db", lambda: None)
    return test_session_local


@pytest.fixture(autouse=True)
def _force_keyword_retrieval(monkeypatch: pytest.MonkeyPatch):
    """Force RecipeRetriever.retrieve onto its deterministic keyword-search
    path -- whatever this developer's real, shared vector store happens to
    have persisted is an irrelevant (and flaky) variable to control out
    here. Mirrors tests/test_recommendation_isolation.py."""

    class _EmptyVectorStore:
        def count(self) -> int:
            return 0

    monkeypatch.setattr(recipe_retriever_module, "get_vector_store", lambda: _EmptyVectorStore())


def _client() -> TestClient:
    return TestClient(create_app())


def _token(user_id: str) -> str:
    return mint_session_token(user_id, get_settings())


def _auth_headers(user_id: str) -> dict[str, str]:
    return {SESSION_TOKEN_HEADER: _token(user_id)}


def _recommend_payload(extra: dict | None = None) -> dict:
    payload = {
        "input_type": "text",
        "typed_ingredients": "chicken, rice, broccoli",
        "user_profile": {
            "allergies": [],
            "disliked_ingredients": [],
            "diet_type": None,
            "preferred_cuisines": [],
            "macro_targets": {},
            "max_cook_time_min": 60,
        },
    }
    if extra:
        payload.update(extra)
    return payload


def _parse_sse(raw_lines: list[str]) -> list[tuple[str, dict]]:
    """Parse raw SSE lines (as yielded by httpx's `iter_lines()`) into
    `(event_type, data_dict)` pairs, per this project's `_sse` formatting
    (app.api.routes_stream._sse): one `event: <type>` line followed by one
    `data: <json>` line, blank-line-terminated. Comment (`: heartbeat`)
    lines carry no event/data pair and are skipped."""
    events: list[tuple[str, dict]] = []
    pending_event: str | None = None
    for line in raw_lines:
        if not line or line.startswith(":"):
            continue
        if line.startswith("event: "):
            pending_event = line[len("event: ") :]
        elif line.startswith("data: "):
            assert pending_event is not None, "data line with no preceding event line"
            events.append((pending_event, json.loads(line[len("data: ") :])))
            pending_event = None
    return events


# ---------------------------------------------------------------------------
# Auth: same requirement as POST /recipes/recommend -- no session -> 401.
# ---------------------------------------------------------------------------


def test_requires_session_401(isolated_session_factory) -> None:
    client = _client()
    response = client.post("/recipes/recommend/stream", json=_recommend_payload())
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Happy path: node events arrive in graph order, each carries a summary +
# elapsed_ms once finished, and the stream ends with exactly one `result`
# event that parses as a valid RecommendationResponse.
# ---------------------------------------------------------------------------


def test_node_events_arrive_in_order_then_result(isolated_session_factory) -> None:
    client = _client()
    with client.stream(
        "POST",
        "/recipes/recommend/stream",
        json=_recommend_payload(),
        headers=_auth_headers("stream_user"),
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw_lines = list(response.iter_lines())

    events = _parse_sse(raw_lines)
    assert events, "no SSE events were received"

    node_events = [(etype, data) for etype, data in events if etype == "node"]
    assert node_events, "no `node` events were received"

    finished_node_order = [
        data["node"] for etype, data in node_events if data["status"] == "finished"
    ]
    # Matches app/graph/nodes.py's fixed node order (see the module docstring
    # for the full 11-node sequence); the first four run unconditionally.
    assert finished_node_order[:4] == [
        "intake_node",
        "inventory_confirmation_node",
        "constraint_builder_node",
        "recipe_retriever_node",
    ]

    retriever_summary = next(
        data["summary"]
        for etype, data in node_events
        if data["node"] == "recipe_retriever_node" and data["status"] == "finished"
    )
    assert "candidate" in retriever_summary

    for _etype, data in node_events:
        assert data["status"] in {"started", "finished", "failed"}
        if data["status"] in {"finished", "failed"}:
            assert data["elapsed_ms"] is not None
            assert data["summary"]

    terminal_types = [etype for etype, _ in events if etype in {"result", "error"}]
    assert terminal_types == ["result"], "expected exactly one terminal `result` event"

    result_data = events[-1][1]
    parsed = RecommendationResponse.model_validate(result_data)
    assert isinstance(parsed.recommendations, list)


# ---------------------------------------------------------------------------
# A mid-graph exception must surface as a clean `error` event, not a
# dropped connection or an unhandled 500.
# ---------------------------------------------------------------------------


def test_mid_graph_exception_yields_clean_error_event(
    isolated_session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(state):
        raise RuntimeError("synthetic mid-graph failure for the test")

    # Patches the name bound inside app.graph.builder's own namespace (where
    # build_macrochef_graph reads it from at call time), not
    # app.graph.nodes.recipe_retriever_node -- builder.py imported the
    # function object directly (`from app.graph.nodes import ...
    # recipe_retriever_node ...`), so only patching builder_module's own
    # attribute actually reaches the compiled graph.
    monkeypatch.setattr(builder_module, "recipe_retriever_node", _boom)

    client = _client()
    with client.stream(
        "POST",
        "/recipes/recommend/stream",
        json=_recommend_payload(),
        headers=_auth_headers("stream_user_error"),
    ) as response:
        assert response.status_code == 200
        raw_lines = list(response.iter_lines())

    events = _parse_sse(raw_lines)
    assert events, "no SSE events were received"

    node_events = [(etype, data) for etype, data in events if etype == "node"]
    finished_before_failure = [
        data["node"] for etype, data in node_events if data["status"] == "finished"
    ]
    assert "intake_node" in finished_before_failure
    assert "constraint_builder_node" in finished_before_failure
    assert "recipe_retriever_node" not in finished_before_failure

    terminal_events = [(etype, data) for etype, data in events if etype in {"result", "error"}]
    assert len(terminal_events) == 1, "expected exactly one terminal event"
    etype, data = terminal_events[0]
    assert etype == "error"
    assert data["detail"] == "Internal Server Error"
    assert data["error_type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# ROADMAP.md Phase 3, Step 3.2: the stream itself can pause. This is the
# literal "upload photo -> stream pauses -> confirm -> resume" README demo
# flow ROADMAP.md's Step 3.2 acceptance criterion names -- node events relay
# live right up through inventory_confirmation_node's interrupt, the stream
# ends in a NEW `awaiting_input` terminal event (not `result`/`error`)
# carrying a resumable `thread_id`, and POST /runs/{thread_id}/resume
# (unmodified from app.api.routes_runs) produces the final plan.
# ---------------------------------------------------------------------------


@pytest.fixture()
def _isolated_graph_run_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """GraphRunRepository (the thread_id -> owner_user_id ownership check)
    needs its own isolated DB for this test, same as
    tests/test_hitl_resume.py's fixture of the same purpose -- not
    `autouse` here since the other tests in this file never touch
    `/runs`."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(graph_run_repo_module, "SessionLocal", test_session_local)


@pytest.fixture()
def _checkpoint_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Points the checkpointed graph's SqliteSaver at a real file, mirrors
    tests/test_hitl_resume.py's `_use_checkpoint_db`."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'stream_hitl_checkpoints.db'}")
    get_settings.cache_clear()
    builder_module._get_checkpointer.cache_clear()
    yield
    builder_module._get_checkpointer.cache_clear()


def test_stream_pauses_with_awaiting_input_then_resume_completes(
    isolated_session_factory,
    _isolated_graph_run_db,
    _checkpoint_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_extract(image_path):
        return [
            InventoryObservation(
                raw_name="shrimp paste",
                normalized_name="shrimp paste",
                confidence=0.4,
                source="vision",
                needs_confirmation=True,
            )
        ]

    monkeypatch.setattr(nodes_module, "extract_inventory_from_image", fake_extract)
    monkeypatch.setenv("MACROCHEF_ENABLE_VISION", "true")
    get_settings.cache_clear()

    client = _client()
    headers = _auth_headers("stream_hitl_user")
    payload = _recommend_payload({"input_type": "image", "image_path": "fake.jpg"})

    with client.stream(
        "POST", "/recipes/recommend/stream", json=payload, headers=headers
    ) as response:
        assert response.status_code == 200
        raw_lines = list(response.iter_lines())

    events = _parse_sse(raw_lines)
    assert events, "no SSE events were received"

    # Node events still relay live, right up through the pause -- the
    # ROADMAP's own framing ("every second shows the system reasoning")
    # still applies to a run that ends up pausing. `interrupt()` raises
    # `GraphInterrupt` on this (the pausing) call -- see
    # app.graph.nodes.inventory_confirmation_node and
    # app.observability.events.traced_node's docstring -- so the node
    # genuinely never returns here: it emits `started` but never `finished`
    # (that only happens on the later RESUME call, once interrupt() returns
    # a value instead of raising). Asserting `finished` here would be
    # asserting something that cannot happen given real LangGraph semantics.
    node_events = [(etype, data) for etype, data in events if etype == "node"]
    finished_nodes = [data["node"] for etype, data in node_events if data["status"] == "finished"]
    started_nodes = [data["node"] for etype, data in node_events if data["status"] == "started"]
    failed_nodes = [data["node"] for etype, data in node_events if data["status"] == "failed"]
    assert "intake_node" in finished_nodes
    assert "inventory_confirmation_node" in started_nodes
    assert "inventory_confirmation_node" not in finished_nodes
    assert "inventory_confirmation_node" not in failed_nodes

    terminal_event_types = {"result", "error", "awaiting_input"}
    terminal_types = [etype for etype, _ in events if etype in terminal_event_types]
    assert terminal_types == ["awaiting_input"], (
        "expected exactly one terminal `awaiting_input` event, not `result`/`error`"
    )

    awaiting_data = events[-1][1]
    thread_id = awaiting_data["thread_id"]
    assert thread_id
    assert awaiting_data["awaiting"]["reason"] == "low_confidence_inventory"

    resume_payload = {"confirmed_inventory": [{"name": "miso paste", "quantity": "1 tbsp"}]}
    resumed = client.post(f"/runs/{thread_id}/resume", json=resume_payload, headers=headers)
    assert resumed.status_code == 200
    resumed_body = resumed.json()
    assert resumed_body["status"] == "completed"
    assert resumed_body["result"]["errors"] == []
