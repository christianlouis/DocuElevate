"""
System reset utilities for DocuElevate.

Provides functions to:
- Wipe all user data (database rows + work-files on disk) for a fresh start.
- Wipe with re-import: move original files to a dedicated folder, wipe
  everything, then let the watch-folder mechanism re-ingest the files.

Security: All public functions in this module require admin-level access.
They MUST only be invoked from admin-guarded API/view endpoints.
"""

import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

# Subdirectories inside *workdir* that contain user-generated data.
# Everything else (app code, static assets, config) is left untouched.
_USER_DATA_SUBDIRS = ("original", "processed", "tmp", "pdfa", "backups")

# JSON cache files written by watch-folder / ingest tasks.
_CACHE_FILES = (
    "watch_folder_processed.json",
    "ftp_ingest_processed.json",
    "sftp_ingest_processed.json",
    "dropbox_ingest_processed.json",
    "gdrive_ingest_processed.json",
    "onedrive_ingest_processed.json",
    "nextcloud_ingest_processed.json",
    "s3_ingest_processed.json",
    "webdav_ingest_processed.json",
    "processed_mails.json",
    "credential_failures.json",
)

# The folder name used for storing files prior to re-import.
REIMPORT_FOLDER_NAME = "reimport"


def _wipe_workdir_data(workdir: str) -> dict[str, int]:
    """Delete user data subdirectories and cache files inside *workdir*.

    Leaves the workdir directory itself intact so the application can
    continue to write into it.  Also leaves any files that do not belong
    to the known data subdirectories or caches.

    Returns:
        A dict with counts of deleted directories and files.
    """
    workdir_path = Path(workdir)
    deleted_dirs = 0
    deleted_files = 0

    # Remove data subdirectories
    for subdir in _USER_DATA_SUBDIRS:
        target = workdir_path / subdir
        if target.is_dir():
            shutil.rmtree(target)
            logger.info("Deleted data directory: %s", target)
            deleted_dirs += 1

    # Remove cache / state JSON files
    for cache_file in _CACHE_FILES:
        target = workdir_path / cache_file
        if target.is_file():
            target.unlink()
            logger.info("Deleted cache file: %s", target)
            deleted_files += 1

    # Also remove user_wf_*.json files (per-user watch folder caches)
    for f in workdir_path.glob("user_wf_*.json"):
        f.unlink()
        logger.info("Deleted user watch-folder cache: %s", f)
        deleted_files += 1

    # Remove loose files in workdir root that are user uploads (uuid-named
    # files like "a1b2c3d4-…pdf") but NOT application config files.
    for entry in workdir_path.iterdir():
        if entry.is_file() and entry.suffix.lower() in {
            ".pdf",
            ".png",
            ".jpg",
            ".jpeg",
            ".tiff",
            ".tif",
            ".docx",
            ".doc",
            ".xlsx",
            ".xls",
            ".pptx",
            ".heic",
            ".heif",
            ".webp",
            ".bmp",
            ".gif",
            ".txt",
            ".rtf",
            ".odt",
            ".ods",
            ".odp",
            ".csv",
            ".pages",
            ".numbers",
            ".keynote",
        }:
            entry.unlink()
            logger.info("Deleted loose workdir file: %s", entry)
            deleted_files += 1

    return {"deleted_dirs": deleted_dirs, "deleted_files": deleted_files}


def _wipe_database(db: Session) -> dict[str, int]:
    """Delete all user-generated rows from the database.

    Preserves schema (tables, migrations) and system-seeded rows that will
    be re-created on the next startup (subscription plans, default pipeline,
    scheduled jobs, compliance templates).

    Returns:
        A dict mapping table name → number of rows deleted.
    """
    from app.models import (
        AuditLog,
        BackupRecord,
        DocumentMetadata,
        FileProcessingStep,
        FileRecord,
        InAppNotification,
        ProcessingLog,
        SavedSearch,
        SettingsAuditLog,
        SharedLink,
        UserImapAccount,
        UserIntegration,
        UserNotificationPreference,
        UserNotificationTarget,
    )

    # Order matters: delete children before parents to respect FK constraints.
    tables_to_wipe: list[tuple[str, type]] = [
        ("file_processing_steps", FileProcessingStep),
        ("processing_logs", ProcessingLog),
        ("shared_links", SharedLink),
        ("in_app_notifications", InAppNotification),
        ("user_notification_preferences", UserNotificationPreference),
        ("user_notification_targets", UserNotificationTarget),
        ("user_imap_accounts", UserImapAccount),
        ("user_integrations", UserIntegration),
        ("saved_searches", SavedSearch),
        ("settings_audit_log", SettingsAuditLog),
        ("audit_logs", AuditLog),
        ("backup_records", BackupRecord),
        ("document_metadata", DocumentMetadata),
        ("files", FileRecord),
    ]

    result: dict[str, int] = {}
    for table_name, model in tables_to_wipe:
        try:
            count = db.query(model).delete()
            result[table_name] = count
            logger.info("Wiped %d rows from %s", count, table_name)
        except Exception:
            logger.exception("Failed to wipe table %s during system reset", table_name)
            db.rollback()
            raise

    db.commit()
    return result


