import { useState } from "react";
import type { ShoppingItem } from "../api/types";
import { ShareButton } from "./ShareButton";

/**
 * Extracted from `HomePage`'s previously-inline shopping-list block (same
 * behavior, just its own component) -- mirrors the sentence-case heading of
 * `frontend/components/shopping_list.py`. Quantities render in mono
 * numerals per the design system's provenance grammar.
 *
 * Shareable shopping list (task "Shareable Shopping Lists"): each item is
 * now a checkbox (local `useState`, client-side only -- no persistence,
 * per that task's spec) instead of a plain list, a "Copy" button copies a
 * clean plain-text representation to the clipboard, and a "Share" action
 * reuses `ShareButton` with `planType="shopping_list"` so a shared link
 * opens directly to this same list (see `SharedPlanPage.tsx`'s
 * `shopping_list` dispatch branch). Checked state is intentionally NOT sent
 * to the share payload -- the server-side allowlist
 * (`app.services.share_service.shopping_list_to_public`) only ever sees
 * `ShoppingItem[]`, never a client-side UI toggle.
 */

function quantityText(item: ShoppingItem): string {
  return item.quantity ?? (item.amount != null ? `${item.amount} ${item.unit ?? ""}`.trim() : "");
}

function itemLineText(item: ShoppingItem): string {
  const quantity = quantityText(item);
  return quantity ? `- ${quantity} ${item.name}` : `- ${item.name}`;
}

function shoppingListPlainText(items: ShoppingItem[]): string {
  return items.map(itemLineText).join("\n");
}

const COPIED_RESET_MS = 2000;

export function ShoppingList({ items }: { items: ShoppingItem[] }) {
  const [checkedIds, setCheckedIds] = useState<Set<number>>(() => new Set());
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);

  if (items.length === 0) {
    return null;
  }

  function toggleChecked(index: number) {
    setCheckedIds((current) => {
      const next = new Set(current);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }

  async function handleCopy() {
    setCopyError(null);
    try {
      await navigator.clipboard.writeText(shoppingListPlainText(items));
      setCopied(true);
      setTimeout(() => setCopied(false), COPIED_RESET_MS);
    } catch {
      setCopyError("Could not copy automatically -- select and copy the list manually.");
    }
  }

  return (
    <section className="rounded-lg border border-sage-line bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display text-base font-semibold text-cast-iron">Shopping list</h2>
        <button
          type="button"
          onClick={handleCopy}
          className="shrink-0 rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium text-cast-iron hover:bg-sage-line/40"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      {copyError && <p className="mt-1 text-sm text-chili">{copyError}</p>}

      <ul className="mt-2 flex flex-col gap-1 text-sm">
        {items.map((item, index) => {
          const checked = checkedIds.has(index);
          return (
            <li
              key={index}
              className="flex items-center justify-between gap-4 border-b border-sage-line/60 pb-1 last:border-none"
            >
              <label className="flex flex-1 items-center gap-2">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleChecked(index)}
                  aria-label={`Mark ${item.name} as gathered`}
                />
                <span className={checked ? "text-cast-iron/40 line-through" : undefined}>
                  {item.name}
                </span>
              </label>
              <span className="font-mono text-cast-iron/70">{quantityText(item)}</span>
            </li>
          );
        })}
      </ul>

      <div className="mt-3">
        <ShareButton planType="shopping_list" payload={items} />
      </div>
    </section>
  );
}
