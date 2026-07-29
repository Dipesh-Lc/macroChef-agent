"""ROADMAP.md Phase 3, Step 3.3 -- the "Chef" conversational agent.

Mirrors tests/test_hitl_resume.py's session-secret/DB-isolation fixture
pattern. The LLM is scripted end-to-end via a monkeypatched `app.agent.
chef_agent.generate_structured` (this module's own ONE choke point for LLM
calls) -- no real provider HTTP happens anywhere in this file, matching the
existing `MODEL_PROVIDER=mock`-adjacent test convention used across
tests/test_model_provider.py.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.agent.chef_agent as chef_agent_module
import app.agent.memory as chef_memory_module
import app.agent.tools as tools_module
import app.api.routes_chat as routes_chat_module
import app.data.agent_note_repository as agent_note_repo_module
import app.data.chat_thread_repository as chat_thread_repo_module
import app.data.recipe_library_repository as recipe_library_repo_module
import app.graph.builder as builder_module
import app.services.memory_service as memory_service_module
from app.agent.chef_agent import ChefStep, evaluate_response_gate, run_chef_turn
from app.agent.memory import ToolCallLogEntry
from app.agent.prompts import FALLBACK_MESSAGE
from app.agent.tools import TOOL_NAMES, GetUserContextArgs, ToolContext, dispatch_tool_call
from app.config import get_settings
from app.data.agent_note_repository import AgentNoteRepository
from app.data.db import Base
from app.data.recipe_library_repository import RecipeLibraryRepository
from app.data.repositories import FeedbackRepository
from app.dependencies import SESSION_TOKEN_HEADER, mint_session_token
from app.main import create_app
from app.schemas.ingredient import Ingredient
from app.schemas.recipe import Recipe
from app.schemas.recommendation import FeedbackRequest
from app.schemas.user import UserProfile

# ---------------------------------------------------------------------------
# Fixtures -- session secret + one shared isolated in-memory DB, monkeypatched
# into every module that opens its own SessionLocal-derived session (mirrors
# tests/test_stream_endpoint.py's/_test_hitl_resume.py's identical pattern).
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "chef-agent-test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(chat_thread_repo_module, "SessionLocal", test_session_local)
    monkeypatch.setattr(agent_note_repo_module, "SessionLocal", test_session_local)
    monkeypatch.setattr(chef_memory_module, "SessionLocal", test_session_local)
    monkeypatch.setattr(tools_module, "SessionLocal", test_session_local)
    monkeypatch.setattr(routes_chat_module, "SessionLocal", test_session_local)
    monkeypatch.setattr(recipe_library_repo_module, "SessionLocal", test_session_local)
    monkeypatch.setattr(memory_service_module, "SessionLocal", test_session_local)
    monkeypatch.setattr(memory_service_module, "init_db", lambda: None)
    return test_session_local


@pytest.fixture(autouse=True)
def _isolated_checkpointer(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """`app.agent.chef_agent.get_compiled_chef_graph` reuses `app.graph.
    builder._get_checkpointer()` -- the process-wide `@lru_cache`d
    SqliteSaver singleton, which otherwise opens a connection to the real
    `DATABASE_URL` default (`sqlite:///./macrochef.db`, the actual repo-root
    dev DB) the moment any test in this file runs. Redirect it at a tmp file
    and clear the cache before/after, mirroring tests/test_hitl_resume.py's
    identical `_use_checkpoint_db`/`_clear_compiled_graph_cache` fixtures --
    this suite must never write LangGraph checkpoint state into the
    developer's real database."""
    checkpoint_db_path = tmp_path / "chef_agent_test_checkpoints.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{checkpoint_db_path}")
    get_settings.cache_clear()
    builder_module._get_checkpointer.cache_clear()
    yield
    builder_module._get_checkpointer.cache_clear()
    get_settings.cache_clear()


