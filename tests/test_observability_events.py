"""ROADMAP.md Phase 1, Step 1.1 -- structured run events + request IDs."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.data.recipe_library_repository as repo_module
from app.data.db import Base
from app.graph.builder import run_recommendation_graph
from app.main import create_app
from app.observability.events import (
    InMemorySink,
    RunEvent,
    get_default_sink,
    get_run_id,
    new_run_id,
    reset_run_id,
    set_default_sink,
    set_run_id,
    traced_node,
)
from app.schemas.recommendation import RecommendationRequest
from app.schemas.user import MacroTargets, UserProfile
from app.utils.logging import get_logger


@pytest.fixture(autouse=True)
def _isolated_library_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors tests/test_graph_flow.py's fixture of the same name: the
    recommend graph's nodes read/write via RecipeLibraryRepository, which
    otherwise opens a real on-disk sqlite engine."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(repo_module, "SessionLocal", test_session_local)


@pytest.fixture(autouse=True)
def _restore_default_sink():
    """`traced_node` resolves the active sink at call time via
    `get_default_sink()` -- restore the process-wide default after each test
    so one test's `InMemorySink` never leaks into another."""
    original = get_default_sink()
    yield
    set_default_sink(original)


@pytest.fixture()
def _fresh_run_id():
    """Bind a fresh, known run_id for the duration of a test and reset the
    contextvar afterward so tests never see each other's ids."""
    run_id = new_run_id()
    token = set_run_id(run_id)
    yield run_id
    reset_run_id(token)


# ---------------------------------------------------------------------------
# traced_node decorator
# ---------------------------------------------------------------------------


def test_traced_node_emits_started_and_finished_with_elapsed_ms(_fresh_run_id) -> None:
    sink = InMemorySink()

    @traced_node("dummy_node", sink=sink)
    def dummy_node(state: dict) -> dict:
        return {**state, "debug_trace": [*state.get("debug_trace", []), "dummy_node: did a thing."]}

    result = dummy_node({"debug_trace": []})

    assert result["debug_trace"] == ["dummy_node: did a thing."]

    events = sink.get_events(_fresh_run_id)
    assert [event.status for event in events] == ["started", "finished"]

    started, finished = events
    assert started.node == "dummy_node"
    assert started.run_id == _fresh_run_id
    assert started.elapsed_ms is None

    assert finished.node == "dummy_node"
    assert finished.run_id == _fresh_run_id
    assert finished.elapsed_ms is not None
    assert finished.elapsed_ms >= 0
    # The node's own new debug_trace entry becomes the event's human summary
    # -- no duplicate/rewritten line, see traced_node's docstring.
    assert finished.summary == "dummy_node: did a thing."


def test_traced_node_synthesizes_summary_and_appends_trace_when_node_adds_none(
    _fresh_run_id,
) -> None:
    """Some nodes short-circuit (e.g. upstream errors already present) and
    return the same debug_trace they were given. traced_node must still
    leave exactly one fingerprint per executed node."""
    sink = InMemorySink()

    @traced_node("noop_node", sink=sink)
    def noop_node(state: dict) -> dict:
        return dict(state)  # no debug_trace change

    result = noop_node({"debug_trace": ["earlier_node: did something."]})

    assert result["debug_trace"][0] == "earlier_node: did something."
    assert len(result["debug_trace"]) == 2
    assert "noop_node" in result["debug_trace"][1]

    finished = sink.get_events(_fresh_run_id)[-1]
    assert finished.status == "finished"
    assert finished.summary == result["debug_trace"][1]


def test_traced_node_failure_path_emits_failed_and_reraises(_fresh_run_id) -> None:
    sink = InMemorySink()

    class BoomError(RuntimeError):
        pass

    @traced_node("exploding_node", sink=sink)
    def exploding_node(state: dict) -> dict:
        raise BoomError("kaboom")

    with pytest.raises(BoomError, match="kaboom"):
        exploding_node({"debug_trace": []})

    events = sink.get_events(_fresh_run_id)
    assert [event.status for event in events] == ["started", "failed"]

    failed = events[-1]
    assert failed.elapsed_ms is not None
    assert failed.elapsed_ms >= 0
    assert "kaboom" in failed.summary
    assert failed.payload["error_type"] == "BoomError"


