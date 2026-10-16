import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ImpactItem } from "@/components/ImpactItem";
import { RunView } from "@/components/RunView";
import { THEME_KEY, ThemeToggle, applyTheme, readStoredTheme } from "@/components/ThemeToggle";
import { VersionPane } from "@/components/VersionPane";
import { MAX_DROPPED_FILES, collectDropped } from "@/lib/files";
import { impact, run } from "./fixtures";

const api = vi.hoisted(() => ({ getRun: vi.fn(), getSnippet: vi.fn() }));
vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()), ...api }));

// ---- fakes for the File System entries a browser hands over on a drop ----
type Entry = Record<string, unknown>;
const fileEntry = (path: string, text = "# x"): Entry => ({
  isFile: true,
  isDirectory: false,
  name: path.split("/").pop(),
  fullPath: `/${path}`,
  file: (ok: (f: File) => void) => ok(new File([text], path.split("/").pop() as string)),
});
const dirEntry = (path: string, children: Entry[], batch = 2): Entry => {
  let index = 0;
  return {
    isFile: false,
    isDirectory: true,
    name: path.split("/").pop(),
    fullPath: `/${path}`,
    createReader: () => ({
      readEntries: (ok: (e: Entry[]) => void) => {
        const part = children.slice(index, index + batch);
        index += batch;
        ok(part);
      },
    }),
  };
};
const dropData = (entries: Entry[], files: File[] = []) =>
  ({
    types: ["Files"],
    files,
    items: entries.map((entry) => ({ kind: "file", webkitGetAsEntry: () => entry })),
  }) as unknown as DataTransfer;

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("collectDropped", () => {
  it("reads a dropped folder in batches, keeps relative paths and ignores node_modules and .git", async () => {
    const folder = dirEntry("v1", [
      fileEntry("v1/openapi.yaml"),
      dirEntry("v1/docs", [fileEntry("v1/docs/a.md"), fileEntry("v1/docs/b.md"), fileEntry("v1/docs/c.md")]),
      dirEntry("v1/node_modules", [fileEntry("v1/node_modules/junk.md")]),
      dirEntry("v1/.git", [fileEntry("v1/.git/config.txt")]),
    ]);
    const { files, fromFolder, notes } = await collectDropped(dropData([folder]));
    const paths = files.map((f) => (f as File & { webkitRelativePath: string }).webkitRelativePath).sort();
    expect(paths).toEqual(["v1/docs/a.md", "v1/docs/b.md", "v1/docs/c.md", "v1/openapi.yaml"]);
    expect(fromFolder).toBe(true);
    expect(notes).toEqual([]);
  });

  it("treats loose files as files, not as a folder", async () => {
    const { files, fromFolder } = await collectDropped(dropData([fileEntry("a.md"), fileEntry("b.md")]));
    expect(files.map((f) => f.name)).toEqual(["a.md", "b.md"]);
    expect(fromFolder).toBe(false);
  });

  it("falls back to the plain file list when the browser gives no entries", async () => {
    const plain = new File(["x"], "plain.md");
    const { files } = await collectDropped({ types: ["Files"], files: [plain], items: [] } as unknown as DataTransfer);
    expect(files).toEqual([plain]);
  });

  it("stops at the cap and says so", async () => {
    const many = Array.from({ length: MAX_DROPPED_FILES + 50 }, (_, i) => fileEntry(`big/f${i}.md`));
    const { files, notes } = await collectDropped(dropData([dirEntry("big", many, 100)]));
    expect(files.length).toBeGreaterThanOrEqual(MAX_DROPPED_FILES);
    expect(files.length).toBeLessThan(MAX_DROPPED_FILES + 100);
    expect(notes).toEqual([`only the first ${MAX_DROPPED_FILES} files were read`]);
  });
});

