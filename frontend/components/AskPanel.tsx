"use client";

import { useId, useState } from "react";
import { askRun } from "@/lib/api";
import { describeError } from "@/lib/format";
import type { Answer, Edge } from "@/lib/types";
import { ImpactItem } from "./ImpactItem";
import { Notice } from "./Notice";

const HEADLINE: Record<Answer["status"], string> = {
  answered: "Impacts found",
  uncertain: "Not enough to answer",
  no_change: "Nothing changed",
};

interface Props {
  runId: string;
  versionOf: (edge: Edge) => "a" | "b";
}

export function AskPanel({ runId, versionOf }: Props) {
  const inputId = useId();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await askRun(runId, text));
    } catch (e) {
      setAnswer(null);
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="section" aria-labelledby="ask-heading">
      <h2 id="ask-heading">Ask about this comparison</h2>
      <form onSubmit={submit} className="ask" noValidate>
        <div className="field ask__field">
          <label htmlFor={inputId}>Question</label>
          <input
            id={inputId}
            type="text"
            value={question}
            maxLength={500}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="What breaks if Pet changes?"
            aria-describedby={`${inputId}-hint`}
            autoComplete="off"
          />
          <p id={`${inputId}-hint`} className="muted">
            Name an endpoint, schema, section or requirement exactly as it appears in the change list.
          </p>
        </div>
        <button type="submit" className="button button--primary" disabled={!question.trim() || busy}>
          {busy ? "Asking..." : "Ask"}
        </button>
      </form>

      <div aria-live="polite">
        {error ? (
          <Notice kind="error" title="The question could not be answered">
            {error}
          </Notice>
        ) : null}
        {answer ? (
          <div className="answer">
            <h3>{HEADLINE[answer.status]}</h3>
            <p>{answer.reason}</p>
            {answer.matched.length > 0 ? (
              <p className="muted">
                Matched: <span className="mono">{answer.matched.join(", ")}</span>
              </p>
            ) : null}
            {answer.impacts.length > 0 ? (
              <ul className="plain impacts">
                {answer.impacts.map((impact) => (
                  <ImpactItem
                    key={`${impact.change_key}-${impact.impacted_key}`}
                    impact={impact}
                    runId={runId}
                    versionOf={versionOf}
                    showChange
                  />
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
