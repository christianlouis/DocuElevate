// frontend/static/js/upload.js
// Reusable drag-and-drop upload functionality for DocuElevate

// Configuration
const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500MB

// Upload throttling defaults (overridden by window.uploadConfig when available)
const DEFAULT_UPLOAD_CONCURRENCY = 3;
const DEFAULT_UPLOAD_QUEUE_DELAY_MS = 500;

// Allowed file types
const ACCEPTED_TYPES = {
  // PDF files
  'application/pdf': true,

  // Image formats
  'image/jpeg': true, 'image/jpg': true, 'image/png': true,
  'image/gif': true, 'image/bmp': true, 'image/tiff': true,
  'image/webp': true, 'image/svg+xml': true,

  // Office document formats - Word
  'application/msword': true,
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': true,
  'application/vnd.openxmlformats-officedocument.wordprocessingml.template': true,
  'application/vnd.ms-word.document.macroEnabled.12': true,

  // Excel
  'application/vnd.ms-excel': true,
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': true,
  'application/vnd.openxmlformats-officedocument.spreadsheetml.template': true,
  'application/vnd.ms-excel.sheet.macroEnabled.12': true,

  // PowerPoint
  'application/vnd.ms-powerpoint': true,
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': true,
  'application/vnd.openxmlformats-officedocument.presentationml.template': true,
  'application/vnd.openxmlformats-officedocument.presentationml.slideshow': true,

  // Other common formats
  'text/plain': true,
  'text/csv': true,
  'application/rtf': true,
  'text/rtf': true,
  'text/html': true,
  'application/xml': true,
  'text/xml': true
};

// File extensions that are always allowed (even if mime type is not recognized)
const ACCEPTED_EXTENSIONS = [
  '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
  '.odt', '.ods', '.odp', '.rtf', '.txt', '.csv',
  '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg', '.md'
];

// ---------------------------------------------------------------------------
// Directory traversal helpers (FileSystem Access API)
// ---------------------------------------------------------------------------

/**
 * Read all file entries from a DirectoryReader, handling the 100-entry limit
 * by calling readEntries() repeatedly until it returns an empty batch.
 * @param {FileSystemDirectoryReader} reader
 * @returns {Promise<FileSystemEntry[]>}
 */
function readAllDirectoryEntries(reader) {
  return new Promise((resolve, reject) => {
    const entries = [];
    function readBatch() {
      reader.readEntries((batch) => {
        if (batch.length === 0) {
          resolve(entries);
        } else {
          entries.push(...batch);
          readBatch();
        }
      }, reject);
    }
    readBatch();
  });
}

/**
 * Recursively collect all File objects from a FileSystemEntry tree.
 * @param {FileSystemEntry} entry
 * @param {File[]} files  - accumulator array
 * @returns {Promise<void>}
 */
async function traverseFileEntry(entry, files) {
  if (entry.isFile) {
    await new Promise((resolve) => {
      entry.file((file) => { files.push(file); resolve(); }, resolve);
    });
  } else if (entry.isDirectory) {
    const reader = entry.createReader();
    const subEntries = await readAllDirectoryEntries(reader);
    for (const sub of subEntries) {
      await traverseFileEntry(sub, files);
    }
  }
}

/**
 * Extract all File objects from a DataTransfer, recursively expanding any
 * dropped directories.  Falls back gracefully to dataTransfer.files when
 * the FileSystem Entry API is unavailable.
 * @param {DataTransfer} dataTransfer
 * @returns {Promise<File[]>}
 */
