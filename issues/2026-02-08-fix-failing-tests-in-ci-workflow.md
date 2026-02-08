# Fix failing tests in CI workflow

## Problems Addressed:

### 1. Services Not Running (Redis, RabbitMQ)
Many test failures are caused by connection errors to Redis (localhost:6379) and AMQP/RabbitMQ (127.0.0.1:5672) with `ConnectionRefusedError: [Errno 111] Connection refused`. 

**Solution:** Add service containers to `.github/workflows/tests.yaml`:
```yaml
services:
  redis:
    image: redis:7
    ports:
      - 6379:6379
  rabbitmq:
    image: rabbitmq:3-management
    ports:
      - 5672:5672
      - 15672:15672
```

### 2. Jinja2 Template Error: 'file' is undefined
Error in `file_detail.html` template. The view rendering this template is missing the 'file' variable in the context when handling nonexistent files. 

**Solution:** Ensure the template response includes the file variable or handle the error case differently in the view.

### 3. SQLAlchemy IntegrityError: NOT NULL constraint failed: files.local_filename
In `tests/test_bulk_operations.py::TestBulkOperations::test_bulk_reprocess_missing_files`, the test tries to insert a file record with `local_filename=None`, but the database schema requires this field. 

**Solution:** Fix test data to provide a value for local_filename or make the field nullable in the schema.

### 4. API Response Type Mismatch
In `tests/test_api.py::TestFileEndpoints::test_list_files_empty`, the test expects a list but receives a dictionary with 'files' and 'pagination' keys. 

**Solution:** Update either the test expectations or the API response format to be consistent.

### 5. Subtask Retry Error Message
In `tests/test_file_detail_endpoints.py::TestSubtaskRetry::test_retry_subtask_invalid_task_name`, the test expects error message 'invalid subtask name' but gets 'processed file not found. cannot retry upload.'. 

**Solution:** Fix the error handling logic to return the expected error message.

### 6. File Reprocessing 500 Error
In `tests/test_file_detail_endpoints.py::TestFileReprocessing::test_reprocess_existing_file`, the endpoint returns 500 Internal Server Error instead of 200. 

**Solution:** Investigate the cause of this server error and fix the underlying issue.

## Failed Tests:
- `tests/test_api.py::TestFileEndpoints::test_list_files_empty`
- `tests/test_bulk_operations.py::TestBulkOperations::test_bulk_reprocess_missing_files`
- `tests/test_file_detail_endpoints.py::TestFileReprocessing::test_reprocess_existing_file`
- `tests/test_file_detail_endpoints.py::TestSubtaskRetry::test_retry_subtask_invalid_task_name`
- `tests/test_file_detail_endpoints.py::TestFileDetailView::test_file_detail_view_nonexistent`
- All tests in `test_file_upload.py` (9 tests failing due to RabbitMQ connection)

## CI Run:
https://github.com/christianlouis/DocuElevate/actions/runs/21794817705/job/62880458485

## Commit:
`93149d0c56e0e7373ad92d59fd8c575eb9095914`