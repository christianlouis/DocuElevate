"""
User-related API endpoints
"""

import logging
from hashlib import md5

from fastapi import APIRouter, HTTPException, Request

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()


async def whoami_handler(request: Request):
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
    # MD5 is used here for Gravatar's URL generation (not for security), so usedforsecurity=False
    email_hash = md5(email.strip().lower().encode(), usedforsecurity=False).hexdigest()
    gravatar_url = f"https://www.gravatar.com/avatar/{email_hash}?d=identicon"

    # Add the gravatar URL to the user object instead of creating a new response
    user_response = user.copy()  # Create a copy to avoid modifying the session
    user_response["picture"] = gravatar_url

    return user_response


# Register the same handler under two different paths
@router.get("/whoami", responses={401: {"description": "Not logged in"}, 400: {"description": "User has no email"}})
async def whoami(request: Request):
    return await whoami_handler(request)


@router.get(
    "/auth/whoami", responses={401: {"description": "Not logged in"}, 400: {"description": "User has no email"}}
)
async def auth_whoami(request: Request):
    return await whoami_handler(request)
