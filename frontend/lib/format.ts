import { ApiError } from "./api";
import { LIMITS } from "./files";
import type { Change, ChangeType, Classification, Impact } from "./types";

export const CLASSIFICATION_LABEL: Record<Classification, string> = {
  breaking: "Breaking",
  unknown: "Needs review",
  non_breaking: "Non-breaking",
  documentation: "Documentation only",
};

/** Most urgent first. */
export const CLASSIFICATION_ORDER: Classification[] = [
  "breaking",
  "unknown",
  "non_breaking",
  "documentation",
];

export const CHANGE_TYPE_LABEL: Record<ChangeType, string> = {
  added: "Added",
  removed: "Removed",
  modified: "Modified",
};

const RELATION_LABEL: Record<string, string> = {
  uses_schema: "uses schema",
  mentions_endpoint: "mentions endpoint",
  links_to: "links to",
  mentions_requirement: "mentions requirement",
  mentions_name: "names",
  similar_properties: "has matching keys with",
};

export const relationLabel = (relation: string) => RELATION_LABEL[relation] ?? relation;

export const percent = (value: number) => `${Math.round(value * 100)}%`;

export function sortChanges(changes: Change[]): Change[] {
  return [...changes].sort(
    (a, b) =>
      CLASSIFICATION_ORDER.indexOf(a.classification) -
        CLASSIFICATION_ORDER.indexOf(b.classification) || a.key.localeCompare(b.key),
  );
}

export function summarize(changes: Change[], impacts: Record<string, Impact[]>) {
  const all = Object.values(impacts).flat();
  return {
    changes: changes.length,
    breaking: changes.filter((c) => c.classification === "breaking").length,
    impacts: all.length,
    confirmed: all.filter((i) => i.certainty === "confirmed").length,
    inferred: all.filter((i) => i.certainty === "inferred").length,
  };
}

/** Plain-language text for an API failure: what happened and what to do. */
export function describeError(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something unexpected went wrong. Try again.";
  switch (error.code) {
    case "network":
      return "The SpecTrace API could not be reached. Check that the backend is running and that NEXT_PUBLIC_API_URL points to it.";
    case "timeout":
      return "The API took longer than 30 seconds to answer. Try smaller inputs.";
    case "rate_limited":
      return error.retryAfter
        ? `Too many requests. Try again in ${error.retryAfter} seconds.`
        : "Too many requests. Wait a minute and try again.";
    case "input_too_large":
      return `The input is too large. Limits are ${LIMITS.maxFileBytes / 1_000_000} MB per file and ${LIMITS.maxTotalBytes / 1_000_000} MB per version.`;
    case "unsupported_input":
      return "A file name is not allowed (absolute paths and .. are rejected) or a file type is not supported.";
    case "limit_exceeded":
      return "A file is too deeply nested or has too many entries to analyze safely.";
    case "parse_error":
      return "A YAML or JSON file could not be read. Check its syntax.";
    case "invalid_request":
      return "The request was not valid. Check the version names and files.";
    case "not_found":
      return "That comparison does not exist. It may have been removed.";
    case "internal_error":
      return "The API hit an internal error. Try again; if it repeats, report the request id from the server log.";
    default:
      return "The API rejected the request.";
  }
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
