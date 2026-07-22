import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProfileForm } from "./ProfileForm";

// Backfills coverage for the "per-macro on/off toggle, all OFF by default"
// change to `lib/profile.ts` / `ProfileForm.tsx`: every macro starts
// disabled, its NumberField input starts disabled too, and toggling the
// checkbox both enables the input and starts sending its number on the
// wire (via the `onProfileChange` callback).

beforeEach(() => {
  window.localStorage.clear();
});

describe("ProfileForm macro toggles", () => {
  it("starts every macro target disabled, greys out its input, and sends null for all of them", () => {
    const onProfileChange = vi.fn();
    render(<ProfileForm onProfileChange={onProfileChange} />);

    for (const label of ["Enable Calories target", "Enable Protein (g) target", "Enable Carbs (g) target", "Enable Fat (g) target", "Enable Fiber (g) target"]) {
      expect(screen.getByLabelText(label)).not.toBeChecked();
    }

    expect(screen.getByLabelText("Calories")).toBeDisabled();
    expect(screen.getByLabelText("Protein (g)")).toBeDisabled();
    expect(screen.getByLabelText("Carbs (g)")).toBeDisabled();
    expect(screen.getByLabelText("Fat (g)")).toBeDisabled();
    expect(screen.getByLabelText("Fiber (g)")).toBeDisabled();

    const lastCall = onProfileChange.mock.calls.at(-1)?.[0];
    expect(lastCall.macro_targets).toEqual({
      calories: null,
      protein_g: null,
      carbs_g: null,
      fat_g: null,
      fiber_g: null,
    });
  });

  it("enables the NumberField and sends its number once the checkbox is checked", () => {
    const onProfileChange = vi.fn();
    render(<ProfileForm onProfileChange={onProfileChange} />);

    fireEvent.click(screen.getByLabelText("Enable Calories target"));

    expect(screen.getByLabelText("Calories")).not.toBeDisabled();
    const lastCall = onProfileChange.mock.calls.at(-1)?.[0];
    expect(lastCall.macro_targets.calories).toBe(2000);
    expect(lastCall.macro_targets.protein_g).toBeNull();
  });
});
