import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AskPanel } from "@/components/AskPanel";
import { RunView } from "@/components/RunView";
import { GeneratedText, Sources } from "@/components/Sources";
import { SummaryPanel } from "@/components/SummaryPanel";
import { ApiError } from "@/lib/api";
import { ownerToken, resetOwnerTokenCache } from "@/lib/owner";
import type { Answer, Capabilities, Citation, Generated, Narrative } from "@/lib/types";
import { impact, run } from "./fixtures";

const api = vi.hoisted(() => ({
  createNarrative: vi.fn(),
  askRun: vi.fn(),
  getRun: vi.fn(),
  getCapabilities: vi.fn(),
  getSnippet: vi.fn(),
}));
vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()), ...api }));

const citation = (over: Partial<Citation> = {}): Citation => ({
  id: "C1",
  kind: "change",
  title: "schema:Pet",
  text: "schema:Pet was modified. Classification: breaking.",
  file: "openapi.yaml",
  line_start: 69,
  line_end: 78,
  version: "b",
  via: "graph",
  similarity: null,
  ...over,
});

const part = (over: Partial<Generated> = {}): Generated => ({
  status: "answered",
  text: "Pet.id became an integer [C1].",
  citations: [citation()],
  warnings: [],
  truncated: false,
  ...over,
});

const narrative = (over: Partial<Narrative> = {}): Narrative => ({
  version_a: part({ text: "Version one describes pets [C1]." }),
  version_b: part({ text: "Version two describes pets [C1]." }),
  changes: part(),
  model: "provider/model-x",
  sent_to: ["OpenRouter"],
  generated_at: "2026-10-17T10:00:00+00:00",
  ...over,
});

const caps = (over: Partial<Capabilities> = {}): Capabilities => ({
  llm: { enabled: true, model: "provider/model-x" },
  embeddings: { enabled: true, model: "emb" },
  sends_documents_to: ["OpenRouter"],
  ...over,
});

const answer = (over: Partial<Answer> = {}): Answer => ({
  status: "answered",
  matched: [],
  impacts: [],
  reason: "r",
  answer: "Update the guide [C1].",
  citations: [citation()],
  generated: true,
  model: "provider/model-x",
  warnings: [],
  truncated: false,
  retrieval: { chunks: 20, semantic: true, items: 3 },
  ...over,
});

const versionOf = () => "b" as const;

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  resetOwnerTokenCache();
  api.getCapabilities.mockResolvedValue(caps());
});

describe("owner token", () => {
  it("is random, valid for the API, stored, and reused", () => {
    const first = ownerToken();
    expect(first).toMatch(/^[A-Za-z0-9_-]{16,128}$/);
    expect(window.localStorage.getItem("spectrace-owner")).toBe(first);
    resetOwnerTokenCache();
    expect(ownerToken()).toBe(first);
  });

  it("differs between browsers", () => {
    const a = ownerToken();
    window.localStorage.clear();
    resetOwnerTokenCache();
    expect(ownerToken()).not.toBe(a);
  });

  it("replaces a stored value that the API would reject", () => {
    window.localStorage.setItem("spectrace-owner", "short");
    expect(ownerToken()).toMatch(/^[A-Za-z0-9_-]{16,128}$/);
  });

  it("still works, with one token per page visit, when storage is blocked", () => {
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const token = ownerToken();
    expect(token).toMatch(/^[A-Za-z0-9_-]{16,128}$/);
    expect(ownerToken()).toBe(token);
    get.mockRestore();
    set.mockRestore();
  });
});

