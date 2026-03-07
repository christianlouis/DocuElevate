# How to Scan Documents from Your Phone or Tablet

DocuElevate works seamlessly with mobile scanning apps. This guide covers the best ways to capture documents with your phone or tablet and get them into DocuElevate automatically.

---

## Option 1: DocuElevate Web Upload (Simplest)

The easiest way is to use DocuElevate's built-in web interface directly from your mobile browser.

1. Open your phone's browser and navigate to your DocuElevate instance (e.g., `http://your-docuelevate-host:8000`).
2. Tap **Upload** in the top navigation.
3. Tap **Choose File** — your phone will open the camera or file picker.
4. Select **Camera** to capture a photo of the document, or pick an existing file.
5. Tap **Upload** — DocuElevate will process the image and convert it to a searchable PDF.

> **Tip:** Use good lighting and hold the phone steady for better OCR quality.

---

## Option 2: DocuElevate Browser Extension

The **DocuElevate Browser Extension** for Chrome/Firefox allows one-tap uploading from your mobile browser.

See the [Browser Extension guide](../BrowserExtension.md) for installation and setup instructions.

---

## Option 3: Mobile Scanning Apps

These apps provide superior document capture (auto perspective correction, multi-page, etc.) and can send directly to DocuElevate.

### Microsoft Lens (iOS / Android)

Microsoft Lens is free and integrates with OneDrive, which DocuElevate supports natively.

1. Install **Microsoft Lens** from the App Store or Google Play.
2. Scan your document.
3. Save to **OneDrive** in a folder you've connected to DocuElevate.
4. DocuElevate will automatically process new files in your OneDrive folder.

### Adobe Scan (iOS / Android)

Adobe Scan produces high-quality searchable PDFs.

1. Install **Adobe Scan** from the App Store or Google Play.
2. Scan your document.
3. Tap **Share** → **Save to Files** (iOS) or **Share** (Android).
4. Choose to save to your connected cloud storage (Dropbox, Google Drive) monitored by DocuElevate.

**Or use email ingestion:**
1. Tap **Share** → **Email**.
2. Send to your DocuElevate ingestion email address.
3. See [Email Ingestion Setup](./EmailIngestion.md) for configuration.

### SwiftScan (iOS)

SwiftScan (formerly Scanbot) offers excellent auto-capture and document enhancement.

1. Install **SwiftScan** from the App Store.
2. Scan your document.
3. Configure the **Auto-Upload** feature:
   - Go to **Settings** → **Cloud Services**.
   - Connect Dropbox, Google Drive, or OneDrive.
   - Set the upload folder to your DocuElevate-monitored folder.
4. Every scan is automatically uploaded and processed by DocuElevate.

### CamScanner (iOS / Android)

1. Install **CamScanner**.
2. Configure **Auto Backup** to Dropbox or Google Drive.
3. Point DocuElevate at the same cloud folder.

---

## Option 4: iOS Shortcuts Automation

On iPhone/iPad, you can create an **iOS Shortcut** that scans a document and uploads it directly to DocuElevate's API.

### Creating the Shortcut

1. Open the **Shortcuts** app on your iPhone.
2. Tap **+** to create a new shortcut.
3. Add the following actions:
   - **Scan Document** — opens the camera for scanning
   - **Get Contents of URL** — configures the API call:
     - **URL:** `http://your-docuelevate-host:8000/api/upload`
     - **Method:** POST
     - **Headers:** `Authorization: Bearer YOUR_API_KEY`
     - **Request Body:** Form data with `file` = Scanned Document
4. Name the shortcut "Send to DocuElevate".
5. Add it to your home screen for one-tap scanning.

```
Shortcut flow:
┌─────────────┐    ┌──────────────┐    ┌──────────────────────┐
│ Scan Document│ → │ Select pages │ → │ POST to DocuElevate  │
│  (Camera)   │    │    & crop    │    │     /api/upload      │
└─────────────┘    └──────────────┘    └──────────────────────┘
```

---

## Option 5: Android Automation with Tasker

On Android, **Tasker** can automate document upload when files appear in a specific folder.

1. Install **Tasker** from Google Play.
2. Create a **Profile** triggered by **File Created** in your scanner app's output folder.
3. Add a **Task** that calls DocuElevate's upload API using the **HTTP Request** action.

---

## Recommended Mobile Scanning Settings

For best results with DocuElevate's OCR engine:

| Setting | Recommended Value |
|---------|------------------|
| Output Format | PDF |
| Resolution/Quality | High (equivalent to 300 DPI) |
| Color Mode | Auto (greyscale for text, color for mixed) |
| Perspective Correction | On (auto-straighten) |
| Filter | Document / Black & White for text |
| Multi-page | Combine into single PDF |

---

## Troubleshooting

**Upload fails from mobile browser?**  
→ Check that DocuElevate is accessible from your phone's network (same WiFi, or publicly reachable).  
→ Verify your session is still logged in.

**OCR quality is poor?**  
→ Ensure good lighting, no shadows on the document.  
→ Use your scanning app's auto-enhance or document filter.  
→ Increase resolution to "High" or "Best" in the app settings.

**Files synced to cloud but not processed?**  
→ Check DocuElevate's cloud storage connection in Settings.  
→ View worker logs: `docker logs document_worker --tail 50`

---

## Related Documentation

- [Email Ingestion Setup](./EmailIngestion.md)
- [HP Enterprise Printer Setup](./HPPrinterSetup.md)
- [ScanSnap Setup](./SnapScanSetup.md)
- [Browser Extension](../BrowserExtension.md)
- [API Reference](../API.md)
