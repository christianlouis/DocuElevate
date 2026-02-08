## Problem Description

7 tests in `tests/test_file_upload.py` are failing in the CI pipeline due to Celery task mocking issues. The tests expect the `delay` method to be called once, but it's being called 0 times.

### Failing Tests
- `test_upload_valid_text_file`
- `test_upload_valid_image_jpeg`
- `test_upload_valid_png_image`
- `test_upload_office_document_docx`
- `test_upload_csv_file`
- `test_upload_executable_file`
- `test_image_by_extension`

### Error Message
```
AssertionError: Expected 'delay' to have been called once. Called 0 times.
```

### Root Cause Analysis

The test fixture `mock_celery_tasks` is patching the Celery tasks at:
- `app.api.files.process_document.delay`
- `app.api.files.convert_to_pdf.delay`

However, looking at the actual implementation in `app/api/files.py` (lines 656, 662, 669, 674), the tasks are invoked using `.delay()` method correctly:
- Line 656: `task = process_document.delay(target_path, original_filename=safe_filename)`
- Line 662: `task = convert_to_pdf.delay(target_path, original_filename=safe_filename)`
- Line 669: `task = convert_to_pdf.delay(target_path, original_filename=safe_filename)`
- Line 674: `task = convert_to_pdf.delay(target_path, original_filename=safe_filename)`

The issue is that the patches are applied correctly but the mocks are not being invoked. This suggests:
1. The patch path might need adjustment
2. The tasks might be imported/accessed differently at runtime
3. There might be an issue with how the tasks are being called in the test environment

### Files to Fix
- `tests/test_file_upload.py` - Fix the mock patching in the `mock_celery_tasks` fixture (lines 20-36)

### Expected Behavior
All tests should pass with 100% success rate. The mocked Celery tasks should be called appropriately when files are uploaded through the `/api/ui-upload` endpoint.

### Solution Approach
1. Verify the correct patch path for the Celery tasks
2. Ensure the patch is applied before the import of the tasks
3. Consider patching at the module level where tasks are defined rather than where they're used
4. Alternative: Patch the task objects directly: `app.tasks.process_document.process_document` and `app.tasks.convert_to_pdf.convert_to_pdf`

### Reference
- Failing job: https://github.com/christianlouis/DocuElevate/actions/runs/21801196852/job/62896908441
- Commit: 17795620c62c0bcf744eb7e940a3262c364f9bed

### Acceptance Criteria
- All 7 failing tests pass
- Total test suite passes with 180/180 tests passing (currently 173/180)
- CI pipeline succeeds
- No regression in other tests