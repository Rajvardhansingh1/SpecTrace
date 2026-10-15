import { diffStats, parseDiff } from "@/lib/diff";
import type { Change, Edge, Impact } from "@/lib/types";
import { ImpactItem } from "./ImpactItem";
import { ChangeTypeText, ClassificationTag } from "./Tags";

interface Props {
  change: Change;
  impacts: Impact[];
  runId: string;
  versionOf: (edge: Edge) => "a" | "b";
}

const where = (loc: { file: string; line_start: number; line_end: number } | null) =>
  loc ? `${loc.file}:${loc.line_start}${loc.line_end !== loc.line_start ? `-${loc.line_end}` : ""}` : null;

export function ChangeDetail({ change, impacts, runId, versionOf }: Props) {
  const diff = parseDiff(change.source_diff);
  const stats = diffStats(diff);
  const confirmed = impacts.filter((i) => i.certainty === "confirmed").length;

  return (
    <article aria-labelledby="detail-heading">
      <h2 id="detail-heading" className="mono detail__title" tabIndex={-1}>
        {change.key}
      </h2>
      <p className="detail__meta">
        <ClassificationTag value={change.classification} /> <ChangeTypeText value={change.change_type} />
        {where(change.before) ? (
          <span className="muted">
            {" "}
            Before: <span className="mono">{where(change.before)}</span>
          </span>
        ) : null}
        {where(change.after) ? (
          <span className="muted">
            {" "}
            After: <span className="mono">{where(change.after)}</span>
          </span>
        ) : null}
      </p>

      <section className="section" aria-labelledby="why-heading">
        <h3 id="why-heading">Why it is classified this way</h3>
        <ul className="plain">
          {change.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </section>

      <section className="section" aria-labelledby="impact-heading">
        <h3 id="impact-heading">What depends on it</h3>
        {change.change_type === "added" ? (
          <p className="muted">
            This entity is new, so nothing in the earlier version could depend on it. Impacts are only
            computed for modified and removed entities.
          </p>
        ) : impacts.length === 0 ? (
          <p className="muted">
            Nothing in the compared files depends on this entity, within three links of it.
          </p>
        ) : (
          <>
            <p className="muted">
              {impacts.length} {impacts.length === 1 ? "dependent" : "dependents"}: {confirmed} confirmed,{" "}
              {impacts.length - confirmed} inferred. Confirmed means every link is an explicit reference;
              inferred means at least one link is a guess.
            </p>
            <ul className="plain impacts">
              {impacts.map((impact) => (
                <ImpactItem key={impact.impacted_key} impact={impact} runId={runId} versionOf={versionOf} />
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="section" aria-labelledby="diff-heading">
        <h3 id="diff-heading">Source diff</h3>
        {diff.length === 0 ? (
          <p className="muted">No text difference to show.</p>
        ) : (
          <>
            <p className="muted">
              {stats.added} added, {stats.removed} removed lines.
            </p>
            <pre className="diff" aria-label={`Source diff for ${change.key}`}>
              {diff.map((line, i) => (
                <span key={i} className={`diff__line diff__line--${line.kind}`}>
                  {line.text || " "}
                  {"\n"}
                </span>
              ))}
            </pre>
          </>
        )}
      </section>
    </article>
  );
}
