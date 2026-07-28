from fastapi import APIRouter, Depends, Query

from app.dependencies import get_session_user
from app.observability.llm_ledger import build_usage_response
from app.schemas.admin import LLMUsageResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/llm-usage", response_model=LLMUsageResponse)
def get_llm_usage(
    days: int = Query(default=7, ge=1, le=90),
    session_user_id: str = Depends(get_session_user),
) -> LLMUsageResponse:
    """Cost/usage dashboard for the LLM call ledger (ROADMAP.md Phase 1,
    Step 1.2): calls, tokens, and estimated cost aggregated by
    (day, provider, model, purpose) over the last `days` days.

    SCOPING (deliberate, see this task's executor report for the full
    reasoning): `Depends(get_session_user)` here is an access-control speed
    bump only, NOT per-user data isolation -- the aggregates returned are
    GLOBAL (every user's calls), never filtered to `session_user_id`. This
    app has no admin-role concept (sessions are anonymous, one per
    browser); scoping this endpoint to "the caller's own calls" would make
    it useless for its actual purpose (a maintainer cost dashboard), so
    instead it requires ANY valid session as a minimal deterrent against a
    fully anonymous crawler. Consequence: any authenticated session
    (i.e. any browser that has ever hit POST /session) can see total
    app-wide LLM spend. Acceptable for a single-maintainer demo app today;
    must be replaced with a real admin check before this app ever has
    multiple real accounts with something to hide from each other -- see
    docs/BACKLOG.md.
    """
    del session_user_id
    return build_usage_response(days)
