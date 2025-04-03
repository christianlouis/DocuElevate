"""
File management views for displaying and managing files.
"""
from fastapi import Request, Depends
from sqlalchemy.orm import Session

from app.views.base import APIRouter, templates, require_login, get_db, logger

router = APIRouter()

@router.get("/files")
@require_login
def files_page(request: Request, db: Session = Depends(get_db)):
    """
    Return the 'files.html' template with files from the database
    """
    try:
        # Import the model here to avoid circular imports
        from app.models import FileRecord
        
        # Fetch all files from the database
        files = db.query(FileRecord).order_by(FileRecord.created_at.desc()).all()
        
        # Debug output
        logger.info(f"Retrieved {len(files)} files from database")
        
        return templates.TemplateResponse("files.html", {
            "request": request,
            "files": files
        })
    except Exception as e:
        # Log any errors
        logger.error(f"Error retrieving files: {str(e)}")
        # Return error message to template
        return templates.TemplateResponse("files.html", {
            "request": request,
            "files": [],
            "error": str(e)
        })
