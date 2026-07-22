/**
 * Distinct card region for `Recipe.substitution_note` -- a fully-formed,
 * deterministic template string built by
 * `app.services.substitution_service._build_note` (e.g. "Swapped peanuts ->
 * almonds (nut-free). macro impact: +12 kcal, ...").
 *
 * Rendered VERBATIM: this component never rewrites, summarizes, or
 * re-derives the copy -- it only gives it a distinct basil-accented visual
 * treatment so a substitution is impossible to miss. No LLM involvement,
 * matching the deterministic-substitution-engine discipline documented in
 * `app/services/substitution_service.py`.
 */
export function SubstitutionNoteCard({ note }: { note: string }) {
  return (
    <div className="rounded-md border-l-4 border-basil bg-basil/5 px-3 py-2 text-sm text-cast-iron">
      <p className="text-xs font-medium uppercase tracking-wide text-basil">Substitution</p>
      <p className="mt-1">{note}</p>
    </div>
  );
}