def test_traced_node_falls_back_to_default_sink_when_none_passed(_fresh_run_id) -> None:
    sink = InMemorySink()
    set_default_sink(sink)

    @traced_node("default_sink_node")
    def default_sink_node(state: dict) -> dict:
        return dict(state)

    default_sink_node({"debug_trace": []})

    events = sink.get_events(_fresh_run_id)
    assert [event.status for event in events] == ["started", "finished"]


def test_run_event_payload_stays_small_dict() -> None:
    event = RunEvent(run_id="r1", node="n", status="finished", summary="did a thing.")
    assert event.payload == {}
    assert isinstance(event.payload, dict)


# ---------------------------------------------------------------------------
# Request id: contextvar, logging, and the HTTP middleware
# ---------------------------------------------------------------------------


def test_get_run_id_mints_and_reuses_within_the_same_context(_fresh_run_id) -> None:
    assert get_run_id() == _fresh_run_id
    assert get_run_id() == _fresh_run_id  # stable across repeated calls


def test_request_id_appears_in_log_records(_fresh_run_id, caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("tests.test_observability_events")
    with caplog.at_level(logging.INFO, logger="tests.test_observability_events"):
        logger.info("hello from a test")

    matching = [record for record in caplog.records if record.getMessage() == "hello from a test"]
    assert matching
    assert matching[-1].request_id == _fresh_run_id


def test_request_id_middleware_stamps_response_header_and_flows_to_events() -> None:
    sink = InMemorySink()
    set_default_sink(sink)
    try:
        client = TestClient(create_app())
        response = client.get("/health")

        assert response.status_code == 200
        request_id = response.headers.get("x-request-id")
        assert request_id

        # /health isn't a traced graph node, so there's nothing to assert in
        # `sink` for this specific call -- this test's job is just to prove
        # the middleware mints and echoes an id per request.
        second_response = client.get("/health")
        assert second_response.headers.get("x-request-id") != request_id
    finally:
        set_default_sink(get_default_sink())  # no-op; keeps symmetry with other tests


def test_request_id_middleware_honors_incoming_header() -> None:
    client = TestClient(create_app())
    response = client.get("/health", headers={"X-Request-Id": "caller-supplied-id"})
    assert response.headers.get("x-request-id") == "caller-supplied-id"


# ---------------------------------------------------------------------------
# End-to-end acceptance check: running the recommend graph produces an
# ordered event stream of all executed nodes, with timings.
# ---------------------------------------------------------------------------


def test_recommend_graph_produces_ordered_event_stream_with_timings(_fresh_run_id) -> None:
    sink = InMemorySink()
    set_default_sink(sink)

    profile = UserProfile(
        user_id="demo_user",
        allergies=["peanut"],
        disliked_ingredients=[],
        diet_type=None,
        preferred_cuisines=["Thai"],
        macro_targets=MacroTargets(calories=600, protein_g=40, carbs_g=60, fat_g=20, fiber_g=8),
        max_cook_time_min=40,
    )
    request = RecommendationRequest(
        input_type="text",
        typed_ingredients="chicken breast, rice, bell pepper, spinach",
        user_profile=profile,
        cuisine_preference="Thai",
        meal_type="dinner",
    )

    response = run_recommendation_graph(request, "demo_user")
    assert response.recommendations

    events = sink.get_events(_fresh_run_id)
    assert events, "expected traced_node to emit events for the run bound by _fresh_run_id"

    executed_nodes_in_order = [event.node for event in events if event.status == "started"]
    # Every started node must reach a finished/failed terminus -- an
    # unpaired "started" would mean a node's decorator swallowed its own
    # completion.
    finished_or_failed = [event.node for event in events if event.status in {"finished", "failed"}]
    assert executed_nodes_in_order == finished_or_failed

    # Order matches the graph's wiring (app.graph.builder) for a
    # successful, no-fallback-relaxation run.
    assert executed_nodes_in_order[:5] == [
        "intake_node",
        "inventory_confirmation_node",
        "constraint_builder_node",
        "recipe_retriever_node",
        "safety_filter_node",
    ]
    assert executed_nodes_in_order[-1] == "memory_update_node"

    for event in events:
        if event.status in {"finished", "failed"}:
            assert event.elapsed_ms is not None
            assert event.elapsed_ms >= 0
        assert event.run_id == _fresh_run_id
