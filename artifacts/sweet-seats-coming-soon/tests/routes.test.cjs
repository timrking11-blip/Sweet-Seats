// Renders the ported TSX with TypeScript + react-dom/server under node:test.
/* eslint-disable @typescript-eslint/no-require-imports -- Node CommonJS test harness. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { Router } = require('wouter');

const BASE = '/coming-soon/';
const cache = new Map();
function load(file) {
  const filename = require.resolve(file);
  if (cache.has(filename)) return cache.get(filename).exports;
  const source = fs.readFileSync(filename, 'utf8')
    .replace(/import\.meta\.env\.BASE_URL/g, JSON.stringify(BASE))
    .replace(/import\.meta\.env\.DEV/g, 'false');
  const out = ts.transpileModule(source, {
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
  m._compile(out, filename);
  return m.exports;
}
const { AppRoutes } = load(path.resolve(__dirname, '../src/App.tsx'));
const render = (p) => renderToStaticMarkup(React.createElement(Router, { base: '/coming-soon', ssrPath: p }, React.createElement(AppRoutes)));

test('/ renders the coming-soon landing page', () => {
  const html = render('/coming-soon/');
  assert.match(html, /Be there/);
  assert.match(html, /good stuff\./);
  assert.match(html, /Finding a great show should feel easy\./);
  assert.match(html, /src="\/coming-soon\/sweet-seats-logo\.svg"/);
  assert.match(html, /href="\/coming-soon\/"/);
  assert.match(html, /href="https:\/\/github\.com\/timrking11-blip"/);
  assert.match(html, /id="the-idea"/);
  assert.doesNotMatch(html, /Page not found/);
  assert.match(html, /href="\/"[^>]*>Explore the discovery demo/);
  assert.match(html, /class="ss-button ss-button--primary/);
  assert.match(html, /class="ss-link/);
  assert.match(html, /No connected waitlist/);
  assert.doesNotMatch(html, /<form|<input|Join the waitlist/);
});

test('unknown routes render the original 404 with a base-aware home link', () => {
  const html = render('/coming-soon/nope');
  assert.match(html, /404/);
  assert.match(html, /Page not found/);
  assert.match(html, /href="\/coming-soon\/"/);
});
