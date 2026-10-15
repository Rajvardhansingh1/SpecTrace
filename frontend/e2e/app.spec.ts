import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const API = "http://localhost:8000";

async function compareSample(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Load petstore example" }).click();
  await page.getByRole("button", { name: "Compare versions" }).click();
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("v1 to v2");
}

test.describe("main flow", () => {
  test("compare the petstore versions and read the evidence for the breaking change", async ({ page }) => {
    await compareSample(page);

    // One breaking change, selected first, with the reason and a visible diff.
    await expect(page.getByRole("heading", { level: 2, name: "schema:Pet" })).toBeVisible();
    await expect(page.getByText("property id type changed string -> integer")).toBeVisible();
    await expect(page.getByText("+          type: integer")).toBeVisible();
    await expect(page.getByText(/7 dependents: 5 confirmed, 2 inferred/)).toBeVisible();

    // Confirmed and inferred dependents are labeled in words.
    const guide = page.locator("li.impact", { hasText: "section:docs/guide.md#listing-pets" });
    await expect(guide.getByText("Confirmed", { exact: true }).first()).toBeVisible();
    const requirement = page.locator("li.impact", { hasText: "requirement:REQ-001" });
    await expect(requirement.getByText(/Inferred 80%/).first()).toBeVisible();
    await expect(requirement.getByText(/At least one link is a guess/)).toBeVisible();

    // The cited line is fetched from the stored files and shown with its number.
    await guide.getByRole("button", { name: /Show source at docs\/guide.md:4/ }).click();
    const cited = page.locator(".snippet__line--cited", { hasText: "Call `GET /pets`" });
    await expect(cited).toBeVisible();
    await expect(cited.locator(".snippet__n")).toHaveText("4");
  });

  test("the cited OpenAPI line for an endpoint comes from the stored spec", async ({ page }) => {
    await compareSample(page);
    const endpoint = page.locator("li.impact", { hasText: "endpoint:GET /pets/{petId}" }).first();
    await endpoint.getByRole("button", { name: /Show source at openapi.yaml/ }).click();
    await expect(page.locator(".snippet__line--cited", { hasText: "$ref" })).toBeVisible();
  });

  test("ask a question, then ask one the data cannot answer", async ({ page }) => {
    await compareSample(page);
    await page.getByLabel("Question").fill("What breaks if Pet changes?");
    await page.getByRole("button", { name: "Ask" }).click();
    await expect(page.getByRole("heading", { name: "Impacts found" })).toBeVisible();
    await expect(page.locator(".answer li.impact").first()).toBeVisible();

    await page.getByLabel("Question").fill("What about the moon?");
    await page.getByRole("button", { name: "Ask" }).click();
    await expect(page.getByRole("heading", { name: "Not enough to answer" })).toBeVisible();
    await expect(page.locator(".answer li.impact")).toHaveCount(0);
  });

  test("filter the change list and open the history entry later", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Load petstore example" }).click();
    await page.getByRole("button", { name: "Compare versions" }).click();
    await expect(page.getByRole("button", { name: "Breaking (1)" })).toBeVisible();
    await page.getByRole("button", { name: "Documentation only (0)" }).count();

    await page.getByRole("link", { name: "Compare", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Earlier comparisons" })).toBeVisible();
    await page.getByRole("link", { name: "v1 to v2" }).first().click();
    await expect(page.getByRole("heading", { level: 2, name: "schema:Pet" })).toBeVisible();
  });
});

test.describe("own files, bad input and failures", () => {
  test("uploaded files are compared; unsupported ones are reported, not silently dropped", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("files-A").setInputFiles([
      { name: "guide.md", mimeType: "text/markdown", buffer: Buffer.from("## Setup\nInstall it.\n") },
      { name: "logo.png", mimeType: "image/png", buffer: Buffer.from("png") },
    ]);
    await page.getByTestId("files-B").setInputFiles({
      name: "guide.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("## Setup\nInstall it, then restart.\n"),
    });
    await expect(page.getByText(/Version A, logo\.png: unsupported file type/)).toBeVisible();
    await expect(page.getByText("1 file, 21 B")).toBeVisible();
    await page.getByRole("button", { name: "Compare versions" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "section:guide.md#setup" })).toBeVisible();
    await expect(page.getByText("Documentation only").first()).toBeVisible();
  });

  test("a file can be removed before comparing", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("files-A").setInputFiles({ name: "a.md", mimeType: "text/markdown", buffer: Buffer.from("# a") });
    await page.getByRole("button", { name: "Remove a.md from version A" }).click();
    await expect(page.getByText(/No files yet/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Compare versions" })).toBeDisabled();
  });

  test("invalid YAML shows a readable error and keeps the form", async ({ page }) => {
    await page.goto("/");
    const bad = { name: "openapi.yaml", mimeType: "text/yaml", buffer: Buffer.from("openapi: [unclosed\n") };
    await page.getByTestId("files-A").setInputFiles(bad);
    await page.getByTestId("files-B").setInputFiles(bad);
    await page.getByRole("button", { name: "Compare versions" }).click();
    await expect(page.locator(".notice[role=alert]")).toContainText("could not be read");
    await expect(page).toHaveURL("/");
    await expect(page.getByRole("button", { name: "Compare versions" })).toBeEnabled();
  });

  test("the backend being down is explained with the next step", async ({ page }) => {
    await page.route(`${API}/v1/runs`, (route) => (route.request().method() === "POST" ? route.abort() : route.continue()));
    await page.goto("/");
    await page.getByRole("button", { name: "Load petstore example" }).click();
    await page.getByRole("button", { name: "Compare versions" }).click();
    await expect(page.locator(".notice[role=alert]")).toContainText("could not be reached");
    await expect(page.locator(".notice[role=alert]")).toContainText("NEXT_PUBLIC_API_URL");
  });

  test("a rate limit says how long to wait", async ({ page }) => {
    await page.route(`${API}/v1/runs`, (route) =>
      route.request().method() === "POST"
        ? route.fulfill({
            status: 429,
            headers: { "content-type": "application/json", "retry-after": "17", "access-control-allow-origin": "*", "access-control-expose-headers": "retry-after" },
            body: JSON.stringify({ error: { code: "rate_limited", message: "too many requests" } }),
          })
        : route.continue(),
    );
    await page.goto("/");
    await page.getByRole("button", { name: "Load petstore example" }).click();
    await page.getByRole("button", { name: "Compare versions" }).click();
    await expect(page.locator(".notice[role=alert]")).toContainText("Try again in 17 seconds");
  });

  test("an unknown comparison id shows a not-found message with a way back", async ({ page }) => {
    await page.goto("/runs/not-a-real-id");
    await expect(page.locator(".notice[role=alert]")).toContainText("does not exist");
    await expect(page.getByRole("link", { name: "Back to Compare" })).toBeVisible();
  });

  test("an unknown page shows the not-found page", async ({ page }) => {
    const response = await page.goto("/nothing-here");
    expect(response?.status()).toBe(404);
    await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  });

  test("a comparison with no differences says so", async ({ page }) => {
    await page.goto("/");
    const same = { name: "a.md", mimeType: "text/markdown", buffer: Buffer.from("## A\ntext\n") };
    await page.getByTestId("files-A").setInputFiles(same);
    await page.getByTestId("files-B").setInputFiles(same);
    await page.getByRole("button", { name: "Compare versions" }).click();
    await expect(page.getByText("No differences found")).toBeVisible();
  });
});

