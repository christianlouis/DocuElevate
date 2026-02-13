// frontend/static/js/upload.js
// Reusable drag-and-drop upload functionality for DocuElevate

// Configuration
const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500MB

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

/**
 * Process a list of files for upload
 * @param {FileList} files - Files to process
 * @param {HTMLElement} progressContainer - Container element for progress display
 * @param {HTMLElement} statusMessage - Element for status message display
 */
function processFiles(files, progressContainer, statusMessage) {
  if (files.length === 0) return;

  if (statusMessage) {
    statusMessage.textContent = `Processing ${files.length} file(s)...`;
  }

  // Clear previous upload progress
  if (progressContainer) {
    progressContainer.innerHTML = "";
  }

  // Process each file
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    validateAndUpload(file, progressContainer, statusMessage);
  }
}

/**
 * Validate and upload a single file
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

  // Validate file type by checking both MIME type and extension
  const isValidMimeType = ACCEPTED_TYPES[file.type] || false;
  const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
  const isValidExtension = ACCEPTED_EXTENSIONS.includes(fileExtension);

  if (!isValidMimeType && !isValidExtension) {
    statusEl.textContent = `Error: ${file.name} - Unsupported file type`;
    statusEl.className = "text-xs text-red-500 mt-1";
    return;
  }

  // Validate file size
  if (file.size > MAX_FILE_SIZE) {
    statusEl.textContent = `Error: ${file.name} - File size exceeds 500MB limit`;
    statusEl.className = "text-xs text-red-500 mt-1";
    return;
  }

  // Upload the file
  uploadFile(file, progressBar, statusEl, statusMessage);
}

/**
 * Upload a file to the server
 * @param {File} file - File to upload
 * @param {HTMLElement} progressBar - Progress bar element
 * @param {HTMLElement} statusEl - Status element
 * @param {HTMLElement} statusMessage - Overall status message element
 */
async function uploadFile(file, progressBar, statusEl, statusMessage) {
  statusEl.textContent = `Uploading...`;
  try {
    let formData = new FormData();
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/ui-upload", true);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const percentComplete = (e.loaded / e.total) * 100;
        progressBar.style.width = percentComplete + "%";
        statusEl.textContent = `Uploading: ${Math.round(percentComplete)}%`;
      }
    };

    xhr.onload = function() {
      if (xhr.status === 200) {
        const result = JSON.parse(xhr.responseText);
        progressBar.style.width = "100%";
        progressBar.className = "file-progress-bar bg-green-500 h-2 rounded-full";
        statusEl.textContent = `Success: Task ID: ${result.task_id}`;
        statusEl.className = "text-xs text-green-600 mt-1";
        updateOverallStatus(statusMessage);
      } else {
        throw new Error(`Upload failed with status ${xhr.status}`);
      }
    };

    xhr.onerror = function() {
      throw new Error("Network error occurred");
    };

    xhr.send(formData);

  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
    statusEl.className = "text-xs text-red-500 mt-1";
    progressBar.className = "file-progress-bar bg-red-500 h-2 rounded-full";
    updateOverallStatus(statusMessage);
  }
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
  let total = fileStatuses.length;

  fileStatuses.forEach(status => {
    if (status.textContent.includes('Success') || status.textContent.includes('Error')) {
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
 * Initialize drag-and-drop on an element
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

  element.addEventListener("drop", (e) => {
    e.preventDefault();
    e.stopPropagation();

    // Remove visual feedback
    if (options.dragOverClass) {
      element.classList.remove(options.dragOverClass);
    }

    if (e.dataTransfer.files.length) {
      processFiles(e.dataTransfer.files, progressContainer, statusMessage);
    }
  });
}
