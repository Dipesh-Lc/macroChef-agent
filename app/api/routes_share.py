"""Roadmap item "Shareable plan URLs" (Phase 4 item 4, docs/ROADMAP.md).

POST /share is AUTHENTICATED (requires the same signed session token every
other per-user write in this app requires) -- the caller must already be a
MacroChef session holder to mint a share link. GET /share/{id} is
DELIBERATELY UNAUTHENTICATED -- that is the entire point of a public share
link -- and is instead gated by a caller-IP rate limit
(`require_share_view_rate_limit`).

No LLM anywhere on this path -- see `app.services.share_service`'s
docstring and `tests/test_share_no_llm_import.py`.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import require_share_create_rate_limit, require_share_view_rate_limit
from app.schemas.share import ShareCreateRequest, ShareCreateResponse, SharedPlanView
from app.services.share_service import create_share, get_share

router = APIRouter(prefix="/share", tags=["share"])


@router.post("", response_model=ShareCreateResponse)
def create_share_link(
    request: ShareCreateRequest,
    user_id: str = Depends(require_share_create_rate_limit),
) -> ShareCreateResponse:
    """Builds the public snapshot via `app.services.share_service.
    create_share` -- the caller's own request object (a `Recipe`/`DayPlan`/
    `BatchPlan`/`WeeklyPlan` it already holds) is READ from, mapped through
    the server-side allowlist, and never persisted or echoed verbatim (see
    `share_service`'s module docstring, the load-bearing safety property of
    this whole feature). `user_id` is the verified session identity (see
    `app.dependencies.get_session_user`, which `require_share_create_rate_
    limit` itself depends on) -- never a client-supplied value."""
    return create_share(request, owner_user_id=user_id)


@router.get("/{share_id}", response_model=SharedPlanView)
def get_share_view(
    share_id: str,
    _caller_id: str = Depends(require_share_view_rate_limit),
) -> SharedPlanView:
    """UNAUTHENTICATED by design. Returns 404 for BOTH a missing id and a
    revoked (`is_active=False`) one -- `app.services.share_service.
    get_share` already collapses those two cases into a single `None`, so
    there is no oracle here for "exists but was revoked" vs "never
    existed". Never returns the ORM row or `owner_user_id` -- only the
    `SharedPlanView` schema's own fields (`plan_type`, `content`,
    `disclaimer`), built from `SharedPlan.content` + `SharedPlan.plan_type`
    alone."""
    view = get_share(share_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return view
