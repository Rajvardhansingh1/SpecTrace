export type DiffLineKind = "file" | "hunk" | "add" | "del" | "context";

export interface DiffLine {
  kind: DiffLineKind;
  text: string;
}

/** Parses the unified diff the API returns. Marker characters stay in the text so the change reads without color. */
export function parseDiff(diff: string): DiffLine[] {
  if (!diff.trim()) return [];
  return diff.split("\n").map((text) => {
    if (text.startsWith("---") || text.startsWith("+++")) return { kind: "file", text };
    if (text.startsWith("@@")) return { kind: "hunk", text };
    if (text.startsWith("+")) return { kind: "add", text };
    if (text.startsWith("-")) return { kind: "del", text };
    return { kind: "context", text };
  });
}

export function diffStats(lines: DiffLine[]): { added: number; removed: number } {
  return {
    added: lines.filter((l) => l.kind === "add").length,
    removed: lines.filter((l) => l.kind === "del").length,
  };
}
