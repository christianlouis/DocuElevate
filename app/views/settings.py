"""
Settings management views for the application.
"""

import inspect
import logging
import os
from functools import wraps

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.utils.config_validator.masking import mask_sensitive_value
from app.utils.settings_service import (
    SETTING_METADATA,
    get_all_settings_from_db,
    get_setting_metadata,
    get_settings_by_category,
)
from app.views.base import APIRouter, get_db, require_login, settings, templates

logger = logging.getLogger(__name__)
router = APIRouter()


def require_admin_access(func):
    """
    Decorator to require admin access for a route.

    This decorator checks if the user in the session has admin privileges.
    If not, redirects to the home page. Works with both sync and async functions,
    though FastAPI route handlers should always be async.
    """

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        user = request.session.get("user")
        if not user or not user.get("is_admin"):
            logger.warning("Non-admin user attempted to access admin-only route")
            return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

        # FastAPI route handlers are async, but we support sync for flexibility
        if inspect.iscoroutinefunction(func):
            return await func(request, *args, **kwargs)
        else:
            return func(request, *args, **kwargs)

    return wrapper


@router.get("/settings")
@require_login
@require_admin_access
async def settings_page(request: Request, db: Session = Depends(get_db)):
    """
    Settings management page - admin only.

    This page is a convenience feature to view and edit settings.
    Values are displayed in precedence order: Database > Environment > Defaults
    """

    try:
        # Get settings from database
        db_settings = get_all_settings_from_db(db)

        # Get settings organized by category
        categories = get_settings_by_category()

        # Build settings data for display
        settings_data = {}
        for category, keys in categories.items():
            settings_data[category] = []
            for key in keys:
                # Determine the source of this setting and get the effective value
                # Check if it's in the database (DB takes precedence)
                if key in db_settings:
                    source = "database"
                    source_label = "DB"
                    source_color = "green"
                    value = db_settings[key]
                # Check if it's from environment variable
                elif key.upper() in os.environ or key in os.environ:
                    source = "environment"
                    source_label = "ENV"
                    source_color = "blue"
                    value = getattr(settings, key, None)
                else:
                    # It's using the default value
                    source = "default"
                    source_label = "DEFAULT"
                    source_color = "gray"
                    value = getattr(settings, key, None)

                # Get metadata
                metadata = get_setting_metadata(key)

                # Mask sensitive values
                display_value = value
                if metadata.get("sensitive") and value:
                    display_value = mask_sensitive_value(value)

                settings_data[category].append(
                    {
                        "key": key,
                        "display_value": (display_value if display_value is not None else ""),
                        "metadata": metadata,
                        "source": source,
                        "source_label": source_label,
                        "source_color": source_color,
                    }
                )

        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "settings_data": settings_data,
                "app_version": settings.version,
            },
        )
    except Exception as e:
        logger.error(f"Error loading settings page: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load settings page",
        )


@router.get("/admin/credentials")
@require_login
@require_admin_access
async def credentials_page(request: Request, db: Session = Depends(get_db)):
    """
    Credential audit page - admin only.

    Displays all sensitive credential settings grouped by category, showing
    whether each is configured and whether it comes from the database or an
    environment variable. Supports the credential rotation workflow.
    """
    try:
        db_settings = get_all_settings_from_db(db)
        categories: dict[str, list[dict]] = {}

        for key, meta in SETTING_METADATA.items():
            if not meta.get("sensitive", False):
                continue

            env_value = getattr(settings, key, None)
            in_db = key in db_settings and db_settings[key]

            if in_db:
                source = "db"
                configured = True
            elif env_value:
                source = "env"
                configured = True
            else:
                source = None
                configured = False

            category = meta.get("category", "Other")
            if category not in categories:
                categories[category] = []

            categories[category].append(
                {
                    "key": key,
                    "description": meta.get("description", ""),
                    "configured": configured,
                    "source": source,
                    "restart_required": meta.get("restart_required", False),
                }
            )

        total = sum(len(v) for v in categories.values())
        configured_count = sum(1 for creds in categories.values() for c in creds if c["configured"])

        return templates.TemplateResponse(
            "credentials.html",
            {
                "request": request,
                "categories": categories,
                "total": total,
                "configured_count": configured_count,
                "unconfigured_count": total - configured_count,
                "app_version": settings.version,
            },
        )
    except Exception as e:
        logger.error(f"Error loading credentials page: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load credentials page",
        )


