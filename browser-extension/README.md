# DocuElevate Browser Extension

Clip web pages and send files from your browser directly to DocuElevate for processing with a single click.

## Features

- **Web Page Clipping**: Clip full pages or selected content as PDF documents
- **One-Click File Sending**: Send file URLs from your browser to DocuElevate
- **Context Menu Integration**: Right-click on links or pages to send or clip them
- **Dual Mode Interface**: Toggle between "Send URL" and "Clip Page" modes
- **PDF Conversion**: Automatically converts clipped pages to PDF format
- **Secure Configuration**: Store your DocuElevate server URL and authentication in the extension
- **Cross-Browser Support**: Compatible with Chrome, Firefox, Edge, and other Chromium-based browsers
- **Minimal Permissions**: Only requests necessary permissions for functionality
- **Status Feedback**: Get immediate feedback on file submission success or errors

## Installation

### Chrome / Edge / Chromium-based Browsers

1. **Download the Extension**:
   - Download or clone the DocuElevate repository
   - Navigate to the `browser-extension` folder

2. **Load the Extension**:
   - Open your browser and go to the extensions page:
     - Chrome: `chrome://extensions/`
     - Edge: `edge://extensions/`
   - Enable "Developer mode" (toggle in the top right)
   - Click "Load unpacked"
   - Select the `browser-extension` folder

3. **Configure the Extension**:
   - Click the DocuElevate icon in your browser toolbar
   - Enter your DocuElevate server URL (e.g., `https://docuelevate.example.com`)
   - If authentication is enabled, enter your session cookie (optional)
   - Click "Save Configuration"

### Firefox

1. **Download the Extension**:
   - Download or clone the DocuElevate repository
   - Navigate to the `browser-extension` folder

2. **Load the Extension Temporarily**:
   - Open Firefox and go to `about:debugging#/runtime/this-firefox`
   - Click "Load Temporary Add-on"
   - Select the `manifest.json` file in the `browser-extension` folder

3. **Configure the Extension**:
   - Click the DocuElevate icon in your browser toolbar
   - Enter your DocuElevate server URL
   - If authentication is enabled, enter your session cookie (optional)
   - Click "Save Configuration"

**Note**: For permanent installation in Firefox, you'll need to sign the extension through Mozilla's add-on portal. Firefox supports the same Chrome API for PDF conversion (tabs.printToPDF).

## Usage

### Method 1: Extension Popup (Send URL Mode)

1. Navigate to a page with a file URL (e.g., a PDF, DOCX, image)
2. Click the DocuElevate extension icon
3. Select "Send URL" mode (default)
4. Optionally, enter a custom filename
5. Click "Send to DocuElevate"
6. Wait for confirmation that the file was sent

### Method 2: Extension Popup (Clip Page Mode)

1. Navigate to any web page you want to clip
2. Click the DocuElevate extension icon
3. Select "Clip Page" mode
4. Choose either:
   - **Clip Full Page**: Captures the entire page content
   - **Clip Selection**: Captures only the selected text/content (select text first)
5. Optionally, enter a custom filename
6. The page will be converted to PDF and sent to DocuElevate

### Method 3: Context Menu - Send URL

1. Right-click on a link or the current page
2. Select "Send URL to DocuElevate" from the context menu
3. A notification will confirm the file was sent or show an error

### Method 4: Context Menu - Clip Page

1. Right-click on any page
2. Select "Clip Full Page to DocuElevate" from the context menu
3. The entire page will be clipped as PDF and sent

### Method 5: Context Menu - Clip Selection

1. Select text or content on the page
2. Right-click on the selection
3. Select "Clip Selection to DocuElevate" from the context menu
4. Only the selected content will be clipped as PDF and sent

## Configuration

### Server URL

The DocuElevate server URL should point to your DocuElevate instance:
- Format: `https://your-domain.com` or `http://localhost:8000`
- Do not include trailing slashes or API paths
- For URL mode: Extension appends `/api/process-url`
- For clip mode: Extension appends `/api/files/upload`

### Session Cookie (Optional)

If your DocuElevate instance has authentication enabled, you need to provide a session cookie:

1. **Get Your Session Cookie**:
   - Log in to DocuElevate in your browser
   - Open browser DevTools (F12)
   - Go to the "Application" or "Storage" tab
   - Find "Cookies" in the left sidebar
   - Look for a cookie named `session`
   - Copy its value

2. **Enter in Extension**:
   - Format: `session=your_session_value_here`
   - The extension will include this in API requests

**Security Note**: Your session cookie is stored securely in the browser's extension storage. Never share your session cookie with others.

## Supported Content

### URL Mode
The extension can send any URL, but DocuElevate will only process supported file types:
- **Documents**: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, CSV, RTF
- **Images**: JPG, PNG, GIF, BMP, TIFF, WebP, SVG

### Clip Mode
Any web page can be clipped. The extension will:
- Capture HTML content with styles
- Convert to PDF format using browser's print API
- Upload to DocuElevate for processing

