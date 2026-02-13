# Document Storage Architecture

## Overview

DocuElevate implements a robust document storage architecture that maintains immutable originals, processed copies, and comprehensive traceability throughout the document lifecycle.

## Storage Structure

### Directory Layout

```
workdir/
├── original/          # Immutable original files (never modified)
│   ├── <uuid>.pdf
│   ├── <uuid>-0001.pdf
│   └── ...
├── tmp/               # Temporary processing area
│   ├── <uuid>.pdf
│   └── ...
└── processed/         # Final processed files with metadata
    ├── 2024-01-01_Invoice.pdf
    ├── 2024-01-01_Invoice.json
    ├── 2024-01-15_Contract-0001.pdf
    └── ...
```

### Directory Purposes

#### `/workdir/original`
- **Purpose**: Immutable storage of files as they were first ingested
- **When Created**: When a new file is uploaded or processed
- **Naming**: UUID-based to prevent collisions (e.g., `a1b2c3d4-e5f6.pdf`)
- **Immutability**: Files in this directory are never modified or deleted
- **Database Reference**: `FileRecord.original_file_path`

#### `/workdir/tmp`
- **Purpose**: Temporary working directory for document processing
- **When Created**: During processing pipeline
- **Lifecycle**: Files are copied here during processing and may be deleted after successful completion
- **Database Reference**: `FileRecord.local_filename`

#### `/workdir/processed`
- **Purpose**: Final processed files with embedded metadata
- **When Created**: After successful metadata extraction and embedding
- **Naming**: Human-readable names from metadata (e.g., `2024-01-01_Invoice.pdf`)
- **Collision Handling**: Automatic `-0001`, `-0002` suffix when names collide
- **Database Reference**: `FileRecord.processed_file_path`
- **Companion Files**: Each PDF has a corresponding `.json` file with metadata

## Collision Handling

### Naming Strategy

When a file name collision occurs in the `processed` directory, DocuElevate automatically appends a zero-padded numeric suffix:

```
2024-01-01_Invoice.pdf        # First file
2024-01-01_Invoice-0001.pdf   # First collision
2024-01-01_Invoice-0002.pdf   # Second collision
2024-01-01_Invoice-0003.pdf   # Third collision
...
2024-01-01_Invoice-9999.pdf   # Max numeric suffix
```

### Features
- **Zero-padded**: Always uses 4-digit format (`-0001`, not `-1`)
- **Automatic**: No user intervention required
- **Deterministic**: Same base name always gets next available number
- **Scalable**: Supports up to 10,000 variations of the same filename

### Implementation

The collision handling is implemented in `app/utils/filename_utils.py`:

```python
from app.utils import get_unique_filepath_with_counter

# Get unique path with automatic collision handling
unique_path = get_unique_filepath_with_counter(
    directory="/workdir/processed",
    base_filename="2024-01-01_Invoice",
    extension=".pdf"
)
# Returns: "/workdir/processed/2024-01-01_Invoice.pdf" (or -0001, -0002, etc.)
```

## Document Lifecycle

### 1. Initial Upload

```
User uploads document.pdf
    ↓
Saved to /workdir/<uuid>.pdf
    ↓
File hash computed (SHA-256)
    ↓
Database record created
```

### 2. Processing Pipeline

```
Original saved to /workdir/original/<uuid>.pdf
    ↓
Working copy to /workdir/tmp/<uuid>.pdf
    ↓
Text extraction (local or Cloud OCR)
    ↓
Metadata extraction (GPT)
    ↓
Metadata embedding into PDF
    ↓
Move to /workdir/processed/<filename>.pdf
    ↓
Save metadata JSON
    ↓
Queue for upload to destinations
    ↓
Cleanup /workdir/tmp/<uuid>.pdf
```

### 3. Reprocessing

When reprocessing an existing file:

```
User triggers reprocess (file_id provided)
    ↓
Retrieve existing FileRecord
    ↓
Use original_file_path (immutable original)
    ↓
Skip saving new original (already exists)
    ↓
Continue with processing pipeline
    ↓
New processed file may get -0001 suffix
```

## Metadata JSON Structure

