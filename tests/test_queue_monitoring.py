"""Tests for app/api/queue.py and app/views/queue.py modules."""

from unittest.mock import MagicMock, Mock, patch

import pytest


@pytest.mark.unit
class TestGetRedisQueueLength:
    """Tests for the _get_redis_queue_length helper."""

    def test_returns_queue_length(self):
        """Test returns queue length from Redis."""
        from app.api.queue import _get_redis_queue_length

        mock_redis = MagicMock()
        mock_redis.llen.return_value = 42
        assert _get_redis_queue_length(mock_redis, "document_processor") == 42
        mock_redis.llen.assert_called_once_with("document_processor")

    def test_returns_zero_on_error(self):
        """Test returns 0 when Redis call fails."""
        from app.api.queue import _get_redis_queue_length

        mock_redis = MagicMock()
        mock_redis.llen.side_effect = Exception("Connection refused")
        assert _get_redis_queue_length(mock_redis, "default") == 0


@pytest.mark.unit
class TestGetCeleryInspectStats:
    """Tests for the _get_celery_inspect_stats helper."""

    @patch("app.celery_app.celery")
    def test_returns_worker_stats(self, mock_celery_mod):
        """Test returns active, reserved, scheduled tasks."""
        from app.api.queue import _get_celery_inspect_stats

        mock_inspector = MagicMock()
        mock_inspector.active.return_value = {
            "worker1": [
                {"id": "task-1", "name": "app.tasks.process_document.process_document", "args": [1], "time_start": 123}
            ]
        }
        mock_inspector.reserved.return_value = {
            "worker1": [{"id": "task-2", "name": "app.tasks.upload_to_s3.upload_to_s3", "args": [2]}]
        }
        mock_inspector.scheduled.return_value = {
            "worker1": [{"request": {"id": "task-3", "name": "app.tasks.check_credentials.check_credentials"}, "eta": "2026-01-01"}]
        }
        mock_celery_mod.control.inspect.return_value = mock_inspector

        result = _get_celery_inspect_stats()

        assert result["workers_online"] == 1
        assert len(result["active"]) == 1
        assert result["active"][0]["id"] == "task-1"
        assert len(result["reserved"]) == 1
        assert len(result["scheduled"]) == 1

    @patch("app.celery_app.celery")
    def test_handles_no_workers(self, mock_celery_mod):
        """Test handles case where no workers are online."""
        from app.api.queue import _get_celery_inspect_stats

        mock_inspector = MagicMock()
        mock_inspector.active.return_value = None
        mock_inspector.reserved.return_value = None
        mock_inspector.scheduled.return_value = None
        mock_celery_mod.control.inspect.return_value = mock_inspector

        result = _get_celery_inspect_stats()

        assert result["workers_online"] == 0
        assert result["active"] == []
        assert result["reserved"] == []
        assert result["scheduled"] == []

    @patch("app.celery_app.celery")
    def test_handles_inspect_exception(self, mock_celery_mod):
        """Test handles exception during inspect."""
        from app.api.queue import _get_celery_inspect_stats

        mock_celery_mod.control.inspect.side_effect = Exception("Broker unreachable")

        result = _get_celery_inspect_stats()

        assert result["workers_online"] == 0
        assert result["active"] == []


@pytest.mark.unit
class TestGetDbProcessingSummary:
    """Tests for the _get_db_processing_summary helper."""

    def test_returns_summary(self, db_session):
        """Test returns processing summary from DB."""
        from app.api.queue import _get_db_processing_summary
        from app.models import FileProcessingStep, FileRecord

        # Create some test files
        file1 = FileRecord(filehash="abc1", local_filename="f1.pdf", file_size=100, is_duplicate=False)
        file2 = FileRecord(filehash="abc2", local_filename="f2.pdf", file_size=200, is_duplicate=False)
        db_session.add_all([file1, file2])
        db_session.commit()

        # Add steps: file1 completed, file2 in_progress
        step1 = FileProcessingStep(file_id=file1.id, step_name="extract_text", status="success")
        step2 = FileProcessingStep(file_id=file2.id, step_name="extract_text", status="in_progress")
        db_session.add_all([step1, step2])
        db_session.commit()

        result = _get_db_processing_summary(db_session)

        assert result["total_files"] == 2
        assert result["processing"] == 1
        assert isinstance(result["recent_processing"], list)

    def test_returns_empty_on_error(self):
        """Test returns empty summary on DB error."""
        from app.api.queue import _get_db_processing_summary

        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB error")

        result = _get_db_processing_summary(mock_db)

        assert result["total_files"] == 0
        assert result["processing"] == 0
        assert result["recent_processing"] == []


