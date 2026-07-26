import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RecipeSearchForm } from "./RecipeSearchForm";

describe("RecipeSearchForm", () => {
  it("submits an empty-filter RecipeSearchRequest by default", () => {
    const onSearch = vi.fn();
    render(<RecipeSearchForm onSearch={onSearch} isPending={false} />);

    fireEvent.click(screen.getByRole("button", { name: "Search recipes" }));

    expect(onSearch).toHaveBeenCalledWith({
      cuisines: undefined,
      allergies: undefined,
      diet_type: undefined,
      calorie_min: undefined,
      calorie_max: undefined,
      protein_min: undefined,
      protein_max: undefined,
      carbs_min: undefined,
      carbs_max: undefined,
      fat_min: undefined,
      fat_max: undefined,
    });
  });

  it("fills cuisine, allergen, diet type, and macro ranges and produces the expected request shape", () => {
    const onSearch = vi.fn();
    render(<RecipeSearchForm onSearch={onSearch} isPending={false} />);

    fireEvent.click(screen.getByRole("button", { name: "Japanese" }));

    fireEvent.change(screen.getByLabelText("Allergens to exclude"), {
      target: { value: "peanut" },
    });
    fireEvent.keyDown(screen.getByLabelText("Allergens to exclude"), { key: "Enter" });

    fireEvent.change(screen.getByLabelText("Diet type"), { target: { value: "vegetarian" } });

    fireEvent.change(screen.getByLabelText("Calories minimum"), { target: { value: "300" } });
    fireEvent.change(screen.getByLabelText("Calories maximum"), { target: { value: "700" } });
    fireEvent.change(screen.getByLabelText("Protein (g) minimum"), { target: { value: "20" } });

    fireEvent.click(screen.getByRole("button", { name: "Search recipes" }));

    expect(onSearch).toHaveBeenCalledWith(
      expect.objectContaining({
        cuisines: ["Japanese"],
        allergies: ["peanut"],
        diet_type: "vegetarian",
        calorie_min: 300,
        calorie_max: 700,
        protein_min: 20,
        protein_max: undefined,
      }),
    );
  });

  it("disables the submit button while pending", () => {
    render(<RecipeSearchForm onSearch={vi.fn()} isPending={true} />);
    expect(screen.getByRole("button", { name: "Searching…" })).toBeDisabled();
  });
});
