"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createRun } from "@/lib/api";
import { checkVersion } from "@/lib/files";
import { describeError } from "@/lib/format";
import sample from "@/lib/sample-data.json";
import type { VersionFiles } from "@/lib/types";
import { HistoryList } from "./HistoryList";
import { Notice } from "./Notice";
import { VersionPane } from "./VersionPane";

export function CompareForm() {
  const router = useRouter();
  const [labelA, setLabelA] = useState("v1");
  const [labelB, setLabelB] = useState("v2");
  const [filesA, setFilesA] = useState<VersionFiles>({});
  const [filesB, setFilesB] = useState<VersionFiles>({});
  // Skipped files are kept per version so choosing files for B does not erase the notice for A.
  const [skipped, setSkipped] = useState<{ A: string[]; B: string[] }>({ A: [], B: [] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const problemA = checkVersion("version A", filesA);
  const problemB = checkVersion("version B", filesB);
  const blocked = problemA ?? problemB;

  function adder(side: "A" | "B", set: (f: (prev: VersionFiles) => VersionFiles) => void) {
    return (added: VersionFiles, notSupported: string[]) => {
      set((prev) => ({ ...prev, ...added }));
      setSkipped((prev) => ({ ...prev, [side]: notSupported }));
    };
  }

  function remover(set: (f: (prev: VersionFiles) => VersionFiles) => void) {
    return (name: string) =>
      set((prev) => Object.fromEntries(Object.entries(prev).filter(([n]) => n !== name)));
  }

  function loadSample() {
    setLabelA(sample.a.label);
    setLabelB(sample.b.label);
    setFilesA(sample.a.files);
    setFilesB(sample.b.files);
    setSkipped({ A: [], B: [] });
    setError(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (blocked || busy) return;
    setBusy(true);
    setError(null);
    try {
      const run = await createRun({
        files_a: filesA,
        files_b: filesB,
        label_a: labelA.trim() || "A",
        label_b: labelB.trim() || "B",
      });
      router.push(`/runs/${run.id}`);
    } catch (e) {
      setError(describeError(e));
      setBusy(false);
    }
  }

  return (
    <>
      <form onSubmit={submit} noValidate>
        <div className="panes">
          <VersionPane
            side="A"
            heading="Version A (before)"
            label={labelA}
            files={filesA}
            onLabel={setLabelA}
            onAdd={adder("A", setFilesA)}
            onRemove={remover(setFilesA)}
          />
          <VersionPane
            side="B"
            heading="Version B (after)"
            label={labelB}
            files={filesB}
            onLabel={setLabelB}
            onAdd={adder("B", setFilesB)}
            onRemove={remover(setFilesB)}
          />
        </div>

        {skipped.A.length + skipped.B.length > 0 ? (
          <Notice kind="empty" title="Some files were not added">
            {[
              ...skipped.A.map((s) => `Version A, ${s}`),
              ...skipped.B.map((s) => `Version B, ${s}`),
            ].join("; ")}
          </Notice>
        ) : null}

        <div className="actions">
          <button
            type="submit"
            className="button button--primary"
            disabled={Boolean(blocked) || busy}
            aria-describedby="submit-hint"
          >
            {busy ? "Comparing..." : "Compare versions"}
          </button>
          <button type="button" className="button" onClick={loadSample} disabled={busy}>
            Load petstore example
          </button>
          <p id="submit-hint" className="muted actions__hint" aria-live="polite">
            {busy
              ? `Comparing ${Object.keys(filesA).length + Object.keys(filesB).length} files.`
              : (blocked ?? "Ready to compare.")}
          </p>
        </div>

        {error ? (
          <Notice kind="error" title="The comparison could not be completed">
            {error}
          </Notice>
        ) : null}
      </form>

      <section aria-labelledby="history-heading" className="section">
        <h2 id="history-heading">Earlier comparisons</h2>
        <HistoryList refreshKey={busy ? 1 : 0} />
      </section>
    </>
  );
}
