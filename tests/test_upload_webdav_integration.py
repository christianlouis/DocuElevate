"""
Integration tests for WebDAV upload with real server.

These tests spin up a real WebDAV server in a Docker container and test
actual file uploads against it, then verify the files were uploaded successfully.
"""
import os
import time
import pytest
import requests
from pathlib import Path
from unittest.mock import patch

from app.tasks.upload_to_webdav import upload_to_webdav

# Import testcontainers - required for these tests
pytest.importorskip("testcontainers", reason="testcontainers not installed")
from testcontainers.core.container import DockerContainer

_TEST_CREDENTIAL = "testpass"  # noqa: S105
_TEST_WRONG_CREDENTIAL = "wrongpass"  # noqa: S105


@pytest.mark.integration
@pytest.mark.requires_docker
class TestWebDAVIntegration:
    """Integration tests with real WebDAV server."""

    @pytest.fixture(scope="class")
    def webdav_server(self):
        """
        Start a real WebDAV server in a Docker container.
        
        Uses bytemark/webdav image which provides a simple WebDAV server.
        """
        # Start WebDAV container
        container = DockerContainer("bytemark/webdav:latest")
        container.with_exposed_ports(80)
        container.with_env("AUTH_TYPE", "Basic")
        container.with_env("USERNAME", "testuser")
        container.with_env("PASSWORD", _TEST_CREDENTIAL)
        
        # Start the container
        container.start()
        
        # Wait for server to be ready
        time.sleep(2)
        
        # Get the mapped port
        host = container.get_container_host_ip()
        port = container.get_exposed_port(80)
        
        server_info = {
            "container": container,
            "host": host,
            "port": port,
            "url": f"http://{host}:{port}",
            "username": "testuser",
            "password": _TEST_CREDENTIAL
        }
        
        # Verify server is accessible
        try:
            response = requests.get(
                server_info["url"],
                auth=(server_info["username"], server_info["password"]),
                timeout=5
            )
            assert response.status_code in [200, 301, 302, 401], \
                f"WebDAV server not ready, got status {response.status_code}"
        except Exception as e:
            container.stop()
            pytest.fail(f"Failed to connect to WebDAV server: {e}")
        
        yield server_info
        
        # Cleanup
        container.stop()

    def test_upload_file_to_real_webdav_server(self, webdav_server, sample_text_file):
        """Test uploading a file to a real WebDAV server."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            # Configure settings to point to real WebDAV server
            mock_settings.webdav_url = webdav_server["url"] + "/"
            mock_settings.webdav_username = webdav_server["username"]
            mock_settings.webdav_password = webdav_server["password"]
            mock_settings.webdav_folder = ""
            mock_settings.webdav_verify_ssl = False  # HTTP server
            mock_settings.http_request_timeout = 30
            
            # Upload the file
            result = upload_to_webdav.apply(
                args=[sample_text_file],
                kwargs={"file_id": 1}
            ).get()
            
            # Verify upload succeeded
            assert result["status"] == "Completed"
            assert result["file"] == sample_text_file
            assert "url" in result
            
            # Verify the file actually exists on the server
            filename = os.path.basename(sample_text_file)
            file_url = f"{webdav_server['url']}/{filename}"
            
            response = requests.get(
                file_url,
                auth=(webdav_server["username"], webdav_server["password"]),
                timeout=5
            )
            
            assert response.status_code == 200, \
                f"File not found on server: {response.status_code}"
            
            # Verify file content matches
            with open(sample_text_file, "rb") as f:
                expected_content = f.read()
            
            assert response.content == expected_content, \
                "Uploaded file content does not match original"

    def test_upload_to_subfolder(self, webdav_server, sample_text_file):
        """Test uploading a file to a subfolder on WebDAV server."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            # Create a test folder first
            folder_name = "test-uploads"
            folder_url = f"{webdav_server['url']}/{folder_name}"
            
            # Create folder using MKCOL method
            requests.request(
                "MKCOL",
                folder_url,
                auth=(webdav_server["username"], webdav_server["password"]),
                timeout=5
            )
            
            # Configure settings
            mock_settings.webdav_url = webdav_server["url"] + "/"
            mock_settings.webdav_username = webdav_server["username"]
            mock_settings.webdav_password = webdav_server["password"]
            mock_settings.webdav_folder = folder_name
            mock_settings.webdav_verify_ssl = False
            mock_settings.http_request_timeout = 30
            
            # Upload the file
            result = upload_to_webdav.apply(
                args=[sample_text_file],
                kwargs={"file_id": 2}
            ).get()
            
            # Verify upload succeeded
            assert result["status"] == "Completed"
            
            # Verify the file exists in the subfolder
            filename = os.path.basename(sample_text_file)
            file_url = f"{webdav_server['url']}/{folder_name}/{filename}"
            
            response = requests.get(
                file_url,
                auth=(webdav_server["username"], webdav_server["password"]),
                timeout=5
            )
            
            assert response.status_code == 200, \
                f"File not found in subfolder: {response.status_code}"

    def test_upload_pdf_file(self, webdav_server, sample_pdf_path):
        """Test uploading a PDF file to WebDAV server."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = webdav_server["url"] + "/"
            mock_settings.webdav_username = webdav_server["username"]
            mock_settings.webdav_password = webdav_server["password"]
            mock_settings.webdav_folder = ""
            mock_settings.webdav_verify_ssl = False
            mock_settings.http_request_timeout = 30
            
            # Upload the PDF
            result = upload_to_webdav.apply(
                args=[sample_pdf_path],
                kwargs={"file_id": 3}
            ).get()
            
            # Verify upload succeeded
            assert result["status"] == "Completed"
            
            # Verify the file exists
            filename = os.path.basename(sample_pdf_path)
            file_url = f"{webdav_server['url']}/{filename}"
            
            response = requests.get(
                file_url,
                auth=(webdav_server["username"], webdav_server["password"]),
                timeout=5
            )
            
            assert response.status_code == 200
            
            # Verify it's a PDF (check magic bytes)
            assert response.content.startswith(b'%PDF'), \
                "Uploaded file is not a valid PDF"

    def test_upload_with_wrong_credentials(self, webdav_server, sample_text_file):
        """Test that upload fails with wrong credentials."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = webdav_server["url"] + "/"
            mock_settings.webdav_username = "wronguser"
            mock_settings.webdav_password = _TEST_WRONG_CREDENTIAL
            mock_settings.webdav_folder = ""
            mock_settings.webdav_verify_ssl = False
            mock_settings.http_request_timeout = 30
            
            # Upload should fail with 401 Unauthorized
            with pytest.raises(Exception, match="Failed to upload.*401"):
                upload_to_webdav.apply(
                    args=[sample_text_file],
                    kwargs={"file_id": 4}
                ).get()

    def test_upload_multiple_files(self, webdav_server, sample_text_file, tmp_path):
        """Test uploading multiple files sequentially."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = webdav_server["url"] + "/"
            mock_settings.webdav_username = webdav_server["username"]
            mock_settings.webdav_password = webdav_server["password"]
            mock_settings.webdav_folder = ""
            mock_settings.webdav_verify_ssl = False
            mock_settings.http_request_timeout = 30
            
            # Create additional test files
            file1 = tmp_path / "test1.txt"
            file1.write_text("Test file 1")
            
            file2 = tmp_path / "test2.txt"
            file2.write_text("Test file 2")
            
            file3 = tmp_path / "test3.txt"
            file3.write_text("Test file 3")
            
            # Upload all files
            files = [str(file1), str(file2), str(file3)]
            uploaded_files = []
            
            for idx, file_path in enumerate(files, start=1):
                result = upload_to_webdav.apply(
                    args=[file_path],
                    kwargs={"file_id": idx + 10}
                ).get()
                
                assert result["status"] == "Completed"
                uploaded_files.append(os.path.basename(file_path))
            
            # Verify all files exist on server
            for filename in uploaded_files:
                file_url = f"{webdav_server['url']}/{filename}"
                response = requests.get(
                    file_url,
                    auth=(webdav_server["username"], webdav_server["password"]),
                    timeout=5
                )
                assert response.status_code == 200, \
                    f"File {filename} not found on server"

    def test_overwrite_existing_file(self, webdav_server, sample_text_file, tmp_path):
        """Test that uploading a file with the same name overwrites the existing one."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = webdav_server["url"] + "/"
            mock_settings.webdav_username = webdav_server["username"]
            mock_settings.webdav_password = webdav_server["password"]
            mock_settings.webdav_folder = ""
            mock_settings.webdav_verify_ssl = False
            mock_settings.http_request_timeout = 30
            
            # Create two files with same name but different content
            file1 = tmp_path / "duplicate.txt"
            file1.write_text("Original content")
            
            # Upload first version
            result1 = upload_to_webdav.apply(
                args=[str(file1)],
                kwargs={"file_id": 20}
            ).get()
            assert result1["status"] == "Completed"
            
            # Verify first version
            file_url = f"{webdav_server['url']}/duplicate.txt"
            response = requests.get(
                file_url,
                auth=(webdav_server["username"], webdav_server["password"]),
                timeout=5
            )
            assert response.text == "Original content"
            
            # Update file content
            file1.write_text("Updated content - version 2")
            
            # Upload second version
            result2 = upload_to_webdav.apply(
                args=[str(file1)],
                kwargs={"file_id": 21}
            ).get()
            assert result2["status"] == "Completed"
            
            # Verify file was overwritten
            response = requests.get(
                file_url,
                auth=(webdav_server["username"], webdav_server["password"]),
                timeout=5
            )
            assert response.text == "Updated content - version 2"

    def test_large_file_upload(self, webdav_server, tmp_path):
        """Test uploading a larger file (1MB)."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = webdav_server["url"] + "/"
            mock_settings.webdav_username = webdav_server["username"]
            mock_settings.webdav_password = webdav_server["password"]
            mock_settings.webdav_folder = ""
            mock_settings.webdav_verify_ssl = False
            mock_settings.http_request_timeout = 60  # Longer timeout for large file
            
            # Create a 1MB test file
            large_file = tmp_path / "large_file.bin"
            large_file.write_bytes(b"X" * (1024 * 1024))  # 1MB of X's
            
            # Upload the large file
            result = upload_to_webdav.apply(
                args=[str(large_file)],
                kwargs={"file_id": 30}
            ).get()
            
            assert result["status"] == "Completed"
            
            # Verify file exists and has correct size
            file_url = f"{webdav_server['url']}/large_file.bin"
            response = requests.get(
                file_url,
                auth=(webdav_server["username"], webdav_server["password"]),
                timeout=10
            )
            
            assert response.status_code == 200
            assert len(response.content) == 1024 * 1024, \
                f"File size mismatch: expected 1MB, got {len(response.content)} bytes"


@pytest.mark.integration
@pytest.mark.requires_docker
class TestWebDAVServerVerification:
    """Tests to verify WebDAV server behavior."""

    @pytest.fixture(scope="class")
    def webdav_server(self):
        """Start WebDAV server for verification tests."""
        container = DockerContainer("bytemark/webdav:latest")
        container.with_exposed_ports(80)
        container.with_env("AUTH_TYPE", "Basic")
        container.with_env("USERNAME", "admin")
        container.with_env("PASSWORD", "admin123")
        
        container.start()
        time.sleep(2)
        
        host = container.get_container_host_ip()
        port = container.get_exposed_port(80)
        
        server_info = {
            "container": container,
            "url": f"http://{host}:{port}",
            "username": "admin",
            "password": "admin123"
        }
        
        yield server_info
        container.stop()

    def test_webdav_server_basic_auth(self, webdav_server):
        """Verify WebDAV server requires authentication."""
        # Request without auth should fail
        response = requests.get(webdav_server["url"], timeout=5)
        assert response.status_code == 401
        
        # Request with auth should succeed
        response = requests.get(
            webdav_server["url"],
            auth=(webdav_server["username"], webdav_server["password"]),
            timeout=5
        )
        assert response.status_code in [200, 301, 302]

    def test_webdav_put_method(self, webdav_server, tmp_path):
        """Verify WebDAV server accepts PUT requests."""
        test_file = tmp_path / "put_test.txt"
        test_file.write_text("PUT method test")
        
        with open(test_file, "rb") as f:
            response = requests.put(
                f"{webdav_server['url']}/put_test.txt",
                auth=(webdav_server["username"], webdav_server["password"]),
                data=f,
                timeout=5
            )
        
        assert response.status_code in [200, 201, 204]

    def test_webdav_propfind_method(self, webdav_server):
        """Verify WebDAV server supports PROPFIND (directory listing)."""
        response = requests.request(
            "PROPFIND",
            webdav_server["url"],
            auth=(webdav_server["username"], webdav_server["password"]),
            timeout=5
        )
        
        # PROPFIND may return 207 Multi-Status, 200 OK, or 403 Forbidden
        # depending on server configuration
        assert response.status_code in [200, 207, 403]
