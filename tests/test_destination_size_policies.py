"""Focused boundary tests for destination size policies."""

from email import message_from_bytes
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.api.integrations import _validate_destination_size_config
from app.models import DestinationDeliveryPart, FileRecord, IntegrationType, UserIntegration
from app.tasks.upload_to_user_integration import (
    DestinationDeliveryUncertain,
    DestinationSizeLimitError,
    _effective_size_config,
    _upload_email,
)


def _smtp(*, size: str | None = None):
    server = MagicMock()
    server.esmtp_features = {} if size is None else {"size": size}
    server.sendmail.return_value = {}
    server.__enter__.return_value = server
    server.__exit__.return_value = False
    return server


def _cfg(**extra):
    value = {
        "host": "smtp.example.test",
        "sender": "sender@example.test",
        "recipient": "recipient@example.test",
        "use_tls": False,
    }
    value.update(extra)
    return value


def _ledger_ids(db_session, path):
    record = FileRecord(
        owner_id="owner",
        filehash="delivery-test-file",
        local_filename=str(path),
        file_size=path.stat().st_size,
    )
    integration = UserIntegration(
        owner_id="owner",
        direction="DESTINATION",
        integration_type=IntegrationType.EMAIL,
        name="Delivery test email",
    )
    db_session.add_all((record, integration))
    db_session.commit()
    return record.id, integration.id


def _ledger_factory(db_session):
    return sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind())


def test_smtp_size_zero_is_unlimited_and_mime_is_crlf(tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"payload")
    server = _smtp(size="0")
    with patch("smtplib.SMTP", return_value=server):
        result = _upload_email(str(path), _cfg(), {}, "task")
    assert result["status"] == "Completed"
    payload = server.sendmail.call_args.args[2]
    assert isinstance(payload, str)
    assert "\r\n" in payload
    assert len(payload.encode("ascii")) == result["message_size_bytes"]
    parsed = message_from_bytes(payload.encode("ascii"))
    assert parsed.get_payload()[1].get_payload(decode=True) == b"payload"


def test_configured_cap_blocks_before_send(tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"payload")
    server = _smtp()
    with patch("smtplib.SMTP", return_value=server):
        with pytest.raises(DestinationSizeLimitError, match="Serialized email"):
            _upload_email(str(path), _cfg(max_message_size_bytes=20), {}, "task")
    server.sendmail.assert_not_called()


def test_link_policy_requires_https_public_url(tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"payload")
    server = _smtp()
    with patch("smtplib.SMTP", return_value=server):
        with pytest.raises(ValueError, match="HTTPS public URL"):
            _upload_email(
                str(path),
                _cfg(size_policy="link", max_message_size_bytes=20, public_url_base="http://unsafe.test"),
                {},
                "task",
                file_id=42,
            )


def test_552_is_terminal_and_not_fallback(tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"payload")
    server = _smtp()
    error = __import__("smtplib").SMTPDataError(552, b"5.3.4 Message size exceeds fixed limit")
    server.sendmail.side_effect = error
    with patch("smtplib.SMTP", return_value=server):
        with pytest.raises(DestinationSizeLimitError):
            _upload_email(
                str(path), _cfg(size_policy="link", public_url_base="https://safe.test"), {}, "task", file_id=42
            )
    assert server.sendmail.call_count == 1


def test_refused_recipients_are_uncertain(tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"payload")
    server = _smtp()
    server.sendmail.return_value = {"recipient@example.test": (550, b"recipient refused")}
    with patch("smtplib.SMTP", return_value=server):
        with pytest.raises(DestinationDeliveryUncertain):
            _upload_email(str(path), _cfg(), {}, "task")


def test_refused_552_is_size_error_without_fallback(tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"payload")
    server = _smtp()
    server.sendmail.return_value = {"recipient@example.test": (552, b"message too large")}
    with patch("smtplib.SMTP", return_value=server):
        with pytest.raises(DestinationSizeLimitError):
            _upload_email(
                str(path), _cfg(size_policy="link", public_url_base="https://safe.test"), {}, "task", file_id=42
            )
    assert server.sendmail.call_count == 1


def test_split_preflights_all_parts_before_first_send(tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"original")
    server = _smtp(size="500")

    class FakeReader:
        pages = [object(), object()]

    class FakeWriter:
        def add_page(self, _page):
            pass

        def write(self, output):
            output.write(b"page-content")

    fake_pypdf = SimpleNamespace(PdfReader=lambda _path: FakeReader(), PdfWriter=FakeWriter)
    with patch.dict("sys.modules", {"pypdf": fake_pypdf}), patch("smtplib.SMTP", return_value=server):
        with pytest.raises(DestinationSizeLimitError):
            _upload_email(str(path), _cfg(size_policy="split"), {}, "task", file_id=42, integration_id=7)
    server.sendmail.assert_not_called()


def test_api_rejects_bool_cap_and_invalid_notion_split():
    with pytest.raises(Exception):
        _validate_destination_size_config(IntegrationType.EMAIL, {"max_message_size_bytes": True})
    _validate_destination_size_config(IntegrationType.EMAIL, {"size_policy": "split"})
    with pytest.raises(Exception):
        _validate_destination_size_config(IntegrationType.NOTION, {"size_policy": "split"})


def test_source_override_requires_trusted_file_provenance():
    cfg = {"size_policy": "stop", "size_policy_overrides": {"17": {"size_policy": "link"}}}
    assert _effective_size_config(cfg, SimpleNamespace(source_integration_id=None))["size_policy"] == "stop"
    assert _effective_size_config(cfg, SimpleNamespace(source_integration_id=17))["size_policy"] == "link"


