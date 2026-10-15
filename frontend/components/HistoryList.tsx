"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listRuns } from "@/lib/api";
import { describeError, formatDate } from "@/lib/format";
import type { RunSummary } from "@/lib/types";
import { Notice } from "./Notice";

const STATUS_TEXT = { running: "Running", done: "Done", failed: "Failed" } as const;

export function HistoryList({ refreshKey = 0 }: { refreshKey?: number }) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    listRuns()
      .then((r) => live && (setRuns(r), setError(null)))
      .catch((e) => live && setError(describeError(e)));
    return () => {
      live = false;
    };
  }, [refreshKey]);

  if (error) return <Notice kind="error" title="Earlier comparisons could not be loaded">{error}</Notice>;
  if (runs === null) return <Notice kind="loading" title="Loading earlier comparisons" />;
  if (runs.length === 0) {
    return (
      <Notice kind="empty" title="No comparisons yet">
        Load the petstore example above to see what a result looks like.
      </Notice>
    );
  }

  return (
    <table className="ledger">
      <caption className="sr-only">Earlier comparisons, newest first</caption>
      <thead>
        <tr>
          <th scope="col">Versions</th>
          <th scope="col">Status</th>
          <th scope="col">Created</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => (
          <tr key={run.id}>
            <td>
              {run.status === "done" ? (
                <Link href={`/runs/${run.id}`}>
                  <span className="mono">{run.label_a}</span> to <span className="mono">{run.label_b}</span>
                </Link>
              ) : (
                <span>
                  <span className="mono">{run.label_a}</span> to <span className="mono">{run.label_b}</span>
                </span>
              )}
            </td>
            <td>
              {STATUS_TEXT[run.status]}
              {run.error_code ? <span className="muted mono"> {run.error_code}</span> : null}
            </td>
            <td className="muted">{formatDate(run.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
