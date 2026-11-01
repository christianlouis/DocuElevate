/* Durable metadata and cross-tab leases. Browser lifetime is not a job runner:
 * the page resumes HTTP transfers, while this worker owns queue transactions. */
const DB_NAME = 'docuelevate-upload-queue';
const DB_VERSION = 4;
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
async function handle(message) {
  if (typeof message.principal !== 'string' || !message.principal) throw new Error('Queue owner required');
  const now = Date.now();
  if (message.op === 'putMany') {
    if (!Array.isArray(message.items) || message.items.length > 100000) throw new Error('Invalid queue metadata');
    return transaction('readwrite', store => {
      for (const item of message.items) {
        const request = store.get(item.key);
        request.onsuccess = () => {
          const previous = request.result;
          if (previous && previous.principal !== message.principal) return;
          // A metadata update must never clear another tab's lease.
          store.put({ ...previous, ...item, principal: message.principal, updatedAt: now,
            leaseOwner: previous?.leaseOwner, leaseUntil: previous?.leaseUntil,
            ...(previous?.fileId && !item.fileId ? { fileId: previous.fileId, state: previous.state } : {}) });
        };
      }
    });
  }
  if (message.op === 'snapshot') return transaction('readonly', (store, result) => {
    const request = store.index('ownerBatch').getAll(IDBKeyRange.only([message.principal, message.batchId]));
    request.onsuccess = () => result(request.result.filter(item => item.principal === message.principal && item.batchId === message.batchId));
  });
  if (message.op === 'lease' || message.op === 'release') return transaction('readwrite', (store, result) => {
    result(false);
    const request = store.get(message.key);
    request.onsuccess = () => {
      const item = request.result;
      if (!item || item.principal !== message.principal) return;
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