def perform_full_reset(db: Session) -> dict:
    """Perform a complete system reset: wipe database rows + work-files.

    Args:
        db: An active SQLAlchemy session.

    Returns:
        Summary dict with ``database`` and ``filesystem`` sub-dicts.
    """
    logger.warning(">>> SYSTEM RESET: wiping all user data <<<")

    db_result = _wipe_database(db)
    fs_result = _wipe_workdir_data(settings.workdir)

    logger.warning(">>> SYSTEM RESET complete <<<")
    return {"database": db_result, "filesystem": fs_result}


def perform_reset_and_reimport(db: Session) -> dict:
    """Move original files to a reimport folder, wipe everything, then
    configure the reimport folder as a watch folder for re-ingestion.

    The watch-folder scanner (``scan_all_watch_folders``) will pick up
    the files on its next periodic run and process them exactly as if
    they had been freshly uploaded — respecting the same backoff
    strategy, size limits, and rate limits.

    Args:
        db: An active SQLAlchemy session.

    Returns:
        Summary dict with ``database``, ``filesystem``, and ``reimport`` sub-dicts.
    """
    workdir_path = Path(settings.workdir)
    reimport_dir = workdir_path / REIMPORT_FOLDER_NAME
    original_dir = workdir_path / "original"

    # 1. Collect original files
    files_moved = 0
    reimport_dir.mkdir(parents=True, exist_ok=True)

    if original_dir.is_dir():
        for entry in original_dir.iterdir():
            if entry.is_file():
                # Validate the resolved path stays within original_dir (path traversal guard)
                try:
                    entry.resolve().relative_to(original_dir.resolve())
                except ValueError:
                    logger.warning("Skipping file outside original dir: %s", entry)
                    continue
                dest = reimport_dir / entry.name
                # Avoid overwriting: append counter if name clash
                if dest.exists():
                    stem = dest.stem
                    suffix = dest.suffix
                    counter = 1
                    while dest.exists():
                        dest = reimport_dir / f"{stem}_{counter}{suffix}"
                        counter += 1
                shutil.copy2(str(entry), str(dest))
                files_moved += 1

    logger.info("Copied %d original files to reimport folder: %s", files_moved, reimport_dir)

    # 2. Perform the full reset (wipe DB + other workdir data)
    reset_result = perform_full_reset(db)

    # 3. Ensure the reimport folder survived the wipe (it's not in _USER_DATA_SUBDIRS)
    #    and set up watch folder config to point at it.
    _configure_reimport_watch_folder(str(reimport_dir))

    reset_result["reimport"] = {
        "files_moved": files_moved,
        "reimport_folder": str(reimport_dir),
    }
    logger.warning(">>> SYSTEM RESET with re-import configured — %d files staged <<<", files_moved)
    return reset_result


def _configure_reimport_watch_folder(reimport_path: str) -> None:
    """Append *reimport_path* to the application's watch-folder list.

    The watch-folder scanner uses ``settings.watch_folders`` (a
    comma-separated string).  We mutate the runtime setting so the
    next scan picks up the folder.  We also set
    ``watch_folder_delete_after_process = True`` so files are cleaned
    up after successful processing.
    """
    current = getattr(settings, "watch_folders", None) or ""
    folders = [f.strip() for f in current.split(",") if f.strip()]

    if reimport_path not in folders:
        folders.append(reimport_path)

    # Mutate runtime settings (not persisted to .env — ephemeral)
    object.__setattr__(settings, "watch_folders", ",".join(folders))
    object.__setattr__(settings, "watch_folder_delete_after_process", True)
    logger.info("Configured reimport watch folder: %s", reimport_path)


def perform_startup_reset() -> None:
    """Called during application startup when ``FACTORY_RESET_ON_STARTUP=True``.

    Wipes database and filesystem data so the instance starts completely
    fresh.  Uses its own DB session so it runs before the normal lifespan
    seeding logic.
    """
    from app.database import SessionLocal

    logger.warning("FACTORY_RESET_ON_STARTUP is enabled — wiping all data")
    db = SessionLocal()
    try:
        perform_full_reset(db)
    except Exception:
        logger.exception("Factory reset on startup failed")
        db.rollback()
    finally:
        db.close()
