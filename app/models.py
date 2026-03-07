# app/models.py

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func

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

    # Owner identifier for multi-user mode.
    # Stores the user's unique identifier (e.g. email or OAuth sub claim).
    # NULL means the file belongs to the shared/global space (single-user mode).
    owner_id = Column(String, nullable=True, index=True)

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
    mime_type = Column(String, index=True)

    # Deduplication tracking: True if this file is a duplicate of another file
    # When a duplicate is detected, this file record is created but marked as duplicate
    is_duplicate = Column(Boolean, default=False, nullable=False, index=True)

    # If this is a duplicate, record the ID of the original file for reference
    duplicate_of_id = Column(Integer, ForeignKey(_FILES_ID_FK), nullable=True)

    # Full OCR/extracted text for full-text search and RAG
    ocr_text = Column(Text, nullable=True)

    # AI-assessed quality score for the OCR/extracted text (0–100; NULL = not yet assessed)
    ocr_quality_score = Column(Integer, nullable=True)

    # AI-extracted metadata stored as JSON string (filename, tags, title, sender, etc.)
    ai_metadata = Column(Text, nullable=True)

    # Human-readable document title from AI metadata
    document_title = Column(String, nullable=True)

    # PDF/A archival variant paths (generated when ENABLE_PDFA_CONVERSION is True)
    original_pdfa_path = Column(String, nullable=True)  # PDF/A copy of the original ingested file
    processed_pdfa_path = Column(String, nullable=True)  # PDF/A copy of the processed file

    # Pre-computed text embedding vector stored as JSON array of floats
    embedding = Column(Text, nullable=True)

    # Timestamp when we inserted this record
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class FileProcessingStep(Base):
    """
    Tracks the current status of each processing step for a file.
    This provides a definitive, queryable state for each step without scanning logs.
    """

    __tablename__ = "file_processing_steps"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey(_FILES_ID_FK), nullable=False, index=True)
    step_name = Column(String, nullable=False, index=True)  # e.g., "hash_file", "upload_to_dropbox"
    status = Column(String, nullable=False, index=True)  # "pending", "in_progress", "success", "failure", "skipped"
    started_at = Column(DateTime(timezone=True), nullable=True)  # When step started
    completed_at = Column(DateTime(timezone=True), nullable=True)  # When step finished (success/failure)
    error_message = Column(Text, nullable=True)  # Error message if status is "failure"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("file_id", "step_name", name="unique_file_step"),)


class ProcessingLog(Base):
    __tablename__ = "processing_logs"
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey(_FILES_ID_FK), nullable=True, index=True)  # Optional file association
    task_id = Column(String, index=True)  # Celery task ID
    step_name = Column(String)  # e.g., "OCR", "convert_to_pdf", "upload_s3"
    status = Column(String)  # "pending", "in_progress", "success", "failure"
    message = Column(String, nullable=True)  # Error text or success note
    detail = Column(Text, nullable=True)  # Verbose worker log output for diagnostics
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class ApplicationSettings(Base):
    """Store application settings in database with precedence over environment variables"""

    __tablename__ = "application_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)  # Setting key (e.g., 'database_url')
    value = Column(String, nullable=True)  # Setting value (stored as string, converted as needed)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SettingsAuditLog(Base):
    """Audit log for all configuration changes made via the settings UI."""

    __tablename__ = "settings_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, index=True)  # Setting key that was changed
    old_value = Column(String, nullable=True)  # Previous value (None if first-time set)
    new_value = Column(String, nullable=True)  # New value (None if deleted)
    changed_by = Column(String, nullable=False)  # Username of the admin who made the change
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    action = Column(String, nullable=False)  # "update" or "delete"


class SavedSearch(Base):
    """User-defined saved search filters for quick access to frequently used filter combinations."""

    __tablename__ = "saved_searches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)  # Username or user identifier from session
    name = Column(String, nullable=False)  # Human-readable name for the saved search
    filters = Column(Text, nullable=False)  # JSON-encoded filter parameters
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("user_id", "name", name="unique_user_search_name"),)


