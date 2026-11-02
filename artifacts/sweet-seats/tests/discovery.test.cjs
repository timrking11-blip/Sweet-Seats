// Render actual TSX with the existing TypeScript/React packages and Node's test runner.
/* eslint-disable @typescript-eslint/no-require-imports -- Node CommonJS test harness. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const filename = path.resolve(__dirname, '../src/app/discovery.tsx');
const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;
const component = new Module(filename, module);
component.filename = filename;
component.paths = Module._nodeModulePaths(path.dirname(filename));
component._compile(compiled, filename);
const { DiscoveryFeedView, eventTime } = component.exports;
const event = {
  event_id: 'demo-event', title: 'Synthetic Night', status: 'rescheduled',
  venue: { name: 'Demo Room', neighborhood: 'Brooklyn' },
  performers: [{ name: 'Demo Artist' }], local_date: '2026-11-06',
  timezone: 'America/New_York', starts_at: '2026-11-07T01:00:00Z',
  observed_at: '2026-10-18T06:50:00Z', stale: false, sources: [],
};
const base = { mode: 'synthetic', status: 'ready', review_count: 0, unresolved: [],
  events: [event], collections: [], pagination: { total: 1, offset: 0, limit: 100, next_offset: null } };
function render(result) {
  return renderToStaticMarkup(React.createElement(DiscoveryFeedView, { result, retry() {} }));
}
test('loading exposes an accessible busy status', () => {
  const html = render({ state: 'loading' });
  assert.match(html, /aria-busy="true"/);
  assert.match(html, /Loading the local event feed/);
});
test('network failure renders an alert and retry', () => {
  const html = render({ state: 'error' });
  assert.match(html, /role="alert"/);
  assert.match(html, /Try again/);
});
test('empty is distinct from an unavailable source', () => {
  const html = render({ state: 'ready', data: { ...base, status: 'empty', events: [] } });
  assert.match(html, /No events returned/);
  assert.match(html, /does not mean tickets are sold out/);
});
test('partial feed retains artists, venue, status and event-local time', () => {
  const html = render({ state: 'ready', data: { ...base, status: 'partial' } });
  for (const text of ['A source failed', 'Demo Artist', 'Demo Room', 'Brooklyn', 'rescheduled', '8:00 PM EST']) {
    assert.ok(html.includes(text), text);
  }
  assert.equal(eventTime({ ...event, starts_at: null }), 'Time to be announced');
});
test('unresolved identities remain visible without inventing an event', () => {
  const html = render({ state: 'ready', data: { ...base, review_count: 1,
    unresolved: [{ source_record_id: 'unresolved', title: 'Unknown Night' }] } });
  assert.match(html, /Unresolved identities/);
  assert.match(html, /Unknown Night/);
  assert.match(html, /no match was guessed/);
  assert.equal((html.match(/class="event-card /g) || []).length, 1);
});
test('blocked feeds explain permissions and withhold event cards', () => {
  const html = render({ state: 'ready', data: { ...base, status: 'blocked', events: [] } });
  assert.match(html, /permissions do not allow/);
  assert.doesNotMatch(html, /class="event-card /);
});
