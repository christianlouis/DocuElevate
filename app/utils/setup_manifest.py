"""Declarative, idempotent setup manifests for humans and automation agents."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.config import settings
from app.models import LocalUser, Tenant, Tribe, TribeMembership, UserProfile
from app.utils.local_auth import hash_password, verify_password
from app.utils.settings_service import (
    SETTING_METADATA,
    get_setting_from_db,
    get_setting_metadata,
    save_setting_to_db,
    validate_setting_value,
)
from app.utils.settings_sync import notify_settings_updated
from app.utils.setup_wizard import get_missing_required_settings
from app.utils.tribe_scope import DEFAULT_TENANT_ID, ensure_personal_scope, personal_tribe_id

MANIFEST_API_VERSION = "docuelevate.org/v1alpha1"
MANIFEST_KIND = "DocuElevateSetup"
BOOTSTRAP_SETTING_KEYS = {"database_url", "session_secret"}
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{2,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_MANIFEST_BYTES = 1024 * 1024


class SetupManifestError(ValueError):
    """Raised when a setup manifest is unsafe or structurally invalid."""


def load_setup_manifest(path: str | Path) -> dict[str, Any]:
    """Read a bounded JSON setup manifest from disk."""
    manifest_path = Path(path)
    if manifest_path.suffix.lower() != ".json":
        raise SetupManifestError("Setup manifests must use the .json extension")
    if manifest_path.stat().st_size > _MAX_MANIFEST_BYTES:
        raise SetupManifestError("Setup manifest exceeds the 1 MiB limit")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupManifestError(f"Could not read setup manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise SetupManifestError("Setup manifest root must be an object")
    return payload


def _scalar_string(value: Any, *, path: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)) and not isinstance(value, complex):
        return str(value)
    raise SetupManifestError(f"{path} must be a string, number, boolean, or fromEnv reference")


def _resolve_value(value: Any, *, path: str, environ: Mapping[str, str]) -> tuple[str, str | None]:
    if not isinstance(value, dict):
        return _scalar_string(value, path=path), None
    if set(value) != {"fromEnv"}:
        raise SetupManifestError(f'{path} supports only {{"fromEnv": "NAME"}} references')
    env_name = value["fromEnv"]
    if not isinstance(env_name, str) or not _ENV_NAME_RE.fullmatch(env_name):
        raise SetupManifestError(f"{path}.fromEnv must be a valid environment variable name")
    resolved = environ.get(env_name)
    if not resolved:
        raise SetupManifestError(f"Required environment variable {env_name} is not set")
    return resolved, env_name


def _validate_root(manifest: dict[str, Any]) -> dict[str, Any]:
    allowed_root = {"apiVersion", "kind", "metadata", "spec"}
    unknown = sorted(set(manifest) - allowed_root)
    if unknown:
        raise SetupManifestError(f"Unknown manifest fields: {', '.join(unknown)}")
    if manifest.get("apiVersion") != MANIFEST_API_VERSION:
        raise SetupManifestError(f"apiVersion must be {MANIFEST_API_VERSION}")
    if manifest.get("kind") != MANIFEST_KIND:
        raise SetupManifestError(f"kind must be {MANIFEST_KIND}")
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict) or not str(metadata.get("name") or "").strip():
        raise SetupManifestError("metadata.name is required")
    unknown_metadata = sorted(set(metadata) - {"name"})
    if unknown_metadata:
        raise SetupManifestError(f"Unknown metadata fields: {', '.join(unknown_metadata)}")
    spec = manifest.get("spec")
    if not isinstance(spec, dict):
        raise SetupManifestError("spec must be an object")
    unknown_spec = sorted(set(spec) - {"completeSetup", "settings", "users", "tribes"})
    if unknown_spec:
        raise SetupManifestError(f"Unsupported spec fields: {', '.join(unknown_spec)}")
    if "completeSetup" in spec and not isinstance(spec["completeSetup"], bool):
        raise SetupManifestError("spec.completeSetup must be a boolean")
    return spec


def resolve_setup_manifest(
    manifest: dict[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate and resolve secret references without writing anything."""
    env = environ if environ is not None else os.environ
    spec = _validate_root(manifest)
    resolved_settings: list[dict[str, Any]] = []
    raw_settings = spec.get("settings", {})
    if not isinstance(raw_settings, dict):
        raise SetupManifestError("spec.settings must be an object")
    for key, raw_value in raw_settings.items():
        if key not in SETTING_METADATA:
            raise SetupManifestError(f"Unknown setting: {key}")
        if key in BOOTSTRAP_SETTING_KEYS:
            raise SetupManifestError(f"{key} is deployment bootstrap state and cannot be stored by a manifest")
        value, env_name = _resolve_value(raw_value, path=f"spec.settings.{key}", environ=env)
        metadata = get_setting_metadata(key)
        if metadata.get("sensitive") and env_name is None:
            raise SetupManifestError(f"Sensitive setting {key} must use a fromEnv reference")
        valid, error = validate_setting_value(key, value)
        if not valid:
            raise SetupManifestError(error or f"Invalid setting: {key}")
        resolved_settings.append({"key": key, "value": value, "from_env": env_name})

    resolved_users: list[dict[str, Any]] = []
    raw_users = spec.get("users", [])
    if not isinstance(raw_users, list):
        raise SetupManifestError("spec.users must be an array")
    seen_emails: set[str] = set()
    seen_usernames: set[str] = set()
    for index, raw_user in enumerate(raw_users):
        path = f"spec.users[{index}]"
        if not isinstance(raw_user, dict):
            raise SetupManifestError(f"{path} must be an object")
        unknown_user = sorted(set(raw_user) - {"email", "username", "displayName", "password", "isAdmin"})
        if unknown_user:
            raise SetupManifestError(f"Unknown fields in {path}: {', '.join(unknown_user)}")
        email = str(raw_user.get("email") or "").strip().lower()
        username = str(raw_user.get("username") or "").strip()
        if not _EMAIL_RE.fullmatch(email):
            raise SetupManifestError(f"{path}.email is invalid")
        if not _USERNAME_RE.fullmatch(username):
            raise SetupManifestError(f"{path}.username is invalid")
        if email in seen_emails:
            raise SetupManifestError(f"Duplicate user email: {email}")
        if username in seen_usernames:
            raise SetupManifestError(f"Duplicate username: {username}")
        seen_emails.add(email)
        seen_usernames.add(username)
        if "isAdmin" in raw_user and not isinstance(raw_user["isAdmin"], bool):
            raise SetupManifestError(f"{path}.isAdmin must be a boolean")
        password, password_env = _resolve_value(raw_user.get("password"), path=f"{path}.password", environ=env)
        if password_env is None:
            raise SetupManifestError(f"{path}.password must use a fromEnv reference")
        if len(password) < 12:
            raise SetupManifestError(f"{path}.password must contain at least 12 characters")
        resolved_users.append(
            {
                "email": email,
                "username": username,
                "display_name": str(raw_user.get("displayName") or username).strip(),
                "password": password,
                "password_from_env": password_env,
                "is_admin": bool(raw_user.get("isAdmin", False)),
            }
        )

    resolved_tribes: list[dict[str, Any]] = []
    raw_tribes = spec.get("tribes", [])
    if not isinstance(raw_tribes, list):
        raise SetupManifestError("spec.tribes must be an array")
    seen_tribe_names: set[str] = set()
    for index, raw_tribe in enumerate(raw_tribes):
        path = f"spec.tribes[{index}]"
        if not isinstance(raw_tribe, dict) or set(raw_tribe) - {"name", "members"}:
            raise SetupManifestError(f"{path} supports only name and members")
        name = str(raw_tribe.get("name") or "").strip()
        members = raw_tribe.get("members", [])
        if not name or not isinstance(members, list) or not members:
            raise SetupManifestError(f"{path} requires a name and at least one member")
        if name in seen_tribe_names:
            raise SetupManifestError(f"Duplicate Tribe name: {name}")
        seen_tribe_names.add(name)
        resolved_members = []
        seen_member_emails: set[str] = set()
        for member_index, member in enumerate(members):
            if not isinstance(member, dict) or set(member) - {"email", "role"}:
                raise SetupManifestError(f"{path}.members[{member_index}] supports only email and role")
            email = str(member.get("email") or "").strip().lower()
            role = str(member.get("role") or "member").strip().lower()
            if not _EMAIL_RE.fullmatch(email) or role not in {"admin", "member"}:
                raise SetupManifestError(f"Invalid member in {path}.members[{member_index}]")
            if email in seen_member_emails:
                raise SetupManifestError(f"Duplicate member in {path}: {email}")
            seen_member_emails.add(email)
            resolved_members.append({"email": email, "role": role})
        if not any(member["role"] == "admin" for member in resolved_members):
            raise SetupManifestError(f"{path} requires at least one admin member")
        resolved_tribes.append({"name": name, "members": resolved_members})

    return {
        "name": str(manifest["metadata"]["name"]).strip(),
        "complete_setup": bool(spec.get("completeSetup", False)),
        "settings": resolved_settings,
        "users": resolved_users,
        "tribes": resolved_tribes,
    }


