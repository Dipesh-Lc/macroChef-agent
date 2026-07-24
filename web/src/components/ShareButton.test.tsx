import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ShoppingItem } from "../api/types";
import { ShareButton } from "./ShareButton";

// Task "Shareable Shopping Lists": the `shopping_list` plan-type variant of
// the pre-existing generic `ShareButton` (recipe/day/batch/week already
// worked; this only needed the new discriminated-union arm, see
// `ShareButtonProps` in ShareButton.tsx).
vi.mock("../api/endpoints", () => ({
  createShare: vi.fn(),
}));

import { createShare } from "../api/endpoints";

function buildShoppingList(): ShoppingItem[] {
  return [{ name: "flour", quantity: "300 g", amount: 300, unit: "g", reason: null }];
}

beforeEach(() => {
  vi.mocked(createShare).mockReset();
});

describe("ShareButton with planType=shopping_list", () => {
  it("posts a shopping_list ShareCreateRequest and renders the resulting share link", async () => {
    vi.mocked(createShare).mockResolvedValue({ share_id: "abc123" });

    render(<ShareButton planType="shopping_list" payload={buildShoppingList()} />);
    fireEvent.click(screen.getByRole("button", { name: "Share" }));

    await waitFor(() => expect(createShare).toHaveBeenCalledTimes(1));
    expect(createShare).toHaveBeenCalledWith({
      plan_type: "shopping_list",
      shopping_list: buildShoppingList(),
    });

    await waitFor(() => expect(screen.getByLabelText("Share link")).toBeInTheDocument());
    expect(screen.getByLabelText("Share link")).toHaveValue(
      `${window.location.origin}/shared/abc123`,
    );
  });

  it("shows an error and a retry option when share creation fails", async () => {
    vi.mocked(createShare).mockRejectedValue(new Error("boom"));

    render(<ShareButton planType="shopping_list" payload={buildShoppingList()} />);
    fireEvent.click(screen.getByRole("button", { name: "Share" }));

    await waitFor(() =>
      expect(
        screen.getByText("Could not create a share link. Please try again."),
      ).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
