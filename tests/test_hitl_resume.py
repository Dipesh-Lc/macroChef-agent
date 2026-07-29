"""ROADMAP.md Phase 3, Step 3.2 -- LangGraph checkpointer + true HITL
inventory confirmation (app.api.routes_runs).

Vision extraction is mocked (`app.graph.nodes.extract_inventory_from_image`)
to deterministically return one low-confidence observation -- this suite
tests the checkpoint/interrupt/resume/ownership mechanics, not vision
quality (see tests/test_vision_service.py for that). `MACROCHEF_ENABLE_VISION`
is set True only in these tests so `intake_node` actually calls the (mocked)
extractor.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.data.graph_run_repository as graph_run_repo_module
import app.graph.nodes as nodes_module
from app.config import get_settings
from app.data.db import Base
from app.dependencies import SESSION_TOKEN_HEADER, mint_session_token
from app.graph import builder as builder_module
from app.main import create_app
from app.schemas.inventory import InventoryObservation


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    """See tests/test_rate_limiting.py's identical fixture for why this is
    needed regardless of ambient .env state."""
    monkeypatch.setenv("SESSION_SECRET", "hitl-test-session-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolated_graph_run_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """GraphRunRepository (the thread_id -> owner_user_id ownership check)
    gets its own isolated in-memory DB -- orthogonal to the checkpointer's
    own storage under test (see `checkpoint_db_path`/`_use_checkpoint_db`
    below), mirrors tests/test_rate_limiting.py's `_isolated_library_db`."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(graph_run_repo_module, "SessionLocal", test_session_local)


@pytest.fixture(autouse=True)
def _clear_compiled_graph_cache():
    """`get_compiled_macrochef_graph` itself is NOT cached (see its
    docstring), but the checkpointer/connection it uses
    (`_get_checkpointer`) IS `@lru_cache`d process-wide by design. Clear
    around every test so one test's DATABASE_URL/checkpointer connection
    never leaks into the next. (`build_macrochef_graph`, the uncheckpointed
    graph, is also deliberately not cached -- nothing to clear there.)"""
    builder_module._get_checkpointer.cache_clear()
    yield
    builder_module._get_checkpointer.cache_clear()


@pytest.fixture()
def checkpoint_db_path(tmp_path):
    return tmp_path / "hitl_checkpoints.db"


