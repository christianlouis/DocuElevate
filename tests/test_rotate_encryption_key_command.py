from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.rotate_encryption_key import main
from app.utils.encryption import EncryptionRotationError


@pytest.mark.unit
def test_rotation_command_requires_previous_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.rotate_encryption_key.settings.session_secret_previous", None)

    with patch("sys.argv", ["rotate_encryption_key"]), pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2


@pytest.mark.unit
def test_rotation_command_reports_counts_without_values(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr("app.rotate_encryption_key.settings.session_secret_previous", "x" * 32)
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = MagicMock()
    report = SimpleNamespace(scanned=4, rotated=3, invalid=0)

    with (
        patch("sys.argv", ["rotate_encryption_key"]),
        patch("app.rotate_encryption_key.SessionLocal", session_factory),
        patch("app.rotate_encryption_key.rotate_database_encryption", return_value=report) as rotate,
    ):
        result = main()

    assert result == 0
    assert capsys.readouterr().out == "Encryption rotation counts: scanned=4 rotated=3 invalid=0\n"
    rotate.assert_called_once_with(session_factory.return_value.__enter__.return_value, verify_only=False)


@pytest.mark.unit
def test_verify_command_fails_when_non_primary_values_remain(capsys):
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = MagicMock()
    report = SimpleNamespace(scanned=5, rotated=0, invalid=1)

    with (
        patch("sys.argv", ["rotate_encryption_key", "--verify-only"]),
        patch("app.rotate_encryption_key.SessionLocal", session_factory),
        patch("app.rotate_encryption_key.rotate_database_encryption", return_value=report) as rotate,
    ):
        result = main()

    assert result == 1
    assert capsys.readouterr().out == "Encryption rotation counts: scanned=5 rotated=0 invalid=1\n"
    rotate.assert_called_once_with(session_factory.return_value.__enter__.return_value, verify_only=True)


@pytest.mark.unit
def test_rotation_command_reports_encryption_failure_without_traceback(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr("app.rotate_encryption_key.settings.session_secret_previous", "x" * 32)
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = MagicMock()

    with (
        patch("sys.argv", ["rotate_encryption_key"]),
        patch("app.rotate_encryption_key.SessionLocal", session_factory),
        patch(
            "app.rotate_encryption_key.rotate_database_encryption",
            side_effect=EncryptionRotationError("Value is not decryptable by the configured keyring"),
        ),
    ):
        result = main()

    assert result == 1
    assert capsys.readouterr().out == (
        "Encryption rotation failed: Value is not decryptable by the configured keyring\n"
    )
