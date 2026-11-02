const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');

function helpers(overrides = {}) {
  const context = { window: { addEventListener() {}, uploadQueueTestMode: true }, navigator: {}, document: { getElementById() { return null; } }, console, crypto: { randomUUID: () => 'test-uuid', subtle: crypto.webcrypto.subtle }, WebSocket: class {}, location: { protocol: 'http:', host: 'localhost' }, setTimeout, clearTimeout, setInterval, clearInterval, ...overrides };
  vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname, 'upload-bulk.js'), 'utf8'), context);
  return { ...context.window.uploadQueueTestHelpers, Queue: context.window.PersistentBulkUploadQueue };
}

function controller(overrides = {}) {
  const messages = [];
  const { swResults = {}, onSW, ...contextOverrides } = overrides;
  const context = {
    self: { UPLOAD_CONTROLLER_TEST: true, postMessage(value) {
      messages.push(value);
      if (value.type === 'sw') {
        const respond = result => queueMicrotask(() => context.self.onmessage({ data: {
          type: 'swResponse', id: value.id, ok: true, result
        } }));
        if (onSW) onSW(value, respond);
        else respond(swResults[value.op] ?? true);
      }
    } },
    crypto: { randomUUID: (() => { let n = 0; return () => `id-${++n}`; })() },
    fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
    setTimeout, clearTimeout, setInterval, clearInterval, WebSocket: undefined,
    location: { protocol: 'http:', host: 'localhost' },
    importScripts(file) { vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname, file.replace('/static/js/', '')), 'utf8'), context); },
    ...contextOverrides
  };
  vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname, 'upload-controller-worker.js'), 'utf8'), context);
  return { api: context.self.__uploadControllerTest, messages, worker: context.self };
}

