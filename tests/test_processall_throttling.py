"""
Tests for /processall endpoint throttling behavior.
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestProcessAllThrottling:
    """Tests for processall endpoint with throttling."""

    @patch('app.api.process.process_document')
    def test_processall_no_throttling_for_small_batch(self, mock_task, client: TestClient, tmp_path, monkeypatch):
        """Test that small batches (<=20 files) are not throttled."""
        # Create test directory with 10 PDF files
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        
        for i in range(10):
            (workdir / f"test{i}.pdf").write_text("dummy pdf content")
        
        # Mock the task
        mock_task.delay = Mock(return_value=Mock(id="task-id"))
        mock_task.apply_async = Mock(return_value=Mock(id="task-id"))
        
        # Use monkeypatch to modify the settings imported in the process module
        from app.api import process
        monkeypatch.setattr(process.settings, 'workdir', str(workdir))
        monkeypatch.setattr(process.settings, 'processall_throttle_threshold', 20)
        monkeypatch.setattr(process.settings, 'processall_throttle_delay', 3)
            
        response = client.post("/api/processall")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should use .delay() (not throttled)
        assert mock_task.delay.call_count == 10
        assert mock_task.apply_async.call_count == 0
        
        # Response should indicate no throttling
        assert data["throttled"] is False
        assert len(data["pdf_files"]) == 10
        assert len(data["task_ids"]) == 10

    @patch('app.api.process.process_document')
    def test_processall_throttling_for_large_batch(self, mock_task, client: TestClient, tmp_path, monkeypatch):
        """Test that large batches (>20 files) are throttled."""
        # Create test directory with 25 PDF files
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        
        for i in range(25):
            (workdir / f"test{i}.pdf").write_text("dummy pdf content")
        
        # Mock the task
        mock_task_result = Mock(id="task-id")
        mock_task.apply_async = Mock(return_value=mock_task_result)
        
        from app.api import process
        monkeypatch.setattr(process.settings, 'workdir', str(workdir))
        monkeypatch.setattr(process.settings, 'processall_throttle_threshold', 20)
        monkeypatch.setattr(process.settings, 'processall_throttle_delay', 3)
            
        response = client.post("/api/processall")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should use .apply_async() with countdown (throttled)
        assert mock_task.apply_async.call_count == 25
        
        # Verify countdown values are increasing
        calls = mock_task.apply_async.call_args_list
        for i, call_args in enumerate(calls):
            expected_countdown = i * 3  # 3 seconds delay
            assert call_args[1]['countdown'] == expected_countdown
        
        # Response should indicate throttling
        assert data["throttled"] is True
        assert len(data["pdf_files"]) == 25
        assert len(data["task_ids"]) == 25
        assert "throttled over" in data["message"]

    @patch('app.api.process.process_document')
    def test_processall_exactly_at_threshold(self, mock_task, client: TestClient, tmp_path, monkeypatch):
        """Test behavior when file count equals threshold."""
        # Create test directory with exactly 20 PDF files
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        
        for i in range(20):
            (workdir / f"test{i}.pdf").write_text("dummy pdf content")
        
        # Mock the task
        mock_task.delay = Mock(return_value=Mock(id="task-id"))
        
        from app.api import process
        monkeypatch.setattr(process.settings, 'workdir', str(workdir))
        monkeypatch.setattr(process.settings, 'processall_throttle_threshold', 20)
        monkeypatch.setattr(process.settings, 'processall_throttle_delay', 3)
            
        response = client.post("/api/processall")
        
        assert response.status_code == 200
        data = response.json()
        
        # At threshold, should NOT throttle (only >threshold)
        assert mock_task.delay.call_count == 20
        assert data["throttled"] is False

    @patch('app.api.process.process_document')
    def test_processall_one_over_threshold(self, mock_task, client: TestClient, tmp_path, monkeypatch):
        """Test that throttling activates at threshold + 1."""
        # Create test directory with 21 PDF files (threshold is 20)
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        
        for i in range(21):
            (workdir / f"test{i}.pdf").write_text("dummy pdf content")
        
        # Mock the task
        mock_task.apply_async = Mock(return_value=Mock(id="task-id"))
        
        from app.api import process
        monkeypatch.setattr(process.settings, 'workdir', str(workdir))
        monkeypatch.setattr(process.settings, 'processall_throttle_threshold', 20)
        monkeypatch.setattr(process.settings, 'processall_throttle_delay', 3)
            
        response = client.post("/api/processall")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be throttled
        assert mock_task.apply_async.call_count == 21
        assert data["throttled"] is True

    def test_processall_empty_directory(self, client: TestClient, tmp_path, monkeypatch):
        """Test processall with no PDF files."""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        
        from app.api import process
        monkeypatch.setattr(process.settings, 'workdir', str(workdir))
            
        response = client.post("/api/processall")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "No PDF files found in that directory."

    def test_processall_nonexistent_directory(self, client: TestClient, tmp_path, monkeypatch):
        """Test processall with non-existent directory."""
        workdir = tmp_path / "nonexistent"
        
        from app.api import process
        monkeypatch.setattr(process.settings, 'workdir', str(workdir))
            
        response = client.post("/api/processall")
        
        assert response.status_code == 400
        data = response.json()
        assert "does not exist" in data["detail"]

    @patch('app.api.process.process_document')
    def test_processall_custom_threshold(self, mock_task, client: TestClient, tmp_path, monkeypatch):
        """Test that custom threshold value is respected."""
        # Create test directory with 15 PDF files
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        
        for i in range(15):
            (workdir / f"test{i}.pdf").write_text("dummy pdf content")
        
        # Mock the task
        mock_task.apply_async = Mock(return_value=Mock(id="task-id"))
        
        from app.api import process
        monkeypatch.setattr(process.settings, 'workdir', str(workdir))
        monkeypatch.setattr(process.settings, 'processall_throttle_threshold', 10)  # Lower threshold
        monkeypatch.setattr(process.settings, 'processall_throttle_delay', 2)
            
        response = client.post("/api/processall")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be throttled because 15 > 10
        assert mock_task.apply_async.call_count == 15
        assert data["throttled"] is True


@pytest.mark.unit
class TestThrottlingConfiguration:
    """Tests for throttling configuration settings."""

    def test_default_throttle_threshold(self):
        """Test that default threshold is 20."""
        from app.config import Settings
        settings = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost",
            openai_api_key="test-key",
            workdir="/tmp",
            azure_ai_key="test-key",
            azure_region="test-region",
            azure_endpoint="https://test.endpoint",
            gotenberg_url="http://gotenberg",
            session_secret="a" * 32,
        )
        assert settings.processall_throttle_threshold == 20

    def test_default_throttle_delay(self):
        """Test that default delay is 3 seconds."""
        from app.config import Settings
        settings = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost",
            openai_api_key="test-key",
            workdir="/tmp",
            azure_ai_key="test-key",
            azure_region="test-region",
            azure_endpoint="https://test.endpoint",
            gotenberg_url="http://gotenberg",
            session_secret="a" * 32,
        )
        assert settings.processall_throttle_delay == 3
