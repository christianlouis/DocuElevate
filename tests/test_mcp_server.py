import asyncio
import json
import os
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock

import pytest
import requests
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.mcp_server import (
    DocuElevateClient,
    _normalize_sources,
    _validate_base_url,
    get_document,
    mcp,
    search_documents,
)


def response(payload, status=200, redirect=False):
    item = Mock()
    item.status_code = status
    item.ok = status < 400
    item.is_redirect = redirect
    item.json.return_value = payload
    return item


def test_search_forwards_contract_and_normalizes_citation():
    session = Mock()
    session.request.return_value = response({"results": [{"source_url": "/files/7", "text": "invoice"}]})
    client = DocuElevateClient("https://docs.example", "de_secret", session)
    result = _normalize_sources(client.search("invoice", 4, 0.3), client.base_url)
    call = session.request.call_args
    assert call.kwargs["json"] == {"query": "invoice", "limit": 4, "score_threshold": 0.3}
    assert result["results"][0]["source_url"] == "https://docs.example/files/7"


@pytest.mark.parametrize("status", [401, 403, 404, 429, 502])
def test_upstream_errors_are_sanitized(status):
    session = Mock()
    session.request.return_value = response({"secret": "must not leak"}, status)
    with pytest.raises(RuntimeError) as error:
        DocuElevateClient("https://docs.example", "de_secret", session).document(1)
    assert "secret" not in str(error.value)


def test_redirects_are_rejected_without_following_them():
    session = Mock()
    session.request.return_value = response({"location": "https://attacker.example"}, 302, redirect=True)
    with pytest.raises(RuntimeError, match="unsafe redirect"):
        DocuElevateClient("https://docs.example", "de_secret", session).document(1)
    assert session.request.call_args.kwargs["allow_redirects"] is False


def test_transport_and_json_failures_do_not_expose_upstream_data(caplog):
    token = "transport-token-marker"
    session = Mock()
    session.request.side_effect = requests.RequestException(f"body={token}")
    with pytest.raises(RuntimeError) as error:
        DocuElevateClient("https://docs.example", token, session).document(1)
    assert token not in "".join(traceback.format_exception(error.value))
    assert token not in caplog.text

    malformed = response(None)
    malformed.json.side_effect = ValueError("body=malformed-json-marker")
    session.request.side_effect = None
    session.request.return_value = malformed
    with pytest.raises(RuntimeError) as error:
        DocuElevateClient("https://docs.example", token, session).document(1)
    assert "malformed-json-marker" not in "".join(traceback.format_exception(error.value))
    assert "malformed-json-marker" not in caplog.text


def test_url_validation_rejects_unsafe_urls():
    with pytest.raises(ValueError):
        _validate_base_url("http://public.example")
    with pytest.raises(ValueError):
        _validate_base_url("https://user:pass@docs.example")
    with pytest.raises(ValueError):
        _validate_base_url("https://docs.example/api?token=leak")
    assert _validate_base_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"


@pytest.mark.parametrize("args", [("", 8, 0.25), ("x", 0, 0.25), ("x", 51, 0.25), ("x", 1, 1.1)])
def test_search_validates_inputs(monkeypatch, args):
    monkeypatch.setenv("DOCUELEVATE_API_TOKEN", "de_test")
    with pytest.raises(ValueError):
        search_documents(*args)


def test_get_document_validates_id(monkeypatch):
    monkeypatch.setenv("DOCUELEVATE_API_TOKEN", "de_test")
    with pytest.raises(ValueError):
        get_document(0)


def test_mcp_exposes_read_only_tools_and_calls_search(monkeypatch):
    class FakeClient:
        base_url = "https://docs.example"

        def search(self, query, limit, score_threshold):
            assert (query, limit, score_threshold) == ("invoice", 8, 0.25)
            return {"count": 1, "results": [{"source_url": "/files/7", "text": "invoice"}]}

    monkeypatch.setattr("app.mcp_server._client", FakeClient)

    async def invoke():
        tools = await mcp.list_tools()
        assert {tool.name for tool in tools} == {"search_documents", "get_document"}
        assert all(tool.annotations.read_only_hint for tool in tools)
        return await mcp.call_tool("search_documents", {"query": "invoice"})

    result = asyncio.run(invoke())
    assert result.is_error is False
    assert result.structured_content["results"][0]["source_url"] == "https://docs.example/files/7"


def test_stdio_client_initializes_lists_tools_and_redacts_upstream_error(caplog):
    token = "de-transport-secret"
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            paths.append(self.path)
            assert self.headers["Authorization"] == f"Bearer {token}"
            length = int(self.headers["Content-Length"])
            request = json.loads(self.rfile.read(length))
            assert request["query"] == "invoice"
            payload = {"count": 1, "results": [{"text": "invoice", "source_url": "/files/7"}]}
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            paths.append(self.path)
            if self.path == "/api/knowledge/documents/7":
                body = json.dumps(
                    {
                        "document_id": 7,
                        "title": "Invoice",
                        "text": "authoritative OCR",
                        "source_url": "/files/7",
                    }
                ).encode()
                status = 200
            else:
                body = json.dumps({"detail": f"token={token}"}).encode()
                status = 401
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        env = os.environ.copy()
        env.update(
            DOCUELEVATE_URL=f"http://127.0.0.1:{server.server_port}",
            DOCUELEVATE_API_TOKEN=token,
        )
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
            env=env,
        )

        async def invoke():
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    assert {tool.name for tool in tools.tools} == {"search_documents", "get_document"}
                    assert all(tool.annotations.read_only_hint for tool in tools.tools)
                    search = await client.call_tool("search_documents", {"query": "invoice"})
                    document = await client.call_tool("get_document", {"document_id": 7})
                    denied = await client.call_tool("get_document", {"document_id": 8})
                    return search, document, denied

        search, document, denied = asyncio.run(invoke())
        assert not search.is_error
        assert search.structured_content["results"][0]["source_url"].endswith("/files/7")
        assert not document.is_error
        assert document.structured_content["title"] == "Invoice"
        assert document.structured_content["source_url"].endswith("/files/7")
        assert denied.is_error
        assert token not in str(denied)
        assert token not in caplog.text
        assert paths == [
            "/api/knowledge/search",
            "/api/knowledge/documents/7",
            "/api/knowledge/documents/8",
        ]
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