def _redacted_setting(setting: dict[str, Any]) -> str:
    return "<resolved-secret>" if setting["from_env"] else setting["value"]


def _effective_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def plan_setup_manifest(db: Session, resolved: dict[str, Any]) -> dict[str, Any]:
    """Return a secret-safe desired-state diff."""
    changes: list[dict[str, Any]] = []
    desired_user_emails = {user["email"] for user in resolved["users"]}
    for tribe in resolved["tribes"]:
        for member in tribe["members"]:
            if member["email"] in desired_user_emails:
                continue
            if db.query(UserProfile).filter(UserProfile.user_id == member["email"]).first() is None:
                raise SetupManifestError(f"Tribe member does not exist: {member['email']}")
    for setting in resolved["settings"]:
        key = setting["key"]
        current = get_setting_from_db(db, key)
        if current is None:
            current = getattr(settings, key, None)
        status = (
            "unchanged"
            if _effective_string(current) == setting["value"]
            else ("create" if current is None else "update")
        )
        changes.append({"resource": "setting", "key": key, "status": status, "desired": _redacted_setting(setting)})

    for user in resolved["users"]:
        existing = db.query(LocalUser).filter(LocalUser.email == user["email"]).first()
        username_owner = db.query(LocalUser).filter(LocalUser.username == user["username"]).first()
        if username_owner is not None and (existing is None or username_owner.id != existing.id):
            raise SetupManifestError(f"Username already belongs to another user: {user['username']}")
        status = "create"
        if existing is not None:
            has_personal_scope = (
                db.query(TribeMembership)
                .filter(
                    TribeMembership.tribe_id == personal_tribe_id(user["email"], DEFAULT_TENANT_ID),
                    TribeMembership.user_id == user["email"],
                    TribeMembership.role == "admin",
                )
                .first()
                is not None
            )
            unchanged = (
                existing.username == user["username"]
                and (existing.display_name or existing.username) == user["display_name"]
                and bool(existing.is_admin) == user["is_admin"]
                and bool(existing.is_active)
                and verify_password(user["password"], existing.hashed_password)
                and has_personal_scope
            )
            status = "unchanged" if unchanged else "update"
        changes.append({"resource": "user", "key": user["email"], "status": status, "desired": "configured"})

    for tribe in resolved["tribes"]:
        existing = db.query(Tribe).filter(Tribe.tenant_id == DEFAULT_TENANT_ID, Tribe.name == tribe["name"]).first()
        status = "create"
        if existing is not None:
            current_members = {
                membership.user_id: membership.role
                for membership in db.query(TribeMembership).filter(TribeMembership.tribe_id == existing.id).all()
            }
            desired_members = {member["email"]: member["role"] for member in tribe["members"]}
            status = "unchanged" if current_members == desired_members else "update"
        changes.append(
            {
                "resource": "tribe",
                "key": tribe["name"],
                "status": status,
                "desired": {"members": len(tribe["members"])},
            }
        )

    return {
        "success": True,
        "mode": "plan",
        "manifest": resolved["name"],
        "changes": changes,
        "summary": {
            "create": sum(change["status"] == "create" for change in changes),
            "update": sum(change["status"] == "update" for change in changes),
            "unchanged": sum(change["status"] == "unchanged" for change in changes),
        },
    }


