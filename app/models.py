# app/models.py

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func

from app.database import Base

# Foreign key constants
_FILES_ID_FK = "files.id"
_PIPELINES_ID_FK = "pipelines.id"


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

    # Processing pipeline assigned to this file (NULL = use system default)
    pipeline_id = Column(Integer, ForeignKey(_PIPELINES_ID_FK), nullable=True, index=True)

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

    # Pending subscription change (added in migration 020_add_subscription_change_pending)
    # When a user requests a downgrade, the new tier is stored here and the
    # change is applied on `subscription_change_pending_date`.  Upgrades are
    # applied immediately and these fields are left NULL.
    subscription_change_pending_tier = Column(String(50), nullable=True)
    subscription_change_pending_date = Column(DateTime(timezone=True), nullable=True)

    # When True, the user is on a complimentary (uncharged) plan — they keep all tier
    # quota benefits but are never billed via Stripe.  Automatically set for admin users.
    is_complimentary = Column(Boolean, nullable=False, default=False, server_default="0")

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


class Pipeline(Base):
    """User-defined processing pipeline: an ordered set of steps.

    Pipelines are user-specific.  A pipeline with ``owner_id = NULL`` is a
    *system default* pipeline that only admins may create.  Regular users
    create pipelines under their own ``owner_id``.  When a file has no
    explicit pipeline assigned, the active system default is used.
    """

    __tablename__ = "pipelines"

    id = Column(Integer, primary_key=True, index=True)

    # Owner of this pipeline.  NULL = system/admin pipeline visible to everyone.
    owner_id = Column(String, nullable=True, index=True)

    # Human-readable name (unique per owner)
    name = Column(String(255), nullable=False)

    # Optional description
    description = Column(Text, nullable=True)

    # When True this pipeline is the default for new files belonging to the owner
    # (or the global default when owner_id is NULL).  Only one pipeline per
    # owner may be active default at a time — enforced at the application level.
    is_default = Column(Boolean, nullable=False, default=False)

    # Soft-disable without deleting
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PipelineStep(Base):
    """A single step in a processing pipeline.

    Steps are executed in ascending ``position`` order.  Each step has a
    ``step_type`` that maps to a built-in processing action and an optional
    ``config`` JSON blob with step-specific parameters.
    """

    __tablename__ = "pipeline_steps"

    id = Column(Integer, primary_key=True, index=True)
    pipeline_id = Column(Integer, ForeignKey(_PIPELINES_ID_FK), nullable=False, index=True)

    # Execution order within the pipeline (lower = earlier)
    position = Column(Integer, nullable=False, default=0)

    # One of the recognised step types (see PIPELINE_STEP_TYPES in pipelines.py)
    step_type = Column(String(100), nullable=False)

    # Optional human-readable label override (defaults to step_type label)
    label = Column(String(255), nullable=True)

    # JSON-encoded step-specific configuration dict
    config = Column(Text, nullable=True)

    # When False this step is skipped during execution
    enabled = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserImapAccount(Base):
    """Per-user IMAP ingestion account.

    Each row represents one IMAP mailbox that a user wants DocuElevate to
    poll for document attachments.  The periodic ``pull_all_inboxes`` Celery
    task iterates over all active accounts and processes any new emails.

    Quota enforcement: the user's subscription plan's ``max_mailboxes`` field
    controls how many accounts a user may configure (0 = unlimited for paid
    plans; free tier is not permitted any accounts).
    """

    __tablename__ = "user_imap_accounts"

    id = Column(Integer, primary_key=True, index=True)

    # Stable owner identifier — matches FileRecord.owner_id
    owner_id = Column(String, nullable=False, index=True)

    # Human-readable label chosen by the user (e.g. "Work Gmail", "Scanner mailbox")
    name = Column(String(255), nullable=False)

    # IMAP connection settings
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False, default=993)
    username = Column(String(255), nullable=False)
    # Password stored encrypted using Fernet symmetric encryption via
    # app.utils.encryption.encrypt_value / decrypt_value (keyed from SESSION_SECRET).
    # New records are always encrypted; legacy plaintext records are transparently
    # handled by decrypt_value which returns the value unchanged when no "enc:" prefix
    # is present.
    password = Column(String(1024), nullable=False)
    use_ssl = Column(Boolean, nullable=False, default=True)

    # Processing options
    # When True, emails are deleted from the mailbox after their attachments are processed
    delete_after_process = Column(Boolean, nullable=False, default=False)

    # When False the account is not polled by the periodic task (but not deleted)
    is_active = Column(Boolean, nullable=False, default=True)

    # Last time this mailbox was successfully polled
    last_checked_at = Column(DateTime(timezone=True), nullable=True)

    # Last error message if the most recent poll failed (NULL = last poll succeeded)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BackupRecord(Base):
    """Tracks database backup files and their retention metadata.

    Each row represents one backup archive (a gzipped SQLite dump).
    ``backup_type`` classifies the backup for retention purposes:
    - ``hourly``  – kept for up to 4 days (96 snapshots)
    - ``daily``   – kept for up to 3 weeks (21 snapshots)
    - ``weekly``  – kept for up to 13 weeks (≈ 90 days)
    ``local_path`` is the full filesystem path of the local copy (``None``
    once pruned).  ``remote_destination`` and ``remote_path`` describe the
    remote copy when one has been uploaded to a storage provider or e-mailed.
    """

    __tablename__ = "backup_records"

    id = Column(Integer, primary_key=True, index=True)

    # Human-readable archive filename (e.g. backup_hourly_2026-03-07T12-00-00.db.gz)
    filename = Column(String(255), nullable=False, unique=True)

    # Full path on the local filesystem (may be NULL for remote-only backups)
    local_path = Column(String(1024), nullable=True)

    # Classification used by the retention policy
    backup_type = Column(String(20), nullable=False, index=True)  # hourly | daily | weekly

    # Archive size in bytes (0 if unknown)
    size_bytes = Column(Integer, nullable=False, default=0)

    # Checksum of the archive for integrity verification (SHA-256 hex)
    checksum = Column(String(64), nullable=True)

    # Whether the backup was successfully created
    status = Column(String(20), nullable=False, default="ok")  # ok | failed

    # Storage destination where a remote copy was uploaded (e.g. "s3", "dropbox", "email")
    remote_destination = Column(String(50), nullable=True)

    # Path / key of the remote copy (bucket key, folder path, etc.)
    remote_path = Column(String(1024), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# ---------------------------------------------------------------------------
# Integration direction / type constants
# ---------------------------------------------------------------------------


class IntegrationDirection:
    """Direction of data flow for a UserIntegration."""

    SOURCE = "SOURCE"
    DESTINATION = "DESTINATION"

    ALL = {SOURCE, DESTINATION}


class IntegrationType:
    """Supported integration types for UserIntegration."""

    # Source integrations (ingestion)
    IMAP = "IMAP"
    WATCH_FOLDER = "WATCH_FOLDER"
    WEBHOOK = "WEBHOOK"

    # Destination integrations (storage / output)
    S3 = "S3"
    DROPBOX = "DROPBOX"
    GOOGLE_DRIVE = "GOOGLE_DRIVE"
    ONEDRIVE = "ONEDRIVE"
    WEBDAV = "WEBDAV"
    NEXTCLOUD = "NEXTCLOUD"
    FTP = "FTP"
    SFTP = "SFTP"
    EMAIL = "EMAIL"
    PAPERLESS = "PAPERLESS"
    RCLONE = "RCLONE"

    ALL = {
        IMAP,
        WATCH_FOLDER,
        WEBHOOK,
        S3,
        DROPBOX,
        GOOGLE_DRIVE,
        ONEDRIVE,
        WEBDAV,
        NEXTCLOUD,
        FTP,
        SFTP,
        EMAIL,
        PAPERLESS,
        RCLONE,
    }


class UserIntegration(Base):
    """Generic per-user integration record (source or destination).

    Replaces ad-hoc per-integration-type tables with a single, extensible
    model that supports any combination of ingestion sources and storage
    destinations without schema changes when new integrations are added.

    ``config`` holds non-sensitive connection settings as a JSON string
    (e.g. host, port, bucket name, folder path).

    ``credentials`` holds sensitive secrets (passwords, tokens, API keys)
    as a Fernet-encrypted JSON string.  Always use
    ``app.utils.encryption.encrypt_value`` / ``decrypt_value`` when
    writing / reading this field.

    Example config + credentials shapes by integration type:

    IMAP:
      config      = {"host": "imap.example.com", "port": 993,
                     "username": "user@example.com", "use_ssl": true,
                     "delete_after_process": false}
      credentials = {"password": "secret"}

    S3:
      config      = {"bucket": "my-bucket", "region": "us-east-1",
                     "endpoint_url": null, "folder_prefix": ""}
      credentials = {"access_key_id": "AKI…", "secret_access_key": "…"}

    DROPBOX:
      config      = {"folder": "/DocuElevate"}
      credentials = {"refresh_token": "…", "app_key": "…",
                     "app_secret": "…"}

    GOOGLE_DRIVE:
      config      = {"folder_id": "1abc…"}
      credentials = {"credentials_json": "{…service-account or OAuth…}"}

    WEBDAV / NEXTCLOUD:
      config      = {"url": "https://cloud.example.com/dav/",
                     "folder": "/Documents"}
      credentials = {"username": "user", "password": "secret"}
    """

    __tablename__ = "user_integrations"

    id = Column(Integer, primary_key=True, index=True)

    # Stable owner identifier — matches FileRecord.owner_id / UserImapAccount.owner_id
    owner_id = Column(String, nullable=False, index=True)

    # "SOURCE" or "DESTINATION"  (see IntegrationDirection)
    direction = Column(String(20), nullable=False, index=True)

    # One of the IntegrationType constants (e.g. "IMAP", "S3", "DROPBOX")
    integration_type = Column(String(50), nullable=False, index=True)

    # Human-readable label chosen by the user (e.g. "Work Gmail", "S3 Archive")
    name = Column(String(255), nullable=False)

    # Non-sensitive connection configuration (JSON string)
    config = Column(Text, nullable=True)

    # Sensitive credentials — always stored encrypted via encrypt_value()
    credentials = Column(Text, nullable=True)

    # When False the integration is not polled / used by background tasks
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamp of the last successful use of this integration
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Last error message if the most recent operation failed (NULL = last op succeeded)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ApiToken(Base):
    """Personal API token for programmatic access.

    Users can create multiple tokens, each with a human-readable name.
    Only the SHA-256 hash of the token is stored; the plaintext is shown
    exactly once at creation time.  A short prefix (first 8 chars) is
    persisted for easy identification in the UI.

    Usage tracking records the timestamp and IP address of the most
    recent request that used the token.
    """

    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)

    # Stable owner identifier — matches FileRecord.owner_id / UserIntegration.owner_id
    owner_id = Column(String, nullable=False, index=True)

    # Human-readable label chosen by the user (e.g. "CI Pipeline", "Webhook Upload")
    name = Column(String(255), nullable=False)

    # SHA-256 hex digest of the full token value
    token_hash = Column(String(64), nullable=False, unique=True, index=True)

    # First 12 characters of the token for display (e.g. "de_Ab3xY7kL…")
    token_prefix = Column(String(16), nullable=False)

    # Usage tracking
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    last_used_ip = Column(String(45), nullable=True)  # IPv6 max length

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class UserNotificationTarget(Base):
    """Per-user notification target (email or webhook channel)."""

    __tablename__ = "user_notification_targets"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, index=True)
    channel_type = Column(String(20), nullable=False)  # "email" or "webhook"
    name = Column(String(255), nullable=False)  # Human-readable label
    config = Column(Text, nullable=True)  # JSON: smtp config or webhook url
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserNotificationPreference(Base):
    """Mapping: which user events trigger which notification channel."""

    __tablename__ = "user_notification_preferences"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # "document.processed", "document.failed"
    channel_type = Column(String(20), nullable=False)  # "in_app", "email", "webhook"
    target_id = Column(Integer, nullable=True)  # NULL = in_app, else UserNotificationTarget.id
    is_enabled = Column(Boolean, nullable=False, default=True)

    __table_args__ = (UniqueConstraint("owner_id", "event_type", "channel_type", "target_id"),)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class InAppNotification(Base):
    """In-app notification record for the bell icon / inbox."""

    __tablename__ = "in_app_notifications"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # "document.processed", "document.failed"
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    is_read = Column(Boolean, nullable=False, default=False, index=True)
    file_id = Column(Integer, nullable=True)  # Optional link to FileRecord
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
