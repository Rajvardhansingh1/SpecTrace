import type { Metadata } from "next";
import data from "@/data/benchmark.json";

export const metadata: Metadata = { title: "Benchmark" };

interface Counts {
  precision: number | null;
  recall: number | null;
  reported: number;
  expected: number;
}
interface CaseScore {
  id: string;
  split: string;
  engine: { true_positive: number; expected: number; reported: number; missed: string[][]; extra: string[][] };
  baseline: { true_positive: number; expected: number; reported: number; missed: string[][]; extra: string[][] };
}

const result = data as unknown as {
  dataset: { version: string; split: string; cases: number };
  run: { date: string; commit: string | null };
  config: Record<string, unknown>;
  aggregate: {
    engine: Counts & {
      certainty_accuracy: number | null;
      citation_accuracy: number | null;
      false_confirmed: number;
    };
    baseline: Counts;
    changes: {
      detection_precision: number | null;
      detection_recall: number | null;
      classification_accuracy: number | null;
    };
    unsupported_impacts: number;
    ms_per_document: { median: number | null };
  };
  by_split: Record<string, { engine: Counts; baseline: Counts }>;
  cases: CaseScore[];
};

const fmt = (v: number | null) => (v === null ? "n/a" : v.toFixed(2));

export default function Page() {
  const { aggregate: a } = result;
  const rows: [string, { engine: Counts; baseline: Counts }][] = [
    ...Object.entries(result.by_split),
    ["all", a],
  ];

  return (
    <>
      <h1>Benchmark</h1>
      <p className="lede">
        Dataset {result.dataset.version}: {result.dataset.cases} synthetic cases. The engine is compared with
        keyword retrieval, which lists every other entity whose text contains the changed entity&apos;s name.
        The numbers below come from the stored result file, run on {result.run.date.slice(0, 10)}
        {result.run.commit ? ` at commit ${result.run.commit}` : ""}.
      </p>

      <Limits heldoutExpected={result.by_split.heldout?.engine.expected ?? null} />

      <section className="section" aria-labelledby="impact-table">
        <h2 id="impact-table">Finding the dependents of a change</h2>
        <table className="ledger">
          <caption className="sr-only">Precision and recall of each system by dataset split</caption>
          <thead>
            <tr>
              <th scope="col">Split</th>
              <th scope="col">System</th>
              <th scope="col">Precision</th>
              <th scope="col">Recall</th>
              <th scope="col">Reported</th>
              <th scope="col">Expected</th>
            </tr>
          </thead>
          <tbody>
            {rows.flatMap(([split, agg]) =>
              (["engine", "baseline"] as const).map((system) => (
                <tr key={`${split}-${system}`}>
                  <td>{split}</td>
                  <td>{system === "engine" ? "SpecTrace" : "Keyword baseline"}</td>
                  <td className="mono">{fmt(agg[system].precision)}</td>
                  <td className="mono">{fmt(agg[system].recall)}</td>
                  <td className="mono">{agg[system].reported}</td>
                  <td className="mono">{agg[system].expected}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </section>

      <section className="section" aria-labelledby="claims">
        <h2 id="claims">Checks on the evidence</h2>
        <dl className="facts">
          <div>
            <dt>Confirmed claims that the labels call inferred or wrong</dt>
            <dd className="mono">{a.engine.false_confirmed}</dd>
          </div>
          <div>
            <dt>Impacts without a valid evidence path</dt>
            <dd className="mono">{a.unsupported_impacts}</dd>
          </div>
          <div>
            <dt>Certainty label correct, among dependents found</dt>
            <dd className="mono">{fmt(a.engine.certainty_accuracy)}</dd>
          </div>
          <div>
            <dt>Cited line correct, among dependents found</dt>
            <dd className="mono">{fmt(a.engine.citation_accuracy)}</dd>
          </div>
          <div>
            <dt>Changes detected: precision / recall</dt>
            <dd className="mono">
              {fmt(a.changes.detection_precision)} / {fmt(a.changes.detection_recall)}
            </dd>
          </div>
          <div>
            <dt>Changes classified correctly</dt>
            <dd className="mono">{fmt(a.changes.classification_accuracy)}</dd>
          </div>
          <div>
            <dt>Median analysis time per document</dt>
            <dd className="mono">{a.ms_per_document.median === null ? "n/a" : `${a.ms_per_document.median} ms`}</dd>
          </div>
        </dl>
      </section>

      <section className="section" aria-labelledby="cases">
        <h2 id="cases">Case by case</h2>
        <table className="ledger">
          <caption className="sr-only">Dependents found out of dependents expected, for each case</caption>
          <thead>
            <tr>
              <th scope="col">Case</th>
              <th scope="col">Split</th>
              <th scope="col">SpecTrace found</th>
              <th scope="col">Baseline found</th>
              <th scope="col">Wrongly reported by baseline</th>
            </tr>
          </thead>
          <tbody>
            {result.cases.map((c) => (
              <tr key={c.id}>
                <td className="mono">{c.id}</td>
                <td>{c.split}</td>
                <td className="mono">
                  {c.engine.true_positive} of {c.engine.expected}
                </td>
                <td className="mono">
                  {c.baseline.true_positive} of {c.baseline.expected}
                </td>
                <td className="mono">{c.baseline.extra.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

function Limits({ heldoutExpected }: { heldoutExpected: number | null }) {
  return (
    <div className="notice notice--empty" role="note">
      <p className="notice__title">Read these numbers with the limits in mind</p>
      <p className="notice__body">
        The labels were written by the engine&apos;s authors, before the first run, and no
        person has reviewed them. The cases are synthetic and few: the held-out split has{" "}
        {heldoutExpected ?? "few"} labeled dependents, so a single error moves its recall by several
        points. The engine was not tuned on this data. The
        keyword baseline was corrected once after the first run because it ignored names preceded by a
        slash; the engine was not changed.
      </p>
    </div>
  );
}
