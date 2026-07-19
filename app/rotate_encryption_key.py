"""Operator command for rotating database encryption after SESSION_SECRET changes."""

from __future__ import annotations

import argparse

from app.config import settings
from app.database import SessionLocal
from app.utils.encryption import EncryptionRotationError
from app.utils.encryption_rotation import rotate_database_encryption


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-encrypt database credentials with the current SESSION_SECRET without printing values."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Do not modify rows; fail unless every encrypted value uses the current key.",
    )
    args = parser.parse_args()

    if not args.verify_only and not settings.session_secret_previous:
        parser.error("SESSION_SECRET_PREVIOUS is required for a key rotation")

    with SessionLocal() as db:
        try:
            report = rotate_database_encryption(db, verify_only=args.verify_only)
        except EncryptionRotationError as exc:
            print(f"Encryption rotation failed: {exc}")
            return 1

    print(f"Encryption rotation counts: scanned={report.scanned} rotated={report.rotated} invalid={report.invalid}")
    return 1 if report.invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())
