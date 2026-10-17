import type { Citation } from "@/lib/types";

const VIA_LABEL: Record<string, string> = {
  graph: "dependency graph",
  keyword: "keyword match",
  vector: "meaning match",
  both: "keyword and meaning match",
};

function where(c: Citation): string | null {
  if (!c.file || c.line_start === null) return null;
  const end = c.line_end && c.line_end !== c.line_start ? `-${c.line_end}` : "";
  return `${c.file}:${c.line_start}${end}`;
}

/**
 * Text written by the model with its [C1] markers shown as plain labels. The markers are not links:
 * the matching sources are listed right below the text.
 */
export function GeneratedText({ text }: { text: string }) {
  const parts = text.split(/(\[C\d+\])/g);
  return (
    <>
      {parts.map((part, i) =>
        /^\[C\d+\]$/.test(part) ? (
          <span key={i} className="cite">
            {part}
          </span>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

/** Every source the model was shown and cited. Opening one reveals the exact text. */
export function Sources({ citations, label = "Sources" }: { citations: Citation[]; label?: string }) {
  if (citations.length === 0) return null;
  return (
    <ol className="sources" aria-label={label}>
      {citations.map((c) => {
        const location = where(c);
        const via = c.via ? (VIA_LABEL[c.via] ?? c.via) : null;
        return (
          <li key={c.id} className="source">
            <details>
              <summary>
                <span className="cite">[{c.id}]</span> <span className="mono">{c.title}</span>
                {location ? <span className="muted"> at </span> : null}
                {location ? <span className="mono">{location}</span> : null}
                {via ? <span className="muted"> ({via})</span> : null}
              </summary>
              <pre className="source__text">{c.text}</pre>
            </details>
          </li>
        );
      })}
    </ol>
  );
}
