import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AskPanel } from "@/components/AskPanel";
import { ChangeDetail } from "@/components/ChangeDetail";
import { ChangeList } from "@/components/ChangeList";
import { CompareForm } from "@/components/CompareForm";
import { HistoryList } from "@/components/HistoryList";
import { ImpactItem } from "@/components/ImpactItem";
import { Notice } from "@/components/Notice";
import { RunView } from "@/components/RunView";
import { CertaintyTag, ClassificationTag } from "@/components/Tags";
import { VersionPane } from "@/components/VersionPane";
import { ApiError } from "@/lib/api";
import { change, impact, result, run } from "./fixtures";

const api = vi.hoisted(() => ({
  createRun: vi.fn(),
  listRuns: vi.fn(),
  getRun: vi.fn(),
  askRun: vi.fn(),
  getSnippet: vi.fn(),
}));
const push = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()), ...api }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

beforeEach(() => {
  vi.clearAllMocks();
  api.listRuns.mockResolvedValue([]);
  Element.prototype.scrollIntoView = vi.fn();
});

const versionOf = () => "b" as const;

describe("tags", () => {
  it("names every classification in words, with its own shape class", () => {
    const { container } = render(
      <>
        <ClassificationTag value="breaking" />
        <ClassificationTag value="unknown" />
        <ClassificationTag value="non_breaking" />
        <ClassificationTag value="documentation" />
      </>,
    );
    for (const text of ["Breaking", "Needs review", "Non-breaking", "Documentation only"]) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
    expect(container.querySelectorAll(".tag__mark[aria-hidden='true']")).toHaveLength(4);
  });

  it("separates confirmed from inferred by word and style, and shows confidence only for guesses", () => {
    render(
      <>
        <CertaintyTag value="confirmed" confidence={1} />
        <CertaintyTag value="inferred" confidence={0.8} />
      </>,
    );
    expect(screen.getByText("Confirmed")).toHaveClass("certainty--confirmed");
    expect(screen.getByText("Inferred 80%")).toHaveClass("certainty--inferred");
  });
});

