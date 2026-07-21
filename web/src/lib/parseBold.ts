/**
 * Splits `**bold**`-delimited text into plain/bold segments so a caller can
 * render semantic `<strong>` without ever needing `dangerouslySetInnerHTML`
 * (disallowed repo-wide -- see eslint.config.js's `react/no-danger: error`).
 * Purely a markdown-bold-delimiter parser; does not interpret any other
 * markdown syntax.
 */
export interface TextSegment {
  bold: boolean;
  text: string;
}

export function parseBoldSegments(source: string): TextSegment[] {
  const parts = source.split("**");
  return parts
    .map((text, index) => ({ text, bold: index % 2 === 1 }))
    .filter((segment) => segment.text.length > 0);
}
