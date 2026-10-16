import { expect, test, type Page } from "@playwright/test";

const DARK_PAPER = "rgb(20, 19, 15)";
const LIGHT_PAPER = "rgb(244, 241, 232)";

const background = (page: Page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);

async function drop(page: Page, side: "A" | "B", files: { name: string; text: string }[]) {
  const data = await page.evaluateHandle((list) => {
    const dt = new DataTransfer();
    for (const f of list) dt.items.add(new File([f.text], f.name, { type: "text/markdown" }));
    return dt;
  }, files);
  const pane = page.getByRole("group", { name: side === "A" ? "Version A (before)" : "Version B (after)" });
  await pane.dispatchEvent("dragenter", { dataTransfer: data });
  await pane.dispatchEvent("dragover", { dataTransfer: data });
  await pane.dispatchEvent("drop", { dataTransfer: data });
}

test.describe("drag and drop", () => {
  test("dropping files onto a version adds them and announces it", async ({ page }) => {
    await page.goto("/");
    await drop(page, "A", [
      { name: "guide.md", text: "## Setup\nInstall it.\n" },
      { name: "notes.md", text: "## Notes\nText.\n" },
    ]);
    await expect(page.getByTestId("status-A")).toHaveText("Added 2 files.");
    await expect(page.getByText("guide.md", { exact: true })).toBeVisible();
    await expect(page.getByText(/^2 files, \d+ B$/)).toBeVisible();
    await expect(page.getByText("You can also drag files or a folder onto this box.").first()).toBeVisible();
  });

  test("dropped files can be compared end to end", async ({ page }) => {
    await page.goto("/");
    await drop(page, "A", [{ name: "guide.md", text: "## Setup\nInstall it.\n" }]);
    await drop(page, "B", [{ name: "guide.md", text: "## Setup\nInstall it, then restart.\n" }]);
    await page.getByRole("button", { name: "Compare versions" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "section:guide.md#setup" })).toBeVisible();
  });

  test("a dropped file of an unsupported type is reported, not added", async ({ page }) => {
    await page.goto("/");
    await drop(page, "B", [{ name: "photo.png", text: "x" }]);
    await expect(page.getByTestId("status-B")).toHaveText("No files added, 1 skipped.");
    await expect(page.getByText(/Version B, photo\.png: unsupported file type/)).toBeVisible();
  });

  test("a file dropped outside a box does not make the browser leave the page", async ({ page }) => {
    await page.goto("/");
    const prevented = await page.evaluate(() => {
      const dt = new DataTransfer();
      dt.items.add(new File(["x"], "a.md"));
      const event = new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true });
      document.querySelector("h1")!.dispatchEvent(event);
      return event.defaultPrevented;
    });
    expect(prevented).toBe(true);
    await expect(page).toHaveURL("/");
  });

  test("the drop state names the target and goes away on leave", async ({ page }) => {
    await page.goto("/");
    const data = await page.evaluateHandle(() => {
      const dt = new DataTransfer();
      dt.items.add(new File(["x"], "a.md"));
      return dt;
    });
    const pane = page.getByRole("group", { name: "Version B (after)" });
    await pane.dispatchEvent("dragenter", { dataTransfer: data });
    await expect(page.getByText("Release to add these to version B.")).toBeVisible();
    await expect(page.getByText("Release to add these to version A.")).toHaveCount(0);
    await pane.dispatchEvent("dragleave", { dataTransfer: data });
    await expect(page.getByText("Release to add these to version B.")).toHaveCount(0);
  });
});

test.describe("theme toggle", () => {
  test("follows the system until a choice is made", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/");
    expect(await background(page)).toBe(DARK_PAPER);
    await page.emulateMedia({ colorScheme: "light" });
    expect(await background(page)).toBe(LIGHT_PAPER);
    await expect(page.getByRole("button", { name: "System" })).toHaveAttribute("aria-pressed", "true");
  });

  test("a manual choice overrides the system, in both directions", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/");
    await page.getByRole("button", { name: "Dark", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    expect(await background(page)).toBe(DARK_PAPER);

    await page.emulateMedia({ colorScheme: "dark" });
    await page.getByRole("button", { name: "Light", exact: true }).click();
    expect(await background(page)).toBe(LIGHT_PAPER);
  });

  test("the choice survives a reload and is applied before the page is drawn", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/");
    await page.getByRole("button", { name: "Dark", exact: true }).click();
    await page.reload({ waitUntil: "domcontentloaded" });
    // Read straight after the document is parsed, before React has run.
    expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe("dark");
    expect(await background(page)).toBe(DARK_PAPER);
    await expect(page.getByRole("button", { name: "Dark", exact: true })).toHaveAttribute("aria-pressed", "true");
  });

  test("System clears the stored choice", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/");
    await page.getByRole("button", { name: "Dark", exact: true }).click();
    await page.getByRole("button", { name: "System", exact: true }).click();
    await expect(page.locator("html")).not.toHaveAttribute("data-theme", /.+/);
    expect(await page.evaluate(() => localStorage.getItem("spectrace-theme"))).toBeNull();
    expect(await background(page)).toBe(LIGHT_PAPER);
  });

  test("the choice applies on every page and the toggle has three 44px targets", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Dark", exact: true }).click();
    await page.getByRole("link", { name: "Benchmark" }).click();
    await expect(page).toHaveURL(/\/benchmark$/);
    expect(await background(page)).toBe(DARK_PAPER);
    for (const name of ["System", "Light", "Dark"]) {
      const box = await page.getByRole("button", { name, exact: true }).boundingBox();
      expect(box!.height).toBeGreaterThanOrEqual(43.5);
    }
  });

  test("works when storage is blocked", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, "localStorage", {
        get() {
          throw new DOMException("blocked", "SecurityError");
        },
      });
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Dark", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  });

  test("the header still fits at 320px with the toggle", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto("/");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await expect(page.getByRole("button", { name: "Dark", exact: true })).toBeVisible();
  });
});
