#!/usr/bin/env python3

"""
Request Size Limit Middleware for DocuElevate.

This middleware enforces configurable size limits on incoming HTTP request bodies
to prevent memory exhaustion and Denial-of-Service (DoS) attacks.

Two independent limits are enforced:
- ``MAX_REQUEST_BODY_SIZE``: applied to all non-multipart requests (JSON, form data, etc.).
  Default: 1 MB.  Configurable via the ``MAX_REQUEST_BODY_SIZE`` environment variable.
- ``MAX_UPLOAD_SIZE``: applied to multipart/form-data (file upload) requests.
  Default: 1 GB.  Configurable via the ``MAX_UPLOAD_SIZE`` environment variable.

When a request exceeds the applicable limit the middleware immediately returns
``HTTP 413 Request Entity Too Large`` without reading the full body, which keeps
memory usage bounded.

See SECURITY_AUDIT.md – Code Security section for background.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that rejects requests whose body exceeds a configured size limit.

    File-upload requests (``Content-Type: multipart/form-data``) are checked
    against ``config.max_upload_size``; all other requests are checked against
    ``config.max_request_body_size``.

    The check is performed on the ``Content-Length`` header before the body is
    read, so oversized requests are rejected without buffering the payload into
    memory.  If the client omits the ``Content-Length`` header the request is
    passed through to the normal handler (where endpoint-level checks still
    apply for file uploads).
    """

    def __init__(self, app, config):
        """
        Initialize the middleware.

        Args:
            app: The ASGI application to wrap.
            config: Application settings object with ``max_request_body_size``
                    and ``max_upload_size`` attributes.
        """
        super().__init__(app)
        self.max_body_size = config.max_request_body_size
        self.max_upload_size = config.max_upload_size
        logger.info(
            f"Request size limit middleware enabled – "
            f"body limit: {self.max_body_size} bytes, "
            f"upload limit: {self.max_upload_size} bytes"
        )

    async def dispatch(self, request: Request, call_next):
        """
        Check the ``Content-Length`` header and reject oversized requests early.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            HTTP 413 response if the request is too large, otherwise the
            downstream response.
        """
        content_length_header = request.headers.get("content-length")
        if content_length_header is not None:
            try:
                content_length = int(content_length_header)
            except ValueError:
                # Malformed header – let downstream handle it
                return await call_next(request)

            content_type = request.headers.get("content-type", "")
            is_multipart = "multipart/form-data" in content_type

            if is_multipart:
                limit = self.max_upload_size
                limit_description = "file upload"
                config_var = "MAX_UPLOAD_SIZE"
            else:
                limit = self.max_body_size
                limit_description = "request body"
                config_var = "MAX_REQUEST_BODY_SIZE"

            if content_length > limit:
                logger.warning(
                    f"Rejected oversized {limit_description}: "
                    f"{content_length} bytes > {limit} bytes limit "
                    f"(configure with {config_var})"
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"Request body too large: {content_length} bytes "
                            f"(maximum allowed: {limit} bytes). "
                            f"Adjust the {config_var} environment variable to change this limit. "
                            f"See SECURITY_AUDIT.md for details."
                        )
                    },
                )

        return await call_next(request)
