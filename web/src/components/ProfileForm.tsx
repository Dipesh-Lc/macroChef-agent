import { useEffect, useState } from "react";
import type { UserProfile } from "../api/types";
import {
  DIET_TYPE_OPTIONS,
  MAX_COOK_TIME_OPTIONS,
  SERVINGS_OPTIONS,
  applyHighFiberPreset,
  applyHighProteinAndFiberPreset,
  applyHighProteinPreset,
  loadProfileFormValue,
  saveProfileFormValue,
  toUserProfile,
  type ProfileFormValue,
} from "../lib/profile";
import { TagInput } from "./TagInput";

/**
 * Self-contained profile editor: owns its own state (seeded from
 * localStorage -- non-secret UX convenience only, never anything
 * safety-relevant), persists every change back to localStorage, and
 * reports the derived `UserProfile` (the shape `POST /recipes/recommend`
 * actually accepts) to the parent via `onProfileChange` on every change,
 * including on mount.
 *
 * No `user_id` field anywhere in this component or the profile it
 * produces -- identity is the verified session (see api/client.ts), never
 * a client-supplied value.
 *
 * Allergy vocabulary note: this repo has no fixed allergen enum anywhere
 * (`app/schemas/user.py`'s `UserProfile.allergies` is a free-text
 * `list[str]`, and the Streamlit sidebar this ports -- `frontend/
 * components/profile_form.py` -- is a free-text tag input, not a
 * multi-select from a closed list). Ported as free-text tag chips
 * accordingly; see the executor report's ASSUMPTIONS section.
 */
export function ProfileForm({
  onProfileChange,
}: {
  onProfileChange: (profile: UserProfile) => void;
}) {
  // Lazy initializer (not an effect): localStorage is read synchronously
  // exactly once, during the first render, so there is never an initial
  // render with defaults immediately followed by a second render with the
  // persisted value.
  const [value, setValue] = useState<ProfileFormValue>(() => loadProfileFormValue());

  useEffect(() => {
    saveProfileFormValue(value);
    onProfileChange(toUserProfile(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onProfileChange is expected to be stable per render cycle of the parent; re-running on identity changes would re-fire on every parent render.
  }, [value]);

  function update<K extends keyof ProfileFormValue>(key: K, next: ProfileFormValue[K]) {
    setValue((current) => ({ ...current, [key]: next }));
  }

  return (
    <div className="flex flex-col gap-5 rounded-lg border border-sage-line bg-white p-4">
      <div>
        <h2 className="font-display text-base font-semibold text-cast-iron">Profile</h2>
        <p className="text-xs text-cast-iron/60">Saved on this device only.</p>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">
          Macro targets
        </span>
        <p className="text-xs text-cast-iron/50">
          Off by default -- switch a target on to have it count toward recipe scoring.
        </p>
        <div className="flex flex-col gap-1.5">
          <span className="text-xs text-cast-iron/50">Quick presets:</span>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setValue((current) => applyHighProteinPreset(current))}
              className="shrink-0 rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium hover:bg-sage-line/40"
            >
              High Protein
            </button>
            <button
              type="button"
              onClick={() => setValue((current) => applyHighFiberPreset(current))}
              className="shrink-0 rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium hover:bg-sage-line/40"
            >
              High Fibre
            </button>
            <button
              type="button"
              onClick={() => setValue((current) => applyHighProteinAndFiberPreset(current))}
              className="shrink-0 rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium hover:bg-sage-line/40"
            >
              High Protein and Fibre
            </button>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <NumberField
            label="Calories"
            value={value.calories}
            enabled={value.caloriesEnabled}
            onChange={(v) => update("calories", v)}
            onEnabledChange={(v) => update("caloriesEnabled", v)}
          />
          <NumberField
            label="Protein (g)"
            value={value.proteinG}
            enabled={value.proteinEnabled}
            onChange={(v) => update("proteinG", v)}
            onEnabledChange={(v) => update("proteinEnabled", v)}
          />
          <NumberField
            label="Carbs (g)"
            value={value.carbsG}
            enabled={value.carbsEnabled}
            onChange={(v) => update("carbsG", v)}
            onEnabledChange={(v) => update("carbsEnabled", v)}
          />
          <NumberField
            label="Fat (g)"
            value={value.fatG}
            enabled={value.fatEnabled}
            onChange={(v) => update("fatG", v)}
            onEnabledChange={(v) => update("fatEnabled", v)}
          />
          <NumberField
            label="Fiber (g)"
            value={value.fiberG}
            enabled={value.fiberEnabled}
            onChange={(v) => update("fiberG", v)}
            onEnabledChange={(v) => update("fiberEnabled", v)}
          />
        </div>
      </div>

      <TagInput
        label="Allergies"
        placeholder="e.g. peanuts"
        items={value.allergies}
        onChange={(items) => update("allergies", items)}
      />

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">Diet type</span>
        <select
          value={value.dietType}
          onChange={(event) => update("dietType", event.target.value as ProfileFormValue["dietType"])}
          className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
        >
          {DIET_TYPE_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">
          Max cook time
        </span>
        <select
          value={value.maxCookTimeMin ?? ""}
          onChange={(event) =>
            update("maxCookTimeMin", event.target.value === "" ? null : Number(event.target.value))
          }
          className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
        >
          {MAX_COOK_TIME_OPTIONS.map((option) => (
            <option key={option.label} value={option.minutes ?? ""}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <TagInput
        label="Disliked ingredients"
        placeholder="e.g. cilantro"
        items={value.dislikedIngredients}
        onChange={(items) => update("dislikedIngredients", items)}
      />

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">Servings</span>
        <select
          value={value.servings}
          onChange={(event) => update("servings", Number(event.target.value))}
          className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
        >
          {SERVINGS_OPTIONS.map((option) => (
            <option key={option.label} value={option.servings}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

function NumberField({
  label,
  value,
  enabled,
  onChange,
  onEnabledChange,
}: {
  label: string;
  value: number;
  enabled: boolean;
  onChange: (value: number) => void;
  onEnabledChange: (enabled: boolean) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-xs text-cast-iron/60">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => onEnabledChange(event.target.checked)}
          aria-label={`Enable ${label} target`}
        />
        <span>{label}</span>
      </div>
      <label className="flex flex-col gap-1">
        <span className="sr-only">{label}</span>
        <input
          type="number"
          min={0}
          value={value}
          disabled={!enabled}
          onChange={(event) => onChange(Number(event.target.value))}
          className="rounded-md border border-sage-line bg-white px-2 py-1.5 font-mono text-sm text-cast-iron focus:border-basil disabled:opacity-40"
        />
      </label>
    </div>
  );
}
