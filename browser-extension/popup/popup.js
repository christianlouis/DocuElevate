// Popup script for DocuElevate browser extension

// DOM elements
const configSection = document.getElementById('config-section');
const modeSection = document.getElementById('mode-section');
const sendSection = document.getElementById('send-section');
const clipSection = document.getElementById('clip-section');
const statusSection = document.getElementById('status-section');
const statusMessage = document.getElementById('status-message');

const serverUrlInput = document.getElementById('server-url');
const sessionCookieInput = document.getElementById('session-cookie');
const filenameInput = document.getElementById('filename');
const clipFilenameInput = document.getElementById('clip-filename');
const currentUrlDisplay = document.getElementById('current-url');
const pageTitleDisplay = document.getElementById('page-title');

const saveConfigBtn = document.getElementById('save-config');
const sendFileBtn = document.getElementById('send-file');
const showConfigBtn = document.getElementById('show-config');
const showConfigFromClipBtn = document.getElementById('show-config-from-clip');
const modeUrlBtn = document.getElementById('mode-url');
const modeClipBtn = document.getElementById('mode-clip');
const clipFullPageBtn = document.getElementById('clip-full-page');
const clipSelectionBtn = document.getElementById('clip-selection');

let currentMode = 'url'; // 'url' or 'clip'

// Load configuration and current tab URL on popup open
document.addEventListener('DOMContentLoaded', async () => {
    // Load saved configuration
    const config = await loadConfig();

    if (config.serverUrl) {
        serverUrlInput.value = config.serverUrl;
    }

    if (config.sessionCookie) {
        sessionCookieInput.value = config.sessionCookie;
    }

    // Get current tab info
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const currentUrl = tabs[0]?.url || '';
    const pageTitle = tabs[0]?.title || '';
    currentUrlDisplay.textContent = currentUrl;
    pageTitleDisplay.textContent = pageTitle;

    // Show appropriate section
    if (config.serverUrl) {
        showModeSection();
        showUrlMode();
    } else {
        showConfigSection();
    }
});

// Save configuration
saveConfigBtn.addEventListener('click', async () => {
    const serverUrl = serverUrlInput.value.trim();

    if (!serverUrl) {
        showStatus('Please enter a server URL', 'error');
        return;
    }

    // Validate URL format
    try {
        new URL(serverUrl);
    } catch (e) {
        showStatus('Invalid server URL format', 'error');
        return;
    }

    const config = {
        serverUrl: serverUrl,
        sessionCookie: sessionCookieInput.value.trim()
    };

    await saveConfig(config);
    showStatus('Configuration saved successfully!', 'success');

    setTimeout(() => {
        showModeSection();
        showUrlMode();
    }, 1000);
});

// Mode selection
modeUrlBtn.addEventListener('click', () => {
    showUrlMode();
});

modeClipBtn.addEventListener('click', () => {
    showClipMode();
});

// Send file URL to DocuElevate
sendFileBtn.addEventListener('click', async () => {
    const config = await loadConfig();
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const currentUrl = tabs[0]?.url || '';

    if (!currentUrl) {
        showStatus('No URL found in current tab', 'error');
        return;
    }

    // Disable button and show loading
    sendFileBtn.disabled = true;
    sendFileBtn.classList.add('loading');
    showStatus('Sending URL to DocuElevate...', 'info');

    try {
        const payload = {
            url: currentUrl,
            filename: filenameInput.value.trim() || null
        };

        const headers = {
            'Content-Type': 'application/json'
        };

        // Add session cookie if provided
        if (config.sessionCookie) {
            headers['Cookie'] = config.sessionCookie;
        }

        const response = await fetch(`${config.serverUrl}/api/process-url`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload),
            credentials: 'include'
        });

        if (response.ok) {
            const result = await response.json();
            showStatus(
                `✓ URL sent successfully! Task ID: ${result.task_id}\nFilename: ${result.filename}`,
                'success'
            );
        } else {
            // Try to parse JSON error, fall back to status text
            let errorMessage = 'Failed to send URL';
            try {
                const result = await response.json();
                errorMessage = result.detail || errorMessage;
            } catch (jsonError) {
                // Server returned non-JSON error response
                errorMessage = `HTTP ${response.status}: ${response.statusText}`;
            }
            showStatus(`Error: ${errorMessage}`, 'error');
        }
    } catch (error) {
        showStatus(
            `Error: ${error.message || 'Failed to connect to DocuElevate server'}`,
            'error'
        );
    } finally {
        sendFileBtn.disabled = false;
        sendFileBtn.classList.remove('loading');
    }
});

