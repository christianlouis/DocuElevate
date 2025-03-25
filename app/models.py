# app/models.py
#!/usr/bin/env python3

from sqlalchemy import Column, String, Integer, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
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
    file_id = Column(Integer, ForeignKey("files.id"))
    step_name = Column(String)       # e.g. "OCR", "convert_to_pdf", "upload_s3"
    status = Column(String)          # "success" / "failure"
    message = Column(String)         # error text or success note
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
