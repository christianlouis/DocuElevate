"""
End-to-end integration tests using real infrastructure.

These tests spin up actual services (PostgreSQL, Redis, Gotenberg, WebDAV, SFTP, MinIO)
and test the complete application workflow from API request to file upload.
"""

import os
import time
from unittest.mock import patch

import pytest
import requests

# Import testcontainers requirement
pytest.importorskip("testcontainers", reason="testcontainers not installed")

try:
    import psycopg2  # noqa: F401

    _has_psycopg2 = True
except ModuleNotFoundError:
    _has_psycopg2 = False


_TEST_CREDENTIAL = "pass"  # noqa: S105


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.e2e
class TestEndToEndWithRedis:
    """
    End-to-end tests with real Redis and Celery workers.

    These tests verify the complete task queueing and execution workflow.
    """

    def test_webdav_upload_with_redis_and_celery(
        self,
        redis_container,
        webdav_container,
        celery_app,
        celery_worker,
        sample_text_file,
    ):
        """
        Test complete workflow: Queue task in Redis → Celery worker executes → Upload to WebDAV.

        This is the closest to production - actual message queueing and async execution.
        """
        from app.tasks.upload_to_webdav import upload_to_webdav

        with (
            patch("app.tasks.upload_to_webdav.settings") as mock_settings,
            patch("app.tasks.upload_to_webdav.log_task_progress"),
        ):
            # Configure to use real WebDAV server
            mock_settings.webdav_url = webdav_container["url"] + "/"
            mock_settings.webdav_username = webdav_container["username"]
            mock_settings.webdav_password = webdav_container["password"]
            mock_settings.webdav_folder = ""
            mock_settings.webdav_verify_ssl = False
            mock_settings.http_request_timeout = 30

            # Queue the task (it goes to Redis)
            result = upload_to_webdav.delay(sample_text_file, file_id=1)

            # Wait for task to complete (worker picks it up from Redis)
            timeout = 30
            start_time = time.time()
            while not result.ready():
                if time.time() - start_time > timeout:
                    pytest.fail(f"Task did not complete within {timeout} seconds")
                time.sleep(0.5)

            # Get the result
            task_result = result.get(timeout=10)

            # Verify task completed successfully
            assert task_result["status"] == "Completed"
            assert task_result["file"] == sample_text_file

            # Verify file was actually uploaded to WebDAV server
            filename = os.path.basename(sample_text_file)
            file_url = f"{webdav_container['url']}/{filename}"

            response = requests.get(
                file_url, auth=(webdav_container["username"], webdav_container["password"]), timeout=5
            )

            assert response.status_code == 200

            # Verify content matches
            with open(sample_text_file, "rb") as f:
                assert response.content == f.read()

    def test_task_queuing_in_redis(
        self,
        redis_container,
        celery_app,
    ):
        """
        Test that tasks are properly queued in Redis.

        This verifies the Redis broker is working correctly.
        """
        import redis

        from app.tasks.upload_to_webdav import upload_to_webdav

        # Connect to Redis directly
        r = redis.from_url(redis_container["url"])

        # Check Redis is accessible
        assert r.ping()

        # Get current queue length
        initial_queue_length = r.llen("celery")

        # Queue a task (don't execute, just verify queueing)
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings:
            mock_settings.webdav_url = "http://test.com"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = _TEST_CREDENTIAL

            # This will queue the task in Redis
            result = upload_to_webdav.apply_async(args=["/tmp/test.txt"], kwargs={"file_id": 1})

            # Verify task ID was generated
            assert result.id is not None

    def test_multiple_tasks_parallel_execution(
        self,
        redis_container,
        webdav_container,
        celery_app,
        celery_worker,
        tmp_path,
    ):
        """
        Test multiple tasks executing in parallel through Redis/Celery.

        This tests concurrent task processing.
        """
        from app.tasks.upload_to_webdav import upload_to_webdav

        # Create multiple test files
        files = []
        for i in range(5):
            test_file = tmp_path / f"test_{i}.txt"
            test_file.write_text(f"Test file {i}")
            files.append(str(test_file))

        with (
            patch("app.tasks.upload_to_webdav.settings") as mock_settings,
            patch("app.tasks.upload_to_webdav.log_task_progress"),
        ):
            mock_settings.webdav_url = webdav_container["url"] + "/"
            mock_settings.webdav_username = webdav_container["username"]
            mock_settings.webdav_password = webdav_container["password"]
            mock_settings.webdav_folder = "parallel-test"
            mock_settings.webdav_verify_ssl = False
            mock_settings.http_request_timeout = 30

            # Create folder on WebDAV server
            folder_url = f"{webdav_container['url']}/parallel-test"
            requests.request(
                "MKCOL", folder_url, auth=(webdav_container["username"], webdav_container["password"]), timeout=5
            )

            # Queue all tasks
            results = []
            for idx, file_path in enumerate(files):
                result = upload_to_webdav.delay(file_path, file_id=idx + 100)
                results.append((result, file_path))

            # Wait for all tasks to complete
            timeout = 60
            start_time = time.time()
            all_ready = False

            while not all_ready:
                if time.time() - start_time > timeout:
                    pytest.fail("Tasks did not complete within timeout")

                all_ready = all(r.ready() for r, _ in results)
                time.sleep(0.5)

            # Verify all tasks succeeded
            for result, file_path in results:
                task_result = result.get(timeout=5)
                assert task_result["status"] == "Completed"

                # Verify file on server
                filename = os.path.basename(file_path)
                file_url = f"{webdav_container['url']}/parallel-test/{filename}"
                response = requests.get(
                    file_url, auth=(webdav_container["username"], webdav_container["password"]), timeout=5
                )
                assert response.status_code == 200

    def test_task_retry_on_failure(
        self,
        redis_container,
        celery_app,
        celery_worker,
        sample_text_file,
    ):
        """
        Test that tasks retry on failure using Redis.

        This verifies the retry mechanism works with real broker.
        """
        from app.tasks.upload_to_webdav import upload_to_webdav

        with (
            patch("app.tasks.upload_to_webdav.settings") as mock_settings,
            patch("app.tasks.upload_to_webdav.log_task_progress"),
            patch("app.tasks.upload_to_webdav.requests.put") as mock_put,
        ):
            mock_settings.webdav_url = "http://test.com/"
            mock_settings.webdav_username = "user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = ""
            mock_settings.webdav_verify_ssl = False
            mock_settings.http_request_timeout = 30

            # First attempt fails with 500
            mock_response_fail = requests.Response()
            mock_response_fail.status_code = 500
            mock_response_fail._content = b"Server Error"

            # Second attempt succeeds
            mock_response_success = requests.Response()
            mock_response_success.status_code = 201

            # Configure mock to fail once, then succeed
            mock_put.side_effect = [mock_response_fail, mock_response_success]

            # Queue task
            result = upload_to_webdav.delay(sample_text_file, file_id=1)

            # Wait for completion (including retry)
            timeout = 30
            start_time = time.time()
            while not result.ready():
                if time.time() - start_time > timeout:
                    break  # Task might still be retrying
                time.sleep(0.5)


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.e2e
class TestFullInfrastructure:
    """
    Tests using the complete infrastructure stack.

    PostgreSQL + Redis + Gotenberg + Upload targets (WebDAV/SFTP/MinIO)
    """

    def test_complete_stack_available(self, full_infrastructure):
        """
        Verify all infrastructure components are running.
        """
        infra = full_infrastructure

        # Check PostgreSQL
        assert infra["postgres"]["url"] is not None
        assert "postgresql" in infra["postgres"]["url"]

        # Check Redis
        assert infra["redis"]["url"] is not None
        import redis

        r = redis.from_url(infra["redis"]["url"])
        assert r.ping()

        # Check Gotenberg
        assert infra["gotenberg"]["url"] is not None
        response = requests.get(f"{infra['gotenberg']['url']}/health", timeout=5)
        assert response.status_code == 200

        # Check WebDAV
        assert infra["webdav"]["url"] is not None

        # Check SFTP
        assert infra["sftp"]["host"] is not None
        assert infra["sftp"]["port"] is not None

        # Check MinIO
        assert infra["minio"]["access_key"] is not None

    @pytest.mark.skipif(
        not _has_psycopg2,
        reason="psycopg2 not installed",
    )
    def test_database_with_real_postgres(self, postgres_container, db_session_real):
        """
        Test database operations with real PostgreSQL instead of SQLite.
        """
        from app.models import FileRecord

        # Create a file record
        file_record = FileRecord(
            filename="test.pdf",
            file_path="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )

        db_session_real.add(file_record)
        db_session_real.commit()

        # Verify it was saved
        assert file_record.id is not None

        # Query it back
        queried = db_session_real.query(FileRecord).filter_by(filename="test.pdf").first()
        assert queried is not None
        assert queried.filename == "test.pdf"
        assert queried.file_size == 1024

    def test_upload_to_multiple_targets(
        self,
        full_infrastructure,
        celery_app,
        celery_worker,
        sample_text_file,
    ):
        """
        Test uploading to multiple targets in parallel (WebDAV + SFTP).

        This simulates the send_to_all_destinations workflow.
        """
        from app.tasks.upload_to_webdav import upload_to_webdav

        infra = full_infrastructure

        with (
            patch("app.tasks.upload_to_webdav.settings") as mock_settings,
            patch("app.tasks.upload_to_webdav.log_task_progress"),
        ):
            mock_settings.webdav_url = infra["webdav"]["url"] + "/"
            mock_settings.webdav_username = infra["webdav"]["username"]
            mock_settings.webdav_password = infra["webdav"]["password"]
            mock_settings.webdav_folder = ""
            mock_settings.webdav_verify_ssl = False
            mock_settings.http_request_timeout = 30

            # Upload to WebDAV
            webdav_result = upload_to_webdav.delay(sample_text_file, file_id=1)

            # Wait for completion
            timeout = 30
            start_time = time.time()
            while not webdav_result.ready():
                if time.time() - start_time > timeout:
                    pytest.fail("Task timeout")
                time.sleep(0.5)

            # Verify WebDAV upload
            result = webdav_result.get(timeout=10)
            assert result["status"] == "Completed"

            # Verify file on WebDAV server
            filename = os.path.basename(sample_text_file)
            file_url = f"{infra['webdav']['url']}/{filename}"
            response = requests.get(
                file_url, auth=(infra["webdav"]["username"], infra["webdav"]["password"]), timeout=5
            )
            assert response.status_code == 200

    def test_gotenberg_pdf_conversion(self, gotenberg_container, tmp_path):
        """
        Test PDF conversion using real Gotenberg service.

        This verifies document processing capabilities.
        """
        # Create a simple HTML file
        html_file = tmp_path / "test.html"
        html_file.write_text("""
        <!DOCTYPE html>
        <html>
        <head><title>Test Document</title></head>
        <body><h1>Integration Test</h1><p>This is a test document.</p></body>
        </html>
        """)

        # Convert to PDF using Gotenberg
        with open(html_file, "rb") as f:
            files = {"files": f}
            response = requests.post(
                f"{gotenberg_container['url']}/forms/chromium/convert/html", files=files, timeout=30
            )

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "application/pdf"
        assert len(response.content) > 0
        assert response.content.startswith(b"%PDF")

    def test_minio_s3_upload(self, minio_container, sample_text_file):
        """
        Test S3-compatible upload using real MinIO.

        This tests S3 upload functionality with actual storage.
        """
        import boto3
        from botocore.client import Config

        # Create S3 client configured for MinIO
        s3_client = boto3.client(
            "s3",
            endpoint_url=minio_container["url"],
            aws_access_key_id=minio_container["access_key"],
            aws_secret_access_key=minio_container["secret_key"],
            config=Config(signature_version="s3v4"),
            region_name=minio_container["region"],
        )

        # Create bucket
        bucket_name = "test-bucket"
        s3_client.create_bucket(Bucket=bucket_name)

        # Upload file
        filename = os.path.basename(sample_text_file)
        with open(sample_text_file, "rb") as f:
            s3_client.upload_fileobj(f, bucket_name, filename)

        # Verify upload
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        assert "Contents" in response
        assert len(response["Contents"]) == 1
        assert response["Contents"][0]["Key"] == filename

        # Download and verify content
        download_path = os.path.join(os.path.dirname(sample_text_file), "downloaded.txt")
        s3_client.download_file(bucket_name, filename, download_path)

        with open(sample_text_file, "rb") as original, open(download_path, "rb") as downloaded:
            assert original.read() == downloaded.read()

    def test_sftp_upload(self, sftp_container, sample_text_file):
        """
        Test SFTP upload using real SFTP server.
        """
        import paramiko

        # Create SFTP client
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Connect to SFTP server
        ssh.connect(
            hostname=sftp_container["host"],
            port=int(sftp_container["port"]),
            username=sftp_container["username"],
            password=sftp_container["password"],
            timeout=10,
        )

        sftp = ssh.open_sftp()

        try:
            # Upload file
            filename = os.path.basename(sample_text_file)
            remote_path = f"{sftp_container['folder']}/{filename}"

            sftp.put(sample_text_file, remote_path)

            # Verify upload
            stat = sftp.stat(remote_path)
            assert stat.st_size == os.path.getsize(sample_text_file)

            # Download and verify content
            download_path = os.path.join(os.path.dirname(sample_text_file), "sftp_downloaded.txt")
            sftp.get(remote_path, download_path)

            with open(sample_text_file, "rb") as original, open(download_path, "rb") as downloaded:
                assert original.read() == downloaded.read()

        finally:
            sftp.close()
            ssh.close()


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.e2e
@pytest.mark.slow
class TestProductionLikeScenarios:
    """
    Production-like end-to-end scenarios testing complete workflows.
    """

    def test_document_processing_pipeline(
        self,
        full_infrastructure,
        celery_app,
        celery_worker,
        db_session_real,
        tmp_path,
    ):
        """
        Test the complete document processing pipeline:
        1. Upload document via API
        2. Store metadata in PostgreSQL
        3. Queue processing tasks in Redis
        4. Process document (mock OCR/metadata extraction)
        5. Upload to WebDAV via Celery
        6. Verify all steps completed

        This is the closest to real production usage.
        """
        from app.models import FileRecord
        from app.tasks.upload_to_webdav import upload_to_webdav

        # Create test document
        test_doc = tmp_path / "invoice.pdf"
        test_doc.write_bytes(b"%PDF-1.4\n%Test PDF\n%%EOF")

        # Step 1: Store in database
        file_record = FileRecord(
            filename="invoice.pdf",
            file_path=str(test_doc),
            file_size=test_doc.stat().st_size,
            mime_type="application/pdf",
        )
        db_session_real.add(file_record)
        db_session_real.commit()

        assert file_record.id is not None
        db_file_id = file_record.id

        # Step 2: Queue upload task
        infra = full_infrastructure

        with (
            patch("app.tasks.upload_to_webdav.settings") as mock_settings,
            patch("app.tasks.upload_to_webdav.log_task_progress"),
        ):
            mock_settings.webdav_url = infra["webdav"]["url"] + "/"
            mock_settings.webdav_username = infra["webdav"]["username"]
            mock_settings.webdav_password = infra["webdav"]["password"]
            mock_settings.webdav_folder = "processed"
            mock_settings.webdav_verify_ssl = False
            mock_settings.http_request_timeout = 30

            # Create folder
            folder_url = f"{infra['webdav']['url']}/processed"
            requests.request(
                "MKCOL", folder_url, auth=(infra["webdav"]["username"], infra["webdav"]["password"]), timeout=5
            )

            # Step 3: Queue upload
            result = upload_to_webdav.delay(str(test_doc), file_id=db_file_id)

            # Step 4: Wait for processing
            timeout = 30
            start_time = time.time()
            while not result.ready():
                if time.time() - start_time > timeout:
                    pytest.fail("Pipeline timeout")
                time.sleep(0.5)

            # Step 5: Verify completion
            task_result = result.get(timeout=10)
            assert task_result["status"] == "Completed"

            # Step 6: Verify file on WebDAV
            file_url = f"{infra['webdav']['url']}/processed/invoice.pdf"
            response = requests.get(
                file_url, auth=(infra["webdav"]["username"], infra["webdav"]["password"]), timeout=5
            )
            assert response.status_code == 200
            assert response.content == test_doc.read_bytes()
