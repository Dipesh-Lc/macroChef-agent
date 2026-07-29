from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recommendation import RecommendationResponse

# ROADMAP.md Phase 3, Step 3.2: wire schemas for the checkpointed,
# HITL-capable recommend flow (app.api.routes_runs). Additive to
# RecommendationRequest/RecommendationResponse (app.schemas.recommendation)
# -- those stay exactly as they are for the existing POST /recipes/recommend
# and /recipes/recommend/stream endpoints, which never pause.


class RunStatusResponse(BaseModel):
    thread_id: str
    status: Literal["awaiting_input", "completed"]
    # The raw interrupt() payload (app.graph.nodes.inventory_confirmation_node)
    # when status == "awaiting_input": {"reason", "observations",
    # "all_observations"} -- see that node's docstring. None otherwise.
    awaiting: dict | None = None
    # Populated only when status == "completed".
    result: RecommendationResponse | None = None


class ResumeRunRequest(BaseModel):
    # The caller's COMPLETE corrected inventory -- not just the corrected
    # subset of low-confidence items -- becomes `confirmed_inventory`
    # directly on resume (see inventory_confirmation_node's docstring for
    # why: it replaces auto-confirmation entirely for a HITL-paused run,
    # it doesn't merge with it).
    confirmed_inventory: list[ConfirmedIngredient] = Field(min_length=1)
