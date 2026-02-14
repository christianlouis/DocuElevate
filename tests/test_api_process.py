"""Tests for app/api/process.py module."""

from unittest.mock import Mock, patch

import pytest


@pytest.mark.integration
class TestProcessEndpoints:
    """Tests for process API endpoints."""

    def test_process_file_not_found(self, client):
        """Test POST /api/process/ with non-existent file."""
        response = client.post("/api/process/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_process_file_success(self, client, tmp_path):
        """Test POST /api/process/ with existing file."""
        # Create a test file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        with patch("app.api.process.process_document") as mock_task:
            mock_task.delay.return_value = Mock(id="test-task-id")
            response = client.post(f"/api/process/?file_path={test_file}")
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "test-task-id"
            assert data["status"] == "queued"
            mock_task.delay.assert_called_once_with(str(test_file))

    def test_send_to_dropbox_file_not_found(self, client):
        """Test POST /api/send_to_dropbox/ with non-existent file."""
        response = client.post("/api/send_to_dropbox/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_send_to_dropbox_success(self, client, tmp_path):
        """Test POST /api/send_to_dropbox/ with existing file."""
        test_file = tmp_path / "processed" / "test.pdf"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("test content")

        with patch("app.api.process.upload_to_dropbox") as mock_task:
            mock_task.delay.return_value = Mock(id="test-task-id")
            response = client.post(f"/api/send_to_dropbox/?file_path={test_file}")
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "test-task-id"
            assert data["status"] == "queued"

    def test_send_to_paperless_file_not_found(self, client):
        """Test POST /api/send_to_paperless/ with non-existent file."""
        response = client.post("/api/send_to_paperless/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_send_to_paperless_success(self, client, tmp_path):
        """Test POST /api/send_to_paperless/ with existing file."""
        test_file = tmp_path / "processed" / "test.pdf"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("test content")

        with patch("app.api.process.upload_to_paperless") as mock_task:
            mock_task.delay.return_value = Mock(id="test-task-id")
            response = client.post(f"/api/send_to_paperless/?file_path={test_file}")
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "test-task-id"
            assert data["status"] == "queued"

    def test_send_to_nextcloud_file_not_found(self, client):
        """Test POST /api/send_to_nextcloud/ with non-existent file."""
        response = client.post("/api/send_to_nextcloud/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_send_to_nextcloud_success(self, client, tmp_path):
        """Test POST /api/send_to_nextcloud/ with existing file."""
        test_file = tmp_path / "processed" / "test.pdf"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("test content")

        with patch("app.api.process.upload_to_nextcloud") as mock_task:
            mock_task.delay.return_value = Mock(id="test-task-id")
            response = client.post(f"/api/send_to_nextcloud/?file_path={test_file}")
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "test-task-id"
            assert data["status"] == "queued"

    def test_send_to_google_drive_file_not_found(self, client):
        """Test POST /api/send_to_google_drive/ with non-existent file."""
        response = client.post("/api/send_to_google_drive/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_send_to_google_drive_success(self, client, tmp_path):
        """Test POST /api/send_to_google_drive/ with existing file."""
        test_file = tmp_path / "processed" / "test.pdf"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("test content")

        with patch("app.api.process.upload_to_google_drive") as mock_task:
            mock_task.delay.return_value = Mock(id="test-task-id")
            response = client.post(f"/api/send_to_google_drive/?file_path={test_file}")
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "test-task-id"
            assert data["status"] == "queued"

    def test_send_to_onedrive_file_not_found(self, client):
        """Test POST /api/send_to_onedrive/ with non-existent file."""
        response = client.post("/api/send_to_onedrive/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_send_to_onedrive_success(self, client, tmp_path):
        """Test POST /api/send_to_onedrive/ with existing file."""
        test_file = tmp_path / "processed" / "test.pdf"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("test content")

        with patch("app.api.process.upload_to_onedrive") as mock_task:
            mock_task.delay.return_value = Mock(id="test-task-id")
            response = client.post(f"/api/send_to_onedrive/?file_path={test_file}")
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "test-task-id"
            assert data["status"] == "queued"

    def test_send_to_all_destinations_file_not_found(self, client):
        """Test POST /api/send_to_all_destinations/ with non-existent file."""
        response = client.post("/api/send_to_all_destinations/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_send_to_all_destinations_success(self, client, tmp_path):
        """Test POST /api/send_to_all_destinations/ with existing file."""
        test_file = tmp_path / "processed" / "test.pdf"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("test content")

        with patch("app.api.process.send_to_all_destinations") as mock_task:
            mock_task.delay.return_value = Mock(id="test-task-id")
            response = client.post(f"/api/send_to_all_destinations/?file_path={test_file}")
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "test-task-id"
            assert data["status"] == "queued"
            assert data["file_path"] == str(test_file)

    def test_processall_endpoint_empty_dir(self, client, tmp_path):
        """Test POST /api/processall with no PDF files in workdir."""
        with patch("app.api.process.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            response = client.post("/api/processall")
            assert response.status_code == 200
            data = response.json()
            assert "No PDF files found" in data["message"]

    def test_processall_endpoint_nonexistent_dir(self, client, tmp_path):
        """Test POST /api/processall with nonexistent workdir."""
        with patch("app.api.process.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path / "nonexistent")
            response = client.post("/api/processall")
            assert response.status_code == 400
            assert "does not exist" in response.json()["detail"]

    def test_processall_single_file_no_throttle(self, client, tmp_path):
        """Test POST /api/processall with single PDF file (no throttling)."""
        # Create a PDF file
        test_file = tmp_path / "test1.pdf"
        test_file.write_text("test content")

        with patch("app.api.process.settings") as mock_settings, patch("app.api.process.process_document") as mock_task:
            mock_settings.workdir = str(tmp_path)
            mock_settings.processall_throttle_threshold = 10
            mock_task.delay.return_value = Mock(id="task-1")

            response = client.post("/api/processall")
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Enqueued 1 PDFs for processing"
            assert len(data["pdf_files"]) == 1
            assert "test1.pdf" in data["pdf_files"]
            assert len(data["task_ids"]) == 1
            assert data["throttled"] is False
            mock_task.delay.assert_called_once()

    def test_processall_multiple_files_no_throttle(self, client, tmp_path):
        """Test POST /api/processall with multiple files below threshold."""
        # Create 3 PDF files
        for i in range(3):
            (tmp_path / f"test{i}.pdf").write_text(f"test content {i}")

        with patch("app.api.process.settings") as mock_settings, patch("app.api.process.process_document") as mock_task:
            mock_settings.workdir = str(tmp_path)
            mock_settings.processall_throttle_threshold = 10
            mock_task.delay.return_value = Mock(id="task-id")

            response = client.post("/api/processall")
            assert response.status_code == 200
            data = response.json()
            assert "Enqueued 3 PDFs for processing" in data["message"]
            assert len(data["pdf_files"]) == 3
            assert len(data["task_ids"]) == 3
            assert data["throttled"] is False
            assert mock_task.delay.call_count == 3

    def test_processall_with_throttling(self, client, tmp_path):
        """Test POST /api/processall with throttling enabled."""
        # Create 12 PDF files (above threshold of 10)
        for i in range(12):
            (tmp_path / f"test{i}.pdf").write_text(f"test content {i}")

        with patch("app.api.process.settings") as mock_settings, patch("app.api.process.process_document") as mock_task:
            mock_settings.workdir = str(tmp_path)
            mock_settings.processall_throttle_threshold = 10
            mock_settings.processall_throttle_delay = 5
            mock_task.apply_async.return_value = Mock(id="task-id")

            response = client.post("/api/processall")
            assert response.status_code == 200
            data = response.json()
            assert "Enqueued 12 PDFs for processing" in data["message"]
            assert "(throttled over 55 seconds)" in data["message"]
            assert len(data["pdf_files"]) == 12
            assert len(data["task_ids"]) == 12
            assert data["throttled"] is True
            assert mock_task.apply_async.call_count == 12

            # Verify countdown values
            calls = mock_task.apply_async.call_args_list
            for idx, call in enumerate(calls):
                assert call[1]["countdown"] == idx * 5

    def test_processall_ignores_non_pdf_files(self, client, tmp_path):
        """Test that processall only processes PDF files."""
        # Create mixed files
        (tmp_path / "test1.pdf").write_text("pdf content")
        (tmp_path / "test2.PDF").write_text("pdf content uppercase")
        (tmp_path / "test.txt").write_text("text content")
        (tmp_path / "test.docx").write_text("word content")
        (tmp_path / "test.jpg").write_text("image content")

        with patch("app.api.process.settings") as mock_settings, patch("app.api.process.process_document") as mock_task:
            mock_settings.workdir = str(tmp_path)
            mock_settings.processall_throttle_threshold = 10
            mock_task.delay.return_value = Mock(id="task-id")

            response = client.post("/api/processall")
            assert response.status_code == 200
            data = response.json()
            # Should process 2 PDF files (case-insensitive)
            assert len(data["pdf_files"]) == 2
            assert "test1.pdf" in data["pdf_files"]
            assert "test2.PDF" in data["pdf_files"]
            assert mock_task.delay.call_count == 2

    def test_processall_threshold_boundary(self, client, tmp_path):
        """Test processall at throttling threshold boundary."""
        threshold = 5

        # Test exactly at threshold (should not throttle)
        for i in range(threshold):
            (tmp_path / f"at_threshold_{i}.pdf").write_text(f"content {i}")

        with patch("app.api.process.settings") as mock_settings, patch("app.api.process.process_document") as mock_task:
            mock_settings.workdir = str(tmp_path)
            mock_settings.processall_throttle_threshold = threshold
            mock_settings.processall_throttle_delay = 2
            mock_task.delay.return_value = Mock(id="task-id")

            response = client.post("/api/processall")
            assert response.status_code == 200
            data = response.json()
            assert data["throttled"] is False
            assert mock_task.delay.call_count == threshold

        # Clean up and test above threshold (should throttle)
        for f in tmp_path.glob("*.pdf"):
            f.unlink()

        for i in range(threshold + 1):
            (tmp_path / f"above_threshold_{i}.pdf").write_text(f"content {i}")

        with patch("app.api.process.settings") as mock_settings, patch("app.api.process.process_document") as mock_task:
            mock_settings.workdir = str(tmp_path)
            mock_settings.processall_throttle_threshold = threshold
            mock_settings.processall_throttle_delay = 2
            mock_task.apply_async.return_value = Mock(id="task-id")

            response = client.post("/api/processall")
            assert response.status_code == 200
            data = response.json()
            assert data["throttled"] is True
            assert mock_task.apply_async.call_count == threshold + 1
