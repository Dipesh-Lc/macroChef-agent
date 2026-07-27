import { useState } from "react";
import type { RecipeCandidate } from "../api/types";
import { ingredientDisplay } from "../lib/scaling";
import { preselectedCandidateIds } from "../lib/libraryCandidates";
import { RecipeArt } from "./RecipeArt";

/**
 * Port of `frontend/components/recipe_candidate_cards.py`'s
 * `render_recipe_candidate_cards`: one card per discovered candidate, a
 * per-card checkbox with the first 3 pre-checked (see
 * `lib/libraryCandidates.preselectedCandidateIds`), and a "Save selected"
 * action the parent wires to `saveRecipeCandidates`. Every candidate here is
 * an LLM/external-source SUGGESTION, not yet a corpus `Recipe` -- this
 * component only displays and lets the user choose which to persist; saving
 * (and the allergy/diet validation that runs on `/library/save`) is the
 * deterministic backend's job, never this component's.
 */

function macroLine(candidate: RecipeCandidate): string {
  const calories = candidate.calories ?? 0;
  const protein = candidate.protein_g ?? 0;
  const carbs = candidate.carbs_g ?? 0;
  const fat = candidate.fat_g ?? 0;
  return `${Math.round(calories)} calories | ${Math.round(protein)}g protein | ${Math.round(carbs)}g carbs | ${Math.round(fat)}g fat`;
}

function metaLine(candidate: RecipeCandidate): string {
  return [
    candidate.cuisine ?? "Any cuisine",
    candidate.meal_type ?? "meal",
    candidate.cook_time_min ? `${candidate.cook_time_min} min` : "time unknown",
    candidate.difficulty ?? "difficulty n/a",
    candidate.source_type,
  ].join(" · ");
}

function CandidateCard({
  candidate,
  checked,
  onToggle,
}: {
  candidate: RecipeCandidate;
  checked: boolean;
  onToggle: () => void;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const [instructionsOpen, setInstructionsOpen] = useState(false);
  // Real image (LLM/source-provided or, once ROADMAP 4.4's [STRETCH] item
  // lands, a generated one) takes priority; if neither is present, or the
  // real one fails to load, fall back to zero-network local art rather
  // than the old `placehold.co` remote call.
  const realImageUrl = candidate.image_url ?? candidate.image_path;

  return (
    <article className="overflow-hidden rounded-lg border border-sage-line bg-white shadow-sm">
      <div className="grid gap-4 p-4 sm:grid-cols-[24px_160px_1fr]">
        <div className="flex items-start justify-center pt-1">
          <input
            type="checkbox"
            checked={checked}
            onChange={onToggle}
            aria-label={`Save ${candidate.title}`}
          />
        </div>

        {realImageUrl && !imageFailed ? (
          <img
            src={realImageUrl}
            alt={candidate.title}
            onError={() => setImageFailed(true)}
            className="h-[120px] w-full rounded-md object-cover sm:h-full"
          />
        ) : (
          <RecipeArt recipe={candidate} className="h-[120px] w-full sm:h-full" />
        )}

        <div className="flex flex-col gap-2">
          <h3 className="font-display text-lg font-semibold text-cast-iron">{candidate.title}</h3>
          <p className="text-sm text-cast-iron/70">{metaLine(candidate)}</p>
          <p className="text-sm text-cast-iron/80">
            {candidate.description ?? "No description provided."}
          </p>
          <p className="font-mono text-sm text-cast-iron">{macroLine(candidate)}</p>

          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/50">
              Ingredients
            </span>
            <p className="text-sm text-cast-iron">
              {(candidate.ingredients ?? []).map((ingredient) => ingredientDisplay(ingredient)).join(", ") ||
                "No ingredients listed."}
            </p>
          </div>

          {candidate.diet_tags && candidate.diet_tags.length > 0 && (
            <p className="text-sm text-cast-iron/80">
              <span className="font-medium">Diet tags:</span> {candidate.diet_tags.join(", ")}
            </p>
          )}

          {candidate.derived_allergens && candidate.derived_allergens.length > 0 && (
            <p className="text-sm text-cast-iron/80">
              {/* Ingredient-derived, display-only (never the safety-relevant
                  self-reported `allergens` field) -- see
                  `app.schemas.recipe_candidate.RecipeCandidate.derived_allergens`. */}
              <span className="font-medium">Allergens:</span> {candidate.derived_allergens.join(", ")}
            </p>
          )}

          {candidate.validation_warnings && candidate.validation_warnings.length > 0 && (
            <div className="rounded-md border border-honey-dark bg-honey/10 px-3 py-2 text-sm text-honey-dark">
              {candidate.validation_warnings.join(" | ")}
            </div>
          )}

          {candidate.instructions && candidate.instructions.length > 0 && (
            <div>
              <button
                type="button"
                onClick={() => setInstructionsOpen((value) => !value)}
                className="text-xs font-medium uppercase tracking-wide text-cast-iron/60 underline underline-offset-2"
              >
                {instructionsOpen ? "Hide instructions" : "Show instructions"}
              </button>
              {instructionsOpen && (
                <ol className="mt-2 flex list-inside list-decimal flex-col gap-1 text-sm text-cast-iron">
                  {candidate.instructions.map((step, index) => (
                    <li key={index}>{step}</li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

export function RecipeCandidateCards({
  candidates,
  onSave,
  isSaving,
}: {
  candidates: RecipeCandidate[];
  onSave: (selected: RecipeCandidate[]) => void;
  isSaving: boolean;
}) {
  const [checkedIds, setCheckedIds] = useState<Set<string>>(() => preselectedCandidateIds(candidates));
  // Tracks which `candidates` array this component's `checkedIds` was
  // derived from -- see the render-time reset below.
  const [candidatesForCheckedIds, setCandidatesForCheckedIds] = useState(candidates);

  // Re-derive the pre-check set whenever a new discovery response replaces
  // the candidate list -- a stale `checkedIds` from a previous discovery
  // call must never silently carry over onto a different candidate set.
  // Done during render (React's documented "adjusting state when a prop
  // changes" pattern), not inside a `useEffect`, so there is no extra
  // render pass between the candidate swap and the correct pre-check state.
  if (candidates !== candidatesForCheckedIds) {
    setCandidatesForCheckedIds(candidates);
    setCheckedIds(preselectedCandidateIds(candidates));
  }

  if (candidates.length === 0) {
    return null;
  }

  function toggle(candidateId: string) {
    setCheckedIds((current) => {
      const next = new Set(current);
      if (next.has(candidateId)) {
        next.delete(candidateId);
      } else {
        next.add(candidateId);
      }
      return next;
    });
  }

  const selected = candidates.filter((candidate) => checkedIds.has(candidate.candidate_id));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display text-base font-semibold text-cast-iron">Candidate recipes</h2>
        <button
          type="button"
          onClick={() => onSave(selected)}
          disabled={selected.length === 0 || isSaving}
          className="rounded-md bg-basil px-3 py-2 text-sm font-medium text-porcelain disabled:opacity-50"
        >
          {isSaving ? "Saving…" : `Save selected (${selected.length})`}
        </button>
      </div>

      <div className="flex flex-col gap-4">
        {candidates.map((candidate) => (
          <CandidateCard
            key={candidate.candidate_id}
            candidate={candidate}
            checked={checkedIds.has(candidate.candidate_id)}
            onToggle={() => toggle(candidate.candidate_id)}
          />
        ))}
      </div>
    </div>
  );
}
