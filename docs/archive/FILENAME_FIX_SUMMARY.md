# Fix for Issue: Uploaded files do not maintain original file name

## Problem Summary
Users reported that files uploaded through the UI were being renamed to UUIDs during processing, making it impossible to recognize the original files. For example, a file originally named "Apostille Sverige.pdf" would appear as "e64b2825-9ff2-486b-aff1-08af2957140b.pdf" in the file detail view.

## Root Cause
The issue occurred because:
1. In `app/api/files.py`, the `ui_upload` endpoint saves uploaded files with UUID-based filenames for security (to prevent path traversal and filename conflicts)
2. This UUID-based path is passed to the `process_document` task
3. The `process_document` task extracts the filename from the path using `os.path.basename()`, which returns the UUID-based name
4. This UUID-based name is then stored in the database as the `original_filename`

## Solution Implemented

### Changes Made

#### 1. Modified `app/tasks/process_document.py`
- Added optional `original_filename` parameter to the `process_document` function
- When provided, uses the passed filename instead of extracting from path
- Falls back to `os.path.basename()` when parameter is not provided (backward compatibility)

```python
def process_document(self, original_local_file: str, original_filename: str = None):
    # ...
    if original_filename is None:
        original_filename = os.path.basename(original_local_file)
```

#### 2. Modified `app/tasks/convert_to_pdf.py`
- Added optional `original_filename` parameter to the `convert_to_pdf` function
- Passes through the original filename to `process_document` after conversion
- Adjusts file extension to .pdf when passing to the next stage

```python
def convert_to_pdf(self, file_path, original_filename=None):
    # ...
    if original_filename:
        original_base = os.path.splitext(original_filename)[0]
        pdf_original_filename = f"{original_base}.pdf"
        process_document.delay(converted_file_path, original_filename=pdf_original_filename)
    else:
        process_document.delay(converted_file_path)
```

#### 3. Modified `app/api/files.py`
- Updated `ui_upload` endpoint to pass the original safe filename to processing tasks
- Passes `original_filename=safe_filename` parameter to both `process_document` and `convert_to_pdf`

```python
# For PDFs
task = process_document.delay(target_path, original_filename=safe_filename)

# For images and office documents
task = convert_to_pdf.delay(target_path, original_filename=safe_filename)
```

### Testing

#### Unit Tests (`tests/test_original_filename_preservation.py`)
Created comprehensive unit tests to verify:
1. **Test 1**: Original filename is preserved when parameter is provided
   - Uploads a file with UUID-based path but provides original filename "Apostille Sverige.pdf"
   - Verifies the database stores the original filename, not the UUID-based path

2. **Test 2**: Backward compatibility is maintained
   - Calls `process_document` without the optional parameter
   - Verifies it falls back to extracting filename from path

All tests pass successfully.

#### Existing Tests
All existing tests in `tests/test_process_document.py` continue to pass, confirming backward compatibility.

### Benefits of This Solution

1. **Minimal Changes**: Only 3 files modified, optional parameter added to maintain backward compatibility
2. **Security Maintained**: Files are still stored with UUID-based names on disk to prevent:
   - Filename conflicts
   - Path traversal attacks
   - Overwriting existing files
3. **User Experience Improved**: Users can now see their original filenames in the UI
4. **Backward Compatible**: Existing code that calls these tasks without the new parameter continues to work

### Example Flow

**Before the fix:**
```
User uploads: "Apostille Sverige.pdf"
→ Saved as: "e64b2825-9ff2-486b-aff1-08af2957140b.pdf"
→ process_document extracts: "e64b2825-9ff2-486b-aff1-08af2957140b.pdf"
→ Database stores: "e64b2825-9ff2-486b-aff1-08af2957140b.pdf" ❌
```

**After the fix:**
```
User uploads: "Apostille Sverige.pdf"
→ Saved as: "e64b2825-9ff2-486b-aff1-08af2957140b.pdf" (for security)
→ ui_upload passes original_filename="Apostille Sverige.pdf" to process_document
→ Database stores: "Apostille Sverige.pdf" ✅
```

### Files Changed
- `app/tasks/process_document.py`: Added optional parameter and logic to use it
- `app/tasks/convert_to_pdf.py`: Added optional parameter and pass-through logic
- `app/api/files.py`: Updated to pass original filename to tasks
- `tests/test_original_filename_preservation.py`: New comprehensive unit tests

### Code Quality
- All code formatted with Black (line length 120)
- All imports sorted with isort (Black profile)
- All linting issues resolved (flake8)
- All existing and new tests pass
