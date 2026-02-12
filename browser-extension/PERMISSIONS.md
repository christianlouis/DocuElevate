# Browser Extension Permissions

This document explains the permissions requested by the DocuElevate browser extension.

## Requested Permissions

The extension requests the following permissions in `manifest.json`:

### activeTab
- **Purpose**: Get the URL of the currently active tab
- **Usage**: When you click the extension icon, it reads the current tab's URL to display in the popup
- **Privacy**: Only accesses the active tab when you explicitly open the popup
- **Alternative**: Without this, the extension couldn't show you which file you're sending

### storage
- **Purpose**: Save your configuration (server URL and session cookie)
- **Usage**: Stores your DocuElevate server URL and optional session cookie locally
- **Privacy**: All data stays on your device; nothing is sent to third parties
- **Alternative**: Without this, you'd need to reconfigure the extension every time

### contextMenus
- **Purpose**: Add "Send to DocuElevate" to the right-click menu
- **Usage**: Creates a context menu item for quick access
- **Privacy**: No data access; only adds a menu item
- **Alternative**: Without this, you'd only have the toolbar icon

### notifications
- **Purpose**: Show success/error notifications
- **Usage**: Displays browser notifications when files are sent successfully or errors occur
- **Privacy**: Only shows notifications based on your actions
- **Alternative**: Without this, you wouldn't get feedback from context menu actions

## No Host Permissions

The extension has an **empty `host_permissions` array** (`[]`).

### Why Empty?

- **Privacy-First**: The extension doesn't request blanket access to all websites
- **User-Controlled**: You configure the DocuElevate server URL, not us
- **Minimal Permissions**: Only accesses the server you explicitly configure
- **Dynamic Access**: API requests are made from popup/background scripts, not from web pages

### How It Works

1. You configure your DocuElevate server URL in the extension
2. The extension stores this URL in local storage
3. When you send a file, the extension makes a direct API request to your configured server
4. No need for static host permissions because the extension doesn't inject scripts or modify web pages

### Comparison to Other Extensions

Many similar extensions request:
- ❌ `"<all_urls>"` or `"*://*/*"` - Access to all websites
- ❌ `"http://*/*"` and `"https://*/*"` - Access to all HTTP/HTTPS sites

DocuElevate requests:
- ✅ `[]` - No blanket host permissions
- ✅ Only access to your configured server (via fetch API)

## Permission Justification

| Permission | Required? | Justification |
|------------|-----------|---------------|
| activeTab | ✅ Yes | Must read current tab URL to send files |
| storage | ✅ Yes | Must save configuration to function |
| contextMenus | ⚠️ Optional | Nice to have for quick access |
| notifications | ⚠️ Optional | Nice to have for feedback |

## Security Benefits

1. **No Web Page Access**: Extension can't read or modify content on websites you visit
2. **No Browsing History**: Extension doesn't track your browsing
3. **No Cross-Site Access**: Extension only talks to your configured server
4. **User-Controlled**: All communication is initiated by you
5. **Transparent**: All code is visible in the extension folder

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

If you want even fewer permissions:

1. **Remove contextMenus**: Delete the `contextMenus` permission from `manifest.json`
   - Trade-off: Lose right-click menu option
   - You'd only have the toolbar icon

2. **Remove notifications**: Delete the `notifications` permission
   - Trade-off: No success/error notifications
   - You'd only see status in the popup

3. **Remove content script**: Delete the `content_scripts` section
   - Trade-off: None (it's not actively used currently)
   - Reduces extension footprint slightly

## Privacy Statement

The DocuElevate browser extension:

- ✅ Does NOT collect any personal data
- ✅ Does NOT track your browsing history
- ✅ Does NOT send data to third parties
- ✅ Does NOT modify web page content
- ✅ Does NOT inject ads or tracking scripts
- ✅ Only communicates with YOUR configured DocuElevate server
- ✅ Stores configuration locally on your device only

## Questions?

If you have concerns about permissions or privacy, please:

- Review the source code in the `browser-extension` folder
- Open an issue on [GitHub](https://github.com/christianlouis/DocuElevate/issues)
- Check the [Browser Extension Guide](../docs/BrowserExtension.md)

---

Last updated: 2024