test.describe("benchmark page", () => {
  test("shows both systems, the evidence checks and the limits of the labels", async ({ page }) => {
    await page.goto("/benchmark");
    await expect(page.getByRole("heading", { name: "Benchmark", level: 1 })).toBeVisible();
    await expect(page.getByRole("cell", { name: "Keyword baseline" }).first()).toBeVisible();
    await expect(page.getByRole("cell", { name: "SpecTrace" }).first()).toBeVisible();
    await expect(page.getByText("Impacts without a valid evidence path")).toBeVisible();
    await expect(page.getByText(/no person has reviewed them/)).toBeVisible();
    await expect(page.getByRole("cell", { name: "c04-transitive-chain" })).toBeVisible();
  });
});

test.describe("keyboard", () => {
  test("the whole flow works without a mouse and focus is always visible", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#main$/);

    await page.getByRole("button", { name: "Load petstore example" }).focus();
    const outline = await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle);
    expect(outline).not.toBe("none");
    await page.keyboard.press("Enter");

    await page.getByRole("button", { name: "Compare versions" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("v1 to v2");

    const second = page.getByRole("list", { name: "Changes" }).getByRole("button").first();
    await second.focus();
    await page.keyboard.press("Space");
    await expect(page.getByRole("heading", { level: 2, name: "schema:Pet" })).toBeFocused();

    // The button renames itself from "Show" to "Hide", so match both.
    const toggle = page.getByRole("button", { name: /source at/ }).first();
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator(".snippet__line--cited").first()).toBeVisible();
  });
});

