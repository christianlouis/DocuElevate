"""API endpoints for managing per-user integrations (sources and destinations).

Provides CRUD operations for :class:`~app.models.UserIntegration` records.
Each record represents one ingestion source (e.g. IMAP, Watch Folder) or
storage destination (e.g. S3, Dropbox, Google Drive) configured by a user.

Sensitive credentials are encrypted at rest using Fernet symmetric encryption
(keyed from ``SESSION_SECRET``) via :mod:`app.utils.encryption`.  Credential
values are **never** returned in API responses.

Subscription quota enforcement
------------------------------
On creation, the endpoint checks the user's subscription tier limits:

* **Destinations** — ``max_storage_destinations`` from the plan.
* **Sources (IMAP)** — ``max_mailboxes`` from the plan.

Exceeding the quota returns HTTP 403 with an actionable error message.
"""

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import IntegrationDirection, IntegrationType, UserIntegration
from app.utils.encryption import decrypt_value, encrypt_value
from app.utils.subscription import get_tier, get_user_tier_id
from app.utils.user_scope import get_current_owner_id

# Optional Dropbox SDK — imported at module level so tests can patch it cleanly.
try:
    import dropbox as dbx_lib
    from dropbox.exceptions import AuthError as _DropboxAuthError
    from dropbox.exceptions import BadInputError as _DropboxBadInputError
except ImportError:  # pragma: no cover
    dbx_lib = None  # type: ignore[assignment]

    class _DropboxAuthError(Exception):  # type: ignore[no-redef]
        """Stub — only used when the dropbox package is missing."""

    class _DropboxBadInputError(Exception):  # type: ignore[no-redef]
        """Stub — only used when the dropbox package is missing."""


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])

DbSession = Annotated[Session, Depends(get_db)]

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _get_owner_id(request: Request) -> str:
    """Return the current user's owner ID, raising 401 if unauthenticated."""
    owner_id = get_current_owner_id(request)
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return owner_id


CurrentOwner = Annotated[str, Depends(_get_owner_id)]

# ---------------------------------------------------------------------------
# Quota helpers
# ---------------------------------------------------------------------------

_FREE_TIER_ID = "free"

# Source types that consume the mailbox quota
_MAILBOX_SOURCE_TYPES = {IntegrationType.IMAP}


def _get_max_destinations(tier: dict[str, Any]) -> int | None:
    """Return the maximum number of storage destinations allowed by *tier*.

    Returns:
        ``None``  — unlimited (paid tiers with ``max_storage_destinations == 0``)
        positive  — the configured limit
    """
    tier_id: str = tier.get("id", _FREE_TIER_ID)
    max_dest: int = tier.get("max_storage_destinations", 0)

    # Free tier: the value itself is the limit (e.g. 1)
    if tier_id == _FREE_TIER_ID:
        return max_dest if max_dest > 0 else 1  # safe default

    # Paid tiers: 0 means unlimited
    if max_dest == 0:
        return None

    return max_dest


def _get_max_sources(tier: dict[str, Any]) -> int | None:
    """Return the maximum number of IMAP source integrations allowed by *tier*.

    Returns:
        ``None``  — unlimited (paid tiers with ``max_mailboxes == 0``)
        ``0``     — no mailboxes allowed (free tier)
        positive  — the configured limit
    """
    tier_id: str = tier.get("id", _FREE_TIER_ID)
    max_mb: int = tier.get("max_mailboxes", 0)

    # Free tier: 0 means "no access" (not "unlimited")
    if tier_id == _FREE_TIER_ID:
        return 0

    # Paid tiers: 0 means unlimited
    if max_mb == 0:
        return None

    return max_mb


