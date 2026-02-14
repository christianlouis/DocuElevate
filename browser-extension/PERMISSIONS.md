# Browser Extension Permissions

This document explains the permissions requested by the DocuElevate browser extension.

## Requested Permissions

The extension requests the following permissions in `manifest.json`:

### activeTab
- **Purpose**: Get the URL and content of the currently active tab
- **Usage**: When you click the extension icon, it reads the current tab's URL and content for clipping
- **Privacy**: Only accesses the active tab when you explicitly use the extension
- **Alternative**: Without this, the extension couldn't show you which file you're sending or clip pages

### storage
- **Purpose**: Save your configuration (server URL and session cookie)
- **Usage**: Stores your DocuElevate server URL and optional session cookie locally
- **Privacy**: All data stays on your device; nothing is sent to third parties
- **Alternative**: Without this, you'd need to reconfigure the extension every time

### contextMenus
- **Purpose**: Add context menu options for sending URLs and clipping pages
- **Usage**: Creates context menu items for quick access (Send URL, Clip Full Page, Clip Selection)
- **Privacy**: No data access; only adds menu items
- **Alternative**: Without this, you'd only have the toolbar icon

### notifications
- **Purpose**: Show success/error notifications
- **Usage**: Displays browser notifications when files are sent or clipped successfully, or when errors occur
- **Privacy**: Only shows notifications based on your actions
- **Alternative**: Without this, you wouldn't get feedback from context menu actions

### scripting (New in v1.1.0)
- **Purpose**: Inject content capture code into web pages for clipping
- **Usage**: When you click "Clip Page" or "Clip Selection", this permission allows the extension to execute code that captures page HTML
- **Privacy**: Code only executes when you explicitly clip a page; no tracking or monitoring
- **Scope**: Only runs in the active tab, only when you trigger clipping
- **Alternative**: Without this, web page clipping wouldn't be possible

## Host Permissions (v1.1.0)

### <all_urls> - Required for Web Clipping

**Why Required**: The `<all_urls>` host permission is necessary for the web clipping feature to work on any website you visit.

**Specific Use Cases**:
1. **Page Content Capture**: To clip a web page, the extension must access the page's HTML and CSS
2. **PDF Conversion**: The browser's printToPDF API requires host permissions to convert page content
3. **Dynamic Content**: Ensures clipped pages include all styles and content, regardless of the website

**Security Safeguards**:
- **User-Initiated Only**: Content access only happens when you explicitly click "Clip Page" or "Clip Selection"
- **No Automatic Access**: The extension doesn't monitor or track your browsing
- **Local Processing**: Page content is captured and converted to PDF locally in your browser
- **No Third-Party Transmission**: Content goes only to your configured DocuElevate server
- **Temporary Access**: Content is processed immediately and not stored by the extension

**Alternative Options**:
- **activeTab Only**: If you only want URL sending (not web clipping), the extension could work with just `activeTab` permission
- **Manual Permission**: You could be prompted per-site, but this would be cumbersome for frequent use

**Privacy Guarantee**: Even with `<all_urls>`, the extension:
- Does NOT monitor your browsing
- Does NOT collect page content automatically
- Does NOT track which sites you visit
- Only accesses content when you explicitly clip a page

## Permission Justification

| Permission | Required? | Justification |
|------------|-----------|---------------|
| activeTab | ✅ Yes | Must read current tab URL and content |
| storage | ✅ Yes | Must save configuration to function |
| contextMenus | ⚠️ Optional | Nice to have for quick access |
| notifications | ⚠️ Optional | Nice to have for feedback |
| scripting | ✅ Yes (for clipping) | Required to capture page content for web clipping |
| host_permissions: <all_urls> | ✅ Yes (for clipping) | Required for web clipping to work on any website |

## Security Benefits

1. **User-Initiated Access**: Extension only accesses page content when you explicitly click "Clip"
2. **Local Processing**: Pages converted to PDF in your browser, not on a server
3. **User-Controlled Server**: Extension only talks to your configured DocuElevate server
4. **No Automatic Tracking**: Extension doesn't monitor your browsing or collect data in the background
5. **Transparent Code**: All code is visible in the extension folder for audit

## How Web Clipping Works Securely

1. **You Trigger**: You click "Clip Page" or "Clip Selection"
2. **Content Capture**: Extension captures page HTML (only when you click)
3. **Local Conversion**: Your browser converts HTML to PDF using built-in API
4. **Direct Upload**: PDF is sent only to your configured DocuElevate server
5. **Temporary Tab**: A hidden tab is created temporarily for PDF conversion, then immediately closed

**No data leaves your machine except to your own DocuElevate server.**

## How to Verify Permissions

### Chrome/Edge

1. Go to `chrome://extensions/` or `edge://extensions/`
2. Find "DocuElevate - Send to Document Processor"
3. Click "Details"
4. Review "Permissions" section

### Firefox

1. Go to `about:addons`
2. Find "DocuElevate - Send to Document Processor"
3. Click on the extension name
4. View "Permissions" tab

## Reducing Permissions Further

If you want fewer permissions or don't need web clipping:

1. **Disable Web Clipping**: Use v1.0.0 instead of v1.1.0
   - No scripting permission
   - No host_permissions (<all_urls>)
   - Trade-off: Can only send URLs, not clip pages

2. **Remove contextMenus**: Delete the `contextMenus` permission from `manifest.json`
   - Trade-off: Lose right-click menu options
   - You'd only have the toolbar icon

3. **Remove notifications**: Delete the `notifications` permission
   - Trade-off: No success/error notifications
   - You'd only see status in the popup

## Privacy Statement

The DocuElevate browser extension (v1.1.0):

- ✅ Does NOT collect any personal data
- ✅ Does NOT track your browsing history
- ✅ Does NOT monitor web pages you visit
- ✅ Does NOT send data to third parties
- ✅ Does NOT modify web page content (except when you explicitly clip)
- ✅ Does NOT inject ads or tracking scripts
- ✅ Only accesses page content when you explicitly click "Clip"
- ✅ Only communicates with YOUR configured DocuElevate server
- ✅ Stores configuration locally on your device only
- ✅ Converts pages to PDF locally in your browser

## Questions?

If you have concerns about permissions or privacy, please:

- Review the source code in the `browser-extension` folder
- Open an issue on [GitHub](https://github.com/christianlouis/DocuElevate/issues)
- Check the [Browser Extension Guide](../docs/BrowserExtension.md)
- Use v1.0.0 if you don't need web clipping features

---

Last updated: 2024 (v1.1.0)
