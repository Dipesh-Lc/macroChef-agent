/**
 * Ergonomic re-exports of the schemas we actually use from the generated
 * `types.gen.ts` (produced by `openapi-typescript` from the FastAPI app's
 * own OpenAPI schema -- see `scripts/export_openapi.py`). Import from here,
 * not from `types.gen.ts` directly, so a regeneration that renames an
 * internal `operations["..."]` key doesn't ripple through every component.
 */
import type { components } from "./types.gen";

export type UserProfile = components["schemas"]["UserProfile"];
export type MacroTargets = components["schemas"]["MacroTargets"];

export type Ingredient = components["schemas"]["Ingredient"];
export type ConfirmedIngredient = components["schemas"]["ConfirmedIngredient"];
export type InventoryObservation = components["schemas"]["InventoryObservation"];

// `Recipe` has a `derived_allergens` computed field (display-only, see
// `app.schemas.recipe.Recipe.derived_allergens`), which openapi-typescript
// splits into a request-shaped "Recipe-Input" (no computed field) and a
// response-shaped "Recipe-Output" (includes it). Every frontend use of
// `Recipe` is a value the app *received* from the backend (even when it's
// later forwarded verbatim into a request body, e.g. `ShareButton`'s
// `ShareCreateRequest.recipe`), so the response shape is the correct one --
// TypeScript's structural typing still allows passing it wherever the
// narrower "Recipe-Input" is expected.
export type Recipe = components["schemas"]["Recipe-Output"];
export type RecipeScore = components["schemas"]["RecipeScore"];
export type MealRecommendation = components["schemas"]["MealRecommendation"];
export type RejectedRecipe = components["schemas"]["RejectedRecipe"];
export type ShoppingItem = components["schemas"]["ShoppingItem"];

export type GroundingStatus = components["schemas"]["GroundingStatus"];
export type FoodMacros = components["schemas"]["FoodMacros"];
export type IngredientContribution = components["schemas"]["IngredientContribution"];
export type RecipeNutrition = components["schemas"]["RecipeNutrition"];

export type RecommendationRequest = components["schemas"]["RecommendationRequest"];
export type RecommendationResponse = components["schemas"]["RecommendationResponse"];

export type DetailedInstructionsRequest = components["schemas"]["DetailedInstructionsRequest"];
export type DetailedInstructionsResponse = components["schemas"]["DetailedInstructionsResponse"];

export type FeedbackRequest = components["schemas"]["FeedbackRequest"];

export type TasteProfile = components["schemas"]["TasteProfile"];
export type WasteNudge = components["schemas"]["WasteNudge"];
export type SuggestedRecipe = components["schemas"]["SuggestedRecipe"];

export type DayPlan = components["schemas"]["DayPlan"];
export type PlanItem = components["schemas"]["PlanItem"];
export type DayPlanRequest = components["schemas"]["DayPlanRequest"];
export type DayPlanResponse = components["schemas"]["DayPlanResponse"];

export type ShoppingListRequest = components["schemas"]["ShoppingListRequest"];
export type ShoppingListResponse = components["schemas"]["ShoppingListResponse"];
export type ShoppingListForItemsRequest = components["schemas"]["ShoppingListForItemsRequest"];

export type RecipeSearchRequest = components["schemas"]["RecipeSearchRequest"];
export type RecipeSearchResponse = components["schemas"]["RecipeSearchResponse"];

export type BatchPlan = components["schemas"]["BatchPlan"];
export type RecipeFit = components["schemas"]["RecipeFit"];
export type BatchPlanRequest = components["schemas"]["BatchPlanRequest"];
export type BatchPlanResponse = components["schemas"]["BatchPlanResponse"];

export type WeeklyPlan = components["schemas"]["WeeklyPlan"];
export type WeeklyPlanRequest = components["schemas"]["WeeklyPlanRequest"];
export type WeeklyPlanResponse = components["schemas"]["WeeklyPlanResponse"];

export type ShareCreateRequest = components["schemas"]["ShareCreateRequest"];
export type ShareCreateResponse = components["schemas"]["ShareCreateResponse"];
export type SharedPlanView = components["schemas"]["SharedPlanView"];

