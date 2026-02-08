"""
Tests for app/celery_worker.py

Tests Celery worker configuration and task registration.
Note: These tests use pytest.mark.requires_redis since they depend on Celery configuration.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


@pytest.mark.unit
class TestCeleryWorkerConfiguration:
    """Test Celery worker configuration"""

    def test_celery_worker_module_imports(self):
        """Test that celery_worker module can be imported"""
        import app.celery_worker

        assert hasattr(app.celery_worker, "celery")
        assert hasattr(app.celery_worker, "test_task")

    def test_test_task_defined(self):
        """Test that test_task is defined"""
        from app.celery_worker import test_task

        # Task should be callable
        assert callable(test_task)


@pytest.mark.unit
class TestTaskImports:
    """Test that all tasks can be imported correctly"""

    def test_process_document_imported(self):
        """Test process_document task import"""
        from app.celery_worker import process_document

        assert callable(process_document)

    def test_convert_to_pdf_imported(self):
        """Test convert_to_pdf task import"""
        from app.celery_worker import convert_to_pdf

        assert callable(convert_to_pdf)

    def test_embed_metadata_into_pdf_imported(self):
        """Test embed_metadata_into_pdf task import"""
        from app.celery_worker import embed_metadata_into_pdf

        assert callable(embed_metadata_into_pdf)

    def test_extract_metadata_with_gpt_imported(self):
        """Test extract_metadata_with_gpt task import"""
        from app.celery_worker import extract_metadata_with_gpt

        assert callable(extract_metadata_with_gpt)

    def test_send_to_all_destinations_imported(self):
        """Test send_to_all_destinations task import"""
        from app.celery_worker import send_to_all_destinations

        assert callable(send_to_all_destinations)

    def test_upload_tasks_imported(self):
        """Test that upload tasks are imported"""
        from app.celery_worker import (
            upload_to_dropbox,
            upload_to_email,
            upload_to_ftp,
            upload_to_google_drive,
            upload_to_nextcloud,
            upload_to_onedrive,
            upload_to_paperless,
            upload_to_s3,
            upload_to_sftp,
            upload_to_webdav,
        )

        # All should be callable
        assert callable(upload_to_dropbox)
        assert callable(upload_to_email)
        assert callable(upload_to_ftp)
        assert callable(upload_to_google_drive)
        assert callable(upload_to_nextcloud)
        assert callable(upload_to_onedrive)
        assert callable(upload_to_paperless)
        assert callable(upload_to_s3)
        assert callable(upload_to_sftp)
        assert callable(upload_to_webdav)

    def test_utility_tasks_imported(self):
        """Test utility tasks are imported"""
        from app.celery_worker import (
            pull_all_inboxes,
            ping_uptime_kuma,
            check_credentials,
        )

        assert callable(pull_all_inboxes)
        assert callable(ping_uptime_kuma)
        assert callable(check_credentials)

    def test_processing_tasks_imported(self):
        """Test processing tasks are imported"""
        from app.celery_worker import (
            process_with_azure_document_intelligence,
            refine_text_with_gpt,
            rotate_pdf_pages,
        )

        assert callable(process_with_azure_document_intelligence)
        assert callable(refine_text_with_gpt)
        assert callable(rotate_pdf_pages)
