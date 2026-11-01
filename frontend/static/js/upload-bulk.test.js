const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function helpers() {
  const context = { window: { addEventListener() {} }, navigator: {}, document: { getElementById() { return null; } }, console, setTimeout, clearTimeout };
  vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname, 'upload-bulk.js'), 'utf8'), context);
  return context.window.uploadQueueTestHelpers;
}

test('preflight windows cover every item without an oversized request', () => {
  const { windows } = helpers();
  const items = Array.from({ length: 405 }, (_, i) => i);
  const result = windows(items);
  assert.deepEqual(Array.from(result, (w) => w.length), [200, 200, 5]);
  assert.deepEqual(Array.from(result.flat()), items);
});

test('zero server capacity is preserved as a pause signal', () => {
  const { slots } = helpers();
  assert.equal(slots({ slots: 0 }), 0);
  assert.equal(slots({ slots: 2 }), 2);
});

test('preflight duplicate states suppress byte upload', () => {
  const applyPreflightResults = helpers().applyPreflightResults;
  const item = {key: 'client-1', state: 'queued'};
  applyPreflightResults([item], {
    files: [{client_id: 'client-1', state: 'duplicate', file_id: 'server-77'}]
  });
  assert.equal(item.state, 'duplicate');
  assert.equal(item.fileId, 'server-77');
});

test('preflight worker hashes data across chunk boundaries', async () => {
  const source = fs.readFileSync(require('node:path').join(__dirname, 'upload-preflight-worker.js'), 'utf8');
  let result;
  const context = { self: { postMessage(value) { result = value; } }, Uint8Array, Uint32Array, DataView, TextEncoder, setTimeout };
  vm.runInNewContext(source, context);
  const bytes = new TextEncoder().encode('abc');
  const file = { name: 'x.txt', type: 'text/plain', size: bytes.length, slice(start, end) { return { arrayBuffer: async () => bytes.slice(start, end).buffer }; } };
  await context.self.onmessage({ data: { id: 'hash', file, name: file.name, mime: file.type } });
  assert.equal(result.sha256, 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
});
