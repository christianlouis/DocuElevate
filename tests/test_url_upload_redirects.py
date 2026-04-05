from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException

from app.api.url_upload import check_redirect


@pytest.mark.asyncio
async def test_check_redirect_allows_safe_url():
    response = MagicMock(spec=httpx.Response)
    response.is_redirect = True
    response.headers = {"Location": "/safe/path"}
    response.url = httpx.URL("https://example.com/start")

    # Should not raise any exception
    await check_redirect(response)


@pytest.mark.asyncio
async def test_check_redirect_blocks_unsafe_url():
    response = MagicMock(spec=httpx.Response)
    response.is_redirect = True
    response.headers = {"Location": "http://127.0.0.1/admin"}
    response.url = httpx.URL("https://example.com/start")

    with pytest.raises(HTTPException) as exc_info:
        await check_redirect(response)

    assert exc_info.value.status_code == 400
    assert "private" in exc_info.value.detail.lower()
