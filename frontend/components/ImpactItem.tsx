"use client";

import { useId, useState } from "react";
import { getSnippet } from "@/lib/api";
import { citation, hopsFromImpacted } from "@/lib/evidence";
import { describeError, percent, relationLabel } from "@/lib/format";
import type { Edge, Impact, Snippet } from "@/lib/types";
import { CertaintyTag } from "./Tags";

interface Context {
  runId: string;
  versionOf: (edge: Edge) => "a" | "b";
}

function EvidenceHop({ edge, runId, versionOf }: Context & { edge: Edge }) {
  const [open, setOpen] = useState(false);
  const [snippet, setSnippet] = useState<Snippet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const where = citation(edge);
  const regionId = useId();

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (!next || snippet || loading) return;
    setLoading(true);
    setError(null);
    try {
      setSnippet(
        await getSnippet(runId, versionOf(edge), edge.evidence.file, edge.evidence.line_start),
      );
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="button button--quiet hop__toggle"
        aria-expanded={open}
        aria-controls={regionId}
        onClick={toggle}
      >
        {open ? "Hide" : "Show"} source at <span className="mono">{where}</span>
      </button>
      {/* Always rendered: a live region that appears together with its content is often not announced. */}
      <div id={regionId} className="snippet" aria-live="polite">
        {open ? (
          <>
            {loading ? <p className="muted">Loading source...</p> : null}
            {error ? <p role="alert">{error}</p> : null}
            {snippet ? (
              <pre aria-label={`Source around ${where}`}>
                {snippet.lines.map((line) => (
                  <span
                    key={line.n}
                    className={
                      line.n === edge.evidence.line_start
                        ? "snippet__line snippet__line--cited"
                        : "snippet__line"
                    }
                  >
                    <span className="snippet__n">{line.n}</span>
                    <span className="snippet__text">{line.text || " "}</span>
                    {"\n"}
                  </span>
                ))}
              </pre>
            ) : null}
          </>
        ) : null}
      </div>
    </>
  );
}

interface Props extends Context {
  impact: Impact;
  /** Show which change this impact belongs to; used for answers that span several changes. */
  showChange?: boolean;
}

export function ImpactItem({ impact, runId, versionOf, showChange = false }: Props) {
  const hops = hopsFromImpacted(impact);
  return (
    <li className="impact">
      <div className="impact__head">
        <span className="mono impact__key">{impact.impacted_key}</span>
        <CertaintyTag value={impact.certainty} confidence={impact.confidence} />
        {impact.confirmed_breaking ? <span className="flag">Confirmed breaking</span> : null}
      </div>
      {showChange ? (
        <p className="muted">
          Depends on <span className="mono">{impact.change_key}</span>
        </p>
      ) : null}
      {impact.certainty === "inferred" ? (
        <p className="muted">
          At least one link is a guess ({percent(impact.confidence)} combined confidence). Check the source
          before acting on it.
        </p>
      ) : null}
      <ol className="hops" aria-label={`How ${impact.impacted_key} depends on ${impact.change_key}`}>
        {hops.map((edge, i) => (
          <li key={`${edge.source_key}-${edge.target_key}-${i}`} className="hop">
            <p>
              <span className="mono">{edge.source_key}</span>{" "}
              <span className="hop__rel">{relationLabel(edge.relation)}</span>{" "}
              <span className="mono">{edge.target_key}</span>
            </p>
            <p className="muted hop__meta">
              {/* A confirmed impact has only confirmed hops, so the label is only worth showing
                  on an inferred one, where it points at the link that is a guess. */}
              {impact.certainty === "inferred" ? <CertaintyTag value={edge.label} /> : null}
              {edge.reason}
            </p>
            <EvidenceHop edge={edge} runId={runId} versionOf={versionOf} />
          </li>
        ))}
      </ol>
    </li>
  );
}
