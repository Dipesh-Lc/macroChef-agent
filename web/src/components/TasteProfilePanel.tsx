import type { TasteProfile } from "../api/types";

/**
 * Trivial list render of the derived taste-profile signal (Phase 3:
 * visible personalization loop) -- port of `frontend/components/
 * taste_profile.py`'s copy/logic. Built ONLY from
 * `TasteProfile.avoided_ingredients`/`preferred_cuisines`
 * (`app.services.memory_service.derive_taste_profile`); no LLM-authored
 * copy, same "deterministic code decides, LLM never does" discipline that
 * governs allergy/nutrition decisions elsewhere. `derive_taste_profile`
 * enforces a minimum-sample-size floor before either list is populated, so
 * an empty/missing profile here always means "not enough feedback yet",
 * never a profile fabricated from one data point.
 */
export function TasteProfilePanel({ tasteProfile }: { tasteProfile: TasteProfile | null | undefined }) {
  const preferred = tasteProfile?.preferred_cuisines ?? [];
  const avoided = tasteProfile?.avoided_ingredients ?? [];
  if (preferred.length === 0 && avoided.length === 0) {
    return null;
  }

  return (
    <section className="rounded-lg border border-sage-line bg-white p-4">
      <h2 className="font-display text-base font-semibold text-cast-iron">
        What we've learned from your feedback
      </h2>
      {preferred.length > 0 && (
        <div className="mt-2">
          <p className="text-xs font-medium uppercase tracking-wide text-cast-iron/50">
            Drifting toward these cuisines, based on what you've liked
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {preferred.map((cuisine) => (
              <span key={cuisine} className="rounded-full border border-basil px-2 py-0.5 text-xs text-basil">
                {cuisine}
              </span>
            ))}
          </div>
        </div>
      )}
      {avoided.length > 0 && (
        <div className="mt-2">
          <p className="text-xs font-medium uppercase tracking-wide text-cast-iron/50">
            Auto-avoided ingredients, based on what you've disliked
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {avoided.map((ingredient) => (
              <span
                key={ingredient}
                className="rounded-full border border-dashed border-sage-line px-2 py-0.5 text-xs text-cast-iron/60"
              >
                {ingredient}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