test.describe("accessibility with axe", () => {
  for (const scheme of ["light", "dark"] as const) {
    test(`no violations on every screen in ${scheme} mode`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      const scan = async (label: string) => {
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
          .analyze();
        expect(results.violations.map((v) => `${label}: ${v.id} ${v.nodes.map((n) => n.target).join(",")}`)).toEqual([]);
      };

      await page.goto("/");
      await scan("compare, empty");
      await page.getByRole("button", { name: "Load petstore example" }).click();
      await scan("compare, filled");
      await page.getByRole("button", { name: "Compare versions" }).click();
      await expect(page.getByRole("heading", { level: 1 })).toContainText("v1 to v2");
      await page.getByRole("button", { name: /Show source at/ }).first().click();
      await expect(page.locator(".snippet__line--cited").first()).toBeVisible();
      await page.getByLabel("Question").fill("What breaks if Pet changes?");
      await page.getByRole("button", { name: "Ask" }).click();
      await expect(page.getByRole("heading", { name: "Impacts found" })).toBeVisible();
      await scan("run, with evidence and answer");
      await page.goto("/benchmark");
      await scan("benchmark");
      await page.goto("/nothing-here");
      await scan("not found");
    });
  }
});

test.describe("small screens", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("no horizontal overflow and tap targets of 44px on the main screens", async ({ page }) => {
    const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    const smallTargets = () =>
      page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>("button, nav a, input[type=text]")]
          .filter((el) => el.offsetParent !== null)
          .map((el) => ({ text: (el.textContent || el.getAttribute("aria-label") || el.tagName).trim().slice(0, 30), h: el.getBoundingClientRect().height }))
          .filter((t) => t.h < 43.5),
      );

    await page.goto("/");
    expect(await overflow()).toBeLessThanOrEqual(0);
    expect(await smallTargets()).toEqual([]);

    await page.getByRole("button", { name: "Load petstore example" }).click();
    expect(await overflow()).toBeLessThanOrEqual(0);
    await page.getByRole("button", { name: "Compare versions" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("v1 to v2");
    await page.getByRole("button", { name: /Show source at/ }).first().click();
    expect(await overflow()).toBeLessThanOrEqual(0);
    expect(await smallTargets()).toEqual([]);

    // On a phone the detail sits below the list; choosing a change must bring the reader to it.
    await page.getByRole("list", { name: "Changes" }).getByRole("button").first().click();
    await expect(page.getByRole("heading", { level: 2, name: "schema:Pet" })).toBeInViewport();

    await page.goto("/benchmark");
    expect(await overflow()).toBeLessThanOrEqual(0);
  });

  test("still usable at 320px width", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto("/");
    await page.getByRole("button", { name: "Load petstore example" }).click();
    await page.getByRole("button", { name: "Compare versions" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("v1 to v2");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});

test.describe("server safety", () => {
  test("the page never sends the database URL or any secret to the browser", async ({ page }) => {
    const bodies: string[] = [];
    page.on("response", async (r) => {
      if (r.url().startsWith("http://localhost:3000") && /javascript|html|json/.test(r.headers()["content-type"] ?? "")) {
        bodies.push(await r.text().catch(() => ""));
      }
    });
    await compareSample(page);
    const all = bodies.join("\n");
    expect(all).not.toMatch(/postgres(ql)?(\+\w+)?:\/\//);
    expect(all).not.toMatch(/SPECTRACE_DATABASE_URL|service_role|sb_secret/);
  });
});
