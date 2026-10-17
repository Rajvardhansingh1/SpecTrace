"use client";

import { useState } from "react";
import { createNarrative } from "@/lib/api";
import { describeError, formatDate } from "@/lib/format";
import type { Capabilities, Generated, Narrative } from "@/lib/types";
import { Notice } from "./Notice";
import { GeneratedText, Sources } from "./Sources";

interface Props {
  runId: string;
  labelA: string;
  labelB: string;
  capabilities: Capabilities | null;
  initial?: Narrative;
}

function Part({ title, part }: { title: string; part: Generated }) {
  return (
    <section className="summary__part" aria-label={title}>
      <h3>{title}</h3>
      {part.status === "uncertain" ? (
        <p className="muted">{part.text}</p>
      ) : (
        <p>
          <GeneratedText text={part.text} />
        </p>
      )}
      {part.warnings.map((w) => (
        <p key={w} className="muted">
          {w}
        </p>
      ))}
      {part.truncated ? (
        <p className="muted">Only part of the documents fit in the prompt, so this is a partial summary.</p>
      ) : null}
      <Sources citations={part.citations} label={`Sources for ${title}`} />
    </section>
  );
}

export function SummaryPanel({ runId, labelA, labelB, capabilities, initial }: Props) {
  const [narrative, setNarrative] = useState<Narrative | undefined>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate(refresh: boolean) {
    setBusy(true);
    setError(null);
    try {
      setNarrative(await createNarrative(runId, refresh));
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  if (capabilities && !capabilities.llm.enabled && !narrative) {
    return (
      <section className="section" aria-labelledby="summary-heading">
        <h2 id="summary-heading">Summary</h2>
        <p className="muted">
          Written summaries are off because no language model is configured on this server. The change
          list below, the evidence and the question box work without one.
        </p>
      </section>
    );
  }

  const recipients = narrative?.sent_to ?? capabilities?.sends_documents_to ?? [];
  const consent =
    recipients.length > 0
      ? `Writing the summary sends the text of both versions to ${recipients.join(" and ")}.`
      : "Writing the summary runs on this server. No document text is sent to a third party.";

  return (
    <section className="section" aria-labelledby="summary-heading">
      <h2 id="summary-heading">Summary</h2>

      {!narrative ? (
        <div className="summary__start">
          <p className="muted">
            A short summary of {labelA}, of {labelB}, and of what changed between them. Every sentence
            cites the text it came from, and a sentence that cites nothing is removed.
          </p>
          <p className="muted" id="summary-consent">
            {consent}
          </p>
          <button
            type="button"
            className="button button--primary"
            onClick={() => generate(false)}
            disabled={busy || !capabilities}
            aria-describedby="summary-consent"
          >
            {busy ? "Writing the summary..." : "Summarize both versions"}
          </button>
        </div>
      ) : (
        <>
          <div className="summary">
            <Part title="What changed" part={narrative.changes} />
            <Part title={`Version ${labelA}`} part={narrative.version_a} />
            <Part title={`Version ${labelB}`} part={narrative.version_b} />
          </div>
          <p className="muted summary__foot">
            Written by <span className="mono">{narrative.model}</span> on {formatDate(narrative.generated_at)}
            . The sources listed under each part are the only text it was allowed to use.{" "}
            <button
              type="button"
              className="button button--quiet"
              onClick={() => generate(true)}
              disabled={busy}
            >
              {busy ? "Writing again..." : "Write it again"}
            </button>
          </p>
        </>
      )}

      <div aria-live="polite">
        {busy && !narrative ? (
          <Notice kind="loading" title="Writing the summary">
            This calls the language model three times and can take up to a minute.
          </Notice>
        ) : null}
        {error ? (
          <Notice kind="error" title="The summary could not be written">
            {error}
          </Notice>
        ) : null}
      </div>
    </section>
  );
}
