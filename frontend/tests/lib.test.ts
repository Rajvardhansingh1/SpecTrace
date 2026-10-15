import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, askRun, createRun, getRun, getSnippet, listRuns } from "@/lib/api";
import { diffStats, parseDiff } from "@/lib/diff";
import { citation, hopsFromImpacted, versionResolver } from "@/lib/evidence";
import {
  LIMITS,
  checkVersion,
  formatBytes,
  isSupported,
  normalizeName,
  readFiles,
  totalBytes,
} from "@/lib/files";
import { describeError, percent, relationLabel, sortChanges, summarize } from "@/lib/format";
import { change, edge, impact, result } from "./fixtures";

describe("files", () => {
  it("normalizes separators and drops the picked folder's own name", () => {
    expect(normalizeName("docs\\guide.md", false)).toBe("docs/guide.md");
    expect(normalizeName("./docs//guide.md", false)).toBe("docs/guide.md");
    expect(normalizeName("v1/docs/guide.md", true)).toBe("docs/guide.md");
    expect(normalizeName("guide.md", true)).toBe("guide.md");
  });

  it("accepts only the supported extensions, ignoring case", () => {
    for (const n of ["a.yaml", "a.YML", "a.json", "a.md", "a.markdown", "a.txt"]) {
      expect(isSupported(n)).toBe(true);
    }
    for (const n of ["a.pdf", "a", ".md", "a.md.exe"]) expect(isSupported(n)).toBe(false);
  });

  it("reads files, skipping unsupported and oversized ones with a reason", async () => {
    const ok = new File(["# hi"], "guide.md");
    const bad = new File(["x"], "image.png");
    const big = new File(["x".repeat(LIMITS.maxFileBytes + 1)], "huge.md");
    const { files, skipped } = await readFiles([ok, bad, big], false);
    expect(Object.keys(files)).toEqual(["guide.md"]);
    expect(files["guide.md"]).toBe("# hi");
    expect(skipped).toHaveLength(2);
    expect(skipped.join(" ")).toMatch(/image\.png: unsupported/);
    expect(skipped.join(" ")).toMatch(/huge\.md: larger than 1 MB/);
  });

  it("uses the relative path of a picked folder", async () => {
    const file = new File(["a"], "guide.md");
    Object.defineProperty(file, "webkitRelativePath", { value: "v1/docs/guide.md" });
    const { files } = await readFiles([file], true);
    expect(Object.keys(files)).toEqual(["docs/guide.md"]);
  });

  it("validates a version before upload", () => {
    expect(checkVersion("version A", {})).toBe("Add at least one file to version A.");
    expect(checkVersion("version A", { "a.md": "x" })).toBeNull();
    const many = Object.fromEntries(Array.from({ length: LIMITS.maxFiles + 1 }, (_, i) => [`f${i}.md`, ""]));
    expect(checkVersion("version B", many)).toMatch(/more than 200 files/);
    const heavy = { "a.md": "é".repeat(LIMITS.maxTotalBytes) };
    expect(totalBytes(heavy)).toBeGreaterThan(LIMITS.maxTotalBytes);
    expect(checkVersion("version B", heavy)).toMatch(/larger than 5 MB/);
  });

  it("formats sizes", () => {
    expect(formatBytes(12)).toBe("12 B");
    expect(formatBytes(1500)).toBe("1.5 kB");
    expect(formatBytes(2_500_000)).toBe("2.5 MB");
  });
});

describe("diff", () => {
  it("classifies lines and keeps the marker characters", () => {
    const lines = parseDiff("--- A:x:1\n+++ B:x:1\n@@ -1 +1 @@\n ctx\n-old\n+new");
    expect(lines.map((l) => l.kind)).toEqual(["file", "file", "hunk", "context", "del", "add"]);
    expect(lines[4].text).toBe("-old");
    expect(diffStats(lines)).toEqual({ added: 1, removed: 1 });
  });

  it("returns nothing for an empty diff", () => {
    expect(parseDiff("")).toEqual([]);
    expect(parseDiff("  \n")).toEqual([]);
  });
});

