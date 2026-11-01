// frontend/static/js/upload.js
// Reusable drag-and-drop upload functionality for DocuElevate

// ── Configuration ─────────────────────────────────────────────────────────────
const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500 MB

/** Fallback upload throttling values when window.uploadConfig is not set. */
const DEFAULT_UPLOAD_CONCURRENCY = 3;
const DEFAULT_UPLOAD_QUEUE_DELAY_MS = 500;

/** Maximum number of 429 retries before a file is permanently marked failed. */
const MAX_RATE_LIMIT_RETRIES = 5;

const DEFAULT_UPLOAD_I18N = {
  queuedBatch: 'Queued {count} file(s) for upload…',
  allComplete: 'All uploads completed ({done}/{total})',
  uploadingBatch: 'Uploading files ({done}/{total})',
  statusQueued: 'Queued',
  unsupportedType: 'Unsupported file type',
  tooLarge: 'Exceeds 500 MB limit',
  retryExhausted: 'Failed: rate limit retries exhausted',
  uploading: 'Uploading…',
  uploadingPercent: 'Uploading: {percent}%',
  duplicate: 'Duplicate – already processed (file #{fileId})',
  successTask: 'Success: Task ID: {taskId}',
  retryRateLimit: 'Rate limited – queued to retry…',
  errorHttp: 'Error: HTTP {status}',
  errorNetwork: 'Error: Network error',
  urlSuccess: 'Success! File "{filename}" ({size}) downloaded and queued for processing.',
  urlError: 'Error: {detail}',
  urlNetworkError: 'Network error: {detail}',
};

function uploadMessage(key, values = {}) {
  const configured = window.uploadI18n || {};
  let message = configured[key] || DEFAULT_UPLOAD_I18N[key] || key;
  Object.entries(values).forEach(([name, value]) => {
    message = message.replaceAll(`{${name}}`, String(value));
  });
  return message;
}

// ── Accepted MIME types (mirrors app/utils/allowed_types.py) ─────────────────
// All types processable by Gotenberg (LibreOffice, Chromium, or Markdown routes).
const ACCEPTED_TYPES = {
  // PDF
  'application/pdf': true,
  // Word
  'application/msword': true,
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': true,
  'application/vnd.openxmlformats-officedocument.wordprocessingml.template': true,
  'application/vnd.ms-word.document.macroEnabled.12': true,
  'application/vnd.ms-word.template.macroEnabled.12': true,
  // Excel
  'application/vnd.ms-excel': true,
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': true,
  'application/vnd.openxmlformats-officedocument.spreadsheetml.template': true,
  'application/vnd.ms-excel.sheet.macroEnabled.12': true,
  'application/vnd.ms-excel.sheet.binary.macroEnabled.12': true,
  // PowerPoint
  'application/vnd.ms-powerpoint': true,
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': true,
  'application/vnd.openxmlformats-officedocument.presentationml.template': true,
  'application/vnd.openxmlformats-officedocument.presentationml.slideshow': true,
  'application/vnd.ms-powerpoint.presentation.macroEnabled.12': true,
  // OpenDocument (LibreOffice native)
  'application/vnd.oasis.opendocument.text': true,
  'application/vnd.oasis.opendocument.spreadsheet': true,
  'application/vnd.oasis.opendocument.presentation': true,
  'application/vnd.oasis.opendocument.graphics': true,
  'application/vnd.oasis.opendocument.formula': true,
  // Images
  'image/jpeg': true, 'image/jpg': true, 'image/png': true,
  'image/gif': true, 'image/bmp': true, 'image/tiff': true,
  'image/webp': true, 'image/svg+xml': true,
  // Text / data
  'text/plain': true,
  'text/csv': true,
  'application/rtf': true,
  'text/rtf': true,
  // HTML (Gotenberg Chromium route)
  'text/html': true,
  // Markdown (Gotenberg Chromium/Markdown route)
  'text/markdown': true,
  'text/x-markdown': true,
};

