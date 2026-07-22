import { useState } from "react";

export function TagInput({
  label,
  placeholder,
  items,
  onChange,
}: {
  label: string;
  placeholder: string;
  items: string[];
  onChange: (items: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  function addTag() {
    const value = draft.trim();
    if (!value) {
      return;
    }
    if (items.some((item) => item.toLowerCase() === value.toLowerCase())) {
      setDraft("");
      return;
    }
    onChange([...items, value]);
    setDraft("");
  }

  function removeTag(target: string) {
    onChange(items.filter((item) => item !== target));
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">{label}</span>
      {items.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {items.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => removeTag(item)}
              className="rounded-full border border-sage-line bg-porcelain px-2 py-0.5 text-xs text-cast-iron"
              aria-label={`Remove ${item}`}
              title="Remove"
            >
              {item} ×
            </button>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <input
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addTag();
            }
          }}
          placeholder={placeholder}
          aria-label={label}
          className="w-full rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
        />
        <button
          type="button"
          onClick={addTag}
          className="shrink-0 rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium text-cast-iron hover:bg-sage-line/40"
        >
          Add
        </button>
      </div>
    </div>
  );
}
