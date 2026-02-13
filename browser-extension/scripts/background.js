// Background service worker for DocuElevate browser extension

// Listen for installation
chrome.runtime.onInstalled.addListener((details) => {
    if (details.reason === 'install') {
        console.log('DocuElevate extension installed');
        // Note: We don't open the popup automatically to avoid poor UX
        // User can click the extension icon to configure
    } else if (details.reason === 'update') {
        console.log('DocuElevate extension updated');
    }

    // Create context menu item
    chrome.contextMenus.create({
        id: 'send-to-docuelevate',
        title: 'Send to DocuElevate',
        contexts: ['link', 'page']
    });
});

// Listen for messages from content script or popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'SEND_URL') {
        handleSendUrl(message.data)
            .then(result => sendResponse({ success: true, data: result }))
            .catch(error => sendResponse({ success: false, error: error.message }));
        return true; // Keep channel open for async response
    }
});

// Handle sending URL to DocuElevate
async function handleSendUrl(data) {
    const { url, filename, serverUrl, sessionCookie } = data;

    if (!url || !serverUrl) {
        throw new Error('URL and server URL are required');
    }

    const headers = {
        'Content-Type': 'application/json'
    };

    if (sessionCookie) {
        headers['Cookie'] = sessionCookie;
    }

    const payload = {
        url: url,
        filename: filename || null
    };

    const response = await fetch(`${serverUrl}/api/process-url`, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload),
        credentials: 'include'
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    return await response.json();
}

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
    if (info.menuItemId === 'send-to-docuelevate') {
        // Get the URL to send (link URL or page URL)
        const targetUrl = info.linkUrl || info.pageUrl;

        // Load configuration
        const config = await new Promise((resolve) => {
            chrome.storage.sync.get(['serverUrl', 'sessionCookie'], resolve);
        });

        if (!config.serverUrl) {
            // Open popup to configure
            chrome.action.openPopup();
            return;
        }

        // Send the URL
        try {
            const result = await handleSendUrl({
                url: targetUrl,
                serverUrl: config.serverUrl,
                sessionCookie: config.sessionCookie
            });

            // Show success notification
            chrome.notifications.create({
                type: 'basic',
                iconUrl: 'icons/icon48.png',
                title: 'DocuElevate',
                message: `File sent successfully! Task ID: ${result.task_id}`
            });
        } catch (error) {
            // Show error notification
            chrome.notifications.create({
                type: 'basic',
                iconUrl: 'icons/icon48.png',
                title: 'DocuElevate Error',
                message: `Failed to send file: ${error.message}`
            });
        }
    }
});
