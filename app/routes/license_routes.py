from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

router = APIRouter()


@router.get("/licenses/lgpl.txt", response_class=PlainTextResponse)
async def get_lgpl_license():
    """
    Serve the LGPL license text file
    """
    license_path = Path("frontend/static/licenses/lgpl.txt")
    if not license_path.exists():
        raise HTTPException(status_code=404, detail="License file not found")

    with open(license_path, "r") as f:
        return f.read()
