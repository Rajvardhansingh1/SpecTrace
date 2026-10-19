export type Classification = "breaking" | "non_breaking" | "documentation" | "unknown";
export type ChangeType = "added" | "removed" | "modified";
export type Label = "confirmed" | "inferred";
export type RunStatus = "running" | "done" | "failed";

export interface Location {
  file: string;
  line_start: number;
  line_end: number;
}

export interface Change {
  key: string;
  kind: string;
  change_type: ChangeType;
  classification: Classification;
  reasons: string[];
  source_diff: string;
  before: Location | null;
  after: Location | null;
}

export interface Edge {
  source_key: string;
  target_key: string;
  relation: string;
  label: Label;
  confidence: number;
  evidence: Location;
  reason: string;
}

export interface Impact {
  change_key: string;
  impacted_key: string;
  certainty: Label;
  confidence: number;
  /** path[0] points at the changed entity; the last edge starts at the impacted entity. */
  path: Edge[];
  confirmed_breaking: boolean;
  summary: string;
}

export interface GraphEntity {
  key: string;
  kind: string;
  name: string;
  location: Location;
}

export interface Citation {
  id: string;
  kind: "change" | "impact" | "chunk" | "outline";
  title: string;
  text: string;
  file: string | null;
  line_start: number | null;
  line_end: number | null;
  /** "both" when the same passage reads identically in the two versions. */
  version: "a" | "b" | "both" | null;
  via: string | null;
  similarity: number | null;
}

/** Text written by the language model, after the server has checked it against its sources. */
export interface Generated {
  status: "answered" | "uncertain";
  text: string;
  citations: Citation[];
  warnings: string[];
  truncated: boolean;
}

export interface Narrative {
  version_a: Generated;
  version_b: Generated;
  changes: Generated;
  model: string;
  sent_to: string[];
  generated_at: string;
}

export interface Capabilities {
  llm: { enabled: boolean; model: string | null };
  embeddings: { enabled: boolean; model: string | null };
  /** Who receives document text. Empty means nothing leaves the server. */
  sends_documents_to: string[];
}

export interface RunResult {
  narrative?: Narrative;
  changes: Change[];
  impacts: Record<string, Impact[]>;
  graph: { entities: GraphEntity[]; edges_a: Edge[]; edges_b: Edge[] };
  unsupported: string[];
  warnings: string[];
  stats: Record<string, number>;
}

export interface RunSummary {
  id: string;
  status: RunStatus;
  label_a: string;
  label_b: string;
  created_at: string;
  finished_at: string | null;
  error_code: string | null;
}

export interface RunDetail extends RunSummary {
  result: RunResult | null;
}

export interface CreatedRun extends RunSummary {
  stats: Record<string, number>;
}

export interface Answer {
  status: "answered" | "uncertain" | "no_change";
  matched: string[];
  impacts: Impact[];
  reason: string;
  /** Set only when a language model wrote the answer. */
  answer: string | null;
  citations: Citation[];
  generated: boolean;
  model: string | null;
  warnings: string[];
  truncated: boolean;
  retrieval: { chunks: number; semantic: boolean; items: number } | null;
}

export interface Snippet {
  file: string;
  version: "a" | "b";
  line: number;
  lines: { n: number; text: string }[];
}

export type VersionFiles = Record<string, string>;
