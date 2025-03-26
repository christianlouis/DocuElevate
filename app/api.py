# app/api.py
from fastapi import APIRouter, Request, HTTPException, status, Depends
from hashlib import md5
from sqlalchemy.orm import Session
from typing import List

from app.auth import require_login
from app.database import SessionLocal
from app.models import FileRecord

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/whoami")
async def whoami(request: Request):
    """
    Returns user info if logged in, else 401.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    email = user.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="User has no email in session")

    # Generate Gravatar URL from email
    email_hash = md5(email.strip().lower().encode()).hexdigest()
    gravatar_url = f"https://www.gravatar.com/avatar/{email_hash}?d=identicon"

    return {
        "email": email,
        "picture": gravatar_url
    }

@router.get("/files")
@require_login
def list_files_api(request: Request, db: Session = Depends(get_db)):
    """
    Returns a JSON list of all FileRecord entries.
    Protected by `@require_login`, so only logged-in sessions can access.
    
    Example response:
    [
      {
        "id": 123,
        "filehash": "abc123...",
        "original_filename": "example.pdf",
        "local_filename": "/workdir/tmp/<uuid>.pdf",
        "file_size": 1048576,
        "mime_type": "application/pdf",
        "created_at": "2025-05-01T12:34:56.789000"
      },
      ...
    ]
    """
    files = db.query(FileRecord).order_by(FileRecord.created_at.desc()).all()
    # Return a simple list of dicts
    result = []
    for f in files:
        result.append({
            "id": f.id,
            "filehash": f.filehash,
            "original_filename": f.original_filename,
            "local_filename": f.local_filename,
            "file_size": f.file_size,
            "mime_type": f.mime_type,
            "created_at": f.created_at.isoformat() if f.created_at else None
        })
    return result
