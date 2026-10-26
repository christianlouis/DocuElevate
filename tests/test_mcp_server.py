from unittest.mock import Mock
import asyncio

import pytest

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

    monkeypatch.setattr("app.mcp_server._client", lambda: FakeClient())

    async def invoke():
        tools = await mcp.list_tools()
        assert {tool.name for tool in tools} == {"search_documents", "get_document"}
        assert all(tool.annotations.read_only_hint for tool in tools)
        return await mcp.call_tool("search_documents", {"query": "invoice"})

    result = asyncio.run(invoke())
    assert result.is_error is False
    assert result.structured_content["results"][0]["source_url"] == "https://docs.example/files/7"
