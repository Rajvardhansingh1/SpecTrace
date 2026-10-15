import type { Edge, Impact } from "./types";

const edgeId = (e: Edge) => `${e.source_key}\u0000${e.target_key}\u0000${e.relation}`;

/**
 * The engine merges the edges of both versions and lets version B win, so an edge present in B
 * was cited from B's files; any other edge (for example one that points at a removed entity)
 * was cited from A's files.
 */
export function versionResolver(edgesB: Edge[]): (edge: Edge) => "a" | "b" {
  const inB = new Set(edgesB.map(edgeId));
  return (edge) => (inB.has(edgeId(edge)) ? "b" : "a");
}

/** Hops ordered from the impacted entity down to the changed one, the way a reader follows them. */
export function hopsFromImpacted(impact: Impact): Edge[] {
  return [...impact.path].reverse();
}

export const citation = (edge: Edge) => `${edge.evidence.file}:${edge.evidence.line_start}`;