def _script_llm(monkeypatch: pytest.MonkeyPatch, steps: list[ChefStep]) -> None:
    """Monkeypatch the Chef agent's ONE LLM choke point
    (`app.agent.chef_agent.generate_structured`) with a scripted queue of
    `ChefStep`s, popped one per call regardless of `provider`/`prompt`. Once
    exhausted, keeps returning a safe final_answer so a test bug never hangs
    instead of failing loudly."""
    queue = list(steps)

    def _fake_generate_structured(provider, prompt, schema, settings, *, purpose, **kwargs):
        assert schema is ChefStep
        if queue:
            return queue.pop(0)
        return ChefStep(step_type="final_answer", content="(script exhausted)")

    monkeypatch.setattr(chef_agent_module, "generate_structured", _fake_generate_structured)


def _client() -> TestClient:
    return TestClient(create_app())


def _token(user_id: str) -> str:
    return mint_session_token(user_id, get_settings())


def _headers(user_id: str) -> dict[str, str]:
    return {SESSION_TOKEN_HEADER: _token(user_id)}


_SAFE_RECIPE = Recipe(
    recipe_id="test_recipe_1",
    title="High-Protein Turkey Bowl",
    ingredients=[Ingredient(name="ground turkey", amount=200, unit="g")],
    allergens=[],
)


# ---------------------------------------------------------------------------
# 1. Tool-call sequence includes check_recipe_safety.
# ---------------------------------------------------------------------------


def test_tool_call_sequence_includes_check_recipe_safety(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tools_module,
        "get_recipe_by_id",
        lambda recipe_id: _SAFE_RECIPE if recipe_id == "test_recipe_1" else None,
    )
    _script_llm(
        monkeypatch,
        [
            ChefStep(
                step_type="tool_call",
                tool="check_recipe_safety",
                tool_args={"recipe_ids": ["test_recipe_1"]},
            ),
            ChefStep(step_type="final_answer", content="That turkey bowl works for you."),
        ],
    )

    profile = UserProfile(allergies=["peanuts"])
    result = run_chef_turn(
        "thread-seq-1",
        "user-a",
        profile,
        "high-protein dinner from my pantry, I'm allergic to peanuts",
    )

    tool_names = [call["tool"] for call in result.tool_calls]
    assert "check_recipe_safety" in tool_names
    assert result.assistant_message == "That turkey bowl works for you."


# ---------------------------------------------------------------------------
# 2. Response gate blocks an answer lacking a safety call; retry path fires
#    end-to-end.
# ---------------------------------------------------------------------------


def test_response_gate_blocks_missing_safety_check_directly() -> None:
    """Pure-function gate test -- no LLM, no tool dispatch."""
    log = [
        ToolCallLogEntry(
            tool="search_recipes",
            args={},
            ok=True,
            summary="Found 1 recipe(s): Pad Thai.",
            raw={"recipes": [{"recipe_id": "pad_thai", "title": "Pad Thai"}]},
        )
    ]
    gate = evaluate_response_gate(log, "Here's Pad Thai, enjoy!")
    assert gate.passed is False
    assert gate.uncovered_recipe_ids == ["pad_thai"]


def test_response_gate_blocks_zero_tool_call_turn() -> None:
    """Second FULL TREATMENT review finding: a turn with NO tool calls at
    all must never pass just because there's nothing to cross-reference --
    otherwise a hallucinated, never-searched, never-checked recipe
    recommendation sails through untouched."""
    gate = evaluate_response_gate([], "Try Grandma's Peanut Butter Stew, it's great!")
    assert gate.passed is False
    assert gate.uncovered_recipe_ids == []
    assert "No tool was called" in gate.reason


def test_response_gate_blocks_recipe_checked_and_rejected_but_endorsed() -> None:
    """Second FULL TREATMENT review finding: a recipe_id that WAS checked
    but came back `is_valid=False` must not count as "covered" just because
    check_recipe_safety was called on it -- the gate must compare the
    verdict, not just whether the tool ran."""
    log = [
        ToolCallLogEntry(
            tool="check_recipe_safety",
            args={"recipe_ids": ["peanut_noodles"]},
            ok=True,
            summary="Checked 1 recipe(s): 0 safe, 1 rejected.",
            raw={
                "results": [
                    {
                        "recipe_id": "peanut_noodles",
                        "result": {"is_valid": False, "rejection_reason": "contains peanuts"},
                    }
                ]
            },
            recipe_ids_covered=["peanut_noodles"],
        ),
        ToolCallLogEntry(
            tool="search_recipes",
            args={},
            ok=True,
            summary="Found 1 recipe(s): Peanut Noodles.",
            raw={"recipes": [{"recipe_id": "peanut_noodles", "title": "Peanut Noodles"}]},
        ),
    ]
    gate = evaluate_response_gate(log, "Peanut Noodles is totally fine for you, enjoy!")
    assert gate.passed is False
    assert gate.uncovered_recipe_ids == ["peanut_noodles"]


