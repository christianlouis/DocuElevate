import asyncio
import time
from unittest.mock import Mock, patch

from app.api.url_upload import process_url, URLUploadRequest
from app.config import settings

async def main():
    # Mock request and URLUploadRequest
    request = Mock()
    url_request = URLUploadRequest(url="https://example.com/file.pdf")

    # Generate a large chunk
    large_chunk = b"A" * 8192
    num_chunks = 10000 # 8192 * 10000 = ~80MB

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "application/pdf"}
    mock_response.iter_content = Mock(return_value=[large_chunk] * num_chunks)

    # For async client later
    class AsyncMockResponse:
        def __init__(self):
            self.status_code = 200
            self.headers = {"Content-Type": "application/pdf"}
        def raise_for_status(self):
            pass
        async def aiter_bytes(self, chunk_size):
            for _ in range(num_chunks):
                yield large_chunk

    async_mock_response = AsyncMockResponse()

    # We will mock requests.get for synchronous, httpx.AsyncClient.get for asynchronous

    # Test sync
    start_time = time.time()
    with patch("app.api.url_upload.requests.get", return_value=mock_response), \
         patch("app.api.url_upload.process_document"):
        try:
            await process_url(request=request, url_request=url_request)
        except Exception as e:
            print(f"Error: {e}")
    end_time = time.time()
    print(f"Original execution time (sync writing): {end_time - start_time:.4f} seconds")

if __name__ == "__main__":
    asyncio.run(main())
