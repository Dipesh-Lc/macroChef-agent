import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SharedPlanView } from "../api/types";
import SharedPlanPage from "./SharedPlanPage";

// Task "Shareable Shopping Lists": rendering test for the new
// `plan_type: "shopping_list"` dispatch branch this page now handles (see
// `SharedShoppingListView`, which reuses `ShoppingList` verbatim).
vi.mock("../api/endpoints", () => ({
  getSharedPlan: vi.fn(),
  createShare: vi.fn(),
}));

import { getSharedPlan } from "../api/endpoints";

function renderAtShareId(shareId: string) {
  return render(
    <MemoryRouter initialEntries={[`/shared/${shareId}`]}>
      <Routes>
        <Route path="/shared/:shareId" element={<SharedPlanPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(getSharedPlan).mockReset();
});

describe("SharedPlanPage: shopping_list plan type", () => {
  it("renders the shared shopping list's items and the disclaimer", async () => {
    const view: SharedPlanView = {
      plan_type: "shopping_list",
      content: [
        { name: "flour", quantity: "300 g", amount: 300, unit: "g", reason: null },
        { name: "eggs", quantity: null, amount: 2, unit: "count", reason: null },
      ],
      disclaimer: "Hobby project — not medical advice.",
    };
    vi.mocked(getSharedPlan).mockResolvedValue(view);

    renderAtShareId("shop123");

    await waitFor(() => expect(screen.getByText("flour")).toBeInTheDocument());
    expect(screen.getByText("eggs")).toBeInTheDocument();
    expect(screen.getByText("Hobby project — not medical advice.")).toBeInTheDocument();
    expect(screen.getByLabelText("Mark flour as gathered")).toBeInTheDocument();
  });

  it("shows the not-found state for a missing shopping list share id", async () => {
    const { NotFoundError } = await import("../api/client");
    vi.mocked(getSharedPlan).mockRejectedValue(new NotFoundError("not found"));

    renderAtShareId("does-not-exist");

    await waitFor(() =>
      expect(screen.getByText("This shared plan wasn't found")).toBeInTheDocument(),
    );
  });
});
