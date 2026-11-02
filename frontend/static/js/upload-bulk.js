/* HTTP carries bytes; the websocket only advertises capacity and status.
 * IndexedDB stores metadata, never a second copy of the selected corpus. */
(function () {
  const useDedicatedController = typeof Worker !== 'undefined' && !window.uploadQueueTestMode;
  // The adapter is included by the base layout. Keep an accidental second tag
  // from starting a second controller (and a competing upload worker).
  if (useDedicatedController && window.__docuElevateUploadQueueStarted) return;
  if (useDedicatedController) window.__docuElevateUploadQueueStarted = true;
  function globalPopup() {
    const panel = document.getElementById('globalUploadQueue');
    if (!panel) return null;
    const reopen = document.getElementById('globalUploadQueueReopen');
    const diagnosticsPanel = document.getElementById('globalUploadQueueDiagnosticsPanel');
    const diagnosticsButton = document.getElementById('globalUploadQueueDiagnosticsButton');
    const addFilesButton = document.getElementById('globalUploadQueueAddFiles');
    const addFilesInput = document.getElementById('globalUploadQueueFileInput');
    let minimized = false;
    const show = () => { minimized = false; panel.classList.remove('hidden'); reopen?.classList.add('hidden'); };
    const hide = () => { minimized = true; panel.classList.add('hidden'); reopen?.classList.remove('hidden'); };
    document.getElementById('globalUploadQueueMinimize')?.addEventListener('click', hide);
    document.getElementById('globalUploadQueueClose')?.addEventListener('click', hide);
    reopen?.addEventListener('click', show);
    addFilesButton?.addEventListener('click', () => { show(); addFilesInput?.click(); });
    addFilesInput?.addEventListener('change', event => { const files = event.target?.files; if (files?.length) void window.processFiles?.(files); event.target.value = ''; });
    const states = { queued: 'wartet auf Upload', accepted: 'angenommen', duplicate: 'bereits vorhanden', processing: 'in Verarbeitung', complete: 'verarbeitet', completed: 'verarbeitet', needs_files: 'Originaldatei erneut auswählen', failed: 'fehlgeschlagen', transfer_failed: 'Übertragung fehlgeschlagen' };
    const errors = { transfer_rejected: 'vom Server abgelehnt', network_retrying: 'Verbindung wird erneut versucht', file_inspection_failed: 'Datei konnte nicht geprüft werden' };
    const renderDiagnostics = details => {
      const list = document.getElementById('globalUploadQueueDiagnostics');
      if (!list) return;
      const entries = [
        ['Service Worker', details.serviceWorker || 'wird geprüft'],
        ['Controller', details.controller || 'noch nicht aktiv'],
        ['Upload-Worker', details.worker || 'wird gestartet'],
        ['Letzte Phase', details.phase || 'noch nicht gestartet'],
        ['Pausiert weil', details.pausedReason || 'nein'],
        ['Serverkapazität', details.capacity || 'noch nicht bekannt'],
        ['WebSocket', details.websocket || 'noch nicht verbunden'],
        ['Dauerhafter Speicher', details.persisted || 'wird geprüft'],
        ['Speicherbelegung', details.storage || 'wird geprüft'],
        ['Queue', details.queue || '0 Dateien'],
      ];
      list.replaceChildren();
      for (const [label, value] of entries) { const term = document.createElement('dt'); term.className = 'font-medium'; term.textContent = label; const description = document.createElement('dd'); description.textContent = value; list.append(term, description); }
    };
    let diagnosticsHandler = null;
    diagnosticsButton?.addEventListener('click', () => { show(); diagnosticsPanel?.classList.remove('hidden'); diagnosticsButton.setAttribute('aria-expanded', 'true'); void diagnosticsHandler?.(); });
    return { panel, show, beginSelection() { show(); const summary = document.getElementById('globalUploadQueueSummary'); const notice = document.getElementById('globalUploadQueueNotice'); if (summary) summary.textContent = 'Dateien werden eingelesen'; if (notice) notice.textContent = 'Die Auswahl wird vorbereitet.'; }, renderDiagnostics, setDiagnosticsHandler(handler) { diagnosticsHandler = handler; }, render(payload, options = {}) {
      const summary = document.getElementById('globalUploadQueueSummary');
      const notice = document.getElementById('globalUploadQueueNotice');
      const progress = document.getElementById('globalUploadQueueProgress');
      const rows = document.getElementById('globalUploadQueueRows');
      const queue = payload.queue || []; const total = Number(payload.total ?? queue.length);
      const accepted = Number(payload.accepted ?? queue.filter(item => item.fileId != null).length);
      const failed = Number(payload.failed ?? queue.filter(item => String(item.state || '').includes('failed')).length);
      const complete = Number(payload.complete ?? queue.filter(item => ['complete', 'completed'].includes(item.state)).length);
      const needsFiles = Number(payload.needsFiles ?? queue.filter(item => item.state === 'needs_files').length);
      const processing = Number(payload.processing ?? queue.filter(item => item.state === 'processing').length);
      if (summary) summary.textContent = `${total} insgesamt · ${accepted} angenommen · ${complete} verarbeitet · ${failed} fehlgeschlagen · ${needsFiles} erneut auswählen · ${processing} in Verarbeitung`;
      if (notice) notice.textContent = payload.message || '';
      if (progress) progress.style.width = `${total ? Math.min(100, (complete / total) * 100) : 0}%`;
      if (rows) { rows.replaceChildren(); const rank = item => (String(item.state).includes('failed') ? 0 : ['queued','needs_files','processing'].includes(item.state) ? 1 : 2); for (const item of [...queue].sort((a,b) => rank(a)-rank(b)).slice(0, 100)) { const row = document.createElement('div'); row.className = 'rounded border px-2 py-1'; const reason = item.errorCode ? `: ${errors[item.errorCode] || 'Übertragungsfehler'}` : ''; row.textContent = `${item.name || 'Datei'} — ${states[item.state] || 'unbekannter Status'}${reason}`; rows.appendChild(row); } }
      if (payload.diagnostics) renderDiagnostics(payload.diagnostics);
      if (options.open && (!minimized || options.force)) show();
    }};
  }
  const popup = globalPopup();
  if (useDedicatedController) {
    const worker = new Worker('/static/js/upload-controller-worker.js');
    let registration;
    let latestStatus = { total: 0, accepted: 0, complete: 0, failed: 0, needsFiles: 0, processing: 0 };
    const diagnostic = { serviceWorker: 'wird gestartet', controller: 'noch nicht aktiv', worker: 'wird gestartet', phase: 'Initialisierung', pausedReason: '', capacity: 'noch nicht bekannt', websocket: 'noch nicht verbunden', persisted: 'wird geprüft', storage: 'wird geprüft', queue: '0 Dateien' };
    const owner = crypto.randomUUID();
    const csrf = () => typeof getCsrfToken === 'function' ? getCsrfToken() : '';
    function postSW(message) {
      return new Promise((resolve, reject) => {
        const controller = navigator.serviceWorker?.controller || registration?.active;
        if (!controller) return reject(new Error('Persistent upload queue is unavailable'));
        const channel = new MessageChannel();
        const timer = setTimeout(() => { channel.port1.close(); reject(new Error('Queue acknowledgement timed out')); }, 10000);
        channel.port1.onmessage = event => { clearTimeout(timer); channel.port1.close(); event.data?.ok ? resolve(event.data.result) : reject(new Error(event.data?.error || 'Queue error')); };
        controller.postMessage({ ...message, principal: window.uploadConfig?.queueOwner || 'single-user' }, [channel.port2]);
      });
    }
    function diagnosticsFrom(payload = {}) {
      const report = payload.diagnostics || {};
      diagnostic.worker = report.worker || diagnostic.worker;
      diagnostic.phase = report.phase || diagnostic.phase;
      diagnostic.pausedReason = report.pausedReason || '';
      diagnostic.capacity = report.capacity ? `${report.capacity.slots ?? '?'} Plätze, ${formatBytes(report.capacity.maxBytes)} (${report.capacity.source || 'Server'}, ${report.capacity.at || 'Zeit unbekannt'})` : diagnostic.capacity;
      diagnostic.websocket = report.websocket ? `${report.websocket.state || 'unbekannt'} (${report.websocket.at || 'Zeit unbekannt'})` : diagnostic.websocket;
      diagnostic.queue = `${payload.total ?? latestStatus.total} Dateien · ${payload.accepted ?? latestStatus.accepted} angenommen · ${payload.complete ?? latestStatus.complete} verarbeitet · ${payload.failed ?? latestStatus.failed} fehlgeschlagen`;
      return diagnostic;
    }
    function formatBytes(value) { return Number.isFinite(Number(value)) ? `${(Number(value) / 1024 / 1024).toFixed(1)} MB` : 'unbegrenzt'; }
    async function refreshDiagnostics() {
      diagnostic.serviceWorker = registration ? `registriert (${registration.active?.state || registration.installing?.state || 'wartet'})` : 'nicht registriert';
      diagnostic.controller = navigator.serviceWorker?.controller ? 'aktiv' : 'noch nicht aktiv (nach Neuladen verfügbar)';
      try { diagnostic.persisted = navigator.storage?.persisted ? (await navigator.storage.persisted() ? 'angefordert und bestätigt' : 'nicht bestätigt') : 'Browser unterstützt keine Abfrage'; } catch (_) { diagnostic.persisted = 'konnte nicht abgefragt werden'; }
      try { const estimate = await navigator.storage?.estimate?.(); diagnostic.storage = estimate ? `${formatBytes(estimate.usage)} von ${formatBytes(estimate.quota)}` : 'Browser unterstützt keine Abfrage'; } catch (_) { diagnostic.storage = 'konnte nicht abgefragt werden'; }
      popup?.renderDiagnostics(diagnostic);
    }
    popup?.setDiagnosticsHandler(refreshDiagnostics);
    function render(payload) {
      latestStatus = { ...latestStatus, ...payload };
      const pending = Number(payload.total || 0) > Number(payload.complete || 0);
      const newDrop = /hinzugefügt/.test(payload.message || '');
      const opensForWork = pending && (/wiederhergestellt/.test(payload.message || '') || newDrop);
      diagnosticsFrom(payload);
      popup?.render({ ...payload, diagnostics: diagnostic }, { open: opensForWork, force: newDrop });
      const container = document.getElementById('uploadProgress');
      const status = document.getElementById('statusMessage');
      if (status) status.textContent = payload.message || '';
      if (!container || !payload.queue) return;
      container.replaceChildren();
      const states = { queued: 'wartet', accepted: 'angenommen', duplicate: 'bereits vorhanden', processing: 'in Verarbeitung', complete: 'verarbeitet', completed: 'verarbeitet', needs_files: 'Originaldatei erneut auswählen', failed: 'fehlgeschlagen', transfer_failed: 'Übertragung fehlgeschlagen' };
      for (const item of payload.queue.slice(0, 100)) { const row = document.createElement('div'); row.className = 'text-xs mb-1'; row.textContent = `${item.name} — ${states[item.state] || 'unbekannter Status'}`; container.appendChild(row); }
      const accepted = payload.accepted ?? payload.queue.filter(item => item.fileId).length;
      if (status) status.textContent = `${accepted} von ${payload.total ?? payload.queue.length} Dateien sicher angenommen. ${payload.message || ''}`;
    }
    worker.onmessage = event => {
      const message = event.data || {};
      if (message.type === 'sw') postSW({ op: message.op, ...(message.batchId ? { batchId: message.batchId } : {}), ...(message.items ? { items: message.items } : {}), ...(message.key ? { key: message.key } : {}), ...(message.owner ? { owner: message.owner } : {}), ...(message.ttl ? { ttl: message.ttl } : {}) }).then(result => worker.postMessage({ type: 'swResponse', id: message.id, ok: true, result })).catch(error => worker.postMessage({ type: 'swResponse', id: message.id, ok: false, error: String(error) }));
      if (message.type === 'status') render(message);
      if (message.type === 'ready') { diagnostic.worker = 'bereit'; diagnosticsFrom(message); }
      if (message.type === 'accepted') window.onDocuElevateUploadQueued?.(message);
    };
    async function start() {
      if (!navigator.serviceWorker) throw new Error('This browser needs Service Worker support for resumable uploads');
      registration = await navigator.serviceWorker.register('/upload-queue-sw.js', { scope: '/' }); await navigator.serviceWorker.ready;
      if (navigator.storage?.persist) await navigator.storage.persist().catch(() => false);
      await refreshDiagnostics();
      worker.postMessage({ type: 'init', principal: window.uploadConfig?.queueOwner || 'single-user', owner, csrf: csrf(), config: window.uploadConfig || {} });
    }
    let startPromise;
    function ensureStarted() {
      if (!startPromise) startPromise = start().catch(error => { diagnostic.phase = 'nicht verfügbar'; diagnostic.pausedReason = 'Service Worker konnte nicht gestartet werden'; render({ message: String(error), queue: [] }); throw error; });
      return startPromise;
    }
    window.beginUploadSelection = () => popup?.beginSelection();
    window.processFiles = async files => {
      const added = Array.from(files || []);
      if (!added.length) return;
      const total = Number(latestStatus.total || 0) + added.length;
      popup?.render({ ...latestStatus, total, message: `${added.length} Datei${added.length === 1 ? '' : 'en'} zur Upload-Queue hinzugefügt.`, diagnostics: diagnostic }, { open: true });
      await ensureStarted(); worker.postMessage({ type: 'add', files: added });
    };
    window.addEventListener('DOMContentLoaded', () => { void ensureStarted().catch(() => {}); });
    return;
  }
  const WINDOW = 200, HASH_WORKERS = 2, MAX_RETRIES = 5;
  const principal = window.uploadConfig?.queueOwner || 'single-user';
  const owner = crypto.randomUUID(); // Each tab has its own lease identity.
  const storageKey = `docuelevate.upload.batch.${principal}`;
  let registration;
  let preflightWorker;
  const preflightJobs = new Map();
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
      const candidates = seen.get(item.sha256);
      if (candidates) candidates.push(item); else seen.set(item.sha256, [item]);
    }
    for (const candidates of seen.values()) {
      // Prefer an admitted item, then a currently transferable item. A
      // needs_files entry must never suppress a reselected copy.
      const leader = candidates.find(candidate => candidate.fileId) || candidates.find(candidate => candidate.file);
      if (!leader) continue;
      for (const candidate of candidates) {
        if (candidate.key === leader.key) continue;
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
      if (!preflightWorker) {
        preflightWorker = new Worker('/static/js/upload-preflight-worker.js');
        preflightWorker.onmessage = event => {
          const job = preflightJobs.get(event.data?.id);
          if (!job) return;
          preflightJobs.delete(event.data.id);
          event.data.error ? job.reject(new Error(event.data.error)) : job.resolve(event.data);
        };
        preflightWorker.onerror = error => {
          const failure = new Error(error?.message || 'File inspection failed');
          for (const job of preflightJobs.values()) job.reject(failure);
          preflightJobs.clear(); preflightWorker.terminate(); preflightWorker = null;
        };
      }
      preflightJobs.set(item.key, { resolve, reject });
      preflightWorker.postMessage({ id: item.key, file: item.file, name: item.file.name, mime: item.file.type });
    });
  }
  function shutdownPreflightWorker() {
    if (!preflightWorker) return;
    preflightWorker.terminate(); preflightWorker = null;
    const failure = new Error('Upload page closed');
    for (const job of preflightJobs.values()) job.reject(failure);
    preflightJobs.clear();
  }
  window.addEventListener('pagehide', shutdownPreflightWorker);
  function metadata(item, batchId) {
    return { key: item.key, batchId: item.batchId || batchId, name: item.name, size: item.size, lastModified: item.lastModified,
      state: item.state, sha256: item.sha256, mime: item.mime, fileId: item.fileId, duplicateOf: item.duplicateOf };
  }
  class Queue {
    constructor(container, status) {
      this.container = container; this.status = status; this.queue = []; this.batchId = null; this.batchIds = [];
      this.capacity = { slots: 0, max_bytes: 0 }; this.running = false;
      this.pendingAdds = [];
      this.refreshPromise = null;
    }
    message(text) { if (this.status) this.status.textContent = text; }
    render() {
      popup?.render({ queue: this.queue, total: this.queue.length, accepted: this.queue.filter(item => item.fileId != null).length }, { open: false });
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
    async enqueue(files, options = {}) {
      const list = Array.from(files || []).filter(file => file && file.size <= (window.uploadConfig?.maxFileSize || MAX_FILE_SIZE) && _isAcceptedFile(file));
      if (!list.length) return;
      if (this.running) {
        // Keep the drop zone live. The active scheduler finishes its current
        // batch, then starts this addition as a separate server batch.
        this.pendingAdds.push(list);
        this.message(`${this.pendingAdds.reduce((count, batch) => count + batch.length, 0)} weitere Dateien vorgemerkt.`);
        return;
      }
      this.running = true;
      try {
        await ensureSW();
        if (!options.append && this.batchId && this.queue.some(item => !item.fileId)) {
          await this.refresh(); this.queue = matchReselected(this.queue, list);
          if (!this.queue.some(item => item.file && !item.fileId)) {
            this.message('Die Auswahl passt nicht zur offenen Queue. Bitte die ursprünglichen Dateien erneut auswählen.'); return;
          }
        } else {
          this.socket?.close(); this.batchId = null;
          const additions = list.map(file => ({ key: crypto.randomUUID(), file, name: file.name, size: file.size, lastModified: file.lastModified || 0, state: 'queued' }));
          this.queue = [...this.queue, ...additions];
          const clientBatchId = crypto.randomUUID();
          const batch = await json('/api/uploads/batches', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ client_batch_id: clientBatchId, total_files: list.length, total_bytes: list.reduce((sum, file) => sum + file.size, 0) }) });
          this.batchId = batch.batch_id; additions.forEach(item => { item.batchId = this.batchId; }); this.batchIds = [...new Set([...this.batchIds, this.batchId])];
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
      finally {
        this.running = false;
        const next = this.pendingAdds.shift();
        if (next?.length) void this.enqueue(next, { append: true });
      }
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
    popup?.show();
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
  window.uploadQueueTestHelpers = { windows, slots, applyPreflightResults, matchReselected, deduplicate, selectReady, digest };
})();