// File extensions always accepted even when the browser reports no / wrong MIME type.
const ACCEPTED_EXTENSIONS = new Set([
  // PDF
  '.pdf',
  // Word
  '.doc', '.docx', '.docm', '.dot', '.dotx', '.dotm',
  // Excel
  '.xls', '.xlsx', '.xlsm', '.xlsb', '.xlt', '.xltx', '.xlw',
  // PowerPoint
  '.ppt', '.pptx', '.pptm', '.pps', '.ppsx', '.pot', '.potx',
  // OpenDocument
  '.odt', '.ods', '.odp', '.odg', '.odf',
  // Text / data
  '.rtf', '.txt', '.csv',
  // Images
  '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.svg',
  // Web
  '.html', '.htm',
  // Markdown
  '.md', '.markdown',
]);

// ── Adaptive throttle state ───────────────────────────────────────────────────
// Module-level so the backoff state persists across multiple drop/select events
// on the same page (rate limits are per-user on the server).
const _adaptiveState = {
  /** Current effective inter-slot delay (ms). null = use window.uploadConfig value. */
  delayMs: null,
  /** Current effective concurrency. null = use window.uploadConfig value. */
  concurrency: null,
  /** Consecutive successful uploads without a 429. Resets on each 429 or recovery step. */
  consecutiveOk: 0,
  /** Date.now() timestamp after which the queue may resume (set on 429 backoff). */
  pauseUntil: 0,
};

function _cfgDelay() {
  return (window.uploadConfig && window.uploadConfig.queueDelayMs != null)
    ? window.uploadConfig.queueDelayMs
    : DEFAULT_UPLOAD_QUEUE_DELAY_MS;
}

function _cfgConcurrency() {
  return (window.uploadConfig && window.uploadConfig.concurrency != null)
    ? window.uploadConfig.concurrency
    : DEFAULT_UPLOAD_CONCURRENCY;
}

/** Effective delay between upload slot starts (increased during backoff). */
function _effectiveDelay() {
  return _adaptiveState.delayMs !== null ? _adaptiveState.delayMs : _cfgDelay();
}

/** Fallback backoff multiplier when no Retry-After header is present. */
const FALLBACK_BACKOFF_MULTIPLIER = 4;
/** Minimum fallback pause duration (ms) when no Retry-After header is present. */
const MIN_FALLBACK_BACKOFF_MS = 5000;
/** Maximum inter-slot delay after repeated exponential backoff (ms). */
const MAX_BACKOFF_DELAY_MS = 30000;

/** Effective concurrency (reduced to 1 during backoff). */
function _effectiveConcurrency() {
  return _adaptiveState.concurrency !== null ? _adaptiveState.concurrency : _cfgConcurrency();
}

/**
 * Called when an HTTP 429 Too Many Requests response is received.
 * Pauses the queue and applies exponential backoff.
 * @param {number} retryAfterSeconds - Value of the Retry-After header (0 = absent).
 */
function _onRateLimited(retryAfterSeconds) {
  // Determine how long to pause – prefer the server's Retry-After; fall back to
  // FALLBACK_BACKOFF_MULTIPLIER × the current delay (minimum MIN_FALLBACK_BACKOFF_MS).
  const waitMs = retryAfterSeconds > 0
    ? retryAfterSeconds * 1000
    : Math.max(_effectiveDelay() * FALLBACK_BACKOFF_MULTIPLIER, MIN_FALLBACK_BACKOFF_MS);

  _adaptiveState.pauseUntil = Date.now() + waitMs;
  // Exponential backoff on the inter-slot delay, capped at MAX_BACKOFF_DELAY_MS.
  _adaptiveState.delayMs = Math.min(_effectiveDelay() * 2, MAX_BACKOFF_DELAY_MS);
  // Serialize uploads while we recover.
  _adaptiveState.concurrency = 1;
  _adaptiveState.consecutiveOk = 0;

  console.warn(
    `[DocuElevate] Rate limited. Pausing ${waitMs} ms. ` +
    `New delay: ${_adaptiveState.delayMs} ms, concurrency: 1.`
  );
}

/**
 * Called after each successful (non-429) upload.
 * After 5 consecutive successes, gently recovers toward the configured values.
 */
