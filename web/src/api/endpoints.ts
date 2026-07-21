/**
 * Endpoint-specific wrappers over `apiRequest` (see `./client.ts`). Kept
 * separate from the transport module so each call site only needs to know
 * its own request/response shape, not the retry/session-bootstrap plumbing.
 */
import { apiRequest } from "./client";
import type {
  DayPlanRequest,
  DayPlanResponse,
  FeedbackRequest,
  InventoryObservation,
  RecommendationRequest,
  RecommendationResponse,
  ShareCreateRequest,
  ShareCreateResponse,
  SharedPlanView,
  ShoppingListRequest,
  ShoppingListResponse,
} from "./types";

// POST /recipes/recommend can take 30-90s (LLM parsing + corpus scoring +
// USDA grounding lookups) -- see HomePage's staged loading copy.
const RECOMMEND_TIMEOUT_MS = 90_000;

// POST /plan/day runs constraint_engine.validate_recipe over the full
// corpus plus exhaustive combination enumeration -- generous but bounded,
// same idea as RECOMMEND_TIMEOUT_MS.
const DAY_PLAN_TIMEOUT_MS = 60_000;

/** Public call: no session bootstrap, no CSRF header. */
export async function extractInventory(typedIngredients: string): Promise<InventoryObservation[]> {
  const body = new URLSearchParams({ typed_ingredients: typedIngredients });
  return apiRequest<InventoryObservation[]>("/inventory/extract", {
    method: "POST",
    body,
  });
}

/** Session-required: bootstraps a session and sends the CSRF header. */
export async function recommendRecipes(
  request: RecommendationRequest,
): Promise<RecommendationResponse> {
  return apiRequest<RecommendationResponse>("/recipes/recommend", {
    method: "POST",
    json: request,
    sessionRequired: true,
    timeoutMs: RECOMMEND_TIMEOUT_MS,
  });
}

/** Session-required: bootstraps a session and sends the CSRF header. */
export async function postFeedback(request: FeedbackRequest): Promise<void> {
  await apiRequest<unknown>("/feedback", {
    method: "POST",
    json: request,
    sessionRequired: true,
  });
}

/**
 * Public call: no session bootstrap, no CSRF header. Every candidate recipe
 * is safety-cleared server-side by `app.services.constraint_engine.
 * validate_recipe` before the solver ever sees it (see
 * `app.api.routes_day_planner.plan_day`'s docstring) -- this wrapper makes
 * no safety decision of its own, it only calls the endpoint.
 */
export async function planDay(request: DayPlanRequest): Promise<DayPlanResponse> {
  return apiRequest<DayPlanResponse>("/plan/day", {
    method: "POST",
    json: request,
    timeoutMs: DAY_PLAN_TIMEOUT_MS,
  });
}

/** Public call: no session bootstrap, no CSRF header. Pure quantity
 * arithmetic over an already safety-cleared `DayPlan` -- see
 * `app.api.routes_day_planner.plan_shopping_list`'s docstring. */
export async function getShoppingList(
  request: ShoppingListRequest,
): Promise<ShoppingListResponse> {
  return apiRequest<ShoppingListResponse>("/plan/shopping-list", {
    method: "POST",
    json: request,
  });
}

/** Session-required: bootstraps a session and sends the CSRF header -- see
 * `app.api.routes_share.create_share_link`'s docstring for why POST /share
 * needs an authenticated caller even though the resulting link is public. */
export async function createShare(request: ShareCreateRequest): Promise<ShareCreateResponse> {
  return apiRequest<ShareCreateResponse>("/share", {
    method: "POST",
    json: request,
    sessionRequired: true,
  });
}

/** Public call: no session bootstrap, no CSRF header -- this is the whole
 * point of a public share link (see `app.api.routes_share.get_share_view`'s
 * docstring). A missing OR revoked share both surface as a 404, which
 * `apiRequest` turns into a `NotFoundError` (see client.ts) the caller can
 * distinguish from other failures via `error instanceof NotFoundError`. */
export async function getSharedPlan(shareId: string): Promise<SharedPlanView> {
  return apiRequest<SharedPlanView>(`/share/${encodeURIComponent(shareId)}`, {
    method: "GET",
  });
}
