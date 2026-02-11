# app/models.py

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func

from app.database import Base


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
    filehash = Column(String, unique=True, index=True, nullable=False)

    # The name of the file as it was originally uploaded (if known)
    original_filename = Column(String)

    # The name/path we store on disk (e.g. /workdir/tmp/<uuid>.pdf)
    local_filename = Column(String, nullable=False)

    # Size of the file in bytes
    file_size = Column(Integer, nullable=False)

    # MIME type or extension (optional)
    mime_type = Column(String)

    # Timestamp when we inserted this record
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ProcessingLog(Base):
    __tablename__ = "processing_logs"
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=True)  # Optional file association
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
    key = Column(String, unique=True, index=True, nullable=False)  # Setting key (e.g., 'database_url')
    value = Column(String, nullable=True)  # Setting value (stored as string, converted as needed)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
