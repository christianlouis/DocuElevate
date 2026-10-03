"""Regression checks for mobile deep-link security boundaries."""

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_unmatched_route_never_reconstructs_or_queues_files():
    source = (ROOT / "mobile/app/+not-found.tsx").read_text()
    assert "addPendingFile" not in source
    assert "file://" not in source
    assert "FS_PATH_ROOTS" not in source


def test_qr_login_requires_persisted_server_origin():
    source = (ROOT / "mobile/src/screens/QRScannerScreen.tsx").read_text()
    assert "!configuredServer" in source
    assert "new URL(configuredServer).origin !== url.origin" in source
    assert "Confirm QR Login" in source
