import asyncio
import time
import httpx
from unittest.mock import patch, MagicMock, AsyncMock
from app.api.onedrive import test_onedrive_token
from app.config import settings

settings.onedrive_refresh_token = "dummy"
settings.onedrive_client_id = "dummy"
settings.onedrive_client_secret = "dummy"

class DummyRequest:
    def __init__(self):
        self.session = {"user": "dummy"}

async def run_benchmark(func_name, mock_post, mock_get):
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {
        "access_token": "dummy_access",
        "expires_in": 3600
    }
    mock_post.return_value = mock_post_resp

    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = {
        "displayName": "Test User",
        "userPrincipalName": "test@example.com"
    }
    mock_get.return_value = mock_get_resp

    start_time = time.time()
    for _ in range(100):
        await test_onedrive_token(DummyRequest())
    end_time = time.time()
    print(f"{func_name} took {end_time - start_time:.4f} seconds")

async def run_benchmark_async(func_name, mock_post, mock_get):
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json = MagicMock(return_value={
        "access_token": "dummy_access",
        "expires_in": 3600
    })
    mock_post.return_value = mock_post_resp

    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json = MagicMock(return_value={
        "displayName": "Test User",
        "userPrincipalName": "test@example.com"
    })
    mock_get.return_value = mock_get_resp

    start_time = time.time()
    for _ in range(100):
        await test_onedrive_token(DummyRequest())
    end_time = time.time()
    print(f"{func_name} took {end_time - start_time:.4f} seconds")


@patch('app.api.onedrive.requests.get')
@patch('app.api.onedrive.requests.post')
def benchmark_sync(mock_post, mock_get):
    asyncio.run(run_benchmark("Sync requests (baseline)", mock_post, mock_get))

if __name__ == "__main__":
    benchmark_sync()
