"""Transactional rotation of database values encrypted by ``SESSION_SECRET``."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import ApplicationSettings, UserImapAccount, UserIntegration
from app.utils.encryption import rotate_encrypted_value, value_uses_primary_key
from app.utils.settings_service import get_setting_metadata


@dataclass(frozen=True)
class RotationReport:
    scanned: int
    rotated: int
    invalid: int


def _query_rows(db: Session, model: type[object], *, lock_rows: bool) -> list[object]:
    query = db.query(model)
    if lock_rows:
        query = query.with_for_update()
    return query.all()


def _encrypted_columns(db: Session, *, lock_rows: bool) -> list[tuple[object, str]]:
    """Return model rows and encrypted attributes without exposing values."""
    rows: list[tuple[object, str]] = []
    for setting in _query_rows(db, ApplicationSettings, lock_rows=lock_rows):
        metadata = get_setting_metadata(setting.key)
        if metadata.get("sensitive", False) and not metadata.get("environment_only", False):
            rows.append((setting, "value"))
    rows.extend((row, "credentials") for row in _query_rows(db, UserIntegration, lock_rows=lock_rows))
    rows.extend((row, "password") for row in _query_rows(db, UserImapAccount, lock_rows=lock_rows))
    return rows


def rotate_database_encryption(db: Session, *, verify_only: bool = False) -> RotationReport:
    """Rotate every known encrypted database column in one transaction.

    The function reports counts only. Any undecryptable value aborts the whole
    transaction so a partial key migration cannot be committed.
    """
    rows = _encrypted_columns(db, lock_rows=not verify_only)
    rotated = 0
    invalid = 0

    if verify_only:
        for row, attribute in rows:
            if not value_uses_primary_key(getattr(row, attribute)):
                invalid += 1
        return RotationReport(scanned=len(rows), rotated=0, invalid=invalid)

    try:
        for row, attribute in rows:
            new_value, changed = rotate_encrypted_value(getattr(row, attribute))
            if changed:
                setattr(row, attribute, new_value)
                rotated += 1
        db.commit()
    except Exception:
        db.rollback()
        raise

    return RotationReport(scanned=len(rows), rotated=rotated, invalid=0)
