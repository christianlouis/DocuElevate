/* Single upload orchestrator. The page is an adapter; durable metadata and
 * leases remain in the service worker, while this worker owns all execution. */
importScripts('/static/js/upload-preflight-worker.js');

const WINDOW = 200;
let config = {}, principal = 'single-user', csrfToken = '', owner = '';
let queue = [], running = new Set(), capacities = new Map(), sockets = new Map(), swRequests = new Map(), nextRpc = 0;
let activeUploads = 0, ready = Promise.resolve(), controllerInspectionTail = Promise.resolve();

function status(message, extra = {}) {
  const visible = queue.slice(0, 100).map(({ file, ...item }) => item);
  self.postMessage({ type: 'status', message, queue: visible, total: queue.length,
    accepted: queue.filter(item => item.fileId != null).length, failed: queue.filter(item => item.state === 'failed').length, ...extra });
}
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
    if (!response.ok) { const error = new Error(`Upload request failed (${response.status})`); error.permanent = response.status < 500; throw error; }
    return response.json();
  }
}
function signature(file) { return JSON.stringify([file.name, file.size, file.lastModified || 0]); }
function inspectFile(item) {
  const task = controllerInspectionTail.then(() => self.inspectUploadFile({ id: item.key, file: item.file, name: item.name, mime: item.file.type }));
  controllerInspectionTail = task.catch(() => {});
  return task;
}
function selectReady(items, capacity) {
  const limit = Math.max(0, Math.min(Number(capacity?.slots || 0), Number(config.concurrency || 3)));
  const maxBytes = capacity?.max_bytes == null ? Infinity : Number(capacity.max_bytes);
  const selected = []; let bytes = 0;
  for (const item of items) {
    if (selected.length >= limit) break;
    if (item.state !== 'queued' || !item.file || item.fileId || item.duplicateOf || bytes + item.size > maxBytes) continue;
    selected.push(item); bytes += item.size;
  }
  return selected;
}
function dedup(items) {
  const changed = [], changedSet = new Set();
  const remember = item => { if (!changedSet.has(item)) { changedSet.add(item); changed.push(item); } };
  if (config.enableDeduplication === false) { items.forEach(item => { if (item.duplicateOf !== undefined) { delete item.duplicateOf; remember(item); } }); return changed; }
  const groups = new Map();
  for (const item of items) {
    if (item.duplicateOf !== undefined) { delete item.duplicateOf; remember(item); }
    if (!item.sha256 || item.state === 'failed') continue;
    if (!groups.has(item.sha256)) groups.set(item.sha256, []);
    groups.get(item.sha256).push(item);
  }
  for (const group of groups.values()) {
    const leader = group.find(item => item.fileId) || group.find(item => item.file);
    if (!leader) continue;
    for (const item of group) if (item !== leader) {
      if (item.duplicateOf !== leader.key) { item.duplicateOf = leader.key; remember(item); }
      if (leader.fileId && (item.fileId !== leader.fileId || item.state !== 'duplicate')) { item.fileId = leader.fileId; item.state = 'duplicate'; remember(item); }
    }
  }
  return changed;
}
async function persist(items) { if (items.length) await sw('putMany', { items: items.map(item => ({ key: item.key, batchId: item.batchId, name: item.name, size: item.size, lastModified: item.lastModified, state: item.state, sha256: item.sha256, mime: item.mime, fileId: item.fileId, duplicateOf: item.duplicateOf })) }); }
async function makeBatch(files) {
  const batch = await api('/api/uploads/batches', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ client_batch_id: crypto.randomUUID(), total_files: files.length, total_bytes: files.reduce((sum, file) => sum + file.size, 0) }) });
  const items = files.map(file => ({ key: crypto.randomUUID(), batchId: batch.batch_id, file, name: file.name, size: file.size, lastModified: file.lastModified || 0, state: 'queued' }));
  queue.push(...items); await persist(items); status(`${queue.length} Dateien in der Upload-Queue.`); return items;
}
function matchPendingFiles(files) {
  const pending = new Map();
  for (const item of queue) {
    if (item.state !== 'needs_files') continue;
    const key = signature(item); if (!pending.has(key)) pending.set(key, []); pending.get(key).push(item);
  }
  const matched = [], fresh = [];
  for (const file of files) {
    const key = signature(file), candidates = pending.get(key), item = candidates?.shift();
    if (item) { item.file = file; item.state = 'queued'; matched.push(item); if (!candidates.length) pending.delete(key); } else fresh.push(file);
  }
  return { matched, fresh };
}
function connectCapacity(batchId) {
  if (typeof WebSocket === 'undefined' || sockets.has(batchId)) return;
  const protocol = self.location?.protocol === 'https:' ? 'wss' : 'ws';
  const host = self.location?.host; if (!host) return;
  const socket = new WebSocket(`${protocol}://${host}/api/uploads/events?batch_id=${encodeURIComponent(batchId)}`); sockets.set(batchId, socket);
  socket.onopen = () => { socket._heartbeat = setInterval(() => { if (socket.readyState === WebSocket.OPEN) socket.send('capacity'); }, 5000); };
  socket.onmessage = event => { try { const message = JSON.parse(event.data); if (message.capacity) capacities.set(batchId, message.capacity); if (message.slots !== undefined) capacities.set(batchId, message); } catch (_) {} };
  socket.onclose = () => { clearInterval(socket._heartbeat); if (sockets.get(batchId) === socket) sockets.delete(batchId); if (running.has(batchId)) setTimeout(() => connectCapacity(batchId), 5000); };
}
async function acquireUploadSlot() {
  while (activeUploads >= Math.max(1, Number(config.concurrency || 3))) await new Promise(resolve => setTimeout(resolve, 100));
  activeUploads += 1;
}
async function send(item) {
  await acquireUploadSlot();
  let leased;
  try { leased = await sw('lease', { key: item.key, owner, ttl: 60000 }); }
  catch (error) { activeUploads -= 1; status(String(error)); return false; }
  if (!leased) { activeUploads -= 1; return false; }
  const renewal = setInterval(() => sw('lease', { key: item.key, owner, ttl: 60000 }).catch(() => {}), 10000);
  try {
    const body = new FormData(); body.append('file', item.file); body.append('batch_id', item.batchId); body.append('client_id', item.key); body.append('sha256', item.sha256);
    const result = await api('/api/uploads/files', { method: 'POST', body });
    item.fileId = result.file_id; item.state = result.duplicate ? 'duplicate' : result.state || 'accepted'; item.file = null; await persist([item]);
    self.postMessage({ type: 'accepted', fileId: item.fileId, filename: item.name, state: item.state }); return true;
  } catch (error) { item.state = error.permanent ? 'failed' : 'queued'; await persist([item]); status(error.permanent ? `Upload fehlgeschlagen: ${error.message}` : `Upload pausiert: ${error.message}`); return false; }
  finally { clearInterval(renewal); await sw('release', { key: item.key, owner }).catch(() => {}); activeUploads -= 1; }
}
async function processBatch(items) {
  const batchId = items[0]?.batchId; if (!batchId || running.has(batchId)) return;
  running.add(batchId); connectCapacity(batchId);
  try {
    for (let offset = 0; offset < items.length; offset += WINDOW) {
      const group = items.slice(offset, offset + WINDOW);
      for (const item of group.filter(item => item.file && !item.fileId)) {
        try { const result = await inspectFile(item); item.sha256 = result.sha256; item.mime = result.mime; }
        catch (error) { item.state = 'failed'; status(String(error)); }
      }
      await persist(dedup(queue));
      const check = group.filter(item => item.state === 'queued' && item.file && item.sha256 && !item.duplicateOf);
      if (check.length) {
        const result = await api('/api/uploads/preflight', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ batch_id: batchId, files: check.map(item => ({ client_id: item.key, sha256: item.sha256, size: item.size, mime: item.mime })) }) });
        for (const entry of result.files || []) { const item = check.find(candidate => candidate.key === entry.client_id); if (item && entry.state === 'duplicate') { item.state = 'duplicate'; item.fileId = entry.file_id; } }
      }
      await persist([...new Set([...group, ...dedup(queue)])]);
      for (;;) {
        const capacity = capacities.get(batchId) || await api(`/api/uploads/capacity?batch_id=${encodeURIComponent(batchId)}`);
        capacities.set(batchId, capacity);
        const selected = selectReady(group, capacity);
        if (!selected.length) { if (!group.some(item => item.state === 'queued' && item.file && !item.fileId && !item.duplicateOf)) break; capacities.delete(batchId); status('Server pausiert die Uploads – warte auf Kapazität…'); await new Promise(resolve => setTimeout(resolve, 2000)); continue; }
        await Promise.all(selected.map(send)); await persist([...new Set([...group, ...dedup(queue)])]);
      }
      status('Upload-Queue wird verarbeitet.');
    }
  } finally {
    running.delete(batchId); const socket = sockets.get(batchId); if (socket) { clearInterval(socket._heartbeat); socket.close(); } sockets.delete(batchId); status('Upload-Queue aktualisiert.');
    // A reselection can arrive while this batch is processing. The current
    // bounded window is a snapshot, so schedule those new entries afterwards.
    const waiting = queue.filter(item => item.batchId === batchId && item.state === 'queued' && item.file && !item.fileId && !item.duplicateOf);
    if (waiting.length) void processBatch(waiting).catch(error => status(`Upload pausiert: ${error.message || error}`));
  }
}
async function add(files) {
  await ready;
  const list = Array.from(files || []).filter(file => file && file.size <= (config.maxFileSize || 1024 * 1024 * 1024));
  if (!list.length) return;
  const { matched, fresh } = matchPendingFiles(list);
  if (matched.length) {
    await persist(matched);
    for (const batch of new Map(matched.map(item => [item.batchId, null])).keys()) {
      void processBatch(queue.filter(item => item.batchId === batch)).catch(error => status(`Upload pausiert: ${error.message || error}`));
    }
  }
  if (fresh.length) {
    const batch = await makeBatch(fresh);
    void processBatch(batch).catch(error => status(`Upload pausiert: ${error.message || error}`));
  }
}
async function restore() {
  const batches = await sw('listBatches');
  for (const batchId of batches || []) {
    const items = await sw('snapshot', { batchId });
    const byClient = new Map((items || []).map(item => [item.key, item]));
    const changed = [];
    let cursor = null;
    do {
      const snapshot = await api(`/api/uploads/batches/${encodeURIComponent(batchId)}?limit=${WINDOW}${cursor === null ? '' : `&cursor=${cursor}`}`);
      for (const server of snapshot.items || []) {
        const item = byClient.get(server.client_id);
        if (item && server.file_id && item.fileId !== server.file_id) { item.fileId = server.file_id; item.state = server.state || item.state; changed.push(item); }
      }
      cursor = snapshot.next_cursor ?? null;
    } while (cursor !== null);
    await persist(changed);
    queue.push(...(items || []).map(item => ({ ...item, state: item.fileId ? item.state : (item.state === 'failed' ? 'failed' : 'needs_files') })));
  }
  status('Queue wiederhergestellt.');
}
self.onmessage = event => {
  const message = event.data || {};
  if (message.type === 'init') { config = message.config || {}; principal = message.principal || principal; csrfToken = message.csrf || ''; owner = message.owner || crypto.randomUUID(); ready = restore().catch(error => { status(String(error)); return false; }); return; }
  if (message.type === 'add') { void add(message.files).catch(error => status(String(error))); return; }
  if (message.type === 'swResponse') { const request = swRequests.get(message.id); if (!request) return; swRequests.delete(message.id); message.ok ? request.resolve(message.result) : request.reject(new Error(message.error || 'Queue error')); return; }
};
if (self.UPLOAD_CONTROLLER_TEST) self.__uploadControllerTest = { add, restore, send, status, api, dedup, inspect: self.inspectUploadFile, matchPendingFiles, selectReady, state: () => ({ queue, activeUploads, running }) };
