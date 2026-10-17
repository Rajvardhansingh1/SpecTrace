import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

const API = "http://localhost:8000";

async function openRun(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Load petstore example" }).click();
  await page.getByRole("button", { name: "Compare versions" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("v1 to v2");
}

const capabilities = (over: object = {}) => ({
  llm: { enabled: true, model: "provider/model-x" },
  embeddings: { enabled: true, model: "emb" },
  sends_documents_to: [],
  ...over,
});

const envelope = (status: number, code: string, message = "m") => ({
  status,
  headers: { "content-type": "application/json", "access-control-allow-origin": "*" },
  body: JSON.stringify({ error: { code, message } }),
});

test.describe("summary", () => {
  test("is written only when asked, cites its sources, and is saved with the comparison", async ({ page }) => {
    const sent: string[] = [];
    page.on("request", (r) => {
      if (r.url().endsWith("/narrative")) sent.push(r.method());
    });
    await openRun(page);
    // Nothing is sent to a model before the click, and the page says where the text would go.
    await expect(page.getByText(/No document text is sent to a third party/)).toBeVisible();
    expect(sent).toEqual([]);

    await page.getByRole("button", { name: "Summarize both versions" }).click();
    for (const name of ["What changed", "Version v1", "Version v2"]) {
      await expect(page.getByRole("region", { name })).toBeVisible();
    }
    const changes = page.getByRole("region", { name: "What changed" });
    await expect(changes.getByText(/Test summary/)).toBeVisible();
    await expect(page.getByText(/Written by/)).toContainText("test-model");

    // A source opens to the exact text the summary was built from.
    const first = changes.getByRole("list", { name: "Sources for What changed" }).getByRole("listitem").first();
    await first.getByText(/schema:Pet/).first().click();
    await expect(first.locator(".source__text")).toContainText("Classification: breaking");

    // Reloading shows the saved summary without asking the model again.
    sent.length = 0;
    await page.reload();
    await expect(page.getByRole("region", { name: "What changed" })).toBeVisible();
    expect(sent).toEqual([]);
    await expect(page.getByRole("button", { name: "Summarize both versions" })).toHaveCount(0);

    await page.getByRole("button", { name: "Write it again" }).click();
    await expect.poll(() => sent.length).toBe(1);
  });

  test("names the provider that would receive the documents before anything is sent", async ({ page }) => {
    await page.route(`${API}/v1/capabilities`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "content-type": "application/json", "access-control-allow-origin": "*" },
        body: JSON.stringify(capabilities({ sends_documents_to: ["OpenRouter"] })),
      }),
    );
    await openRun(page);
    await expect(page.getByText("Writing the summary sends the text of both versions to OpenRouter.")).toBeVisible();
    await expect(page.getByLabel("Question")).toHaveAccessibleDescription(/sent to OpenRouter/);
  });

  test("says it is off, and the rest still works, when the server has no model", async ({ page }) => {
    await page.route(`${API}/v1/capabilities`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "content-type": "application/json", "access-control-allow-origin": "*" },
        body: JSON.stringify(capabilities({ llm: { enabled: false, model: null }, sends_documents_to: [] })),
      }),
    );
    await openRun(page);
    await expect(page.getByText(/Written summaries are off/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Summarize both versions" })).toHaveCount(0);
    await expect(page.getByLabel("Question")).toHaveAccessibleDescription(/matches names only/);
    await expect(page.getByRole("heading", { level: 2, name: "schema:Pet" })).toBeVisible();
  });

  test("a model failure is explained and the comparison stays usable", async ({ page }) => {
    await page.route(`${API}/v1/runs/*/narrative`, (route) => route.fulfill(envelope(502, "llm_bad_output")));
    await openRun(page);
    await page.getByRole("button", { name: "Summarize both versions" }).click();
    await expect(page.locator(".notice[role=alert]")).toContainText("could not be used");
    await expect(page.getByRole("button", { name: "Summarize both versions" })).toBeEnabled();
    await expect(page.getByRole("heading", { level: 2, name: "schema:Pet" })).toBeVisible();
  });
});