function _onUploadSuccess() {
  _adaptiveState.consecutiveOk++;
  if (_adaptiveState.consecutiveOk < 5) return;

  // One recovery step every 5 successes.
  _adaptiveState.consecutiveOk = 0;
  const cfgDelay = _cfgDelay();
  const cfgConc = _cfgConcurrency();

  if (_adaptiveState.delayMs !== null && _adaptiveState.delayMs > cfgDelay) {
    _adaptiveState.delayMs = Math.max(Math.round(_adaptiveState.delayMs * 0.75), cfgDelay);
    if (_adaptiveState.delayMs <= cfgDelay) _adaptiveState.delayMs = null; // fully recovered
  }
  if (_adaptiveState.concurrency !== null && _adaptiveState.concurrency < cfgConc) {
    _adaptiveState.concurrency = Math.min(_adaptiveState.concurrency + 1, cfgConc);
    if (_adaptiveState.concurrency >= cfgConc) _adaptiveState.concurrency = null; // fully recovered
  }
}

// ── Directory traversal helpers ───────────────────────────────────────────────

/**
 * Read all entries from a DirectoryReader, handling the browser's 100-entry
 * per-batch limit by calling readEntries() repeatedly.
 * @param {FileSystemDirectoryReader} reader
 * @returns {Promise<FileSystemEntry[]>}
 */
function readAllDirectoryEntries(reader) {
  return new Promise((resolve, reject) => {
    const entries = [];
    function readBatch() {
      reader.readEntries((batch) => {
        if (batch.length === 0) { resolve(entries); return; }
        entries.push(...batch);
        readBatch();
      }, reject);
    }
    readBatch();
  });
}

/**
 * Recursively collect all File objects from a FileSystemEntry tree.
 * @param {FileSystemEntry} entry
 * @param {File[]} files - accumulator
 * @returns {Promise<void>}
 */
async function traverseFileEntry(entry, files) {
  if (entry.isFile) {
    await new Promise((resolve) => {
      entry.file((file) => { files.push(file); resolve(); }, resolve);
    });
  } else if (entry.isDirectory) {
    const subEntries = await readAllDirectoryEntries(entry.createReader());
    for (const sub of subEntries) {
      await traverseFileEntry(sub, files);
    }
  }
}

/**
 * Extract all File objects from a DataTransfer, recursively expanding any
 * dropped directories.  Falls back gracefully to dataTransfer.files when the
 * FileSystem Entry API is unavailable (Safari < 11.1, some mobile browsers).
 *
 * IMPORTANT: DataTransferItemList is only accessible synchronously during the
 * drop event handler.  All entries and fallback File objects must be collected
 * in a single synchronous pass before any `await`, otherwise the browser clears
 * the list after the first yield — causing only the first file to be captured
 * when multiple files are dropped.
 *
 * @param {DataTransfer} dataTransfer
 * @returns {Promise<File[]>}
 */
async function getFilesFromDataTransfer(dataTransfer) {
  if (dataTransfer.items && dataTransfer.items.length > 0) {
    // ── Synchronous pass ───────────────────────────────────────────────────
    // Collect all FileSystemEntry objects and any plain File fallbacks NOW,
    // before the first `await`, while the DataTransferItemList is still valid.
    const entries = [];
    const fallbackFiles = [];
    for (let i = 0; i < dataTransfer.items.length; i++) {
      const item = dataTransfer.items[i];
      const entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
      if (entry) {
        entries.push(entry);
      } else if (item.kind === 'file') {
        const file = item.getAsFile();
        if (file) fallbackFiles.push(file);
      }
    }
    // ── Asynchronous traversal ─────────────────────────────────────────────
    // DataTransferItemList is no longer needed here; we work only with the
    // already-captured FileSystemEntry objects and File objects.
    const files = [...fallbackFiles];
    for (const entry of entries) {
      await traverseFileEntry(entry, files);
    }
    return files;
  }
  return Array.from(dataTransfer.files || []);
}

// ── Core queue runner ─────────────────────────────────────────────────────────