def apply_setup_manifest(db: Session, resolved: dict[str, Any]) -> dict[str, Any]:
    """Apply an already validated manifest and return a secret-safe report."""
    plan = plan_setup_manifest(db, resolved)
    applied: list[dict[str, str]] = []
    restart_required: list[str] = []

    for setting in resolved["settings"]:
        planned = next(
            change for change in plan["changes"] if change["resource"] == "setting" and change["key"] == setting["key"]
        )
        if planned["status"] == "unchanged":
            continue
        if not save_setting_to_db(db, setting["key"], setting["value"], changed_by="agentic_setup"):
            raise SetupManifestError(f"Failed to persist setting {setting['key']}")
        applied.append({"resource": "setting", "key": setting["key"]})
        if get_setting_metadata(setting["key"]).get("restart_required"):
            restart_required.append(setting["key"])

    for user in resolved["users"]:
        planned = next(
            change for change in plan["changes"] if change["resource"] == "user" and change["key"] == user["email"]
        )
        if planned["status"] == "unchanged":
            continue
        existing = db.query(LocalUser).filter(LocalUser.email == user["email"]).first()
        if existing is None:
            existing = LocalUser(email=user["email"], username=user["username"])
            db.add(existing)
        elif existing.username != user["username"]:
            duplicate = (
                db.query(LocalUser).filter(LocalUser.username == user["username"], LocalUser.id != existing.id).first()
            )
            if duplicate:
                raise SetupManifestError(f"Username already belongs to another user: {user['username']}")
        existing.username = user["username"]
        existing.display_name = user["display_name"]
        existing.hashed_password = hash_password(user["password"])
        existing.is_active = True
        existing.is_admin = user["is_admin"]
        profile = db.query(UserProfile).filter(UserProfile.user_id == user["email"]).first()
        if profile is None:
            profile = UserProfile(user_id=user["email"])
            db.add(profile)
        profile.display_name = user["display_name"]
        ensure_personal_scope(db, user["email"], DEFAULT_TENANT_ID)
        applied.append({"resource": "user", "key": user["email"]})
    db.commit()

    tenant = db.query(Tenant).filter(Tenant.id == DEFAULT_TENANT_ID).first()
    if tenant is None:
        tenant = Tenant(id=DEFAULT_TENANT_ID, name="Default tenant")
        db.add(tenant)
        db.commit()
    for tribe_spec in resolved["tribes"]:
        planned = next(
            change
            for change in plan["changes"]
            if change["resource"] == "tribe" and change["key"] == tribe_spec["name"]
        )
        if planned["status"] == "unchanged":
            continue
        tribe = db.query(Tribe).filter(Tribe.tenant_id == DEFAULT_TENANT_ID, Tribe.name == tribe_spec["name"]).first()
        if tribe is None:
            tribe = Tribe(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"docuelevate:tribe:{DEFAULT_TENANT_ID}:{tribe_spec['name']}")),
                tenant_id=DEFAULT_TENANT_ID,
                name=tribe_spec["name"],
            )
            db.add(tribe)
            db.flush()
        desired_emails = {member["email"] for member in tribe_spec["members"]}
        existing_members = db.query(TribeMembership).filter(TribeMembership.tribe_id == tribe.id).all()
        for membership in existing_members:
            if membership.user_id not in desired_emails:
                db.delete(membership)
        for member in tribe_spec["members"]:
            if db.query(UserProfile).filter(UserProfile.user_id == member["email"]).first() is None:
                raise SetupManifestError(f"Tribe member does not exist: {member['email']}")
            membership = (
                db.query(TribeMembership)
                .filter(TribeMembership.tribe_id == tribe.id, TribeMembership.user_id == member["email"])
                .first()
            )
            if membership is None:
                membership = TribeMembership(
                    tenant_id=DEFAULT_TENANT_ID,
                    tribe_id=tribe.id,
                    user_id=member["email"],
                )
                db.add(membership)
            membership.role = member["role"]
        applied.append({"resource": "tribe", "key": tribe_spec["name"]})
    db.commit()

    notify_settings_updated()
    missing = get_missing_required_settings()
    setup_completed = False
    if resolved["complete_setup"] and not missing:
        if not save_setting_to_db(db, "_setup_wizard_completed", "true", changed_by="agentic_setup"):
            raise SetupManifestError("Failed to record setup completion")
        setup_completed = True
        notify_settings_updated()

    return {
        "success": not (resolved["complete_setup"] and missing),
        "mode": "apply",
        "manifest": resolved["name"],
        "applied": applied,
        "setup_completed": setup_completed,
        "missing_required_settings": missing,
        "restart_required": sorted(set(restart_required)),
        "next_actions": [
            "Complete interactive OAuth grants in the browser for integrations that require user consent."
        ],
    }
