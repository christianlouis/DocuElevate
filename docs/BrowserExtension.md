# Browser Extension Guide

The DocuElevate Browser Extension enables users to send files from their web browser directly to DocuElevate for processing.

## Overview

The browser extension provides a seamless way to process files without manually downloading them first. Users can send file URLs with a single click, and DocuElevate will download and process the files automatically.

## Features

### Core Functionality

- **One-Click File Sending**: Send file URLs from the browser to DocuElevate
- **Context Menu Integration**: Right-click on links or pages to send them
- **Popup Interface**: Simple configuration and file submission UI
- **Status Notifications**: Immediate feedback on submission success or failure

### Security Features

- **Minimal Permissions**: Only requests necessary browser permissions
- **Secure Storage**: Configuration stored locally in browser extension storage
- **Direct Communication**: All requests go directly to your DocuElevate server
- **Session-Based Auth**: Supports DocuElevate authentication via session cookies

### Cross-Browser Support

The extension is compatible with:
- Google Chrome
- Microsoft Edge
- Chromium-based browsers (Brave, Opera, etc.)
- Mozilla Firefox (with minor adjustments)

## Installation

### For End Users

See the [Browser Extension README](../browser-extension/README.md) for detailed installation instructions.

Quick steps:
1. Load the extension from the `browser-extension` folder
2. Configure your DocuElevate server URL
3. Optionally add authentication (session cookie)
4. Start sending files!

### For Administrators

#### Prerequisites

- DocuElevate server running with URL upload API enabled
- Server accessible from users' browsers (not blocked by firewall/CORS)
- Optional: Authentication configured if required

#### Deployment Options

**Option 1: Direct Distribution**
- Share the `browser-extension` folder with users
- Users load it as an unpacked extension

**Option 2: Internal Extension Store**
- Package the extension as a .zip file
- Distribute via internal Chrome Web Store or Firefox Add-ons for Enterprise

**Option 3: Public Store** (requires additional steps)
- Submit to Chrome Web Store
- Submit to Firefox Add-ons

## Configuration

### Extension Settings

Users need to configure two settings:

1. **DocuElevate Server URL** (required)
   - Format: `https://docuelevate.example.com`
   - Must be accessible from user's browser
   - Should not include trailing slashes or API paths

2. **Session Cookie** (optional, if auth enabled)
   - Format: `session=cookie_value_here`
   - Obtained by logging into DocuElevate and copying session cookie
   - Expires when the session expires (users need to update it)

### Server Configuration

No server-side configuration is required. The extension uses the existing URL upload API endpoint:

```
POST /api/process-url
```

Ensure this endpoint is:
- Accessible from users' browsers
- Not blocked by CORS policies (if different domain)
- Properly secured with authentication if needed

## Usage

### Sending Files via Popup

1. Click the DocuElevate extension icon
2. The current page URL is displayed
3. Optionally enter a custom filename
4. Click "Send to DocuElevate"
5. Status message shows success or error

### Sending Files via Context Menu

1. Right-click on any link or the current page
2. Select "Send to DocuElevate"
3. A notification appears with the result

### Supported URLs

The extension can send any URL, but DocuElevate will only process:

**Document URLs**:
- PDFs: `https://example.com/document.pdf`
- Office: `https://example.com/report.docx`
- Spreadsheets: `https://example.com/data.xlsx`
- Text files: `https://example.com/notes.txt`

**Image URLs**:
- `https://example.com/image.jpg`
- `https://example.com/scan.png`
- `https://example.com/diagram.svg`

## How It Works

### Architecture

```
┌─────────────┐         ┌──────────────────┐         ┌──────────────┐
│   Browser   │         │  Browser Ext.    │         │ DocuElevate  │
│     Tab     │────────▶│  (popup.js)      │────────▶│   Server     │
│             │  URL    │                  │  API    │              │
└─────────────┘         └──────────────────┘ Request └──────────────┘
                               │
                               │ Stores config in
                               ▼
                        ┌──────────────────┐
                        │ Browser Storage  │
                        │ (chrome.storage) │
                        └──────────────────┘
```

### Data Flow

1. **User initiates send**: Via popup or context menu
2. **Extension gets current URL**: From active tab
3. **Extension loads config**: Server URL and session cookie from storage
4. **API request sent**: POST to `/api/process-url` with URL and optional filename
5. **DocuElevate processes**:
   - Downloads file from URL
   - Validates file type and size
   - Enqueues for processing (OCR, metadata extraction)
6. **Response returned**: Task ID and status
7. **User notified**: Success or error message displayed

### Security Flow

The extension implements several security measures:

1. **No direct file access**: Extension only sends URLs, not file contents
2. **User-controlled config**: Server URL and auth stored per-user
3. **HTTPS recommended**: Encourages secure communication
4. **Minimal permissions**: Only requests necessary browser APIs
5. **Server-side validation**: DocuElevate validates all URLs (SSRF protection)