// Clip full page
clipFullPageBtn.addEventListener('click', async () => {
    await handleClipPage('full');
});

// Clip selection
clipSelectionBtn.addEventListener('click', async () => {
    await handleClipPage('selection');
});

// Handle clipping page
async function handleClipPage(mode) {
    const config = await loadConfig();
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];

    if (!tab) {
        showStatus('No active tab found', 'error');
        return;
    }

    // Disable buttons and show loading
    const button = mode === 'full' ? clipFullPageBtn : clipSelectionBtn;
    button.disabled = true;
    button.classList.add('loading');
    showStatus(`Clipping ${mode === 'full' ? 'full page' : 'selection'}...`, 'info');

    try {
        // Capture page content using content script
        let captureFunc;
        if (mode === 'full') {
            captureFunc = () => {
                const styles = Array.from(document.styleSheets)
                    .map(sheet => {
                        try {
                            return Array.from(sheet.cssRules)
                                .map(rule => rule.cssText)
                                .join('\n');
                        } catch (e) {
                            return '';
                        }
                    })
                    .join('\n');
                
                return {
                    html: `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>${document.title}</title>
    <style>${styles}</style>
</head>
<body>
    ${document.body.innerHTML}
</body>
</html>`,
                    title: document.title,
                    url: window.location.href
                };
            };
        } else {
            captureFunc = () => {
                const selection = window.getSelection();
                
                if (!selection || selection.rangeCount === 0) {
                    throw new Error('No content selected');
                }
                
                const range = selection.getRangeAt(0);
                const container = document.createElement('div');
                container.appendChild(range.cloneContents());
                
                return {
                    html: `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>${document.title} - Selection</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
    </style>
</head>
<body>
    <h1>${document.title}</h1>
    <p><small>Source: ${window.location.href}</small></p>
    <hr>
    ${container.innerHTML}
</body>
</html>`,
                    title: document.title + ' - Selection',
                    url: window.location.href
                };
            };
        }

        const [result] = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: captureFunc
        });

        if (!result || !result.result) {
            throw new Error('Failed to capture page content');
        }

        const pageData = result.result;

        // Send message to background script to convert and upload
        const response = await chrome.runtime.sendMessage({
            type: 'CLIP_PAGE',
            data: {
                html: pageData.html,
                title: pageData.title,
                filename: clipFilenameInput.value.trim() || pageData.title,
                serverUrl: config.serverUrl,
                sessionCookie: config.sessionCookie
            }
        });

        if (response.success) {
            showStatus(
                `✓ Page clipped successfully! Task ID: ${response.data.task_id}`,
                'success'
            );
        } else {
            throw new Error(response.error || 'Failed to clip page');
        }
    } catch (error) {
        showStatus(
            `Error: ${error.message || 'Failed to clip page'}`,
            'error'
        );
    } finally {
        button.disabled = false;
        button.classList.remove('loading');
    }
}

// Show configuration section
showConfigBtn.addEventListener('click', () => {
    showConfigSection();
});

showConfigFromClipBtn.addEventListener('click', () => {
    showConfigSection();
});

// Utility functions
function showConfigSection() {
    configSection.classList.remove('hidden');
    modeSection.classList.add('hidden');
    sendSection.classList.add('hidden');
    clipSection.classList.add('hidden');
    statusSection.classList.add('hidden');
}

function showModeSection() {
    configSection.classList.add('hidden');
    modeSection.classList.remove('hidden');
    statusSection.classList.add('hidden');
}

function showUrlMode() {
    currentMode = 'url';
    modeUrlBtn.classList.add('active');
    modeClipBtn.classList.remove('active');
    sendSection.classList.remove('hidden');
    clipSection.classList.add('hidden');
    statusSection.classList.add('hidden');
}

function showClipMode() {
    currentMode = 'clip';
    modeClipBtn.classList.add('active');
    modeUrlBtn.classList.remove('active');
    clipSection.classList.remove('hidden');
    sendSection.classList.add('hidden');
    statusSection.classList.add('hidden');
}

function showStatus(message, type) {
    statusMessage.textContent = message;
    statusMessage.className = type;
    statusSection.classList.remove('hidden');
}

async function loadConfig() {
    return new Promise((resolve) => {
        chrome.storage.sync.get(['serverUrl', 'sessionCookie'], (result) => {
            resolve(result);
        });
    });
}

async function saveConfig(config) {
    return new Promise((resolve) => {
        chrome.storage.sync.set(config, () => {
            resolve();
        });
    });
}