class WebhookConfig(Base):
    """Webhook configuration for notifying external systems of document events."""

    __tablename__ = "webhook_configs"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=False)  # Target URL for webhook delivery
    secret = Column(String, nullable=True)  # Shared secret for HMAC-SHA256 signature
    events = Column(Text, nullable=False)  # JSON list of subscribed events
    is_active = Column(Boolean, default=True, nullable=False)  # Whether the webhook is active
    description = Column(String, nullable=True)  # Optional human-readable description
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LocalUser(Base):
    """A locally-registered user authenticated by email and bcrypt password.

    Created during the self-registration flow when ``allow_local_signup`` is
    enabled.  The account is inactive (``is_active=False``) until the user
    clicks the verification link sent to their email address.
    """

    __tablename__ = "local_users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=False, server_default="0")
    is_admin = Column(Boolean, nullable=False, default=False, server_default="0")
    email_verification_token = Column(String(128), nullable=True)
    email_verification_sent_at = Column(DateTime(timezone=True), nullable=True)
    password_reset_token = Column(String(128), nullable=True)
    password_reset_sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserProfile(Base):
    """Per-user profile for admin-managed settings in multi-user mode.

    Each row corresponds to one authenticated user (identified by their
    ``user_id``, which matches ``FileRecord.owner_id``).  The admin can
    create or update profiles to override global defaults such as the
    daily upload limit and to attach notes or block a user.
    """

    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # Stable user identifier — matches FileRecord.owner_id (OAuth sub / email / username)
    user_id = Column(String, unique=True, nullable=False, index=True)

    # Optional human-readable display name set by the admin
    display_name = Column(String, nullable=True)

    # Per-user daily upload limit; NULL means "use global default"
    daily_upload_limit = Column(Integer, nullable=True)

    # Admin-only free-text notes about this user
    notes = Column(Text, nullable=True)

    # When True the user is prevented from uploading new documents
    is_blocked = Column(Boolean, default=False, nullable=False)

    # Subscription tier: "free" | "starter" | "professional" | "business"
    # NULL is treated as "free" by the subscription utility.
    subscription_tier = Column(String(50), nullable=True, default="free")

    # Billing cycle and overage settings (added in migration 016)
    subscription_billing_cycle = Column(String(10), nullable=False, default="monthly", server_default="monthly")
    subscription_period_start = Column(DateTime(timezone=True), nullable=True)
    allow_overage = Column(Boolean, nullable=False, default=False, server_default="0")

    # Onboarding tracking (added in migration 017)
    onboarding_completed = Column(Boolean, nullable=False, default=False, server_default="0")
    onboarding_completed_at = Column(DateTime(timezone=True), nullable=True)
    contact_email = Column(String(255), nullable=True)
    preferred_destination = Column(String(50), nullable=True)
    stripe_customer_id = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SubscriptionPlan(Base):
    """Dynamically configurable subscription plan stored in the database.

    Plans are shown on the public /pricing page and assigned to users via
    UserProfile.subscription_tier (which stores plan_id).  On first start the
    four default plans are seeded from TIER_DEFAULTS in app/utils/subscription.py.
    """

    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    tagline = Column(String(255), nullable=True)

    # Pricing
    price_monthly = Column(Float, nullable=False, default=0.0)
    price_yearly = Column(Float, nullable=False, default=0.0)
    trial_days = Column(Integer, nullable=False, default=0)

    # Volume limits (0 = unlimited)
    lifetime_file_limit = Column(Integer, nullable=False, default=0)
    daily_upload_limit = Column(Integer, nullable=False, default=0)
    monthly_upload_limit = Column(Integer, nullable=False, default=0)
    max_storage_destinations = Column(Integer, nullable=False, default=0)
    max_ocr_pages_monthly = Column(Integer, nullable=False, default=0)
    max_file_size_mb = Column(Integer, nullable=False, default=0)
    max_mailboxes = Column(Integer, nullable=False, default=0)

    # Overage configuration
    overage_percent = Column(Integer, nullable=False, default=20)
    allow_overage_billing = Column(Boolean, nullable=False, default=False)
    overage_price_per_doc = Column(Float, nullable=True)
    overage_price_per_ocr_page = Column(Float, nullable=True)

    # Display / marketing
    is_active = Column(Boolean, nullable=False, default=True)
    is_highlighted = Column(Boolean, nullable=False, default=False)
    badge_text = Column(String(50), nullable=True)
    cta_text = Column(String(100), nullable=False, default="Get started")
    sort_order = Column(Integer, nullable=False, default=0)
    features = Column(Text, nullable=True)  # JSON-encoded list[str]
    api_access = Column(Boolean, nullable=False, default=False)
    stripe_price_id_monthly = Column(String(128), nullable=True)
    stripe_price_id_yearly = Column(String(128), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
