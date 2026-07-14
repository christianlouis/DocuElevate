"""Resolve Dropbox OAuth credentials without copying operator secrets to users."""

from typing import Any

from app.config import settings


def resolve_dropbox_oauth_credentials(credentials: dict[str, Any]) -> tuple[str, str, str]:
    """Return ``(app_key, app_secret, refresh_token)`` for a user integration.

    Personal OAuth grants may reference the operator-managed Dropbox application.
    In that mode only the refresh token is stored in the encrypted user record;
    the application credentials remain in the operator configuration.
    """
    uses_operator_app = bool(credentials.get("use_global_app_secret")) or credentials.get("auth_mode") == "operator"
    refresh_token = str(credentials.get("refresh_token") or "")
    if not refresh_token:
        if uses_operator_app:
            raise ValueError("Dropbox integration is missing refresh_token in credentials")
        raise ValueError("Dropbox integration is missing app_key, app_secret or refresh_token in credentials")

    if uses_operator_app:
        if not settings.dropbox_allow_global_credentials_for_integrations:
            raise ValueError("Dropbox operator application credentials are not enabled for user integrations")
        app_key = settings.dropbox_app_key or ""
        app_secret = settings.dropbox_app_secret or ""
    else:
        app_key = str(credentials.get("app_key") or "")
        app_secret = str(credentials.get("app_secret") or "")

    if not app_key or not app_secret:
        raise ValueError("Dropbox integration is missing app_key or app_secret in application credentials")
    return app_key, app_secret, refresh_token
