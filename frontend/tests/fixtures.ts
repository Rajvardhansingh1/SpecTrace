import type { Change, Edge, Impact, RunDetail, RunResult } from "@/lib/types";

const loc = (file: string, line: number) => ({ file, line_start: line, line_end: line });

export const edge = (over: Partial<Edge> = {}): Edge => ({
  source_key: "section:docs/guide.md#listing",
  target_key: "endpoint:GET /pets",
  relation: "mentions_endpoint",
  label: "confirmed",
  confidence: 1,
  evidence: loc("docs/guide.md", 4),
  reason: "mentions GET /pets",
  ...over,
});

export const change = (over: Partial<Change> = {}): Change => ({
  key: "schema:Pet",
  kind: "schema",
  change_type: "modified",
  classification: "breaking",
  reasons: ["property id type changed string -> integer"],
  source_diff: "--- A:openapi.yaml:2\n+++ B:openapi.yaml:2\n@@ -1,2 +1,2 @@\n context\n-  type: string\n+  type: integer",
  before: loc("openapi.yaml", 2),
  after: loc("openapi.yaml", 2),
  ...over,
});

export const impact = (over: Partial<Impact> = {}): Impact => {
  const second = edge({
    source_key: "endpoint:GET /pets",
    target_key: "schema:Pet",
    relation: "uses_schema",
    reason: "$ref to #/components/schemas/Pet",
    evidence: loc("openapi.yaml", 12),
  });
  return {
    change_key: "schema:Pet",
    impacted_key: "section:docs/guide.md#listing",
    certainty: "confirmed",
    confidence: 1,
    path: [second, edge()],
    confirmed_breaking: true,
    summary: "s",
    ...over,
  };
};

export function result(over: Partial<RunResult> = {}): RunResult {
  const inferred = impact({
    impacted_key: "requirement:REQ-001",
    certainty: "inferred",
    confidence: 0.8,
    confirmed_breaking: false,
    path: [
      edge({
        source_key: "requirement:REQ-001",
        target_key: "schema:Pet",
        relation: "mentions_name",
        label: "inferred",
        confidence: 0.8,
        reason: "backticked identifier `Pet` equals a schema name",
        evidence: loc("docs/guide.md", 9),
      }),
    ],
  });
  return {
    changes: [
      change({ key: "section:docs/a.md#intro", kind: "section", classification: "documentation", reasons: ["text changed"], source_diff: "" }),
      change(),
      change({ key: "endpoint:GET /new", kind: "endpoint", change_type: "added", classification: "non_breaking", reasons: ["endpoint added"] }),
    ],
    impacts: { "schema:Pet": [impact(), inferred], "section:docs/a.md#intro": [] },
    graph: { entities: [], edges_a: [], edges_b: [edge()] },
    unsupported: ["notes.pdf: unsupported file type"],
    warnings: [],
    stats: { entities_a: 7, entities_b: 7, elapsed_ms: 12.4 },
    ...over,
  };
}

export const run = (over: Partial<RunDetail> = {}): RunDetail => ({
  id: "11111111-1111-4111-8111-111111111111",
  status: "done",
  label_a: "v1",
  label_b: "v2",
  created_at: "2026-10-16T10:00:00+00:00",
  finished_at: "2026-10-16T10:00:01+00:00",
  error_code: null,
  result: result(),
  ...over,
});
