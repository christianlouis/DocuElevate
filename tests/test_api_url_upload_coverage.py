import pytest
from unittest.mock import patch, MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_validate_redirect_hook_direct():
    import httpx
    from fastapi import HTTPException

    # We will test the inline validate_redirect function by calling process_url with a mocked httpx.AsyncClient
    # that extracts the hook and calls it directly.
    from app.api.url_upload import process_url

    # We can capture the validate_redirect function by mocking httpx.AsyncClient
    hook_funcs = []

    class MockAsyncClient:
        def __init__(self, **kwargs):
            if "event_hooks" in kwargs and "response" in kwargs["event_hooks"]:
                hook_funcs.extend(kwargs["event_hooks"]["response"])

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def stream(self, method, url):
            class MockStreamContext:
                async def __aenter__(self):
                    response = MagicMock()
                    response.headers = {}
                    response.aiter_bytes = AsyncMock(return_value=[])
                    return response
                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass
            return MockStreamContext()

    with patch("app.api.url_upload.httpx.AsyncClient", new=MockAsyncClient):
        from app.api.url_upload import URLUploadRequest
        from fastapi import Request
        request = MagicMock(spec=Request)
        url_request = URLUploadRequest(url="http://example.com")

        try:
            await process_url(request, url_request)
        except Exception:
            pass # we just want to get the hooks out

    assert len(hook_funcs) == 2
    validate_redirect = hook_funcs[0] # it was the first one

    # Now we can test the hook
    with patch("app.api.url_upload.validate_url_safety", side_effect=HTTPException(status_code=400, detail="bad")):
        resp = MagicMock(spec=httpx.Response)
        resp.is_redirect = True
        resp.headers = {"Location": "http://bad.com"}
        resp.url = httpx.URL("http://example.com")
        resp.request = httpx.Request("GET", "http://example.com")

        with pytest.raises(httpx.RequestError) as exc:
            await validate_redirect(resp)
        assert "Unsafe redirect target: bad" in str(exc.value)

    with patch("app.api.url_upload.validate_url_safety", return_value=None):
        resp = MagicMock(spec=httpx.Response)
        resp.is_redirect = True
        resp.headers = {"Location": "http://good.com"}
        resp.url = httpx.URL("http://example.com")
        resp.request = httpx.Request("GET", "http://example.com")

        await validate_redirect(resp) # should not raise

        # Test no location
        resp.headers = {}
        await validate_redirect(resp) # should not raise

        # Test not redirect
        resp.is_redirect = False
        await validate_redirect(resp) # should not raise
