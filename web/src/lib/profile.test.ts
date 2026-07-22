import { describe, expect, it } from "vitest";
import { DEFAULT_PROFILE_FORM_VALUE, toUserProfile, type ProfileFormValue } from "./profile";

// Macro targets are OFF by default (see DEFAULT_PROFILE_FORM_VALUE) -- a
// disabled macro must never leak its numeric value onto the wire, even if
// a nonzero number is sitting in the (disabled) input.

describe("toUserProfile macro target enabled flags", () => {
  it("emits null for every macro when all *Enabled flags are false", () => {
    const profile = toUserProfile(DEFAULT_PROFILE_FORM_VALUE);
    expect(profile.macro_targets).toEqual({
      calories: null,
      protein_g: null,
      carbs_g: null,
      fat_g: null,
      fiber_g: null,
    });
  });

  it("still emits null for a disabled macro even when its number field holds a nonzero value", () => {
    const value: ProfileFormValue = {
      ...DEFAULT_PROFILE_FORM_VALUE,
      calories: 2500,
      caloriesEnabled: false,
    };
    expect(toUserProfile(value).macro_targets?.calories).toBeNull();
  });

  it("emits the numeric value only for macros whose enabled flag is true", () => {
    const value: ProfileFormValue = {
      ...DEFAULT_PROFILE_FORM_VALUE,
      calories: 2200,
      caloriesEnabled: true,
      proteinG: 180,
      proteinEnabled: true,
      carbsG: 210,
      carbsEnabled: false,
      fatG: 70,
      fatEnabled: false,
      fiberG: 30,
      fiberEnabled: false,
    };
    expect(toUserProfile(value).macro_targets).toEqual({
      calories: 2200,
      protein_g: 180,
      carbs_g: null,
      fat_g: null,
      fiber_g: null,
    });
  });

  it("emits every macro's number when all flags are enabled", () => {
    const value: ProfileFormValue = {
      ...DEFAULT_PROFILE_FORM_VALUE,
      caloriesEnabled: true,
      proteinEnabled: true,
      carbsEnabled: true,
      fatEnabled: true,
      fiberEnabled: true,
    };
    expect(toUserProfile(value).macro_targets).toEqual({
      calories: DEFAULT_PROFILE_FORM_VALUE.calories,
      protein_g: DEFAULT_PROFILE_FORM_VALUE.proteinG,
      carbs_g: DEFAULT_PROFILE_FORM_VALUE.carbsG,
      fat_g: DEFAULT_PROFILE_FORM_VALUE.fatG,
      fiber_g: DEFAULT_PROFILE_FORM_VALUE.fiberG,
    });
  });
});
