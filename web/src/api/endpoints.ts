/**
 * Endpoint-specific wrappers over `apiRequest` (see `./client.ts`). Kept
 * separate from the transport module so each call site only needs to know
 * its own request/response shape, not the retry/session-bootstrap plumbing.
 */
import { apiRequest } from "./client";
import type {
  BatchPlanRequest,
  BatchPlanResponse,
  DayPlanRequest,
  DayPlanResponse,
  DeleteRecipeResponse,
  DetailedInstructionsRequest,
  DetailedInstructionsResponse,
  FeedbackRequest,
  InventoryObservation,
  Recipe,
  RecipeDiscoveryRequest,
  RecipeDiscoveryResponse,
  RecommendationRequest,
  RecommendationResponse,
  ReindexLibraryResponse,
  SaveRecipeCandidatesRequest,
  SaveRecipeCandidatesResponse,
  ShareCreateRequest,
  ShareCreateResponse,
  SharedPlanView,
  ShoppingListRequest,
  ShoppingListResponse,
  UserRecipeLibraryResponse,
  WeeklyPlanRequest,
  WeeklyPlanResponse,
} from "./types";

// POST /recipes/recommend can take 30-90s (LLM parsing + corpus scoring +
// USDA grounding lookups) -- see HomePage's staged loading copy.
const RECOMMEND_TIMEOUT_MS = 90_000;

// POST /plan/day runs constraint_engine.validate_recipe over the full
// corpus plus exhaustive combination enumeration -- generous but bounded,
// same idea as RECOMMEND_TIMEOUT_MS.
const DAY_PLAN_TIMEOUT_MS = 60_000;

// POST /plan/batch is a single filter-then-sort-then-take-top pass (see
// `app.services.batch_planner`'s module docstring -- NOT combinatorial
// enumeration like `assemble_day_plan`), but still runs
// constraint_engine.validate_recipe over the full corpus first, so it gets
// the same generous-but-bounded timeout as DAY_PLAN_TIMEOUT_MS.
const BATCH_PLAN_TIMEOUT_MS = 60_000;

// POST /plan/week calls assemble_day_plan (the same enumeration
// DAY_PLAN_TIMEOUT_MS budgets for) once per requested day (up to 14) plus
// one consolidated shopping-list reconciliation -- a multi-day solve is
// slower than a single day, so this gets a longer budget.
const WEEK_PLAN_TIMEOUT_MS = 90_000;

// POST /library/discover's `discovery_node` can call an LLM (source_mode
// "llm"/"hybrid") or hit an external recipe source ("external"/"hybrid") --
// same generous budget as RECOMMEND_TIMEOUT_MS, and what
// `frontend/pages/1_Recipe_Library_Builder.py` already used (timeout=90).
const DISCOVER_TIMEOUT_MS = 90_000;

// POST /library/save runs `selected_candidate_validation_node` +
// `save_recipe_node` + `index_recipe_node` (an embedding upsert per saved
// candidate) -- not LLM-backed, but still I/O over however many candidates
// were selected, so it gets a bounded (if shorter) timeout rather than none.
const SAVE_LIBRARY_TIMEOUT_MS = 60_000;

// POST /library/reindex is a synchronous full-corpus re-embed (see
// `app.api.routes_library.reindex_recipe_library`'s docstring) -- the
// single most expensive request path in the app, and rate-limited to 2/hour
// (RATE_LIMIT_REINDEX_MAX in app/config.py) specifically because of that
// cost. Manually verified against the running app (W5 executor report):
// reindexing the ~3,884-document demo corpus took ~5 minutes end-to-end
// locally, so a RECOMMEND_TIMEOUT_MS-sized budget would abort a real,
// still-succeeding request. 10 minutes leaves headroom above that observed
// figure; the tight 2/hour rate limit is what actually bounds abuse here,
// not this client-side timeout.
const REINDEX_TIMEOUT_MS = 600_000;

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

// POST /recipes/instructions calls the same LLM provider chain as
// /recipes/recommend (see app.services.model_provider.
// generate_detailed_instructions_with_provider_chain) -- same generous
// budget as RECOMMEND_TIMEOUT_MS.
const DETAILED_INSTRUCTIONS_TIMEOUT_MS = 90_000;

/** Session-required: bootstraps a session and sends the CSRF header. Also
 * rate-limited server-side (shares RATE_LIMIT_RECOMMEND_MAX per
 * RATE_LIMIT_RECOMMEND_WINDOW_SECONDS with /recipes/recommend -- see
 * app/dependencies.py's require_recommend_rate_limit), so callers should
 * handle `RateLimitError` the same way `recommendRecipes` callers do. This
 * is a phrasing/elaboration call only: it never adds/removes/substitutes an
 * ingredient and never states a nutrition or allergy/diet safety claim (see
 * the backend prompt in app.services.model_provider for the guardrails). */