class _FakeRetriever:
    """Stand-in for RecipeRetriever -- returns one canned recipe, no corpus
    load, no vector store."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def retrieve(self, **kwargs):
        return [
            Recipe(
                recipe_id="pad_thai",
                title="Pad Thai",
                ingredients=[Ingredient(name="rice noodles")],
            )
        ]


def test_response_gate_retry_fires_end_to_end(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(tools_module, "RecipeRetriever", _FakeRetriever)
    unsafe_answer = "Here's Pad Thai, enjoy!"
    _script_llm(
        monkeypatch,
        [
            ChefStep(
                step_type="tool_call", tool="search_recipes", tool_args={"ingredients": ["noodles"]}
            ),
            # First final_answer names "Pad Thai" without ever calling
            # check_recipe_safety -> gate blocks, retries once.
            ChefStep(step_type="final_answer", content=unsafe_answer),
            # Retry: the (scripted) model makes the exact same mistake again
            # -> gate blocks a second time -> fail-closed fallback.
            ChefStep(step_type="final_answer", content=unsafe_answer),
        ],
    )

    with caplog.at_level(logging.ERROR):
        result = run_chef_turn("thread-gate-1", "user-a", UserProfile(), "suggest a noodle dish")

    assert result.assistant_message == FALLBACK_MESSAGE
    assert any("blocked thread" in record.message for record in caplog.records)


def test_zero_tool_call_turn_retries_then_fails_closed_end_to_end(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A model that answers immediately, calling no tool at all, must be
    forced through the same retry-then-fallback path -- never silently
    accepted just because there's nothing to cross-reference against."""
    _script_llm(
        monkeypatch,
        [
            # First turn: answers immediately, zero tool calls -> gate
            # blocks ("No tool was called"), retries once.
            ChefStep(step_type="final_answer", content="Sure, try a stir fry!"),
            # Retry: the (scripted) model makes the same mistake again ->
            # gate blocks a second time -> fail-closed fallback.
            ChefStep(step_type="final_answer", content="Sure, try a stir fry!"),
        ],
    )

    with caplog.at_level(logging.ERROR):
        result = run_chef_turn("thread-gate-2", "user-a", UserProfile(), "what should I cook?")

    assert result.assistant_message == FALLBACK_MESSAGE
    assert any("blocked thread" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# 3. Cross-user get_user_context isolation.
# ---------------------------------------------------------------------------


def test_get_user_context_tool_has_no_user_id_argument() -> None:
    """Structural guarantee: the LLM cannot pass a different user_id even if
    it tried -- the args schema simply has no such field."""
    assert "user_id" not in GetUserContextArgs.model_fields


def test_get_user_context_is_isolated_per_session_user(monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = chef_memory_module.SessionLocal  # patched by _isolated_db
    session = session_factory()
    try:
        FeedbackRepository(session).add_feedback(
            "user_b", FeedbackRequest(recipe_id="secret_recipe", feedback_type="liked")
        )
    finally:
        session.close()
    RecipeLibraryRepository().save_recipe(
        "user_b",
        Recipe(
            recipe_id="user_b_only",
            title="User B's Secret Recipe",
            ingredients=[Ingredient(name="salt")],
        ),
    )

    ctx_a = ToolContext(user_id="user_a", user_profile=UserProfile())
    result_a = dispatch_tool_call(ctx_a, "get_user_context", {})

    assert result_a.ok is True
    saved_ids_a = {row["recipe_id"] for row in result_a.raw["saved_recipes"]}
    feedback_ids_a = {row["recipe_id"] for row in result_a.raw["recent_feedback"]}
    assert "user_b_only" not in saved_ids_a
    assert "secret_recipe" not in feedback_ids_a


# ---------------------------------------------------------------------------
# 4. Cross-user chat-thread access is 404 (mirrors
#    tests/test_hitl_resume.py::test_cross_user_resume_is_404).
# ---------------------------------------------------------------------------


def test_cross_user_chat_thread_access_is_404() -> None:
    client = _client()
    created = client.post("/chat", json={"user_profile": {}}, headers=_headers("user_a"))
    assert created.status_code == 200
    thread_id = created.json()["thread_id"]

    other_headers = _headers("user_b")
    get_resp = client.get(f"/chat/{thread_id}", headers=other_headers)
    assert get_resp.status_code == 404

    message_resp = client.post(
        f"/chat/{thread_id}/message", json={"message": "hello"}, headers=other_headers
    )
    assert message_resp.status_code == 404

    # The owning user can still read it -- proves the 404 above is a real
    # ownership check, not a broken thread_id.
    own_get = client.get(f"/chat/{thread_id}", headers=_headers("user_a"))
    assert own_get.status_code == 200

    unknown = client.get("/chat/never-existed", headers=_headers("user_a"))
    assert unknown.status_code == 404


# ---------------------------------------------------------------------------
# 5. remember() cap/eviction; human-only delete works; LLM has no delete tool.
# ---------------------------------------------------------------------------


def test_remember_caps_at_30_and_evicts_oldest() -> None:
    repo = AgentNoteRepository()
    for i in range(31):
        repo.remember("user_evict", f"note {i}")

    active = repo.list_active("user_evict")
    assert len(active) == 30
    assert all(note.note != "note 0" for note in active)
    assert active[-1].note == "note 30"


def test_remember_truncates_over_char_cap() -> None:
    repo = AgentNoteRepository()
    row = repo.remember("user_cap", "x" * 500)
    assert len(row.note) == AgentNoteRepository.NOTE_CHAR_CAP


def test_human_only_note_delete_via_dispatch_and_endpoint() -> None:
    ctx = ToolContext(user_id="user_del", user_profile=UserProfile())
    result = dispatch_tool_call(ctx, "remember", {"note": "dislikes cilantro"})
    assert result.ok is True

    repo = AgentNoteRepository()
    note_id = repo.list_active("user_del")[0].id

    client = _client()
    # Wrong user cannot delete it.
    wrong_delete = client.delete(f"/chat/notes/{note_id}", headers=_headers("someone_else"))
    assert wrong_delete.status_code == 404
    assert len(repo.list_active("user_del")) == 1

    own_delete = client.delete(f"/chat/notes/{note_id}", headers=_headers("user_del"))
    assert own_delete.status_code == 200
    assert len(repo.list_active("user_del")) == 0


def test_llm_has_no_delete_tool() -> None:
    assert "delete_note" not in TOOL_NAMES
    assert "forget" not in TOOL_NAMES


# ---------------------------------------------------------------------------
# 6. ground_nutrition rate-limit slicing -- budget exhausted -> excess
#    ingredients land in ungrounded_ingredients, never a hard failure.
# ---------------------------------------------------------------------------


class _FakeRateLimiter:
    def __init__(self, allow_count: int) -> None:
        self._allow_count = allow_count
        self._calls = 0

    def allow(self, key, limit, window_seconds, *, now=None) -> bool:
        self._calls += 1
        return self._calls <= self._allow_count

    def reset(self) -> None:
        self._calls = 0


def test_ground_nutrition_rate_limit_slicing_never_hard_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_limiter = _FakeRateLimiter(allow_count=1)
    monkeypatch.setattr(tools_module, "get_rate_limiter", lambda: fake_limiter)

    ctx = ToolContext(user_id="user_rl", user_profile=UserProfile())
    args = {
        "ingredients": [
            {"name": "flour"},
            {"name": "sugar"},
            {"name": "salt"},
        ]
    }
    result = dispatch_tool_call(ctx, "ground_nutrition", args)

    assert result.ok is True
    assert result.error is None
    assert {"sugar", "salt"}.issubset(set(result.raw["ungrounded_ingredients"]))
