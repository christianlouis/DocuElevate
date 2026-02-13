# File Detail Page - Technical Reference

## API Endpoints

```
GET /files/{id}/detail                → Main detail page (template view)
GET /files/{id}/preview/original      → Serve original PDF file
GET /files/{id}/preview/processed     → Serve processed PDF file
GET /files/{id}/text/original         → Extract text from original PDF (on-demand)
GET /files/{id}/text/processed        → Extract text from processed PDF (on-demand)
POST /api/files/{id}/retry            → Retry full processing
POST /api/files/{id}/retry-subtask    → Retry specific task
```

## Text Extraction

Text extraction is performed **on-demand** when the user clicks "View Extracted Text":
- Uses pypdf to extract text from PDF files in real-time
- Returns JSON: `{"text": "...", "page_count": 3}`
- Client-side caching prevents re-extraction on subsequent views
- Loading indicator shown during extraction
- Graceful error handling if extraction fails

## Template Context Variables

| Variable | Type | Description |
|----------|------|-------------|
| `file` | FileRecord | Database record with file metadata |
| `gpt_metadata` | dict | Extracted metadata from JSON file (or None) |
| `extracted_text` | str | Text content from OCR/extraction (or None) |
| `original_file_exists` | bool | True if original file exists on disk |
| `processed_file_exists` | bool | True if processed file exists on disk |
| `logs` | List[ProcessingLog] | Processing history records |
| `step_summary` | dict | Aggregated processing status counts |
| `flow_data` | dict | Processing flow visualization data |

## File System Structure

```
workdir/
├── tmp/
│   └── {uuid}.pdf                    ← Temporary ingestion file
├── original/
│   └── {uuid}.pdf                    ← Immutable original copy (original_file_path)
└── processed/
    ├── 2024-01-15_Invoice.pdf        ← Processed with metadata (processed_file_path)
    └── 2024-01-15_Invoice.json       ← GPT metadata JSON
```

## Metadata JSON Schema

Stored as `{processed_file_path_without_extension}.json`:

```json
{
  "document_type": "Invoice",
  "filename": "2024-01-15_Company_Invoice",
  "date": "2024-01-15",
  "absender": "Test Company GmbH",
  "empfaenger": "Customer Inc",
  "betrag": "€ 1,234.56",
  "kontonummer": "DE89370400440532013000",
  "tags": ["invoice", "payment", "2024"],
  "original_file_path": "/workdir/original/{uuid}.pdf",
  "processed_file_path": "/workdir/processed/2024-01-15_Invoice.pdf"
}
```

## JavaScript Functions

```javascript
toggleMetadata()               // Show/hide JSON metadata view
toggleTextModal(modalId)       // Open/close text extraction modals
window.onclick                 // Close modal when clicking outside
```

## Database Schema

```sql
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    filehash TEXT NOT NULL,
    original_filename TEXT,
    local_filename TEXT NOT NULL,
    original_file_path TEXT,       -- Points to workdir/original/
    processed_file_path TEXT,      -- Points to workdir/processed/
    file_size INTEGER,
    mime_type TEXT,
    created_at DATETIME
);

CREATE TABLE processing_logs (
    id INTEGER PRIMARY KEY,
    file_id INTEGER,
    task_id TEXT,
    step_name TEXT,                -- e.g., "extract_text", "process_with_azure_document_intelligence"
    status TEXT,                   -- "pending", "in_progress", "success", "failure"
    message TEXT,
    detail TEXT,                   -- May contain extracted text
    timestamp DATETIME
);
```

## Processing Stages

Text extraction logs to check for `extracted_text`:
- `extract_text` - Local PDF text extraction
- `process_with_azure_document_intelligence` - Azure OCR processing

Both may contain extracted text in the `detail` field when `status = 'success'`.
