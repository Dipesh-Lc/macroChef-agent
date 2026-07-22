import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DiscoverForm } from "../components/DiscoverForm";
import { RecipeCandidateCards } from "../components/RecipeCandidateCards";
import { SavedRecipeLibrary } from "../components/SavedRecipeLibrary";
import { ApiError, RateLimitError } from "../api/client";
import {
  deleteLibraryRecipe,
  discoverRecipes,
  getLibrary,
  reindexLibrary,
  saveRecipeCandidates,
} from "../api/endpoints";
import type {
  Recipe,
  RecipeCandidate,
  RecipeDiscoveryRequest,
  UserRecipeLibraryResponse,
} from "../api/types";
import { summarizeSaveOutcome } from "../lib/libraryCandidates";

const LIBRARY_QUERY_KEY = ["library"] as const;

// Same staged-loading precedent as HomePage/WeekPlanPage -- discovery can be
// LLM- or external-source-backed (see `DISCOVER_TIMEOUT_MS` in
// api/endpoints.ts) and is worth narrating for a slow request.
const SLOW_STATUS_AFTER_MS = 10_000;
const VERY_SLOW_STATUS_AFTER_MS = 40_000;

function useElapsedMs(active: boolean): number {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!active) {
      return;
    }
    const startedAt = Date.now();
    const interval = setInterval(() => setElapsed(Date.now() - startedAt), 1000);
    return () => clearInterval(interval);
  }, [active]);

  return active ? elapsed : 0;
}

function DiscoverLoadingStatus({ elapsedMs }: { elapsedMs: number }) {
  let message = "Discovering recipes…";
  if (elapsedMs >= VERY_SLOW_STATUS_AFTER_MS) {
    message = "Still working — this source can take a while…";
  } else if (elapsedMs >= SLOW_STATUS_AFTER_MS) {
    message = "Generating and validating candidates…";
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-cast-iron/70">{message}</p>
      <div className="flex flex-col gap-3">
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            className="h-28 animate-pulse rounded-lg border border-dashed border-sage-line bg-white"
          />
        ))}
      </div>
    </div>
  );
}

function friendlyErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof RateLimitError) {
    return error.message;
  }
  if (error instanceof ApiError) {
    return error.message;
  }
  return fallback;
}

