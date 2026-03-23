"""
Tests for the comprehensive audit logging feature.

Covers the audit service (recording, querying, SIEM forwarding),
the REST API endpoints, and the admin viewer page.
"""

import base64
import json
import socket
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest
from fastapi import HTTPException
from itsdangerous import TimestampSigner
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

    @patch("app.utils.audit_service.settings")
    def test_query_events_filter_resource_type(self, mock_settings, audit_db):
        """query_events filters by resource_type."""
        mock_settings.audit_siem_enabled = False
        from app.utils.audit_service import query_events, record_event

        record_event(audit_db, action="create", user="sys", resource_type="document")
        record_event(audit_db, action="create", user="sys", resource_type="user")
        results = query_events(audit_db, resource_type="document")
        assert len(results) == 1
        assert results[0].resource_type == "document"

    @patch("app.utils.audit_service.settings")
    def test_query_events_filter_since_and_until(self, mock_settings, audit_db):
        """query_events filters by since and until timestamps."""
        mock_settings.audit_siem_enabled = False
        from app.utils.audit_service import query_events

        # Insert two events directly with distinct timestamps (naive, as SQLite stores them)
        early = AuditLog(user="sys", action="early", severity="info", timestamp=datetime(2020, 1, 1))
        late = AuditLog(user="sys", action="late", severity="info", timestamp=datetime(2025, 1, 1))
        audit_db.add(early)
        audit_db.add(late)
        audit_db.commit()

        since_ts = datetime(2022, 1, 1)
        results = query_events(audit_db, since=since_ts)
        assert all(r.timestamp >= since_ts for r in results)
        assert any(r.action == "late" for r in results)
        assert not any(r.action == "early" for r in results)

        until_ts = datetime(2022, 1, 1)
        results = query_events(audit_db, until=until_ts)
        assert all(r.timestamp <= until_ts for r in results)
        assert any(r.action == "early" for r in results)

    @patch("app.utils.audit_service.settings")
    def test_count_events_filters(self, mock_settings, audit_db):
        """count_events filters by user, resource_type, severity, since, and until."""
        mock_settings.audit_siem_enabled = False
        from app.utils.audit_service import count_events, record_event

        record_event(audit_db, action="a", user="alice", resource_type="doc", severity="info")
        record_event(audit_db, action="b", user="bob", resource_type="user", severity="error")

        assert count_events(audit_db, user="alice") == 1
        assert count_events(audit_db, resource_type="doc") == 1
        assert count_events(audit_db, severity="error") == 1

        early = AuditLog(user="sys", action="early", severity="info", timestamp=datetime(2020, 1, 1))
        late = AuditLog(user="sys", action="late", severity="info", timestamp=datetime(2025, 1, 1))
        audit_db.add(early)
        audit_db.add(late)
        audit_db.commit()

        since_ts = datetime(2022, 1, 1)
        assert count_events(audit_db, since=since_ts) >= 1
        until_ts = datetime(2022, 1, 1)
        assert count_events(audit_db, until=until_ts) >= 1

    @patch("app.utils.audit_service._forward_to_siem")
    @patch("app.utils.audit_service.settings")
    def test_record_event_siem_enabled(self, mock_settings, mock_forward, audit_db):
        """record_event starts SIEM forwarding thread when siem is enabled."""
        mock_settings.audit_siem_enabled = True
        from app.utils.audit_service import record_event

        entry = record_event(audit_db, action="login", user="alice")
        assert entry.id is not None
        mock_forward.assert_called_once()

    @patch("app.utils.audit_service.settings")
    def test_record_event_from_request(self, mock_settings, audit_db):
        """record_event_from_request extracts user and IP from the request."""
        mock_settings.audit_siem_enabled = False
        from app.utils.audit_service import record_event_from_request

        mock_request = MagicMock()
        mock_request.session = {"user": {"preferred_username": "carol"}}
        mock_request.headers = {"X-Forwarded-For": "192.168.1.1"}
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.1"

        with (
            patch("app.utils.audit_service.get_username", return_value="carol"),
            patch("app.utils.audit_service.get_client_ip", return_value="192.168.1.1"),
        ):
            entry = record_event_from_request(
                audit_db,
                mock_request,
                action="document.view",
                resource_type="document",
                resource_id="99",
            )
        assert entry.user == "carol"
        assert entry.ip_address == "192.168.1.1"
        assert entry.action == "document.view"


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

    @patch("app.utils.audit_service.settings")
    @patch("app.utils.audit_service._send_syslog")
    def test_forward_to_siem_syslog(self, mock_send_syslog, mock_settings):
        """_forward_to_siem routes to _send_syslog when transport is syslog."""
        mock_settings.audit_siem_transport = "syslog"
        from app.utils.audit_service import _forward_to_siem

        payload = {"user": "test", "action": "login", "severity": "info"}
        _forward_to_siem(payload)
        mock_send_syslog.assert_called_once_with(payload)

    @patch("app.utils.audit_service.settings")
    @patch("app.utils.audit_service._send_http")
    def test_forward_to_siem_http(self, mock_send_http, mock_settings):
        """_forward_to_siem routes to _send_http when transport is http."""
        mock_settings.audit_siem_transport = "http"
        from app.utils.audit_service import _forward_to_siem

        payload = {"user": "test", "action": "login", "severity": "info"}
        _forward_to_siem(payload)
        mock_send_http.assert_called_once_with(payload)

    @patch("app.utils.audit_service.settings")
    def test_forward_to_siem_unknown_transport(self, mock_settings):
        """_forward_to_siem logs a warning for an unknown transport."""
        mock_settings.audit_siem_transport = "unknown_proto"
        from app.utils.audit_service import _forward_to_siem

        # Should not raise; just log a warning
        _forward_to_siem({"user": "test", "action": "login"})

    @patch("app.utils.audit_service.settings")
    def test_forward_to_siem_exception_is_caught(self, mock_settings):
        """_forward_to_siem catches exceptions from transports and logs them."""
        mock_settings.audit_siem_transport = "syslog"
        from app.utils.audit_service import _forward_to_siem

        with patch("app.utils.audit_service._send_syslog", side_effect=OSError("network error")):
            # Must not propagate
            _forward_to_siem({"user": "test", "action": "login"})

    @patch("app.utils.audit_service.settings")
    @patch("app.utils.audit_service.socket")
    def test_send_syslog_tcp(self, mock_socket_mod, mock_settings):
        """_send_syslog opens a TCP stream socket when protocol is tcp."""
        mock_settings.audit_siem_syslog_protocol = "tcp"
        mock_settings.audit_siem_syslog_host = "127.0.0.1"
        mock_settings.audit_siem_syslog_port = 601

        mock_sock = MagicMock()
        mock_socket_mod.AF_INET = socket.AF_INET
        mock_socket_mod.SOCK_STREAM = socket.SOCK_STREAM
        mock_socket_mod.gethostname.return_value = "test-host"
        mock_socket_mod.socket.return_value.__enter__ = MagicMock(return_value=mock_sock)
        mock_socket_mod.socket.return_value.__exit__ = MagicMock(return_value=False)

        from app.utils.audit_service import _send_syslog

        _send_syslog({"user": "test", "action": "login", "severity": "info", "timestamp": "2026-01-01T00:00:00"})
        mock_sock.connect.assert_called_once()
        mock_sock.sendall.assert_called_once()

    @patch("app.utils.audit_service.settings")
    @patch("app.utils.audit_service.httpx")
    def test_send_http_no_url(self, mock_httpx, mock_settings):
        """_send_http returns early and logs a warning when no URL is configured."""
        mock_settings.audit_siem_http_url = ""
        from app.utils.audit_service import _send_http

        _send_http({"user": "test", "action": "login"})
        mock_httpx.Client.assert_not_called()

    @patch("app.utils.audit_service.settings")
    @patch("app.utils.audit_service.httpx")
    def test_send_http_no_token(self, mock_httpx, mock_settings):
        """_send_http omits Authorization header when no token is configured."""
        mock_settings.audit_siem_http_url = "https://siem.example.com/ingest"
        mock_settings.audit_siem_http_token = ""
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
        assert "Authorization" not in call_kwargs.kwargs["headers"]

    @patch("app.utils.audit_service.settings")
    @patch("app.utils.audit_service.httpx")
    def test_send_http_custom_headers_valid(self, mock_httpx, mock_settings):
        """_send_http adds valid custom headers."""
        mock_settings.audit_siem_http_url = "https://siem.example.com/ingest"
        mock_settings.audit_siem_http_token = ""
        mock_settings.audit_siem_http_custom_headers = "X-Tenant-ID: acme, X-Source: audit"

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_httpx.Client.return_value.__exit__ = MagicMock(return_value=False)

        from app.utils.audit_service import _send_http

        _send_http({"user": "test", "action": "login"})
        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs["headers"]
        assert headers.get("X-Tenant-ID") == "acme"
        assert headers.get("X-Source") == "audit"

    @patch("app.utils.audit_service.settings")
    @patch("app.utils.audit_service.httpx")
    def test_send_http_custom_headers_invalid_name(self, mock_httpx, mock_settings):
        """_send_http skips custom headers with invalid names."""
        mock_settings.audit_siem_http_url = "https://siem.example.com/ingest"
        mock_settings.audit_siem_http_token = ""
        mock_settings.audit_siem_http_custom_headers = "Bad Header!: value"

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_httpx.Client.return_value.__exit__ = MagicMock(return_value=False)

        from app.utils.audit_service import _send_http

        _send_http({"user": "test", "action": "login"})
        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs["headers"]
        assert "Bad Header!" not in headers

    @patch("app.utils.audit_service.settings")
    @patch("app.utils.audit_service.httpx")
    def test_send_http_custom_headers_protected_name(self, mock_httpx, mock_settings):
        """_send_http skips custom headers that match protected names."""
        mock_settings.audit_siem_http_url = "https://siem.example.com/ingest"
        mock_settings.audit_siem_http_token = ""
        mock_settings.audit_siem_http_custom_headers = "Authorization: evil-token"

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_httpx.Client.return_value.__exit__ = MagicMock(return_value=False)

        from app.utils.audit_service import _send_http

        _send_http({"user": "test", "action": "login"})
        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs["headers"]
        # Authorization should not have been overwritten by the custom header
        assert headers.get("Authorization") != "evil-token"

    @patch("app.utils.audit_service.settings")
    @patch("app.utils.audit_service.httpx")
    def test_send_http_custom_headers_no_colon(self, mock_httpx, mock_settings):
        """_send_http ignores custom header entries that contain no colon separator."""
        mock_settings.audit_siem_http_url = "https://siem.example.com/ingest"
        mock_settings.audit_siem_http_token = ""
        mock_settings.audit_siem_http_custom_headers = "MalformedHeader"

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_httpx.Client.return_value.__exit__ = MagicMock(return_value=False)

        from app.utils.audit_service import _send_http

        # Should not raise; malformed entry is silently skipped
        _send_http({"user": "test", "action": "login"})
        mock_client.post.assert_called_once()

    @patch("app.utils.audit_service.settings")
    def test_build_siem_payload_no_timestamp(self, mock_settings):
        """_build_siem_payload uses current UTC time when entry.timestamp is None."""
        from app.utils.audit_service import _build_siem_payload

        entry = AuditLog(user="admin", action="login", severity="info")
        entry.timestamp = None  # type: ignore[assignment]
        payload = _build_siem_payload(entry)
        assert "timestamp" in payload
        # Should be a valid ISO timestamp string
        datetime.fromisoformat(payload["timestamp"])


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

