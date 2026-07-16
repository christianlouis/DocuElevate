"""Local entry point for planning and applying declarative setup manifests."""

from __future__ import annotations

import argparse
import json
import sys

from app.database import SessionLocal, init_db
from app.utils.setup_manifest import (
    SetupManifestError,
    apply_setup_manifest,
    load_setup_manifest,
    plan_setup_manifest,
    resolve_setup_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan or apply an idempotent DocuElevate setup manifest")
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("manifest", help="Path to a DocuElevateSetup JSON manifest")
    args = parser.parse_args()

    try:
        init_db()
        resolved = resolve_setup_manifest(load_setup_manifest(args.manifest))
        db = SessionLocal()
        try:
            result = plan_setup_manifest(db, resolved) if args.mode == "plan" else apply_setup_manifest(db, resolved)
        finally:
            db.close()
        print(json.dumps(result, indent=2, sort_keys=True))
        if not result.get("success"):
            raise SystemExit(2)
    except SetupManifestError as exc:
        print(json.dumps({"success": False, "error": str(exc)}, indent=2), file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
