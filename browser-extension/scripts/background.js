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

    // Create context menu items
    chrome.contextMenus.create({
        id: 'send-to-docuelevate',
        title: 'Send URL to DocuElevate',
        contexts: ['link', 'page']
    });
    
    chrome.contextMenus.create({
        id: 'clip-page-to-docuelevate',
        title: 'Clip Full Page to DocuElevate',
        contexts: ['page']
    });
    
    chrome.contextMenus.create({
        id: 'clip-selection-to-docuelevate',
        title: 'Clip Selection to DocuElevate',
        contexts: ['selection']
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
    
    if (message.type === 'CLIP_PAGE') {
        handleClipPage(message.data)
            .then(result => sendResponse({ success: true, data: result }))
            .catch(error => sendResponse({ success: false, error: error.message }));
        return true;
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

// Handle clipping page content to DocuElevate
async function handleClipPage(data) {
    const { html, title, filename, serverUrl, sessionCookie } = data;

    if (!html || !serverUrl) {
        throw new Error('HTML content and server URL are required');
    }

    // Convert HTML to PDF using browser's print API
    let pdfData;
    try {
        pdfData = await convertHtmlToPdf(html);
    } catch (error) {
        throw new Error(`Failed to convert to PDF: ${error.message}`);
    }

    const headers = {};
    if (sessionCookie) {
        headers['Cookie'] = sessionCookie;
    }

    // Determine filename
    const safeFilename = filename || title || 'web-clip';
    const pdfFilename = safeFilename.endsWith('.pdf') ? safeFilename : `${safeFilename}.pdf`;

    // Create form data with PDF
    const formData = new FormData();
    const blob = new Blob([pdfData], { type: 'application/pdf' });
    formData.append('file', blob, pdfFilename);

    const response = await fetch(`${serverUrl}/api/files/upload`, {
        method: 'POST',
        headers: headers,
        body: formData,
        credentials: 'include'
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    return await response.json();
}

/**
 * Convert HTML to PDF using Chrome's printing API
 * @param {string} html - HTML content to convert
 * @returns {Promise<Uint8Array>} PDF data
 */
async function convertHtmlToPdf(html) {
    // Create a data URL with the HTML content
    const dataUrl = 'data:text/html;charset=utf-8,' + encodeURIComponent(html);
    
    // Create a new tab with the HTML
    const tab = await chrome.tabs.create({ url: dataUrl, active: false });
    
    try {
        // Wait for the page to load
        await new Promise(resolve => {
            const listener = (tabId, changeInfo) => {
                if (tabId === tab.id && changeInfo.status === 'complete') {
                    chrome.tabs.onUpdated.removeListener(listener);
                    resolve();
                }
            };
            chrome.tabs.onUpdated.addListener(listener);
        });
        
        // Wait for page to fully render before PDF conversion
        // This delay ensures JavaScript execution, dynamic content rendering,
        // and CSS transitions have completed. May need adjustment for complex pages.
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Use Chrome's print to PDF API
        const pdfData = await chrome.tabs.printToPDF(tab.id, {
            paperFormat: 'A4',
            landscape: false,
            marginTop: 0.4,
            marginBottom: 0.4,
            marginLeft: 0.4,
            marginRight: 0.4,
            printBackground: true,
            preferCSSPageSize: false
        });
        
        return new Uint8Array(pdfData);
    } finally {
        // Close the temporary tab
        await chrome.tabs.remove(tab.id);
    }
}

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
    // Load configuration
    const config = await new Promise((resolve) => {
        chrome.storage.sync.get(['serverUrl', 'sessionCookie'], resolve);
    });

    if (!config.serverUrl) {
        // Open popup to configure
        chrome.action.openPopup();
        return;
    }

    if (info.menuItemId === 'send-to-docuelevate') {
        // Get the URL to send (link URL or page URL)
        const targetUrl = info.linkUrl || info.pageUrl;

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
                message: `URL sent successfully! Task ID: ${result.task_id}`
            });
        } catch (error) {
            // Show error notification
            chrome.notifications.create({
                type: 'basic',
                iconUrl: 'icons/icon48.png',
                title: 'DocuElevate Error',
                message: `Failed to send URL: ${error.message}`
            });
        }
    } else if (info.menuItemId === 'clip-page-to-docuelevate') {
        // Capture full page
        try {
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: () => {
                    // This function runs in the page context
                    const captureFullPage = () => {
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
                    return captureFullPage();
                }
            });
            
            const pageData = result.result;
            
            // Send to DocuElevate
            const uploadResult = await handleClipPage({
                html: pageData.html,
                title: pageData.title,
                filename: `${pageData.title}.pdf`,
                serverUrl: config.serverUrl,
                sessionCookie: config.sessionCookie
            });

            // Show success notification
            chrome.notifications.create({
                type: 'basic',
                iconUrl: 'icons/icon48.png',
                title: 'DocuElevate',
                message: `Page clipped successfully! Task ID: ${uploadResult.task_id}`
            });
        } catch (error) {
            // Show error notification
            chrome.notifications.create({
                type: 'basic',
                iconUrl: 'icons/icon48.png',
                title: 'DocuElevate Error',
                message: `Failed to clip page: ${error.message}`
            });
        }
    } else if (info.menuItemId === 'clip-selection-to-docuelevate') {
        // Capture selection
        try {
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: () => {
                    // This function runs in the page context
                    const captureSelection = () => {
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
                    return captureSelection();
                }
            });
            
            const selectionData = result.result;
            
            // Send to DocuElevate
            const uploadResult = await handleClipPage({
                html: selectionData.html,
                title: selectionData.title,
                filename: `${selectionData.title}.pdf`,
                serverUrl: config.serverUrl,
                sessionCookie: config.sessionCookie
            });

            // Show success notification
            chrome.notifications.create({
                type: 'basic',
                iconUrl: 'icons/icon48.png',
                title: 'DocuElevate',
                message: `Selection clipped successfully! Task ID: ${uploadResult.task_id}`
            });
        } catch (error) {
            // Show error notification
            chrome.notifications.create({
                type: 'basic',
                iconUrl: 'icons/icon48.png',
                title: 'DocuElevate Error',
                message: `Failed to clip selection: ${error.message}`
            });
        }
    }
});
