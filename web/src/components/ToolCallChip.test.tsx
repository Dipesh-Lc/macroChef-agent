import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToolCallChip, type ToolCallChipData } from "./ToolCallChip";

describe("ToolCallChip", () => {
  it("renders a pending call (no result yet) with the live args_summary, disabled/unexpandable", () => {
    const call: ToolCallChipData = {
      callId: "c1",
      tool: "search_recipes",
      argsSummary: "Searching recipes.",
    };
    render(<ToolCallChip call={call} />);

    expect(screen.getByText("Searching recipes.")).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("renders the tool's own summary verbatim once a result arrives, never inventing safety wording", () => {
    const call: ToolCallChipData = {
      callId: "c1",
      tool: "check_recipe_safety",
      result: { summary: "Checked 2 recipe(s): 1 safe, 1 rejected.", raw: { results: [] } },
    };
    render(<ToolCallChip call={call} />);

    expect(screen.getByText(/Checked 2 recipe\(s\): 1 safe, 1 rejected\./)).toBeInTheDocument();
  });

  it("expands to show a pass/fail line per recipe for check_recipe_safety, reading is_valid/rejection_reason verbatim", () => {
    const call: ToolCallChipData = {
      callId: "c1",
      tool: "check_recipe_safety",
      result: {
        summary: "Checked 2 recipe(s): 1 safe, 1 rejected.",
        raw: {
          results: [
            { recipe_id: "safe_1", result: { is_valid: true, rejection_reason: null } },
            {
              recipe_id: "bad_1",
              result: { is_valid: false, rejection_reason: "Contains peanuts" },
            },
          ],
        },
      },
    };
    render(<ToolCallChip call={call} />);

    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByText("Safe")).toBeInTheDocument();
    expect(screen.getByText(/Rejected — Contains peanuts/)).toBeInTheDocument();
  });

  it("visually distinguishes grounded/partial/unknown ground_nutrition status", () => {
    const call: ToolCallChipData = {
      callId: "c1",
      tool: "ground_nutrition",
      result: {
        summary: "Nutrition status: partial. 1 ingredient(s) unverified.",
        raw: {
          status: "partial",
          verified: false,
          per_serving: { calories: 400, protein_g: 30, carbs_g: 40, fat_g: 10, fiber_g: 5 },
          ungrounded_ingredients: ["mystery sauce"],
        },
      },
    };
    render(<ToolCallChip call={call} />);
    fireEvent.click(screen.getByRole("button"));

    const status = screen.getByText("partial");
    expect(status.className).toContain("text-honey-dark");
    expect(screen.getByText(/Unverified: mystery sauce/)).toBeInTheDocument();
  });

  it("renders a 'View recipe' action per row for search_recipes results and fires onViewRecipe", () => {
    const onViewRecipe = vi.fn();
    const call: ToolCallChipData = {
      callId: "c1",
      tool: "search_recipes",
      result: {
        summary: "Found 1 recipe(s): Lentil Soup.",
        raw: {
          recipes: [
            { recipe_id: "recipe_1", title: "Lentil Soup", cuisine: "Any", meal_type: "dinner" },
          ],
        },
      },
    };
    render(<ToolCallChip call={call} onViewRecipe={onViewRecipe} />);
    fireEvent.click(screen.getByRole("button", { name: /search_recipes/ }));

    fireEvent.click(screen.getByRole("button", { name: /view recipe/i }));
    expect(onViewRecipe).toHaveBeenCalledWith("recipe_1");
  });

  it("renders a failed tool call (ok=false, from persisted history) in the chili failure treatment", () => {
    const call: ToolCallChipData = {
      callId: "c1",
      tool: "propose_substitutions",
      ok: false,
      error: "recipe not found",
      result: { summary: "No recipe found for id 'missing_1'.", raw: {} },
    };
    render(<ToolCallChip call={call} />);

    expect(screen.getByText(/No recipe found for id 'missing_1'\./)).toHaveClass("text-chili");
  });
});