_TEST_SESSION_SECRET = "test_secret_key_for_testing_must_be_at_least_32_characters_long"


def _make_admin_session_cookie() -> str:
    """Create a signed session cookie with admin user data for integration tests."""
    session_data = {"user": {"id": "admin", "is_admin": True}}
    signer = TimestampSigner(_TEST_SESSION_SECRET)
    data = base64.b64encode(json.dumps(session_data).encode()).decode("utf-8")
    return signer.sign(data).decode("utf-8")


@pytest.mark.integration
class TestAuditLogView:
    """Test the admin audit-log viewer page."""

    def test_audit_logs_page_loads(self, client):
        """GET /admin/audit-logs returns 200 and renders the template."""
        resp = client.get("/admin/audit-logs")
        assert resp.status_code == 200
        assert "Audit Logs" in resp.text

    def test_audit_logs_page_accessible_with_admin_session(self, client):
        """GET /admin/audit-logs with admin session cookie returns 200."""
        client.cookies.set("session", _make_admin_session_cookie())
        resp = client.get("/admin/audit-logs", follow_redirects=False)
        assert resp.status_code == 200
        assert "Audit Logs" in resp.text

    def test_audit_logs_page_redirects_non_admin(self, client):
        """GET /admin/audit-logs without admin session redirects to home."""
        resp = client.get("/admin/audit-logs", follow_redirects=False)
        assert resp.status_code == 302