export async function getDetailedInstructions(
  request: DetailedInstructionsRequest,
): Promise<DetailedInstructionsResponse> {
  return apiRequest<DetailedInstructionsResponse>("/recipes/instructions", {
    method: "POST",
    json: request,
    sessionRequired: true,
    timeoutMs: DETAILED_INSTRUCTIONS_TIMEOUT_MS,
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
 * Public call: no session bootstrap, no CSRF header -- same convention as
 * `planDay`/`getShoppingList` (a pure by-id lookup, see
 * `app.api.routes_recommendations.get_recipe`'s docstring). Used by
 * `RecipeDetailModal` to resolve a `PlanItem.recipe_id` (day/week plan rows
 * only carry `{recipe_id, title, servings}`) back to the full `Recipe` for
 * display -- computes nothing and makes no safety decision.
 */
export async function getRecipe(recipeId: string): Promise<Recipe> {
  return apiRequest<Recipe>(`/recipes/${encodeURIComponent(recipeId)}`, {
    method: "GET",
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

/**
 * Public call: no session bootstrap, no CSRF header. Every candidate recipe
 * is safety-cleared server-side by `app.services.constraint_engine.
 * validate_recipe` before `app.services.batch_planner` ever sees it (see
 * `app.api.routes_day_planner.plan_batch`'s docstring) -- this wrapper makes
 * no safety decision of its own, it only calls the endpoint.
 */
export async function planBatch(request: BatchPlanRequest): Promise<BatchPlanResponse> {
  return apiRequest<BatchPlanResponse>("/plan/batch", {
    method: "POST",
    json: request,
    timeoutMs: BATCH_PLAN_TIMEOUT_MS,
  });
}

/**
 * Public call: no session bootstrap, no CSRF header. Every candidate recipe
 * is safety-cleared server-side by `app.services.constraint_engine.
 * validate_recipe` before `app.services.weekly_planner` ever sees it (see
 * `app.api.routes_day_planner.plan_week`'s docstring) -- this wrapper makes
 * no safety decision of its own, it only calls the endpoint.
 */
export async function planWeek(request: WeeklyPlanRequest): Promise<WeeklyPlanResponse> {
  return apiRequest<WeeklyPlanResponse>("/plan/week", {
    method: "POST",
    json: request,
    timeoutMs: WEEK_PLAN_TIMEOUT_MS,
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

/** Session-required: bootstraps a session and sends the CSRF header. Also
 * rate-limited server-side (`RATE_LIMIT_DISCOVER_MAX` per
 * `RATE_LIMIT_DISCOVER_WINDOW_SECONDS` -- see `app/dependencies.py`'s
 * `require_discover_rate_limit`), so callers should handle `RateLimitError`
 * the same way `recommendRecipes` callers do. */
export async function discoverRecipes(
  request: RecipeDiscoveryRequest,
): Promise<RecipeDiscoveryResponse> {
  return apiRequest<RecipeDiscoveryResponse>("/library/discover", {
    method: "POST",
    json: request,
    sessionRequired: true,
    timeoutMs: DISCOVER_TIMEOUT_MS,
  });
}

/** Session-required: bootstraps a session and sends the CSRF header. */
export async function saveRecipeCandidates(
  request: SaveRecipeCandidatesRequest,
): Promise<SaveRecipeCandidatesResponse> {
  return apiRequest<SaveRecipeCandidatesResponse>("/library/save", {
    method: "POST",
    json: request,
    sessionRequired: true,
    timeoutMs: SAVE_LIBRARY_TIMEOUT_MS,
  });
}

/** Session-required: bootstraps a session and sends the CSRF header. Also
 * rate-limited server-side to `RATE_LIMIT_REINDEX_MAX` (2) per
 * `RATE_LIMIT_REINDEX_WINDOW_SECONDS` (1 hour) -- the tightest limit of any
 * endpoint in this app (see `app/dependencies.py`'s
 * `require_reindex_rate_limit`), so callers must handle `RateLimitError`
 * with copy that makes the hourly cap explicit, not a generic retry hint. */
export async function reindexLibrary(): Promise<ReindexLibraryResponse> {
  return apiRequest<ReindexLibraryResponse>("/library/reindex", {
    method: "POST",
    sessionRequired: true,
    timeoutMs: REINDEX_TIMEOUT_MS,
  });
}

/** Session-required: bootstraps a session and sends the CSRF header. */
export async function getLibrary(): Promise<UserRecipeLibraryResponse> {
  return apiRequest<UserRecipeLibraryResponse>("/library", {
    method: "GET",
    sessionRequired: true,
  });
}

/** Session-required: bootstraps a session and sends the CSRF header. */
export async function deleteLibraryRecipe(recipeId: string): Promise<DeleteRecipeResponse> {
  return apiRequest<DeleteRecipeResponse>(`/library/${encodeURIComponent(recipeId)}`, {
    method: "DELETE",
    sessionRequired: true,
  });
}
