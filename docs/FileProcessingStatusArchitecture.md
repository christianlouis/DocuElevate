# File Processing Status Architecture

## Overview

DocuElevate now uses a **dual-table architecture** for tracking file processing:

1. **`FileProcessingStep`** - Current state tracking (NEW)
2. **`ProcessingLog`** - Historical audit trail (EXISTING, PRESERVED)

This separation provides both **fast status queries** and **complete audit history**.

## Architecture

### FileProcessingStep Table (Current State)

**Purpose**: Definitive source of truth for current processing status

**Structure**:
```sql
CREATE TABLE file_processing_steps (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL,
    step_name VARCHAR NOT NULL,
    status VARCHAR NOT NULL,  -- 'pending', 'in_progress', 'success', 'failure', 'skipped'
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (file_id, step_name)
)
```

**Key Features**:
- One row per step per file
- Updated when step status changes
- No scanning required - direct lookups
- Indexed for fast queries

### ProcessingLog Table (Audit Trail)

**Purpose**: Complete historical record of all processing events

**Structure**: (Unchanged from original)
```sql
CREATE TABLE processing_logs (
    id INTEGER PRIMARY KEY,
    file_id INTEGER,
    task_id VARCHAR,
    step_name VARCHAR,
    status VARCHAR,
    message VARCHAR,
    detail TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
)
```

**Key Features**:
- Multiple rows per step (one per event)
- Never deleted - complete history
- Used for debugging, compliance, audit
- Detailed error messages and diagnostics

## How They Work Together

### When a File is Created

```python
from app.utils.step_manager import initialize_file_steps

# Create file record
file_record = FileRecord(...)
db.add(file_record)
db.commit()

# Initialize expected processing steps
initialize_file_steps(db, file_record.id)
# Creates FileProcessingStep rows with status='pending'
```

### When a Worker Processes a Step

```python
from app.utils.step_manager import update_step_status

# Worker starts processing
update_step_status(
    db, file_id, "hash_file", "in_progress",
    started_at=datetime.now()
)

# Worker also logs to ProcessingLog (for history)
log = ProcessingLog(
    file_id=file_id,
    step_name="hash_file",
    status="in_progress",
    message="Starting file hash calculation"
)
db.add(log)
db.commit()

# Worker completes successfully
update_step_status(
    db, file_id, "hash_file", "success",
    completed_at=datetime.now()
)

# Also log completion
log = ProcessingLog(
    file_id=file_id,
    step_name="hash_file",
    status="success",
    message="Hash calculated successfully: abc123..."
)
db.add(log)
db.commit()
```

### When Dashboard Queries Status

```python
from app.utils.step_manager import get_file_overall_status, get_step_summary

# Fast lookup - no log scanning!
overall = get_file_overall_status(db, file_id)
# Returns: {"status": "processing", "has_errors": False, ...}

# Get detailed step breakdown
summary = get_step_summary(db, file_id)
# Returns: {
#   "main": {"success": 3, "in_progress": 1, "pending": 4},
#   "uploads": {"success": 2, "queued": 4}
# }
```

### When Viewing Processing History

```python
# Logs provide complete timeline
logs = db.query(ProcessingLog)\
    .filter(ProcessingLog.file_id == file_id)\
    .order_by(ProcessingLog.timestamp.asc())\
    .all()

# Shows every event with timestamps, messages, details
# Example:
# 2024-01-15 10:00:00 | hash_file | in_progress | Starting...
# 2024-01-15 10:00:05 | hash_file | success | Hash: abc123
# 2024-01-15 10:00:06 | check_text | in_progress | Checking...
# ... etc
```

## Migration from Logs

For existing files with only ProcessingLog entries:

```python
from app.utils.migrate_logs_to_steps import migrate_logs_to_steps, migrate_all_files

# Migrate single file
result = migrate_logs_to_steps(db, file_id)
# Parses logs chronologically to reconstruct final state

# Migrate all files (batch processing)
summary = migrate_all_files(db, batch_size=100)
# Finds files with logs but no steps, migrates them all

# Dry run mode (test without committing)
result = migrate_logs_to_steps(db, file_id, dry_run=True)
```

The migration utility:
1. Reads all logs for a file in chronological order
2. Tracks state transitions (pending → in_progress → success/failure)
3. Determines final status per step
4. Creates FileProcessingStep entries
5. Preserves all original logs unchanged

## Benefits

### Performance
- **Old**: Scan all logs, dedupe, find latest → O(n log n)
- **New**: Single table lookup → O(1)

