import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { customFetch, setBaseUrl } from '../src/custom-fetch.ts';

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; setBaseUrl(null); });

test('native responses without a stream still parse JSON', async () => {
  setBaseUrl('https://example.invalid');
  globalThis.fetch = async (url, init) => {
    assert.equal(url, 'https://example.invalid/api/discovery/events');
    assert.equal(init.cache, 'no-store');
    return {
      ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }),
      body: undefined, text: async () => '{"mode":"synthetic","events":[]}',
    };
  };
  assert.deepEqual(await customFetch('/api/discovery/events', { cache: 'no-store', timeoutMs: 100 }), { mode: 'synthetic', events: [] });
});

test('missing records retain HTTP status for distinct missing states', async () => {
  globalThis.fetch = async () => new Response('{"detail":"Not found"}', { status: 404, headers: { 'content-type': 'application/json' } });
  await assert.rejects(customFetch('/api/discovery/events/missing', { timeoutMs: 100 }), error => error.status === 404);
});

test('deadline aborts a stalled network request', async () => {
  globalThis.fetch = async (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
  });
  await assert.rejects(customFetch('/api/discovery/events', { timeoutMs: 10 }), /aborted/);
});

test('query cancellation is forwarded when a deadline is configured', async () => {
  const controller = new AbortController();
  globalThis.fetch = async (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(new Error('cancelled')), { once: true });
  });
  const request = customFetch('/api/discovery/events', { signal: controller.signal, timeoutMs: 1000 });
  controller.abort();
  await assert.rejects(request, /cancelled/);
});
