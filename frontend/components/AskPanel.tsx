"use client";

import { useId, useState } from "react";
import { askRun } from "@/lib/api";
import { describeError } from "@/lib/format";
import type { Answer, Capabilities, Edge } from "@/lib/types";
import { ImpactItem } from "./ImpactItem";
import { Notice } from "./Notice";
import { GeneratedText, Sources } from "./Sources";

const HEADLINE_GENERATED: Record<Answer["status"], string> = {
  answered: "Answer",
  uncertain: "Not enough to answer",
  no_change: "Nothing changed",
};
const HEADLINE_MATCHED: Record<Answer["status"], string> = {
  answered: "Impacts found",
  uncertain: "Not enough to answer",
  no_change: "Nothing changed",
};

interface Props {
  runId: string;
  versionOf: (edge: Edge) => "a" | "b";
  capabilities?: Capabilities | null;
}

export function AskPanel({ runId, versionOf, capabilities = null }: Props) {
  const inputId = useId();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const modelOn = Boolean(capabilities?.llm.enabled);

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

  const recipients = capabilities?.sends_documents_to ?? [];

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
            placeholder={
              modelOn ? "What do the docs need after the Pet change?" : "What breaks if Pet changes?"
            }
            aria-describedby={`${inputId}-hint`}
            autoComplete="off"
          />
          <p id={`${inputId}-hint`} className="muted">
            {modelOn
              ? `Ask in your own words. The answer is written from the two versions and the dependency graph, and each claim cites its source. ${
                  recipients.length > 0
                    ? `Your question and the relevant passages are sent to ${recipients.join(" and ")}.`
                    : "Nothing is sent to a third party."
                }`
              : "Name an endpoint, schema, section or requirement exactly as it appears in the change list. No language model is configured, so this matches names only."}
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
            <h3>{(answer.generated ? HEADLINE_GENERATED : HEADLINE_MATCHED)[answer.status]}</h3>
            {answer.generated && answer.answer ? (
              <>
                <p className={answer.status === "uncertain" ? "muted" : undefined}>
                  <GeneratedText text={answer.answer} />
                </p>
                <p className="muted">
                  Written by <span className="mono">{answer.model}</span> from the sources below.
                  {answer.retrieval && !answer.retrieval.semantic
                    ? " Passages were found by keywords only."
                    : ""}
                </p>
                {answer.warnings.map((w) => (
                  <p key={w} className="muted">
                    {w}
                  </p>
                ))}
                {answer.truncated ? (
                  <p className="muted">Some relevant text did not fit in the prompt and was left out.</p>
                ) : null}
                <Sources citations={answer.citations} />
              </>
            ) : (
              <>
                <p>{answer.reason}</p>
                {answer.matched.length > 0 ? (
                  <p className="muted">
                    Matched: <span className="mono">{answer.matched.join(", ")}</span>
                  </p>
                ) : null}
              </>
            )}
            {answer.impacts.length > 0 ? (
              <>
                {answer.generated ? (
                  <h4 className="answer__sub">Dependents found in the dependency graph</h4>
                ) : null}
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
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
