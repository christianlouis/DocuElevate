const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() { this.textContent = ''; this.children = []; this.listeners = {}; this.style = {}; this.disabled = false; this.files = []; this.classList = { values: new Set(['hidden']), add: v => this.classList.values.add(v), remove: v => this.classList.values.delete(v), contains: v => this.classList.values.has(v) }; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatch(type, event = {}) { for (const fn of this.listeners[type] || []) fn({ preventDefault() {}, target: this, ...event }); }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute() {}
  click() { this.dispatch('click'); }
}

function setup() {
  const ids = ['globalUploadQueue','globalUploadQueueReopen','globalUploadQueueMinimize','globalUploadQueueClose','globalUploadQueueAddFiles','globalUploadQueueFileInput','globalUploadQueueDiagnosticsButton','globalUploadQueueDiagnosticsPanel','globalUploadQueueDiagnostics','globalUploadQueueSummary','globalUploadQueueNotice','globalUploadQueueActionFeedback','globalUploadQueueTransferProgress','globalUploadQueueProcessingProgress','globalUploadQueueTransferLabel','globalUploadQueueProcessingLabel','globalUploadQueueRows','globalUploadQueueRetryFailed','globalUploadQueueDiscardUnsent','globalUploadQueueArchiveCompleted','globalUploadQueueClear'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
  const listeners = {};
  const workers = [];
  class Worker { constructor(url) { this.url = url; this.messages = []; workers.push(this); } postMessage(msg) { this.messages.push(msg); } emit(data) { this.onmessage({ data }); } }
  const context = {
    window: { uploadConfig: { concurrency: 3 }, confirm: () => true, addEventListener(type, fn) { listeners[type] = fn; } },
    document: { getElementById(id) { return elements[id] || null; }, createElement() { return new Element(); } },
    navigator: { serviceWorker: { controller: { postMessage(message, ports) { ports[0].postMessage({ ok: true, result: { protocol: 2, generation: 0 } }); } }, async register() { return { active: { state: 'activated' } }; }, ready: Promise.resolve() }, storage: { async persist() {}, async persisted() { return true; }, async estimate() { return {}; } } },
    Worker, crypto: { randomUUID: () => 'ui-test' }, console, setTimeout, clearTimeout, MessageChannel: require('node:worker_threads').MessageChannel
  };
  vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname, 'upload-bulk.js'), 'utf8'), context);
  listeners.DOMContentLoaded();
  return { elements, worker: workers[0], context };
}

const status = (extra = {}) => ({ type: 'status', message: 'Queue wird wiederhergestellt.', total: 96, accepted: 80, complete: 0, failed: 16, counts: { total: 96, accepted: 80, waiting: 80, complete: 0, duplicate: 0, failed: 16, needsFiles: 0, ready: 0, uploading: 0, processing: 0 }, queue: [{ key: 'x', name: 'bad.zip', state: 'transfer_failed', error: 'Upload request failed (415)' }], ...extra });

test('queue UI renders separate progress and actionable rows', async () => {
  const { elements, worker } = setup();
  worker.emit(status());
  assert.equal(elements.globalUploadQueueTransferLabel.textContent, '80 von 96');
  assert.equal(elements.globalUploadQueueProcessingLabel.textContent, '0 von 80');
  assert.match(elements.globalUploadQueueRows.children[0].textContent, /Dateityp wird nicht unterstützt/);
  elements.globalUploadQueueRows.children[0].children[0].click();
  for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve));
  assert.equal(worker.messages.at(-1).type, 'action');
  assert.equal(worker.messages.at(-1).action, 'removeItems');
  assert.deepEqual([...worker.messages.at(-1).keys], ['x']);
});

test('queue UI keeps action feedback through background updates and handles clear confirmation', async () => {
  const { elements, worker, context } = setup();
  worker.emit(status({ actionFeedback: { message: 'Lokale Queue wird geleert …', busy: true } }));
  assert.equal(elements.globalUploadQueueActionFeedback.textContent, 'Lokale Queue wird geleert …');
  assert.equal(elements.globalUploadQueueClear.disabled, true);
  worker.emit(status({ message: 'Upload-Queue aktualisiert.' }));
  assert.equal(elements.globalUploadQueueActionFeedback.textContent, 'Lokale Queue wird geleert …');
  worker.emit(status({ actionFeedback: { message: 'Lokale Warteschlange geleert.', busy: false } }));
  assert.equal(elements.globalUploadQueueClear.disabled, false);
  context.window.confirm = () => false;
  elements.globalUploadQueueClear.click();
  assert.equal(worker.messages.some(message => message.type === 'action'), false);
  context.window.confirm = () => true;
  elements.globalUploadQueueClear.click();
  for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve));
  assert.equal(worker.messages.at(-1).type, 'action');
  assert.equal(worker.messages.at(-1).action, 'clearQueue');
});

test('uploads in flight stay out of accepted progress and non-415 rejections keep their reason', () => {
  const { elements, worker } = setup();
  worker.emit(status({ total: 4, accepted: 2, complete: 1, counts: { uploading: 1, failed: 2, complete: 1, duplicate: 0 }, queue: [{ key: 'large', state: 'transfer_failed', errorCode: 'transfer_rejected', error: 'Upload request failed (413): too large' }] }));
  assert.equal(elements.globalUploadQueueTransferLabel.textContent, '2 von 4');
  assert.equal(elements.globalUploadQueueTransferProgress.style.width, '50%');
  assert.equal(elements.globalUploadQueueProcessingLabel.textContent, '1 von 2');
  assert.match(elements.globalUploadQueueRows.children[0].textContent, /413.*too large/);
  assert.doesNotMatch(elements.globalUploadQueueRows.children[0].textContent, /415/);
});

test('queue UI limits rendered rows and reports hidden count', () => {
  const { elements, worker } = setup();
  const queue = Array.from({ length: 120 }, (_, i) => ({ key: `k${i}`, name: `file-${i}.pdf`, state: 'accepted' }));
  worker.emit(status({ total: 120, queue, counts: { accepted: 120, waiting: 120, complete: 0, duplicate: 0, failed: 0 } }));
  assert.equal(elements.globalUploadQueueRows.children.length, 101);
  assert.match(elements.globalUploadQueueRows.children.at(-1).textContent, /100 von 120 Einträgen angezeigt/);
});
