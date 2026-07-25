import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ShoppingItem } from "../api/types";
import { ShoppingList } from "./ShoppingList";

// Task "Shareable Shopping Lists": checkbox toggle behavior (client-side
// only, no persistence) and the "Copy" plain-text clipboard action. The
// embedded `ShareButton` (planType="shopping_list") is exercised by its own
// `ShareButton.test.tsx`, so `createShare` is mocked here only so the
// button renders without making a real network call.
vi.mock("../api/endpoints", () => ({
  createShare: vi.fn(),
}));

function buildItems(): ShoppingItem[] {
  return [
    { name: "flour", quantity: "short 300 g", amount: 300, unit: "g", reason: null },
    { name: "eggs", quantity: null, amount: 2, unit: "count", reason: null },
  ];
}

describe("ShoppingList", () => {
  it("returns nothing for an empty list", () => {
    const { container } = render(<ShoppingList items={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders each item as an unchecked checkbox initially", () => {
    render(<ShoppingList items={buildItems()} />);
    const flourCheckbox = screen.getByLabelText("Mark flour as gathered");
    const eggsCheckbox = screen.getByLabelText("Mark eggs as gathered");
    expect(flourCheckbox).not.toBeChecked();
    expect(eggsCheckbox).not.toBeChecked();
  });

  it("toggles an item's checked state independently of the others, client-side only", () => {
    render(<ShoppingList items={buildItems()} />);
    const flourCheckbox = screen.getByLabelText("Mark flour as gathered");
    const eggsCheckbox = screen.getByLabelText("Mark eggs as gathered");

    fireEvent.click(flourCheckbox);
    expect(flourCheckbox).toBeChecked();
    expect(eggsCheckbox).not.toBeChecked();

    fireEvent.click(flourCheckbox);
    expect(flourCheckbox).not.toBeChecked();
  });

  describe("Copy", () => {
    const writeText = vi.fn();

    beforeEach(() => {
      writeText.mockReset().mockResolvedValue(undefined);
      Object.assign(navigator, { clipboard: { writeText } });
    });

    it("copies a clean, one-item-per-line plain-text representation", async () => {
      render(<ShoppingList items={buildItems()} />);
      fireEvent.click(screen.getByRole("button", { name: "Copy" }));

      await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
      expect(writeText).toHaveBeenCalledWith("- short 300 g flour\n- 2 count eggs");
      await waitFor(() => expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument());
    });

    it("shows a manual-copy fallback message if the clipboard write rejects", async () => {
      writeText.mockRejectedValue(new Error("denied"));
      render(<ShoppingList items={buildItems()} />);
      fireEvent.click(screen.getByRole("button", { name: "Copy" }));

      await waitFor(() =>
        expect(
          screen.getByText("Could not copy automatically -- select and copy the list manually."),
        ).toBeInTheDocument(),
      );
    });
  });
});
