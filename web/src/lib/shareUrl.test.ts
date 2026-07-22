import { describe, expect, it } from "vitest";
import { composeShareUrl } from "./shareUrl";

describe("composeShareUrl", () => {
  it("composes a same-origin shared-plan URL", () => {
    expect(composeShareUrl("https://macrochef.example", "abc123")).toBe(
      "https://macrochef.example/shared/abc123",
    );
  });

  it("strips a trailing slash from the origin", () => {
    expect(composeShareUrl("https://macrochef.example/", "abc123")).toBe(
      "https://macrochef.example/shared/abc123",
    );
  });

  it("strips multiple trailing slashes from the origin", () => {
    expect(composeShareUrl("https://macrochef.example//", "abc123")).toBe(
      "https://macrochef.example/shared/abc123",
    );
  });

  it("URL-encodes a share id containing characters that need escaping", () => {
    expect(composeShareUrl("https://macrochef.example", "a b/c")).toBe(
      "https://macrochef.example/shared/a%20b%2Fc",
    );
  });

  it("works with a localhost dev origin", () => {
    expect(composeShareUrl("http://localhost:5173", "xyz")).toBe(
      "http://localhost:5173/shared/xyz",
    );
  });
});
