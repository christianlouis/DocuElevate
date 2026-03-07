# How-To Guides

Welcome to the DocuElevate How-To Guides. These step-by-step articles help you connect common scanners, printers, and mobile devices to DocuElevate for automatic document ingestion and processing.

---

## Document Ingestion Guides

Choose the method that matches your hardware or workflow:

### 🖨️ Scanners & Printers

| Guide | Description |
|-------|-------------|
| [HP Enterprise Printer Setup](howto/HPPrinterSetup.md) | Configure HP MFPs for automatic scan-to-DocuElevate via email, network folder, or WebDAV |
| [Fujitsu ScanSnap Setup](howto/SnapScanSetup.md) | Set up ScanSnap iX1600/iX1500/iX500 to send scans directly to DocuElevate |
| [Watched Folder Setup](howto/WatchedFolderSetup.md) | Monitor a local or network folder and automatically ingest any files dropped into it |

### 📧 Email & Cloud

| Guide | Description |
|-------|-------------|
| [Email Ingestion](howto/EmailIngestion.md) | Route documents sent as email attachments into DocuElevate automatically |
| [Mobile Scanning](howto/MobileScanning.md) | Use iOS/Android apps to capture and upload documents from your phone |

---

## Quick Comparison: Which Method Is Right for You?

| Method | Best For | Setup Complexity |
|--------|----------|-----------------|
| **Web Upload** | Occasional one-off uploads | ⭐ Very Easy |
| **Watched Folder** | Any scanner that saves to a folder | ⭐⭐ Easy |
| **Email Ingestion** | Scanners with Scan-to-Email, fax services | ⭐⭐ Easy |
| **HP Printer (SMB)** | HP Enterprise MFPs on a corporate network | ⭐⭐⭐ Medium |
| **ScanSnap + Cloud** | Home/office ScanSnap via Dropbox/Drive | ⭐⭐ Easy |
| **Mobile App** | On-the-go document capture | ⭐ Very Easy |
| **API Integration** | Custom workflows, developer integrations | ⭐⭐⭐⭐ Advanced |

---

## General Configuration Tips

### Enable OCR for Searchable PDFs

DocuElevate applies OCR (Optical Character Recognition) to scanned documents, making them fully searchable. Configure the OCR engine in your `.env`:

```env
OCR_ENABLED=true
OCR_ENGINE=tesseract          # or: azure, google
OCR_LANGUAGE=eng              # ISO 639-2 language code
```

### Set Up Automatic Cloud Backup

After processing, DocuElevate can store documents in your preferred cloud storage. Configure in Settings or `.env`:

```env
DEFAULT_STORAGE_TARGET=dropbox   # or: gdrive, onedrive, s3, nextcloud
```

### Configure Notifications

Get notified when documents are processed:

```env
NOTIFICATION_ENABLED=true
NOTIFICATION_EMAIL=you@example.com
```

See [Notifications Setup](NotificationsSetup.md) for webhook, Slack, and other integrations.

---

## Need Help?

- Browse the full [Documentation](UserGuide.md)
- Check [Troubleshooting](Troubleshooting.md) for common issues
- View [Configuration Reference](ConfigurationGuide.md) for all settings
- Explore the [API Reference](API.md) for programmatic access