@pytest.mark.unit
class TestAuditLogsPageUnit:
    """Unit tests for the audit_logs_page view function (lines 29-43)."""

    @patch("app.views.audit_logs.templates")
    @patch("app.views.audit_logs.settings")
    @pytest.mark.asyncio
    async def test_audit_logs_page_siem_disabled(self, mock_settings, mock_templates):
        """Renders the template with siem_transport=None when SIEM is disabled."""
        from app.views.audit_logs import audit_logs_page

        mock_settings.audit_siem_enabled = False
        mock_settings.version = "2.0.0"

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        await audit_logs_page(mock_request, mock_db)

        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][0] == "audit_logs.html"
        context = call_args[0][1]
        assert context["siem_enabled"] is False
        assert context["siem_transport"] is None
        assert context["app_version"] == "2.0.0"

    @patch("app.views.audit_logs.templates")
    @patch("app.views.audit_logs.settings")
    @pytest.mark.asyncio
    async def test_audit_logs_page_siem_enabled(self, mock_settings, mock_templates):
        """Renders the template with siem_transport set when SIEM is enabled."""
        from app.views.audit_logs import audit_logs_page

        mock_settings.audit_siem_enabled = True
        mock_settings.audit_siem_transport = "syslog"
        mock_settings.version = "2.0.0"

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        await audit_logs_page(mock_request, mock_db)

        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["siem_enabled"] is True
        assert context["siem_transport"] == "syslog"

    @patch("app.views.audit_logs.settings")
    @pytest.mark.asyncio
    async def test_audit_logs_page_raises_500_on_error(self, mock_settings):
        """Raises HTTP 500 when an unexpected error occurs while loading the page."""
        from app.views.audit_logs import audit_logs_page

        # Make accessing audit_siem_enabled raise an exception to trigger the except branch
        type(mock_settings).audit_siem_enabled = PropertyMock(side_effect=RuntimeError("settings unavailable"))

        mock_request = Mock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}
        mock_db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await audit_logs_page(mock_request, mock_db)
        assert exc_info.value.status_code == 500
        assert "Failed to load audit logs page" in exc_info.value.detail
