// Web page capture script for DocuElevate browser extension
// This script handles capturing web page content for PDF conversion

/**
 * Capture the full page HTML with inline styles
 * @returns {Object} Page data with HTML, title, and URL
 */
function captureFullPage() {
    // Clone the document to avoid modifying the original
    const clonedDoc = document.cloneNode(true);
    
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
    
    // Get page HTML
    const html = document.documentElement.outerHTML;
    
    // Create a complete HTML document with inlined styles
    const styledHtml = `
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>${document.title}</title>
    <style>${styles}</style>
</head>
<body>
    ${document.body.innerHTML}
</body>
</html>
    `;
    
    return {
        html: styledHtml,
        title: document.title,
        url: window.location.href,
        timestamp: new Date().toISOString()
    };
}

/**
 * Capture selected content from the page
 * @returns {Object} Selection data with HTML, text, and metadata
 */
function captureSelection() {
    const selection = window.getSelection();
    
    if (!selection || selection.rangeCount === 0) {
        throw new Error('No content selected');
    }
    
    const range = selection.getRangeAt(0);
    const container = document.createElement('div');
    container.appendChild(range.cloneContents());
    
    // Get computed styles for the selection
    const styles = [];
    const elements = container.querySelectorAll('*');
    elements.forEach(el => {
        const computed = window.getComputedStyle(el);
        // Only preserve essential styles
        const essentialStyles = [
            'font-family', 'font-size', 'font-weight', 'color',
            'background-color', 'text-align', 'margin', 'padding'
        ];
        let styleStr = '';
        essentialStyles.forEach(prop => {
            const value = computed.getPropertyValue(prop);
            if (value) {
                styleStr += `${prop}: ${value}; `;
            }
        });
        if (styleStr) {
            el.setAttribute('style', styleStr);
        }
    });
    
    const html = `
<!DOCTYPE html>
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
</html>
    `;
    
    return {
        html: html,
        text: selection.toString(),
        title: document.title + ' - Selection',
        url: window.location.href,
        timestamp: new Date().toISOString()
    };
}

/**
 * Take a screenshot of the visible viewport
 * @returns {Promise<string>} Data URL of the screenshot
 */
async function captureScreenshot() {
    // This will be called from the background script
    // since content scripts can't use chrome.tabs.captureVisibleTab
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(
            { type: 'CAPTURE_SCREENSHOT' },
            response => {
                if (response.success) {
                    resolve(response.dataUrl);
                } else {
                    reject(new Error(response.error));
                }
            }
        );
    });
}

// Listen for capture requests from popup or background
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'CAPTURE_FULL_PAGE') {
        try {
            const pageData = captureFullPage();
            sendResponse({ success: true, data: pageData });
        } catch (error) {
            sendResponse({ success: false, error: error.message });
        }
        return true;
    }
    
    if (message.type === 'CAPTURE_SELECTION') {
        try {
            const selectionData = captureSelection();
            sendResponse({ success: true, data: selectionData });
        } catch (error) {
            sendResponse({ success: false, error: error.message });
        }
        return true;
    }
});

// Export functions for use in tests or other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        captureFullPage,
        captureSelection
    };
}
