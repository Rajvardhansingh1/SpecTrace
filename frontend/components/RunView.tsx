"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { getRun } from "@/lib/api";
import { versionResolver } from "@/lib/evidence";
import { describeError, sortChanges, summarize } from "@/lib/format";
import type { RunDetail } from "@/lib/types";
import { AskPanel } from "./AskPanel";
import { ChangeDetail } from "./ChangeDetail";
import { ChangeList } from "./ChangeList";
import { Notice } from "./Notice";

export function RunView({ id }: { id: string }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const detailRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    getRun(id)
      .then((r) => live && setRun(r))
      .catch((e) => live && setError(describeError(e)));
    return () => {
      live = false;
    };
  }, [id]);

  const result = run?.result ?? null;
  const versionOf = useMemo(() => versionResolver(result?.graph.edges_b ?? []), [result]);
  const sorted = useMemo(() => (result ? sortChanges(result.changes) : []), [result]);
  const activeKey = selected ?? sorted[0]?.key ?? null;
  const active = result?.changes.find((c) => c.key === activeKey) ?? null;
  const totals = useMemo(() => (result ? summarize(result.changes, result.impacts) : null), [result]);

  function select(key: string) {
    setSelected(key);
    // On a narrow screen the detail sits below the list, so move the reader to it.
    requestAnimationFrame(() => {
      const heading = detailRef.current?.querySelector<HTMLElement>("#detail-heading");
      heading?.focus({ preventScroll: true });
      detailRef.current?.scrollIntoView({ block: "start" });
    });
  }

  if (error) {
    return (
      <Notice
        kind="error"
        title="This comparison could not be opened"
        action={<Link href="/">Back to Compare</Link>}
      >
        {error}
      </Notice>
    );
  }
  if (!run) return <Notice kind="loading" title="Loading comparison" />;
  if (run.status === "failed") {
    return (
      <Notice
        kind="error"
        title="This comparison failed"
        action={<Link href="/">Start a new comparison</Link>}
      >
        The analysis stopped with the error code <span className="mono">{run.error_code ?? "unknown"}</span>.
      </Notice>
    );
  }
  if (!result || !totals) return <Notice kind="loading" title="The analysis is still running" />;

  return (
    <>
      <header className="runhead">
        <h1>
          <span className="mono">{run.label_a}</span> to <span className="mono">{run.label_b}</span>
        </h1>
        <p className="muted">
          {totals.changes} {totals.changes === 1 ? "change" : "changes"}, {totals.breaking} breaking.{" "}
          {totals.impacts} {totals.impacts === 1 ? "dependent" : "dependents"} found: {totals.confirmed}{" "}
          confirmed, {totals.inferred} inferred. Analyzed {result.stats.entities_a} and{" "}
          {result.stats.entities_b} entities in {Math.round(result.stats.elapsed_ms)} ms.{" "}
          <a href="#ask-heading">Ask a question about this comparison</a>.
        </p>
      </header>

      {result.unsupported.length > 0 || result.warnings.length > 0 ? (
        <details className="notes">
          <summary>
            Notes from the analysis ({result.unsupported.length + result.warnings.length})
          </summary>
          <ul className="plain">
            {[...result.unsupported, ...result.warnings].map((note) => (
              <li key={note} className="mono">
                {note}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {result.changes.length === 0 ? (
        <section className="section">
          <Notice kind="empty" title="No differences found">
            Both versions produce the same entities. Formatting and comment changes are ignored on purpose.
          </Notice>
        </section>
      ) : (
        <div className="review">
          <section className="section review__list" aria-labelledby="changes-heading">
            <h2 id="changes-heading">Changes</h2>
            <ChangeList
              changes={result.changes}
              impacts={result.impacts}
              selectedKey={activeKey}
              onSelect={select}
            />
          </section>
          <div className="section review__detail" ref={detailRef}>
            {active ? (
              <ChangeDetail
                key={active.key}
                change={active}
                impacts={result.impacts[active.key] ?? []}
                runId={run.id}
                versionOf={versionOf}
              />
            ) : null}
          </div>
        </div>
      )}

      {/* After the review, so a long answer never pushes the change list out of view. */}
      <AskPanel runId={run.id} versionOf={versionOf} />
    </>
  );
}