describe("evidence", () => {
  it("cites the version whose edges contain the hop, with B winning", () => {
    const inB = edge();
    const onlyInA = edge({ source_key: "x", target_key: "y" });
    const resolve = versionResolver([inB]);
    expect(resolve(inB)).toBe("b");
    expect(resolve(onlyInA)).toBe("a");
  });

  it("orders hops from the impacted entity to the change", () => {
    const hops = hopsFromImpacted(impact());
    expect(hops[0].source_key).toBe("section:docs/guide.md#listing");
    expect(hops[hops.length - 1].target_key).toBe("schema:Pet");
    expect(citation(hops[0])).toBe("docs/guide.md:4");
  });
});

describe("format", () => {
  it("sorts changes most urgent first, then by key", () => {
    const sorted = sortChanges(result().changes).map((c) => c.classification);
    expect(sorted).toEqual(["breaking", "non_breaking", "documentation"]);
  });

  it("summarizes counts", () => {
    const r = result();
    expect(summarize(r.changes, r.impacts)).toEqual({
      changes: 3,
      breaking: 1,
      impacts: 2,
      confirmed: 1,
      inferred: 1,
    });
  });

  it("turns each API failure into a sentence with a next step", () => {
    const codes = [
      "network",
      "timeout",
      "rate_limited",
      "input_too_large",
      "unsupported_input",
      "limit_exceeded",
      "parse_error",
      "invalid_request",
      "not_found",
      "internal_error",
      "something_else",
    ];
    const messages = codes.map((c) => describeError(new ApiError(c, 400, "m")));
    expect(new Set(messages).size).toBe(codes.length);
    expect(describeError(new ApiError("rate_limited", 429, "m", 12))).toMatch(/12 seconds/);
    expect(describeError(new Error("boom"))).toMatch(/unexpected/);
    expect(messages.join(" ")).not.toMatch(/—/);
  });

  it("labels relations and percentages", () => {
    expect(relationLabel("uses_schema")).toBe("uses schema");
    expect(relationLabel("brand_new")).toBe("brand_new");
    expect(percent(0.8)).toBe("80%");
  });
});

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  const respond = (body: unknown, init: ResponseInit = {}) =>
    new Response(typeof body === "string" ? body : JSON.stringify(body), {
      headers: { "content-type": "application/json", ...(init.headers ?? {}) },
      ...init,
    });

  it("sends JSON and returns the parsed body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond({ id: "r1", status: "done", stats: {} }, { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const run = await createRun({ files_a: { "a.md": "x" }, files_b: { "a.md": "y" }, label_a: "A", label_b: "B" });
    expect(run.id).toBe("r1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/v1/runs");
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body).label_a).toBe("A");
  });

  it("reads the error envelope and Retry-After", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        respond({ error: { code: "rate_limited", message: "too many requests" } }, { status: 429, headers: { "retry-after": "7" } }),
      ),
    );
    await expect(listRuns()).rejects.toMatchObject({ code: "rate_limited", status: 429, retryAfter: 7 });
  });

  it("maps network failure, non-JSON errors and unreadable success to stable codes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(getRun("x")).rejects.toMatchObject({ code: "network" });

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 })));
    await expect(getRun("x")).rejects.toMatchObject({ code: "unknown", status: 502 });

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not json", { status: 200 })));
    await expect(getRun("x")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("times out after 30 seconds", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init: RequestInit) => {
        return new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        });
      }),
    );
    const pending = expect(listRuns()).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(30_000);
    await pending;
  });

  it("encodes ids and query values", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => respond({ file: "a b.md", version: "a", line: 1, lines: [] }));
    vi.stubGlobal("fetch", fetchMock);
    await getSnippet("id/with slash", "a", "docs/a b.md", 3, 1);
    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://localhost:8000/v1/runs/id%2Fwith%20slash/snippet?version=a&file=docs%2Fa+b.md&line=3&context=1",
    );
    fetchMock.mockImplementation(async () => respond({ status: "uncertain", matched: [], impacts: [], reason: "r" }));
    await askRun("abc", "what?");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ question: "what?" });
  });
});

describe("fixtures stay consistent with the API shape", () => {
  it("has a change for every impact key", () => {
    const r = result();
    for (const key of Object.keys(r.impacts)) expect(r.changes.some((c) => c.key === key)).toBe(true);
    expect(change().reasons.length).toBeGreaterThan(0);
  });
});
