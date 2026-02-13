// Web page capture script for DocuElevate browser extension
// This script handles capturing web page content for PDF conversion

/**
 * Capture the full page HTML with inline styles
 * @returns {Object} Page data with HTML, title, and URL
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

// Export functions for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        captureFullPage,
        captureSelection
    };
}