def _check_quota(db: Session, owner_id: str, direction: str, integration_type: str) -> None:
    """Raise 403 if the user has reached their integration quota.

    Quota rules:
    * DESTINATION integrations are limited by ``max_storage_destinations``.
    * SOURCE integrations of type IMAP are limited by ``max_mailboxes``.
    * Other SOURCE types (WATCH_FOLDER, WEBHOOK) are not quota-limited yet.
    """
    tier_id = get_user_tier_id(db, owner_id)
    tier = get_tier(tier_id, db)

    if direction == IntegrationDirection.DESTINATION:
        max_dest = _get_max_destinations(tier)
        if max_dest is not None:
            current_count = (
                db.query(UserIntegration)
                .filter(
                    UserIntegration.owner_id == owner_id,
                    UserIntegration.direction == IntegrationDirection.DESTINATION,
                )
                .count()
            )
            if current_count >= max_dest:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        f"You have reached your plan limit of {max_dest} storage destination(s). "
                        "Please remove an existing destination or upgrade your plan."
                    ),
                )

    elif direction == IntegrationDirection.SOURCE and integration_type in _MAILBOX_SOURCE_TYPES:
        max_src = _get_max_sources(tier)

        if max_src == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your current plan does not include email ingestion. Upgrade to a paid plan to add IMAP sources.",
            )

        if max_src is not None:
            current_count = (
                db.query(UserIntegration)
                .filter(
                    UserIntegration.owner_id == owner_id,
                    UserIntegration.direction == IntegrationDirection.SOURCE,
                    UserIntegration.integration_type.in_(list(_MAILBOX_SOURCE_TYPES)),
                )
                .count()
            )
            if current_count >= max_src:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        f"You have reached your plan limit of {max_src} IMAP source(s). "
                        "Please remove an existing source or upgrade your plan."
                    ),
                )


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

_VALID_DIRECTIONS = IntegrationDirection.ALL
_VALID_TYPES = IntegrationType.ALL


class IntegrationCreate(BaseModel):
    """Schema for creating a new integration."""

    direction: str = Field(..., description="'SOURCE' or 'DESTINATION'")
    integration_type: str = Field(..., description="Integration type (e.g. 'IMAP', 'S3', 'DROPBOX')")
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable label")
    config: dict[str, Any] | None = Field(default=None, description="Non-sensitive configuration (JSON object)")
    credentials: dict[str, Any] | None = Field(
        default=None, description="Sensitive credentials (JSON object, encrypted at rest)"
    )
    is_active: bool = Field(default=True, description="Whether the integration is active")


class IntegrationUpdate(BaseModel):
    """Schema for updating an existing integration (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    config: dict[str, Any] | None = None
    credentials: dict[str, Any] | None = None
    is_active: bool | None = None


class IntegrationTestRequest(BaseModel):
    """Schema for testing an integration connection without saving it."""

    integration_type: str = Field(..., description="Integration type (e.g. 'IMAP', 'S3', 'DROPBOX')")
    config: dict[str, Any] | None = Field(default=None, description="Non-sensitive configuration")
    credentials: dict[str, Any] | None = Field(default=None, description="Credentials for the connection test")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_direction(direction: str) -> None:
    """Raise 400 if *direction* is not a known value."""
    if direction not in _VALID_DIRECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid direction '{direction}'. Must be one of: {sorted(_VALID_DIRECTIONS)}",
        )


def _validate_integration_type(integration_type: str) -> None:
    """Raise 400 if *integration_type* is not a known value."""
    if integration_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid integration_type '{integration_type}'. Must be one of: {sorted(_VALID_TYPES)}",
        )


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _to_response(integration: UserIntegration) -> dict[str, Any]:
    """Serialise a :class:`UserIntegration` row to a response dict.

    Credentials are **never** included; only a boolean flag indicating
    whether credentials have been configured is returned.
    """
    config_data: dict[str, Any] | None = None
    if integration.config:
        try:
            config_data = json.loads(integration.config)
        except (json.JSONDecodeError, TypeError):
            config_data = None

    return {
        "id": integration.id,
        "owner_id": integration.owner_id,
        "direction": integration.direction,
        "integration_type": integration.integration_type,
        "name": integration.name,
        "config": config_data,
        "has_credentials": bool(integration.credentials),
        "is_active": integration.is_active,
        "last_used_at": integration.last_used_at.isoformat() if integration.last_used_at else None,
        "last_error": integration.last_error,
        "created_at": integration.created_at.isoformat() if integration.created_at else None,
        "updated_at": integration.updated_at.isoformat() if integration.updated_at else None,
    }


def _encode_credentials(credentials: dict[str, Any] | None) -> str | None:
    """Serialise *credentials* dict to an encrypted JSON string for storage."""
    if not credentials:
        return None
    plaintext = json.dumps(credentials)
    return encrypt_value(plaintext)


def _decode_credentials(stored: str | None) -> dict[str, Any] | None:
    """Decrypt and deserialise stored credentials back to a dict.

    Returns ``None`` when *stored* is empty or cannot be decoded.
    """
    if not stored:
        return None
    plaintext = decrypt_value(stored)
    if not plaintext:
        return None
    try:
        return json.loads(plaintext)
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to decode credentials JSON after decryption")
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", summary="List integrations for the current user")
def list_integrations(
    request: Request,
    db: DbSession,
    owner_id: CurrentOwner,
    direction: str | None = None,
    integration_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return all integrations belonging to the authenticated user.

    Optional query-string filters:

    - ``direction`` — ``SOURCE`` or ``DESTINATION``
    - ``integration_type`` — e.g. ``IMAP``, ``S3``, ``DROPBOX``
    """
    query = db.query(UserIntegration).filter(UserIntegration.owner_id == owner_id)

    if direction is not None:
        _validate_direction(direction)
        query = query.filter(UserIntegration.direction == direction)

    if integration_type is not None:
        _validate_integration_type(integration_type)
        query = query.filter(UserIntegration.integration_type == integration_type)

    integrations = query.order_by(UserIntegration.id).all()
    return [_to_response(i) for i in integrations]


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a new integration")
def create_integration(
    request: Request,
    body: IntegrationCreate,
    db: DbSession,
    owner_id: CurrentOwner,
) -> dict[str, Any]:
    """Create a new source or destination integration for the current user.

    ``credentials`` are encrypted at rest using Fernet symmetric encryption
    before being persisted and are **never** returned in API responses.

    Quota is enforced against the user's subscription plan before the
    integration is persisted.
    """
    _validate_direction(body.direction)
    _validate_integration_type(body.integration_type)

    _check_quota(db, owner_id, body.direction, body.integration_type)

    integration = UserIntegration(
        owner_id=owner_id,
        direction=body.direction,
        integration_type=body.integration_type,
        name=body.name,
        config=json.dumps(body.config) if body.config is not None else None,
        credentials=_encode_credentials(body.credentials),
        is_active=body.is_active,
    )

    try:
        db.add(integration)
        db.commit()
        db.refresh(integration)
    except Exception:
        db.rollback()
        raise

    logger.info(
        "User %s created %s integration %d (%s)",
        owner_id,
        body.direction,
        integration.id,
        body.integration_type,
    )
    return _to_response(integration)


