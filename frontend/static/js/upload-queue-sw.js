/* Durable metadata and cross-tab leases. Browser lifetime is not a job runner:
 * the page resumes HTTP transfers, while this worker owns queue transactions. */
const DB_NAME = 'docuelevate-upload-queue';
const DB_VERSION = 5;
const CLEAR_KEY = principal => `__clear__:${principal}`;
function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const store = request.result.objectStoreNames.contains('items')
        ? request.transaction.objectStore('items') : request.result.createObjectStore('items', { keyPath: 'key' });
      if (!store.indexNames.contains('ownerBatch')) store.createIndex('ownerBatch', ['principal', 'batchId']);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function transaction(mode, callback) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('items', mode);
    let result;
    callback(tx.objectStore('items'), value => { result = value; });
    tx.oncomplete = () => { db.close(); resolve(result); };
    tx.onerror = () => { db.close(); reject(tx.error); };
    tx.onabort = () => { db.close(); reject(tx.error || new Error('Queue transaction aborted')); };
  });
}
async function notifyQueueChange(message, result) {
  // Notify only after the transaction commits. A sleeping/old tab still cannot
  // revive cleared rows: the generation fence and tombstones enforce that.
  try {
    const clients = await self.clients?.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clients || []) client.postMessage({
      type: 'uploadQueueChanged', principal: message.principal, owner: message.owner,
      cleared: message.op === 'clearAll', generation: result.generation,
      keys: Array.isArray(result) ? result : []
    });
  } catch (_) { /* Durable state remains authoritative if a tab has closed. */ }
  return result;
}
async function handle(message) {
  if (typeof message.principal !== 'string' || !message.principal) throw new Error('Queue owner required');
  const now = Date.now();
  if (message.op === 'putMany') {
    if (!Array.isArray(message.items) || message.items.length > 100000) throw new Error('Invalid queue metadata');
    return transaction('readwrite', (store, result) => {
      const fenceRequest = store.get(CLEAR_KEY(message.principal));
      fenceRequest.onsuccess = () => {
        const fence = fenceRequest.result;
        const generation = Number(message.generation || 0);
        const current = Number(fence?.clearGeneration || 0);
        result({ ignored: generation !== current, generation: current });
        if (generation !== current) return;
        for (const item of message.items) {
          const request = store.get(item.key);
          request.onsuccess = () => {
            const previous = request.result;
            if (previous && previous.principal !== message.principal) return;
            // A metadata update must never clear another tab's lease.
            if (previous?.archivedAt) return;
            store.put({ ...previous, ...item, principal: message.principal, updatedAt: now,
              leaseOwner: previous?.leaseOwner, leaseUntil: previous?.leaseUntil,
              generation,
              ...(previous?.fileId && !item.fileId ? { fileId: previous.fileId, state: previous.state } : {}) });
          };
        }
      };
    });
  }
  if (message.op === 'clearAll') return transaction('readwrite', (store, result) => {
    const fenceRequest = store.get(CLEAR_KEY(message.principal));
    fenceRequest.onsuccess = () => {
      const generation = Number(fenceRequest.result?.clearGeneration || 0) + 1;
      let count = 0;
      // Read the owner's live metadata in one request. A cursor round trip per
      // row makes a 50,000-file clear take tens of seconds in Chromium.
      const rows = store.index('ownerBatch').getAll(
        IDBKeyRange.bound([message.principal, ''], [message.principal, '\uffff'])
      );
      rows.onsuccess = () => {
        for (const item of rows.result) {
          if (item.principal !== message.principal || item.archivedAt || item.key === CLEAR_KEY(message.principal)) continue;
          count += 1;
          store.put({ key: item.key, principal: item.principal, archivedAt: now, updatedAt: now, generation });
        }
        store.put({ key: CLEAR_KEY(message.principal), principal: message.principal, clearGeneration: generation, updatedAt: now });
        result({ generation, count });
      };
    };
  }).then(result => notifyQueueChange(message, result));
  if (message.op === 'clearState') return transaction('readonly', (store, result) => {
    const request = store.get(CLEAR_KEY(message.principal));
    request.onsuccess = () => result({ protocol: 2, generation: Number(request.result?.clearGeneration || 0) });
  });
  if (message.op === 'archiveMany') {
    if (!Array.isArray(message.keys) || message.keys.length > 100000) throw new Error('Invalid archive request');
    const allowed = message.kind === 'completed' ? new Set(['complete', 'completed', 'duplicate'])
      : message.kind === 'unsent' ? new Set(['needs_files', 'queued', 'uploading', 'failed', 'transfer_failed']) : null;
    if (!allowed && message.kind !== 'local') throw new Error('Invalid archive kind');
    return transaction('readwrite', (store, result) => {
      const archived = [];
      result(archived);
      for (const key of message.keys) {
        const request = store.get(key);
        request.onsuccess = () => {
          const item = request.result;
          if (!item || item.principal !== message.principal || item.archivedAt || (allowed && !allowed.has(item.state))) return;
          if (item.leaseUntil > now && (message.kind !== 'local' || !message.owner || item.leaseOwner !== message.owner)) return;
          if (message.kind === 'unsent' && item.fileId != null) return;
          // Keep a small tombstone so late writes and leases stay rejected,
          // without retaining a completed batch in the ownerBatch index.
          store.put({ key: item.key, principal: item.principal, archivedAt: now, updatedAt: now });
          archived.push(key);
          result(archived);
        };
      }
    }).then(result => notifyQueueChange(message, result));
  }
  if (message.op === 'listBatches') return transaction('readonly', (store, result) => {
    const batches = new Set();
    const request = store.index('ownerBatch').openKeyCursor(
      IDBKeyRange.bound([message.principal, ''], [message.principal, '\uffff']), 'nextunique'
    );
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) return result([...batches]);
      if (typeof cursor.key[1] === 'string' && cursor.key[1]) batches.add(cursor.key[1]);
      cursor.continue();
    };
  });
  if (message.op === 'snapshot') return transaction('readonly', (store, result) => {
    const request = store.index('ownerBatch').getAll(IDBKeyRange.only([message.principal, message.batchId]));
    request.onsuccess = () => result(request.result.filter(item => item.principal === message.principal && item.batchId === message.batchId && !item.archivedAt));
  });
  if (message.op === 'lease' || message.op === 'release') return transaction('readwrite', (store, result) => {
    result(false);
    const request = store.get(message.key);
    request.onsuccess = () => {
      const item = request.result;
      if (!item || item.principal !== message.principal || item.archivedAt) return;
      if (message.op === 'lease') {
        if (item.leaseUntil > now && item.leaseOwner !== message.owner) return;
        item.leaseOwner = message.owner; item.leaseUntil = now + Math.min(60000, message.ttl || 60000);
      } else {
        if (item.leaseOwner !== message.owner) return;
        item.leaseOwner = null; item.leaseUntil = 0;
      }
      store.put(item); result(true);
    };
  });
  throw new Error('Unknown queue operation');
}
self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('message', event => {
  const port = event.ports?.[0];
  if (!port) return;
  event.waitUntil(handle(event.data || {}).then(result => port.postMessage({ ok: true, result }))
    .catch(error => port.postMessage({ ok: false, error: String(error) })));
});