@router.get("/admin/connections")
@require_login
@require_admin_access
async def connections_page(request: Request, db: Session = Depends(get_db)):
    """
    Connections management page - admin only.

    Allows administrators to configure external authentication providers,
    SSO settings, and service integrations through a wizard-like interface.
    """
    try:
        from app.auth import OAUTH_CONFIGURED, SOCIAL_PROVIDERS

        db_settings = get_all_settings_from_db(db)

        def _get_effective(key: str):
            """Return DB value if present, else fall back to settings attr."""
            if key in db_settings and db_settings[key] is not None:
                return db_settings[key]
            return getattr(settings, key, None)

        def _is_truthy(val) -> bool:
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes")
            return bool(val)

        # Build service status list
        services = []

        # --- SSO (Authentik / OIDC) ---
        services.append(
            {
                "key": "oidc",
                "name": settings.oauth_provider_name or "Single Sign-On",
                "icon": "fas fa-lock",
                "type": "SSO",
                "linked": OAUTH_CONFIGURED,
                "description": "OpenID Connect SSO provider",
                "settings_keys": [
                    "authentik_client_id",
                    "authentik_client_secret",
                    "authentik_config_url",
                    "oauth_provider_name",
                ],
            }
        )

        # --- Google ---
        services.append(
            {
                "key": "google",
                "name": "Google",
                "icon": "fab fa-google",
                "type": "Sign-in authentication",
                "linked": "google" in SOCIAL_PROVIDERS,
                "description": "Sign-in authentication",
                "settings_keys": [
                    "social_auth_google_enabled",
                    "social_auth_google_client_id",
                    "social_auth_google_client_secret",
                ],
            }
        )

        # --- GitHub ---
        services.append(
            {
                "key": "github",
                "name": "GitHub",
                "icon": "fab fa-github",
                "type": "Sign-in authentication",
                "linked": "github" in SOCIAL_PROVIDERS,
                "description": "Sign-in authentication",
                "settings_keys": [
                    "social_auth_github_enabled",
                    "social_auth_github_client_id",
                    "social_auth_github_client_secret",
                ],
            }
        )

        # --- Microsoft ---
        services.append(
            {
                "key": "microsoft",
                "name": "Microsoft",
                "icon": "fab fa-microsoft",
                "type": "Sign-in authentication",
                "linked": "microsoft" in SOCIAL_PROVIDERS,
                "description": "Sign-in authentication",
                "settings_keys": [
                    "social_auth_microsoft_enabled",
                    "social_auth_microsoft_client_id",
                    "social_auth_microsoft_client_secret",
                    "social_auth_microsoft_tenant",
                ],
            }
        )

        # --- Apple ---
        services.append(
            {
                "key": "apple",
                "name": "Apple",
                "icon": "fab fa-apple",
                "type": "Sign-in authentication",
                "linked": "apple" in SOCIAL_PROVIDERS,
                "description": "Sign-in authentication",
                "settings_keys": [
                    "social_auth_apple_enabled",
                    "social_auth_apple_client_id",
                    "social_auth_apple_team_id",
                    "social_auth_apple_key_id",
                    "social_auth_apple_private_key",
                ],
            }
        )

        # --- Dropbox ---
        services.append(
            {
                "key": "dropbox",
                "name": "Dropbox",
                "icon": "fab fa-dropbox",
                "type": "Sign-in authentication",
                "linked": "dropbox" in SOCIAL_PROVIDERS,
                "description": "Sign-in authentication",
                "settings_keys": [
                    "social_auth_dropbox_enabled",
                    "social_auth_dropbox_client_id",
                    "social_auth_dropbox_client_secret",
                    "social_auth_dropbox_use_global_credentials",
                ],
            }
        )

        # --- Keycloak ---
        services.append(
            {
                "key": "keycloak",
                "name": "Keycloak",
                "icon": "fas fa-key",
                "type": "SSO",
                "linked": "keycloak" in SOCIAL_PROVIDERS,
                "description": "SSO",
                "settings_keys": [
                    "social_auth_keycloak_enabled",
                    "social_auth_keycloak_client_id",
                    "social_auth_keycloak_client_secret",
                    "social_auth_keycloak_server_url",
                    "social_auth_keycloak_realm",
                ],
            }
        )

        # --- Generic OAuth2 ---
        services.append(
            {
                "key": "generic_oauth2",
                "name": "Generic OAuth2",
                "icon": "fas fa-sign-in-alt",
                "type": "SSO",
                "linked": "generic_oauth2" in SOCIAL_PROVIDERS,
                "description": "SSO",
                "settings_keys": [
                    "social_auth_generic_oauth2_enabled",
                    "social_auth_generic_oauth2_client_id",
                    "social_auth_generic_oauth2_client_secret",
                    "social_auth_generic_oauth2_authorize_url",
                    "social_auth_generic_oauth2_token_url",
                    "social_auth_generic_oauth2_userinfo_url",
                    "social_auth_generic_oauth2_scope",
                    "social_auth_generic_oauth2_name",
                ],
            }
        )

        # --- SAML2 ---
        _saml2_configured = bool(
            _is_truthy(_get_effective("social_auth_saml2_enabled"))
            and _get_effective("social_auth_saml2_sso_url")
            and _get_effective("social_auth_saml2_entity_id")
        )
        services.append(
            {
                "key": "saml2",
                "name": settings.social_auth_saml2_name or "SAML2",
                "icon": "fas fa-id-badge",
                "type": "SSO (SAML)",
                "linked": _saml2_configured,
                "description": "SSO (SAML)",
                "settings_keys": [
                    "social_auth_saml2_enabled",
                    "social_auth_saml2_entity_id",
                    "social_auth_saml2_sso_url",
                    "social_auth_saml2_certificate",
                    "social_auth_saml2_name",
                ],
            }
        )

        # --- SMTP Mail ---
        _smtp_configured = bool(_get_effective("email_host") and _get_effective("email_username"))
        services.append(
            {
                "key": "smtp",
                "name": "SMTP Mail",
                "icon": "fas fa-envelope",
                "type": "Email Notifications",
                "linked": _smtp_configured,
                "description": "Email Notifications",
                "settings_keys": [
                    "email_host",
                    "email_port",
                    "email_username",
                    "email_password",
                    "email_use_tls",
                    "email_sender",
                ],
            }
        )

        # --- Telegram Bot ---
        _telegram_configured = bool(
            _is_truthy(_get_effective("telegram_enabled")) and _get_effective("telegram_bot_token")
        )
        services.append(
            {
                "key": "telegram",
                "name": "Telegram Bot",
                "icon": "fab fa-telegram",
                "type": "Notifications",
                "linked": _telegram_configured,
                "description": "Configure Telegram bot connectivity, access controls, and feedback behavior.",
                "settings_keys": [
                    "telegram_enabled",
                    "telegram_bot_token",
                    "telegram_chat_id",
                ],
            }
        )

        # Get setting details for the modal forms
        service_settings = {}
        for svc in services:
            svc_settings = []
            for skey in svc["settings_keys"]:
                meta = get_setting_metadata(skey)
                # Get current effective value
                val = _get_effective(skey)
                display_val = val
                if meta.get("sensitive") and val:
                    display_val = mask_sensitive_value(val)
                svc_settings.append(
                    {
                        "key": skey,
                        "value": val,
                        "display_value": display_val if display_val is not None else "",
                        "metadata": meta,
                    }
                )
            service_settings[svc["key"]] = svc_settings

        # Feature toggles
        sso_auto_login = _is_truthy(_get_effective("sso_auto_login"))
        qr_login_enabled = _is_truthy(_get_effective("qr_login_challenge_ttl_seconds"))
        frontend_url_configured = bool(_get_effective("public_base_url"))

        return templates.TemplateResponse(
            "admin_connections.html",
            {
                "request": request,
                "services": services,
                "service_settings": service_settings,
                "sso_auto_login": sso_auto_login,
                "oauth_configured": OAUTH_CONFIGURED,
                "qr_login_enabled": qr_login_enabled,
                "frontend_url_configured": frontend_url_configured,
                "app_version": settings.version,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading connections page: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load connections page",
        )


@router.get("/admin/settings/audit-log")
@require_login
@require_admin_access
async def audit_log_page(request: Request, db: Session = Depends(get_db)):
    """
    Settings audit log page - admin only.

    Displays a chronological log of all configuration changes made via the
    settings UI, including who made the change and what the old/new values
    were.  Sensitive values are masked.  Provides rollback buttons to revert
    any setting to a previous value.
    """
    from app.utils.settings_service import get_audit_log

    try:
        entries = get_audit_log(db, limit=200)
        return templates.TemplateResponse(
            "audit_log.html",
            {
                "request": request,
                "entries": entries,
                "app_version": settings.version,
            },
        )
    except Exception as e:
        logger.error(f"Error loading audit log page: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load audit log page",
        )
