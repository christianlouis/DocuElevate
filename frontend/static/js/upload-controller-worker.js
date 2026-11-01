/* Single upload orchestrator. The page is an adapter; durable metadata and
 * leases remain in the service worker, while this worker owns all execution. */
importScripts('/static/js/upload-preflight-worker.js');

const WINDOW = 200;
let config = {}, principal = 'single-user', csrfToken = '', owner = '';
let queue = [], running = new Set(), capacities = new Map(), swRequests = new Map(), nextRpc = 0;

function status(message, extra = {}) { self.postMessage({ type: 'status', message, queue: queue.map(({ file, ...item }) => item), ...extra }); }
function sw(op, data = {}) {
  return new Promise((resolve, reject) => {
    const id = `sw-${++nextRpc}`; swRequests.set(id, { resolve, reject });
    self.postMessage({ type: 'sw', id, op, principal, ...data });
  });
}
function retryAfter(response, fallback) {
  const value = response.headers?.get?.('Retry-After');
  if (!value) return fallback;
  const seconds = Number(value);
  return Number.isFinite(seconds) ? Math.max(0, seconds * 1000) : Math.max(0, Date.parse(value) - Date.now());
}
async function api(url, options = {}) {
  let backoff = 500;
  for (;;) {
    let response;
    try { response = await fetch(url, { ...options, headers: { ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}), ...options.headers } }); }
    catch (error) { await new Promise(resolve => setTimeout(resolve, backoff)); backoff = Math.min(backoff * 2, 30000); continue; }
    if (response.status === 429) { status('Serverlimit erreicht – Upload pausiert.'); await new Promise(resolve => setTimeout(resolve, retryAfter(response, backoff))); backoff = Math.min(backoff * 2, 30000); continue; }
    if (response.status >= 500) { await new Promise(resolve => setTimeout(resolve, backoff)); backoff = Math.min(backoff * 2, 30000); continue; }
    if (!response.ok) throw new Error(`Upload request failed (${response.status})`);
    return response.json();
  }
}
function signature(file) { return JSON.stringify([file.name, file.size, file.lastModified || 0]); }
function dedup(items) {
  const groups = new Map();
  for (const item of items) {
    delete item.duplicateOf;
    if (!item.sha256 || item.state === 'failed') continue;
    if (!groups.has(item.sha256)) groups.set(item.sha256, []);
    groups.get(item.sha256).push(item);
  }
  for (const group of groups.values()) {
    const leader = group.find(item => item.fileId) || group.find(item => item.file);
    if (!leader) continue;
    for (const item of group) if (item !== leader) { item.duplicateOf = leader.key; if (leader.fileId) { item.fileId = leader.fileId; item.state = 'duplicate'; } }
  }
}
async function persist(items) { if (items.length) await sw('putMany', { items: items.map(item => ({ key: item.key, batchId: item.batchId, name: item.name, size: item.size, lastModified: item.lastModified, state: item.state, sha256: item.sha256, mime: item.mime, fileId: item.fileId, duplicateOf: item.duplicateOf })) }); }
async function makeBatch(files) {
  const batch = await api('/api/uploads/batches', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ client_batch_id: crypto.randomUUID(), total_files: files.length, total_bytes: files.reduce((sum, file) => sum + file.size, 0) }) });
  const items = files.map(file => ({ key: crypto.randomUUID(), batchId: batch.batch_id, file, name: file.name, size: file.size, lastModified: file.lastModified || 0, state: 'queued' }));
  queue.push(...items); await persist(items); status(`${queue.length} Dateien in der Upload-Queue.`); return items;
}
function connectCapacity(batchId) {
  if (typeof WebSocket === 'undefined') return;
  const protocol = self.location?.protocol === 'https:' ? 'wss' : 'ws';
  const host = self.location?.host; if (!host) return;
  const socket = new WebSocket(`${protocol}://${host}/api/uploads/events?batch_id=${encodeURIComponent(batchId)}`);
  socket.onmessage = event => { try { const message = JSON.parse(event.data); if (message.capacity) capacities.set(batchId, message.capacity); if (message.slots !== undefined) capacities.set(batchId, message); } catch (_) {} };
  socket.onclose = () => { if (running.has(batchId)) setTimeout(() => connectCapacity(batchId), 5000); };
}
async function send(item) {
  if (!await sw('lease', { key: item.key, owner, ttl: 60000 })) return false;
  const renewal = setInterval(() => sw('lease', { key: item.key, owner, ttl: 60000 }).catch(() => {}), 10000);
  try {
    const body = new FormData(); body.append('file', item.file); body.append('batch_id', item.batchId); body.append('client_id', item.key); body.append('sha256', item.sha256);
    const result = await api('/api/uploads/files', { method: 'POST', body });
    item.fileId = result.file_id; item.state = result.duplicate ? 'duplicate' : result.state || 'accepted'; await persist([item]);
    self.postMessage({ type: 'accepted', fileId: item.fileId, filename: item.name, state: item.state }); return true;
  } catch (error) { item.state = 'queued'; await persist([item]); status(`Upload pausiert: ${error.message}`); return false; }
  finally { clearInterval(renewal); await sw('release', { key: item.key, owner }).catch(() => {}); }
}
async function processBatch(items) {
  const batchId = items[0]?.batchId; if (!batchId || running.has(batchId)) return;
  running.add(batchId); connectCapacity(batchId);
  try {
    for (let offset = 0; offset < items.length; offset += WINDOW) {
      const group = items.slice(offset, offset + WINDOW);
      for (const item of group.filter(item => item.file && !item.fileId)) {
        try { const result = await self.inspectUploadFile({ id: item.key, file: item.file, name: item.name, mime: item.file.type }); item.sha256 = result.sha256; item.mime = result.mime; }
        catch (error) { item.state = 'failed'; status(String(error)); }
      }
      dedup(queue);
      const check = group.filter(item => item.state === 'queued' && item.file && item.sha256 && !item.duplicateOf);
      if (check.length) {
        const result = await api('/api/uploads/preflight', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ batch_id: batchId, files: check.map(item => ({ client_id: item.key, sha256: item.sha256, size: item.size, mime: item.mime })) }) });
        for (const entry of result.files || []) { const item = check.find(candidate => candidate.key === entry.client_id); if (item && entry.state === 'duplicate') { item.state = 'duplicate'; item.fileId = entry.file_id; } }
      }
      dedup(queue); await persist(group);
      for (;;) {
        const capacity = capacities.get(batchId) || await api(`/api/uploads/capacity?batch_id=${encodeURIComponent(batchId)}`);
        capacities.set(batchId, capacity);
        const selected = group.filter(item => item.state === 'queued' && item.file && !item.fileId && !item.duplicateOf).slice(0, Math.max(0, Math.min(Number(capacity.slots || 0), Number(config.concurrency || 3))));
        if (!selected.length) { if (!group.some(item => item.state === 'queued' && item.file && !item.fileId && !item.duplicateOf)) break; status('Server pausiert die Uploads – warte auf Kapazität…'); await new Promise(resolve => setTimeout(resolve, 2000)); continue; }
        await Promise.all(selected.map(send)); await persist(group);
      }
      status('Upload-Queue wird verarbeitet.');
    }
  } finally { running.delete(batchId); status('Upload-Queue aktualisiert.'); }
}
async function add(files) {
  const list = Array.from(files || []).filter(file => file && file.size <= (config.maxFileSize || 1024 * 1024 * 1024));
  if (!list.length) return;
  const pending = new Map(queue.filter(item => item.state === 'needs_files' || !item.file).map(item => [signature(item), item]));
  const matched = [];
  const fresh = [];
  for (const file of list) { const item = pending.get(signature(file)); if (item) { item.file = file; item.state = 'queued'; matched.push(item); pending.delete(signature(file)); } else fresh.push(file); }
  if (matched.length) { await persist(matched); void processBatch(matched); }
  if (fresh.length) void processBatch(await makeBatch(fresh));
}
async function restore() {
  const batches = await sw('listBatches');
  for (const batchId of batches || []) { const items = await sw('snapshot', { batchId }); queue.push(...(items || []).map(item => ({ ...item, state: item.fileId ? item.state : 'needs_files' }))); }
  status('Queue wiederhergestellt.');
}
self.onmessage = event => {
  const message = event.data || {};
  if (message.type === 'init') { config = message.config || {}; principal = message.principal || principal; csrfToken = message.csrf || ''; owner = message.owner || crypto.randomUUID(); void restore().catch(error => status(String(error))); return; }
  if (message.type === 'add') { void add(message.files); return; }
  if (message.type === 'swResponse') { const request = swRequests.get(message.id); if (!request) return; swRequests.delete(message.id); message.ok ? request.resolve(message.result) : request.reject(new Error(message.error || 'Queue error')); return; }
};
