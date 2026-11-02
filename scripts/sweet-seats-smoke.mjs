import { chromium, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Optional second argument selects a system Chromium; otherwise use Playwright's.
const origin = process.argv[2] ?? "http://localhost:80";
const browser = await chromium.launch({
  headless: true,
  ...(process.argv[3] ? { executablePath: process.argv[3] } : {}),
  args: ["--no-sandbox"],
});
const screenshots = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../generated-artifacts/migration");
await mkdir(screenshots, { recursive: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
try {
  await page.goto(origin);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Catch the nights");
  await expect(page.locator(".event-card")).toHaveCount(3);
  await page.getByRole("link", { name: /Explore the demo/ }).click();
  const search = page.getByRole("searchbox");
  await search.fill("Violet Static");
  await expect(page.locator(".event-card").first()).toContainText("Violet Static");
  await search.fill("Brooklyn");
  await expect(page.locator(".event-card").first()).toContainText("Brooklyn");
  await search.fill("zzzz-no-matching-concert");
  await expect(page.getByRole("heading", { name: "Nothing matches this search." })).toBeVisible();
  await search.fill("");
  await page.getByRole("button", { name: "Refresh feed" }).click();
  await expect(page.locator(".event-card")).toHaveCount(3);
  await page.screenshot({ path: path.join(screenshots, "desktop-feed.png"), fullPage: true });
  const link = page.locator(".event-card h3 a").first();
  const title = await link.innerText();
  await link.click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
  await expect(page.getByRole("heading", { name: "The lineup" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "The source trail" })).toBeVisible();
  await expect(page.getByRole("button", { name: "No ticket link in this demo" })).toBeDisabled();
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
  await page.screenshot({ path: path.join(screenshots, "event-detail.png"), fullPage: true });
  await page.getByRole("link", { name: /All events/ }).click();
  await expect(page.locator(".event-card")).toHaveCount(3);
  await page.goto(`${origin}/events/00000000-0000-0000-0000-000000000000`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("This event isn't available.");
  await page.getByRole("link", { name: "Back to all events" }).click();
  await expect(page.locator(".event-card")).toHaveCount(3);
  // Exercise the actual client retry after an upstream failure.
  await page.route("**/api/discovery/events?*", (route) => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Refresh feed" }).click();
  await expect(page.getByRole("alert")).toContainText("Discovery is unavailable.");
  await page.unroute("**/api/discovery/events?*");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator(".event-card")).toHaveCount(3);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(origin);
  await expect(page.locator(".event-card")).toHaveCount(3);
  const overflows = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  expect(overflows).toBe(false);
  await page.screenshot({ path: path.join(screenshots, "mobile.png"), fullPage: true });
  expect(errors).toEqual([]);
  console.log("PASS: feed, search, empty state, refresh, detail, deep-link reload, missing event, error/retry, mobile layout; no browser exceptions.");
} finally {
  await browser.close();
}
