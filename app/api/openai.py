"""
OpenAI API endpoints
"""
from fastapi import APIRouter, Request, HTTPException, status
import logging
import os
import requests

from app.auth import require_login
from app.config import settings

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/openai/test")
@require_login
async def test_openai_connection(request: Request):
    """
    Test if the configured OpenAI API key is valid.
    """
    try:
        import openai
        
        logger.info("Testing OpenAI API key validity")
        
        # Check if API key is configured
        if not settings.openai_api_key:
            logger.warning("No OpenAI API key configured")
            return {
                "status": "error",
                "message": "No OpenAI API key is configured"
            }
        
        # Configure the client
        client = openai.OpenAI(api_key=settings.openai_api_key)
        
        # Try to make a simple request to validate the key
        try:
            # Use a models list endpoint as a simple validation
            models = client.models.list()
            
            # If we got here, the key is valid
            logger.info("OpenAI API key is valid")
            return {
                "status": "success",
                "message": "OpenAI API key is valid",
                "models_available": len(models.data) if hasattr(models, "data") else "Unknown"
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"OpenAI API key test failed: {error_msg}")
            
            # Determine if this is an authentication error
            is_auth_error = "auth" in error_msg.lower() or "api key" in error_msg.lower()
            
            return {
                "status": "error",
                "message": f"API key validation failed: {error_msg}",
                "is_auth_error": is_auth_error
            }
    
    except ImportError:
        logger.exception("OpenAI package not installed")
        return {
            "status": "error",
            "message": "OpenAI package not installed"
        }
    except Exception as e:
        logger.exception("Unexpected error testing OpenAI connection")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }
