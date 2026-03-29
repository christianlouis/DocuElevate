# Mock settings before importing
import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost"
os.environ["OPENAI_API_KEY"] = "mock"
os.environ["WORKDIR"] = "/tmp"
os.environ["AZURE_AI_KEY"] = "mock"
os.environ["AZURE_REGION"] = "mock"
os.environ["AZURE_ENDPOINT"] = "mock"
os.environ["GOTENBERG_URL"] = "mock"
os.environ["AUTH_ENABLED"] = "False"

from fastapi import HTTPException

from app.api.url_upload import check_redirect


@pytest.mark.asyncio
async def test_check_redirect_no_redirect():
    response = MagicMock(spec=httpx.Response)
    response.is_redirect = False
    # Should do nothing
    await check_redirect(response)


@pytest.mark.asyncio
async def test_check_redirect_safe_url():
    response = MagicMock(spec=httpx.Response)
    response.is_redirect = True
    response.headers = httpx.Headers({"Location": "https://example.com/file.pdf"})
    response.url = httpx.URL("https://example.com/")

    with patch("app.api.url_upload.validate_url_safety") as mock_validate:
        await check_redirect(response)
        mock_validate.assert_called_once_with("https://example.com/file.pdf")


@pytest.mark.asyncio
async def test_check_redirect_unsafe_url():
    response = MagicMock(spec=httpx.Response)
    response.is_redirect = True
    response.headers = httpx.Headers({"Location": "http://169.254.169.254/metadata"})
    response.url = httpx.URL("http://example.com/")

    with pytest.raises(HTTPException):
        await check_redirect(response)
