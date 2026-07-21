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

export type Recipe = components["schemas"]["Recipe"];
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

export type BatchPlan = components["schemas"]["BatchPlan"];
export type WeeklyPlan = components["schemas"]["WeeklyPlan"];

export type ShareCreateRequest = components["schemas"]["ShareCreateRequest"];
export type ShareCreateResponse = components["schemas"]["ShareCreateResponse"];
export type SharedPlanView = components["schemas"]["SharedPlanView"];

export type PublicRecipe = components["schemas"]["PublicRecipe"];
export type PublicDayPlan = components["schemas"]["PublicDayPlan"];
export type PublicBatchPlan = components["schemas"]["PublicBatchPlan"];
export type PublicWeeklyPlan = components["schemas"]["PublicWeeklyPlan"];

export type UserRecipeLibraryResponse = components["schemas"]["UserRecipeLibraryResponse"];

export type HTTPValidationError = components["schemas"]["HTTPValidationError"];