async function getFilesFromDataTransfer(dataTransfer) {
  // Use the FileSystem Entry API when available (all modern browsers)
  if (dataTransfer.items && dataTransfer.items.length > 0) {
    const files = [];
    const itemList = dataTransfer.items;
    for (let i = 0; i < itemList.length; i++) {
      const item = itemList[i];
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
  // Fallback: plain FileList (no directory support)
  return Array.from(dataTransfer.files || []);
}

// ---------------------------------------------------------------------------
// Queue-based upload runner
// ---------------------------------------------------------------------------

/**
 * Upload a list of files using a concurrency-limited queue with a configurable
 * delay between slot starts to prevent server overload.
 *
 * @param {File[]} files - Files to upload
 * @param {HTMLElement} progressContainer - Container element for progress display
 * @param {HTMLElement} statusMessage - Element for status message display
 */
function processFiles(files, progressContainer, statusMessage) {
  if (files.length === 0) return;

  const concurrency = (window.uploadConfig && window.uploadConfig.concurrency) || DEFAULT_UPLOAD_CONCURRENCY;
  const delayMs = (window.uploadConfig && window.uploadConfig.queueDelayMs) || DEFAULT_UPLOAD_QUEUE_DELAY_MS;

  if (statusMessage) {
    statusMessage.textContent = `Queued ${files.length} file(s) for upload…`;
  }

  // Clear previous upload progress
  if (progressContainer) {
    progressContainer.innerHTML = "";
  }

  // Pre-create all progress elements so the user sees the full list immediately
  const progressElements = files.map((file) => {
    const fileProgress = document.createElement("div");
    fileProgress.className = "flex flex-col mb-2";
    fileProgress.innerHTML = `
      <div class="flex justify-between">
        <span class="text-sm truncate" title="${file.name}">${file.name}</span>
        <span class="text-xs text-gray-500">${formatFileSize(file.size)}</span>
      </div>
      <div class="w-full bg-gray-200 h-2 rounded-full mt-1">
        <div class="file-progress-bar bg-gray-300 h-2 rounded-full" style="width: 0%"></div>
      </div>
      <div class="file-status text-xs text-gray-400 mt-1">Queued</div>
    `;
    if (progressContainer) progressContainer.appendChild(fileProgress);
    return fileProgress;
  });

  // Queue runner
  let index = 0;
  let active = 0;

  function startNext() {
    while (active < concurrency && index < files.length) {
      const i = index++;
      active++;
      const progressBar = progressElements[i].querySelector(".file-progress-bar");
      const statusEl = progressElements[i].querySelector(".file-status");
      validateAndUploadQueued(files[i], progressBar, statusEl, statusMessage).finally(() => {
        active--;
        setTimeout(startNext, delayMs);
      });
    }
  }

  startNext();
}

/**
 * Validate and upload a single file (used by the queue runner).
 * @param {File} file
 * @param {HTMLElement} progressBar
 * @param {HTMLElement} statusEl
 * @param {HTMLElement} statusMessage
 * @returns {Promise<void>}
 */
function validateAndUploadQueued(file, progressBar, statusEl, statusMessage) {
  // Validate file type by checking both MIME type and extension
  const isValidMimeType = ACCEPTED_TYPES[file.type] || false;
  const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
  const isValidExtension = ACCEPTED_EXTENSIONS.includes(fileExtension);

  if (!isValidMimeType && !isValidExtension) {
    statusEl.textContent = `Unsupported file type`;
    statusEl.className = "text-xs text-red-500 mt-1";
    progressBar.className = "file-progress-bar bg-red-500 h-2 rounded-full";
    updateOverallStatus(statusMessage);
    return Promise.resolve();
  }

  if (file.size > MAX_FILE_SIZE) {
    statusEl.textContent = `Exceeds 500 MB limit`;
    statusEl.className = "text-xs text-red-500 mt-1";
    progressBar.className = "file-progress-bar bg-red-500 h-2 rounded-full";
    updateOverallStatus(statusMessage);
    return Promise.resolve();
  }

  return uploadFile(file, progressBar, statusEl, statusMessage);
}

/**
 * Validate and upload a single file (legacy entry point kept for compatibility).
 * @param {File} file - File to validate and upload
 * @param {HTMLElement} progressContainer - Container element for progress display
 * @param {HTMLElement} statusMessage - Element for status message display
 */
function validateAndUpload(file, progressContainer, statusMessage) {
  // Create progress element for this file
  const fileProgress = document.createElement("div");
  fileProgress.className = "flex flex-col mb-2";
  fileProgress.innerHTML = `
    <div class="flex justify-between">
      <span class="text-sm truncate" title="${file.name}">${file.name}</span>
      <span class="text-xs text-gray-500">${formatFileSize(file.size)}</span>
    </div>
    <div class="w-full bg-gray-200 h-2 rounded-full mt-1">
      <div class="file-progress-bar bg-blue-500 h-2 rounded-full" style="width: 0%"></div>
    </div>
    <div class="file-status text-xs text-gray-600 mt-1">Validating...</div>
  `;

  if (progressContainer) {
    progressContainer.appendChild(fileProgress);
  }

  const progressBar = fileProgress.querySelector(".file-progress-bar");
  const statusEl = fileProgress.querySelector(".file-status");

  validateAndUploadQueued(file, progressBar, statusEl, statusMessage);
}

/**
 * Upload a file to the server
 * @param {File} file - File to upload
 * @param {HTMLElement} progressBar - Progress bar element
 * @param {HTMLElement} statusEl - Status element
 * @param {HTMLElement} statusMessage - Overall status message element
 * @returns {Promise<void>}
 */
function uploadFile(file, progressBar, statusEl, statusMessage) {
  statusEl.textContent = `Uploading…`;
  statusEl.className = "text-xs text-gray-600 mt-1";
  progressBar.className = "file-progress-bar bg-blue-500 h-2 rounded-full";

  return new Promise((resolve) => {
    try {
      const formData = new FormData();
      formData.append("file", file);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/ui-upload", true);

      // Attach CSRF token so the server-side CSRF middleware accepts the request.
      const csrfToken = typeof getCsrfToken === 'function' ? getCsrfToken() : '';
      if (csrfToken) {
        xhr.setRequestHeader("X-CSRF-Token", csrfToken);
      }

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const percentComplete = (e.loaded / e.total) * 100;
          progressBar.style.width = percentComplete + "%";
          statusEl.textContent = `Uploading: ${Math.round(percentComplete)}%`;
        }
      };

      xhr.onload = function () {
        if (xhr.status === 200) {
          const result = JSON.parse(xhr.responseText);
          progressBar.style.width = "100%";
          progressBar.className = "file-progress-bar bg-green-500 h-2 rounded-full";
          statusEl.textContent = `Success: Task ID: ${result.task_id}`;
          statusEl.className = "text-xs text-green-600 mt-1";
        } else {
          progressBar.className = "file-progress-bar bg-red-500 h-2 rounded-full";
          statusEl.textContent = `Error: Upload failed (HTTP ${xhr.status})`;
          statusEl.className = "text-xs text-red-500 mt-1";
        }
        updateOverallStatus(statusMessage);
        resolve();
      };

      xhr.onerror = function () {
        progressBar.className = "file-progress-bar bg-red-500 h-2 rounded-full";
        statusEl.textContent = `Error: Network error`;
        statusEl.className = "text-xs text-red-500 mt-1";
        updateOverallStatus(statusMessage);
        resolve();
      };

      xhr.send(formData);
    } catch (err) {
      statusEl.textContent = `Error: ${err.message}`;
      statusEl.className = "text-xs text-red-500 mt-1";
      progressBar.className = "file-progress-bar bg-red-500 h-2 rounded-full";
      updateOverallStatus(statusMessage);
      resolve();
    }
  });
}

