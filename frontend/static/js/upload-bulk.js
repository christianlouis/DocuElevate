/* HTTP carries bytes; the websocket only advertises capacity and status.
 * IndexedDB stores metadata, never a second copy of the selected corpus. */
(function () {
  const WINDOW = 200, HASH_WORKERS = 2, MAX_RETRIES = 5;
  const principal = window.uploadConfig?.queueOwner || 'single-user';
  const owner = crypto.randomUUID(); // Each tab has its own lease identity.
  const storageKey = `docuelevate.upload.batch.${principal}`;
  let registration;
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const csrf = () => {
    const token = typeof getCsrfToken === 'function' ? getCsrfToken() : '';
    return token ? { 'X-CSRF-Token': token } : {};
  };
  function postSW(message) {
    return new Promise((resolve, reject) => {
      const controller = navigator.serviceWorker?.controller || registration?.active;
      if (!controller) return reject(new Error('Persistent upload queue is unavailable'));
      const channel = new MessageChannel();
      const timer = setTimeout(() => { channel.port1.close(); reject(new Error('Queue acknowledgement timed out')); }, 10000);
      channel.port1.onmessage = event => {
        clearTimeout(timer); channel.port1.close();
        event.data?.ok ? resolve(event.data.result) : reject(new Error(event.data?.error || 'Queue error'));
      };
      controller.postMessage({ ...message, principal }, [channel.port2]);
    });
  }
  async function ensureSW() {
    if (!navigator.serviceWorker) throw new Error('This browser needs Service Worker support for resumable uploads');
    registration = await navigator.serviceWorker.register('/upload-queue-sw.js', { scope: '/' });
    await navigator.serviceWorker.ready;
    if (navigator.storage?.persist) await navigator.storage.persist().catch(() => false);
  }
  async function json(url, options = {}) {
    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
      let response;
      try { response = await fetch(url, { ...options, headers: { ...csrf(), ...options.headers } }); }
      catch (error) { if (attempt === MAX_RETRIES - 1) throw error; await sleep(500 * 2 ** attempt); continue; }
      if ((response.status === 429 || response.status >= 500) && attempt < MAX_RETRIES - 1) {
        const value = response.headers.get('Retry-After');
        const seconds = Number(value);
        const delay = value && !Number.isFinite(seconds) ? Date.parse(value) - Date.now() : seconds * 1000;
        await sleep(Math.max(500 * 2 ** attempt, delay || 0)); continue;
      }
      if (!response.ok) throw new Error(`Upload request failed (${response.status})`);
      return response.json();
    }
  }
  function windows(items) { const result = []; for (let i = 0; i < items.length; i += WINDOW) result.push(items.slice(i, i + WINDOW)); return result; }
  function slots(capacity) { return Math.max(0, Math.min(Number(capacity?.slots ?? 0), Number(window.uploadConfig?.concurrency ?? 3))); }
  function selectReady(queue, capacity) {
    const selected = []; let bytes = 0;
    const maxBytes = capacity?.max_bytes == null ? Infinity : Number(capacity.max_bytes);
    for (const item of queue) {
      if (selected.length >= slots(capacity)) break;
      if (item.state !== 'queued' || item.fileId || !item.file || !item.sha256 || item.duplicateOf) continue;
      if (bytes + item.file.size > maxBytes) continue;
      selected.push(item); bytes += item.file.size;
    }
    return selected;
  }
  function matchReselected(savedItems, files) {
    const bySignature = new Map();
    for (const file of files) {
      const signature = JSON.stringify([file.name, file.size, file.lastModified || 0]);
      if (!bySignature.has(signature)) bySignature.set(signature, []);
      bySignature.get(signature).push(file);
    }
    return savedItems.map(item => {
      const signature = JSON.stringify([item.name, item.size, item.lastModified || 0]);
      const file = bySignature.get(signature)?.shift();
      return { ...item, file, state: item.fileId ? item.state : (file ? 'queued' : 'needs_files') };
    });
  }
  function deduplicate(items) {
    if (window.uploadConfig?.enableDeduplication === false) {
      items.forEach(item => { delete item.duplicateOf; });
      return items;
    }
    const seen = new Map();
    for (const item of items) {
      delete item.duplicateOf;
      if (!item.sha256 || item.state === 'failed') continue;
      const candidates = seen.get(item.sha256) || [];
      candidates.push(item);
      // Prefer an admitted item, then a currently transferable item. A
      // needs_files entry must never suppress a reselected copy.
      const leader = candidates.find(candidate => candidate.fileId) || candidates.find(candidate => candidate.file);
      seen.set(item.sha256, candidates);
      if (!leader) continue;
      for (const candidate of candidates) {
        if (candidate.key === leader.key) { delete candidate.duplicateOf; continue; }
        candidate.duplicateOf = leader.key;
        if (leader.fileId) { candidate.state = 'duplicate'; candidate.fileId = leader.fileId; }
      }
    }
    return items;
  }
  function applyPreflightResults(group, result) {
    const byClient = new Map(group.map(item => [item.key, item]));
    for (const entry of result.files || []) {
      const item = byClient.get(entry.client_id);
      if (item && entry.state === 'duplicate') { item.state = 'duplicate'; item.fileId = entry.file_id; }
    }
  }
  function digest(item) {
    return new Promise((resolve, reject) => {
      const worker = new Worker('/static/js/upload-preflight-worker.js');
      const finish = (error, result) => { worker.terminate(); error ? reject(error) : resolve(result); };
      worker.onmessage = event => event.data.error ? finish(new Error(event.data.error)) : finish(null, event.data);
      worker.onerror = () => finish(new Error('File inspection failed'));
      worker.postMessage({ id: item.key, file: item.file, name: item.file.name, mime: item.file.type });
    });
  }
  function metadata(item, batchId) {
    return { key: item.key, batchId: item.batchId || batchId, name: item.name, size: item.size, lastModified: item.lastModified,
      state: item.state, sha256: item.sha256, mime: item.mime, fileId: item.fileId, duplicateOf: item.duplicateOf };
  }
  class Queue {
    constructor(container, status) {
      this.container = container; this.status = status; this.queue = []; this.batchId = null; this.batchIds = [];
      this.capacity = { slots: 0, max_bytes: 0 }; this.running = false;
      this.refreshPromise = null;
    }
    message(text) { if (this.status) this.status.textContent = text; }
    render() {
      if (!this.container) return;
      this.container.replaceChildren();
      for (const item of this.queue.slice(0, 100)) {
        const row = document.createElement('div'); row.className = 'text-xs mb-1';
        const states = { queued: 'wartet', accepted: 'angenommen', duplicate: 'Duplikat', processing: 'in Verarbeitung',
          complete: 'verarbeitet', completed: 'verarbeitet', failed: 'fehlgeschlagen', needs_files: 'Datei erneut auswählen' };
        row.textContent = `${item.name} — ${states[item.state] || item.state}`; this.container.appendChild(row);
      }
      const accepted = this.queue.filter(item => item.fileId).length;
      this.message(`${accepted} von ${this.queue.length} Dateien sicher angenommen. Die Verarbeitung läuft im Hintergrund.`);
    }
    async persist(items) { if (items.length) await postSW({ op: 'putMany', items: items.map(item => metadata(item, this.batchId)) }); }
    async restore() {
      try {
        await ensureSW();
        const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
        const pointers = JSON.parse(localStorage.getItem(`${storageKey}.batches`) || '[]');
        let discovered = [];
        try { discovered = await postSW({ op: 'listBatches' }); } catch (_) { /* local pointers remain a compatibility fallback */ }
        this.batchIds = [...new Set([...(discovered || []), ...(pointers || []), saved?.batchId].filter(Boolean))];
        if (!this.batchIds.length) return;
        this.batchId = this.batchIds[0];
        const snapshots = await Promise.all(this.batchIds.map(batchId => postSW({ op: 'snapshot', batchId })));
        this.queue = snapshots.flat().map(item => ({ ...item, state: item.fileId ? item.state : 'needs_files' }));
        await this.refresh(); this.render(); this.connectEvents();
        if (this.queue.some(item => !item.fileId)) this.message('Queue wiederhergestellt. Bitte die ursprünglichen Dateien erneut auswählen, um ausstehende Uploads fortzusetzen.');
      } catch (error) { this.message(String(error)); }
    }
    async refresh() {
      if (!this.batchId) return;
      if (this.refreshPromise) return this.refreshPromise;
      this.refreshPromise = (async () => {
      let cursor = null;
      do {
        const snapshot = await json(`/api/uploads/batches/${encodeURIComponent(this.batchId)}?limit=${WINDOW}${cursor === null ? "" : `&cursor=${cursor}`}`);
        await this.reconcile(snapshot.items || []);
        cursor = snapshot.next_cursor ?? null;
      } while (cursor !== null);
      this.capacity = await json(`/api/uploads/capacity?batch_id=${encodeURIComponent(this.batchId)}`);
      })();
      try { return await this.refreshPromise; } finally { this.refreshPromise = null; }
    }
    async reconcile(items) {
      const byClient = new Map(this.queue.map(item => [item.key, item])); const changed = [];
      for (const server of items) {
        const item = byClient.get(server.client_id);
        if (item && server.file_id) { item.fileId = server.file_id; item.state = server.state; changed.push(item); }
      }
      await this.persist(changed); this.render();
    }
    connectEvents() {
      if (!this.batchId || typeof WebSocket === 'undefined') return;
      this.socket?.close(); clearTimeout(this.wsTimer); clearInterval(this.heartbeat);
      const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/uploads/events?batch_id=${encodeURIComponent(this.batchId)}`);
      this.socket = socket;
      socket.onopen = () => { void this.refresh().catch(error => this.message(String(error))); this.heartbeat = setInterval(() => { if (socket.readyState === WebSocket.OPEN) socket.send("capacity"); }, 5000); };
      socket.onmessage = event => {
        try {
          const message = JSON.parse(event.data);
          if (message.capacity) this.capacity = message.capacity;
          if (message.type === 'capacity' && message.slots !== undefined) this.capacity = message;
          const items = message.snapshot?.items || message.items;
          if (items) void this.reconcile(items).catch(error => this.message(String(error)));
          if (message.snapshot?.truncated || message.truncated) void this.refresh().catch(error => this.message(String(error)));
        } catch (_) { /* REST reconciliation also runs after reconnect. */ }
      };
      socket.onclose = () => { if (this.socket === socket) clearInterval(this.heartbeat); if (this.socket === socket) this.wsTimer = setTimeout(() => this.connectEvents(), 5000); };
    }
    async enqueue(files) {
      if (this.running) { this.message('Ein Upload läuft bereits. Bitte danach weitere Dateien auswählen.'); return; }
      this.running = true;
      try {
        await ensureSW();
        const list = Array.from(files || []).filter(file => file && file.size <= (window.uploadConfig?.maxFileSize || MAX_FILE_SIZE) && _isAcceptedFile(file));
        if (!list.length) return;
        if (this.batchId && this.queue.some(item => !item.fileId)) {
          await this.refresh(); this.queue = matchReselected(this.queue, list);
          if (!this.queue.some(item => item.file && !item.fileId)) {
            this.message('Die Auswahl passt nicht zur offenen Queue. Bitte die ursprünglichen Dateien erneut auswählen.'); return;
          }
        } else {
          this.socket?.close(); this.batchId = null;
          this.queue = list.map(file => ({ key: crypto.randomUUID(), file, name: file.name, size: file.size, lastModified: file.lastModified || 0, state: 'queued' }));
          const clientBatchId = crypto.randomUUID();
          const batch = await json('/api/uploads/batches', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ client_batch_id: clientBatchId, total_files: list.length, total_bytes: list.reduce((sum, file) => sum + file.size, 0) }) });
          this.batchId = batch.batch_id; this.queue.forEach(item => { item.batchId = this.batchId; }); this.batchIds = [...new Set([...this.batchIds, this.batchId])];
          localStorage.setItem(storageKey, JSON.stringify({ batchId: this.batchId }));
          const pointerKey = `${storageKey}.batches`;
          const remember = () => { const current = JSON.parse(localStorage.getItem(pointerKey) || '[]'); if (!current.includes(this.batchId)) current.push(this.batchId); localStorage.setItem(pointerKey, JSON.stringify(current)); };
          if (navigator.locks?.request) await navigator.locks.request(`docuelevate-upload-pointers-${principal}`, remember); else remember();
        }
        if (this.queue.length && this.queue.every(item => item.fileId || item.state === 'duplicate') && !this.queue.some(item => item.state === 'failed')) {
          window.dispatchEvent?.(new CustomEvent('allUploadsComplete', { detail: { total: this.queue.length, completed: this.queue.length } }));
        }
        await this.persist(this.queue); this.connectEvents(); this.render();
        // Hash and send in bounded windows, so the first files can start while
        // the rest of a large selection has not yet been inspected.
        const pendingBatchIds = [...new Set(this.queue.filter(item => item.file && !item.fileId).map(item => item.batchId || this.batchId))];
        for (const pendingBatchId of pendingBatchIds) {
          this.batchId = pendingBatchId;
          for (const group of windows(this.queue.filter(item => item.file && !item.fileId && (item.batchId || this.batchId) === pendingBatchId))) {
          for (let i = 0; i < group.length; i += HASH_WORKERS) {
            await Promise.all(group.slice(i, i + HASH_WORKERS).map(async item => {
              try { const result = await digest(item); item.sha256 = result.sha256; item.mime = result.mime; }
              catch (error) { item.state = 'failed'; this.message(String(error)); }
            }));
          }
          deduplicate(this.queue);
          const check = group.filter(item => item.state === 'queued' && !item.duplicateOf);
          if (check.length) applyPreflightResults(check, await json('/api/uploads/preflight', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ batch_id: this.batchId, files: check.map(item => ({ client_id: item.key, sha256: item.sha256, size: item.size })) }) }));
          deduplicate(this.queue); await this.persist(group);
          this.capacity = await json(`/api/uploads/capacity?batch_id=${encodeURIComponent(this.batchId)}`);
          await this.run(group); this.render();
          }
        }
      } catch (error) { this.message(`Upload pausiert: ${error.message}. Die Queue bleibt gespeichert.`); }
      finally { this.running = false; }
    }
    async send(item) {
      if (!await postSW({ op: 'lease', key: item.key, owner, ttl: 60000 })) return false;
      const renewal = setInterval(() => postSW({ op: 'lease', key: item.key, owner, ttl: 60000 }).catch(() => {}), 10000);
      try {
        const body = new FormData(); body.append('file', item.file); body.append('batch_id', item.batchId || this.batchId);
        body.append('client_id', item.key); body.append('sha256', item.sha256);
        const result = await json('/api/uploads/files', { method: 'POST', body });
        item.fileId = result.file_id; item.state = result.duplicate ? 'duplicate' : result.state || 'accepted';
        await this.persist([item]);
        window.onDocuElevateUploadQueued?.({ fileId: item.fileId, filename: item.name, state: item.state });
        return true;
      } catch (error) { item.state = 'failed'; await this.persist([item]); this.message(String(error)); return false; }
      finally { clearInterval(renewal); await postSW({ op: 'release', key: item.key, owner }).catch(() => {}); }
    }
    async run(group) {
      while (group.some(item => item.state === 'queued' && !item.fileId && !item.duplicateOf)) {
        const selected = selectReady(group, this.capacity);
        if (!selected.length) {
          this.message('Server pausiert die Uploads – warte auf Kapazität…'); await sleep(2000);
          this.capacity = await json(`/api/uploads/capacity?batch_id=${encodeURIComponent(this.batchId)}`); continue;
        }
        const results = await Promise.all(selected.map(item => this.send(item)));
        deduplicate(this.queue); await this.persist(group); this.render();
        if (results.every(result => !result)) { await sleep(2000); await this.refresh(); }
        this.capacity = await json(`/api/uploads/capacity?batch_id=${encodeURIComponent(this.batchId)}`);
      }
    }
  }
  window.PersistentBulkUploadQueue = Queue;
  window.processFiles = async (files, container, status) => {
    let queue = window.docuElevateUploadQueue;
    if (!queue) { queue = new Queue(container, status); window.docuElevateUploadQueue = queue; await queue.restore(); }
    if (container) queue.container = container;
    if (status) queue.status = status;
    if (queue.ready) await queue.ready;
    return queue.enqueue(files);
  };
  window.addEventListener('DOMContentLoaded', () => {
    const queue = new Queue(document.getElementById('uploadProgress'), document.getElementById('statusMessage'));
    window.docuElevateUploadQueue = queue;
    queue.ready = queue.restore();
  });
  window.uploadQueueTestHelpers = { windows, slots, applyPreflightResults, matchReselected, deduplicate, selectReady };
})();