export type PublicRecipe = components["schemas"]["PublicRecipe"];
export type PublicDayPlan = components["schemas"]["PublicDayPlan"];
export type PublicBatchPlan = components["schemas"]["PublicBatchPlan"];
export type PublicWeeklyPlan = components["schemas"]["PublicWeeklyPlan"];
// `PublicShoppingList` has no dedicated `components["schemas"]` entry --
// `app.schemas.share.PublicShoppingList` is a bare `list[ShoppingItem]` type
// alias (not a Pydantic `BaseModel`), so FastAPI/openapi-typescript inline
// it as `ShoppingItem[]` wherever it's used (see `SharedPlanView.content`
// in `types.gen.ts`) rather than emitting a named schema component. Declared
// here anyway so call sites can import `PublicShoppingList` the same way
// they import the other three `Public*` plan types.
export type PublicShoppingList = ShoppingItem[];

export type UserRecipeLibraryResponse = components["schemas"]["UserRecipeLibraryResponse"];

// Same "-Input"/"-Output" split as `Recipe` above (`RecipeCandidate` also
// gained a `derived_allergens` computed field); candidates are always
// received from `/discover` first, so the response shape is correct even
// where a candidate is later forwarded into `SaveRecipeCandidatesRequest`
// (request-shaped "-Input").
export type RecipeCandidate = components["schemas"]["RecipeCandidate-Output"];
export type RecipeDiscoveryRequest = components["schemas"]["RecipeDiscoveryRequest"];
export type RecipeDiscoveryResponse = components["schemas"]["RecipeDiscoveryResponse"];
export type SaveRecipeCandidatesRequest = components["schemas"]["SaveRecipeCandidatesRequest"];
export type SaveRecipeCandidatesResponse = components["schemas"]["SaveRecipeCandidatesResponse"];
export type ReindexLibraryResponse = components["schemas"]["ReindexLibraryResponse"];
export type DeleteRecipeResponse = components["schemas"]["DeleteRecipeResponse"];

export type HTTPValidationError = components["schemas"]["HTTPValidationError"];

// ROADMAP 4.6: `GET /evals/latest` (`app.api.routes_evals`) response types.
export type EvalReport = components["schemas"]["EvalReport"];
export type SafetyBenchmarkSuite = components["schemas"]["SafetyBenchmarkSuite"];
export type SafetyBenchmarkBucket = components["schemas"]["SafetyBenchmarkBucket"];
export type SafetyBenchmarkCategoryBreakdown =
  components["schemas"]["SafetyBenchmarkCategoryBreakdown"];
export type RetrievalSuite = components["schemas"]["RetrievalSuite"];
export type RetrievalCategoryResult = components["schemas"]["RetrievalCategoryResult"];
export type ConstraintSuite = components["schemas"]["ConstraintSuite"];
export type ConstraintProfileResult = components["schemas"]["ConstraintProfileResult"];

// `EvalReportNotAvailable` (`app.schemas.evals.EvalReportNotAvailable`) has
// no `components["schemas"]` entry -- `GET /evals/latest` returns it via a
// hand-built `JSONResponse` rather than FastAPI's `response_model=` path
// (see `app.api.routes_evals`'s docstring for why: the file-missing case is
// an ordinary 200, not a schema the OpenAPI response documents), so
// openapi-typescript never sees it. Hand-declared here to mirror the real
// Pydantic model's field defaults exactly; `getLatestEvalReport`
// (`api/endpoints.ts`) discriminates on the `status` field at runtime.
export interface EvalReportNotAvailable {
  status: "not_generated";
  message: string;
}

// ROADMAP 4.3: the Chef chat agent's HTTP surface (`app.api.routes_chat`,
// ROADMAP Phase 3.3). `POST /chat/{thread_id}/message` itself returns SSE,
// not JSON -- its event payloads (`ChatToolCallEvent`/etc.) live in
// `lib/sse.ts` instead, mirroring `RecommendationRequest`/`NodeRunEvent`'s
// same JSON-schema-vs-SSE-event split above.
export type ChatCreateRequest = components["schemas"]["ChatCreateRequest"];
export type ChatCreateResponse = components["schemas"]["ChatCreateResponse"];
export type ChatMessageRequest = components["schemas"]["ChatMessageRequest"];
export type ChatMessageView = components["schemas"]["ChatMessageView"];
export type ChatThreadStatusResponse = components["schemas"]["ChatThreadStatusResponse"];
