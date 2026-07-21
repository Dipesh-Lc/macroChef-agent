/**
 * Endpoint-specific wrappers over `apiRequest` (see `./client.ts`). Kept
 * separate from the transport module so each call site only needs to know
 * its own request/response shape, not the retry/session-bootstrap plumbing.
 */
import { apiRequest } from "./client";
import type {
  FeedbackRequest,
  InventoryObservation,
  RecommendationRequest,
  RecommendationResponse,
} from "./types";

// POST /recipes/recommend can take 30-90s (LLM parsing + corpus scoring +
// USDA grounding lookups) -- see HomePage's staged loading copy.
const RECOMMEND_TIMEOUT_MS = 90_000;

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
