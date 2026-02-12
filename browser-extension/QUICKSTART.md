# Browser Extension - Quick Start Guide

This guide will help you quickly install and configure the DocuElevate browser extension.

## 5-Minute Installation

### Step 1: Load the Extension

**For Chrome/Edge/Chromium browsers:**

1. Open your browser and navigate to:
   - Chrome: `chrome://extensions/`
   - Edge: `edge://extensions/`
   - Other Chromium: Similar URL for your browser

2. Enable **Developer mode** (toggle in top right corner)

3. Click **"Load unpacked"** button

4. Select the `browser-extension` folder from your DocuElevate installation

5. The DocuElevate icon should now appear in your browser toolbar

**For Firefox:**

1. Navigate to `about:debugging#/runtime/this-firefox`

2. Click **"Load Temporary Add-on..."**

3. Select the `manifest.json` file from the `browser-extension` folder

4. The extension will load (note: temporary, removed when Firefox restarts)

### Step 2: Configure Your Server

1. Click the DocuElevate extension icon in your toolbar

2. Enter your DocuElevate server URL:
   ```
   https://your-docuelevate-server.com
   ```
   Or for local testing:
   ```
   http://localhost:8000
   ```

3. Click **"Save Configuration"**

### Step 3: (Optional) Add Authentication

If your DocuElevate server requires authentication:

1. Log in to your DocuElevate server in a regular browser tab

2. Open Developer Tools (F12)

3. Go to **Application** → **Cookies** (Chrome/Edge) or **Storage** → **Cookies** (Firefox)

4. Find the cookie named `session`

5. Copy its **Value**

6. In the extension popup, click **"Change Settings"**

7. Paste the value in the **Session Cookie** field:
   ```
   session=your_copied_session_value
   ```

8. Click **"Save Configuration"**

### Step 4: Send Your First File

1. Navigate to any page with a document URL, for example:
   - `https://example.com/document.pdf`
   - `https://example.com/image.jpg`
   - Any direct link to a supported file

2. Click the DocuElevate extension icon

3. (Optional) Enter a custom filename

4. Click **"Send to DocuElevate"**

5. Wait for the success message!

## Quick Tips

- **Right-click shortcut**: Right-click on any link and select "Send to DocuElevate"
- **Notifications**: You'll get browser notifications for success/error
- **Change settings**: Click "Change Settings" in the extension popup anytime
- **Supported files**: PDF, Office docs, images - see full list in README

## Troubleshooting

**"Failed to connect to server"**
- Check your server URL is correct
- Make sure DocuElevate is running
- Verify network/firewall settings

**"Authentication required"**
- Add your session cookie (see Step 3)
- Your session may have expired - log in again

**"Unsupported file type"**
- URL must point to a document or image file
- Check that the URL has a file extension (.pdf, .docx, etc.)

## Next Steps

- Read the full [Browser Extension Guide](../docs/BrowserExtension.md) for detailed information
- Configure file processing settings in DocuElevate
- Set up storage destinations (Dropbox, Google Drive, etc.)

## Need Help?

- Check the [Browser Extension Guide](../docs/BrowserExtension.md) for detailed troubleshooting
- Review the [API Documentation](../docs/API.md)
- See the main [Troubleshooting Guide](../docs/Troubleshooting.md) for general issues
- Open an issue on [GitHub](https://github.com/christianlouis/DocuElevate/issues)

---

Happy document processing! 🚀
