import type { ShoppingItem } from "../api/types";

/**
 * Extracted from `HomePage`'s previously-inline shopping-list block (same
 * behavior, just its own component) -- mirrors the sentence-case heading of
 * `frontend/components/shopping_list.py`. Quantities render in mono
 * numerals per the design system's provenance grammar.
 */
export function ShoppingList({ items }: { items: ShoppingItem[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <section className="rounded-lg border border-sage-line bg-white p-4">
      <h2 className="font-display text-base font-semibold text-cast-iron">Shopping list</h2>
      <ul className="mt-2 flex flex-col gap-1 text-sm">
        {items.map((item, index) => (
          <li
            key={index}
            className="flex justify-between gap-4 border-b border-sage-line/60 pb-1 last:border-none"
          >
            <span>{item.name}</span>
            <span className="font-mono text-cast-iron/70">
              {item.quantity ?? (item.amount != null ? `${item.amount} ${item.unit ?? ""}` : "")}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