def test_accepted_delivery_is_skipped_and_policy_change_is_blocked(db_session, tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"x" * 1024)
    file_id, integration_id = _ledger_ids(db_session, path)
    server = _smtp()
    factory = _ledger_factory(db_session)

    with (
        patch("app.tasks.upload_to_user_integration.SessionLocal", factory),
        patch("smtplib.SMTP", return_value=server),
    ):
        first = _upload_email(str(path), _cfg(), {}, "task", file_id=file_id, integration_id=integration_id)
        repeat = _upload_email(str(path), _cfg(), {}, "task", file_id=file_id, integration_id=integration_id)
        with pytest.raises(DestinationDeliveryUncertain, match="plan changed"):
            _upload_email(
                str(path),
                _cfg(size_policy="link", max_message_size_bytes=1000, public_url_base="https://safe.test"),
                {},
                "task",
                file_id=file_id,
                integration_id=integration_id,
            )

    assert first["sent_parts"] == 1
    assert repeat["sent_parts"] == 0
    assert repeat["already_accepted_parts"] == 1
    assert server.sendmail.call_count == 1
    assert db_session.query(DestinationDeliveryPart).one().status == "accepted"


def test_disconnect_marks_ledger_unknown_and_suppresses_replay(db_session, tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"payload")
    file_id, integration_id = _ledger_ids(db_session, path)
    server = _smtp()
    server.sendmail.side_effect = __import__("smtplib").SMTPServerDisconnected("connection lost")
    factory = _ledger_factory(db_session)

    with (
        patch("app.tasks.upload_to_user_integration.SessionLocal", factory),
        patch("smtplib.SMTP", return_value=server),
    ):
        with pytest.raises(DestinationDeliveryUncertain, match="outcome is unknown"):
            _upload_email(str(path), _cfg(), {}, "task", file_id=file_id, integration_id=integration_id)
        with pytest.raises(DestinationDeliveryUncertain, match="Prior email outcome"):
            _upload_email(str(path), _cfg(), {}, "task", file_id=file_id, integration_id=integration_id)

    assert server.sendmail.call_count == 1
    assert db_session.query(DestinationDeliveryPart).one().status == "unknown"


def test_sender_552_leaves_ledger_pending_for_safe_retry(db_session, tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"payload")
    file_id, integration_id = _ledger_ids(db_session, path)
    server = _smtp()
    server.sendmail.side_effect = __import__("smtplib").SMTPSenderRefused(
        552, b"message too large", "sender@example.test"
    )
    factory = _ledger_factory(db_session)

    with (
        patch("app.tasks.upload_to_user_integration.SessionLocal", factory),
        patch("smtplib.SMTP", return_value=server),
    ):
        with pytest.raises(DestinationSizeLimitError):
            _upload_email(str(path), _cfg(), {}, "task", file_id=file_id, integration_id=integration_id)

    row = db_session.query(DestinationDeliveryPart).one()
    assert row.status == "pending"
    assert "too large" in row.error


def test_inflight_ledger_claim_is_terminal_not_a_false_success(db_session, tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"payload")
    file_id, integration_id = _ledger_ids(db_session, path)
    server = _smtp()
    factory = _ledger_factory(db_session)

    with (
        patch("app.tasks.upload_to_user_integration.SessionLocal", factory),
        patch("smtplib.SMTP", return_value=server),
    ):
        server.sendmail.side_effect = __import__("smtplib").SMTPServerDisconnected("connection lost")
        with pytest.raises(DestinationDeliveryUncertain):
            _upload_email(str(path), _cfg(), {}, "task", file_id=file_id, integration_id=integration_id)
        row = db_session.query(DestinationDeliveryPart).one()
        row.status = "sending"
        db_session.commit()
        server.sendmail.reset_mock()
        with pytest.raises(DestinationDeliveryUncertain, match="Prior email outcome"):
            _upload_email(str(path), _cfg(), {}, "task", file_id=file_id, integration_id=integration_id)

    server.sendmail.assert_not_called()


def test_split_retry_sends_only_the_previously_rejected_page(db_session, tmp_path):
    import smtplib

    path = tmp_path / "document.pdf"
    path.write_bytes(b"original" * 1000)
    file_id, integration_id = _ledger_ids(db_session, path)
    server = _smtp(size="2000")
    server.sendmail.side_effect = [{}, smtplib.SMTPDataError(552, b"message too large")]

    class FakeWriter:
        def add_page(self, page):
            self.page = page

        def write(self, output):
            output.write(self.page)

    fake_pypdf = SimpleNamespace(
        PdfReader=lambda _path: SimpleNamespace(pages=[b"first page", b"second page"]), PdfWriter=FakeWriter
    )
    with (
        patch.dict("sys.modules", {"pypdf": fake_pypdf}),
        patch("app.tasks.upload_to_user_integration.SessionLocal", _ledger_factory(db_session)),
        patch("smtplib.SMTP", return_value=server),
    ):
        with pytest.raises(DestinationSizeLimitError):
            _upload_email(
                str(path), _cfg(size_policy="split"), {}, "task", file_id=file_id, integration_id=integration_id
            )
        rows = db_session.query(DestinationDeliveryPart).order_by(DestinationDeliveryPart.part_number).all()
        assert [row.status for row in rows] == ["accepted", "pending"]
        server.sendmail.reset_mock(side_effect=True)
        result = _upload_email(
            str(path), _cfg(size_policy="split"), {}, "retry", file_id=file_id, integration_id=integration_id
        )
    assert result["sent_parts"] == 1
    assert result["already_accepted_parts"] == 1
    server.sendmail.assert_called_once()
    payload = message_from_bytes(server.sendmail.call_args.args[2].encode("ascii"))
    assert payload.get_payload()[1].get_payload(decode=True) == b"second page"
    db_session.expire_all()
    assert all(row.status == "accepted" for row in rows)
