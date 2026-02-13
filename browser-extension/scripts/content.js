/* global chrome */
// Content script for DocuElevate browser extension

// This script runs on all web pages to enable communication
// between page content and the extension

// Message handler reserved for future functionality
// Future use case: Extract additional page metadata or interact with page content
// Currently not used - can be removed if not needed
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'GET_PAGE_INFO') {
        // Return information about the current page
        const pageInfo = {
            url: window.location.href,
            title: document.title
        };
        sendResponse(pageInfo);
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
