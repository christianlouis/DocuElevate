"""
Tests for the comprehensive audit logging feature.

Covers the audit service (recording, querying, SIEM forwarding),
the REST API endpoints, and the admin viewer page.
"""

import json
import socket
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AuditLog

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def audit_db():
    """Fresh in-memory database with all tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAuditLogModel:
    """Verify the AuditLog ORM model."""

    def test_create_minimal_entry(self, audit_db):
        """Minimal required fields can be persisted."""
        entry = AuditLog(user="alice", action="login")
        audit_db.add(entry)
        audit_db.commit()
        audit_db.refresh(entry)
        assert entry.id is not None
        assert entry.user == "alice"
        assert entry.action == "login"
        assert entry.severity == "info"  # server default

    def test_create_full_entry(self, audit_db):
        """All columns persist correctly."""
        entry = AuditLog(
            user="bob",
            action="document.create",
            resource_type="document",
            resource_id="42",
            ip_address="10.0.0.1",
            details='{"filename": "invoice.pdf"}',
            severity="warning",
        )
        audit_db.add(entry)
        audit_db.commit()
        audit_db.refresh(entry)
        assert entry.resource_type == "document"
        assert entry.resource_id == "42"
        assert entry.ip_address == "10.0.0.1"
        assert json.loads(entry.details) == {"filename": "invoice.pdf"}
        assert entry.severity == "warning"


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAuditService:
    """Verify the audit_service helper functions."""

    @patch("app.utils.audit_service.settings")
    def test_record_event(self, mock_settings, audit_db):
        """record_event persists a row and returns the entry."""
        mock_settings.audit_siem_enabled = False
        from app.utils.audit_service import record_event

        entry = record_event(
            audit_db,
            action="settings.update",
            user="admin",
            resource_type="settings",
            resource_id="openai_model",
            details={"old": "gpt-4", "new": "gpt-4o"},
        )
        assert entry.id is not None
        assert entry.action == "settings.update"
        assert entry.user == "admin"

    @patch("app.utils.audit_service.settings")
    def test_query_events_no_filter(self, mock_settings, audit_db):
        """query_events returns all events when no filter is supplied."""
        mock_settings.audit_siem_enabled = False
        from app.utils.audit_service import query_events, record_event

        for i in range(5):
            record_event(audit_db, action=f"action_{i}", user="sys")
        results = query_events(audit_db)
        assert len(results) == 5

    @patch("app.utils.audit_service.settings")
    def test_query_events_filter_action(self, mock_settings, audit_db):
        """query_events filters by action."""
        mock_settings.audit_siem_enabled = False
        from app.utils.audit_service import query_events, record_event

        record_event(audit_db, action="login", user="alice")
        record_event(audit_db, action="logout", user="alice")
        results = query_events(audit_db, action="login")
        assert len(results) == 1
        assert results[0].action == "login"

    @patch("app.utils.audit_service.settings")
    def test_query_events_filter_user(self, mock_settings, audit_db):
        """query_events filters by user."""
        mock_settings.audit_siem_enabled = False
        from app.utils.audit_service import query_events, record_event

        record_event(audit_db, action="login", user="alice")
        record_event(audit_db, action="login", user="bob")
        results = query_events(audit_db, user="bob")
        assert len(results) == 1

    @patch("app.utils.audit_service.settings")
    def test_query_events_filter_severity(self, mock_settings, audit_db):
        """query_events filters by severity."""
        mock_settings.audit_siem_enabled = False
        from app.utils.audit_service import query_events, record_event

        record_event(audit_db, action="fail", user="sys", severity="error")
        record_event(audit_db, action="ok", user="sys", severity="info")
        results = query_events(audit_db, severity="error")
        assert len(results) == 1
        assert results[0].severity == "error"

    @patch("app.utils.audit_service.settings")
    def test_count_events(self, mock_settings, audit_db):
        """count_events returns the correct total."""
        mock_settings.audit_siem_enabled = False
        from app.utils.audit_service import count_events, record_event

        for _ in range(3):
            record_event(audit_db, action="ping", user="sys")
        assert count_events(audit_db) == 3
        assert count_events(audit_db, action="ping") == 3
        assert count_events(audit_db, action="pong") == 0

    @patch("app.utils.audit_service.settings")
    def test_query_events_pagination(self, mock_settings, audit_db):
        """query_events respects limit and offset."""
        mock_settings.audit_siem_enabled = False
        from app.utils.audit_service import query_events, record_event

        for i in range(10):
            record_event(audit_db, action=f"a{i}", user="sys")
        page1 = query_events(audit_db, limit=3, offset=0)
        page2 = query_events(audit_db, limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0].id != page2[0].id


# ---------------------------------------------------------------------------
# SIEM forwarding tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSIEMForwarding:
    """Verify SIEM transport helpers."""

    @patch("app.utils.audit_service.settings")
    def test_build_siem_payload(self, mock_settings):
        """_build_siem_payload returns a dict with all expected keys."""
        from app.utils.audit_service import _build_siem_payload

        entry = AuditLog(
            id=1,
            user="admin",
            action="login",
            resource_type="session",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            severity="info",
        )
        payload = _build_siem_payload(entry)
        assert payload["user"] == "admin"
        assert payload["action"] == "login"
        assert payload["source"] == "docuelevate"
        assert "timestamp" in payload

    @patch("app.utils.audit_service.settings")
    @patch("app.utils.audit_service.socket")
    def test_send_syslog_udp(self, mock_socket_mod, mock_settings):
        """_send_syslog sends a UDP datagram to the configured host."""
        mock_settings.audit_siem_syslog_protocol = "udp"
        mock_settings.audit_siem_syslog_host = "127.0.0.1"
        mock_settings.audit_siem_syslog_port = 5140

        mock_sock = MagicMock()
        mock_socket_mod.AF_INET = socket.AF_INET
        mock_socket_mod.SOCK_DGRAM = socket.SOCK_DGRAM
        mock_socket_mod.gethostname.return_value = "test-host"
        mock_socket_mod.socket.return_value.__enter__ = MagicMock(return_value=mock_sock)
        mock_socket_mod.socket.return_value.__exit__ = MagicMock(return_value=False)

        from app.utils.audit_service import _send_syslog

        _send_syslog({"user": "test", "action": "login", "severity": "info", "timestamp": "2026-01-01T00:00:00"})
        mock_sock.sendto.assert_called_once()

    @patch("app.utils.audit_service.settings")
    @patch("app.utils.audit_service.httpx")
    def test_send_http_generic(self, mock_httpx, mock_settings):
        """_send_http POSTs JSON to a generic endpoint."""
        mock_settings.audit_siem_http_url = "https://siem.example.com/ingest"
        mock_settings.audit_siem_http_token = "my-token"
        mock_settings.audit_siem_http_custom_headers = ""

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_httpx.Client.return_value.__exit__ = MagicMock(return_value=False)

        from app.utils.audit_service import _send_http

        _send_http({"user": "test", "action": "login"})
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer my-token"

    @patch("app.utils.audit_service.settings")
    @patch("app.utils.audit_service.httpx")
    def test_send_http_splunk_hec(self, mock_httpx, mock_settings):
        """_send_http wraps payload in Splunk HEC envelope when URL contains /services/collector."""
        mock_settings.audit_siem_http_url = "https://splunk:8088/services/collector/event"
        mock_settings.audit_siem_http_token = "hec-token"
        mock_settings.audit_siem_http_custom_headers = ""

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_httpx.Client.return_value.__exit__ = MagicMock(return_value=False)

        from app.utils.audit_service import _send_http

        _send_http({"user": "test", "action": "login"})
        call_kwargs = mock_client.post.call_args
        body = call_kwargs.kwargs["json"]
        assert "event" in body
        assert body["sourcetype"] == "docuelevate:audit"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAuditLogAPI:
    """Test /api/audit-logs REST endpoints."""

    def test_list_audit_logs_empty(self, client):
        """GET /api/audit-logs returns empty list when no events exist."""
        resp = client.get("/api/audit-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_audit_logs_with_data(self, client, db_session):
        """GET /api/audit-logs returns recorded events."""
        entry = AuditLog(user="tester", action="test.action", severity="info")
        db_session.add(entry)
        db_session.commit()

        resp = client.get("/api/audit-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["action"] == "test.action"

    def test_list_audit_logs_filter_by_action(self, client, db_session):
        """GET /api/audit-logs?action=x filters correctly."""
        db_session.add(AuditLog(user="a", action="login", severity="info"))
        db_session.add(AuditLog(user="a", action="logout", severity="info"))
        db_session.commit()

        resp = client.get("/api/audit-logs?action=login")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_list_distinct_actions(self, client, db_session):
        """GET /api/audit-logs/actions returns distinct action values."""
        db_session.add(AuditLog(user="a", action="login", severity="info"))
        db_session.add(AuditLog(user="b", action="login", severity="info"))
        db_session.add(AuditLog(user="a", action="logout", severity="info"))
        db_session.commit()

        resp = client.get("/api/audit-logs/actions")
        assert resp.status_code == 200
        actions = resp.json()
        assert set(actions) == {"login", "logout"}

    def test_list_distinct_users(self, client, db_session):
        """GET /api/audit-logs/users returns distinct user values."""
        db_session.add(AuditLog(user="alice", action="x", severity="info"))
        db_session.add(AuditLog(user="bob", action="x", severity="info"))
        db_session.commit()

        resp = client.get("/api/audit-logs/users")
        assert resp.status_code == 200
        users = resp.json()
        assert set(users) == {"alice", "bob"}

    def test_list_audit_logs_pagination(self, client, db_session):
        """GET /api/audit-logs supports limit/offset pagination."""
        for i in range(5):
            db_session.add(AuditLog(user="u", action=f"a{i}", severity="info"))
        db_session.commit()

        resp = client.get("/api/audit-logs?limit=2&offset=0")
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5


# ---------------------------------------------------------------------------
# View tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAuditLogView:
    """Test the admin audit-log viewer page."""

    def test_audit_logs_page_loads(self, client):
        """GET /admin/audit-logs returns 200 and renders the template."""
        resp = client.get("/admin/audit-logs")
        assert resp.status_code == 200
        assert "Audit Logs" in resp.text
