const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, 'upload-controller-worker.js'), 'utf8');
function flush() { return new Promise(resolve => setImmediate(resolve)); }
function controller(options = {}) {
  const messages = [], durable = options.durable || [];
  const self = {
    UPLOAD_CONTROLLER_TEST: true, location: { host: '', protocol: 'https:' },
    postMessage(message) {
      messages.push(message);
      if (message.type !== 'sw') return;
      const result = options.onSW ? options.onSW(message, durable) : undefined;
      if (result === undefined) {
        const defaults = { listBatches: [...new Set(durable.map(item => item.batchId))], clearState: { protocol: 2, generation: 0 }, snapshot: durable.filter(item => item.batchId === message.batchId), archiveMany: { keys: message.keys || [] }, clearAll: { generation: 1, count: durable.length }, putMany: { ignored: false, generation: 0 }, lease: true, release: true };
        queueMicrotask(() => self.onmessage({ data: { type: 'swResponse', id: message.id, ok: true, result: defaults[message.op] } }));
      } else Promise.resolve(result).then(value => self.onmessage({ data: { type: 'swResponse', id: message.id, ok: true, result: value } }), error => self.onmessage({ data: { type: 'swResponse', id: message.id, ok: false, error: error.message } }));
    },
    inspectUploadFile: async () => ({ sha256: 'a'.repeat(64), mime: 'application/pdf' }),
  };
  const context = { self, console, crypto: { randomUUID: (() => { let i = 0; return () => `id-${++i}`; })() }, setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask, FormData: class { append() {} }, fetch: options.fetch || (async () => { throw new Error('offline'); }), importScripts() {}, TextEncoder, AbortController };
  vm.runInNewContext(source, context, { filename: 'upload-controller-worker.js' });
  return { worker: self, api: self.__uploadControllerTest, messages };
}

test('local removal is usable after offline restoration and reports a settled result', async () => {
  const { worker, api, messages } = controller({ durable: [{ key: 'reject', batchId: 'b', name: 'bad.mov', size: 1, state: 'transfer_failed', error: 'Upload request failed (415)' }] });
  worker.onmessage({ data: { type: 'init', owner: 'owner' } });
  await flush(); await flush();
  worker.onmessage({ data: { type: 'action', action: 'removeItems', keys: ['reject'] } });
  await flush(); await flush();
  assert.equal(api.state().queue.length, 0);
  const feedback = messages.filter(message => message.type === 'status').at(-1).actionFeedback;
  assert.equal(feedback.busy, false);
  assert.match(feedback.message, /Einträge lokal entfernt/);
});

test('offline reconciliation cannot truncate later restored batches', async () => {
  const durable = [
    { key: 'accepted', batchId: 'first', name: 'kept.pdf', size: 1, state: 'accepted', fileId: 1 },
    { key: 'queued', batchId: 'second', name: 'choose-again.pdf', size: 1, state: 'queued' },
  ];
  const { worker, api } = controller({ durable });
  worker.onmessage({ data: { type: 'init', owner: 'owner' } });
  await flush(); await flush(); await flush();
  const queue = api.state().queue;
  assert.equal(queue.length, 2);
  assert.equal(queue.find(item => item.key === 'queued').state, 'needs_files');
});

test('a clear fences a delayed batch response so it cannot resurrect local rows', async () => {
  let resolveBatch;
  const { worker, api } = controller({ onSW(message, durable) {
    if (message.op === 'clearState') return { protocol: 2, generation: 0 };
    if (message.op === 'listBatches') return [];
    if (message.op === 'snapshot') return [];
    if (message.op === 'clearAll') return { generation: 1, count: 0 };
    if (message.op === 'putMany') return { ignored: false, generation: 0 };
    return undefined;
  }, fetch: async url => {
    if (url === '/api/uploads/batches') return new Promise(resolve => { resolveBatch = () => resolve({ ok: true, status: 200, json: async () => ({ batch_id: 'late' }) }); });
    return { ok: true, status: 200, json: async () => ({ slots: 0, max_bytes: 1 }) };
  } });
  worker.onmessage({ data: { type: 'init', owner: 'owner' } }); await flush(); await flush();
  worker.onmessage({ data: { type: 'add', files: [{ name: 'new.pdf', size: 1, type: 'application/pdf' }] } });
  for (let i = 0; i < 6 && !resolveBatch; i++) await flush();
  assert.ok(resolveBatch);
  await api.clearQueue(); resolveBatch(); await flush(); await flush();
  assert.equal(api.state().queue.length, 0);
});

test('415 rejections are not retried and explain why', async () => {
  const { worker, api, messages } = controller({ durable: [{ key: 'unsupported', batchId: 'b', name: 'movie.mov', size: 1, state: 'transfer_failed', error: 'Upload request failed (415)' }] });
  worker.onmessage({ data: { type: 'init', owner: 'owner' } }); await flush(); await flush();
  assert.equal(await api.retryFailed(), 0);
  assert.match(messages.filter(message => message.type === 'status').at(-1).message, /415/);
});


test('clear during a delayed lease releases the upload slot and lease', async () => {
  let resolveLease;
  const { worker, api, messages } = controller({ onSW(message) {
    if (message.op === 'lease') return new Promise(resolve => { resolveLease = resolve; });
  } });
  worker.onmessage({ data: { type: 'init', owner: 'owner' } });
  await flush(); await flush();
  const sending = api.send({ key: 'pending', batchId: 'b', file: {}, name: 'scan.pdf' });
  await flush();
  assert.equal(api.state().activeUploads, 1);
  await api.clearQueue();
  resolveLease(true);
  assert.equal(await sending, false);
  assert.equal(api.state().activeUploads, 0);
  assert.ok(messages.some(message => message.op === 'release' && message.key === 'pending'));
});

test('failed durable clear retains the visible queue and settles with an error', async () => {
  const { worker, api, messages } = controller({
    durable: [{ key: 'kept', batchId: 'b', state: 'accepted', fileId: 7 }],
    onSW(message) { if (message.op === 'clearAll') return Promise.reject(new Error('Disk unavailable')); },
  });
  worker.onmessage({ data: { type: 'init', owner: 'owner' } });
  await flush(); await flush();
  worker.onmessage({ data: { type: 'action', action: 'clearQueue' } });
  await flush(); await flush();
  assert.equal(api.state().queue.length, 1);
  assert.equal(api.state().actionBusy, false);
  assert.match(messages.filter(message => message.type === 'status').at(-1).actionFeedback.message, /Disk unavailable/);
});

test('fresh selection waits for durable clear, while a pre-clear selection is cancelled', async () => {
  let resolveClear, resolveFence, generation = 0, holdFence = false, batchRequests = 0;
  const { worker, api } = controller({ onSW(message) {
    if (message.op === 'clearState') return holdFence ? new Promise(resolve => { resolveFence = resolve; }) : { protocol: 2, generation };
    if (message.op === 'clearAll') return new Promise(resolve => { resolveClear = () => { generation = 1; resolve({ generation, count: 0 }); }; });
    if (message.op === 'putMany') return { generation, ignored: false };
  }, fetch: async url => {
    if (url === '/api/uploads/batches') { batchRequests += 1; return { ok: true, status: 200, json: async () => ({ batch_id: 'new' }) }; }
    return { ok: true, status: 200, json: async () => ({ slots: 1, max_bytes: 100, file_id: 8, state: 'accepted' }) };
  } });
  worker.onmessage({ data: { type: 'init', owner: 'owner' } }); await flush(); await flush();
  holdFence = true;
  const oldAdd = api.add([{ name: 'before.pdf', size: 1 }]); await flush();
  assert.ok(resolveFence);
  const clearing = api.clearQueue();
  holdFence = false;
  const freshAdd = api.add([{ name: 'after.pdf', size: 1 }]); await flush();
  assert.equal(batchRequests, 0);
  resolveFence({ protocol: 2, generation: 0 });
  resolveClear(); await clearing; await oldAdd; await freshAdd;
  await flush(); await flush();
  assert.equal(batchRequests, 1);
  assert.deepEqual(Array.from(api.state().queue, item => item.name), ['after.pdf']);
});
