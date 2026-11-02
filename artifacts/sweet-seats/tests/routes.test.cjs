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
  const source = fs.readFileSync(filename, 'utf8').replace(/import\.meta\.env\.BASE_URL/g, '"/"');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  const m = new Module(filename, module);
  m.filename = filename;
  m.paths = Module._nodeModulePaths(path.dirname(filename));
  cache.set(filename, m);
  m.require = (id) => id.startsWith('.')
    ? load(path.resolve(path.dirname(filename), id + (path.extname(id) ? '' : '.tsx')))
    : require(require.resolve(id, { paths: [path.dirname(filename)] }));
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
