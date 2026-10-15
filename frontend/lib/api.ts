import type {
  Answer,
  CreatedRun,
  RunDetail,
  RunSummary,
  Snippet,
  VersionFiles,
} from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);

const TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryAfter: number | null;

  constructor(code: string, status: number, message: string, retryAfter: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("timeout", 0, "The request timed out.");
    }
    throw new ApiError("network", 0, "The API could not be reached.");
  } finally {
    clearTimeout(timer);
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    if (response.ok) throw new ApiError("bad_response", response.status, "Unreadable response.");
  }

  if (!response.ok) {
    const envelope = (body as { error?: { code?: unknown; message?: unknown } } | null)?.error;
    const code = typeof envelope?.code === "string" ? envelope.code : "unknown";
    const message = typeof envelope?.message === "string" ? envelope.message : "Request failed.";
    const retry = Number(response.headers.get("retry-after"));
    throw new ApiError(code, response.status, message, Number.isFinite(retry) && retry > 0 ? retry : null);
  }
  return body as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function createRun(input: {
  files_a: VersionFiles;
  files_b: VersionFiles;
  label_a: string;
  label_b: string;
}): Promise<CreatedRun> {
  return request<CreatedRun>("/v1/runs", json(input));
}

export async function listRuns(): Promise<RunSummary[]> {
  return (await request<{ runs: RunSummary[] }>("/v1/runs")).runs;
}

export function getRun(id: string): Promise<RunDetail> {
  return request<RunDetail>(`/v1/runs/${encodeURIComponent(id)}`);
}

export function askRun(id: string, question: string): Promise<Answer> {
  return request<Answer>(`/v1/runs/${encodeURIComponent(id)}/ask`, json({ question }));
}

export function getSnippet(
  id: string,
  version: "a" | "b",
  file: string,
  line: number,
  context = 2,
): Promise<Snippet> {
  const query = new URLSearchParams({ version, file, line: String(line), context: String(context) });
  return request<Snippet>(`/v1/runs/${encodeURIComponent(id)}/snippet?${query}`);
}