describe("notice", () => {
  it("interrupts only for errors", () => {
    render(
      <>
        <Notice kind="error" title="Broke">
          why
        </Notice>
        <Notice kind="loading" title="Waiting" />
      </>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Broke");
    expect(screen.getByRole("status")).toHaveTextContent("Waiting");
  });
});

describe("version pane", () => {
  const setup = (files: Record<string, string> = {}) => {
    const handlers = { onLabel: vi.fn(), onAdd: vi.fn(), onRemove: vi.fn() };
    render(<VersionPane side="A" heading="Version A (before)" label="v1" files={files} {...handlers} />);
    return handlers;
  };

  it("explains the empty state", () => {
    setup();
    expect(screen.getByText(/No files yet/)).toBeInTheDocument();
  });

  it("lists files with sizes and removes by an accessible name", async () => {
    const h = setup({ "docs/guide.md": "# hi", "openapi.yaml": "openapi: 3" });
    expect(screen.getByText("2 files, 14 B")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove docs/guide.md from version A" }));
    expect(h.onRemove).toHaveBeenCalledWith("docs/guide.md");
  });

  it("reads picked files and reports what it skipped", async () => {
    const h = setup();
    // A browser picker can be switched to "All files", so the accept attribute is not a guarantee.
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(screen.getByTestId("files-A"), [
      new File(["# a"], "a.md"),
      new File(["x"], "photo.png"),
    ]);
    await waitFor(() => expect(h.onAdd).toHaveBeenCalled());
    expect(h.onAdd.mock.calls[0][0]).toEqual({ "a.md": "# a" });
    expect(h.onAdd.mock.calls[0][1][0]).toMatch(/photo\.png: unsupported/);
  });

  it("edits the version name", async () => {
    const h = setup();
    await userEvent.type(screen.getByLabelText("Name of this version"), "x");
    expect(h.onLabel).toHaveBeenLastCalledWith("v1x");
  });
});

describe("compare form", () => {
  it("blocks submit until both versions have files, and says why", () => {
    render(<CompareForm />);
    expect(screen.getByRole("button", { name: "Compare versions" })).toBeDisabled();
    expect(screen.getByText("Add at least one file to version A.")).toBeInTheDocument();
  });

  it("loads the petstore example, then submits and opens the result", async () => {
    api.createRun.mockResolvedValue({ id: "abc", status: "done" });
    render(<CompareForm />);
    await userEvent.click(screen.getByRole("button", { name: "Load petstore example" }));
    expect(screen.getByText("Ready to compare.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Compare versions" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/runs/abc"));
    const body = api.createRun.mock.calls[0][0];
    expect(body.label_a).toBe("v1");
    expect(Object.keys(body.files_a)).toEqual(["docs/guide.md", "openapi.yaml"]);
  });

  it("keeps the skipped-file notice for A when files are then chosen for B", async () => {
    render(<CompareForm />);
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(screen.getByTestId("files-A"), [new File(["x"], "logo.png"), new File(["# a"], "a.md")]);
    expect(await screen.findByText(/Version A, logo\.png: unsupported file type/)).toBeInTheDocument();
    await user.upload(screen.getByTestId("files-B"), new File(["# b"], "a.md"));
    await waitFor(() => expect(screen.getByText("Ready to compare.")).toBeInTheDocument());
    expect(screen.getByText(/Version A, logo\.png: unsupported file type/)).toBeInTheDocument();
  });

  it("shows the API failure and re-enables the button", async () => {
    api.createRun.mockRejectedValue(new ApiError("rate_limited", 429, "x", 9));
    render(<CompareForm />);
    await userEvent.click(screen.getByRole("button", { name: "Load petstore example" }));
    await userEvent.click(screen.getByRole("button", { name: "Compare versions" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again in 9 seconds");
    expect(screen.getByRole("button", { name: "Compare versions" })).toBeEnabled();
    expect(push).not.toHaveBeenCalled();
  });
});

describe("history", () => {
  it("shows an empty state, rows with links for finished runs, and failures as text", async () => {
    api.listRuns.mockResolvedValueOnce([]);
    const { unmount } = render(<HistoryList />);
    expect(await screen.findByText("No comparisons yet")).toBeInTheDocument();
    unmount();

    api.listRuns.mockResolvedValueOnce([
      run({ id: "r1" }),
      run({ id: "r2", status: "failed", error_code: "parse_error", label_a: "x", label_b: "y" }),
    ]);
    render(<HistoryList />);
    const link = await screen.findByRole("link", { name: "v1 to v2" });
    expect(link).toHaveAttribute("href", "/runs/r1");
    expect(screen.getByText("parse_error")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "x to y" })).toBeNull();
  });

  it("explains a load failure", async () => {
    api.listRuns.mockRejectedValueOnce(new ApiError("network", 0, "x"));
    render(<HistoryList />);
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be reached");
  });
});

describe("change list", () => {
  const r = result();

  it("orders by urgency, marks the selection, and reports selection", async () => {
    const onSelect = vi.fn();
    render(<ChangeList changes={r.changes} impacts={r.impacts} selectedKey="schema:Pet" onSelect={onSelect} />);
    const buttons = within(screen.getByRole("list", { name: "Changes" })).getAllByRole("button");
    expect(buttons.map((b) => b.querySelector(".change__key")?.textContent)).toEqual([
      "schema:Pet",
      "endpoint:GET /new",
      "section:docs/a.md#intro",
    ]);
    expect(buttons[0]).toHaveAttribute("aria-current", "true");
    await userEvent.click(buttons[1]);
    expect(onSelect).toHaveBeenCalledWith("endpoint:GET /new");
  });

  it("filters by classification and toggles state with aria-pressed", async () => {
    render(<ChangeList changes={r.changes} impacts={r.impacts} selectedKey={null} onSelect={() => {}} />);
    const breaking = screen.getByRole("button", { name: "Breaking (1)" });
    await userEvent.click(breaking);
    expect(breaking).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByRole("list", { name: "Changes" })).getAllByRole("button")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "All (3)" }));
    expect(within(screen.getByRole("list", { name: "Changes" })).getAllByRole("button")).toHaveLength(3);
  });

  it("does not offer a filter for classes that have no changes", () => {
    render(<ChangeList changes={r.changes} impacts={r.impacts} selectedKey={null} onSelect={() => {}} />);
    expect(screen.queryByRole("button", { name: /Needs review/ })).toBeNull();
  });
});

describe("impact item", () => {
  it("lists hops from the impacted entity to the change", () => {
    render(
      <ul>
        <ImpactItem impact={impact()} runId="r" versionOf={versionOf} />
      </ul>,
    );
    expect(screen.getByText("Confirmed breaking")).toBeInTheDocument();
    const hops = within(screen.getByRole("list", { name: /How section:docs\/guide.md#listing depends on schema:Pet/ })).getAllByRole("listitem");
    expect(hops).toHaveLength(2);
    expect(hops[0]).toHaveTextContent("mentions endpoint");
    expect(hops[1]).toHaveTextContent("uses schema");
    // Every hop is confirmed here, so the hop list carries no repeated label.
    expect(within(hops[0]).queryByText("Confirmed")).toBeNull();
  });

  it("warns that an inferred impact is a guess", () => {
    const inferred = result().impacts["schema:Pet"][1];
    render(
      <ul>
        <ImpactItem impact={inferred} runId="r" versionOf={versionOf} />
      </ul>,
    );
    expect(screen.getByText(/At least one link is a guess \(80% combined confidence\)/)).toBeInTheDocument();
    expect(screen.queryByText("Confirmed breaking")).toBeNull();
    // On an inferred impact each hop says whether it is explicit or a guess.
    const hop = within(screen.getByRole("list", { name: /How requirement:REQ-001 depends/ })).getByRole("listitem");
    expect(within(hop).getByText("Inferred")).toBeInTheDocument();
  });

  it("fetches and shows the cited source line from the right version, once", async () => {
    api.getSnippet.mockResolvedValue({
      file: "docs/guide.md",
      version: "b",
      line: 4,
      lines: [
        { n: 3, text: "" },
        { n: 4, text: "Call `GET /pets` to list all pets." },
      ],
    });
    render(
      <ul>
        <ImpactItem impact={impact()} runId="run-1" versionOf={versionOf} />
      </ul>,
    );
    const toggle = screen.getAllByRole("button", { name: /Show source at/ })[0];
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(await screen.findByText("Call `GET /pets` to list all pets.")).toBeInTheDocument();
    expect(api.getSnippet).toHaveBeenCalledWith("run-1", "b", "docs/guide.md", 4);
    await userEvent.click(screen.getByRole("button", { name: /Hide source at/ }));
    await userEvent.click(screen.getAllByRole("button", { name: /Show source at/ })[0]);
    expect(api.getSnippet).toHaveBeenCalledTimes(1);
  });

  it("explains when the source cannot be loaded", async () => {
    api.getSnippet.mockRejectedValue(new ApiError("not_found", 404, "x"));
    render(
      <ul>
        <ImpactItem impact={impact()} runId="r" versionOf={versionOf} />
      </ul>,
    );
    await userEvent.click(screen.getAllByRole("button", { name: /Show source at/ })[0]);
    expect(await screen.findByRole("alert")).toHaveTextContent("does not exist");
  });
});

describe("change detail", () => {
  it("shows reasons, the number of dependents by certainty, and a diff with visible markers", () => {
    const r = result();
    render(<ChangeDetail change={r.changes[1]} impacts={r.impacts["schema:Pet"]} runId="r" versionOf={versionOf} />);
    expect(screen.getByRole("heading", { level: 2, name: "schema:Pet" })).toBeInTheDocument();
    expect(screen.getByText("property id type changed string -> integer")).toBeInTheDocument();
    expect(screen.getByText(/2 dependents: 1 confirmed, 1 inferred/)).toBeInTheDocument();
    // Testing Library collapses runs of spaces when matching text, so match on the exact string.
    const exact = (text: string) => (_: string, node: Element | null) => node?.textContent === `${text}
`;
    expect(screen.getByText(exact("-  type: string"))).toHaveClass("diff__line--del");
    expect(screen.getByText(exact("+  type: integer"))).toHaveClass("diff__line--add");
    expect(screen.getByText("1 added, 1 removed lines.")).toBeInTheDocument();
  });

  it("says why an added entity has no impacts, and what an empty result means", () => {
    const { rerender } = render(
      <ChangeDetail change={change({ change_type: "added" })} impacts={[]} runId="r" versionOf={versionOf} />,
    );
    expect(screen.getByText(/this entity is new/i)).toBeInTheDocument();
    rerender(<ChangeDetail change={change({ source_diff: "" })} impacts={[]} runId="r" versionOf={versionOf} />);
    expect(screen.getByText(/Nothing in the compared files depends on this entity/)).toBeInTheDocument();
    expect(screen.getByText("No text difference to show.")).toBeInTheDocument();
  });
});

describe("ask panel", () => {
  it("keeps Ask disabled until a question is typed", async () => {
    render(<AskPanel runId="r" versionOf={versionOf} />);
    const button = screen.getByRole("button", { name: "Ask" });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Question"), "What breaks if Pet changes?");
    expect(button).toBeEnabled();
  });

  it("shows an answer with evidence, and an honest abstention", async () => {
    api.askRun.mockResolvedValueOnce({
      status: "answered",
      matched: ["schema:Pet"],
      impacts: [impact()],
      reason: "Impacts are listed with evidence paths.",
    });
    render(<AskPanel runId="r" versionOf={versionOf} />);
    await userEvent.type(screen.getByLabelText("Question"), "Pet{enter}");
    expect(await screen.findByRole("heading", { name: "Impacts found" })).toBeInTheDocument();
    expect(screen.getByText(/Depends on/)).toBeInTheDocument();
    expect(api.askRun).toHaveBeenCalledWith("r", "Pet");

    api.askRun.mockResolvedValueOnce({ status: "uncertain", matched: [], impacts: [], reason: "No known name." });
    await userEvent.clear(screen.getByLabelText("Question"));
    await userEvent.type(screen.getByLabelText("Question"), "moon{enter}");
    expect(await screen.findByRole("heading", { name: "Not enough to answer" })).toBeInTheDocument();
    expect(screen.queryByText("Impacts found")).toBeNull();
  });

  it("shows an error and clears the previous answer", async () => {
    api.askRun.mockRejectedValueOnce(new ApiError("rate_limited", 429, "x", 3));
    render(<AskPanel runId="r" versionOf={versionOf} />);
    await userEvent.type(screen.getByLabelText("Question"), "Pet{enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("3 seconds");
  });
});

describe("run view", () => {
  it("shows loading, then the summary and the first change selected", async () => {
    api.getRun.mockResolvedValue(run());
    render(<RunView id="r" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading comparison");
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("v1 to v2");
    expect(screen.getByText(/3 changes, 1 breaking/)).toBeInTheDocument();
    expect(screen.getByText(/2 dependents found: 1 confirmed, 1 inferred/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "schema:Pet" })).toBeInTheDocument();
    expect(screen.getByText(/Notes from the analysis \(1\)/)).toBeInTheDocument();
  });

  it("puts the question box after the review and links to it from the summary", async () => {
    api.getRun.mockResolvedValue(run());
    render(<RunView id="r" />);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByRole("link", { name: "Ask a question about this comparison" })).toHaveAttribute(
      "href",
      "#ask-heading",
    );
    const changes = screen.getByRole("heading", { level: 2, name: "Changes" });
    const ask = screen.getByRole("heading", { level: 2, name: "Ask about this comparison" });
    expect(changes.compareDocumentPosition(ask) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("switches the detail when another change is chosen and moves focus to its heading", async () => {
    api.getRun.mockResolvedValue(run());
    render(<RunView id="r" />);
    await screen.findByRole("heading", { level: 1 });
    await userEvent.click(screen.getByRole("button", { name: /section:docs\/a.md#intro/ }));
    const heading = await screen.findByRole("heading", { level: 2, name: "section:docs/a.md#intro" });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("explains an error, a failed run and a run with no differences", async () => {
    api.getRun.mockRejectedValueOnce(new ApiError("not_found", 404, "x"));
    const { unmount } = render(<RunView id="r" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("does not exist");
    unmount();

    api.getRun.mockResolvedValueOnce(run({ status: "failed", error_code: "parse_error", result: null }));
    const second = render(<RunView id="r" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("parse_error");
    second.unmount();

    api.getRun.mockResolvedValueOnce(run({ result: result({ changes: [], impacts: {}, unsupported: [] }) }));
    render(<RunView id="r" />);
    expect(await screen.findByText("No differences found")).toBeInTheDocument();
  });
});
