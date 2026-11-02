import { chromium, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Only GETs and browser-local mocked failures. Never seeds or changes server data.
const origin = process.argv[2] ?? "http://localhost:80";
const browser = await chromium.launch({
  headless: true,
  ...(process.argv[3] ? { executablePath: process.argv[3] } : {}),
  args: ["--no-sandbox"],
});
const screenshots = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../generated-artifacts/migration");
await mkdir(screenshots, { recursive: true });
const errors = [];
const evidence = (feed) => feed.events.map((event) => ({
  id: event.event_id, observed_at: event.observed_at, available_at: event.available_at,
  fresh_until: event.fresh_until, stale: event.stale, sources: event.sources,
}));
try {
  for (const [name, viewport] of [
    ["desktop", { width: 1280, height: 900 }],
    ["mobile", { width: 390, height: 844 }],
  ]) {
    const page = await browser.newPage({ viewport });
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(origin);
    const response = await page.request.get(`${origin}/api/discovery/events?limit=100&offset=0`);
    expect(response.status()).toBe(200);
    const baseline = await response.json();
    expect(baseline.mode).toBe("synthetic");
    expect(baseline.events.length).toBeGreaterThan(0);
    const count = baseline.events.length;
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Catch the nights");
    await expect(page.locator(".event-card")).toHaveCount(count);
    await expect(page.getByText(/No working sign-in, saved events, artist follows, alert management, ticket purchases, or live ticket links/)).toBeVisible();
    await expect(page.getByRole("searchbox")).toHaveAccessibleName(/on this page/);
    const refresh = page.getByRole("button", { name: "Refresh feed" });
    await expect(refresh).toHaveAccessibleDescription("Reloads stored observations only. Does not collect live events or update observation freshness.");

    // Navigation is visible and usable at each viewport, not hidden behind hover.
    await page.getByRole("link", { name: "About Sweet Seats" }).click();
    await expect(page).toHaveURL(/\/coming-soon\/$/);
    await expect(page.getByText("Synthetic demo available now. No connected waitlist.")).toBeVisible();
    await expect(page.locator("form, input")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Explore the discovery demo" })).toBeVisible();
    await page.screenshot({ path: path.join(screenshots, `${name}-brand.png`), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await page.getByRole("link", { name: "Explore the discovery demo" }).click();
    await expect(page).toHaveURL(`${origin}/`);
    await expect(page.locator(".event-card")).toHaveCount(count);

    const search = page.getByRole("searchbox");
    await search.fill(baseline.events[0].title);
    await expect(page.locator(".event-card")).toHaveCount(baseline.events.filter((event) =>
      [event.title, event.venue.name, event.venue.neighborhood, ...event.performers.map((p) => p.name)]
        .join(" ").toLowerCase().includes(baseline.events[0].title.toLowerCase())).length);
    await search.fill("zzzz-no-matching-concert");
    await expect(page.getByRole("heading", { name: "Nothing matches this search." })).toBeVisible();
    await search.fill("");
    const timesBefore = await page.locator(".event-card time[datetime]").evaluateAll((els) => els.map((el) => el.getAttribute("datetime")));
    const refreshedResponse = page.waitForResponse((r) => r.url().includes("/api/discovery/events?") && r.request().method() === "GET");
    await page.getByRole("button", { name: "Refresh feed" }).click();
    expect(evidence(await (await refreshedResponse).json())).toEqual(evidence(baseline));
    await expect(page.locator(".event-card")).toHaveCount(count);
    expect(await page.locator(".event-card time[datetime]").evaluateAll((els) => els.map((el) => el.getAttribute("datetime")))).toEqual(timesBefore);
    await expect(page.locator(".freshness.stale")).toHaveCount(baseline.events.filter((event) => event.stale).length);
    await page.screenshot({ path: path.join(screenshots, `${name}-feed.png`), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);

    const first = baseline.events[0];
    await page.locator(".event-card h3 a").first().click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(first.title);
    await expect(page.getByRole("heading", { name: "The source trail" })).toBeVisible();
    await expect(page.getByRole("button", { name: "No ticket link in this demo" })).toBeDisabled();
    if (first.stale) await expect(page.getByText("Stale observation. Recheck an official source before making plans.")).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(first.title);
    await page.getByRole("link", { name: "About Sweet Seats" }).click();
    await page.getByRole("link", { name: "Explore the discovery demo" }).click();

    for (const unknown of ["/inspection-unknown-route", "/events", "/events/one/extra"]) {
      await page.goto(`${origin}${unknown}`);
      await expect(page.getByRole("main")).toHaveAccessibleName("Page not found");
      await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
      await expect(page.locator(".event-card")).toHaveCount(0);
      await page.getByRole("link", { name: "Return to discovery home" }).click();
      await expect(page.locator(".event-card")).toHaveCount(count);
    }
    await page.goto(`${origin}/coming-soon/unknown`);
    await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
    await page.goto(`${origin}/events/00000000-0000-0000-0000-000000000000`);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("This event isn't available.");
    await page.getByRole("link", { name: "Back to all events" }).click();

    const apiPattern = "**/api/discovery/events?*";
    await page.route(apiPattern, (route) => route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ ...baseline, status: "unavailable", events: [] }),
    }));
    await page.getByRole("button", { name: "Refresh feed" }).click();
    await expect(page.getByRole("alert")).toContainText("Source unavailable.");
    await expect(page.getByText("No events returned.", { exact: true })).toHaveCount(0);
    await page.unroute(apiPattern);
    await page.route(apiPattern, (route) => route.fulfill({ status: 503, body: "{}" }));
    await page.getByRole("button", { name: "Refresh feed" }).click();
    await expect(page.getByRole("alert")).toContainText("Discovery is unavailable.");
    await page.unroute(apiPattern);
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.locator(".event-card")).toHaveCount(count);
    console.log(`PASS ${name} ${viewport.width}x${viewport.height}: reciprocal navigation, truthful disclosures, unknown routes, event deep links/reload, page-scoped search, refresh with unchanged timestamps/freshness, stale warnings, unavailable/503/retry, disabled tickets, no horizontal overflow.`);
    await page.close();
  }
  expect(errors).toEqual([]);
  console.log("PASS: no browser exceptions; server data was not mutated.");
} finally {
  await browser.close();
}
