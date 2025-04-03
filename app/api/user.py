"""
User-related API endpoints
"""
from fastapi import APIRouter, Request, HTTPException
from hashlib import md5
import logging

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

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