## Technical Details

### Extension Structure

**manifest.json**: Extension metadata and configuration
- Manifest v3 format (latest standard)
- Minimal permissions requested
- Compatible with Chrome, Edge, and Firefox

**popup/**: User interface files
- `popup.html`: Extension popup interface
- `popup.css`: Styling with modern UI design
- `popup.js`: Configuration and file sending logic

**scripts/**: Background functionality
- `background.js`: Service worker for context menu and notifications
- `content.js`: Content script for page interaction (minimal)

**icons/**: Extension icons in multiple sizes

### API Integration

The extension communicates with DocuElevate via the URL upload API:

**Request Format**:
```javascript
POST /api/process-url
Content-Type: application/json
Cookie: session=<session_value>  // if auth enabled

{
  "url": "https://example.com/file.pdf",
  "filename": "optional-custom-name.pdf"  // optional
}
```

**Response Format**:
```javascript
{
  "task_id": "abc-123-def",
  "status": "queued",
  "message": "File downloaded from URL and queued for processing",
  "filename": "file.pdf",
  "size": 1024
}
```

**Error Response**:
```javascript
{
  "detail": "Error message explaining what went wrong"
}
```

### Browser Permissions

The extension requests these permissions:

- **activeTab**: Get URL of current tab
- **storage**: Save configuration (server URL, session cookie)
- **contextMenus**: Add "Send to DocuElevate" to right-click menu
- **notifications**: Show success/error notifications

All permissions are used only for stated purposes. No data is collected or transmitted to third parties.

## Troubleshooting

### Common Issues

**"Failed to connect to DocuElevate server"**
- Check server URL is correct and accessible
- Verify server is running
- Check firewall/network settings
- Test API directly: `curl https://your-server/api/process-url`

**"Authentication required" (401 error)**
- User needs to add session cookie
- Session may have expired (log in again)
- Check AUTH_ENABLED setting in DocuElevate

**"Unsupported file type" (400 error)**
- URL must point to a supported file type
- Check file extension and Content-Type header
- See DocuElevate supported file types

**"File too large" (413 error)**
- File exceeds MAX_UPLOAD_SIZE setting
- Contact admin to increase limit or use smaller file

**Extension not appearing**
- Ensure developer mode is enabled
- Reload the extension
- Check browser console for errors

### Debug Mode

To debug the extension:

1. **Open Extension Console**:
   - Chrome: Right-click extension icon → "Inspect popup"
   - Or go to `chrome://extensions/` → Click "Inspect views: service worker"

2. **Check Console Logs**:
   - Look for error messages
   - Verify API requests are being sent
   - Check response status codes

3. **Test API Directly**:
   ```bash
   curl -X POST https://your-server/api/process-url \
     -H "Content-Type: application/json" \
     -H "Cookie: session=your_session" \
     -d '{"url": "https://example.com/test.pdf"}'
   ```

## Best Practices

### For Users

- Keep your session cookie secure and don't share it
- Verify the DocuElevate server URL is correct before saving
- Only send files from trusted sources
- Check file size limits before sending large files

### For Administrators

- Configure HTTPS for production servers
- Set appropriate MAX_UPLOAD_SIZE limits
- Enable authentication for security
- Monitor API usage and set rate limits if needed
- Provide clear documentation to users on getting session cookies

## Future Enhancements

Possible future improvements:

- **OAuth2 authentication** instead of session cookies
  - Current session cookie approach has limitations:
    - Session cookies expire and need manual refresh
    - Users must manually copy cookie from browser DevTools
    - No automatic token refresh mechanism
  - OAuth2 would provide:
    - Automatic token refresh
    - Better security with short-lived access tokens
    - Easier user experience (login flow instead of cookie copying)
- File preview before sending
- Batch processing multiple URLs
- Progress indication for large files
- History of sent files
- Custom processing options (OCR language, metadata fields, etc.)

### Session Cookie Security Best Practices

For users of the current implementation:

1. **Keep session cookies secure**: Never share your session cookie value
2. **Refresh regularly**: Session cookies expire; update the extension when you log in again
3. **Use HTTPS**: Always use HTTPS for your DocuElevate server
4. **Clear on logout**: Remove the session cookie from extension when logging out
5. **Private browsing**: Session cookies from private/incognito windows have shorter lifetimes

## Related Documentation

- [DocuElevate API Documentation](./API.md)
- [DocuElevate Configuration Guide](./ConfigurationGuide.md)
- [DocuElevate Security Guide](../SECURITY_AUDIT.md)
- [Browser Extension README](../browser-extension/README.md)

## Support

For issues or questions:
- Check the troubleshooting section above
- Review the [main documentation](./README.md)
- Open an issue on [GitHub](https://github.com/christianlouis/DocuElevate/issues)
