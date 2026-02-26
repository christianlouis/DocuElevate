// frontend/static/js/upload.js
// Reusable drag-and-drop upload functionality for DocuElevate

// ── Configuration ─────────────────────────────────────────────────────────────
const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500 MB

/** Fallback upload throttling values when window.uploadConfig is not set. */
const DEFAULT_UPLOAD_CONCURRENCY = 3;
const DEFAULT_UPLOAD_QUEUE_DELAY_MS = 500;

/** Maximum number of 429 retries before a file is permanently marked failed. */
const MAX_RATE_LIMIT_RETRIES = 5;

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
 * @param {DataTransfer} dataTransfer
 * @returns {Promise<File[]>}
 */
async function getFilesFromDataTransfer(dataTransfer) {
  if (dataTransfer.items && dataTransfer.items.length > 0) {
    const files = [];
    for (let i = 0; i < dataTransfer.items.length; i++) {
      const item = dataTransfer.items[i];
      const entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
      if (entry) {
        await traverseFileEntry(entry, files);
      } else if (item.kind === 'file') {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
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
function processFiles(files, progressContainer, statusMessage) {
  const fileArray = Array.from(files);
  if (!fileArray.length) return;

  if (statusMessage) {
    statusMessage.textContent = `Queued ${fileArray.length} file(s) for upload…`;
  }
  if (progressContainer) progressContainer.innerHTML = '';

  // Pre-create one progress row per file.
  const queueItems = fileArray.map((file) => {
    const row = document.createElement('div');
    row.className = 'flex flex-col mb-2';
    row.innerHTML = `
      <div class="flex justify-between">
        <span class="text-sm truncate" title="${file.name}">${file.name}</span>
        <span class="text-xs text-gray-500">${formatFileSize(file.size)}</span>
      </div>
      <div class="w-full bg-gray-200 h-2 rounded-full mt-1">
        <div class="file-progress-bar bg-gray-300 h-2 rounded-full" style="width:0%"></div>
      </div>
      <div class="file-status text-xs text-gray-400 mt-1">Queued</div>
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
        item.statusEl.textContent = 'Unsupported file type';
        item.statusEl.className = 'text-xs text-red-500 mt-1';
        active--;
        updateOverallStatus(statusMessage);
        // No HTTP request – skip straight to next without adding delay.
        scheduleNext();
        continue;
      }

      if (item.file.size > MAX_FILE_SIZE) {
        item.progressBar.className = 'file-progress-bar bg-red-500 h-2 rounded-full';
        item.statusEl.textContent = 'Exceeds 500 MB limit';
        item.statusEl.className = 'text-xs text-red-500 mt-1';
        active--;
        updateOverallStatus(statusMessage);
        scheduleNext();
        continue;
      }

      _uploadSingleFile(item.file, item.progressBar, item.statusEl, statusMessage)
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
              item.statusEl.textContent = 'Failed: rate limit retries exhausted';
              item.statusEl.className = 'text-xs text-red-500 mt-1';
              updateOverallStatus(statusMessage);
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
 * @param {HTMLElement} statusMessage
 * @returns {Promise<{rateLimited: boolean, retryAfterSeconds: number}>}
 */
function _uploadSingleFile(file, progressBar, statusEl, statusMessage) {
  statusEl.textContent = 'Uploading…';
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
        statusEl.textContent = `Uploading: ${pct}%`;
      }
    };

    xhr.onload = () => {
      if (xhr.status === 200) {
        const result = JSON.parse(xhr.responseText);
        progressBar.style.width = '100%';
        progressBar.className = 'file-progress-bar bg-green-500 h-2 rounded-full';
        statusEl.textContent = `Success: Task ID: ${result.task_id}`;
        statusEl.className = 'text-xs text-green-600 mt-1';
        _onUploadSuccess();
        updateOverallStatus(statusMessage);
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
        statusEl.textContent = 'Rate limited – queued to retry…';
        statusEl.className = 'text-xs text-yellow-600 mt-1';
        resolve({ rateLimited: true, retryAfterSeconds: retryAfter });

      } else {
        progressBar.className = 'file-progress-bar bg-red-500 h-2 rounded-full';
        statusEl.textContent = `Error: HTTP ${xhr.status}`;
        statusEl.className = 'text-xs text-red-500 mt-1';
        updateOverallStatus(statusMessage);
        resolve({ rateLimited: false, retryAfterSeconds: 0 });
      }
    };

    xhr.onerror = () => {
      progressBar.className = 'file-progress-bar bg-red-500 h-2 rounded-full';
      statusEl.textContent = 'Error: Network error';
      statusEl.className = 'text-xs text-red-500 mt-1';
      updateOverallStatus(statusMessage);
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

// ── Status helpers ────────────────────────────────────────────────────────────

/**
 * Re-calculate and display the overall upload status.
 * Fires 'allUploadsComplete' when every item has a terminal status.
 * @param {HTMLElement} statusMessage
 */
function updateOverallStatus(statusMessage) {
  if (!statusMessage) return;

  const fileStatuses = document.querySelectorAll('.file-status');
  let done = 0;
  const total = fileStatuses.length;

  fileStatuses.forEach((s) => {
    const t = s.textContent;
    if (
      t.startsWith('Success') ||
      t.startsWith('Error') ||
      t.startsWith('Unsupported') ||
      t.startsWith('Exceeds') ||
      t.startsWith('Failed:')
    ) done++;
  });

  if (done === total && total > 0) {
    statusMessage.textContent = `All uploads completed (${done}/${total})`;
    window.dispatchEvent(new CustomEvent('allUploadsComplete', { detail: { total, completed: done } }));
  } else {
    statusMessage.textContent = `Uploading files (${done}/${total})`;
  }
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


