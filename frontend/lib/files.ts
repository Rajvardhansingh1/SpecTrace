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

/** Directories that are never documentation. Skipping them keeps a dropped project folder fast. */
const IGNORED_DIRS = new Set(["node_modules", ".git"]);
export const MAX_DROPPED_FILES = 1000;

export interface Dropped {
  files: File[];
  /** True when a directory was dropped, so its own name is dropped from the paths. */
  fromFolder: boolean;
  notes: string[];
}

const asFile = (entry: FileSystemFileEntry) =>
  new Promise<File>((ok, fail) => entry.file(ok, fail));

const readBatch = (reader: FileSystemDirectoryReader) =>
  new Promise<FileSystemEntry[]>((ok, fail) => reader.readEntries(ok, fail));

async function walk(entry: FileSystemEntry, out: File[], notes: string[]): Promise<void> {
  if (out.length >= MAX_DROPPED_FILES) return;
  if (entry.isFile) {
    const file = await asFile(entry as FileSystemFileEntry);
    // A File cannot be given a path, so a copy carries it the way a folder picker would.
    const copy = new File([file], file.name, { type: file.type });
    Object.defineProperty(copy, "webkitRelativePath", { value: entry.fullPath.replace(/^\/+/, "") });
    out.push(copy);
    return;
  }
  if (!entry.isDirectory || IGNORED_DIRS.has(entry.name)) return;
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  // readEntries returns at most about 100 entries per call, so it is called until it is empty.
  for (let batch = await readBatch(reader); batch.length > 0; batch = await readBatch(reader)) {
    for (const child of batch) await walk(child, out, notes);
    if (out.length >= MAX_DROPPED_FILES) {
      if (notes.length === 0) notes.push(`only the first ${MAX_DROPPED_FILES} files were read`);
      return;
    }
  }
}

/**
 * Reads what was dropped, including folders. The entries must be taken from the event before the
 * first await, because the browser empties the drop data once the event handler returns.
 */
export async function collectDropped(data: DataTransfer): Promise<Dropped> {
  const entries = Array.from(data.items ?? [])
    .filter((item) => item.kind === "file")
    .map((item) => item.webkitGetAsEntry?.() ?? null)
    .filter((entry): entry is FileSystemEntry => entry !== null);
  const plain = Array.from(data.files ?? []);

  if (entries.length === 0) return { files: plain, fromFolder: false, notes: [] };
  const files: File[] = [];
  const notes: string[] = [];
  for (const entry of entries) await walk(entry, files, notes);
  return { files, fromFolder: entries.some((e) => e.isDirectory), notes };
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
