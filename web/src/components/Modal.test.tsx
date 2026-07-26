import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "./Modal";

describe("Modal", () => {
  it("renders its children", () => {
    render(
      <Modal onClose={vi.fn()}>
        <p>Modal content</p>
      </Modal>,
    );
    expect(screen.getByText("Modal content")).toBeInTheDocument();
  });

  it("has dialog semantics", () => {
    render(
      <Modal onClose={vi.fn()}>
        <p>Modal content</p>
      </Modal>,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("calls onClose when Escape is pressed", () => {
    const onClose = vi.fn();
    render(
      <Modal onClose={onClose}>
        <p>Modal content</p>
      </Modal>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the backdrop is clicked", () => {
    const onClose = vi.fn();
    render(
      <Modal onClose={onClose}>
        <p>Modal content</p>
      </Modal>,
    );
    const backdrop = document.querySelector(".fixed.inset-0") as HTMLElement;
    fireEvent.mouseDown(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not call onClose when clicking inside the dialog", () => {
    const onClose = vi.fn();
    render(
      <Modal onClose={onClose}>
        <p>Modal content</p>
      </Modal>,
    );
    fireEvent.mouseDown(screen.getByText("Modal content"));
    expect(onClose).not.toHaveBeenCalled();
  });
});
