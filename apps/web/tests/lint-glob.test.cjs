// Preserve the exact glob API used by the pinned Next.js ESLint plugin.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join } = require("node:path");
const { createRequire } = require("node:module");
const pluginRequire = createRequire(require.resolve("@next/eslint-plugin-next"));
const { getRootDirs } = pluginRequire("./utils/get-root-dirs.js");

test("Next root discovery retains directories, string/array globs and default cwd", () => {
  const root = mkdtempSync(join(tmpdir(), "sweet-seats-lint-"));
  try {
    mkdirSync(join(root, "one"));
    mkdirSync(join(root, "two"));
    writeFileSync(join(root, "file"), "not a directory");
    const context = (rootDir) => ({ cwd: root, settings: { next: { rootDir } } });
    assert.deepEqual(getRootDirs(context(undefined)), [root]);
    assert.deepEqual(getRootDirs(context(root + "/*")).sort(), [join(root, "one"), join(root, "two")].sort());
    assert.deepEqual(getRootDirs(context([root + "/one", root + "/two"])).sort(), [join(root, "one"), join(root, "two")].sort());
    assert.deepEqual(getRootDirs(context(root + "/{one,two}")).sort(), [join(root, "one"), join(root, "two")].sort());
    assert.deepEqual(getRootDirs(context(root + "/missing*")), []);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("Next core web vitals rules remain enabled", () => {
  const plugin = require("@next/eslint-plugin-next");
  assert.equal(plugin.configs["core-web-vitals"].rules["@next/next/no-html-link-for-pages"], "error");
  assert.equal(plugin.configs.recommended.rules["@next/next/no-img-element"], "warn");
});
