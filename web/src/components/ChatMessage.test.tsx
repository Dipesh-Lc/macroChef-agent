import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatMessage, type ChatTranscriptRow } from "./ChatMessage";

describe("ChatMessage", () => {
  it("renders a user row right-aligned with plain content", () => {
    const row: ChatTranscriptRow = { kind: "user", id: "u1", content: "What can I cook tonight?" };
    render(<ChatMessage row={row} />);

    const bubble = screen.getByText("What can I cook tonight?");
    expect(bubble.closest("div")?.parentElement?.className).toContain("justify-end");
  });

  it("renders an assistant row with **bold** segments as <strong>, paragraphs on blank lines", () => {
    const row: ChatTranscriptRow = {
      kind: "assistant",
      id: "a1",
      content: "**Safety first.**\n\nHere is a plan.",
    };
    render(<ChatMessage row={row} />);

    const bold = screen.getByText("Safety first.");
    expect(bold.tagName).toBe("STRONG");
    expect(screen.getByText("Here is a plan.")).toBeInTheDocument();
  });

  it("renders a tool row as a ToolCallChip", () => {
    const row: ChatTranscriptRow = {
      kind: "tool",
      id: "c1",
      call: {
        callId: "c1",
        tool: "remember",
        result: { summary: "Noted.", raw: { note: "prefers spicy food" } },
      },
    };
    render(<ChatMessage row={row} />);

    expect(screen.getByText(/Noted\./)).toBeInTheDocument();
  });
});
