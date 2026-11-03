/* Single upload orchestrator. The page is an adapter; durable metadata and
 * leases remain in the service worker, while this worker owns all execution. */
importScripts('/static/js/upload-preflight-worker.js');

const WINDOW = 200;
const STATUS_RETRIES = 2;
let config = {}, principal = 'single-user', csrfToken = '', owner = '';
let queue = [], running = new Set(), capacities = new Map(), sockets = new Map(), swRequests = new Map(), nextRpc = 0;
let activeUploads = 0, ready = Promise.resolve(), controllerInspectionTail = Promise.resolve();
let refreshTimer = null;
const retryTimers = new Map();
let pendingAdds = 0, phase = 'Initialisierung', pausedReason = '', lastCapacity = null, lastWebSocket = null, processingHealth = null, snapshotError = '', restored = false, clearGeneration = 0, queueEpoch = 0, statusRevision = 0, actionBusy = false, lastActionFeedback = null, clearBarrier = Promise.resolve();
const requestControllers = new Map(), removedKeys = new Set(), pendingServerReconcile = new Set();

function timestamp() { return new Date().toISOString(); }
function diagnostics() {
  return { worker: 'bereit', phase, pausedReason, capacity: lastCapacity, websocket: lastWebSocket };
}
function rememberCapacity(batchId, capacity, source) {
  if (!capacity) return;
  if (capacity.processing) processingHealth = capacity.processing;
  lastCapacity = { slots: capacity.slots, maxBytes: capacity.max_bytes, source, batchId, at: timestamp() };
}
function rememberWebSocket(state) { lastWebSocket = { state, at: timestamp() }; }
function context() { return { epoch: queueEpoch, generation: clearGeneration }; }
function current(value) { return !value || value.epoch === queueEpoch && value.generation === clearGeneration; }
function currentItem(value, item) { return current(value) && !removedKeys.has(item.key); }
function abortError() { const error = new Error('Lokale Upload-Queue wurde beendet'); error.name = 'AbortError'; return error; }
function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener?.('abort', () => { clearTimeout(timer); reject(abortError()); }, { once: true });
  });
}
function makeAbortController() {
  if (typeof AbortController !== 'undefined') return new AbortController();
  let aborted = false; const listeners = [];
  const signal = { get aborted() { return aborted; }, addEventListener(type, listener) { if (type === 'abort') listeners.push(listener); } };
  return { signal, abort() { if (aborted) return; aborted = true; listeners.splice(0).forEach(listener => listener()); } };
}
function beginRequest(key) {
  const controller = makeAbortController(); requestControllers.set(key, controller); return controller;
}
function endRequest(key, controller) { if (requestControllers.get(key) === controller) requestControllers.delete(key); }
function stopItem(key) { const controller = requestControllers.get(key); if (controller) { controller.abort(); requestControllers.delete(key); } }
function stopRuntime() {
  for (const [key, controller] of requestControllers) { controller.abort(); requestControllers.delete(key); }
  for (const [batchId, timer] of retryTimers) { clearTimeout(timer); retryTimers.delete(batchId); }
  for (const [batchId, socket] of sockets) { clearInterval(socket._heartbeat); socket.close(); sockets.delete(batchId); }
  if (refreshTimer) { clearTimeout(refreshTimer); refreshTimer = null; }
}
function feedback(message, busy = false) { lastActionFeedback = { message, busy }; status(message, { actionFeedback: lastActionFeedback }); }