### Correctness
- **Old**: Dependent on log ordering, can miss retries
- **New**: Definitive state, always up-to-date

### Flexibility
- **Old**: Hard-coded step list, can't add dynamic steps
- **New**: Dynamic upload destinations, custom workflows

### Debugging
- **Old**: Only logs available
- **New**: Current state + complete history

## Example Workflow

```python
# 1. File uploaded
file = FileRecord(filehash="abc123", ...)
db.add(file)
db.commit()

# 2. Initialize steps
initialize_file_steps(db, file.id)
# FileProcessingStep: 9 rows with status='pending'

# 3. Add upload destinations (discovered later)
add_upload_steps(db, file.id, ["dropbox", "s3", "nextcloud"])
# FileProcessingStep: +6 rows with status='pending'

# 4. Worker processes each step
for step in ["hash_file", "create_file_record", "check_text", ...]:
    # Start
    update_step_status(db, file.id, step, "in_progress", started_at=now())
    log_event(db, file.id, step, "in_progress", "Starting...")

    # Do work...

    # Complete
    update_step_status(db, file.id, step, "success", completed_at=now())
    log_event(db, file.id, step, "success", "Completed successfully")

# 5. Dashboard queries
status = get_file_overall_status(db, file.id)
# status="completed", all steps done

# 6. User views history
logs = get_processing_logs(db, file.id)
# Complete timeline with all events, messages, timestamps
```

## Status Flow

```
pending → in_progress → success
                     ↓
                   failure
```

## Main Processing Steps

Defined in `app/utils/step_manager.py`:
```python
MAIN_PROCESSING_STEPS = [
    "hash_file",
    "create_file_record",
    "check_text",
    "extract_text",
    "extract_metadata_with_gpt",
    "embed_metadata_into_pdf",
    "finalize_document_storage",
    "send_to_all_destinations",
]
```

## Upload Steps

Dynamically created per destination:
- `queue_{destination}` - Queued for upload
- `upload_to_{destination}` - Actual upload

Example: Dropbox
- `queue_dropbox` - Added to upload queue
- `upload_to_dropbox` - Upload to Dropbox

## API Reference

### Step Manager Functions

```python
# Initialize steps for new file
initialize_file_steps(db: Session, file_id: int) -> None

# Add upload destination steps
add_upload_steps(db: Session, file_id: int, destinations: List[str]) -> None

# Update step status
update_step_status(
    db: Session,
    file_id: int,
    step_name: str,
    status: str,
    error_message: Optional[str] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None
) -> None

# Query step status
get_file_step_status(db: Session, file_id: int) -> Dict[str, Dict]
get_file_overall_status(db: Session, file_id: int) -> Dict
get_step_summary(db: Session, file_id: int) -> Dict
```

### Migration Functions

```python
# Migrate single file
migrate_logs_to_steps(
    db: Session,
    file_id: int,
    dry_run: bool = False
) -> Dict

# Migrate all files
migrate_all_files(
    db: Session,
    batch_size: int = 100,
    dry_run: bool = False
) -> Dict

# Verify migration
verify_migration(db: Session, file_id: int) -> Dict
```

## Best Practices

1. **Always log AND update status**: Workers should do both
2. **Logs are append-only**: Never delete or modify logs
3. **Status is current state**: FileProcessingStep reflects latest status
4. **Initialize early**: Create steps when file is created
5. **Add uploads dynamically**: Add upload steps when destinations are known
6. **Handle retries**: update_step_status() handles overwriting previous status
7. **Preserve history**: Use logs for debugging and compliance

## Troubleshooting

### Status shows wrong state
- Check FileProcessingStep table directly
- Use `get_file_step_status()` to see all steps
- Verify workers are calling `update_step_status()`

### Missing steps
- Check if `initialize_file_steps()` was called
- For uploads, check if `add_upload_steps()` was called
- Use migration utility to backfill from logs

### Dashboard shows old data
- Clear any caching
- Verify status table is being queried, not logs
- Check `app/views/files.py` is using `get_step_summary_from_table()`

## Migration Checklist

For deploying to existing system:

- [ ] Apply database migration: `alembic upgrade head`
- [ ] Run migration utility: `migrate_all_files(db, dry_run=True)` to test
- [ ] Run actual migration: `migrate_all_files(db, dry_run=False)`
- [ ] Verify: Check a few files with `verify_migration()`
- [ ] Update workers to call `update_step_status()`
- [ ] Update file creation to call `initialize_file_steps()`
- [ ] Monitor dashboard for correct status display
