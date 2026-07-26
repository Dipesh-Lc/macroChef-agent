import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

/**
 * First modal primitive in the app (no prior overlay/dialog pattern
 * existed -- see the "Interactive Plan Recipes" task spec). Deliberately
 * minimal: no animation library, no focus-trap dependency. Closes on
 * Escape and on backdrop click; focuses the dialog container itself on
 * mount so keyboard users land somewhere sensible and Escape works
 * immediately without an extra click.
 *
 * `createPortal`'d into `document.body` so it always overlays the whole
 * viewport regardless of where it's mounted in the component tree (e.g. a
 * `PlanItemRow` nested several levels inside a scrolling calendar grid).
 */
export function Modal({
  onClose,
  children,
}: {
  onClose: () => void;
  children: React.ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    dialogRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  function handleBackdropClick(event: React.MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) {
      onClose();
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-cast-iron/50 p-4 sm:p-8"
      onMouseDown={handleBackdropClick}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        className="my-4 w-full max-w-2xl outline-none"
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