test.describe("questions with a model", () => {
  test("a question in plain words is answered from sources that can be opened", async ({ page }) => {
    await openRun(page);
    await page.getByLabel("Question").fill("What do the docs need after the Pet change?");
    await page.getByRole("button", { name: "Ask" }).click();

    await expect(page.getByRole("heading", { name: "Answer", exact: true })).toBeVisible();
    const answer = page.locator(".answer");
    await expect(answer.getByText(/Test answer based on the supplied context/)).toBeVisible();
    await expect(answer.getByText(/Written by/)).toContainText("test-model");
    // Passages were found by meaning as well as by keywords.
    await expect(answer.getByText(/found by keywords only/)).toHaveCount(0);

    const sources = answer.getByRole("list", { name: "Sources" });
    await expect(sources.getByRole("listitem").first()).toContainText("schema:Pet");
    await sources.getByRole("listitem").first().locator("summary").click();
    await expect(sources.locator(".source__text").first()).toBeVisible();

    // The deterministic evidence is still shown, labeled as coming from the graph.
    await expect(answer.getByRole("heading", { name: "Dependents found in the dependency graph" })).toBeVisible();
    await expect(answer.locator("li.impact").first()).toBeVisible();
  });

  test("a question the documents cannot answer is not sent for a made-up answer", async ({ page }) => {
    await openRun(page);
    await page.getByLabel("Question").fill("zzzz qqqq xxxx");
    await page.getByRole("button", { name: "Ask" }).click();
    await expect(page.getByRole("heading", { name: "Not enough to answer" })).toBeVisible();
    await expect(page.locator(".answer").getByText(/Nothing in the compared documents relates/)).toBeVisible();
    await expect(page.locator(".answer").getByRole("list", { name: "Sources" })).toHaveCount(0);
  });

  test("an unusable reply from the model is never shown", async ({ page }) => {
    await page.route(`${API}/v1/runs/*/ask`, (route) => route.fulfill(envelope(502, "llm_bad_output")));
    await openRun(page);
    await page.getByLabel("Question").fill("What breaks if Pet changes?");
    await page.getByRole("button", { name: "Ask" }).click();
    await expect(page.locator(".notice[role=alert]")).toContainText("nothing is shown");
  });

  test("the spending limit is explained", async ({ page }) => {
    await page.route(`${API}/v1/runs/*/ask`, (route) => route.fulfill(envelope(429, "budget_exceeded")));
    await openRun(page);
    await page.getByLabel("Question").fill("What breaks if Pet changes?");
    await page.getByRole("button", { name: "Ask" }).click();
    await expect(page.locator(".notice[role=alert]")).toContainText("limit for language-model requests");
  });
});

test.describe("privacy between visitors", () => {
  async function visitor(browser: Browser) {
    const context = await browser.newContext(); // separate storage, so a separate owner token
    return { context, page: await context.newPage() };
  }

  test("another browser cannot open, list or read someone else's comparison", async ({ browser, page }) => {
    await openRun(page);
    const url = page.url();
    await page.getByRole("button", { name: "Summarize both versions" }).click();
    await expect(page.getByRole("region", { name: "What changed" })).toBeVisible();

    const other = await visitor(browser);
    await other.page.goto(url);
    await expect(other.page.locator(".notice[role=alert]")).toContainText("does not exist");

    await other.page.goto("/");
    await expect(other.page.getByText("No comparisons yet")).toBeVisible();
    await other.context.close();

    // The same browser still sees it.
    await page.goto("/");
    await expect(page.getByRole("link", { name: "v1 to v2" }).first()).toBeVisible();
  });

  test("direct API calls without the owner token are refused", async ({ request }) => {
    const list = await request.get(`${API}/v1/runs`);
    expect(list.status()).toBe(401);
    expect((await list.json()).error.code).toBe("owner_required");
    const guess = await request.get(`${API}/v1/runs/00000000-0000-4000-8000-000000000000`, {
      headers: { "X-Owner-Token": "a-token-that-owns-nothing-1234" },
    });
    expect(guess.status()).toBe(404);
  });
});

test.describe("accessibility and layout of the new parts", () => {
  async function withSummaryAndAnswer(page: Page) {
    await openRun(page);
    await page.getByRole("button", { name: "Summarize both versions" }).click();
    await expect(page.getByRole("region", { name: "What changed" })).toBeVisible();
    await page.getByRole("region", { name: "What changed" }).getByText(/schema:Pet/).first().click();
    await page.getByLabel("Question").fill("What breaks if Pet changes?");
    await page.getByRole("button", { name: "Ask" }).click();
    await expect(page.getByRole("heading", { name: "Answer", exact: true })).toBeVisible();
    await page.locator(".answer .source summary").first().click();
  }

  for (const scheme of ["light", "dark"] as const) {
    test(`axe finds no violations with the summary, sources and answer open (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await withSummaryAndAnswer(page);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
        .analyze();
      expect(results.violations.map((v) => `${v.id} ${v.nodes.map((n) => n.target).join(",")}`)).toEqual([]);
    });
  }

  test("sources open and close from the keyboard, and the consent button is reachable", async ({ page }) => {
    await openRun(page);
    const button = page.getByRole("button", { name: "Summarize both versions" });
    await button.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "What changed" })).toBeVisible();
    const summary = page.getByRole("region", { name: "What changed" }).locator(".source summary").first();
    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(summary.locator("xpath=..")).toHaveAttribute("open", "");
    await page.keyboard.press("Space");
    await expect(summary.locator("xpath=..")).not.toHaveAttribute("open", "");
  });

  test("no sideways scrolling and 44px targets on a phone with everything open", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await withSummaryAndAnswer(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    const small = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>("button, summary, input[type=text]")]
        .filter((el) => el.offsetParent !== null)
        .map((el) => ({ t: (el.textContent || el.tagName).trim().slice(0, 30), h: el.getBoundingClientRect().height }))
        .filter((x) => x.h < 43.5),
    );
    expect(small).toEqual([]);
  });

  test("forced colors keep the citation markers readable", async ({ page }) => {
    await page.emulateMedia({ forcedColors: "active" });
    await withSummaryAndAnswer(page);
    await expect(page.locator(".answer .cite").first()).toBeVisible();
  });
});
