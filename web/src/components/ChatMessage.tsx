import { parseBoldSegments } from "../lib/parseBold";
import { ToolCallChip, type ToolCallChipData } from "./ToolCallChip";

/**
 * One row in a Chef chat transcript (ROADMAP.md Step 4.3). A `tool` row
 * renders as `ToolCallChip`; `user`/`assistant` rows render as a plain
 * bubble. `id` is a stable React key -- for a live-streaming turn it's the
 * SSE `call_id` (tool rows) or a locally-minted id (text rows); for history
 * replay it's derived from the message's position in `GET
 * /chat/{thread_id}`'s response (see `ChatPage`'s `messagesToRows`).
 */
export type ChatTranscriptRow =
  | { kind: "user"; id: string; content: string }
  | { kind: "assistant"; id: string; content: string }
  | { kind: "tool"; id: string; call: ToolCallChipData };

/**
 * Plain-text-with-paragraph-breaks markdown fallback. This repo has no
 * markdown-rendering dependency in `package.json` (checked before writing
 * this) -- rather than add one just for this step's assistant bubble, a
 * blank line starts a new paragraph, a single newline becomes a line break,
 * and `**bold**` reuses the exact same `parseBoldSegments` helper
 * `DisclaimerBanner` already relies on. No other markdown syntax (lists,
 * links, headings) is interpreted. Tradeoff noted in the executor report:
 * a real Chef answer with markdown lists/headings will read as flattened
 * prose rather than a formatted list -- acceptable for this step, revisit
 * if `remark`/`react-markdown` is ever pulled in for another reason.
 */
function renderLiteMarkdown(content: string) {
  const paragraphs = content.split(/\n{2,}/);
  return paragraphs.map((paragraph, paragraphIndex) => {
    const lines = paragraph.split("\n");
    return (
      <p key={paragraphIndex} className={paragraphIndex > 0 ? "mt-2" : undefined}>
        {lines.map((line, lineIndex) => (
          <span key={lineIndex}>
            {parseBoldSegments(line).map((segment, segmentIndex) =>
              segment.bold ? (
                <strong key={segmentIndex} className="font-semibold">
                  {segment.text}
                </strong>
              ) : (
                <span key={segmentIndex}>{segment.text}</span>
              ),
            )}
            {lineIndex < lines.length - 1 && <br />}
          </span>
        ))}
      </p>
    );
  });
}

export function ChatMessage({
  row,
  onViewRecipe,
}: {
  row: ChatTranscriptRow;
  onViewRecipe?: (recipeId: string) => void;
}) {
  if (row.kind === "tool") {
    return <ToolCallChip call={row.call} onViewRecipe={onViewRecipe} />;
  }

  const isUser = row.kind === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          isUser
            ? "bg-cast-iron text-porcelain"
            : "border border-sage-line bg-white text-cast-iron"
        }`}
      >
        {renderLiteMarkdown(row.content)}
      </div>
    </div>
  );
}
