import type { VersionFiles } from "./types";

/** Mirrors the backend limits so problems show up before an upload. */
export const LIMITS = { maxFiles: 200, maxFileBytes: 1_000_000, maxTotalBytes: 5_000_000 };

export const ACCEPT = ".yaml,.yml,.json,.md,.markdown,.txt";
const SUPPORTED = new Set(ACCEPT.split(",").map((e) => e.slice(1)));

const encoder = new TextEncoder();
export const byteLength = (text: string) => encoder.encode(text).length;

/**
 * Uses forward slashes and no leading "./". A picked folder keeps its own name as the first
 * path segment ("v1/docs/guide.md"); that segment is dropped so two versions line up.
 */
export function normalizeName(name: string, fromFolder: boolean): string {
  let parts = name.replace(/\\/g, "/").split("/").filter((p) => p !== "" && p !== ".");
  if (fromFolder && parts.length > 1) parts = parts.slice(1);
  return parts.join("/");
}

export function isSupported(name: string): boolean {
  const dot = name.lastIndexOf(".");
  return dot > 0 && SUPPORTED.has(name.slice(dot + 1).toLowerCase());
}

export interface ReadResult {
  files: VersionFiles;
  skipped: string[];
}

export async function readFiles(list: Iterable<File>, fromFolder: boolean): Promise<ReadResult> {
  const files: VersionFiles = {};
  const skipped: string[] = [];
  for (const file of list) {
    const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
    const name = normalizeName(relative || file.name, fromFolder && Boolean(relative));
    if (!name || !isSupported(name)) {
      skipped.push(`${name || file.name}: unsupported file type`);
      continue;
    }
    if (file.size > LIMITS.maxFileBytes) {
      skipped.push(`${name}: larger than ${LIMITS.maxFileBytes / 1_000_000} MB`);
      continue;
    }
    files[name] = await file.text();
  }
  return { files, skipped };
}

export function totalBytes(files: VersionFiles): number {
  return Object.values(files).reduce((sum, text) => sum + byteLength(text), 0);
}

/** Returns a message when a version cannot be submitted, or null when it can. */
export function checkVersion(label: string, files: VersionFiles): string | null {
  const count = Object.keys(files).length;
  if (count === 0) return `Add at least one file to ${label}.`;
  if (count > LIMITS.maxFiles) return `${label} has more than ${LIMITS.maxFiles} files.`;
  if (totalBytes(files) > LIMITS.maxTotalBytes) {
    return `${label} is larger than ${LIMITS.maxTotalBytes / 1_000_000} MB in total.`;
  }
  return null;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1000) return `${bytes} B`;
  if (bytes < 1_000_000) return `${(bytes / 1000).toFixed(1)} kB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}
