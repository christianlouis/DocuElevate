from fastapi import APIRouter, Request, HTTPException, status
from hashlib import md5

router = APIRouter()

@router.get("/whoami")
async def whoami(request: Request):
    """
    Returns user info if logged in, else 401.
    Example response:
    {
      "email": "someone@example.com",
      "picture": "https://www.gravatar.com/avatar/..."
    }
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    email = user.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="User has no email in session")

    # Generate Gravatar URL from email
    # For more options, see: https://en.gravatar.com/site/implement/images/
    email_hash = md5(email.strip().lower().encode()).hexdigest()
    gravatar_url = f"https://www.gravatar.com/avatar/{email_hash}?d=identicon"

    return {
        "email": email,
        "picture": gravatar_url
    }