/**
 * Validate and queue files for upload with adaptive throttling.
 *
 * Files are pre-rendered as progress rows so the user immediately sees the
 * full list.  The queue runner respects the current effective concurrency and
 * delay, slowing down automatically when the server signals rate limiting (429).
 *
 * @param {File[]|FileList} files
 * @param {HTMLElement} progressContainer
 * @param {HTMLElement} statusMessage
 */
function legacyProcessFiles(files, progressContainer, statusMessage) {
  const fileArray = Array.from(files);
  if (!fileArray.length) return;

  if (statusMessage) {
    statusMessage.textContent = uploadMessage('queuedBatch', { count: fileArray.length });
  }

  // Per-batch counters tracked in closure variables (avoids fragile DOM queries).
  const total = fileArray.length;
  let done = 0;

  function updateStatus() {
    if (!statusMessage) return;
    if (done === total) {
      statusMessage.textContent = uploadMessage('allComplete', { done, total });
      window.dispatchEvent(new CustomEvent('allUploadsComplete', { detail: { total, completed: done } }));
    } else {
      statusMessage.textContent = uploadMessage('uploadingBatch', { done, total });
    }
  }

  function markDone() {
    done++;
    updateStatus();
  }

  // Pre-create one progress row per file.
  const queueItems = fileArray.map((file) => {
    const row = document.createElement('div');
    row.className = 'flex flex-col mb-2';
    const safeFileName = window.escapeHtml(file.name);
    row.innerHTML = `
      <div class="flex justify-between">
        <span class="text-sm truncate" title="${safeFileName}">${safeFileName}</span>
        <span class="text-xs text-gray-500">${formatFileSize(file.size)}</span>
      </div>
      <div class="w-full bg-gray-200 h-2 rounded-full mt-1">
        <div class="file-progress-bar bg-gray-300 h-2 rounded-full" style="width:0%"></div>
      </div>
      <div class="file-status text-xs text-gray-400 mt-1">${window.escapeHtml(uploadMessage('statusQueued'))}</div>
    `;
    if (progressContainer) progressContainer.appendChild(row);
    return {
      file,
      progressBar: row.querySelector('.file-progress-bar'),
      statusEl: row.querySelector('.file-status'),
      retryCount: 0,
    };
  });

  // Mutable queue – rate-limited items are pushed back to the front.
  const queue = [...queueItems];
  let active = 0;

  function scheduleNext() {
    // Respect global backoff pause.
    const pauseRemaining = _adaptiveState.pauseUntil - Date.now();
    if (pauseRemaining > 0) {
      setTimeout(scheduleNext, pauseRemaining + 50);
      return;
    }

    while (active < _effectiveConcurrency() && queue.length > 0) {
      const item = queue.shift();
      active++;

      // Validate before hitting the network.
      if (!_isAcceptedFile(item.file)) {
        item.progressBar.className = 'file-progress-bar bg-red-500 h-2 rounded-full';
        item.statusEl.textContent = uploadMessage('unsupportedType');
        item.statusEl.className = 'text-xs text-red-500 mt-1';
        active--;
        markDone();
        // No HTTP request – skip straight to next without adding delay.
        scheduleNext();
        continue;
      }

      if (item.file.size > MAX_FILE_SIZE) {
        item.progressBar.className = 'file-progress-bar bg-red-500 h-2 rounded-full';
        item.statusEl.textContent = uploadMessage('tooLarge');
        item.statusEl.className = 'text-xs text-red-500 mt-1';
        active--;
        markDone();
        scheduleNext();
        continue;
      }

      _uploadSingleFile(item.file, item.progressBar, item.statusEl, markDone)
        .then((result) => {
          active--;
          if (result.rateLimited) {
            _onRateLimited(result.retryAfterSeconds);
            item.retryCount++;
            if (item.retryCount < MAX_RATE_LIMIT_RETRIES) {
              // Re-insert at the front of the queue to retry after the pause.
              queue.unshift(item);
            } else {
              item.progressBar.className = 'file-progress-bar bg-red-500 h-2 rounded-full';
              item.statusEl.textContent = uploadMessage('retryExhausted');
              item.statusEl.className = 'text-xs text-red-500 mt-1';
              markDone();
            }
            // Resume after the backoff window.
            const wait = Math.max(_adaptiveState.pauseUntil - Date.now() + 50, 0);
            setTimeout(scheduleNext, wait);
          } else {
            // Success or permanent error – wait the configured delay before next slot.
            setTimeout(scheduleNext, _effectiveDelay());
          }
        });
    }
  }

  scheduleNext();
}

