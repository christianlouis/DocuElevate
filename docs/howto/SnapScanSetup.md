# How to Set Up Fujitsu ScanSnap to Automatically Send Documents to DocuElevate

This guide walks you through configuring a Fujitsu ScanSnap scanner to automatically upload scanned documents to DocuElevate for AI-powered processing and storage.

---

## Supported ScanSnap Models

This guide applies to the following ScanSnap models:

- **iX1600 / iX1500 / iX1400** – Wi-Fi and USB, ScanSnap Home software
- **iX500 / iX100** – USB/Wi-Fi, ScanSnap Manager software
- **S1300i / S1100i** – USB, ScanSnap Manager software

> **Note:** ScanSnap Home (for newer models) and ScanSnap Manager (for older models) differ in their profile/job configuration interface. Both methods are covered below.

---

## Method 1: Scan to Folder → DocuElevate Watched Folder

This is the simplest method and works with all ScanSnap models.

### Step 1: Configure DocuElevate's Watched Folder

Add the following to your DocuElevate `.env` file and restart the service:

```env
WATCH_FOLDER_ENABLED=true
WATCH_FOLDER_PATH=/srv/scan-inbox
WATCH_FOLDER_INTERVAL=10
```

Create the directory and set permissions:

```bash
mkdir -p /srv/scan-inbox
chmod 777 /srv/scan-inbox
```

If running DocuElevate in Docker, mount this folder into the container in your `docker-compose.yaml`:

```yaml
services:
  api:
    volumes:
      - /srv/scan-inbox:/srv/scan-inbox
  worker:
    volumes:
      - /srv/scan-inbox:/srv/scan-inbox
```

### Step 2: Configure ScanSnap Home (iX1600/iX1500/iX1400)

1. Open **ScanSnap Home** on your computer.
2. Click **+** to create a new profile.
3. Select **Save to folder** as the action.
4. Configure the profile:
   - **Folder:** `/srv/scan-inbox` (or a local folder that syncs to it)
   - **File format:** PDF
   - **Image quality:** Normal or Better
   - **Color mode:** Auto
   - **Scanning side:** Both sides (auto)
5. Enable **Convert to searchable PDF** if your ScanSnap and ScanSnap Home version support it.
6. Name the profile "DocuElevate" and save.

Now, pressing the scan button while this profile is active will send the scanned PDF directly to the watched folder.

### Step 3: Configure ScanSnap Manager (older models)

1. Right-click the ScanSnap Manager icon in the system tray.
2. Select **Scan Button Settings**.
3. Choose the **Save** tab.
4. Set **Image saving folder** to `/srv/scan-inbox` (or use a shared network path).
5. Under **File format**, select **PDF**.
6. Click **OK** to save.

---

## Method 2: Scan to Cloud Storage → DocuElevate Sync

If you already use Dropbox, Google Drive, or OneDrive with ScanSnap, you can leverage those integrations to feed documents into DocuElevate.

### Using Dropbox

1. In ScanSnap Home, create a profile with action **Save to Dropbox**.
2. Set the destination folder to `ScanSnap/` (or any folder).
3. In DocuElevate settings, configure Dropbox as your storage provider and point DocuElevate to monitor/pull from that folder.
4. DocuElevate will process new documents as they appear in Dropbox.

### Using Google Drive

1. Create a ScanSnap profile that saves to **Google Drive** under a dedicated folder (e.g., `ScanSnap/Inbox`).
2. Configure DocuElevate's Google Drive integration to use that folder as a source/destination.

---

## Method 3: Scan to Email → DocuElevate

ScanSnap can send scanned documents as email attachments. Pair this with the email-to-DocuElevate bridge described in the [HP Printer Guide](./HPPrinterSetup.md#option-a-scan-to-email--docuelevate-api-upload) for automatic ingestion.

1. In ScanSnap Home, create a profile with action **Send by E-mail**.
2. Configure the recipient address as your DocuElevate-monitored mailbox.
3. Set file format to **PDF**.
4. The email bridge script will pick up the attachment and upload it to DocuElevate.

---

## Method 4: ScanSnap Cloud (iX1600 / ScanSnap Home 3.x+)

The ScanSnap iX1600 supports **ScanSnap Cloud**, which can send directly to cloud services.

1. Open the **ScanSnap Home** app or use the printer's touchscreen.
2. Configure a **ScanSnap Cloud** profile that saves to **Google Drive** or **Dropbox**.
3. Point DocuElevate to monitor that cloud folder.

---

## Recommended Scan Settings

| Setting | Recommended Value |
|---------|------------------|
| File Format | PDF (Searchable PDF if available) |
| Image Quality | Normal (200 DPI) for text, Better (300 DPI) for photos |
| Color Mode | Auto (detects black/white vs color) |
| Scanning Side | Both Sides (Auto) |
| Compression | Medium |
| Rotate | Auto |
| Remove blank pages | Yes |
| Correct skewed scans | Yes |

---

## Automating with ScanSnap Home Profiles

You can create multiple profiles in ScanSnap Home for different document types:

| Profile | Settings | Notes |
|---------|----------|-------|
| **Documents** | B&W, 200 DPI, PDF | For invoices, letters, contracts |
| **Photos** | Color, 300 DPI, PDF | For photo documents |
| **Receipts** | B&W, 200 DPI, PDF, Remove blank pages | For expense reports |
| **Business Cards** | Color, 300 DPI, JPEG | May require separate OCR |

Each profile can be assigned to the scanner's shortcut button (on models with a touchscreen).

---

## Setting Up One-Button Scanning

On the **ScanSnap iX1600** with its touchscreen:

1. Tap the profile name (e.g., "DocuElevate") on the scanner's display.
2. The scanner will use that profile for the next scan.
3. Press the physical **Scan** button.
4. The document is scanned and automatically delivered to DocuElevate's watched folder.

On models without a touchscreen:

1. Set the "DocuElevate" profile as the **default profile** in ScanSnap Manager/Home.
2. Press the **Scan** button — the document goes directly to DocuElevate.

---

## Troubleshooting

**Files appear in the folder but DocuElevate doesn't process them?**  
→ Check that `WATCH_FOLDER_ENABLED=true` in your `.env` and that the worker can read the folder:
```bash
docker logs document_worker --tail 50
```

**ScanSnap can't find the network folder?**  
→ Ensure the folder is shared over SMB/CIFS (Windows share). See the [HP Printer Setup guide](./HPPrinterSetup.md#step-1-set-up-a-shared-network-folder) for Samba configuration.

**Scanned PDFs have poor text recognition?**  
→ Increase scan resolution to 300 DPI. Enable "Convert to searchable PDF" in ScanSnap Home if available.

**Files are processed twice (duplicates)?**  
→ Enable duplicate detection in DocuElevate settings. Check [Troubleshooting](../Troubleshooting.md) for deduplication options.

**ScanSnap doesn't appear in ScanSnap Home after network change?**  
→ Re-run the ScanSnap network setup wizard. Ensure the scanner and your computer are on the same Wi-Fi network/subnet.

---

## Related Documentation

- [HP Enterprise Printer Setup](./HPPrinterSetup.md)
- [DocuElevate Configuration Guide](../ConfigurationGuide.md)
- [Dropbox Setup](../DropboxSetup.md)
- [Google Drive Setup](../GoogleDriveSetup.md)
- [Troubleshooting](../Troubleshooting.md)