Each processed PDF has a companion JSON file with the same base name:

**File**: `/workdir/processed/2024-01-01_Invoice.json`

```json
{
  "filename": "2024-01-01_Invoice",
  "document_type": "Invoice",
  "absender": "ACME Corp",
  "empfaenger": "John Doe",
  "tags": ["finance", "2024", "Q1"],
  "language": "en",
  "confidence_score": 95,
  "original_file_path": "/workdir/original/a1b2c3d4-e5f6.pdf",
  "processed_file_path": "/workdir/processed/2024-01-01_Invoice.pdf"
}
```

### Metadata Fields

#### Core Metadata (from GPT extraction)
- `filename`: Suggested filename from metadata
- `document_type`: Classification (Invoice, Contract, etc.)
- `absender`: Sender
- `empfaenger`: Recipient
- `tags`: Thematic keywords
- `language`: ISO 639-1 language code
- `confidence_score`: Extraction confidence (0-100)

#### File Path References (added by DocuElevate)
- `original_file_path`: Path to immutable original
- `processed_file_path`: Path to processed file with metadata

## Forced Cloud OCR

### Use Cases

Force Cloud OCR reprocessing when:
1. PDF has poor quality embedded text
2. OCR accuracy is insufficient
3. Embedded text is corrupted or garbled
4. Higher quality extraction is needed

### API Endpoint

```bash
POST /api/files/{file_id}/reprocess-with-cloud-ocr
```

### Behavior

1. Bypasses local text extraction
2. Always uses Azure Document Intelligence OCR
3. Processes from `original_file_path` if available
4. Creates new processed file (may get collision suffix)
5. Updates database with new `processed_file_path`

### Example

```bash
curl -X POST "http://localhost:8000/api/files/123/reprocess-with-cloud-ocr" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response**:
```json
{
  "status": "success",
  "message": "File queued for Cloud OCR reprocessing",
  "file_id": 123,
  "filename": "invoice.pdf",
  "task_id": "task-uuid",
  "force_cloud_ocr": true
}
```

## Database Schema

### FileRecord Model

```python
class FileRecord(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True)
    filehash = Column(String, unique=True, nullable=False)
    original_filename = Column(String)           # User's original name
    local_filename = Column(String)              # /workdir/tmp/<uuid>.pdf
    original_file_path = Column(String)          # /workdir/original/<uuid>.pdf
    processed_file_path = Column(String)         # /workdir/processed/<name>.pdf
    file_size = Column(Integer)
    mime_type = Column(String)
    created_at = Column(DateTime)
```

## File Operations Safety

### Immutability Guarantees

1. **Original Directory**: Files are never modified or deleted
2. **Processed Directory**: Files are never modified after creation
3. **Path Validation**: All file operations use path validation to prevent traversal
4. **Database Integrity**: File paths are stored in database for traceability

### Cleanup Policy

- **Original**: Never deleted (permanent archive)
- **Tmp**: Deleted after successful processing
- **Processed**: Kept until explicitly deleted by user or retention policy

## Benefits

### Traceability
- Every file has a permanent, unmodified original
- Complete processing history tracked in database
- Metadata JSON provides audit trail

### Flexibility
- Reprocessing uses original for best quality
- Forced Cloud OCR option for quality improvements
- Multiple processed versions can coexist

### Reliability
- Collision handling prevents file overwrites
- Immutable originals enable recovery
- Database references ensure consistency

## Migration

For existing installations, the new fields are added via database migration:

```bash
# Migration creates nullable columns
alembic upgrade head

# Existing files will have NULL for new paths
# Future processing will populate these fields
```

### Backfilling

To populate file paths for existing records:

```python
from app.models import FileRecord
from app.database import SessionLocal

with SessionLocal() as db:
    for record in db.query(FileRecord).filter(
        FileRecord.original_file_path.is_(None)
    ):
        # Logic to backfill based on local_filename if needed
        pass
```

## See Also

- [API Documentation](API.md) - API endpoints for file operations
- [User Guide](UserGuide.md) - User-facing documentation
- [Configuration Guide](ConfigurationGuide.md) - Storage configuration options