/**
 * Check whether a file passes MIME type and extension validation.
 * @param {File} file
 * @returns {boolean}
 */
function _isAcceptedFile(file) {
  if (ACCEPTED_TYPES[file.type]) return true;
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  return ACCEPTED_EXTENSIONS.has(ext);
}

/**
 * Upload a single file via XHR, returning a structured result.
 * Detects HTTP 429 responses and reads the Retry-After / X-RateLimit-Reset
 * headers so the caller can apply precise backoff.
 *
 * @param {File} file
 * @param {HTMLElement} progressBar
 * @param {HTMLElement} statusEl
 * @param {Function} onTerminal - Called when the file reaches a terminal state (success or permanent error).
 * @returns {Promise<{rateLimited: boolean, retryAfterSeconds: number}>}
 */
function _uploadSingleFile(file, progressBar, statusEl, onTerminal) {
  statusEl.textContent = uploadMessage('uploading');
  statusEl.className = 'text-xs text-gray-600 mt-1';
  progressBar.style.width = '0%';
  progressBar.className = 'file-progress-bar bg-blue-500 h-2 rounded-full';

  return new Promise((resolve) => {
    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/ui-upload', true);

    const csrfToken = typeof getCsrfToken === 'function' ? getCsrfToken() : '';
    if (csrfToken) xhr.setRequestHeader('X-CSRF-Token', csrfToken);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        progressBar.style.width = pct + '%';
        statusEl.textContent = uploadMessage('uploadingPercent', { percent: pct });
      }
    };

    xhr.onload = () => {
      if (xhr.status === 200) {
        const result = JSON.parse(xhr.responseText);
        progressBar.style.width = '100%';

        if (result.status === 'duplicate' && result.duplicate_of) {
          // Exact duplicate – no processing task was created
          progressBar.className = 'file-progress-bar bg-yellow-400 h-2 rounded-full';
          statusEl.textContent = uploadMessage('duplicate', { fileId: result.duplicate_of.original_file_id });
          statusEl.className = 'text-xs text-yellow-600 mt-1';
          if (typeof window.onDocuElevateUploadQueued === 'function') {
            window.onDocuElevateUploadQueued({
              duplicateFileId: result.duplicate_of.original_file_id,
              filename: file.name
            });
          }
        } else {
          const taskId = result.task_id || (Array.isArray(result.task_ids) ? result.task_ids[0] : null);
          progressBar.className = 'file-progress-bar bg-green-500 h-2 rounded-full';
          statusEl.textContent = uploadMessage('successTask', { taskId: taskId || '' });
          statusEl.className = 'text-xs text-green-600 mt-1';
          if (typeof window.onDocuElevateUploadQueued === 'function') {
            window.onDocuElevateUploadQueued({
              operationId: result.operation_id,
              taskId,
              taskIds: result.task_ids || (taskId ? [taskId] : []),
              filename: file.name
            });
          }
        }
        _onUploadSuccess();
        onTerminal();
        resolve({ rateLimited: false, retryAfterSeconds: 0 });

      } else if (xhr.status === 429) {
        // Parse Retry-After (seconds integer).
        let retryAfter = parseInt(xhr.getResponseHeader('Retry-After') || '0', 10);
        if (!retryAfter) {
          // Fall back to X-RateLimit-Reset (Unix timestamp).
          const reset = parseInt(xhr.getResponseHeader('X-RateLimit-Reset') || '0', 10);
          if (reset) retryAfter = Math.max(reset - Math.floor(Date.now() / 1000), 1);
        }
        progressBar.className = 'file-progress-bar bg-yellow-400 h-2 rounded-full';
        statusEl.textContent = uploadMessage('retryRateLimit');
        statusEl.className = 'text-xs text-yellow-600 mt-1';
        resolve({ rateLimited: true, retryAfterSeconds: retryAfter });

      } else {
        progressBar.className = 'file-progress-bar bg-red-500 h-2 rounded-full';
        statusEl.textContent = uploadMessage('errorHttp', { status: xhr.status });
        statusEl.className = 'text-xs text-red-500 mt-1';
        onTerminal();
        resolve({ rateLimited: false, retryAfterSeconds: 0 });
      }
    };

    xhr.onerror = () => {
      progressBar.className = 'file-progress-bar bg-red-500 h-2 rounded-full';
      statusEl.textContent = uploadMessage('errorNetwork');
      statusEl.className = 'text-xs text-red-500 mt-1';
      onTerminal();
      resolve({ rateLimited: false, retryAfterSeconds: 0 });
    };

    xhr.send(formData);
  });
}

