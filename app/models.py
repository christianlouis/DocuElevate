# app/models.py

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String,
                        Text, UniqueConstraint, func)

from app.database import Base

# Foreign key constants
_FILES_ID_FK = "files.id"


class DocumentMetadata(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True)
    sender = Column(String)
    recipient = Column(String)
    tags = Column(String)
    summary = Column(String)


class FileRecord(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)

    # Hash of the file content (e.g. SHA-256)
    # Note: duplicates are allowed so filehash is not unique
    filehash = Column(String, index=True, nullable=False)

    # The name of the file as it was originally uploaded (if known)
    original_filename = Column(String)

    # The name/path we store on disk (e.g. /workdir/tmp/<uuid>.pdf)
    local_filename = Column(String, nullable=False)

    # Immutable original copy path (e.g. /workdir/original/<uuid>.pdf)
    # This is the first copy made when the file is ingested
    original_file_path = Column(String)

    # Processed copy path (e.g. /workdir/processed/2024-01-01_Invoice.pdf)
    # This is the final file with embedded metadata before upload
    processed_file_path = Column(String)

    # Size of the file in bytes
    file_size = Column(Integer, nullable=False)

    # MIME type or extension (optional)
    mime_type = Column(String)

    # Deduplication tracking: True if this file is a duplicate of another file
    # When a duplicate is detected, this file record is created but marked as duplicate
    is_duplicate = Column(Boolean, default=False, nullable=False, index=True)

    # If this is a duplicate, record the ID of the original file for reference
    duplicate_of_id = Column(Integer, ForeignKey(_FILES_ID_FK), nullable=True)

    # Timestamp when we inserted this record
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FileProcessingStep(Base):
    """
    Tracks the current status of each processing step for a file.
    This provides a definitive, queryable state for each step without scanning logs.
    """

    __tablename__ = "file_processing_steps"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey(_FILES_ID_FK), nullable=False, index=True)
    step_name = Column(
        String, nullable=False, index=True
    )  # e.g., "hash_file", "upload_to_dropbox"
    status = Column(
        String, nullable=False
    )  # "pending", "in_progress", "success", "failure", "skipped"
    started_at = Column(DateTime(timezone=True), nullable=True)  # When step started
    completed_at = Column(
        DateTime(timezone=True), nullable=True
    )  # When step finished (success/failure)
    error_message = Column(Text, nullable=True)  # Error message if status is "failure"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("file_id", "step_name", name="unique_file_step"),
    )


class ProcessingLog(Base):
    __tablename__ = "processing_logs"
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(
        Integer, ForeignKey(_FILES_ID_FK), nullable=True
    )  # Optional file association
    task_id = Column(String, index=True)  # Celery task ID
    step_name = Column(String)  # e.g., "OCR", "convert_to_pdf", "upload_s3"
    status = Column(String)  # "pending", "in_progress", "success", "failure"
    message = Column(String, nullable=True)  # Error text or success note
    detail = Column(Text, nullable=True)  # Verbose worker log output for diagnostics
    timestamp = Column(DateTime(timezone=True), server_default=func.now())


class ApplicationSettings(Base):
    """Store application settings in database with precedence over environment variables"""

    __tablename__ = "application_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(
        String, unique=True, index=True, nullable=False
    )  # Setting key (e.g., 'database_url')
    value = Column(
        String, nullable=True
    )  # Setting value (stored as string, converted as needed)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SettingsAuditLog(Base):
    """Audit log for all configuration changes made via the settings UI."""

    __tablename__ = "settings_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, index=True)  # Setting key that was changed
    old_value = Column(String, nullable=True)  # Previous value (None if first-time set)
    new_value = Column(String, nullable=True)  # New value (None if deleted)
    changed_by = Column(
        String, nullable=False
    )  # Username of the admin who made the change
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    action = Column(String, nullable=False)  # "update" or "delete"
