/* eslint-disable @typescript-eslint/no-require-imports -- Existing Node render-test harness. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { Router } = require('wouter');
const cache = new Map();
function load(file) {
  const filename = require.resolve(file);
  if (cache.has(filename)) return cache.get(filename).exports;
  const source = fs.readFileSync(filename, 'utf8')
    .replace(/import\.meta\.env\.BASE_URL/g, '"/"')
    .replace(/import\.meta\.env\.DEV/g, 'false');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  const m = new Module(filename, module);
  m.filename = filename;
  m.paths = Module._nodeModulePaths(path.dirname(filename));
  cache.set(filename, m);
  m.require = (id) => {
    if (!id.startsWith('.')) return require(require.resolve(id, { paths: [path.dirname(filename)] }));
    const request = path.resolve(path.dirname(filename), id);
    const resolved = path.extname(request) ? request : ['.tsx', '.ts', '.js'].map((ext) => request + ext).find((candidate) => fs.existsSync(candidate));
    if (!resolved) throw new Error(`Cannot resolve ${id} from ${filename}`);
    return load(resolved);
  };
  m._compile(compiled, filename);
  return m.exports;
}
const { AppRoutes } = load(path.resolve(__dirname, '../src/App.tsx'));
const render = (ssrPath) => renderToStaticMarkup(React.createElement(Router, { ssrPath }, React.createElement(AppRoutes)));
test('only the root renders discovery home, including honest limitations and brand navigation', () => {
  const html = render('/');
  assert.match(html, /Catch the nights/);
  assert.match(html, /href="\/coming-soon\/"/);
  assert.match(html, /No working sign-in, saved events, artist follows, alert management, ticket purchases, or live ticket links/);
});
test('shared discovery controls expose native primitive and focus/target semantics', () => {
  const discovery = fs.readFileSync(path.resolve(__dirname, '../src/app/discovery.tsx'), 'utf8');
  const controls = fs.readFileSync(path.resolve(__dirname, '../../../lib/sweet-seats-brand/controls.css'), 'utf8');
  assert.match(discovery, /ss-button/);
  assert.match(discovery, /ss-control/);
  assert.match(discovery, /ss-status/);
  assert.match(controls, /min-height: var\(--ss-target-min\)/);
  assert.match(controls, /:focus-visible/);
  assert.match(controls, /prefers-reduced-motion/);
});
test('the living style guide is development-only and absent from the production route set', () => {
  const html = render('/style-guide');
  const source = fs.readFileSync(path.resolve(__dirname, '../src/App.tsx'), 'utf8');
  assert.match(source, /import\.meta\.env\.DEV \? lazy/);
  assert.match(source, /StyleGuide && <Route path="\/style-guide"/);
  assert.match(html, /Page not found/);
  assert.doesNotMatch(html, /One shared|DEVELOPMENT STYLE GUIDE/);
});
test('unknown discovery paths render a dedicated accessible not-found page and home action', () => {
  for (const p of ['/not-a-page', '/events', '/events/one/extra']) {
    const html = render(p);
    assert.match(html, /<main[^>]+aria-labelledby="not-found-title"/);
    assert.match(html, /<h1 id="not-found-title">Page not found/);
    assert.match(html, /href="\/">Return to discovery home/);
    assert.doesNotMatch(html, /Catch the nights/);
  }
});
test('event deep links still match the detail route, not home or not-found', () => {
  const html = render('/events/00000000-0000-0000-0000-000000000000');
  assert.match(html, /Loading event details/);
  assert.match(html, /href="\/coming-soon\/"/);
  assert.doesNotMatch(html, /Page not found|Catch the nights/);
});
