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
    if (id.startsWith('@workspace/sweet-seats-design-system/components/ui/')) {
      const name = id.split('/').at(-1);
      const element = (tag) => function Component({ children, variant: _variant, ...props }) {
        return React.createElement(tag, props, children);
      };
      if (name === 'button') return { Button: element('button') };
      if (name === 'link') return { Link: element('a') };
      if (name === 'field') return {
        Field: element('div'),
        FieldLabel: element('label'),
        FieldControl: element('input'),
        FieldHelp: element('p'),
      };
      if (name === 'status') return {
        StatusMessage: ({ tone, role, children, ...props }) =>
          React.createElement('p', { ...props, role: role ?? (tone === 'error' ? 'alert' : 'status'), 'data-tone': tone }, children),
      };
    }
    if (id.endsWith('.png')) return '/test-sweet-seats-logo.png';
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
  assert.match(html, /Your next night starts here/);
  assert.match(html, /href="\/coming-soon\/"/);
  assert.match(html, /No working sign-in, saved events, artist follows, alert management, ticket purchases, or live ticket links/);
});
test('screens consume the linked design-system controls and theme', () => {
  const discovery = fs.readFileSync(path.resolve(__dirname, '../src/app/discovery.tsx'), 'utf8');
  const theme = fs.readFileSync(path.resolve(__dirname, '../src/app/globals.css'), 'utf8');
  assert.match(discovery, /components\/ui\/button/);
  assert.match(discovery, /components\/ui\/field/);
  assert.match(discovery, /components\/ui\/status/);
  assert.match(theme, /@import "@workspace\/sweet-seats-design-system\/styles\.css"/);
});
test('the living style guide is development-only and absent from the production route set', () => {
  const html = render('/style-guide');
  const source = fs.readFileSync(path.resolve(__dirname, '../src/App.tsx'), 'utf8');
  assert.match(source, /import\.meta\.env\.DEV \? lazy/);
  assert.match(source, /StyleGuide && <Route path="\/style-guide"/);
  assert.match(html, /does not match a Sweet Seats discovery page/);
  assert.doesNotMatch(html, /One shared|DEVELOPMENT STYLE GUIDE/);
});
test('unknown discovery paths render a dedicated accessible not-found page and home action', () => {
  for (const p of ['/not-a-page', '/events', '/events/one/extra']) {
    const html = render(p);
    assert.match(html, /<main[^>]+aria-labelledby="not-found-title"/);
    assert.match(html, /<h1 id="not-found-title">That page isn’t here/);
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
