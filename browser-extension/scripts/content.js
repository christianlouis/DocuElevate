// Content script for DocuElevate browser extension

// This script runs on all web pages to enable communication
// between page content and the extension

/**
 * Capture the full page HTML with inline styles
 */
function captureFullPage() {
    // Get all stylesheets and inline them
    const styles = Array.from(document.styleSheets)
        .map(sheet => {
            try {
                return Array.from(sheet.cssRules)
                    .map(rule => rule.cssText)
                    .join('\n');
            } catch (e) {
                // Handle CORS issues with external stylesheets
                console.warn('Could not access stylesheet:', sheet.href, e);
                return '';
            }
        })
        .join('\n');
    
    // Create a complete HTML document with inlined styles
    const styledHtml = `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>${document.title}</title>
    <style>${styles}</style>
</head>
<body>
    ${document.body.innerHTML}
</body>
</html>`;
    
    return {
        html: styledHtml,
        title: document.title,
        url: window.location.href,
        timestamp: new Date().toISOString()
    };
}

/**
 * Capture selected content from the page
 * Note: For performance, uses basic HTML structure without per-element computed styles.
 * The resulting PDF will use browser default styles.
 */
function captureSelection() {
    const selection = window.getSelection();
    
    if (!selection || selection.rangeCount === 0) {
        throw new Error('No content selected');
    }
    
    const range = selection.getRangeAt(0);
    const container = document.createElement('div');
    container.appendChild(range.cloneContents());
    
    const html = `<!DOCTYPE html>
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
</html>`;
</body>
</html>`;
    
    return {
        html: html,
        text: selection.toString(),
        title: document.title + ' - Selection',
        url: window.location.href,
        timestamp: new Date().toISOString()
    };
}

// Message handler
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'GET_PAGE_INFO') {
        // Return information about the current page (synchronous)
        const pageInfo = {
            url: window.location.href,
            title: document.title
        };
        sendResponse(pageInfo);
        return false; // Synchronous response, no need to keep channel open
    }
    
    if (message.type === 'CAPTURE_FULL_PAGE') {
        try {
            const pageData = captureFullPage();
            sendResponse({ success: true, data: pageData });
        } catch (error) {
            sendResponse({ success: false, error: error.message });
        }
        return true; // Keep channel open for async response
    }
    
    if (message.type === 'CAPTURE_SELECTION') {
        try {
            const selectionData = captureSelection();
            sendResponse({ success: true, data: selectionData });
        } catch (error) {
            sendResponse({ success: false, error: error.message });
        }
        return true; // Keep channel open for async response
    }
});

// Detect if current page is a direct file link
function isDirectFileUrl(url) {
    const fileExtensions = [
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.txt', '.csv', '.rtf', '.jpg', '.jpeg', '.png', '.gif',
        '.bmp', '.tiff', '.webp', '.svg'
    ];

    const urlLower = url.toLowerCase();
    return fileExtensions.some(ext => urlLower.endsWith(ext));
}

// Add visual indicator for file pages (optional enhancement)
if (isDirectFileUrl(window.location.href)) {
    console.log('DocuElevate: Direct file URL detected');
}