@router.get("/{integration_id}", summary="Get a single integration")
def get_integration(
    integration_id: int,
    request: Request,
    db: DbSession,
    owner_id: CurrentOwner,
) -> dict[str, Any]:
    """Return a single integration by ID (must belong to the current user)."""
    integration = (
        db.query(UserIntegration)
        .filter(UserIntegration.id == integration_id, UserIntegration.owner_id == owner_id)
        .first()
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return _to_response(integration)


@router.put("/{integration_id}", summary="Update an integration")
def update_integration(
    integration_id: int,
    request: Request,
    body: IntegrationUpdate,
    db: DbSession,
    owner_id: CurrentOwner,
) -> dict[str, Any]:
    """Update an existing integration.  Only provided fields are changed.

    When ``credentials`` is supplied the stored value is replaced in full
    with the freshly encrypted version of the new credentials dict.
    """
    integration = (
        db.query(UserIntegration)
        .filter(UserIntegration.id == integration_id, UserIntegration.owner_id == owner_id)
        .first()
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    if body.name is not None:
        integration.name = body.name
    if body.config is not None:
        integration.config = json.dumps(body.config)
    if body.credentials is not None:
        integration.credentials = _encode_credentials(body.credentials)
    if body.is_active is not None:
        integration.is_active = body.is_active

    # Reset last_error so the next operation gives a fresh result
    integration.last_error = None

    try:
        db.commit()
        db.refresh(integration)
    except Exception:
        db.rollback()
        raise

    logger.info("User %s updated integration %d", owner_id, integration_id)
    return _to_response(integration)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an integration")
def delete_integration(
    integration_id: int,
    request: Request,
    db: DbSession,
    owner_id: CurrentOwner,
) -> None:
    """Delete an integration permanently."""
    integration = (
        db.query(UserIntegration)
        .filter(UserIntegration.id == integration_id, UserIntegration.owner_id == owner_id)
        .first()
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    try:
        db.delete(integration)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("User %s deleted integration %d", owner_id, integration_id)


@router.get("/{integration_id}/credentials", summary="Retrieve decrypted credentials for an integration")
def get_integration_credentials(
    integration_id: int,
    request: Request,
    db: DbSession,
    owner_id: CurrentOwner,
) -> dict[str, Any]:
    """Return the decrypted credentials dict for a saved integration.

    This endpoint is intended for internal use by background tasks that need
    to authenticate with a third-party service.  Treat the response as
    sensitive — it contains plaintext secrets.
    """
    integration = (
        db.query(UserIntegration)
        .filter(UserIntegration.id == integration_id, UserIntegration.owner_id == owner_id)
        .first()
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    credentials = _decode_credentials(integration.credentials)
    return {"credentials": credentials or {}}


# ---------------------------------------------------------------------------
# Connection test helpers
# ---------------------------------------------------------------------------


def _test_imap_connection(config: dict[str, Any] | None, credentials: dict[str, Any] | None) -> dict[str, Any]:
    """Test an IMAP connection using the provided config and credentials."""
    import imaplib

    cfg = config or {}
    creds = credentials or {}
    host = cfg.get("host", "")
    port = int(cfg.get("port", 993))
    username = cfg.get("username", "")
    password = creds.get("password", "")
    use_ssl = cfg.get("use_ssl", True)

    if not host or not username or not password:
        return {"success": False, "message": "Missing required fields: host, username, and password"}

    from app.utils.network import is_private_ip

    if is_private_ip(host):
        logger.warning("SSRF blocked: Attempt to connect to private IP %s", host)
        return {"success": False, "message": "Connection error: Invalid hostname or IP address"}

    try:
        if use_ssl:
            mail = imaplib.IMAP4_SSL(host, port)
        else:
            mail = imaplib.IMAP4(host, port)
        mail.login(username, password)
        mail.logout()
        return {"success": True, "message": "IMAP connection successful"}
    except OSError as exc:
        logger.warning("IMAP network error for %s@%s: %s", username, host, exc)
        return {"success": False, "message": "IMAP connection failed — check host, port, and network connectivity"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("IMAP error for %s@%s: %s", username, host, exc)
        return {"success": False, "message": "IMAP authentication or connection failed"}


def _test_s3_connection(config: dict[str, Any] | None, credentials: dict[str, Any] | None) -> dict[str, Any]:
    """Test an S3 connection by calling HeadBucket."""
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        return {"success": False, "message": "boto3 is not installed"}

    cfg = config or {}
    creds = credentials or {}
    bucket = cfg.get("bucket", "")
    region = cfg.get("region", "us-east-1")
    endpoint_url = cfg.get("endpoint_url")

    if not bucket:
        return {"success": False, "message": "Missing required field: bucket"}

    if endpoint_url:
        from urllib.parse import urlparse

        from app.utils.network import is_private_ip

        parsed_url = urlparse(endpoint_url)
        if parsed_url.hostname and is_private_ip(parsed_url.hostname):
            logger.warning("SSRF blocked: Attempt to connect to private IP via S3 endpoint %s", endpoint_url)
            return {"success": False, "message": "Connection error: Invalid endpoint URL or private IP"}

    try:
        client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=creds.get("access_key_id", ""),
            aws_secret_access_key=creds.get("secret_access_key", ""),
            endpoint_url=endpoint_url,
        )
        client.head_bucket(Bucket=bucket)
        return {"success": True, "message": f"S3 bucket '{bucket}' is accessible"}
    except (BotoCoreError, ClientError) as exc:
        logger.warning("S3 connection error for bucket '%s': %s", bucket, exc)
        return {"success": False, "message": "S3 connection failed — check bucket name, region, and credentials"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("S3 unexpected error for bucket '%s': %s", bucket, exc)
        return {"success": False, "message": "S3 connection failed"}


def _test_dropbox_connection(config: dict[str, Any] | None, credentials: dict[str, Any] | None) -> dict[str, Any]:
    """Test a Dropbox connection by verifying OAuth credentials via the Dropbox API."""
    if dbx_lib is None:
        return {"success": False, "message": "dropbox package is not installed"}  # pragma: no cover

    creds = credentials or {}
    app_key = creds.get("app_key", "")
    app_secret = creds.get("app_secret", "")
    refresh_token = creds.get("refresh_token", "")

    if not refresh_token:
        return {"success": False, "message": "Missing required credential: refresh_token"}
    if not app_key or not app_secret:
        return {"success": False, "message": "Missing required credentials: app_key and app_secret"}

    try:
        dbx = dbx_lib.Dropbox(
            app_key=app_key,
            app_secret=app_secret,
            oauth2_refresh_token=refresh_token,
        )
        account = dbx.users_get_current_account()
        display_name = getattr(account, "name", None)
        name_str = ""
        if display_name:
            name_str = f" ({getattr(display_name, 'display_name', '') or ''})"
        return {"success": True, "message": f"Dropbox connection successful{name_str}"}
    except _DropboxAuthError as exc:
        logger.warning("Dropbox auth error: %s", exc)
        return {
            "success": False,
            "message": "Dropbox authentication failed — check app_key, app_secret, and refresh_token",
        }
    except _DropboxBadInputError as exc:
        logger.warning("Dropbox bad input error: %s", exc)
        return {"success": False, "message": "Dropbox connection failed — invalid credentials format"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Dropbox connection error: %s", exc)
        return {"success": False, "message": "Dropbox connection failed — check credentials and network connectivity"}


def _test_webdav_connection(config: dict[str, Any] | None, credentials: dict[str, Any] | None) -> dict[str, Any]:
    """Test a WebDAV/Nextcloud connection by issuing an HTTP PROPFIND."""
    import httpx

    cfg = config or {}
    creds = credentials or {}
    url = cfg.get("url", "")
    username = creds.get("username", "")
    password = creds.get("password", "")

    if not url:
        return {"success": False, "message": "Missing required field: url"}

    # Only allow http/https to prevent file:// or other custom scheme attacks
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"success": False, "message": "URL must use http or https scheme"}

    # Block requests to private/internal IPs to prevent SSRF
    hostname = parsed.hostname or ""
    if hostname:
        from app.utils.network import is_private_ip

        if is_private_ip(hostname):
            return {"success": False, "message": "URLs pointing to internal or private networks are not allowed"}

    try:
        auth = (username, password) if username and password else None
        headers = {"Depth": "0"}

        # Use httpx for secure connection testing, avoiding urllib vulnerabilities
        resp = httpx.request("PROPFIND", url, auth=auth, headers=headers, timeout=10.0, follow_redirects=False)
        if resp.status_code < 400:
            return {"success": True, "message": "WebDAV connection successful"}
        return {"success": False, "message": f"WebDAV returned HTTP {resp.status_code}"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("WebDAV connection error for %s: %s", hostname, exc)
        return {"success": False, "message": "WebDAV connection failed — check URL and credentials"}


_CONNECTION_TESTERS: dict[str, Any] = {
    IntegrationType.DROPBOX: _test_dropbox_connection,
    IntegrationType.IMAP: _test_imap_connection,
    IntegrationType.S3: _test_s3_connection,
    IntegrationType.WEBDAV: _test_webdav_connection,
    IntegrationType.NEXTCLOUD: _test_webdav_connection,
}


# ---------------------------------------------------------------------------
# Test & quota endpoints
# ---------------------------------------------------------------------------


@router.post("/test", summary="Test an integration connection without saving")
def test_integration_connection(
    request: Request,
    body: IntegrationTestRequest,
    owner_id: CurrentOwner,
) -> dict[str, Any]:
    """Test integration credentials without persisting anything.

    Useful for the "Test connection" button in the UI before the user saves
    a new integration.  Returns ``{"success": bool, "message": str}``.
    """
    _validate_integration_type(body.integration_type)

    tester = _CONNECTION_TESTERS.get(body.integration_type)
    if tester is None:
        return {
            "success": False,
            "message": f"Connection testing is not yet supported for '{body.integration_type}'. "
            "The integration can still be saved and will be validated on first use.",
        }

    return tester(body.config, body.credentials)


@router.get("/quota/", summary="Get integration quota information for the current user")
def get_integration_quota(
    request: Request,
    db: DbSession,
    owner_id: CurrentOwner,
) -> dict[str, Any]:
    """Return the user's current integration usage vs. their plan quota.

    Includes separate counts for destinations and IMAP sources.
    """
    tier_id = get_user_tier_id(db, owner_id)
    tier = get_tier(tier_id, db)

    max_dest = _get_max_destinations(tier)
    max_src = _get_max_sources(tier)

    dest_count = (
        db.query(UserIntegration)
        .filter(
            UserIntegration.owner_id == owner_id,
            UserIntegration.direction == IntegrationDirection.DESTINATION,
        )
        .count()
    )

    src_count = (
        db.query(UserIntegration)
        .filter(
            UserIntegration.owner_id == owner_id,
            UserIntegration.direction == IntegrationDirection.SOURCE,
            UserIntegration.integration_type.in_(list(_MAILBOX_SOURCE_TYPES)),
        )
        .count()
    )

    return {
        "tier_id": tier_id,
        "tier_name": tier.get("name", tier_id),
        "destinations": {
            "current_count": dest_count,
            "max_allowed": max_dest,
            "can_add": max_dest is None or dest_count < max_dest,
        },
        "sources": {
            "current_count": src_count,
            "max_allowed": max_src,
            "can_add": max_src is None or (max_src > 0 and src_count < max_src),
        },
    }