/**
 * Update the overall status message based on file statuses
 * @param {HTMLElement} statusMessage - Status message element
 */
function updateOverallStatus(statusMessage) {
  if (!statusMessage) return;

  // Count success/failure
  const fileStatuses = document.querySelectorAll('.file-status');
  let completed = 0;
  const total = fileStatuses.length;

  fileStatuses.forEach(status => {
    if (status.textContent.includes('Success') || status.textContent.includes('Error') || status.textContent.includes('Unsupported') || status.textContent.includes('Exceeds')) {
      completed++;
    }
  });

  if (completed === total) {
    statusMessage.textContent = `All uploads completed (${completed}/${total})`;

    // Trigger a custom event when all uploads are complete
    const allUploadsComplete = new CustomEvent('allUploadsComplete', {
      detail: { total: total, completed: completed }
    });
    window.dispatchEvent(allUploadsComplete);
  } else {
    statusMessage.textContent = `Uploading files (${completed}/${total})`;
  }
}

/**
 * Format file size for display
 * @param {number} bytes - File size in bytes
 * @returns {string} Formatted file size
 */
function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Initialize drag-and-drop on an element with directory support.
 * @param {HTMLElement} element - Element to enable drag-and-drop on
 * @param {HTMLElement} progressContainer - Container for progress display
 * @param {HTMLElement} statusMessage - Element for status messages
 * @param {Object} options - Additional options
 */
function initDragAndDrop(element, progressContainer, statusMessage, options = {}) {
  if (!element) {
    console.error("Element not found for drag-and-drop initialization");
    return;
  }

  // Add event listeners for drag-and-drop
  element.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "copy";

    // Add visual feedback
    if (options.dragOverClass) {
      element.classList.add(options.dragOverClass);
    }
  });

  element.addEventListener("dragleave", (e) => {
    e.preventDefault();
    e.stopPropagation();

    // Remove visual feedback
    if (options.dragOverClass) {
      element.classList.remove(options.dragOverClass);
    }
  });

  element.addEventListener("drop", async (e) => {
    e.preventDefault();
    e.stopPropagation();

    // Remove visual feedback
    if (options.dragOverClass) {
      element.classList.remove(options.dragOverClass);
    }

    const files = await getFilesFromDataTransfer(e.dataTransfer);
    if (files.length > 0) {
      processFiles(files, progressContainer, statusMessage);
    }
  });
}

