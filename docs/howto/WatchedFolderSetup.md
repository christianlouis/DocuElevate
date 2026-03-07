# How to Set Up a Watched Folder for Automatic Document Ingestion

The **Watched Folder** feature allows DocuElevate to automatically detect and process documents placed in a specific local directory. Any scanner, application, or script that saves files to that folder will have its output automatically ingested.

---

## Overview

```
Scanner / Any App → Drop files in folder → DocuElevate watches for new files → Process & Store
```

This is one of the simplest ingestion methods and works with virtually any scanner, OCR app, or document workflow tool.

---

## Configuration

Add these settings to your `.env` file:

```env
WATCH_FOLDER_ENABLED=true
WATCH_FOLDER_PATH=/srv/docuelevate/watch
WATCH_FOLDER_INTERVAL=30           # Polling interval in seconds
WATCH_FOLDER_RECURSIVE=false       # Watch subdirectories too
WATCH_FOLDER_DELETE_AFTER=true     # Delete originals after successful processing
WATCH_FOLDER_EXTENSIONS=pdf,jpg,jpeg,png,tiff,tif
```

**Restart** the services after editing:

```bash
docker compose restart api worker
```

---

## Docker Setup

When running DocuElevate with Docker Compose, mount the watch folder into both the `api` and `worker` containers:

```yaml
# docker-compose.yaml
services:
  api:
    volumes:
      - /srv/docuelevate/watch:/srv/docuelevate/watch
      - /var/docparse/workdir:/workdir

  worker:
    volumes:
      - /srv/docuelevate/watch:/srv/docuelevate/watch
      - /var/docparse/workdir:/workdir
```

Create the folder and set permissions:

```bash
sudo mkdir -p /srv/docuelevate/watch
sudo chmod 777 /srv/docuelevate/watch
```

---

## Multiple Watch Folders

If you have multiple scanners or document sources, you can organize them by subfolder:

```
/srv/docuelevate/watch/
├── reception/         ← Front desk scanner
├── accounting/        ← Finance team scanner
├── hr/                ← HR department
└── general/           ← General purpose
```

Enable recursive watching:

```env
WATCH_FOLDER_RECURSIVE=true
```

DocuElevate will monitor all subdirectories and tag documents with the subfolder name for easy filtering.

---

## Using with Network Scanners

### Windows / Samba Share

Share the watch folder over the network so scanners and Windows PCs can drop files directly:

```bash
# Install Samba
sudo apt-get install samba -y

# Add to /etc/samba/smb.conf
[DocuElevate-Inbox]
  comment = DocuElevate Document Inbox
  path = /srv/docuelevate/watch
  browsable = yes
  guest ok = yes
  read only = no
  create mask = 0777
  directory mask = 0777
```

Restart Samba:
```bash
sudo systemctl restart smbd nmbd
```

Windows access: `\\your-server-ip\DocuElevate-Inbox`

### NFS Share (Linux)

```bash
# Add to /etc/exports
/srv/docuelevate/watch  192.168.1.0/24(rw,sync,no_subtree_check)

# Apply changes
sudo exportfs -ra
```

### FTP Server (for older devices)

Many older scanners only support FTP. Run a simple FTP server alongside DocuElevate:

```yaml
# Add to docker-compose.yaml
services:
  ftp:
    image: garethflowers/ftp-server
    container_name: docuelevate_ftp
    environment:
      - FTP_USER=scanner
      - FTP_PASS=changeme
    ports:
      - "21:21"
      - "20:20"
      - "21100-21110:21100-21110"
    volumes:
      - /srv/docuelevate/watch:/home/scanner
```

Configure your scanner's FTP settings to use this server. Files will land in the watched folder.

---

## Supported File Types

| Format | Extension | Notes |
|--------|-----------|-------|
| PDF | `.pdf` | OCR applied if not already searchable |
| JPEG | `.jpg`, `.jpeg` | Converted to PDF |
| PNG | `.png` | Converted to PDF |
| TIFF | `.tif`, `.tiff` | Supports multi-page TIFF |
| HEIC | `.heic` | iPhone photos (converted) |

---

## Monitoring

Check that the watched folder is active:

```bash
# View worker logs
docker logs document_worker --follow

# Expected output:
# INFO  Watch folder monitor: watching /srv/docuelevate/watch (interval: 30s)
# INFO  Watch folder: found new file invoice.pdf
# INFO  Watch folder: queued document ID 156 for processing
```

You can also view processing status in the DocuElevate web interface under **Queue Monitor**.

---

## Troubleshooting

**Files are dropped but not picked up?**
- Verify `WATCH_FOLDER_ENABLED=true` in `.env`
- Check that `WATCH_FOLDER_PATH` matches the mounted path in docker-compose
- Look at worker logs: `docker logs document_worker --tail 100`

**Permission denied errors?**
```bash
# Fix permissions
sudo chmod -R 777 /srv/docuelevate/watch
# Or use ACLs for more granular control
sudo setfacl -m u:nobody:rwx /srv/docuelevate/watch
```

**Files processed but not deleted?**
- Set `WATCH_FOLDER_DELETE_AFTER=true`
- If you want to keep originals, set to `false` and manage cleanup separately

**File appears partially uploaded?**
- Large files may arrive before the scanner finishes writing them
- Increase `WATCH_FOLDER_INTERVAL` to give time for files to be fully written
- DocuElevate uses file-lock detection to avoid processing incomplete files

---

## Related Documentation

- [HP Enterprise Printer Setup](./HPPrinterSetup.md)
- [ScanSnap Setup](./SnapScanSetup.md)
- [Email Ingestion](./EmailIngestion.md)
- [Configuration Guide](../ConfigurationGuide.md)
- [Deployment Guide](../DeploymentGuide.md)
