# How to Set Up Automatic Document Ingestion with an HP Enterprise Printer

This guide explains how to configure an HP Enterprise printer/MFP (Multi-Function Printer) to automatically send scanned documents to DocuElevate for processing and storage.

---

## Prerequisites

- An HP Enterprise printer or MFP with **Scan to Email** or **Scan to Network Folder** capability
- DocuElevate running and accessible on your network
- Admin access to the HP printer's Embedded Web Server (EWS)
- (Optional) An SMTP server or a configured email address for Scan to Email

---

## Option A: Scan to Email → DocuElevate API Upload

HP Enterprise printers can send scanned documents as email attachments. You can set up a dedicated inbox that forwards documents to DocuElevate via the REST API.

### Step 1: Configure Scan to Email on the Printer

1. Open a browser and navigate to the printer's IP address (e.g., `http://192.168.1.100`) to access the **Embedded Web Server (EWS)**.
2. Go to **Scan** → **Scan to E-mail**.
3. Enable **Scan to E-mail** and configure your SMTP server settings.
4. Create a **Quick Set** (shortcut) for the destination:
   - **From:** `scanner@yourdomain.com`
   - **To:** `docuelevate-inbox@yourdomain.com` (the receiving address you'll configure)
   - **File Type:** PDF
   - **Resolution:** 200–300 DPI (recommended)
   - **Color Mode:** Grayscale or Black & White for text documents

### Step 2: Set Up an Email-to-DocuElevate Bridge

Use a lightweight tool like [imapfilter](https://github.com/lefcha/imapfilter) or a simple Python script (see below) to poll the inbox and upload attachments to DocuElevate via its REST API.

**Example Python script (`email_to_docuelevate.py`):**

```python
import imaplib
import email
import os
import sys

import requests

IMAP_HOST = "mail.yourdomain.com"
IMAP_USER = "docuelevate-inbox@yourdomain.com"
# Use an app-specific password (Gmail/Outlook), NOT your main account password.
# Store credentials as environment variables – never hardcode them.
IMAP_PASS = os.environ.get("IMAP_PASS")
DOCUELEVATE_URL = "http://your-docuelevate-host:8000"
API_KEY = os.environ.get("DOCUELEVATE_API_KEY")

if not IMAP_PASS:
    sys.exit("Error: IMAP_PASS environment variable is not set.")
if not API_KEY:
    sys.exit("Error: DOCUELEVATE_API_KEY environment variable is not set.")


def fetch_and_upload():
    mail = imaplib.IMAP4_SSL(IMAP_HOST)
    mail.login(IMAP_USER, IMAP_PASS)
    mail.select("INBOX")

    _, msg_ids = mail.search(None, "UNSEEN")
    for msg_id in msg_ids[0].split():
        _, msg_data = mail.fetch(msg_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])

        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue
            filename = part.get_filename()
            if filename and filename.lower().endswith(".pdf"):
                payload = part.get_payload(decode=True)
                files = {"file": (filename, payload, "application/pdf")}
                headers = {"Authorization": f"Bearer {API_KEY}"}
                resp = requests.post(
                    f"{DOCUELEVATE_URL}/api/upload",
                    files=files,
                    headers=headers
                )
                print(f"Uploaded {filename}: {resp.status_code}")
        mail.store(msg_id, "+FLAGS", "\\Seen")

    mail.logout()

if __name__ == "__main__":
    fetch_and_upload()
```

Run this script via a cron job every few minutes:

```bash
*/5 * * * * /usr/bin/python3 /opt/email_to_docuelevate.py >> /var/log/docuelevate_import.log 2>&1
```

---

## Option B: Scan to Network Folder (SMB/CIFS)

HP Enterprise printers can scan directly to a network folder. You can configure a watched folder that DocuElevate monitors for new files.

### Step 1: Set Up a Shared Network Folder

On your DocuElevate server (or any reachable server), create a shared folder:

```bash
# Create the shared folder
mkdir -p /srv/scanner-inbox

# Create a dedicated Samba user for the printer
sudo useradd -M -s /sbin/nologin scanner
sudo smbpasswd -a scanner   # set a password for the printer to authenticate with

# Install Samba
sudo apt-get install samba

# Add to /etc/samba/smb.conf:
[scanner-inbox]
  path = /srv/scanner-inbox
  writable = yes
  guest ok = no
  valid users = scanner
  create mask = 0660
  directory mask = 0770
```

> **Security note:** Use a dedicated user (`scanner`) with a strong password instead of `guest ok = yes`. This prevents unauthorised devices on your network from depositing files.

Restart Samba: `sudo systemctl restart smbd`

### Step 2: Configure the HP Printer for Scan to Network Folder

1. Open the printer's **Embedded Web Server (EWS)**.
2. Go to **Scan** → **Scan to Network Folder**.
3. Click **Add** to create a new Quick Set:
   - **UNC Path:** `\\192.168.1.200\scanner-inbox` (replace with your server's IP)
   - **Username:** `scanner` (the Samba user created above)
   - **Password:** the password set with `smbpasswd`
   - **File Type:** PDF (Searchable PDF if available)
   - **Resolution:** 200–300 DPI
4. Test the connection from the EWS interface.

### Step 3: Configure DocuElevate to Watch the Folder

In your DocuElevate `.env` configuration:

```env
# Enable folder watching
WATCH_FOLDER_ENABLED=true
WATCH_FOLDER_PATH=/srv/scanner-inbox
WATCH_FOLDER_INTERVAL=30  # seconds between checks
```

DocuElevate's Celery worker will automatically detect and process new files placed in the watched folder.

---

## Option C: Scan to FTP/WebDAV

DocuElevate supports FTP and WebDAV as upload targets. HP printers can send scanned documents directly.

### WebDAV Configuration

1. In the EWS, go to **Scan** → **Save to SharePoint** or **Save to Network Folder**.
2. Some HP models support WebDAV directly — configure the WebDAV URL to point to DocuElevate's WebDAV endpoint (if enabled):
   - **URL:** `http://your-docuelevate-host:8000/webdav/inbox/`
   - **Username/Password:** Your DocuElevate credentials

### FTP Configuration

1. Ensure an FTP server is running alongside DocuElevate (or configure one in docker-compose).
2. In the EWS, configure **Scan to FTP**:
   - **FTP Server:** `192.168.1.200`
   - **Port:** `21`
   - **Remote Path:** `/scanner-inbox/`
3. DocuElevate's watch folder will pick up the FTP-delivered files.

---

## Recommended Scanner Quick Set Settings

| Setting | Recommended Value |
|---------|------------------|
| File Type | PDF (Searchable PDF / PDF/A if available) |
| Resolution | 200–300 DPI |
| Color Mode | Auto Detect or Grayscale |
| Sides | Auto Detect (2-sided) |
| Original Size | Auto Detect |
| Orientation | Auto Detect |

---

## Troubleshooting

**Printer can't connect to the network folder?**  
→ Verify the IP address and that the Samba/SMB service is running. Check firewall rules (port 445/TCP).

**Scanned PDFs aren't being processed?**  
→ Check DocuElevate's Celery worker logs: `docker logs document_worker --follow`

**Email attachments not arriving?**  
→ Verify SMTP settings on the printer. Check spam filters on the receiving mailbox.

**Poor OCR quality?**  
→ Increase scan resolution to 300 DPI and use Grayscale mode for text documents.

---

## Related Documentation

- [DocuElevate Configuration Guide](../ConfigurationGuide.md)
- [Storage Architecture](../StorageArchitecture.md)
- [Troubleshooting](../Troubleshooting.md)