describe("generated text and sources", () => {
  it("shows citation markers as labels, not links", () => {
    const { container } = render(
      <p>
        <GeneratedText text="Pet changed [C1] and the guide [C2] is stale." />
      </p>,
    );
    expect([...container.querySelectorAll(".cite")].map((e) => e.textContent)).toEqual(["[C1]", "[C2]"]);
    expect(container.querySelector("a")).toBeNull();
    expect(container).toHaveTextContent("Pet changed [C1] and the guide [C2] is stale.");
  });

  it("lists each source with its location and how it was found, and reveals the exact text", async () => {
    render(
      <Sources
        citations={[
          citation(),
          citation({ id: "C2", kind: "chunk", title: "section:docs/g.md#a", text: "Call GET /pets.", file: "docs/g.md", line_start: 4, line_end: 4, via: "both" }),
        ]}
      />,
    );
    const list = screen.getByRole("list", { name: "Sources" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("[C1] schema:Pet at openapi.yaml:69-78 (dependency graph)");
    expect(items[1]).toHaveTextContent("at docs/g.md:4 (keyword and meaning match)");
    await userEvent.click(within(items[1]).getByText(/section:docs/));
    expect(within(items[1]).getByText("Call GET /pets.")).toBeVisible();
  });

  it("renders nothing for no sources and copes with a source that has no location", () => {
    const { container, rerender } = render(<Sources citations={[]} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<Sources citations={[citation({ file: null, line_start: null, line_end: null, via: null })]} />);
    expect(screen.getByRole("listitem")).toHaveTextContent("[C1] schema:Pet");
    expect(screen.getByRole("listitem")).not.toHaveTextContent(" at ");
  });
});

describe("summary panel", () => {
  const panel = (over: Partial<React.ComponentProps<typeof SummaryPanel>> = {}) =>
    render(<SummaryPanel runId="r" labelA="v1" labelB="v2" capabilities={caps()} {...over} />);

  it("says it is off, without offering a button, when no model is configured", () => {
    panel({ capabilities: caps({ llm: { enabled: false, model: null }, sends_documents_to: [] }) });
    expect(screen.getByText(/no language model is configured/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Summarize/ })).toBeNull();
  });

  it("names who receives the documents before anything is sent, and waits for the click", () => {
    panel();
    expect(screen.getByText("Writing the summary sends the text of both versions to OpenRouter.")).toBeInTheDocument();
    expect(api.createNarrative).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Summarize both versions" })).toHaveAccessibleDescription(
      /sends the text of both versions to OpenRouter/,
    );
  });

  it("says nothing leaves the server when the model is local", () => {
    panel({ capabilities: caps({ sends_documents_to: [] }) });
    expect(screen.getByText(/No document text is sent to a third party/)).toBeInTheDocument();
  });

  it("writes the summary on request and shows each part with its sources", async () => {
    api.createNarrative.mockResolvedValue(narrative());
    panel();
    await userEvent.click(screen.getByRole("button", { name: "Summarize both versions" }));
    expect(api.createNarrative).toHaveBeenCalledWith("r", false);
    for (const title of ["What changed", "Version v1", "Version v2"]) {
      expect(await screen.findByRole("region", { name: title })).toBeInTheDocument();
    }
    const changes = screen.getByRole("region", { name: "What changed" });
    // The marker appears in the text and again at the head of its source.
    expect(within(changes).getAllByText("[C1]", { selector: ".cite" })).toHaveLength(2);
    expect(within(changes).getByRole("list", { name: "Sources for What changed" })).toBeInTheDocument();
    expect(screen.getByText(/Written by/)).toHaveTextContent("provider/model-x");
    expect(screen.queryByRole("button", { name: "Summarize both versions" })).toBeNull();
  });

  it("shows a loading state while the model works", async () => {
    let finish: (n: Narrative) => void = () => undefined;
    api.createNarrative.mockReturnValue(new Promise<Narrative>((ok) => (finish = ok)));
    panel();
    await userEvent.click(screen.getByRole("button", { name: "Summarize both versions" }));
    expect(screen.getByRole("status")).toHaveTextContent("Writing the summary");
    expect(screen.getByRole("button", { name: "Writing the summary..." })).toBeDisabled();
    finish(narrative());
    expect(await screen.findByRole("region", { name: "What changed" })).toBeInTheDocument();
  });

  it("explains a failure and lets the reader try again", async () => {
    api.createNarrative.mockRejectedValueOnce(new ApiError("llm_rate_limited", 429, "x"));
    panel();
    await userEvent.click(screen.getByRole("button", { name: "Summarize both versions" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("service is busy");
    api.createNarrative.mockResolvedValueOnce(narrative());
    await userEvent.click(screen.getByRole("button", { name: "Summarize both versions" }));
    expect(await screen.findByRole("region", { name: "What changed" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a saved summary at once and can write it again", async () => {
    panel({ initial: narrative() });
    expect(screen.getByRole("region", { name: "What changed" })).toBeInTheDocument();
    api.createNarrative.mockResolvedValue(narrative({ model: "second-model" }));
    await userEvent.click(screen.getByRole("button", { name: "Write it again" }));
    expect(api.createNarrative).toHaveBeenCalledWith("r", true);
    await waitFor(() => expect(screen.getByText(/Written by/)).toHaveTextContent("second-model"));
  });

  it("shows a withheld part as plain muted text, and says when the input was cut", () => {
    panel({
      initial: narrative({
        changes: part({ status: "uncertain", text: "The model's reply could not be checked.", citations: [] }),
        version_a: part({ truncated: true, warnings: ["Removed a citation to C9."] }),
      }),
    });
    const changes = screen.getByRole("region", { name: "What changed" });
    expect(within(changes).getByText(/could not be checked/)).toHaveClass("muted");
    const a = screen.getByRole("region", { name: "Version v1" });
    expect(within(a).getByText(/Only part of the documents fit/)).toBeInTheDocument();
    expect(within(a).getByText("Removed a citation to C9.")).toBeInTheDocument();
  });

  it("keeps the saved summary even if the server reports no model any more", () => {
    panel({ capabilities: caps({ llm: { enabled: false, model: null } }), initial: narrative() });
    expect(screen.getByRole("region", { name: "What changed" })).toBeInTheDocument();
  });
});

describe("ask panel with a model", () => {
  const panel = (c: Capabilities | null = caps()) =>
    render(<AskPanel runId="r" versionOf={versionOf} capabilities={c} />);

  it("invites free-form questions and discloses where the text goes", () => {
    panel();
    expect(screen.getByText(/Ask in your own words/)).toHaveTextContent("sent to OpenRouter");
    expect(screen.getByLabelText("Question")).toHaveAttribute("placeholder", expect.stringContaining("docs need"));
  });

  it("shows a generated answer with its sources and the graph evidence beneath", async () => {
    api.askRun.mockResolvedValue(answer({ impacts: [impact()] }));
    panel();
    await userEvent.type(screen.getByLabelText("Question"), "What should I update?{enter}");
    expect(await screen.findByRole("heading", { name: "Answer" })).toBeInTheDocument();
    expect(screen.getByText(/Update the guide/)).toBeInTheDocument();
    expect(screen.getByText(/Written by/)).toHaveTextContent("provider/model-x");
    expect(screen.getByRole("list", { name: "Sources" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Dependents found in the dependency graph" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Show source at/ }).length).toBeGreaterThan(0);
  });

  it("says when only keywords were used, when warnings exist, and when text was left out", async () => {
    api.askRun.mockResolvedValue(
      answer({ retrieval: { chunks: 5, semantic: false, items: 2 }, warnings: ["Semantic search was unavailable; keywords were used."], truncated: true }),
    );
    panel();
    await userEvent.type(screen.getByLabelText("Question"), "x{enter}");
    expect(await screen.findByText(/found by keywords only/)).toBeInTheDocument();
    expect(screen.getByText(/Semantic search was unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/did not fit in the prompt/)).toBeInTheDocument();
  });

  it("shows an abstention as muted text with no sources", async () => {
    api.askRun.mockResolvedValue(
      answer({ status: "uncertain", answer: "The documents do not say.", citations: [] }),
    );
    panel();
    await userEvent.type(screen.getByLabelText("Question"), "x{enter}");
    expect(await screen.findByRole("heading", { name: "Not enough to answer" })).toBeInTheDocument();
    expect(screen.getByText("The documents do not say.").closest("p")).toHaveClass("muted");
    expect(screen.queryByRole("list", { name: "Sources" })).toBeNull();
  });

  it("explains a model failure and keeps the box usable", async () => {
    api.askRun.mockRejectedValue(new ApiError("budget_exceeded", 429, "x"));
    panel();
    await userEvent.type(screen.getByLabelText("Question"), "x{enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("limit for language-model requests");
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });
});

describe("ask panel without a model", () => {
  it("says it matches names and shows the plain answer", async () => {
    api.askRun.mockResolvedValue(
      answer({ generated: false, answer: null, citations: [], model: null, retrieval: null, reason: "Impacts are listed.", matched: ["schema:Pet"], impacts: [impact()] }),
    );
    render(<AskPanel runId="r" versionOf={versionOf} capabilities={caps({ llm: { enabled: false, model: null }, sends_documents_to: [] })} />);
    expect(screen.getByText(/matches names only/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Question"), "Pet{enter}");
    expect(await screen.findByRole("heading", { name: "Impacts found" })).toBeInTheDocument();
    expect(screen.getByText("Impacts are listed.")).toBeInTheDocument();
    expect(screen.queryByText(/Written by/)).toBeNull();
  });

  it("behaves like the name-matching panel while capabilities are still unknown", () => {
    render(<AskPanel runId="r" versionOf={versionOf} />);
    expect(screen.getByText(/matches names only/)).toBeInTheDocument();
  });
});

describe("run view and capabilities", () => {
  it("shows the summary controls when the server has a model", async () => {
    api.getRun.mockResolvedValue(run());
    render(<RunView id="r" />);
    expect(await screen.findByRole("button", { name: "Summarize both versions" })).toBeInTheDocument();
  });

  it("hides them, and still works, when capabilities cannot be read", async () => {
    api.getCapabilities.mockRejectedValue(new ApiError("network", 0, "x"));
    api.getRun.mockResolvedValue(run());
    render(<RunView id="r" />);
    expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Summarize both versions" })).toBeDisabled();
  });

  it("shows a summary that was saved with the run", async () => {
    const saved = run();
    saved.result = { ...saved.result!, narrative: narrative() };
    api.getRun.mockResolvedValue(saved);
    render(<RunView id="r" />);
    expect(await screen.findByRole("region", { name: "What changed" })).toBeInTheDocument();
  });
});
