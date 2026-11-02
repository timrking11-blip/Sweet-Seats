import { chromium, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const origin = process.argv[2] ?? "http://localhost:80";
const browser = await chromium.launch({
  headless: true,
  ...(process.argv[3] ? { executablePath: process.argv[3] } : {}),
  args: ["--no-sandbox"],
});
const out = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../generated-artifacts/foundation");
await mkdir(out, { recursive: true });
const errors = [];
const results = [];
const rgb = (color) => color.match(/[\d.]+/g).slice(0, 3).map(Number);
const luminance = (color) => rgb(color).map((v) => v / 255)
  .map((v) => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
  .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a, b) => (Math.max(luminance(a), luminance(b)) + 0.05) / (Math.min(luminance(a), luminance(b)) + 0.05);
try {
  const page = await browser.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const pages = process.argv[4] === "guide-only"
      ? [["guide", "/style-guide"]]
      : [["discovery", "/"], ["public", "/coming-soon/"], ["guide", "/style-guide"]];
    for (const [name, route] of pages) {
      await page.goto(`${origin}${route}`);
      await expect(page.locator("h1")).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-ss-brand", "midnight-session");
      await expect(page.locator(".ss-button").first()).toBeVisible();
      if (name === "discovery") await expect(page.locator(".event-card").first()).toBeVisible();
      const computed = await page.evaluate(() => {
        const root = getComputedStyle(document.documentElement);
        const body = getComputedStyle(document.body);
        const h1 = document.querySelector("h1");
        const control = document.querySelector(".ss-button--primary");
        const cs = control && getComputedStyle(control);
        return {
          width: innerWidth,
          overflow: document.documentElement.scrollWidth > innerWidth,
          tokenBackground: root.getPropertyValue("--ss-bg").trim(),
          background: body.backgroundColor,
          text: body.color,
          headingFont: getComputedStyle(h1).fontFamily,
          action: cs && { background: cs.backgroundColor, text: cs.color, height: control.getBoundingClientRect().height },
        };
      });
      expect(computed.overflow, `${name} ${width} overflow`).toBe(false);
      expect(computed.tokenBackground).toBe("#031126");
      expect(computed.background).toBe("rgb(3, 17, 38)");
      expect(computed.headingFont).not.toMatch(/Georgia|Times/);
      expect(contrast(computed.text, computed.background)).toBeGreaterThanOrEqual(4.5);
      if (computed.action) {
        expect(computed.action.background).toBe("rgb(255, 98, 77)");
        expect(computed.action.height).toBeGreaterThanOrEqual(44);
        expect(contrast(computed.action.text, computed.action.background)).toBeGreaterThanOrEqual(4.5);
      }
      if (name === "guide") {
        const swatches = await page.locator(".guide-swatch").evaluateAll((els) => els.map((el) => {
          const css = getComputedStyle(el);
          return { text: css.color, background: css.backgroundColor };
        }));
        for (const swatch of swatches) expect(contrast(swatch.text, swatch.background)).toBeGreaterThanOrEqual(4.5);
      }
      await page.screenshot({ path: path.join(out, `${name}-${width}.png`), fullPage: width === 390 || width === 1440 });
      results.push({ page: name, width, ...computed });
    }
  }

  await page.goto(`${origin}/style-guide`);
  await page.keyboard.press("Tab");
  const focus = await page.evaluate(() => {
    const el = document.activeElement;
    const css = getComputedStyle(el);
    return { tag: el.tagName, outline: css.outlineStyle, width: css.outlineWidth };
  });
  expect(focus.tag).toBe("A");
  expect(focus.outline).not.toBe("none");
  expect(parseFloat(focus.width)).toBeGreaterThanOrEqual(2);

  const input = page.locator("input:not([disabled])").first();
  await expect(input).toHaveAccessibleName(/.+/);
  await input.fill("A deliberately long artist and venue name for the shared form example");
  await expect(input).toHaveValue(/deliberately long/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await expect(page.locator("button[disabled]").first()).toBeDisabled();

  await page.emulateMedia({ reducedMotion: "reduce" });
  const motion = await page.evaluate(() => ({
    scroll: getComputedStyle(document.documentElement).scrollBehavior,
    transitions: getComputedStyle(document.querySelector(".ss-button")).transitionDuration,
  }));
  expect(motion.scroll).toBe("auto");
  expect(motion.transitions.split(",").every((v) => parseFloat(v) <= 0.01)).toBe(true);
  expect(errors).toEqual([]);
  await writeFile(path.join(out, process.argv[4] === "guide-only" ? "guide-checks.json" : "checks.json"), JSON.stringify({ results, keyboardFocus: focus, reducedMotion: motion, browserErrors: errors }, null, 2));
  console.log(`PASS: ${results.length} page/viewport cases; shared palette, sans typography, primary action contrast/44px target, no overflow; keyboard focus, labeled long-text control, disabled example and reduced motion; no browser exceptions.`);
} finally {
  await browser.close();
}
