import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RecipeArt } from "./RecipeArt";

describe("RecipeArt", () => {
  it("renders the same gradient background for the same recipe on repeated renders", () => {
    const recipe = { title: "Slow Cooker Beef Rendang", cuisine: "Indonesian" };
    const first = render(<RecipeArt recipe={recipe} />);
    const firstStyle = first.container.querySelector("div[aria-hidden]")?.getAttribute("style");
    first.unmount();

    const second = render(<RecipeArt recipe={recipe} />);
    const secondStyle = second.container.querySelector("div[aria-hidden]")?.getAttribute("style");

    expect(firstStyle).toBeTruthy();
    expect(secondStyle).toBe(firstStyle);
  });

  it("renders as decorative-only: no network image, no baked-in text", () => {
    const { container } = render(<RecipeArt recipe={{ title: "Any Recipe", cuisine: "Any" }} />);
    expect(container.querySelector("img")).toBeNull();
    // No text content anywhere in the art -- the title lives in the card,
    // never inside the generated art itself.
    expect(container.textContent).toBe("");
  });

  it("marks the art aria-hidden so screen readers rely on the adjacent title text instead", () => {
    const { container } = render(<RecipeArt recipe={{ title: "Any Recipe", cuisine: "Any" }} />);
    const art = container.querySelector("[aria-hidden='true']");
    expect(art).not.toBeNull();
  });
});