// ── Legacy single-file entry point (kept for backward compat) ─────────────────

/**
 * Validate and upload a single file (legacy path – wraps the queue runner).
 * @param {File} file
 * @param {HTMLElement} progressContainer
 * @param {HTMLElement} statusMessage
 */
function validateAndUpload(file, progressContainer, statusMessage) {
  processFiles([file], progressContainer, statusMessage);
}

/**
 * Format a byte count for human-readable display.
 * @param {number} bytes
 * @returns {string}
 */
function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// ── Drag-and-drop initialiser ─────────────────────────────────────────────────

/**
 * Wire up drag-and-drop on an element with full directory-traversal support.
 * @param {HTMLElement} element
 * @param {HTMLElement} progressContainer
 * @param {HTMLElement} statusMessage
 * @param {Object} [options]
 * @param {string} [options.dragOverClass] - CSS class added during drag-over
 */
function initDragAndDrop(element, progressContainer, statusMessage, options = {}) {
  if (!element) {
    console.error('[DocuElevate] Element not found for drag-and-drop initialization');
    return;
  }

  element.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
    if (options.dragOverClass) element.classList.add(options.dragOverClass);
  });

  element.addEventListener('dragleave', (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (options.dragOverClass) element.classList.remove(options.dragOverClass);
  });

  element.addEventListener('drop', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (options.dragOverClass) element.classList.remove(options.dragOverClass);

    const files = await getFilesFromDataTransfer(e.dataTransfer);
    if (files.length > 0) processFiles(files, progressContainer, statusMessage);
  });
}

