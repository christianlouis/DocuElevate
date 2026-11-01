const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');

function helpers() {
  const context = { window: { addEventListener() {} }, navigator: {}, document: { getElementById() { return null; } }, console, crypto: { randomUUID: () => 'test-uuid', subtle: crypto.webcrypto.subtle }, WebSocket: class {}, location: { protocol: 'http:', host: 'localhost' }, setTimeout, clearTimeout };
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

test('preflight worker hashes a vector larger than one megabyte', async () => {
  const source = fs.readFileSync(require('node:path').join(__dirname, 'upload-preflight-worker.js'), 'utf8');
  let result;
  const context = { self: { postMessage(value) { result = value; } }, Uint8Array, Uint32Array, DataView, TextEncoder, setTimeout };
  vm.runInNewContext(source, context);
  const bytes = Buffer.alloc(1_048_579, 0x61);
  const file = { name: 'large.bin', type: 'application/octet-stream', size: bytes.length, slice(start, end) { return { arrayBuffer: async () => bytes.subarray(start, end).buffer.slice(bytes.byteOffset + start, bytes.byteOffset + Math.min(end, bytes.length)) }; } };
  await context.self.onmessage({ data: { id: 'large', file, name: file.name, mime: file.type } });
  assert.equal(result.sha256, crypto.createHash('sha256').update(bytes).digest('hex'));
});

test('reselect reconciliation preserves batch and client identities', () => {
  const { matchReselected } = helpers();
  const saved = [{ key: 'client-a', batchId: 'batch-1', name: 'a.pdf', size: 12, lastModified: 7 }];
  const matched = matchReselected(saved, [{ name: 'a.pdf', size: 12, lastModified: 7 }]);
  assert.equal(matched[0].key, 'client-a');
  assert.equal(matched[0].batchId, 'batch-1');
});

test('local SHA map marks later content duplicates before upload', () => {
  const { deduplicate } = helpers();
  const result = deduplicate([{ key: 'a', sha256: 'x', state: 'queued' }, { key: 'b', sha256: 'x', state: 'queued' }, { key: 'c', sha256: 'y', state: 'queued' }]);
  assert.equal(result[1].state, 'duplicate');
  assert.equal(result[1].duplicateOf, 'a');
  assert.equal(result[2].state, undefined);
});

test('capacity zero pauses and a WebSocket-style update resumes bounded work', () => {
  const { selectReady } = helpers();
  const queue = [{ key: 'a', size: 5, state: 'queued' }, { key: 'b', size: 5, state: 'queued' }];
  assert.deepEqual(selectReady(queue, { slots: 0 }), []);
  assert.deepEqual(selectReady(queue, { slots: 1, max_bytes: 5 }).map((x) => x.key), ['a']);
});

test('worker reports file read errors instead of leaving a pending hash', async () => {
  const source = fs.readFileSync(require('node:path').join(__dirname, 'upload-preflight-worker.js'), 'utf8');
  let result;
  const context = { self: { postMessage(value) { result = value; } }, Uint8Array, Uint32Array, DataView, TextEncoder, setTimeout };
  vm.runInNewContext(source, context);
  const file = { name: 'broken.bin', type: '', size: 3, slice() { return { arrayBuffer: async () => { throw new Error('read failed'); } }; } };
  await context.self.onmessage({ data: { id: 'broken', file, name: file.name, mime: '' } });
  assert.equal(result.id, 'broken');
  assert.match(result.error, /read failed/);
});
