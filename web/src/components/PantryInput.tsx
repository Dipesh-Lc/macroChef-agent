import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { extractInventory } from "../api/endpoints";
import type { ConfirmedIngredient } from "../api/types";

const SAMPLE_TYPED_INGREDIENTS =
  "chicken breast, spinach, eggs, garlic, olive oil, rice, lemon, Greek yogurt, bell peppers, onions";

const CUISINE_OPTIONS = [
  "Any",
  "Mediterranean",
  "Mexican",
  "Italian",
  "Indian",
  "Japanese",
  "American",
  "Thai",
];

const MEAL_TYPE_OPTIONS = ["breakfast", "lunch", "dinner"];

interface InventoryRow {
  key: string;
  normalizedName: string;
  quantity: string;
  amount: number | null;
  unit: string | null;
  confidence: number;
  needsConfirmation: boolean;
  include: boolean;
}

export interface PantryState {
  typedIngredients: string;
  cuisine: string | null;
  mealType: string;
  confirmedInventory: ConfirmedIngredient[];
}

function toConfirmedInventory(rows: InventoryRow[]): ConfirmedIngredient[] {
  return rows
    .filter((row) => row.include && row.normalizedName.trim().length > 0)
    .map((row) => ({
      name: row.normalizedName,
      quantity: row.quantity.trim() ? row.quantity.trim() : null,
      amount: row.amount,
      unit: row.unit,
      expires_soon: false,
    }));
}

export function PantryInput({ onChange }: { onChange: (state: PantryState) => void }) {
  const [typedIngredients, setTypedIngredients] = useState(SAMPLE_TYPED_INGREDIENTS);
  const [cuisine, setCuisine] = useState("Any");
  const [mealType, setMealType] = useState("dinner");
  const [rows, setRows] = useState<InventoryRow[]>([]);
  const [manualName, setManualName] = useState("");
  const [manualQuantity, setManualQuantity] = useState("");

  const extractMutation = useMutation({
    mutationFn: () => extractInventory(typedIngredients),
    onSuccess: (observations) => {
      setRows(
        observations.map((observation, index) => ({
          key: `${observation.normalized_name}-${index}`,
          normalizedName: observation.normalized_name,
          quantity: observation.quantity ?? "",
          amount: observation.amount ?? null,
          unit: observation.unit ?? null,
          confidence: observation.confidence,
          needsConfirmation: observation.needs_confirmation,
          include: true,
        })),
      );
    },
  });

  useEffect(() => {
    onChange({
      typedIngredients,
      cuisine: cuisine === "Any" ? null : cuisine,
      mealType,
      confirmedInventory: toConfirmedInventory(rows),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onChange is expected stable per parent render; re-firing on its identity would loop.
  }, [typedIngredients, cuisine, mealType, rows]);

  function updateRow(key: string, patch: Partial<InventoryRow>) {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function addManualRow() {
    const name = manualName.trim();
    if (!name) {
      return;
    }
    setRows((current) => [
      ...current,
      {
        key: `manual-${Date.now()}`,
        normalizedName: name,
        quantity: manualQuantity.trim(),
        amount: null,
        unit: null,
        confidence: 1,
        needsConfirmation: false,
        include: true,
      },
    ]);
    setManualName("");
    setManualQuantity("");
  }

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-sage-line bg-white p-4">
      <div>
        <h2 className="font-display text-base font-semibold text-cast-iron">Pantry</h2>
        <p className="text-xs text-cast-iron/60">
          Add what's in your kitchen to get started.
        </p>
      </div>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">Cuisine</span>
        <select
          value={cuisine}
          onChange={(event) => setCuisine(event.target.value)}
          className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
        >
          {CUISINE_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">Meal type</span>
        <select
          value={mealType}
          onChange={(event) => setMealType(event.target.value)}
          className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
        >
          {MEAL_TYPE_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">
          Fridge &amp; pantry inventory
        </span>
        <textarea
          value={typedIngredients}
          onChange={(event) => setTypedIngredients(event.target.value)}
          rows={4}
          placeholder="List everything you have, e.g. chicken breast, spinach, eggs, garlic, olive oil, rice"
          className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
        />
        <span className="text-xs text-cast-iron/50">Separate ingredients with commas.</span>
      </label>

      <button
        type="button"
        onClick={() => extractMutation.mutate()}
        disabled={extractMutation.isPending || !typedIngredients.trim()}
        className="rounded-md bg-basil px-3 py-2 text-sm font-medium text-porcelain disabled:opacity-50"
      >
        {extractMutation.isPending ? "Extracting…" : "Extract inventory"}
      </button>

      {extractMutation.isError && (
        <p className="text-sm text-chili">
          Could not extract your inventory. Check your connection and try again.
        </p>
      )}

      {rows.length > 0 && (
        <div className="flex flex-col gap-2">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-cast-iron/50">
              <tr>
                <th className="py-1 pr-2 font-medium">Use</th>
                <th className="py-1 pr-2 font-medium">Ingredient</th>
                <th className="py-1 pr-2 font-medium">Quantity</th>
                <th className="py-1 font-medium">Review</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.key}
                  className={row.needsConfirmation ? "bg-honey/10" : undefined}
                >
                  <td className="py-1 pr-2">
                    <input
                      type="checkbox"
                      checked={row.include}
                      onChange={(event) => updateRow(row.key, { include: event.target.checked })}
                      aria-label={`Include ${row.normalizedName}`}
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <input
                      type="text"
                      value={row.normalizedName}
                      onChange={(event) => updateRow(row.key, { normalizedName: event.target.value })}
                      className="w-full rounded border border-sage-line px-1.5 py-0.5"
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <input
                      type="text"
                      value={row.quantity}
                      onChange={(event) => updateRow(row.key, { quantity: event.target.value })}
                      className="w-full rounded border border-sage-line px-1.5 py-0.5"
                    />
                  </td>
                  <td className="py-1 text-xs">
                    {row.needsConfirmation ? (
                      <span className="text-honey-dark">Needs review</span>
                    ) : (
                      <span className="text-cast-iron/40">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="flex gap-2">
            <input
              type="text"
              value={manualName}
              onChange={(event) => setManualName(event.target.value)}
              placeholder="Add missed ingredient"
              aria-label="Add missed ingredient"
              className="w-1/2 rounded-md border border-sage-line px-2 py-1.5 text-sm"
            />
            <input
              type="text"
              value={manualQuantity}
              onChange={(event) => setManualQuantity(event.target.value)}
              placeholder="Quantity (optional)"
              aria-label="Quantity (optional)"
              className="w-1/3 rounded-md border border-sage-line px-2 py-1.5 text-sm"
            />
            <button
              type="button"
              onClick={addManualRow}
              className="shrink-0 rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium hover:bg-sage-line/40"
            >
              Add
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
