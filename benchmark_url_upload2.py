import asyncio
import time
import os
import shutil
import tempfile
from unittest.mock import Mock, patch
from fastapi import HTTPException

from app.api.url_upload import process_url, URLUploadRequest
from app.config import settings

async def main():
    # Setup test dir
    test_dir = tempfile.mkdtemp()
    settings.workdir = test_dir

    # Mock request and URLUploadRequest
    request = Mock()
    url_request = URLUploadRequest(url="https://example.com/file.pdf")

    # Generate a large chunk
    chunk_size = 8192
    num_chunks = 20000 # 20000 * 8192 = ~160MB
    large_chunk = b"A" * chunk_size

    class SyncMockResponse:
        def __init__(self):
            self.status_code = 200
            self.headers = {"Content-Type": "application/pdf"}
        def raise_for_status(self):
            pass
        def iter_content(self, chunk_size):
            for _ in range(num_chunks):
                # sleep slightly to simulate network latency, otherwise OS file cache obscures the difference
                time.sleep(0.0001)
                yield large_chunk

    sync_mock_response = SyncMockResponse()

    class AsyncMockResponse:
        def __init__(self):
            self.status_code = 200
            self.headers = {"Content-Type": "application/pdf"}
            self.is_success = True
            self.status_code = 200
        def raise_for_status(self):
            pass
        async def aiter_bytes(self, chunk_size=8192):
            for _ in range(num_chunks):
                await asyncio.sleep(0.0001)
                yield large_chunk

    class AsyncMockContext:
        async def __aenter__(self):
            return AsyncMockResponse()
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    async_mock_response = AsyncMockResponse()

    # Test sync
    start_time = time.time()
    with patch("app.api.url_upload.requests.get", return_value=sync_mock_response), \
         patch("app.api.url_upload.process_document"):
        try:
            await process_url(request=request, url_request=url_request)
        except Exception as e:
            print(f"Error (sync): {e}")
    end_time = time.time()
    print(f"Original execution time (sync writing): {end_time - start_time:.4f} seconds")

    shutil.rmtree(test_dir)

if __name__ == "__main__":
    asyncio.run(main())
