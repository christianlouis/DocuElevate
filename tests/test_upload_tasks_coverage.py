"""Tests to increase coverage for upload task modules."""

import os
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.upload_to_ftp import upload_to_ftp
from app.tasks.upload_to_nextcloud import upload_to_nextcloud
from app.tasks.upload_to_onedrive import upload_to_onedrive
from app.tasks.upload_to_paperless import upload_to_paperless
from app.tasks.upload_to_s3 import upload_to_s3
from app.tasks.upload_to_sftp import upload_to_sftp
from app.tasks.upload_to_webdav import upload_to_webdav


@pytest.mark.unit
class TestTasksImportable:
    """Test that all upload task modules can be imported."""

    def test_paperless_importable(self):
        """Test upload_to_paperless is importable."""
        assert callable(upload_to_paperless)

    def test_nextcloud_importable(self):
        """Test upload_to_nextcloud is importable."""
        assert callable(upload_to_nextcloud)

    def test_onedrive_importable(self):
        """Test upload_to_onedrive is importable."""
        assert callable(upload_to_onedrive)

    def test_s3_importable(self):
        """Test upload_to_s3 is importable."""
        assert callable(upload_to_s3)

    def test_sftp_importable(self):
        """Test upload_to_sftp is importable."""
        assert callable(upload_to_sftp)

    def test_webdav_importable(self):
        """Test upload_to_webdav is importable."""
        assert callable(upload_to_webdav)

    def test_ftp_importable(self):
        """Test upload_to_ftp is importable."""
        assert callable(upload_to_ftp)