/* ── Durable bulk queue ───────────────────────────────────────────────────────
// The queue is deliberately metadata-first. Browser quotas make copying a
// 40,000-file corpus into IndexedDB unsafe; FileSystem handles are retained when
// available and otherwise the UI reports which files need to be selected again.
class PersistentBulkUploadQueue {
  constructor(progressContainer, statusMessage) {
    this.progressContainer = progressContainer; this.statusMessage = statusMessage;
    this.items = []; this.batchId = null; this.worker = null; this.workerSeq = 0;
    this.socket = null; this.capacity = { slots: 2, maxBytes: Infinity }; this.running = false;
  }
  async enqueue(files) {
    const list = Array.from(files || []).filter((f) => f && f.size <= MAX_FILE_SIZE && _isAcceptedFile(f));
    if (!list.length) return;
    this.items = list.map((file, index) => ({ key: `${crypto.randomUUID ? crypto.randomUUID() : Date.now()+'-'+index}`, file, state: 'queued', sha256: null, mime: file.type || '', fileId: null }));
    this.render(); this.setStatus(uploadMessage('queuedBatch', { count: this.items.length }));
    await this.persistMetadata();
    try {
      const response = await fetch('/api/uploads/batches', { method: 'POST', headers: { 'Content-Type': 'application/json', ...this.csrf() }, body: JSON.stringify({ client_batch_id: this.batchId || this.items[0].key, total_files: this.items.length, total_bytes: this.items.reduce((n, i) => n + i.file.size, 0) }) });
      if (!response.ok) { if (response.status === 404 || response.status === 405) return legacyProcessFiles(files, this.progressContainer, this.statusMessage); throw new Error(`batch ${response.status}`); }
      const batch = await response.json(); this.batchId = batch.batch_id; await this.persistBatch(batch);
      await this.preflight(); this.connectEvents(); await this.pump();
    } catch (error) { console.warn('[DocuElevate] durable queue unavailable, using legacy upload:', error); legacyProcessFiles(files, this.progressContainer, this.statusMessage); }
  }
  csrf() { const token = typeof getCsrfToken === 'function' ? getCsrfToken() : ''; return token ? { 'X-CSRF-Token': token } : {}; }
  async persistBatch(batch) {
    try {
      if (!navigator.serviceWorker?.controller) return;
      navigator.serviceWorker.controller.postMessage({ type: 'enqueue', item: { key: `batch:${this.batchId}`, batchId: this.batchId, state: 'queued', totalFiles: batch.total_files || this.items.length } });
      // Persist only a bounded metadata record. The File object is intentionally
      // omitted; callers with a FileSystemFileHandle can add it to this record.
      this.items.forEach((item) => navigator.serviceWorker.controller.postMessage({ type: 'enqueue', item: { key: item.key, batchId: this.batchId, clientId: item.key, name: item.file.name, size: item.file.size, state: item.state, handle: item.handle || null } }));
    } catch (_) { /* best effort */ }
  }
  async persistMetadata() {
    // Keep at most a small manifest in local storage. Files remain in the page
    // and are never serialized; this is the important 40k-file memory guard.
    try { localStorage.setItem('docuelevate.upload.batch', JSON.stringify({ batchId: this.items[0]?.key, count: this.items.length, updatedAt: Date.now() })); } catch (_) { /* private mode/quota */ }
  }
  async preflight() {
    this.worker = new Worker('/static/js/upload-preflight-worker.js');
    const candidates = this.items.slice(0, 200); // bounded request; remaining files follow in windows
    const digests = await Promise.all(candidates.map((item) => new Promise((resolve) => { const id = ++this.workerSeq; const on = (e) => { if (e.data.id !== id) return; this.worker.removeEventListener('message', on); resolve(e.data); }; this.worker.addEventListener('message', on); this.worker.postMessage({ id, file: item.file, name: item.file.name, mime: item.file.type }); })));
    digests.forEach((result, index) => { const item = candidates[index]; if (result.error) { item.state = 'failed'; item.error = result.error; } else { item.sha256 = result.sha256; item.mime = result.mime; } });
    const response = await fetch('/api/uploads/preflight', { method: 'POST', headers: { 'Content-Type': 'application/json', ...this.csrf() }, body: JSON.stringify({ batch_id: this.batchId, files: candidates.map((i) => ({ client_id: i.key, sha256: i.sha256, size: i.file.size, name: i.file.name, mime: i.mime })) }) });
    if (!response.ok) throw new Error(`preflight ${response.status}`);
    const result = await response.json();
    (result.files || result.items || []).forEach((entry) => { const item = candidates.find((i) => i.key === (entry.client_id || entry.key)); if (!item) return; if (entry.duplicate || entry.duplicate_of) { item.state = 'duplicate'; item.fileId = entry.file_id || entry.duplicate_of; } });
    this.render();
  }
  connectEvents() {
    if (!this.batchId || !window.WebSocket) return;
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:'; this.socket = new WebSocket(`${scheme}//${location.host}/api/uploads/events?batch_id=${encodeURIComponent(this.batchId)}`);
    this.socket.onmessage = (event) => { try { const data = JSON.parse(event.data); if (data.type === 'capacity') this.capacity = { slots: Math.max(1, data.slots || 1), maxBytes: data.max_bytes || Infinity }; if (data.type === 'snapshot') this.reconcile(data); this.pump(); } catch (_) {} };
    this.socket.onclose = () => { this.socket = null; setTimeout(() => this.connectEvents(), 3000); };
  }
  reconcile(snapshot) { (snapshot.items || snapshot.files || []).forEach((entry) => { const item = this.items.find((i) => i.key === (entry.client_id || entry.key)); if (item && entry.file_id) { item.fileId = entry.file_id; item.state = entry.state || 'accepted'; } }); this.render(); }
  async pump() {
    if (this.running || !this.batchId) return; this.running = true;
    try {
      while (true) {
        const pending = this.items.filter((i) => i.state === 'queued' && i.sha256 && i.file);
        if (!pending.length) break;
        const slots = Math.max(1, Math.min(this.capacity.slots || 1, _effectiveConcurrency()));
        const window = pending.slice(0, slots); await Promise.all(window.map((item) => this.send(item)));
        this.render(); this.setStatus(uploadMessage('uploadingBatch', { done: this.items.filter((i) => ['accepted','duplicate','processed'].includes(i.state)).length, total: this.items.length }));
        await new Promise((resolve) => setTimeout(resolve, _effectiveDelay()));
      }
      this.setStatus(uploadMessage('allComplete', { done: this.items.filter((i) => i.state !== 'failed').length, total: this.items.length }));
      window.dispatchEvent(new CustomEvent('allUploadsComplete', { detail: { total: this.items.length, completed: this.items.filter((i) => i.state !== 'failed').length } }));
    } finally { this.running = false; }
  }
  async send(item) {
    const body = new FormData(); body.append('file', item.file); body.append('batch_id', this.batchId); body.append('client_id', item.key); body.append('sha256', item.sha256); if (item.mime) body.append('mime', item.mime);
    item.state = 'uploading'; this.render();
    try { const response = await fetch('/api/uploads/files', { method: 'POST', headers: this.csrf(), body }); if (response.status === 429) { item.state='queued'; const retry=Number(response.headers.get('Retry-After') || 2); _onRateLimited(retry); await new Promise((resolve)=>setTimeout(resolve,retry*1000)); return this.send(item); } if (!response.ok) throw new Error(`upload ${response.status}`); const result=await response.json(); item.fileId=result.file_id || result.id || result.duplicate_of; item.state=result.duplicate ? 'duplicate' : (result.state || 'accepted'); this.storeItem(item); const queuedCallback=window.onDocuElevateUploadQueued; if (typeof queuedCallback==='function') queuedCallback({ operationId: result.batch_id || this.batchId, fileId: item.fileId, filename: item.file.name, state: item.state }); }
    catch (error) { item.state = 'failed'; item.error = String(error); }
  }
  setStatus(message) { if (this.statusMessage) this.statusMessage.textContent = message; }
  storeItem(item) { try { navigator.serviceWorker?.controller?.postMessage({ type: 'enqueue', item: { key: item.key, batchId: this.batchId, clientId: item.key, name: item.file.name, size: item.file.size, sha256: item.sha256, state: item.state, fileId: item.fileId || null, handle: item.handle || null } }); } catch (_) {} }
  render() { if (!this.progressContainer) return; this.progressContainer.replaceChildren(); this.items.slice(0, 100).forEach((item) => { const row=document.createElement('div'); row.className='flex justify-between text-xs mb-1'; row.textContent=`${item.file.name} — ${item.state}`; this.progressContainer.appendChild(row); }); if (this.items.length>100) { const more=document.createElement('div'); more.className='text-xs text-gray-500'; more.textContent=`… ${this.items.length-100} weitere Dateien`; this.progressContainer.appendChild(more); } }
}

async function obsoleteProcessFiles(files, progressContainer, statusMessage) {
  if (!files || !Array.from(files).length) return;
  if ('serviceWorker' in navigator && !navigator.serviceWorker.controller) { try { await navigator.serviceWorker.register('/static/js/upload-queue-sw.js', { scope: '/' }); } catch (_) {} }
  const queue = new PersistentBulkUploadQueue(progressContainer, statusMessage); window.docuElevateUploadQueue = queue; await queue.enqueue(files);
}

if (typeof window !== 'undefined') window.PersistentBulkUploadQueue = PersistentBulkUploadQueue;
