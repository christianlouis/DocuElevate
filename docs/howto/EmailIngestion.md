# How to Set Up Automatic Document Ingestion via Email

Many devices (scanners, printers, fax services, and apps) can send documents as email attachments. This guide explains how to automatically route those attachments into DocuElevate.

---

## Overview

The Email Ingestion workflow works like this:

```
Scanner/Device → Email (SMTP) → Monitored Mailbox → DocuElevate API → Processing & Storage
```

DocuElevate periodically checks a designated email inbox, downloads PDF/image attachments, and processes them through the standard document pipeline.

---

## Prerequisites

- An email account dedicated to document ingestion (e.g., `scan@yourdomain.com`)
- IMAP access enabled for that account
- DocuElevate running with the Celery worker active

---

## Configuration

Add the following to your DocuElevate `.env` file:

```env
# Email ingestion settings
EMAIL_INGESTION_ENABLED=true
EMAIL_INGESTION_IMAP_HOST=mail.yourdomain.com
EMAIL_INGESTION_IMAP_PORT=993
EMAIL_INGESTION_IMAP_SSL=true
EMAIL_INGESTION_USERNAME=scan@yourdomain.com
EMAIL_INGESTION_PASSWORD=your-email-password
EMAIL_INGESTION_FOLDER=INBOX
EMAIL_INGESTION_INTERVAL=60           # Check every 60 seconds
EMAIL_INGESTION_MARK_SEEN=true        # Mark emails as read after processing
EMAIL_INGESTION_ALLOWED_SENDERS=      # Comma-separated allowlist (empty = allow all)
```

Restart DocuElevate after saving the configuration:

```bash
docker compose restart api worker
```

---

## Supported File Types

DocuElevate will process the following attachment types from emails:

| Type | Extension | Notes |
|------|-----------|-------|
| PDF | `.pdf` | Native support; OCR applied if not searchable |
| JPEG/PNG | `.jpg`, `.jpeg`, `.png` | Converted to PDF before processing |
| TIFF | `.tif`, `.tiff` | Common format from older scanners/fax |
| Multi-page TIFF | `.tif` | Full multi-page support |

---

## Setting Up Your Scanner/Device

### HP Printers – Scan to Email

See the detailed guide: [HP Enterprise Printer Setup](./HPPrinterSetup.md#option-a-scan-to-email--docuelevate-api-upload)

### Fujitsu ScanSnap – Send by Email

See the detailed guide: [ScanSnap Setup](./SnapScanSetup.md#method-3-scan-to-email--docuelevate)

### iOS/Android Scanning Apps

Most mobile scanning apps (Adobe Scan, Microsoft Lens, SwiftScan) can email scans:

1. Scan your document.
2. Use the app's **Share** or **Send** function.
3. Select **Email** and enter `scan@yourdomain.com`.
4. DocuElevate will pick up the attachment within the configured interval.

### Fax-to-Email Services

Services like eFax, RingCentral Fax, or Twilio Fax can forward incoming faxes as email attachments. Configure them to send to `scan@yourdomain.com`.

---

## Security Considerations

> **Important:** Only process emails from trusted sources to avoid ingesting malicious documents.

Use the `EMAIL_INGESTION_ALLOWED_SENDERS` setting to restrict which email addresses can submit documents:

```env
EMAIL_INGESTION_ALLOWED_SENDERS=scanner@office.com,printer@office.com,fax@office.com
```

DocuElevate will silently skip emails from addresses not in the allowlist.

Additionally:

- Use a **dedicated email account** solely for document ingestion
- Enable **app-specific passwords** (Gmail, Outlook) instead of your main account password
- Store credentials in environment variables, never in config files committed to version control

---

## Monitoring

Check the DocuElevate worker logs to verify email ingestion is running:

```bash
docker logs document_worker --follow
```

You should see log entries like:

```
INFO  Email ingestion: checking inbox scan@yourdomain.com
INFO  Email ingestion: found 3 new messages
INFO  Email ingestion: processing attachment invoice-2024.pdf from printer@office.com
INFO  Email ingestion: queued document ID 142 for processing
```

---

## Troubleshooting

**No emails are being processed?**
→ Verify IMAP credentials and that IMAP is enabled on your mail server.  
→ Check firewall rules: port 993 (SSL) or 143 (plain) must be open from DocuElevate to the mail server.

**Gmail not working?**
→ Enable "App Passwords" in your Google Account security settings.  
→ Use the App Password (not your main Google password) for `EMAIL_INGESTION_PASSWORD`.

**Attachments processed but files are empty?**
→ Some email clients send inline images instead of attachments. Check the raw email source.

**Emails keep getting re-processed?**
→ Set `EMAIL_INGESTION_MARK_SEEN=true` to mark emails as read after processing.  
→ Alternatively, configure a separate ingestion folder and move/delete emails after processing.

---

## Related Documentation

- [HP Enterprise Printer Setup](./HPPrinterSetup.md)
- [ScanSnap Setup](./SnapScanSetup.md)
- [Configuration Guide](../ConfigurationGuide.md)
- [Notifications Setup](../NotificationsSetup.md)
