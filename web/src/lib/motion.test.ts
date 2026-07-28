import { afterEach, describe, expect, it, vi } from "vitest";
import { MICRO_INTERACTION_MS, prefersReducedMotion } from "./motion";

describe("prefersReducedMotion", () => {
  const originalMatchMedia = window.matchMedia;

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it("returns false when window.matchMedia is unavailable (jsdom's default)", () => {
    // @ts-expect-error -- simulating jsdom's actual default (no matchMedia).
    window.matchMedia = undefined;
    expect(prefersReducedMotion()).toBe(false);
  });

  it("returns true when the media query matches", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as unknown as typeof window.matchMedia;
    expect(prefersReducedMotion()).toBe(true);
  });

  it("returns false when the media query does not match", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as unknown as typeof window.matchMedia;
    expect(prefersReducedMotion()).toBe(false);
  });

  it("never throws even if matchMedia itself throws", () => {
    window.matchMedia = vi.fn().mockImplementation(() => {
      throw new Error("not implemented");
    }) as unknown as typeof window.matchMedia;
    expect(() => prefersReducedMotion()).not.toThrow();
    expect(prefersReducedMotion()).toBe(false);
  });
});

describe("MICRO_INTERACTION_MS", () => {
  it("stays inside the roadmap's 150-200ms micro-interaction band", () => {
    expect(MICRO_INTERACTION_MS).toBeGreaterThanOrEqual(150);
    expect(MICRO_INTERACTION_MS).toBeLessThanOrEqual(200);
  });
});