def _use_checkpoint_db(monkeypatch: pytest.MonkeyPatch, path) -> None:
    """Points the CHECKPOINTED graph's SqliteSaver at a real file (never
    :memory:) -- required for the process-restart test below, and a
    faithful stand-in for `DATABASE_URL` driving `_select_checkpointer`
    (ROADMAP 3.2) in production."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")
    get_settings.cache_clear()
    builder_module._get_checkpointer.cache_clear()


def _mock_low_confidence_vision(
    monkeypatch: pytest.MonkeyPatch, name: str = "shrimp paste"
) -> None:
    def fake_extract(image_path):
        return [
            InventoryObservation(
                raw_name=name,
                normalized_name=name,
                confidence=0.4,
                source="vision",
                needs_confirmation=True,
            )
        ]

    monkeypatch.setattr(nodes_module, "extract_inventory_from_image", fake_extract)
    monkeypatch.setenv("MACROCHEF_ENABLE_VISION", "true")
    get_settings.cache_clear()


def _token(user_id: str) -> str:
    return mint_session_token(user_id, get_settings())


def _headers(user_id: str) -> dict[str, str]:
    return {SESSION_TOKEN_HEADER: _token(user_id)}


def _client() -> TestClient:
    return TestClient(create_app())


_START_PAYLOAD = {
    "input_type": "image",
    "image_path": "fake.jpg",
    "user_profile": {},
}


# ---------------------------------------------------------------------------
# Case 1: interrupted run persists.
# ---------------------------------------------------------------------------


def test_interrupted_run_persists(monkeypatch: pytest.MonkeyPatch, checkpoint_db_path) -> None:
    _use_checkpoint_db(monkeypatch, checkpoint_db_path)
    _mock_low_confidence_vision(monkeypatch)
    client = _client()
    headers = _headers("user_a")

    start = client.post("/runs", json=_START_PAYLOAD, headers=headers)
    assert start.status_code == 200
    body = start.json()
    assert body["status"] == "awaiting_input"
    assert body["awaiting"]["reason"] == "low_confidence_inventory"
    assert any(obs["normalized_name"] == "shrimp paste" for obs in body["awaiting"]["observations"])
    thread_id = body["thread_id"]

    # GET must reflect the paused status WITHOUT re-running the graph.
    status = client.get(f"/runs/{thread_id}", headers=headers)
    assert status.status_code == 200
    status_body = status.json()
    assert status_body["status"] == "awaiting_input"
    assert status_body["awaiting"]["reason"] == "low_confidence_inventory"


# ---------------------------------------------------------------------------
# Case 2: resume with corrections produces recommendations honoring them.
# ---------------------------------------------------------------------------


def test_resume_with_corrections_are_honored(
    monkeypatch: pytest.MonkeyPatch, checkpoint_db_path
) -> None:
    _use_checkpoint_db(monkeypatch, checkpoint_db_path)
    _mock_low_confidence_vision(monkeypatch, name="shrimp paste")
    client = _client()
    headers = _headers("user_a")

    start = client.post("/runs", json=_START_PAYLOAD, headers=headers)
    thread_id = start.json()["thread_id"]

    resume_payload = {"confirmed_inventory": [{"name": "miso paste", "quantity": "1 tbsp"}]}
    resumed = client.post(f"/runs/{thread_id}/resume", json=resume_payload, headers=headers)
    assert resumed.status_code == 200
    body = resumed.json()
    assert body["status"] == "completed"
    assert body["result"]["errors"] == []

    # The load-bearing property: confirmed_inventory in the resumed state is
    # the human's CORRECTED ingredient, not the original low-confidence
    # guess -- downstream nodes (retrieval/scoring/safety_filter) consume
    # this, never the discarded "shrimp paste" guess. Inspected directly at
    # the state level since confirmed_inventory isn't itself part of
    # RecommendationResponse's wire shape.
    graph = builder_module.get_compiled_macrochef_graph()
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    confirmed_names = [item["name"] for item in snapshot.values["confirmed_inventory"]]
    assert confirmed_names == ["miso paste"]
    assert "shrimp paste" not in confirmed_names


# ---------------------------------------------------------------------------
# Case 3: cross-user resume is 404 (advisor-reviewed decision -- see
# app.data.models.GraphRun's docstring for why 404, not 403).
# ---------------------------------------------------------------------------


def test_cross_user_resume_is_404(monkeypatch: pytest.MonkeyPatch, checkpoint_db_path) -> None:
    _use_checkpoint_db(monkeypatch, checkpoint_db_path)
    _mock_low_confidence_vision(monkeypatch)
    client = _client()

    start = client.post("/runs", json=_START_PAYLOAD, headers=_headers("user_a"))
    thread_id = start.json()["thread_id"]

    other_headers = _headers("user_b")
    resume_payload = {"confirmed_inventory": [{"name": "miso paste"}]}
    resumed = client.post(f"/runs/{thread_id}/resume", json=resume_payload, headers=other_headers)
    assert resumed.status_code == 404

    status = client.get(f"/runs/{thread_id}", headers=other_headers)
    assert status.status_code == 404

    # The owning user can still resume it -- proves the 404 above is a real
    # ownership check, not a broken thread_id.
    own_resume = client.post(
        f"/runs/{thread_id}/resume", json=resume_payload, headers=_headers("user_a")
    )
    assert own_resume.status_code == 200


def test_resume_of_nonexistent_thread_is_404(
    monkeypatch: pytest.MonkeyPatch, checkpoint_db_path
) -> None:
    _use_checkpoint_db(monkeypatch, checkpoint_db_path)
    client = _client()
    resp = client.get("/runs/never-existed", headers=_headers("user_a"))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Case 4: process-restart-then-resume works with SqliteSaver.
# ---------------------------------------------------------------------------


def test_process_restart_then_resume_works(
    monkeypatch: pytest.MonkeyPatch, checkpoint_db_path
) -> None:
    _use_checkpoint_db(monkeypatch, checkpoint_db_path)
    _mock_low_confidence_vision(monkeypatch)
    client = _client()
    headers = _headers("user_a")

    start = client.post("/runs", json=_START_PAYLOAD, headers=headers)
    assert start.json()["status"] == "awaiting_input"
    thread_id = start.json()["thread_id"]

    # Simulate a process restart: tear down the cached checkpointer
    # connection -- the only thing holding the sqlite connection -- and
    # let it reopen fresh against the SAME DATABASE_URL/file on next use.
    # If persistence were in-memory only, this checkpoint would be gone.
    builder_module._get_checkpointer.cache_clear()
    client_after_restart = _client()

    resume_payload = {"confirmed_inventory": [{"name": "miso paste"}]}
    resumed = client_after_restart.post(
        f"/runs/{thread_id}/resume", json=resume_payload, headers=headers
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# Regression guard: hitl_enabled=True must never reach the UNCHECKPOINTED
# graph (app.api.routes_runs is the only caller that ever sets it, and it
# only ever invokes get_compiled_macrochef_graph()). Documents *why* that
# invariant matters -- advisor-flagged residual risk from the 3.2 design
# consult -- rather than assuming it's obviously safe.
# ---------------------------------------------------------------------------


def test_hitl_enabled_state_on_uncheckpointed_graph_is_unresumable_not_a_hang() -> None:
    """`interrupt()` against a graph compiled with no checkpointer does NOT
    raise and does NOT hang -- it returns normally with an `__interrupt__`
    marker in the result, but there is no persisted checkpoint for any
    `Command(resume=...)` call to ever attach to: the run is silently
    unresumable. This is exactly why `hitl_enabled=True` must be reachable
    ONLY through app.api.routes_runs's checkpointed
    get_compiled_macrochef_graph() -- never build_macrochef_graph() (used
    by the existing POST /recipes/recommend and /recipes/recommend/stream
    endpoints, which is precisely why those endpoints never set
    hitl_enabled)."""
    from app.graph.builder import build_macrochef_graph
    from app.graph.state import MacroChefState
    from app.schemas.inventory import InventoryObservation
    from app.schemas.user import UserProfile

    graph = build_macrochef_graph()
    # No image_path/typed_ingredients set, so intake_node's own extraction
    # is a no-op and the pre-set low-confidence observation below survives
    # merge_inventory_observations unchanged.
    state = MacroChefState(
        user_id="u1",
        hitl_enabled=True,
        input_type="image",
        user_profile=UserProfile(),
        raw_inventory_observations=[
            InventoryObservation(
                raw_name="shrimp paste",
                normalized_name="shrimp paste",
                confidence=0.4,
                source="vision",
                needs_confirmation=True,
            )
        ],
    )

    result = graph.invoke(state.model_dump())

    assert "__interrupt__" in result