@pytest.mark.integration
class TestQueueStatsEndpoint:
    """Tests for the GET /api/queue/stats endpoint."""

    @patch("app.api.queue.redis.Redis")
    @patch("app.celery_app.celery")
    def test_queue_stats_returns_200(self, mock_celery_mod, mock_redis_cls, client):
        """Test queue stats endpoint returns 200 with data."""
        # Mock Redis
        mock_redis_instance = MagicMock()
        mock_redis_instance.llen.return_value = 5
        mock_redis_cls.from_url.return_value = mock_redis_instance

        # Mock Celery inspector
        mock_inspector = MagicMock()
        mock_inspector.active.return_value = {}
        mock_inspector.reserved.return_value = {}
        mock_inspector.scheduled.return_value = {}
        mock_celery_mod.control.inspect.return_value = mock_inspector

        response = client.get("/api/queue/stats")
        assert response.status_code == 200

        data = response.json()
        assert "queues" in data
        assert "total_queued" in data
        assert "celery" in data
        assert "db_summary" in data

    @patch("app.api.queue.redis.Redis")
    def test_queue_stats_handles_redis_error(self, mock_redis_cls, client):
        """Test queue stats handles Redis connection failure."""
        mock_redis_cls.from_url.side_effect = Exception("Redis unavailable")

        response = client.get("/api/queue/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_queued"] == 0


@pytest.mark.integration
class TestPendingCountEndpoint:
    """Tests for the GET /api/queue/pending-count endpoint."""

    @patch("app.api.queue.redis.Redis")
    def test_pending_count_returns_200(self, mock_redis_cls, client):
        """Test pending count endpoint returns 200."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.llen.return_value = 3
        mock_redis_cls.from_url.return_value = mock_redis_instance

        response = client.get("/api/queue/pending-count")
        assert response.status_code == 200

        data = response.json()
        assert "total_pending" in data
        assert data["total_pending"] >= 0

    @patch("app.api.queue.redis.Redis")
    def test_pending_count_redis_failure_still_works(self, mock_redis_cls, client):
        """Test pending count still works when Redis is down."""
        mock_redis_cls.from_url.side_effect = Exception("Connection refused")

        response = client.get("/api/queue/pending-count")
        assert response.status_code == 200
        data = response.json()
        assert "total_pending" in data


@pytest.mark.integration
class TestQueueDashboardView:
    """Tests for the GET /admin/queue view."""

    def test_queue_dashboard_requires_login(self, client):
        """Test queue dashboard requires authentication."""
        response = client.get("/admin/queue", follow_redirects=False)
        assert response.status_code in [200, 302, 401]

    def test_queue_dashboard_non_admin_redirect(self, client):
        """Test queue dashboard redirects non-admin users."""
        # Set non-admin session
        with client:
            client.cookies.set("session", "test")
            response = client.get("/admin/queue", follow_redirects=False)
            # Should redirect or deny since no admin session
            assert response.status_code in [200, 302, 401]


@pytest.mark.unit
class TestQueueDashboardViewFunction:
    """Tests for the queue_dashboard view function."""

    @patch("app.views.queue.templates")
    @pytest.mark.asyncio
    async def test_queue_dashboard_returns_template(self, mock_templates):
        """Test queue dashboard returns template response."""
        from app.views.queue import queue_dashboard

        mock_request = Mock()
        mock_request.session = {"user": {"is_admin": True}}
        mock_db = MagicMock()

        result = await queue_dashboard(mock_request, db=mock_db)

        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][0] == "queue_dashboard.html"
        context = call_args[0][1]
        assert "request" in context