describe("drag and drop on a version pane", () => {
  const setup = () => {
    const handlers = { onLabel: vi.fn(), onAdd: vi.fn(), onRemove: vi.fn() };
    render(<VersionPane side="B" heading="Version B (after)" label="v2" files={{}} {...handlers} />);
    return { ...handlers, pane: screen.getByRole("group", { name: "Version B (after)" }) };
  };

  it("shows a drop state while a file is over the box and clears it on leave", () => {
    const { pane } = setup();
    expect(screen.getByText(/You can also drag files or a folder/)).toBeInTheDocument();
    fireEvent.dragEnter(pane, { dataTransfer: { types: ["Files"] } });
    expect(screen.getByText("Release to add these to version B.")).toBeInTheDocument();
    expect(pane).toHaveClass("pane--drag");
    fireEvent.dragLeave(pane, { dataTransfer: { types: ["Files"] } });
    expect(pane).not.toHaveClass("pane--drag");
  });

  it("ignores drags that carry no files, such as selected text", () => {
    const { pane } = setup();
    fireEvent.dragEnter(pane, { dataTransfer: { types: ["text/plain"] } });
    expect(pane).not.toHaveClass("pane--drag");
  });

  it("adds a dropped folder without its own name and announces the result", async () => {
    const { pane, onAdd } = setup();
    const folder = dirEntry("v2", [fileEntry("v2/openapi.yaml", "openapi: 3"), fileEntry("v2/docs/guide.md", "# g"), fileEntry("v2/logo.png", "x")]);
    fireEvent.drop(pane, { dataTransfer: dropData([folder]) });
    await waitFor(() => expect(onAdd).toHaveBeenCalled());
    expect(Object.keys(onAdd.mock.calls[0][0]).sort()).toEqual(["docs/guide.md", "openapi.yaml"]);
    expect(onAdd.mock.calls[0][1][0]).toMatch(/logo\.png: unsupported/);
    expect(screen.getByTestId("status-B")).toHaveTextContent("Added 2 files, 1 skipped.");
    expect(pane).not.toHaveClass("pane--drag");
  });

  it("announces a removal", async () => {
    const onRemove = vi.fn();
    render(<VersionPane side="A" heading="Version A (before)" label="v1" files={{ "a.md": "x" }} onLabel={() => {}} onAdd={() => {}} onRemove={onRemove} />);
    await userEvent.click(screen.getByRole("button", { name: "Remove a.md from version A" }));
    expect(screen.getByTestId("status-A")).toHaveTextContent("Removed a.md.");
  });

  it("keeps its status region in the page from the start so changes are announced", () => {
    setup();
    expect(screen.getByTestId("status-B")).toHaveAttribute("aria-live", "polite");
  });
});

describe("theme toggle", () => {
  it("starts on System and offers three named choices", () => {
    render(<ThemeToggle />);
    const group = screen.getByRole("group", { name: "Color theme" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "System" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "false");
  });

  it("applies a manual choice to the page, remembers it, and System removes it", async () => {
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(screen.getByRole("button", { name: "Light" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "light");

    await userEvent.click(screen.getByRole("button", { name: "System" }));
    expect(document.documentElement).not.toHaveAttribute("data-theme");
    expect(window.localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("shows the stored choice after load", async () => {
    window.localStorage.setItem(THEME_KEY, "light");
    render(<ThemeToggle />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Light" })).toHaveAttribute("aria-pressed", "true"));
  });

  it("still works when storage is blocked", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readStoredTheme()).toBe("system");
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    getItem.mockRestore();
    setItem.mockRestore();
  });

  it("ignores a stored value that is not a theme", () => {
    window.localStorage.setItem(THEME_KEY, "neon");
    expect(readStoredTheme()).toBe("system");
    applyTheme("system");
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });
});

describe("evidence region and page title", () => {
  it("has the live region in the page before the source is opened, and the button points at it", () => {
    render(
      <ul>
        <ImpactItem impact={impact()} runId="r" versionOf={() => "b"} />
      </ul>,
    );
    const toggle = screen.getAllByRole("button", { name: /Show source at/ })[0];
    const region = document.getElementById(toggle.getAttribute("aria-controls") as string);
    expect(region).not.toBeNull();
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toBeEmptyDOMElement();
  });

  it("names the two versions in the page title", async () => {
    api.getRun.mockResolvedValue(run({ label_a: "2.0", label_b: "2.1" }));
    render(<RunView id="r" />);
    await screen.findByRole("heading", { level: 1 });
    expect(document.title).toBe("2.0 to 2.1 | SpecTrace");
  });
});