export default function MyRecipesPage() {
  const queryClient = useQueryClient();
  const [rateLimitToast, setRateLimitToast] = useState<string | null>(null);
  const [saveNotice, setSaveNotice] = useState<{
    savedCount: number;
    skippedDuplicateCount: number;
    failedCount: number;
  } | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletingRecipeId, setDeletingRecipeId] = useState<string | null>(null);

  const libraryQuery = useQuery({
    queryKey: LIBRARY_QUERY_KEY,
    queryFn: getLibrary,
  });

  const discoverMutation = useMutation({
    mutationFn: (request: RecipeDiscoveryRequest) => discoverRecipes(request),
    onSuccess: () => setSaveNotice(null),
    onError: (error) => {
      if (error instanceof RateLimitError) {
        setRateLimitToast(error.message);
      }
    },
  });

  const saveMutation = useMutation({
    mutationFn: (selected: RecipeCandidate[]) =>
      saveRecipeCandidates({ selected_candidates: selected }),
    onSuccess: (response) => {
      setSaveNotice(summarizeSaveOutcome(response));
      queryClient.invalidateQueries({ queryKey: LIBRARY_QUERY_KEY });
    },
    onError: (error) => {
      if (error instanceof RateLimitError) {
        setRateLimitToast(error.message);
      }
    },
  });

  const reindexMutation = useMutation({
    mutationFn: reindexLibrary,
    onError: (error) => {
      if (error instanceof RateLimitError) {
        setRateLimitToast(error.message);
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (recipeId: string) => deleteLibraryRecipe(recipeId),
    onMutate: async (recipeId: string) => {
      setDeleteError(null);
      setDeletingRecipeId(recipeId);
      await queryClient.cancelQueries({ queryKey: LIBRARY_QUERY_KEY });
      const previous = queryClient.getQueryData<UserRecipeLibraryResponse>(LIBRARY_QUERY_KEY);
      if (previous) {
        queryClient.setQueryData<UserRecipeLibraryResponse>(LIBRARY_QUERY_KEY, {
          recipes: (previous.recipes ?? []).filter(
            (recipe: Recipe) => recipe.recipe_id !== recipeId,
          ),
        });
      }
      return { previous };
    },
    onError: (error, _recipeId, context) => {
      if (context?.previous) {
        queryClient.setQueryData(LIBRARY_QUERY_KEY, context.previous);
      }
      setDeleteError(friendlyErrorMessage(error, "Could not delete recipe. Please try again."));
    },
    onSettled: () => {
      setDeletingRecipeId(null);
      queryClient.invalidateQueries({ queryKey: LIBRARY_QUERY_KEY });
    },
  });

  const elapsedMs = useElapsedMs(discoverMutation.isPending);

  useEffect(() => {
    if (!rateLimitToast) {
      return;
    }
    const timeout = setTimeout(() => setRateLimitToast(null), 6000);
    return () => clearTimeout(timeout);
  }, [rateLimitToast]);

  const discoverFailure = discoverMutation.error;
  const discoverResult = discoverMutation.data;
  const reindexFailure = reindexMutation.error;
  const reindexResult = reindexMutation.data;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2 rounded-lg border border-sage-line bg-white p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="font-display text-lg font-semibold text-cast-iron">Recipe library</h1>
            <p className="text-xs text-cast-iron/60">
              Discover home-cookable recipe candidates, review them, and save the useful ones.
            </p>
          </div>
          <button
            type="button"
            onClick={() => reindexMutation.mutate()}
            disabled={reindexMutation.isPending}
            className="shrink-0 rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium text-cast-iron hover:bg-sage-line/40 disabled:opacity-50"
            title="Rebuilds the recipe search index. Can take several minutes. Limited to 2 requests per hour."
          >
            {reindexMutation.isPending ? "Reindexing…" : "Reindex library"}
          </button>
        </div>

        {reindexMutation.isPending && (
          <p className="text-sm text-cast-iron/60">
            Rebuilding the full recipe search index — this can take several minutes.
          </p>
        )}

        {reindexFailure && !(reindexFailure instanceof RateLimitError) && (
          <div className="rounded-md border border-chili bg-chili/5 px-3 py-2 text-sm text-chili">
            {friendlyErrorMessage(reindexFailure, "Could not reindex the library. Please try again.")}
          </div>
        )}
        {reindexFailure instanceof RateLimitError && (
          <div className="rounded-md border border-honey-dark bg-honey/15 px-3 py-2 text-sm text-honey-dark">
            Reindexing is limited to 2 requests per hour — {reindexFailure.message}
          </div>
        )}
        {reindexResult && !reindexMutation.isPending && (
          <p className="text-sm text-basil">
            Reindexed {reindexResult.indexed_count} recipe(s) — status: {reindexResult.status}.
          </p>
        )}
      </div>

      {rateLimitToast && (
        <div className="rounded-md border border-honey-dark bg-honey/15 px-3 py-2 text-sm text-honey-dark">
          {rateLimitToast}
        </div>
      )}

      <DiscoverForm
        onDiscover={(request) => discoverMutation.mutate(request)}
        isPending={discoverMutation.isPending}
      />

      {discoverFailure && !(discoverFailure instanceof RateLimitError) && (
        <div className="rounded-md border border-chili bg-chili/5 px-3 py-2 text-sm text-chili">
          {friendlyErrorMessage(discoverFailure, "Could not discover recipes. Please try again.")}
        </div>
      )}

      {discoverMutation.isPending && <DiscoverLoadingStatus elapsedMs={elapsedMs} />}

      {!discoverMutation.isPending && discoverResult && (
        <div className="flex flex-col gap-3">
          {discoverResult.errors && discoverResult.errors.length > 0 && (
            <div className="rounded-md border border-chili bg-chili/5 px-3 py-2 text-sm text-chili">
              <ul className="list-inside list-disc">
                {discoverResult.errors.map((message, index) => (
                  <li key={index}>{message}</li>
                ))}
              </ul>
            </div>
          )}

          {discoverResult.warnings && discoverResult.warnings.length > 0 && (
            <div className="rounded-md border border-honey-dark bg-honey/10 px-3 py-2 text-sm text-honey-dark">
              <ul className="list-inside list-disc">
                {discoverResult.warnings.map((message, index) => (
                  <li key={index}>{message}</li>
                ))}
              </ul>
            </div>
          )}

          {(discoverResult.candidates ?? []).length === 0 ? (
            <p className="text-sm text-cast-iron/70">
              No candidates found. Try loosening a filter or a different source mode.
            </p>
          ) : (
            <RecipeCandidateCards
              candidates={discoverResult.candidates ?? []}
              onSave={(selected) => saveMutation.mutate(selected)}
              isSaving={saveMutation.isPending}
            />
          )}
        </div>
      )}

      {saveMutation.isError && !(saveMutation.error instanceof RateLimitError) && (
        <div className="rounded-md border border-chili bg-chili/5 px-3 py-2 text-sm text-chili">
          {friendlyErrorMessage(saveMutation.error, "Could not save recipes. Please try again.")}
        </div>
      )}

      {saveNotice && (
        <div className="flex flex-col gap-1 rounded-md border border-sage-line bg-white px-3 py-2 text-sm">
          {saveNotice.savedCount > 0 && (
            <p className="text-basil">Saved {saveNotice.savedCount} recipe(s).</p>
          )}
          {saveNotice.skippedDuplicateCount > 0 && (
            <p className="text-honey-dark">
              Skipped {saveNotice.skippedDuplicateCount} duplicate(s) already in your library.
            </p>
          )}
          {saveNotice.failedCount > 0 && (
            <p className="text-chili">
              {saveNotice.failedCount} candidate(s) failed validation and were not saved.
            </p>
          )}
          {saveNotice.savedCount === 0 &&
            saveNotice.skippedDuplicateCount === 0 &&
            saveNotice.failedCount === 0 && <p className="text-cast-iron/70">Nothing was saved.</p>}
        </div>
      )}

      <SavedRecipeLibrary
        recipes={libraryQuery.data?.recipes ?? []}
        isLoading={libraryQuery.isFetching}
        loadError={
          libraryQuery.isError
            ? friendlyErrorMessage(libraryQuery.error, "Could not load recipe library.")
            : null
        }
        onRefresh={() => libraryQuery.refetch()}
        onDelete={(recipeId) => deleteMutation.mutate(recipeId)}
        deletingRecipeId={deletingRecipeId}
        deleteError={deleteError}
      />
    </div>
  );
}
