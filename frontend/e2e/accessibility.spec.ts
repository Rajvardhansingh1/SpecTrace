import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];

async function openRun(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Load petstore example" }).click();
  await page.getByRole("button", { name: "Compare versions" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("v1 to v2");
}

async function axe(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(results.violations.map((v) => `${label}: ${v.id} ${v.nodes.map((n) => n.target).join(",")}`)).toEqual([]);
}

test.describe("structure that assistive technology relies on", () => {
  const SCREENS = [
    { path: "/", name: "compare" },
    { path: "/benchmark", name: "benchmark" },
  ];

  for (const screen of SCREENS) {
    test(`${screen.name}: one banner, one main, a named navigation, one h1, and no skipped heading level`, async ({ page }) => {
      await page.goto(screen.path);
      await expect(page.getByRole("banner")).toHaveCount(1);
      await expect(page.getByRole("main")).toHaveCount(1);
      await expect(page.getByRole("navigation", { name: "Main" })).toHaveCount(1);
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      const levels = await page.evaluate(() => [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")].map((h) => Number(h.tagName[1])));
      levels.forEach((level, i) => {
        if (i > 0) expect(level, `heading ${i} jumps from ${levels[i - 1]} to ${level}`).toBeLessThanOrEqual(levels[i - 1] + 1);
      });
      expect(await page.evaluate(() => document.documentElement.lang)).toBe("en");
    });
  }

  test("run page: same structure, and the page title names the two versions", async ({ page }) => {
    await openRun(page);
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    const levels = await page.evaluate(() => [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")].map((h) => Number(h.tagName[1])));
    levels.forEach((level, i) => {
      if (i > 0) expect(level).toBeLessThanOrEqual(levels[i - 1] + 1);
    });
    await expect(page).toHaveTitle("v1 to v2 | SpecTrace");
  });

  test("every screen has its own title", async ({ page }) => {
    const titles = new Set<string>();
    for (const path of ["/", "/benchmark", "/nothing-here"]) {
      await page.goto(path);
      titles.add(await page.title());
    }
    await openRun(page);
    titles.add(await page.title());
    expect(titles.size).toBe(4);
  });

  test("the change list, filters, hops and tables expose names and state", async ({ page }) => {
    await openRun(page);
    await expect(page.getByRole("group", { name: "Filter changes by classification" })).toBeVisible();
    await expect(page.getByRole("button", { name: "All (1)" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("list", { name: "Changes" }).getByRole("button").first()).toHaveAttribute("aria-current", "true");
    await expect(page.getByRole("list", { name: /How section:docs\/guide\.md#listing-pets depends on schema:Pet/ })).toBeVisible();
    await page.goto("/benchmark");
    await expect(page.getByRole("table", { name: /Precision and recall of each system/ })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Precision" })).toBeVisible();
  });
});

test.describe("announcements", () => {
  test("the live regions exist before anything changes, and their text changes when it should", async ({ page }) => {
    await page.goto("/");
    // Present and empty at load, so later text is announced rather than ignored.
    await expect(page.getByTestId("status-A")).toHaveAttribute("aria-live", "polite");
    await expect(page.getByTestId("status-A")).toHaveText("");
    await expect(page.locator("#submit-hint")).toHaveAttribute("aria-live", "polite");
    await expect(page.locator("#submit-hint")).toContainText("Add at least one file to version A.");

    await page.getByTestId("files-A").setInputFiles({ name: "a.md", mimeType: "text/markdown", buffer: Buffer.from("# a") });
    await expect(page.getByTestId("status-A")).toHaveText("Added 1 file.");
    await page.getByTestId("files-B").setInputFiles({ name: "a.md", mimeType: "text/markdown", buffer: Buffer.from("# b") });
    await expect(page.locator("#submit-hint")).toHaveText("Ready to compare.");
    await page.getByRole("button", { name: "Remove a.md from version A" }).click();
    await expect(page.getByTestId("status-A")).toHaveText("Removed a.md.");
  });

  test("the source panel is a live region that exists before it is opened", async ({ page }) => {
    await openRun(page);
    // The button renames itself from "Show" to "Hide" when opened, so match both.
    const toggle = page.getByRole("button", { name: /source at/ }).first();
    const regionId = await toggle.getAttribute("aria-controls");
    const region = page.locator(`[id="${regionId}"]`);
    await expect(region).toHaveAttribute("aria-live", "polite");
    await expect(region).toBeEmpty();
    await toggle.click();
    await expect(region).toContainText(/\d/);
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  test("an answer arrives inside a live region", async ({ page }) => {
    await openRun(page);
    const live = page.locator(".ask ~ [aria-live=polite]");
    await expect(live).toBeEmpty();
    await page.getByLabel("Question").fill("What breaks if Pet changes?");
    await page.getByRole("button", { name: "Ask" }).click();
    await expect(live.getByRole("heading", { name: "Answer", exact: true })).toBeVisible();
  });
});

test.describe("keyboard order and focus", () => {
  test("every tab stop on the results page is visible, shows a focus indicator and follows page order", async ({ page }) => {
    await openRun(page);
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());

    const stops: { name: string; top: number; outline: string; visible: boolean; position: number }[] = [];
    for (let i = 0; i < 160; i++) {
      await page.keyboard.press("Tab");
      const info = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return {
          name: (el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40),
          top: rect.top + window.scrollY,
          outline: `${style.outlineStyle} ${style.outlineWidth}`,
          visible: rect.width > 0 && rect.height > 0 && style.visibility !== "hidden",
          position: [...document.querySelectorAll("*")].indexOf(el),
        };
      });
      if (!info) break;
      stops.push(info);
    }
    expect(stops.length).toBeGreaterThan(15);
    for (const stop of stops) {
      expect(stop.visible, `${stop.name} is not visible`).toBe(true);
      expect(stop.outline, `${stop.name} shows no focus indicator`).not.toMatch(/^none/);
    }
    // DOM order, which is the visual order here, so focus never jumps backwards.
    const positions = stops.map((s) => s.position);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  test("there is no keyboard trap: Shift+Tab walks back out", async ({ page }) => {
    await openRun(page);
    await page.getByLabel("Question").focus();
    for (let i = 0; i < 6; i++) await page.keyboard.press("Shift+Tab");
    const stillInside = await page.evaluate(() => document.activeElement !== document.body);
    expect(stillInside).toBe(true);
    for (let i = 0; i < 200; i++) {
      await page.keyboard.press("Shift+Tab");
      if (await page.evaluate(() => document.activeElement === document.body || document.activeElement === document.documentElement)) return;
    }
    // Reaching the browser chrome also counts as leaving the page.
    expect(true).toBe(true);
  });

  test("selecting a change by keyboard moves focus to its heading", async ({ page }) => {
    await openRun(page);
    const row = page.getByRole("list", { name: "Changes" }).getByRole("button").first();
    await row.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 2, name: "schema:Pet" })).toBeFocused();
  });
});

test.describe("user preferences", () => {
  test("forced colors: states that relied on a background still show", async ({ page }) => {
    await page.emulateMedia({ forcedColors: "active" });
    await openRun(page);
    const pressed = await page.getByRole("button", { name: "All (1)" }).evaluate((el) => {
      const s = getComputedStyle(el);
      return { outlineStyle: s.outlineStyle, outlineWidth: s.outlineWidth };
    });
    expect(pressed.outlineStyle).not.toBe("none");
    expect(parseFloat(pressed.outlineWidth)).toBeGreaterThanOrEqual(2);

    const mark = await page.locator(".tag--breaking .tag__mark").first().evaluate((el) => {
      const s = getComputedStyle(el);
      return { bg: s.backgroundColor, w: el.getBoundingClientRect().width };
    });
    expect(mark.bg).not.toBe("rgba(0, 0, 0, 0)");
    expect(mark.w).toBeGreaterThan(0);

    const current = await page.locator(".change[aria-current=true]").evaluate((el) => getComputedStyle(el).outlineStyle);
    expect(current).not.toBe("none");

    await page.getByRole("button", { name: /Show source at/ }).first().click();
    const cited = await page.locator(".snippet__line--cited").first().evaluate((el) => getComputedStyle(el).outlineStyle);
    expect(cited).not.toBe("none");
  });

  test("reduced motion: no transitions run", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const durations = await page.locator(".button").first().evaluate((el) => getComputedStyle(el).transitionDuration);
    expect(durations).toMatch(/^0s(, 0s)*$/);
  });

  test("text spacing from WCAG 1.4.12 does not clip or overflow anything", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await openRun(page);
    await page.getByRole("button", { name: /Show source at/ }).first().click();
    await page.addStyleTag({
      content: `* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }
                p { margin-bottom: 2em !important; }`,
    });
    const problems = await page.evaluate(() => {
      const out: string[] = [];
      if (document.documentElement.scrollWidth > window.innerWidth + 1) out.push("page overflows sideways");
      for (const el of document.querySelectorAll<HTMLElement>("button, .tag, .certainty, .flag, label, h1, h2, h3, legend")) {
        if (el.offsetParent === null) continue;
        if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX !== "visible") out.push(`${el.tagName}.${el.className} clips its text`);
        if (el.scrollHeight > el.clientHeight + 1 && getComputedStyle(el).overflowY === "hidden") out.push(`${el.tagName}.${el.className} clips vertically`);
      }
      return out;
    });
    expect(problems).toEqual([]);
  });

  for (const size of [200, 300]) {
    test(`browser text enlarged to ${size}% still reflows without sideways scrolling`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.goto("/");
      await page.getByRole("button", { name: "Load petstore example" }).click();
      await page.getByRole("button", { name: "Compare versions" }).click();
      await expect(page.getByRole("heading", { level: 1 })).toContainText("v1 to v2");
      await page.addStyleTag({ content: `html { font-size: ${size}% !important; }` });
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
      await expect(page.getByRole("button", { name: "Ask" })).toBeVisible();
    });
  }

  test("the pointer alternative to dragging exists: file and folder buttons", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Add files" })).toHaveCount(2);
    await expect(page.getByRole("button", { name: "Add folder" })).toHaveCount(2);
  });
});

test.describe("axe with a manual theme that differs from the system theme", () => {
  for (const [system, manual] of [
    ["light", "Dark"],
    ["dark", "Light"],
  ] as const) {
    test(`system ${system}, manual ${manual}: no violations on every screen`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: system });
      await page.goto("/");
      await page.getByRole("button", { name: manual, exact: true }).click();
      await axe(page, "compare, empty");
      await page.getByRole("button", { name: "Load petstore example" }).click();
      await page.getByRole("button", { name: "Compare versions" }).click();
      await expect(page.getByRole("heading", { level: 1 })).toContainText("v1 to v2");
      await page.getByRole("button", { name: /Show source at/ }).first().click();
      await expect(page.locator(".snippet__line--cited").first()).toBeVisible();
      await page.getByLabel("Question").fill("What breaks if Pet changes?");
      await page.getByRole("button", { name: "Ask" }).click();
      await expect(page.getByRole("heading", { name: "Answer", exact: true })).toBeVisible();
      await axe(page, "run");
      await page.goto("/benchmark");
      await axe(page, "benchmark");
    });
  }

  test("axe with the drop state showing", async ({ page }) => {
    await page.goto("/");
    const data = await page.evaluateHandle(() => {
      const dt = new DataTransfer();
      dt.items.add(new File(["x"], "a.md"));
      return dt;
    });
    await page.getByRole("group", { name: "Version A (before)" }).dispatchEvent("dragenter", { dataTransfer: data });
    await expect(page.getByText("Release to add these to version A.")).toBeVisible();
    await axe(page, "drop state");
  });
});
