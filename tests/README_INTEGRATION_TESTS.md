# Integration Testing with Real Infrastructure

This directory contains comprehensive integration tests that spin up real infrastructure components using Docker containers.

## Overview

Unlike unit tests that mock external dependencies, these integration tests use **real services** to test the application as close to production as possible:

- **PostgreSQL** - Real database instead of SQLite in-memory
- **Redis** - Real message broker for Celery tasks
- **Gotenberg** - Real PDF conversion service
- **WebDAV Server** - Real upload target
- **SFTP Server** - Real SSH/SFTP server
- **MinIO** - Real S3-compatible object storage
- **FTP Server** - Real FTP server

## Prerequisites

### Required

1. **Docker** - Must be installed and running
   ```bash
   docker --version
   docker ps  # Should work without errors
   ```

2. **Python Dependencies**
   ```bash
   pip install -r requirements-dev.txt
   ```

This installs:
- `testcontainers` - For managing Docker containers in tests
- `pytest` and testing tools
- `minio`, `boto3`, `redis` - Client libraries for services
- `paramiko` - For SFTP testing

### Optional

- Docker Compose (for manual infrastructure setup)
- Sufficient disk space (~2GB for Docker images)
- Sufficient RAM (~4GB recommended)

## Test Organization

### Test Files

| File | Description | Scope |
|------|-------------|-------|
| `test_upload_webdav_comprehensive.py` | Unit tests with mocks (23 tests) | Fast, no Docker |
| `test_upload_webdav_integration.py` | WebDAV integration with real server (10 tests) | Medium, requires Docker |
| `test_e2e_full_stack.py` | Full end-to-end with all infrastructure (12+ tests) | Slow, requires Docker |
| `fixtures_integration.py` | Reusable fixtures for real services | N/A |

### Test Markers

Tests are organized using pytest markers:

```python
@pytest.mark.unit          # Fast unit tests with mocks
@pytest.mark.integration   # Integration tests with some real services
@pytest.mark.e2e           # Full end-to-end with complete stack
@pytest.mark.requires_docker  # Requires Docker to run
@pytest.mark.slow          # Takes significant time (>30s)
```

## Running Tests

### Quick Start - Unit Tests Only (No Docker)

```bash
# Run only fast unit tests (mocked, no containers)
pytest -m unit -v

# Run WebDAV unit tests specifically
pytest tests/test_upload_webdav_comprehensive.py -v
```

### Integration Tests - WebDAV Only

```bash
# Run WebDAV integration tests (spins up WebDAV container)
pytest tests/test_upload_webdav_integration.py -v

# Run specific test
pytest tests/test_upload_webdav_integration.py::TestWebDAVIntegration::test_upload_file_to_real_webdav_server -v
```

### Full End-to-End Tests - Complete Infrastructure

```bash
# Run all e2e tests (spins up all infrastructure)
pytest -m e2e -v

# Run specific infrastructure test
pytest tests/test_e2e_full_stack.py::TestFullInfrastructure::test_complete_stack_available -v

# Run with real Redis and Celery
pytest tests/test_e2e_full_stack.py::TestEndToEndWithRedis -v
```

### Run Everything

```bash
# Run all tests (unit + integration + e2e)
pytest tests/test_upload_webdav*.py tests/test_e2e*.py -v

# Skip slow tests
pytest -m "not slow" -v

# Run only Docker-based tests
pytest -m requires_docker -v
```

## Infrastructure Fixtures

### Available Fixtures

#### `postgres_container`
Starts PostgreSQL 15 in Alpine container.
```python
def test_with_postgres(postgres_container):
    db_url = postgres_container["url"]
    # Use real PostgreSQL
```

#### `redis_container`
Starts Redis 7 for Celery broker/backend.
```python
def test_with_redis(redis_container):
    redis_url = redis_container["url"]
    # Queue actual tasks
```

#### `gotenberg_container`
Starts Gotenberg for PDF conversion.
```python
def test_with_gotenberg(gotenberg_container):
    url = gotenberg_container["url"]
    # Convert documents
```

#### `webdav_container`
Starts WebDAV server (bytemark/webdav).
```python
def test_with_webdav(webdav_container):
    # Upload files, verify on server
    url = webdav_container["url"]
    username = webdav_container["username"]  # "testuser"
    password = webdav_container["password"]  # "testpass"
```

#### `sftp_container`
Starts SFTP server (atmoz/sftp).
```python
def test_with_sftp(sftp_container):
    # Upload via SFTP, verify
    host = sftp_container["host"]
    port = sftp_container["port"]
```

#### `minio_container`
Starts MinIO (S3-compatible).
```python
def test_with_s3(minio_container):
    # Use boto3 with MinIO
    access_key = minio_container["access_key"]
    secret_key = minio_container["secret_key"]
```

#### `ftp_container`
Starts FTP server (stilliard/pure-ftpd).
```python
def test_with_ftp(ftp_container):
    # Upload via FTP
```

#### `full_infrastructure`
Combined fixture with ALL services.
```python
def test_production_like(full_infrastructure):
    infra = full_infrastructure
    # Access: postgres, redis, gotenberg, webdav, sftp, minio
```

#### `celery_app` and `celery_worker`
Real Celery application with worker.
```python
def test_celery_tasks(celery_app, celery_worker):
    # Queue actual tasks that get processed
    result = my_task.delay(arg1, arg2)
    result.get(timeout=30)  # Wait for worker to process
```

## Test Scenarios

### 1. Simple WebDAV Upload Test

```python
@pytest.mark.integration
@pytest.mark.requires_docker
def test_upload_to_webdav(webdav_container, sample_text_file):
    """Upload file to real WebDAV server and verify."""
    from app.tasks.upload_to_webdav import upload_to_webdav

    with patch("app.tasks.upload_to_webdav.settings") as mock_settings:
        mock_settings.webdav_url = webdav_container["url"] + "/"
        mock_settings.webdav_username = webdav_container["username"]
        mock_settings.webdav_password = webdav_container["password"]

        # Execute upload
        result = upload_to_webdav.apply(args=[sample_text_file]).get()

        # Verify on server
        response = requests.get(
            f"{webdav_container['url']}/test.txt",
            auth=(webdav_container["username"], webdav_container["password"])
        )
        assert response.status_code == 200
```

### 2. End-to-End with Redis and Celery

```python
@pytest.mark.e2e
def test_async_upload(redis_container, webdav_container, celery_worker, sample_text_file):
    """Queue task in Redis, worker executes, uploads to WebDAV."""
    from app.tasks.upload_to_webdav import upload_to_webdav

    # Queue task (goes to Redis)
    result = upload_to_webdav.delay(sample_text_file, file_id=1)

    # Wait for worker to process
    while not result.ready():
        time.sleep(0.5)

    # Verify result
    assert result.get()["status"] == "Completed"
```

### 3. Full Production Pipeline

```python
@pytest.mark.e2e
@pytest.mark.slow
def test_complete_pipeline(full_infrastructure, celery_worker, db_session_real):
    """
    Test complete workflow:
    1. Store in PostgreSQL
    2. Queue task in Redis
    3. Worker processes
    4. Upload to WebDAV
    5. Verify all steps
    """
    # See test_document_processing_pipeline in test_e2e_full_stack.py
```

## Performance Notes

### Container Startup Times

| Container | Startup Time | Notes |
|-----------|--------------|-------|
| PostgreSQL | ~2-3s | Fast |
| Redis | ~1-2s | Very fast |
| WebDAV | ~2s | Fast |
| SFTP | ~3s | Moderate |
| MinIO | ~3-4s | Moderate |
| FTP | ~3s | Moderate |
| Gotenberg | ~5-8s | Slower (Chromium startup) |

### Test Execution Times

- **Unit tests**: <1s per test
- **Single integration test**: 2-5s (with container)
- **E2E with full stack**: 10-30s per test
- **Full suite**: 2-5 minutes

### Resource Usage

- **Memory**: ~100MB per container
- **Disk**: ~500MB total for images
- **CPU**: Varies, mostly idle

## Debugging

### View Container Logs

```python
def test_debug(webdav_container):
    container = webdav_container["container"]
    logs = container.get_logs()
    print(logs)
```

### Keep Containers Running

Set a breakpoint after test to inspect:
```python
def test_inspect(webdav_container):
    result = upload_file()

    import pdb; pdb.set_trace()  # Container still running here

    # Manually inspect: docker ps, docker logs, etc.
```

