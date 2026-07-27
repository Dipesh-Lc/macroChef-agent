import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { InventoryObservation } from "../api/types";
import { PantryInput, type PantryState } from "./PantryInput";

vi.mock("../api/endpoints", () => ({
  extractInventory: vi.fn(),
}));

import { extractInventory } from "../api/endpoints";

function buildObservation(overrides: Partial<InventoryObservation> = {}): InventoryObservation {
  return {
    raw_name: "chicken breast",
    normalized_name: "chicken breast",
    quantity: "2 lb",
    amount: 2,
    unit: "lb",
    confidence: 0.9,
    source: "manual",
    needs_confirmation: false,
    ...overrides,
  };
}

function renderPantryInput(onChange: (state: PantryState) => void) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <PantryInput onChange={onChange} />
    </QueryClientProvider>,
  );
}

async function extractOneRow() {
  vi.mocked(extractInventory).mockResolvedValue([buildObservation()]);
  fireEvent.click(screen.getByRole("button", { name: "Extract inventory" }));
  await waitFor(() => expect(screen.getByLabelText("Amount for chicken breast")).toBeInTheDocument());
}

beforeEach(() => {
  vi.mocked(extractInventory).mockReset();
});

describe("PantryInput", () => {
  it("flows an edited amount/unit on an extracted row into confirmedInventory (not null)", async () => {
    const onChange = vi.fn();
    renderPantryInput(onChange);

    await extractOneRow();

    fireEvent.change(screen.getByLabelText("Amount for chicken breast"), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText("Unit for chicken breast"), {
      target: { value: "kg" },
    });

    await waitFor(() => {
      const lastCall = onChange.mock.calls.at(-1)?.[0] as PantryState;
      expect(lastCall.confirmedInventory).toEqual([
        expect.objectContaining({
          name: "chicken breast",
          amount: 3,
          unit: "kg",
          quantity: "3 kg",
        }),
      ]);
    });
  });

  it("clears amount to null when the amount input is emptied", async () => {
    const onChange = vi.fn();
    renderPantryInput(onChange);

    await extractOneRow();

    fireEvent.change(screen.getByLabelText("Amount for chicken breast"), {
      target: { value: "" },
    });

    await waitFor(() => {
      const lastCall = onChange.mock.calls.at(-1)?.[0] as PantryState;
      expect(lastCall.confirmedInventory[0]).toEqual(
        expect.objectContaining({ amount: null, unit: "lb", quantity: "lb" }),
      );
    });
  });

  it("adds a manual row with amount+unit that flows into confirmedInventory (not null)", async () => {
    const onChange = vi.fn();
    renderPantryInput(onChange);

    await extractOneRow();

    fireEvent.change(screen.getByLabelText("Add missed ingredient"), {
      target: { value: "olive oil" },
    });
    fireEvent.change(screen.getByLabelText("Amount (optional)"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Unit (optional)"), {
      target: { value: "tbsp" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      const lastCall = onChange.mock.calls.at(-1)?.[0] as PantryState;
      expect(lastCall.confirmedInventory).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            name: "olive oil",
            amount: 2,
            unit: "tbsp",
            quantity: "2 tbsp",
          }),
        ]),
      );
    });
  });

  it("adds a manual row with no amount/unit typed as null, not a placeholder string", async () => {
    const onChange = vi.fn();
    renderPantryInput(onChange);

    await extractOneRow();

    fireEvent.change(screen.getByLabelText("Add missed ingredient"), {
      target: { value: "salt" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      const lastCall = onChange.mock.calls.at(-1)?.[0] as PantryState;
      expect(lastCall.confirmedInventory).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ name: "salt", amount: null, unit: null, quantity: null }),
        ]),
      );
    });
  });
});