## Troubleshooting

### "Failed to connect to DocuElevate server"

**Cause**: The extension cannot reach your DocuElevate server.

**Solutions**:
- Verify your server URL is correct
- Check that your DocuElevate server is running
- Ensure there are no firewall or CORS issues
- Try accessing the API directly: `https://your-server.com/api/process-url`

### "Authentication required" or 401 Error

**Cause**: Your DocuElevate instance requires authentication.

**Solutions**:
- Get your session cookie (see Configuration section)
- Enter the session cookie in the extension settings
- Ensure your session hasn't expired (log in again if needed)

### "No content selected" (Clip Selection)

**Cause**: No text or content is selected on the page.

**Solution**:
- Select text or content on the page before clicking "Clip Selection"
- Use "Clip Full Page" to capture the entire page without selection

### "Failed to convert to PDF"

**Cause**: The browser's PDF conversion API failed.

**Solutions**:
- Ensure you're using a modern version of Chrome/Edge/Firefox
- Check browser console for detailed error messages
- Try clipping a simpler page to test
- Ensure the page has finished loading

### "Unsupported file type" (URL Mode)

**Cause**: The URL doesn't point to a supported file type.

**Solution**:
- Verify the URL ends with a supported file extension
- Check that the Content-Type header is set correctly by the server
- Use "Clip Page" mode instead to capture web content

### "File too large"

**Cause**: The file/PDF exceeds the maximum upload size configured in DocuElevate.

**Solutions**:
- Check your DocuElevate `MAX_UPLOAD_SIZE` configuration
- Try a smaller file or clip a smaller selection
- Contact your DocuElevate administrator to increase the limit

## Privacy & Security

### Permissions Explained

The extension requests minimal permissions:

- **activeTab**: To get the URL and content of the current tab
- **storage**: To save your server URL and session cookie configuration
- **contextMenus**: To add context menu options for sending/clipping
- **notifications**: To show success/error notifications
- **scripting**: To inject content capture code into web pages
- **host_permissions**: To access page content for clipping (restricted to active tab)

### Data Handling

- **No Data Collection**: The extension does not collect, store, or transmit any data except what you explicitly send to your DocuElevate server
- **Local Configuration**: Your server URL and session cookie are stored locally in your browser
- **Direct Communication**: All API requests go directly from your browser to your DocuElevate server
- **No Third Parties**: No data is sent to third-party services
- **Page Content**: When clipping, page HTML is captured temporarily in memory and converted to PDF locally in your browser before upload

## Development

### Building from Source

The extension is already in a usable state in the `browser-extension` folder. No build process is required.

### File Structure

```
browser-extension/
├── manifest.json           # Extension manifest (Chrome/Firefox compatible)
├── icons/                  # Extension icons
│   ├── icon16.png
│   ├── icon32.png
│   ├── icon48.png
│   └── icon128.png
├── popup/                  # Extension popup UI
│   ├── popup.html          # Popup interface with mode toggle
│   ├── popup.css           # Styling for popup
│   └── popup.js            # Popup logic for URL and clip modes
└── scripts/                # Background and content scripts
    ├── background.js       # Service worker with PDF conversion
    ├── content.js          # Content script for page capture
    └── capture.js          # Utility functions for web clipping
```

### Testing

1. Load the extension in developer mode
2. Configure it with your local DocuElevate instance
3. Test with various file URLs
4. Check the browser console for any errors
5. Verify files are being processed in DocuElevate

## API Endpoint

The extension uses the DocuElevate URL upload API:

**Endpoint**: `POST /api/process-url`

**Request Body**:
```json
{
  "url": "https://example.com/document.pdf",
  "filename": "optional-custom-name.pdf"
}
```

**Response**:
```json
{
  "task_id": "abc123",
  "status": "queued",
  "message": "File downloaded from URL and queued for processing",
  "filename": "document.pdf",
  "size": 1024
}
```

See the [DocuElevate API Documentation](../docs/API.md) for more details.

## License

This extension is part of the DocuElevate project and is licensed under the same terms as the main project.

## Support

For issues, questions, or feature requests:
- Open an issue on the [DocuElevate GitHub repository](https://github.com/christianlouis/DocuElevate/issues)
- Refer to the main [DocuElevate documentation](../docs/)

## Version History

### 1.1.0 (Current)
- **Web Page Clipping**: Clip full pages or selected content as PDF
- **Dual Mode Interface**: Toggle between "Send URL" and "Clip Page" modes
- **PDF Conversion**: Browser-based PDF generation using printToPDF API
- **Enhanced Context Menus**: Separate options for URL sending and page clipping
- **Selection Clipping**: Clip only selected text/content from pages
- Cross-browser compatibility (Chrome, Firefox, Edge)

### 1.0.0
- Initial release
- Basic URL sending functionality
- Configuration management
- Context menu integration
- Notifications support
