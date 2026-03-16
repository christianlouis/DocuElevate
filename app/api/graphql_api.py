"""
GraphQL API endpoint for DocuElevate.

Provides a flexible query interface alongside the existing REST API.
Schema covers: documents, pipelines, settings, and users.

Endpoint: /graphql
GraphiQL playground: /graphql (via browser)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any

import strawberry
from fastapi import Depends, Request
from sqlalchemy.orm import Session
from strawberry.fastapi import GraphQLRouter

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import ApplicationSettings, FileRecord, Pipeline, PipelineStep, UserProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strawberry types
# ---------------------------------------------------------------------------


@strawberry.type
class DocumentType:
    """A processed document stored in the system."""

    id: int
    owner_id: str | None
    original_filename: str | None
    local_filename: str
    file_size: int
    mime_type: str | None
    document_title: str | None
    is_duplicate: bool
    ocr_quality_score: int | None
    pipeline_id: int | None
    created_at: datetime | None


@strawberry.type
class PipelineStepType:
    """A single step within a processing pipeline."""

    id: int
    pipeline_id: int
    position: int
    step_type: str
    label: str | None
    enabled: bool
    created_at: datetime | None


@strawberry.type
class PipelineType:
    """A processing pipeline with its ordered steps."""

    id: int
    owner_id: str | None
    name: str
    description: str | None
    is_default: bool
    is_active: bool
    steps: list[PipelineStepType]
    created_at: datetime | None
    updated_at: datetime | None


@strawberry.type
class SettingType:
    """An application configuration setting stored in the database."""

    id: int
    key: str
    value: str | None
    created_at: datetime | None
    updated_at: datetime | None


@strawberry.type
class UserType:
    """A user profile in the system."""

    id: int
    user_id: str
    display_name: str | None
    is_blocked: bool
    subscription_tier: str | None
    onboarding_completed: bool
    created_at: datetime | None


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _document_from_record(rec: FileRecord) -> DocumentType:
    return DocumentType(
        id=rec.id,
        owner_id=rec.owner_id,
        original_filename=rec.original_filename,
        local_filename=rec.local_filename,
        file_size=rec.file_size,
        mime_type=rec.mime_type,
        document_title=rec.document_title,
        is_duplicate=rec.is_duplicate,
        ocr_quality_score=rec.ocr_quality_score,
        pipeline_id=rec.pipeline_id,
        created_at=rec.created_at,
    )


def _pipeline_step_from_record(step: PipelineStep) -> PipelineStepType:
    return PipelineStepType(
        id=step.id,
        pipeline_id=step.pipeline_id,
        position=step.position,
        step_type=step.step_type,
        label=step.label,
        enabled=step.enabled,
        created_at=step.created_at,
    )


def _pipeline_from_record(pipeline: Pipeline, db: Session) -> PipelineType:
    steps = db.query(PipelineStep).filter(PipelineStep.pipeline_id == pipeline.id).order_by(PipelineStep.position).all()
    return PipelineType(
        id=pipeline.id,
        owner_id=pipeline.owner_id,
        name=pipeline.name,
        description=pipeline.description,
        is_default=pipeline.is_default,
        is_active=pipeline.is_active,
        steps=[_pipeline_step_from_record(s) for s in steps],
        created_at=pipeline.created_at,
        updated_at=pipeline.updated_at,
    )


def _setting_from_record(setting: ApplicationSettings) -> SettingType:
    return SettingType(
        id=setting.id,
        key=setting.key,
        value=setting.value,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


def _user_from_profile(profile: UserProfile) -> UserType:
    return UserType(
        id=profile.id,
        user_id=profile.user_id,
        display_name=profile.display_name,
        is_blocked=profile.is_blocked,
        subscription_tier=profile.subscription_tier,
        onboarding_completed=profile.onboarding_completed,
        created_at=profile.created_at,
    )


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

# Keys that contain sensitive data and must never be returned via GraphQL
_SENSITIVE_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "openai_api_key",
        "azure_ai_key",
        "session_secret",
        "database_url",
        "redis_url",
        "dropbox_app_secret",
        "dropbox_refresh_token",
        "google_drive_credentials_json",
        "onedrive_client_secret",
        "onedrive_refresh_token",
        "smtp_password",
        "nextcloud_password",
        "s3_secret_access_key",
        "ftp_password",
        "sftp_password",
        "webdav_password",
        "stripe_secret_key",
        "stripe_webhook_secret",
        "sentry_dsn",
        "social_auth_google_client_secret",
        "social_auth_microsoft_client_secret",
        "social_auth_apple_private_key",
        "social_auth_dropbox_app_secret",
    }
)


def _get_current_user_id(user: dict[str, Any] | None) -> str | None:
    """Extract the stable user identifier from the user dict."""
    if not user:
        return None
    return user.get("preferred_username") or user.get("email") or user.get("id") or None


def _get_db_and_user(info: strawberry.types.Info) -> tuple[Session, dict[str, Any] | None]:
    """Extract the database session and current user from the Strawberry context."""
    db: Session = info.context["db"]
    user: dict[str, Any] | None = info.context.get("user")
    return db, user


def _require_auth(user: dict[str, Any] | None) -> None:
    """Raise an error when authentication is enabled and no valid user is present."""
    if settings.auth_enabled and not user:
        raise strawberry.exceptions.StrawberryGraphQLError("Authentication required")


def _require_admin(user: dict[str, Any] | None) -> None:
    """Raise an error when the current user is not an admin.

    When ``auth_enabled`` is *False* (single-user / development mode) all
    callers are implicitly treated as administrators.
    """
    if not settings.auth_enabled:
        # Single-user mode: no auth, treat caller as admin
        return
    _require_auth(user)
    if not (user and user.get("is_admin")):
        raise strawberry.exceptions.StrawberryGraphQLError("Admin access required")


# ---------------------------------------------------------------------------
# Query resolvers
# ---------------------------------------------------------------------------


@strawberry.type
class Query:
    """Root query type for the DocuElevate GraphQL API."""

    @strawberry.field(description="List documents, optionally filtered by owner.")
    def documents(
        self,
        info: strawberry.types.Info,
        owner_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[DocumentType]:
        """Return a paginated list of documents.

        When *auth_enabled* the caller must be authenticated.  Non-admin users
        receive only their own documents; admins may query any *owner_id*.
        """
        db, user = _get_db_and_user(info)
        _require_auth(user)

        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        query = db.query(FileRecord)

        if settings.auth_enabled and user:
            is_admin = user.get("is_admin", False)
            current_user_id = _get_current_user_id(user)
            if not is_admin:
                # Non-admins can only see their own documents
                query = query.filter(FileRecord.owner_id == current_user_id)
            elif owner_id:
                query = query.filter(FileRecord.owner_id == owner_id)
        elif owner_id:
            query = query.filter(FileRecord.owner_id == owner_id)

        records = query.order_by(FileRecord.created_at.desc()).offset(offset).limit(limit).all()
        return [_document_from_record(r) for r in records]

    @strawberry.field(description="Fetch a single document by ID.")
    def document(self, info: strawberry.types.Info, id: int) -> DocumentType | None:
        """Return one document by its primary key, or *null* if not found."""
        db, user = _get_db_and_user(info)
        _require_auth(user)

        rec = db.query(FileRecord).filter(FileRecord.id == id).first()
        if rec is None:
            return None

        if settings.auth_enabled and user:
            is_admin = user.get("is_admin", False)
            current_user_id = _get_current_user_id(user)
            if not is_admin and rec.owner_id != current_user_id:
                return None

        return _document_from_record(rec)

    @strawberry.field(description="List processing pipelines.")
    def pipelines(
        self,
        info: strawberry.types.Info,
        owner_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[PipelineType]:
        """Return a paginated list of pipelines."""
        db, user = _get_db_and_user(info)
        _require_auth(user)

        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        query = db.query(Pipeline)

        if settings.auth_enabled and user:
            is_admin = user.get("is_admin", False)
            current_user_id = _get_current_user_id(user)
            if not is_admin:
                query = query.filter((Pipeline.owner_id == current_user_id) | (Pipeline.owner_id.is_(None)))
            elif owner_id:
                query = query.filter(Pipeline.owner_id == owner_id)
        elif owner_id:
            query = query.filter(Pipeline.owner_id == owner_id)

        rows = query.order_by(Pipeline.id).offset(offset).limit(limit).all()
        return [_pipeline_from_record(p, db) for p in rows]

    @strawberry.field(description="Fetch a single pipeline by ID.")
    def pipeline(self, info: strawberry.types.Info, id: int) -> PipelineType | None:
        """Return one pipeline by its primary key, or *null* if not found."""
        db, user = _get_db_and_user(info)
        _require_auth(user)

        row = db.query(Pipeline).filter(Pipeline.id == id).first()
        if row is None:
            return None

        if settings.auth_enabled and user:
            is_admin = user.get("is_admin", False)
            current_user_id = _get_current_user_id(user)
            if not is_admin and row.owner_id is not None and row.owner_id != current_user_id:
                return None

        return _pipeline_from_record(row, db)

    @strawberry.field(description="List non-sensitive application settings (admin only).")
    def settings(
        self,
        info: strawberry.types.Info,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SettingType]:
        """Return application settings stored in the database.

        Sensitive keys (API secrets, passwords, etc.) are automatically
        excluded.  Requires admin privileges when auth is enabled.
        """
        db, user = _get_db_and_user(info)
        _require_admin(user)

        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        rows = (
            db.query(ApplicationSettings)
            .filter(ApplicationSettings.key.notin_(_SENSITIVE_SETTING_KEYS))
            .order_by(ApplicationSettings.key)
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_setting_from_record(r) for r in rows]

    @strawberry.field(description="List user profiles (admin only).")
    def users(
        self,
        info: strawberry.types.Info,
        limit: int = 20,
        offset: int = 0,
    ) -> list[UserType]:
        """Return a paginated list of user profiles.  Requires admin privileges."""
        db, user = _get_db_and_user(info)
        _require_admin(user)

        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        rows = db.query(UserProfile).order_by(UserProfile.user_id).offset(offset).limit(limit).all()
        return [_user_from_profile(r) for r in rows]

    @strawberry.field(description="Fetch a user profile by user_id (admin only).")
    def user(self, info: strawberry.types.Info, user_id: str) -> UserType | None:
        """Return one user profile by *user_id*, or *null* if not found."""
        db, user = _get_db_and_user(info)
        _require_admin(user)

        row = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        return _user_from_profile(row) if row else None


# ---------------------------------------------------------------------------
# Schema and router
# ---------------------------------------------------------------------------

schema = strawberry.Schema(query=Query)


async def get_graphql_context(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Build the per-request context injected into every resolver."""
    try:
        user = get_current_user(request)
    except Exception:
        logger.debug("Could not resolve current user for GraphQL context", exc_info=True)
        user = None
    return {"request": request, "db": db, "user": user}


graphql_router = GraphQLRouter(
    schema,
    context_getter=get_graphql_context,
    graphql_ide="graphiql",
)