function status(message, extra = {}) {
  const priority = item => String(item.state || '').includes('failed') ? 0 : ['queued', 'needs_files', 'processing'].includes(item.state) ? 1 : 2;
  const buckets = [[], [], []];
  for (const item of queue) buckets[priority(item)].push(item);
  const visible = buckets.flatMap(bucket => bucket.slice(0, 100)).slice(0, 100).map(({ file, ...item }) => item);
  const counts = classify(queue);
  self.postMessage({ type: 'status', revision: ++statusRevision, message, queue: visible, total: queue.length + pendingAdds,
    accepted: counts.accepted, complete: counts.complete, failed: counts.failed,
    needsFiles: counts.needsFiles, processing: counts.processing, counts: { ...counts, total: queue.length + pendingAdds }, processingHealth, snapshotError, diagnostics: diagnostics(), actionFeedback: lastActionFeedback, ...extra });
}
function classify(items) {
  const counts = { needsFiles: 0, ready: 0, uploading: 0, waiting: 0, processing: 0, complete: 0, duplicate: 0, failed: 0, accepted: 0 };
  for (const item of items) {
    const state = String(item.state || '');
    if (item.fileId != null && state !== 'uploading') counts.accepted += 1;
    if (state === 'needs_files') counts.needsFiles += 1;
    else if (state === 'queued' && !item.fileId) counts.ready += 1;
    else if (state === 'uploading') counts.uploading += 1;
    else if (state === 'accepted' || state === 'queued') counts.waiting += 1;
    else if (state === 'processing') counts.processing += 1;
    else if (state === 'complete' || state === 'completed') counts.complete += 1;
    else if (state === 'duplicate') counts.duplicate += 1;
    else if (state.includes('failed')) counts.failed += 1;
  }
  return counts;
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
async function api(url, options = {}, maxRetries = Infinity) {
  let backoff = 500, retries = 0;
  const signal = options.signal;
  const retry = async error => {
    if (signal?.aborted) throw abortError();
    if (retries >= maxRetries) throw error;
    retries += 1; await wait(backoff, signal); backoff = Math.min(backoff * 2, 30000);
  };
  for (;;) {
    if (signal?.aborted) throw abortError();
    let response;
    try { response = await fetch(url, { ...options, headers: { ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}), ...options.headers } }); }
    catch (error) { if (signal?.aborted || error?.name === 'AbortError') throw abortError(); await retry(error); continue; }
    if (response.status === 429) {
      phase = 'pausiert'; pausedReason = 'Serverlimit erreicht'; status('Serverlimit erreicht – Upload pausiert.');
      if (retries >= maxRetries) throw new Error('Upload request failed (429)');
      retries += 1; await wait(maxRetries === Infinity ? retryAfter(response, backoff) : Math.min(5000, retryAfter(response, backoff)), signal); backoff = Math.min(backoff * 2, 30000); continue;
    }
    if (response.status >= 500) { await retry(new Error(`Upload request failed (${response.status})`)); continue; }
    if (!response.ok) {
      let detail = '';
      try {
        const payload = await response.json();
        detail = typeof payload?.detail === 'string' ? payload.detail : typeof payload?.message === 'string' ? payload.message : typeof payload?.error === 'string' ? payload.error : '';
      } catch (_) { /* A non-JSON rejection still gets a useful status code. */ }
      const error = new Error(`Upload request failed (${response.status})${detail ? `: ${detail}` : ''}`);
      error.permanent = response.status < 500; error.status = response.status; throw error;
    }
    return response.json();
  }
}
function markStatusUnavailable(error) {
  snapshotError = error.message || String(error);
  processingHealth = { status: 'unknown', detail: 'Status derzeit nicht verfügbar' };
}
async function readStatus(url) {
  try { return await api(url, {}, STATUS_RETRIES); }
  catch (error) { markStatusUnavailable(error); throw error; }
}
async function readCapacity(batchId) {
  const capacity = await readStatus(`/api/uploads/capacity?batch_id=${encodeURIComponent(batchId)}`);
  rememberCapacity(batchId, capacity, 'Server');
  return capacity;
}
function signature(file) { return JSON.stringify([file.name, file.size, file.lastModified || 0]); }
function validSha256(value) { return /^[0-9a-f]{64}$/i.test(String(value || '')); }
function validClientId(value) { return typeof value === 'string' && value.trim().length > 0; }
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
    if (item.state !== 'queued' || !item.file || item.fileId || item.duplicateOf || !validClientId(item.key) || !validSha256(item.sha256) || bytes + item.size > maxBytes) continue;
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
async function persist(items, value = context()) {
  items = items.filter(item => validClientId(item.key));
  if (!items.length || !current(value)) return { ignored: true, generation: clearGeneration };
  const result = await sw('putMany', { generation: value.generation, items: items.map(item => ({ key: item.key, batchId: item.batchId, name: item.name, size: item.size, lastModified: item.lastModified, state: item.state, error: item.error, errorCode: item.errorCode, sha256: item.sha256, mime: item.mime, fileId: item.fileId, duplicateOf: item.duplicateOf, tryAnyway: Boolean(item.tryAnyway) })) });
  if (result?.generation != null) clearGeneration = Math.max(clearGeneration, Number(result.generation));
  return result || { ignored: false, generation: clearGeneration };
}
async function archiveEligible() {
  if (!restored) { status('Queue wird noch wiederhergestellt.'); return 0; }
  const eligible = queue.filter(item => ['complete', 'completed', 'duplicate'].includes(item.state) && !running.has(item.batchId));
  if (!eligible.length) { status('Keine erledigten Einträge zum Ausblenden.'); return 0; }
  const archived = await sw('archiveMany', { keys: eligible.map(item => item.key), kind: 'completed', owner });
  const keys = new Set(Array.isArray(archived) ? archived : []);
  queue = queue.filter(item => !keys.has(item.key));
  status(`${keys.size} erledigte Einträge lokal ausgeblendet. Server-Dokumente bleiben erhalten.`);
  return keys.size;
}
async function retryFailed() {
  if (!restored) { status('Queue wird noch wiederhergestellt.'); return 0; }
  const retryable = queue.filter(item => String(item.state || '').includes('failed') && item.fileId == null && item.errorCode !== 'unsupported_type' && !/\(415\)/.test(String(item.error || '')) && !running.has(item.batchId));
  for (const item of retryable) { item.state = item.file ? 'queued' : 'needs_files'; item.error = ''; item.errorCode = ''; }
  await persist(retryable);
  for (const batchId of new Set(retryable.filter(item => item.file).map(item => item.batchId))) void processBatch(queue.filter(item => item.batchId === batchId)).catch(error => status(`Upload pausiert: ${error.message || error}`));
  const unsupported = queue.filter(item => String(item.state || '').includes('failed') && item.fileId == null && (item.errorCode === 'unsupported_type' || /\(415\)/.test(String(item.error || '')))).length;
  status(retryable.length ? `${retryable.length} fehlgeschlagene Einträge für Wiederholung vorbereitet.` : unsupported ? `${unsupported} Datei${unsupported === 1 ? '' : 'en'} wurden vom Server nicht unterstützt (415) und werden nicht automatisch erneut versucht.` : 'Keine fehlgeschlagenen Einträge.');
  return retryable.length;
}
async function discardUnsent() {
  if (!restored) { status('Queue wird noch wiederhergestellt.'); return 0; }
  const discardable = queue.filter(item => ['needs_files', 'failed', 'transfer_failed', 'queued'].includes(item.state) && item.fileId == null && !running.has(item.batchId));
  if (!discardable.length) { status('Keine nicht übertragenen Einträge zum Ausblenden.'); return 0; }
  const archived = await sw('archiveMany', { keys: discardable.map(item => item.key), kind: 'unsent', owner });
  const keys = new Set(Array.isArray(archived) ? archived : []); queue = queue.filter(item => !keys.has(item.key));
  status(`${keys.size} nicht übertragene Einträge lokal ausgeblendet. Server-Dokumente bleiben erhalten.`);
  return keys.size;
}
async function removeItems(keys) {
  if (!restored) { status('Queue wird noch wiederhergestellt.'); return 0; }
  const value = context();
  const wanted = new Set((keys || []).filter(Boolean));
  const selected = queue.filter(item => wanted.has(item.key));
  if (!selected.length) { status('Keine passenden Queue-Einträge gefunden.'); return 0; }
  // Tombstone before awaiting the worker: an in-flight request must never put
  // a row back after the user removed it.
  selected.forEach(item => { removedKeys.add(item.key); stopItem(item.key); });
  queue = queue.filter(item => !wanted.has(item.key));
  status(`${selected.length} Einträge werden lokal entfernt …`);
  try {
    const archived = await sw('archiveMany', { keys: selected.map(item => item.key), kind: 'local', owner });
    const archivedKeys = new Set(Array.isArray(archived) ? archived : archived?.keys || []);
    // A rejected key is restored, unless a newer clear/remote update superseded
    // this action. Keep successful tombstones so late async paths stay inert.
    if (current(value) && archivedKeys.size !== selected.length) {
      const restore = selected.filter(item => !archivedKeys.has(item.key));
      if (restore.length) { restore.forEach(item => removedKeys.delete(item.key)); queue.push(...restore); }
    }
    if (current(value)) status(`${archivedKeys.size} Einträge lokal entfernt. Server-Dokumente bleiben erhalten.`);
    return archivedKeys.size;
  } catch (error) {
    if (current(value)) { selected.forEach(item => removedKeys.delete(item.key)); queue.push(...selected); status(`Einträge konnten nicht lokal entfernt werden: ${error.message || error}`); }
    throw error;
  }
}
async function clearQueue() {
  if (!restored) { status('Queue wird noch wiederhergestellt.'); return 0; }
  // First fence all writers and abort requests. We only expose the empty list
  // after durable clearing has committed, so a worker failure cannot fake it.
  queueEpoch += 1;
  const removed = queue.slice(), value = context();
  let releaseClear;
  clearBarrier = new Promise(resolve => { releaseClear = resolve; });
  stopRuntime(); running.clear();
  feedback('Lokale Warteschlange wird geleert …', true);
  try {
    const result = await sw('clearAll', { owner });
    if (!current(value)) return 0;
    clearGeneration = Number(result?.generation || clearGeneration + 1);
    queue = []; removedKeys.clear();
    const count = Number(result?.count ?? removed.length);
    feedback(`${count} lokale Einträge entfernt. Server-Dokumente und die Serververarbeitung bleiben erhalten.`);
    return count;
  } catch (error) {
    if (current(value)) { queue = removed; feedback(`Lokale Warteschlange konnte nicht geleert werden: ${error.message || error}`); }
    throw error;
  } finally {
    releaseClear();
  }
}
async function makeBatch(files, value = context(), tryAnyway = false) {
  const requestKey = `batch:${crypto.randomUUID()}`, controller = beginRequest(requestKey);
  let batch;
  try { batch = await api('/api/uploads/batches', { method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ client_batch_id: crypto.randomUUID(), total_files: files.length, total_bytes: files.reduce((sum, file) => sum + file.size, 0) }) }); }
  finally { endRequest(requestKey, controller); }
  if (!current(value)) return [];
  const items = files.map(file => ({ key: crypto.randomUUID(), batchId: batch.batch_id, file, name: file.name, size: file.size, lastModified: file.lastModified || 0, state: 'queued', tryAnyway }));
  queue.push(...items); const result = await persist(items, value);
  if (!current(value) || result?.ignored) { queue = queue.filter(item => !items.includes(item)); return []; }
  return items;
}
function matchPendingFiles(files, tryAnyway = false) {
  const pending = new Map();
  for (const item of queue) {
    if (!['needs_files', 'failed', 'transfer_failed'].includes(item.state) || item.fileId != null) continue;
    const key = signature(item); if (!pending.has(key)) pending.set(key, []); pending.get(key).push(item);
  }
  const matched = [], fresh = [];
  for (const file of files) {
    const key = signature(file), candidates = pending.get(key), item = candidates?.shift();
    if (item) { item.file = file; item.state = 'queued'; item.tryAnyway = Boolean(tryAnyway); matched.push(item); if (!candidates.length) pending.delete(key); } else fresh.push(file);
  }
  return { matched, fresh };
}
function connectCapacity(batchId) {
  if (typeof WebSocket === 'undefined' || sockets.has(batchId)) return;
  const protocol = self.location?.protocol === 'https:' ? 'wss' : 'ws';
  const host = self.location?.host; if (!host) return;
  const socket = new WebSocket(`${protocol}://${host}/api/uploads/events?batch_id=${encodeURIComponent(batchId)}`); sockets.set(batchId, socket); rememberWebSocket('Verbindung wird aufgebaut');
  socket.onopen = () => { rememberWebSocket('verbunden'); socket._heartbeat = setInterval(() => { if (socket.readyState === WebSocket.OPEN) socket.send('capacity'); }, 5000); };
  socket.onmessage = event => { try { const message = JSON.parse(event.data); if (message.capacity) { capacities.set(batchId, message.capacity); rememberCapacity(batchId, message.capacity, 'WebSocket'); } if (message.slots !== undefined) { capacities.set(batchId, message); rememberCapacity(batchId, message, 'WebSocket'); } } catch (_) {} };
  socket.onclose = () => { rememberWebSocket('getrennt'); clearInterval(socket._heartbeat); if (sockets.get(batchId) === socket) sockets.delete(batchId); if (running.has(batchId)) setTimeout(() => connectCapacity(batchId), 5000); };
}
async function acquireUploadSlot(value, signal) {
  while (activeUploads >= Math.max(1, Number(config.concurrency || 3))) {
    if (!current(value)) throw abortError();
    await wait(100, signal);
  }
  if (!current(value)) throw abortError();
  activeUploads += 1;
}
async function reconcileDurable(batchId, value = context()) {
  const snapshot = await sw('snapshot', { batchId });
  if (!current(value)) return new Map();
  const stored = new Map((snapshot || []).map(item => [item.key, item]));
  for (const item of queue.filter(candidate => candidate.batchId === batchId)) {
    const durable = stored.get(item.key);
    if (!durable) { item.state = 'archived'; continue; }
    const needsFiles = item.state === 'needs_files' && !item.file && durable.fileId == null;
    const localSha = item.sha256, localMime = item.mime, localOverride = item.tryAnyway;
    Object.assign(item, durable, { file: item.file });
    if (!validSha256(durable.sha256) && validSha256(localSha)) item.sha256 = localSha;
    if (!durable.mime && localMime) item.mime = localMime;
    if (item.file && !item.fileId && localOverride) item.tryAnyway = true;
    // Durable queued is authoritative for ownership, but it cannot recreate
    // browser bytes after a reload. Keep the actionable UI projection.
    if (needsFiles) item.state = 'needs_files';
  }
  queue = queue.filter(item => item.batchId !== batchId || stored.has(item.key));
  return stored;
}
function scheduleBatchRetry(batchId, value = context()) {
  if (retryTimers.has(batchId)) return;
  retryTimers.set(batchId, setTimeout(() => {
    retryTimers.delete(batchId);
    if (!current(value)) return;
    const waiting = queue.filter(item => item.batchId === batchId && item.state === 'queued' && item.file && !item.fileId && !item.duplicateOf);
    if (waiting.length) void processBatch(waiting, value).catch(error => current(value) && status(`Upload pausiert: ${error.message || error}`));
  }, 5000));
}
async function send(item, value = context()) {
  const controller = beginRequest(item.key);
  let leased = false, acquired = false, renewal;
  try {
    await acquireUploadSlot(value, controller.signal); acquired = true;
    if (!currentItem(value, item)) return false;
    if (!validClientId(item.key)) {
      item.state = 'failed'; item.errorCode = 'file_inspection_failed'; item.error = 'Ungültiger lokaler Eintrag. Bitte entfernen und die Datei erneut auswählen.';
      status(item.error); return false;
    }
    if (!validSha256(item.sha256)) {
      if (item.file) {
        try {
          const inspected = await inspectFile(item);
          if (!currentItem(value, item)) return false;
          if (!validSha256(inspected.sha256)) throw new Error('Datei konnte nicht sicher geprüft werden');
          item.sha256 = inspected.sha256; item.mime = inspected.mime;
        } catch (error) {
          if (!currentItem(value, item)) return false;
          item.state = 'failed'; item.errorCode = 'file_inspection_failed'; item.error = error.message || 'Datei konnte nicht sicher geprüft werden';
          await persist([item], value); return false;
        }
        await persist([item], value);
      } else {
        item.state = 'needs_files'; item.errorCode = 'file_inspection_failed'; item.error = 'Originaldatei muss erneut ausgewählt werden';
        await persist([item], value); return false;
      }
    }
    if (!currentItem(value, item) || !item.file || item.fileId || item.duplicateOf) return false;
    leased = await sw('lease', { key: item.key, owner, ttl: 60000 });
    if (!currentItem(value, item)) return false;
    if (!leased) {
      try { await reconcileDurable(item.batchId, value); } catch (error) { if (current(value)) status(`Lokale Queue konnte nicht abgeglichen werden: ${error.message || error}`); }
      return false;
    }
    if (!item.file || item.fileId || item.duplicateOf) return false;
    renewal = setInterval(() => currentItem(value, item) && sw('lease', { key: item.key, owner, ttl: 60000 }).catch(() => {}), 10000);
    item.state = 'uploading'; item.error = ''; item.errorCode = ''; await persist([item], value);
    if (!currentItem(value, item)) return false;
    // No await between this guard and constructing the request: reconciliation
    // may have run while acquiring the lease or persisting the uploading state.
    if (!item.file || item.fileId || item.duplicateOf) return false;
    if (!validClientId(item.key) || !validSha256(item.sha256)) {
      item.state = 'failed'; item.errorCode = 'file_inspection_failed'; item.error = 'Upload-Daten sind unvollständig. Bitte erneut versuchen.';
      await persist([item], value); return false;
    }
    status('Dateien werden übertragen.');
    const body = new FormData(); body.append('file', item.file); body.append('batch_id', item.batchId); body.append('client_id', item.key); body.append('sha256', item.sha256); if (item.tryAnyway) body.append('inspect_content', 'true');
    const result = await api('/api/uploads/files', { method: 'POST', body, signal: controller.signal });
    if (!currentItem(value, item)) return false;
    item.fileId = result.file_id; item.state = result.duplicate ? 'duplicate' : result.state || 'accepted'; item.file = null;
    const persisted = await persist([item], value); if (!currentItem(value, item) || persisted?.ignored) return false;
    scheduleRefresh(value);
    self.postMessage({ type: 'accepted', fileId: item.fileId, filename: item.name, state: item.state }); return true;
  } catch (error) {
    if (!currentItem(value, item) || error?.name === 'AbortError') return false;
    if (!leased) { status(String(error)); return false; }
    item.state = error.permanent ? 'transfer_failed' : 'queued';
    item.errorCode = error.status === 415 ? 'unsupported_type' : error.permanent ? 'transfer_rejected' : 'network_retrying'; item.error = error.message;
    await persist([item], value);
    if (currentItem(value, item)) status(error.permanent ? `Upload fehlgeschlagen: ${error.message}` : `Upload pausiert: ${error.message}`);
    return false;
  } finally {
    clearInterval(renewal); endRequest(item.key, controller);
    if (leased) await sw('release', { key: item.key, owner }).catch(() => {});
    if (acquired) activeUploads = Math.max(0, activeUploads - 1);
  }
}
async function processBatch(items, value = context()) {
  const batchId = items[0]?.batchId; if (!batchId || running.has(batchId)) return;
  if (!current(value)) return;
  let deferred = false;
  running.add(batchId); phase = 'Upload wird vorbereitet'; pausedReason = ''; connectCapacity(batchId);
  try {
    for (let offset = 0; offset < items.length && current(value); offset += WINDOW) {
      const group = items.slice(offset, offset + WINDOW);
      phase = 'Dateien werden geprüft';
      for (const item of group.filter(item => item.file && !item.fileId)) {
        try {
          if (!validClientId(item.key)) throw new Error('Ungültiger lokaler Eintrag. Bitte entfernen und die Datei erneut auswählen.');
          const result = await inspectFile(item);
          if (!validSha256(result.sha256)) throw new Error('Datei konnte nicht sicher geprüft werden');
          item.sha256 = result.sha256; item.mime = result.mime;
        }
        catch (error) { if (!currentItem(value, item)) break; item.state = 'failed'; item.errorCode = 'file_inspection_failed'; item.error = error.message || String(error); status(item.error); }
      }
      if (!current(value)) break;
      await persist(dedup(queue), value);
      if (!current(value)) break;
      const check = group.filter(item => item.state === 'queued' && item.file && validSha256(item.sha256) && !item.duplicateOf);
      if (check.length) {
        phase = 'Server prüft Dateien';
        const requestKey = `batch:${batchId}:${value.epoch}:${offset}`, controller = beginRequest(requestKey);
        let result;
        try { result = await api('/api/uploads/preflight', { method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ batch_id: batchId, files: check.map(item => ({ client_id: item.key, sha256: item.sha256, size: item.size, mime: item.mime })) }) }); }
        finally { endRequest(requestKey, controller); }
        if (!current(value)) break;
        for (const entry of result.files || []) { const item = check.find(candidate => candidate.key === entry.client_id); if (item && entry.state === 'duplicate') { item.state = 'duplicate'; item.fileId = entry.file_id; } }
      }
      if (!current(value)) break;
      await persist([...new Set([...group, ...dedup(queue)])], value);
      let noProgress = 0;
      for (; current(value);) {
        const pushedCapacity = capacities.get(batchId);
        const capacity = pushedCapacity || await readCapacity(batchId);
        if (!current(value)) break;
        capacities.set(batchId, capacity); rememberCapacity(batchId, capacity, pushedCapacity ? 'WebSocket' : 'Server');
        const selected = selectReady(group, capacity);
        if (!selected.length) { if (!group.some(item => item.state === 'queued' && item.file && !item.fileId && !item.duplicateOf && validSha256(item.sha256))) break; capacities.delete(batchId); phase = 'pausiert'; pausedReason = 'Server meldet keine freie Upload-Kapazität'; status('Server pausiert die Uploads – warte auf Kapazität…'); await wait(2000); continue; }
        const pendingBefore = group.filter(item => item.state === 'queued' && item.file && !item.fileId && !item.duplicateOf).length;
        phase = 'Dateien werden übertragen'; pausedReason = '';
        const results = await Promise.all(selected.map(item => send(item, value))); if (!current(value)) break; await persist([...new Set([...group, ...dedup(queue)])], value);
        const pendingAfter = group.filter(item => item.state === 'queued' && item.file && !item.fileId && !item.duplicateOf).length;
        if (results.some(Boolean) || pendingAfter < pendingBefore) { noProgress = 0; continue; }
        noProgress += 1;
        if (noProgress >= 3) {
          deferred = true; phase = 'pausiert'; pausedReason = 'Upload wird in einem anderen Tab ausgeführt oder die lokale Queue ist veraltet';
          status('Upload wartet auf den Abgleich mit einem anderen Tab.');
          scheduleBatchRetry(batchId, value);
          break;
        }
        await wait(1000);
      }
      if (current(value)) status('Upload-Queue wird verarbeitet.');
    }
  } finally {
    running.delete(batchId);
    if (!current(value)) return;
    phase = 'wartet auf weitere Dateien'; const socket = sockets.get(batchId); if (socket) { clearInterval(socket._heartbeat); socket.close(); } sockets.delete(batchId); status('Upload-Queue aktualisiert.');
    // A reselection can arrive while this batch is processing. The current
    // bounded window is a snapshot, so schedule those new entries afterwards.
    const waiting = current(value) ? queue.filter(item => item.batchId === batchId && item.state === 'queued' && item.file && !item.fileId && !item.duplicateOf) : [];
    if (waiting.length) {
      if (deferred) scheduleBatchRetry(batchId, value);
      else void processBatch(waiting, value).catch(error => current(value) && status(`Upload pausiert: ${error.message || error}`));
    }
  }
}
async function add(files, tryAnyway = false) {
  const arrivalEpoch = queueEpoch;
  const count = Array.from(files || []).length;
  if (count) { pendingAdds += count; phase = 'neue Dateien werden eingeordnet'; status(`${count} Datei${count === 1 ? '' : 'en'} zur Upload-Queue hinzugefügt.`); }
  try {
    await ready;
    const barrier = clearBarrier;
    await barrier;
    if (arrivalEpoch !== queueEpoch) return;
    const beforeFence = context();
    // A tab which existed before another tab cleared the queue must obtain the
    // new fence before it writes its first new upload.
    const clearState = await sw('clearState');
    if (!current(beforeFence)) return;
    const generation = Number(clearState?.generation || 0);
    if (generation > clearGeneration) {
      // A sleeping tab may have missed the broadcast. Its old in-memory rows
      // are invalid, but this fresh selection may start in the new generation.
      queueEpoch += 1; stopRuntime(); running.clear(); queue = []; removedKeys.clear();
      clearGeneration = generation;
    }
    const value = context();
    const list = Array.from(files || []).filter(file => file && file.size <= (config.maxFileSize || 1024 * 1024 * 1024));
    if (!list.length) return;
    const { matched, fresh } = matchPendingFiles(list, tryAnyway);
    if (matched.length) {
      await persist(matched, value);
      if (!current(value)) return;
      for (const batch of new Map(matched.map(item => [item.batchId, null])).keys()) {
        void processBatch(queue.filter(item => item.batchId === batch), value).catch(error => current(value) && status(`Upload pausiert: ${error.message || error}`));
      }
    }
    if (fresh.length) { const batch = await makeBatch(fresh, value, tryAnyway); if (current(value)) void processBatch(batch, value).catch(error => current(value) && status(`Upload pausiert: ${error.message || error}`)); }
  } finally { if (count) { pendingAdds -= count; status('Upload-Queue aktualisiert.'); } }
}
async function restore() {
  phase = 'gespeicherte Queue wird wiederhergestellt';
  const batches = await sw('listBatches');
  const clearState = await sw('clearState'); clearGeneration = Number(clearState?.generation || 0);
  const value = context();
  if (!current(value)) return false;
  for (const batchId of batches || []) {
    const items = await sw('snapshot', { batchId });
    if (!current(value)) return false;
    if (!items?.length) continue;
    // This is display-only state: files cannot be reconstructed after reload.
    // Never persist this projection back over durable queued records.
    const restoredItems = (items || []).map(item => ({ ...item, state: item.fileId ? item.state : (item.state === 'failed' || item.state === 'transfer_failed' ? item.state : 'needs_files') }));
    queue.push(...restoredItems);
    pendingServerReconcile.add(batchId);
  }
  phase = 'wartet auf weitere Dateien'; restored = true; status('Queue wiederhergestellt.');
  scheduleRefresh(value);
  return true;
}
async function refreshPending(value = context()) {
  if (!current(value)) return;
  phase = 'Verarbeitungsstatus wird abgeglichen';
  try {
    const durableBatches = [...new Set(queue.map(item => item.batchId).filter(Boolean))];
    for (const batchId of durableBatches) { await reconcileDurable(batchId, value); if (!current(value)) return; }
    // The server can have accepted a file while the browser lost its response.
    // Do this once for restored batches; ordinary all-local rows must not poll
    // the server indefinitely.
    for (const batchId of [...new Set(queue.filter(item => item.fileId || pendingServerReconcile.has(item.batchId)).map(item => item.batchId).filter(Boolean))]) {
      let cursor = null;
      do {
        const snapshot = await readStatus(`/api/uploads/batches/${encodeURIComponent(batchId)}?limit=${WINDOW}${cursor === null ? '' : `&cursor=${cursor}`}`);
        if (!current(value)) return;
        if (snapshot.processing_health) processingHealth = snapshot.processing_health;
        if (snapshot.capacity?.processing) processingHealth = snapshot.capacity.processing;
        snapshotError = '';
        const byClient = new Map(queue.filter(item => item.batchId === batchId).map(item => [item.key, item]));
        const changed = [];
        for (const server of snapshot.items || []) { const item = byClient.get(server.client_id); if (item && server.file_id && (item.state !== server.state || item.errorCode !== server.error_code || item.error !== (server.error || server.error_message))) { item.fileId = server.file_id; item.state = server.state || item.state; item.errorCode = server.error_code || item.errorCode; item.error = server.error || server.error_message || item.error; changed.push(item); } }
        await persist(changed, value); cursor = snapshot.next_cursor ?? null;
      } while (cursor !== null);
      pendingServerReconcile.delete(batchId);
      await readCapacity(batchId);
      if (!current(value)) return;
    }
    phase = 'wartet auf weitere Dateien'; status('Upload-Queue aktualisiert.');
  } catch (error) {
    if (!current(value) || error?.name === 'AbortError') return;
    snapshotError = error.message || String(error); phase = 'Statusabgleich fehlgeschlagen';
    status(`Upload-Queue konnte nicht aktualisiert werden: ${snapshotError}`);
    throw error;
  }
}
function scheduleRefresh(value = context()) {
  if (!self.location?.host || refreshTimer || !queue.length) return;
  refreshTimer = setTimeout(async () => { refreshTimer = null; if (!current(value)) return; try { await refreshPending(value); } catch (_) {} if (current(value)) scheduleRefresh(value); }, 15000);
}
self.onmessage = event => {
  const message = event.data || {};
  if (message.type === 'init') { config = message.config || {}; principal = message.principal || principal; csrfToken = message.csrf || ''; owner = message.owner || crypto.randomUUID(); ready = restore().catch(error => { phase = 'Wiederherstellung fehlgeschlagen'; pausedReason = 'Gespeicherte Queue konnte nicht gelesen werden'; status(String(error)); return false; }).then(result => { if (result) void refreshPending(context()).catch(() => {}); self.postMessage({ type: 'ready', diagnostics: diagnostics() }); return result; }); return; }
  if (message.type === 'add') { void add(message.files, Boolean(message.tryAnyway)).catch(error => status(String(error))); return; }
  if (message.type === 'action') {
    if (actionBusy) { feedback('Eine Queue-Aktion wird bereits ausgeführt.', true); return; }
    let action;
    if (message.action === 'archiveCompleted') action = archiveEligible;
    else if (message.action === 'retryFailed') action = retryFailed;
    else if (message.action === 'discardUnsent') action = discardUnsent;
    else if (message.action === 'clearQueue') action = clearQueue;
    else if (message.action === 'removeItems') action = () => removeItems(message.keys);
    else return;
    actionBusy = true; feedback('Queue-Aktion wird ausgeführt …', true);
    void action().then(count => {
      const labels = { archiveCompleted: 'Erledigte Einträge ausgeblendet', retryFailed: 'Wiederholung vorbereitet', discardUnsent: 'Nicht übertragene Einträge ausgeblendet', removeItems: 'Einträge lokal entfernt', clearQueue: 'Lokale Warteschlange geleert' };
      const unsupported = message.action === 'retryFailed' && !count && queue.filter(item => String(item.state || '').includes('failed') && (item.errorCode === 'unsupported_type' || /\(415\)/.test(String(item.error || '')))).length;
      feedback(unsupported ? `${unsupported} nicht unterstützte Datei${unsupported === 1 ? '' : 'en'} (415) wurden nicht erneut versucht.` : `${labels[message.action] || 'Queue-Aktion abgeschlossen'}: ${Number(count || 0)}.`);
    }).catch(error => { feedback(`Queue-Aktion fehlgeschlagen: ${error.message || error}`); }).finally(() => { actionBusy = false; });
    return;
  }
  if (message.type === 'queueChanged') {
    if (message.principal && message.principal !== principal) return;
    if (message.owner && message.owner === owner) return;
    const generation = Number(message.generation || 0);
    if (message.cleared) {
      if (generation <= clearGeneration) return;
      queueEpoch += 1; clearGeneration = Math.max(clearGeneration, generation); stopRuntime(); running.clear(); queue = []; removedKeys.clear();
      status('Die lokale Queue wurde in einem anderen Tab geleert.');
    } else {
      const keys = new Set(message.keys || []);
      if (keys.size) { keys.forEach(key => { removedKeys.add(key); stopItem(key); }); queue = queue.filter(item => !keys.has(item.key)); status(`${keys.size} Queue-Einträge wurden in einem anderen Tab entfernt.`); }
      clearGeneration = Math.max(clearGeneration, generation);
    }
    return;
  }
  if (message.type === 'swResponse') { const request = swRequests.get(message.id); if (!request) return; swRequests.delete(message.id); message.ok ? request.resolve(message.result) : request.reject(new Error(message.error || 'Queue error')); return; }
};
if (self.UPLOAD_CONTROLLER_TEST) self.__uploadControllerTest = { add, restore, send, status, api, readStatus, dedup, inspect: self.inspectUploadFile, matchPendingFiles, selectReady, classify, archiveEligible, retryFailed, discardUnsent, removeItems, clearQueue, processBatch, refreshPending, reconcileDurable, rememberCapacity, scheduleRefresh, state: () => ({ queue, activeUploads, running, clearGeneration, queueEpoch, statusRevision, actionBusy }) };
