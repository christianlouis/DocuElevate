// Popup script for DocuElevate browser extension

// DOM elements
const configSection = document.getElementById('config-section');
const sendSection = document.getElementById('send-section');
const statusSection = document.getElementById('status-section');
const statusMessage = document.getElementById('status-message');

const serverUrlInput = document.getElementById('server-url');
const sessionCookieInput = document.getElementById('session-cookie');
const filenameInput = document.getElementById('filename');
const currentUrlDisplay = document.getElementById('current-url');

const saveConfigBtn = document.getElementById('save-config');
const sendFileBtn = document.getElementById('send-file');
const showConfigBtn = document.getElementById('show-config');

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
    
    // Get current tab URL
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const currentUrl = tabs[0]?.url || '';
    currentUrlDisplay.textContent = currentUrl;
    
    // Show appropriate section
    if (config.serverUrl) {
        showSendSection();
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
        showSendSection();
    }, 1000);
});

// Send file to DocuElevate
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
    showStatus('Sending file to DocuElevate...', 'info');
    
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
        
        const result = await response.json();
        
        if (response.ok) {
            showStatus(
                `✓ File sent successfully! Task ID: ${result.task_id}\nFilename: ${result.filename}`,
                'success'
            );
        } else {
            showStatus(
                `Error: ${result.detail || 'Failed to send file'}`,
                'error'
            );
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

// Show configuration section
showConfigBtn.addEventListener('click', () => {
    showConfigSection();
});

// Utility functions
function showConfigSection() {
    configSection.classList.remove('hidden');
    sendSection.classList.add('hidden');
    statusSection.classList.add('hidden');
}

function showSendSection() {
    configSection.classList.add('hidden');
    sendSection.classList.remove('hidden');
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