### Check Container Health

```bash
# While tests are running
docker ps  # See running containers
docker logs <container_id>  # View logs
docker exec -it <container_id> sh  # Shell into container
```

## Troubleshooting

### "Docker not found"

```bash
# Install Docker
# On Ubuntu/Debian:
sudo apt-get install docker.io
sudo usermod -aG docker $USER  # Add user to docker group
# Logout and login again
```

### "Permission denied" for Docker

```bash
# Add user to docker group
sudo usermod -aG docker $USER
# Logout/login or:
newgrp docker
```

### "Port already in use"

Containers use random ports, but if issues persist:
```bash
docker ps  # Check what's running
docker stop $(docker ps -q)  # Stop all containers
```

### Tests hang or timeout

- Increase timeout values in test code
- Check Docker has enough resources (memory/CPU)
- Check network connectivity

### Containers not cleaning up

```bash
# Manual cleanup
docker ps -a | grep testcontainers | awk '{print $1}' | xargs docker rm -f
docker volume prune -f
```

## CI/CD Integration

### GitHub Actions - Current Configuration

The DocuElevate CI workflow (`.github/workflows/tests.yaml`) **excludes E2E tests** by default because they require Docker-in-Docker (testcontainers), which requires additional configuration in GitHub Actions.

```yaml
- name: Run Tests
  # Exclude E2E tests - they require Docker-in-Docker (testcontainers)
  run: pytest tests/ -v --cov=app -m "not e2e"
```

**To run E2E tests locally:**
```bash
pytest -m e2e -v
```

**To run all tests including E2E locally:**
```bash
pytest tests/ -v
```

### GitHub Actions with E2E Support (Optional)

If you want to enable E2E tests in CI, you need Docker-in-Docker setup:

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      docker:
        image: docker:latest
        options: --privileged

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt

      - name: Run integration tests
        run: |
          pytest -m "integration or e2e" -v --tb=short
```

## Best Practices

### 1. Use Appropriate Markers

```python
# Fast test - use unit
@pytest.mark.unit
def test_validation():
    ...

# Needs Docker - mark it
@pytest.mark.requires_docker
def test_upload():
    ...

# Slow test - mark it
@pytest.mark.slow
def test_large_file():
    ...
```

### 2. Reuse Fixtures (Session Scope)

```python
# Good - starts once for all tests in class
@pytest.fixture(scope="session")
def postgres_container():
    ...

# Bad - starts/stops for each test
@pytest.fixture(scope="function")
def postgres_container():
    ...
```

### 3. Clean Up Resources

```python
def test_with_temp_files(tmp_path):
    # tmp_path auto-cleans up
    file = tmp_path / "test.txt"
    ...
```

### 4. Use Timeouts

```python
# Always set timeouts for container operations
response = requests.get(url, timeout=5)
result.get(timeout=30)
```

### 5. Verify Actual Behavior

```python
# Don't just check return values
result = upload_file()
assert result["status"] == "success"

# Also verify the file actually exists on the server!
assert file_exists_on_server(filename)
```

## Coverage

Running integration tests significantly improves code coverage:

| Test Type | upload_to_webdav.py Coverage |
|-----------|------------------------------|
| Unit only | ~20% |
| + Integration | ~80% |
| + E2E | ~95%+ |

```bash
# Run with coverage
pytest tests/test_upload_webdav*.py --cov=app/tasks/upload_to_webdav --cov-report=html

# View report
open htmlcov/index.html
```

## Contributing

When adding new upload destinations:

1. **Add unit tests** (with mocks) in `test_upload_<destination>_comprehensive.py`
2. **Add container fixture** in `fixtures_integration.py`
3. **Add integration tests** in `test_upload_<destination>_integration.py`
4. **Add e2e scenarios** in `test_e2e_full_stack.py`

See WebDAV tests as reference implementation.

## Summary

| Test Level | Fixtures | Speed | Realism | Use Case |
|------------|----------|-------|---------|----------|
| Unit | Mocks | Fast (ms) | Low | Development, TDD |
| Integration | 1-2 containers | Medium (s) | Medium | Feature testing |
| E2E | Full stack | Slow (10s+) | High | Pre-production validation |

Choose the appropriate level based on what you're testing!
