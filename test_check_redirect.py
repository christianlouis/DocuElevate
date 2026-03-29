import asyncio
from unittest.mock import MagicMock
import httpx
from fastapi import HTTPException

# Mock settings before importing
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost"
os.environ["OPENAI_API_KEY"] = "mock"
os.environ["WORKDIR"] = "/tmp"
os.environ["AZURE_AI_KEY"] = "mock"
os.environ["AZURE_REGION"] = "mock"
os.environ["AZURE_ENDPOINT"] = "mock"
os.environ["GOTENBERG_URL"] = "mock"
os.environ["AUTH_ENABLED"] = "False"

from app.api.url_upload import check_redirect

async def test_unsafe():
    response = MagicMock(spec=httpx.Response)
    response.is_redirect = True
    response.headers = httpx.Headers({"Location": "http://169.254.169.254/metadata"})
    response.url = httpx.URL("http://example.com/")

    try:
        await check_redirect(response)
    except HTTPException as e:
        print("Caught exception:", e.detail)
    except Exception as e:
        print("Caught OTHER exception:", repr(e))

asyncio.run(test_unsafe())