function modernAdapter() {
  class Element {
    constructor() { this.className = ''; this.textContent = ''; this.children = []; this.listeners = {}; this.attributes = {}; this.style = {}; this.classList = { values: new Set(['hidden']), add: value => this.classList.values.add(value), remove: value => this.classList.values.delete(value), contains: value => this.classList.values.has(value) }; }
    addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
    dispatch(type, event = {}) { for (const listener of this.listeners[type] || []) listener({ preventDefault() {}, ...event }); }
    replaceChildren(...children) { this.children = children; }
    append(...children) { this.children.push(...children); }
    appendChild(child) { this.children.push(child); return child; }
    setAttribute(name, value) { this.attributes[name] = value; }
    click() { this.dispatch('click'); }
  }
  const ids = ['globalUploadQueue', 'globalUploadQueueReopen', 'globalUploadQueueMinimize', 'globalUploadQueueClose', 'globalUploadQueueAddFiles', 'globalUploadQueueFileInput', 'globalUploadQueueDiagnosticsButton', 'globalUploadQueueDiagnosticsPanel', 'globalUploadQueueDiagnostics', 'globalUploadQueueSummary', 'globalUploadQueueNotice', 'globalUploadQueueProgress', 'globalUploadQueueRows'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
  const listeners = {};
  const workers = [];
  class FakeWorker { constructor(url) { this.url = url; this.messages = []; workers.push(this); } postMessage(message) { this.messages.push(message); } emit(data) { this.onmessage({ data }); } }
  const context = {
    window: { uploadConfig: { concurrency: 3 }, addEventListener(type, listener) { listeners[type] = listener; } },
    document: { getElementById(id) { return elements[id] || null; }, createElement() { return new Element(); } },
    navigator: { serviceWorker: { controller: {}, async register() { return { active: { state: 'activated' } }; }, ready: Promise.resolve() }, storage: { async persist() { return true; }, async persisted() { return true; }, async estimate() { return { usage: 1024, quota: 4096 }; } } },
    Worker: FakeWorker, crypto: { randomUUID: () => 'adapter-id' }, console, setTimeout, clearTimeout, MessageChannel: require('node:worker_threads').MessageChannel,
  };
  const source = fs.readFileSync(require('node:path').join(__dirname, 'upload-bulk.js'), 'utf8');
  vm.runInNewContext(source, context);
  return { ...context, elements, listeners, workers, runAgain() { vm.runInNewContext(source, context); } };
}

const flush = () => new Promise(resolve => setImmediate(resolve));

test('modern adapter keeps an empty restored queue hidden, honors minimize, and localizes rows', async () => {
  const adapter = modernAdapter();
  adapter.listeners.DOMContentLoaded();
  for (let i = 0; i < 5; i++) await flush();
  const worker = adapter.workers[0];
  assert.equal(worker.url, '/static/js/upload-controller-worker.js');
  assert.ok(worker.messages.some(message => message.type === 'init'));
  worker.emit({ type: 'status', message: 'Queue wiederhergestellt.', queue: [], total: 0, complete: 0 });
  assert.equal(adapter.elements.globalUploadQueue.classList.contains('hidden'), true);
  worker.emit({ type: 'status', message: 'Queue wiederhergestellt.', queue: [{ name: 'scan.pdf', state: 'needs_files' }], total: 1, needsFiles: 1, complete: 0 });
  assert.equal(adapter.elements.globalUploadQueue.classList.contains('hidden'), false);
  assert.match(adapter.elements.globalUploadQueueSummary.textContent, /1 insgesamt/);
  assert.match(adapter.elements.globalUploadQueueRows.children[0].textContent, /Originaldatei erneut auswählen/);
  adapter.elements.globalUploadQueueMinimize.dispatch('click');
  worker.emit({ type: 'status', message: 'Upload-Queue aktualisiert.', queue: [{ name: 'scan.pdf', state: 'needs_files' }], total: 1, needsFiles: 1, complete: 0 });
  assert.equal(adapter.elements.globalUploadQueue.classList.contains('hidden'), true);
  worker.emit({ type: 'status', message: 'Queue wiederhergestellt.', queue: [{ name: 'scan.pdf', state: 'needs_files' }], total: 1, needsFiles: 1, complete: 0 });
  assert.equal(adapter.elements.globalUploadQueue.classList.contains('hidden'), true);
  worker.emit({ type: 'status', message: '1 Datei zur Upload-Queue hinzugefügt.', queue: [{ name: 'scan.pdf', state: 'needs_files' }], total: 2, needsFiles: 1, complete: 0 });
  assert.equal(adapter.elements.globalUploadQueue.classList.contains('hidden'), false);
  const reselected = { name: 'scan.pdf', type: 'application/pdf', size: 2, lastModified: 1 };
  adapter.elements.globalUploadQueueFileInput.files = [reselected];
  adapter.elements.globalUploadQueueFileInput.dispatch('change', { target: adapter.elements.globalUploadQueueFileInput });
  for (let i = 0; i < 3; i++) await flush();
  assert.ok(worker.messages.some(message => message.type === 'add' && message.files[0] === reselected));
});

test('modern adapter exposes a manual diagnostic GUI even when the queue is empty', async () => {
  const adapter = modernAdapter();
  adapter.elements.globalUploadQueueDiagnosticsButton.dispatch('click');
  for (let i = 0; i < 4; i++) await flush();
  assert.equal(adapter.elements.globalUploadQueue.classList.contains('hidden'), false);
  assert.equal(adapter.elements.globalUploadQueueDiagnosticsPanel.classList.contains('hidden'), false);
  assert.equal(adapter.elements.globalUploadQueueDiagnosticsButton.attributes['aria-expanded'], 'true');
  const diagnosticText = adapter.elements.globalUploadQueueDiagnostics.children.map(child => child.textContent).join(' ');
  assert.match(diagnosticText, /Service Worker/);
  assert.match(diagnosticText, /Upload-Worker/);
  assert.match(diagnosticText, /Dauerhafter Speicher/);
});

test('modern adapter starts one controller even if the base script is accidentally included twice', () => {
  const adapter = modernAdapter();
  adapter.runAgain();
  assert.equal(adapter.workers.length, 1);
  assert.equal(adapter.elements.globalUploadQueueMinimize.listeners.click.length, 1);
});

test('controller reports a valid 6000-file drop before delayed restore or batch API work', () => {
  let holdRestore;
  const { worker, messages } = controller({ onSW(message, respond) {
    if (message.op === 'listBatches') { holdRestore = respond; return; }
    respond(true);
  } });
  worker.onmessage({ data: { type: 'init', config: { maxFileSize: 1024 }, owner: 'test-owner' } });
  worker.onmessage({ data: { type: 'add', files: Array.from({ length: 6000 }, (_, index) => ({ name: `${index}.pdf`, type: 'application/pdf', size: 1, lastModified: index })) } });
  const immediate = messages.find(message => message.type === 'status' && /hinzugefügt/.test(message.message));
  assert.equal(immediate.total, 6000);
  assert.equal(immediate.diagnostics.phase, 'neue Dateien werden eingeordnet');
  assert.ok(holdRestore, 'restore is intentionally held before any batch API request');
});

test('templates load the legacy page adapter before the global worker adapter exactly once', () => {
  const base = fs.readFileSync(require('node:path').join(__dirname, '../../templates/base.html'), 'utf8');
  const upload = fs.readFileSync(require('node:path').join(__dirname, '../../templates/upload.html'), 'utf8');
  const files = fs.readFileSync(require('node:path').join(__dirname, '../../templates/files.html'), 'utf8');
  assert.ok(base.indexOf('{% block scripts %}') < base.indexOf('/static/js/upload-bulk.js'));
  assert.equal((base.match(/upload-bulk\.js/g) || []).length, 1);
  assert.ok(upload.indexOf('/static/js/upload.js') >= 0 && !upload.includes('/static/js/upload-bulk.js'));
  assert.ok(files.indexOf('/static/js/upload.js') >= 0 && !files.includes('/static/js/upload-bulk.js'));
  assert.match(base, /globalUploadQueueDiagnosticsButton/);
  assert.match(base, /globalUploadQueueAddFiles/);
  assert.match(base, /globalUploadQueueFileInput/);
});

test('preflight windows cover every item without an oversized request', () => {
  const { windows } = helpers();
  const items = Array.from({ length: 405 }, (_, i) => i);
  const result = windows(items);
  assert.deepEqual(Array.from(result, (w) => w.length), [200, 200, 5]);
  assert.deepEqual(Array.from(result.flat()), items);
});

test('controller status sends only visible rows plus aggregates', () => {
  const { api, messages } = controller();
  api.state().queue.push(...Array.from({ length: 150 }, (_, index) => ({ key: String(index), state: index < 10 ? 'accepted' : 'queued', fileId: index < 10 ? index : undefined })));
  api.status('running');
  const update = messages.at(-1);
  assert.equal(update.queue.length, 100);
  assert.equal(update.total, 150);
  assert.equal(update.accepted, 10);
});

test('controller exposes disjoint queue counters and archives only terminal local rows', async () => {
  const operations = [];
  const { api, worker } = controller({ swResults: { listBatches: [] }, onSW(message, respond) { operations.push(message); respond(message.op === 'listBatches' ? [] : ['done', 'duplicate']); } });
  worker.onmessage({ data: { type: 'init', config: {}, owner: 'test-owner' } });
  await new Promise(resolve => setImmediate(resolve));
  api.state().queue.push(
    { key: 'waiting', state: 'accepted', fileId: 1 },
    { key: 'processing', state: 'processing', fileId: 2 },
    { key: 'done', state: 'complete', fileId: 3 },
    { key: 'duplicate', state: 'duplicate', fileId: 3 },
    { key: 'needs', state: 'needs_files' },
    { key: 'failed', state: 'failed' }
  );
  assert.equal(JSON.stringify(api.classify(api.state().queue)), JSON.stringify({ needsFiles: 1, ready: 0, uploading: 0, waiting: 1, processing: 1, complete: 1, duplicate: 1, failed: 1, accepted: 4 }));
  await api.archiveEligible();
  assert.deepEqual(Array.from(api.state().queue, item => item.key), ['waiting', 'processing', 'needs', 'failed']);
  assert.equal(operations.at(-1).op, 'archiveMany');
  assert.equal(JSON.stringify(operations.at(-1).states), JSON.stringify(['complete', 'completed', 'duplicate']));
});

test('retry keeps server-accepted failures untouched and reselects local failures', async () => {
  const { api, worker } = controller({ swResults: { listBatches: [], putMany: true } });
  worker.onmessage({ data: { type: 'init', config: {}, owner: 'test-owner' } });
  await new Promise(resolve => setImmediate(resolve));
  api.state().queue.push(
    { key: 'server-failed', batchId: 'b1', state: 'failed', fileId: 44, error: 'OCR failed' },
    { key: 'local-missing', batchId: 'b2', state: 'failed', error: 'network failed' }
  );
  await api.retryFailed();
  const queue = api.state().queue;
  assert.equal(queue.find(item => item.key === 'server-failed').state, 'failed');
  assert.equal(queue.find(item => item.key === 'server-failed').error, 'OCR failed');
  assert.equal(queue.find(item => item.key === 'local-missing').state, 'needs_files');
});

test('controller dedup prefers an admitted leader and handles 429 retry-after', async () => {
  let attempts = 0;
  const responses = [
    { ok: false, status: 429, headers: { get: () => '0' } },
    { ok: true, status: 200, json: async () => ({ ok: true }) }
  ];
  const { api } = controller({ fetch: async () => { attempts += 1; return responses.shift(); } });
  const items = [{ key: 'needs', sha256: 'same', state: 'queued' }, { key: 'accepted', sha256: 'same', state: 'accepted', fileId: 7 }];
  api.dedup(items);
  assert.equal(items[0].duplicateOf, 'accepted');
  await api.api('/api/test');
  assert.equal(attempts, 2);
});

test('controller capacity selection honors both slots and byte headroom', () => {
  const { api } = controller();
  const selected = api.selectReady([
    { key: 'too-big', state: 'queued', file: {}, size: 11, sha256: 'a' },
    { key: 'fits', state: 'queued', file: {}, size: 5, sha256: 'b' },
    { key: 'next', state: 'queued', file: {}, size: 5, sha256: 'c' }
  ], { slots: 2, max_bytes: 10 });
  assert.deepEqual(Array.from(selected, item => item.key), ['fits', 'next']);
  const fitted = api.selectReady([
    { key: 'first', state: 'queued', file: {}, size: 8, sha256: 'a' },
    { key: 'second', state: 'queued', file: {}, size: 5, sha256: 'b' }
  ], { slots: 2, max_bytes: 10 });
  assert.deepEqual(Array.from(fitted, item => item.key), ['first']);
});

test('controller restore reconciles accepted server files before marking missing bytes', async () => {
  const { api } = controller({
    swResults: {
      listBatches: ['batch-1'],
      snapshot: [{ key: 'client-1', batchId: 'batch-1', name: 'invoice.pdf', size: 12, state: 'queued' }],
      putMany: true
    },
    fetch: async url => {
      if (url.includes('/api/uploads/capacity')) return { ok: true, status: 200, json: async () => ({ slots: 1, max_bytes: 100, processing: { status: 'healthy' } }) };
      assert.match(url, /\/api\/uploads\/batches\/batch-1/);
      return { ok: true, status: 200, json: async () => ({ items: [{ client_id: 'client-1', file_id: 91, state: 'accepted' }], next_cursor: null }) };
    }
  });
  await api.restore();
  const item = api.state().queue[0];
  assert.equal(item.fileId, 91);
  assert.equal(item.state, 'accepted');
});

test('controller restore follows every snapshot cursor and keeps terminal failures terminal', async () => {
  const urls = [];
  const { api } = controller({
    swResults: {
      listBatches: ['batch-1'],
      snapshot: [
        { key: 'first', batchId: 'batch-1', name: 'a.pdf', size: 1, state: 'queued' },
        { key: 'second', batchId: 'batch-1', name: 'b.pdf', size: 1, state: 'queued' },
        { key: 'invalid', batchId: 'batch-1', name: 'bad.pdf', size: 1, state: 'failed' }
      ],
      putMany: true
    },
    fetch: async url => {
      urls.push(url);
      if (url.includes('/api/uploads/capacity')) return { ok: true, status: 200, json: async () => ({ slots: 1, max_bytes: 100 }) };
      return { ok: true, status: 200, json: async () => urls.length === 1
        ? { items: [{ client_id: 'first', file_id: 1, state: 'accepted' }], next_cursor: 101 }
        : { items: [{ client_id: 'second', file_id: 2, state: 'accepted' }], next_cursor: null } };
    }
  });
  await api.restore();
  const queue = api.state().queue;
  assert.match(urls[1], /cursor=101/);
  assert.equal(queue.find(item => item.key === 'first').fileId, 1);
  assert.equal(queue.find(item => item.key === 'second').fileId, 2);
  assert.equal(queue.find(item => item.key === 'invalid').state, 'failed');
});

test('controller import executes the shared preflight inspector and receives its hash result', async () => {
  const { api } = controller();
  const bytes = new TextEncoder().encode('abc');
  const file = { name: 'x.txt', type: 'text/plain', size: bytes.length, slice(start, end) { return { arrayBuffer: async () => bytes.slice(start, end).buffer }; } };
  const result = await api.inspect({ id: 'hash', file, name: file.name, mime: file.type });
  assert.equal(result.sha256, 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  assert.equal(result.mime, 'text/plain');
});

test('controller accepts a second drop while the first batch upload is pending', async () => {
  class Body { constructor() { this.values = {}; } append(key, value) { this.values[key] = value; } }
  const uploads = [];
  let releaseFirst;
  const response = (fileId) => ({ ok: true, status: 202, json: async () => ({ file_id: fileId, state: 'accepted' }) });
  const { api, worker, messages } = controller({
    FormData: Body,
    swResults: { listBatches: [], putMany: true, lease: true, release: true },
    fetch: async (url, options = {}) => {
      if (url === '/api/uploads/batches') return { ok: true, status: 201, json: async () => ({ batch_id: `batch-${uploads.length + 1}` }) };
      if (url === '/api/uploads/preflight') {
        const files = JSON.parse(options.body).files;
        return { ok: true, status: 200, json: async () => ({ files: files.map(file => ({ client_id: file.client_id, state: 'new' })) }) };
      }
      if (url.startsWith('/api/uploads/capacity')) return { ok: true, status: 200, json: async () => ({ slots: 1, max_bytes: 100 }) };
      if (url === '/api/uploads/files') {
        const name = options.body.values.file.name; uploads.push(name);
        if (name === 'first.pdf') {
          return new Promise(resolve => { releaseFirst = () => resolve(response(1)); });
        }
        return response(2);
      }
      throw new Error(`Unexpected request ${url}`);
    }
  });
  const file = name => {
    const bytes = new TextEncoder().encode(`%PDF-${name}`);
    return { name, type: 'application/pdf', size: bytes.length, lastModified: 1, slice(start, end) { return { arrayBuffer: async () => bytes.slice(start, end).buffer }; } };
  };
  async function waitFor(condition) {
    for (let attempt = 0; attempt < 50; attempt++) {
      if (condition()) return;
      await new Promise(resolve => setImmediate(resolve));
    }
    assert.fail(`controller did not reach expected state: ${messages.map(message => message.message).filter(Boolean).join('; ')}`);
  }
  try {
    worker.onmessage({ data: { type: 'init', config: { concurrency: 2 }, owner: 'test-owner' } });
    await new Promise(resolve => setImmediate(resolve));
    worker.onmessage({ data: { type: 'add', files: [file('first.pdf')] } });
    await waitFor(() => releaseFirst);
    worker.onmessage({ data: { type: 'add', files: [file('second.pdf')] } });
    await waitFor(() => uploads.includes('second.pdf'));
    assert.deepEqual(uploads, ['first.pdf', 'second.pdf']);
    assert.equal(api.state().queue.length, 2);
    assert.equal(api.state().queue.find(item => item.name === 'second.pdf').fileId, 2);
    assert.equal(api.state().queue.find(item => item.name === 'first.pdf').fileId, undefined);
    releaseFirst();
    for (let attempt = 0; attempt < 20 && api.state().queue.some(item => !item.fileId); attempt++) await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(Array.from(api.state().queue, item => [item.name, item.fileId]), [['first.pdf', 1], ['second.pdf', 2]]);
  } finally {
    releaseFirst?.();
    await new Promise(resolve => setImmediate(resolve));
  }
});

test('controller reselects only unaccepted recovered entries and retains duplicate signatures', () => {
  const { api } = controller();
  api.state().queue.push(
    { key: 'accepted', batchId: 'batch-a', name: 'same.pdf', size: 3, lastModified: 1, state: 'accepted', fileId: 91 },
    { key: 'waiting-a', batchId: 'batch-a', name: 'same.pdf', size: 3, lastModified: 1, state: 'needs_files' },
    { key: 'waiting-b', batchId: 'batch-a', name: 'same.pdf', size: 3, lastModified: 1, state: 'needs_files' }
  );
  const file = { name: 'same.pdf', size: 3, lastModified: 1, type: 'application/pdf', slice() { return { arrayBuffer: async () => new Uint8Array().buffer }; } };
  const { matched, fresh } = api.matchPendingFiles([file, file]);
  const queue = api.state().queue;
  assert.equal(fresh.length, 0);
  assert.deepEqual(Array.from(matched, item => item.key), ['waiting-a', 'waiting-b']);
  assert.equal(queue[0].state, 'accepted');
  assert.equal(queue[0].fileId, 91);
  assert.equal(queue[1].file, file);
  assert.equal(queue[2].file, file);
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

test('reuses one long-lived preflight worker for multiple files', async () => {
  let created = 0;
  class FakeWorker {
    constructor() { created += 1; }
    postMessage(message) { queueMicrotask(() => this.onmessage({ data: { id: message.id, sha256: message.id, mime: 'text/plain' } })); }
    terminate() {}
  }
  const { digest } = helpers({ Worker: FakeWorker });
  const file = { name: 'x.txt', type: 'text/plain', size: 0 };
  await digest({ key: 'one', file });
  await digest({ key: 'two', file });
  assert.equal(created, 1);
});

test('accepts a drop while another upload is running instead of blocking or replacing the queue', async () => {
  const { Queue } = helpers({ _isAcceptedFile: () => true, MAX_FILE_SIZE: 10_000 });
  const queue = new Queue(null, null); queue.running = true;
  const file = { name: 'later.pdf', size: 3, lastModified: 1 };
  await queue.enqueue([file]);
  assert.equal(queue.pendingAdds.length, 1);
  assert.equal(queue.pendingAdds[0][0], file);
  assert.equal(queue.running, true);
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
  const result = deduplicate([{ key: 'a', sha256: 'x', state: 'queued', file: {} }, { key: 'b', sha256: 'x', state: 'queued', file: {} }, { key: 'c', sha256: 'y', state: 'queued', file: {} }]);
  assert.equal(result[1].state, 'queued'); // Only mark accepted after the leader has a server ID.
  assert.equal(result[1].duplicateOf, 'a');
  assert.equal(result[2].state, 'queued');
  result[0].fileId = 77; deduplicate(result);
  assert.equal(result[1].state, 'duplicate');
  assert.equal(result[1].fileId, 77);
});

test('deduplicates 40000 identical files linearly with admitted leader preference', () => {
  const { deduplicate } = helpers();
  const items = Array.from({ length: 40000 }, (_, index) => ({
    key: `client-${index}`, sha256: 'same-content', state: 'queued',
    ...(index === 0 ? { state: 'needs_files' } : {}),
    ...(index === 1 ? { file: {} } : {}),
    ...(index === 2 ? { fileId: 9042 } : {})
  }));
  const result = deduplicate(items);
  assert.equal(result[0].state, 'duplicate');
  assert.equal(result[0].duplicateOf, 'client-2');
  assert.equal(result[1].duplicateOf, 'client-2');
  assert.equal(result[2].state, 'queued');
  assert.equal(result[2].fileId, 9042);
  assert.equal(result[39999].duplicateOf, 'client-2');
});

test('capacity zero pauses and a WebSocket-style update resumes bounded work', () => {
  const { selectReady } = helpers();
  const queue = [{ key: 'accepted', file: {size: 5}, fileId: 77, sha256: 'old', state: 'queued' }, { key: 'a', file: {size: 5}, sha256: 'a', state: 'queued' }, { key: 'b', file: {size: 5}, sha256: 'b', state: 'queued' }];
  assert.equal(selectReady(queue, { slots: 0 }).length, 0);
  assert.deepEqual(Array.from(selectReady(queue, { slots: 1, max_bytes: 5 }), x => x.key), ['a']);
});

test('deduplication can be disabled while preserving upload candidates', () => {
  const { deduplicate } = helpers({ window: { uploadConfig: { enableDeduplication: false }, addEventListener() {} } });
  const result = deduplicate([{ key: 'a', sha256: 'x', state: 'queued', file: {} }, { key: 'b', sha256: 'x', state: 'queued', file: {} }]);
  assert.equal(result[0].duplicateOf, undefined);
  assert.equal(result[1].duplicateOf, undefined);
});

test('truncated WebSocket snapshots trigger one coalesced REST refresh', async () => {
  let socket;
  class FakeWebSocket { static OPEN = 1; constructor() { socket = this; this.readyState = 1; } close() {} send() {} }
  const { Queue } = helpers({ WebSocket: FakeWebSocket });
  const queue = new Queue(null, null); queue.batchId = 'batch'; let refreshes = 0; let inFlight;
  queue.refresh = () => inFlight || (inFlight = new Promise(resolve => { refreshes += 1; setImmediate(() => { inFlight = null; resolve(); }); }));
  queue.connectEvents(); socket.onopen(); socket.onmessage({ data: JSON.stringify({ snapshot: { items: [], truncated: true } }) });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(refreshes, 1);
  socket.onclose();
  clearTimeout(queue.wsTimer);
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


test('REST reconciliation follows server cursors rather than repeating the first page', async () => {
  const urls = [];
  const pages = [{ items: [{client_id: 'first'}], next_cursor: 203 }, { items: [{client_id: 'second'}], next_cursor: null }, { slots: 0, max_bytes: 0 }];
  const { Queue } = helpers({ fetch: async url => { urls.push(url); return { ok: true, json: async () => pages.shift() }; } });
  const queue = new Queue(null, null); queue.batchId = 'batch';
  const ids = []; queue.reconcile = async items => ids.push(...items.map(item => item.client_id));
  await queue.refresh();
  assert.deepEqual(ids, ['first', 'second']);
  assert.match(urls[1], /cursor=203/);
  assert.equal(queue.capacity.slots, 0);
});

test('a lost HTTP acceptance response retries the same client identity and commits its file id', async () => {
  const { MessageChannel } = require('node:worker_threads');
  const requests = [], operations = [];
  class Body { constructor() { this.values = {}; } append(key, value) { this.values[key] = value; } }
  const { Queue } = helpers({ MessageChannel, FormData: Body,
    navigator: { serviceWorker: { controller: { postMessage(message, ports) {
      operations.push(message); ports[0].postMessage({ ok: true, result: true }); ports[0].close();
    } } } },
    fetch: async (url, options) => {
      requests.push(options.body.values);
      if (requests.length === 1) throw new Error('lost response');
      return {ok: true, json: async () => ({file_id: 91, state: 'accepted'})};
    }
  });
  const queue = new Queue(null, null); queue.batchId = 'stable-batch';
  const item = {key: 'stable-client', file: {}, sha256: 'abc', name: 'invoice.pdf', state: 'queued'};
  assert.equal(await queue.send(item), true);
  assert.equal(requests.length, 2);
  assert.equal(requests[0].client_id, requests[1].client_id);
  assert.equal(requests[1].batch_id, 'stable-batch');
  assert.equal(item.fileId, 91);
  assert.ok(operations.some(op => op.op === 'putMany' && op.items[0].fileId === 91));
  assert.equal(operations.at(-1).op, 'release');
});

test('service worker discovers durable batches when local pointers are missing and isolates owners', async () => {
  const rows = [
    { key: 'one', principal: 'owner-a', batchId: 'batch-1' },
    { key: 'two', principal: 'owner-a', batchId: 'batch-1' },
    { key: 'three', principal: 'owner-a', batchId: 'batch-2' },
    { key: 'other', principal: 'owner-b', batchId: 'private-batch' }
  ];
  function fakeIndexedDB() {
    const range = (lower, upper) => ({ lower, upper });
    class Tx {
      constructor(store) { this.store = store; this.pending = 0; this.oncomplete = null; }
      add() { this.pending += 1; }
      done() {
        this.pending -= 1;
        if (!this.pending) queueMicrotask(() => this.oncomplete?.());
      }
      objectStore() { return this.store; }
    }
    const inRange = (key, wanted) => !wanted || (key[0] >= wanted.lower[0] && key[0] <= wanted.upper[0]);
    const store = {
      indexNames: { contains() { return true; } },
      index() {
        return {
          openKeyCursor(wanted) {
            const tx = currentTx; const keys = [...new Map(rows.map(item => [item.principal, item.batchId])
              .map(key => [key.join('\0'), key])).values()]
              .filter(key => inRange(key, wanted)).sort((a, b) => a.join('\0').localeCompare(b.join('\0')));
            const request = { result: null, onsuccess: null }; let offset = 0;
            tx.add();
            const emit = () => {
              request.result = offset < keys.length ? { key: keys[offset], continue() { offset += 1; queueMicrotask(emit); } } : null;
              request.onsuccess?.({ target: request });
              if (!request.result) tx.done();
            };
            queueMicrotask(emit); return request;
          }
        };
      }
    };
    let currentTx;
    const db = {
      objectStoreNames: { contains() { return true; } },
      transaction() { currentTx = new Tx(store); return currentTx; },
      close() {}
    };
    return {
      indexedDB: { open() {
        const request = { result: db, transaction: { objectStore() { return store; } }, onupgradeneeded: null, onsuccess: null };
        queueMicrotask(() => { request.onupgradeneeded?.({ target: request }); queueMicrotask(() => request.onsuccess?.({ target: request })); });
        return request;
      } },
      IDBKeyRange: { bound: range }
    };
  }
  const source = fs.readFileSync(require('node:path').join(__dirname, 'upload-queue-sw.js'), 'utf8');
  const fake = fakeIndexedDB();
  const context = { ...fake, self: { addEventListener() {} }, Date };
  vm.runInNewContext(`${source}\nself.__handle = handle;`, context);
  assert.deepEqual(Array.from(await context.self.__handle({ op: 'listBatches', principal: 'owner-a' })), ['batch-1', 'batch-2']);
  assert.deepEqual(Array.from(await context.self.__handle({ op: 'listBatches', principal: 'owner-b' })), ['private-batch']);
});


test('every upload entry script parses before browser event handlers run', () => {
  for (const file of ['upload.js', 'upload-bulk.js', 'upload-preflight-worker.js', 'upload-queue-sw.js', 'upload-controller-worker.js']) {
    assert.doesNotThrow(() => new vm.Script(fs.readFileSync(require('node:path').join(__dirname, file), 'utf8'), {filename: file}));
  }
});
