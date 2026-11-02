"""Hermetic tests for the per-user Notion destination."""

import json
from unittest.mock import Mock, patch

import pytest

from app.tasks.upload_to_notion import (
    NotionPageCreationUncertain,
    test_notion_connection,
    upload_to_notion,
    upload_to_notion_global,
)

DS = "00000000-0000-4000-8000-000000000001"
DATABASE = "00000000-0000-4000-8000-000000000002"
UPLOAD = "00000000-0000-4000-8000-000000000003"
PAGE = "00000000-0000-4000-8000-000000000004"


@pytest.fixture(autouse=True)
def clear_workspace_cache():
    from app.tasks.upload_to_notion import _WORKSPACE_LIMIT_CACHE

    _WORKSPACE_LIMIT_CACHE.clear()


def _workspace(limit=5 * 1024 * 1024 * 1024):
    return _response(200, {"bot": {"workspace_limits": {"max_file_upload_size_in_bytes": limit}}})


def _response(status: int, body: dict):
    response = Mock()
    response.status_code = status
    response.ok = 200 <= status < 300
    response.json.return_value = body
    return response


def test_connection_discovers_title_property():
    response = _response(200, {"properties": {"Subject": {"type": "title"}}})
    with patch("app.tasks.upload_to_notion.requests.request", return_value=response) as request:
        result = test_notion_connection({"data_source_id": DS}, {"api_token": "secret"})
    assert result["success"] is True
    assert "Subject" in result["message"]
    assert request.call_args.kwargs["allow_redirects"] is False
    assert request.call_args.kwargs["headers"]["Notion-Version"] == "2026-03-11"


def test_upload_maps_metadata_and_private_link(tmp_path):
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"pdf")
    (tmp_path / "invoice.json").write_text(
        json.dumps({"title": "March invoice", "summary": "Paid", "tags": ["finance"], "date": "2026-03-01"}),
        encoding="utf-8",
    )
    schema = _response(200, {"properties": {"Name": {"type": "title"}}})
    created = _response(200, {"id": PAGE, "url": "https://notion.so/page-1"})
    with patch("app.tasks.upload_to_notion.requests.request", side_effect=[schema, created]) as request:
        result = upload_to_notion(
            str(pdf),
            {"data_source_id": DS, "document_url_base": "https://docs.example"},
            {"api_token": "secret"},
            "task-1",
            file_id=9,
        )
    payload = request.call_args_list[1].kwargs["json"]
    assert payload["parent"] == {"data_source_id": DS}
    assert payload["properties"]["Name"]["title"][0]["text"]["content"] == "March invoice"
    text = " ".join(
        rich_text["text"]["content"] for block in payload["children"] for rich_text in block["paragraph"]["rich_text"]
    )
    assert "Paid" in text and "finance" in text and "Document date: 2026-03-01" in text
    document_link = payload["children"][-1]["paragraph"]["rich_text"][1]["text"]["link"]
    assert document_link == {"url": "https://docs.example/files/9"}
    assert result["notion_page_id"] == PAGE


def test_upload_does_not_log_or_send_token_on_http_error(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"pdf")
    schema = _response(403, {})
    with patch("app.tasks.upload_to_notion.requests.request", return_value=schema) as request:
        try:
            upload_to_notion(str(pdf), {"data_source_id": DS}, {"api_token": "secret-token"}, "task-1")
        except RuntimeError as exc:
            assert "secret-token" not in str(exc)
    assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer secret-token"


def test_connection_hides_request_and_json_errors():
    from requests import RequestException

    with patch("app.tasks.upload_to_notion.requests.request", side_effect=RequestException("secret-token")):
        result = test_notion_connection({"data_source_id": DS}, {"api_token": "secret-token"})
    assert result == {"success": False, "message": "Notion connection could not be verified"}


def test_connection_rejects_redirect_and_malformed_json():
    redirect = _response(302, {})
    with patch("app.tasks.upload_to_notion.requests.request", return_value=redirect):
        result = test_notion_connection({"data_source_id": DS}, {"api_token": "secret"})
    assert not result["success"]
    malformed = _response(200, {})
    malformed.json.side_effect = ValueError
    with patch("app.tasks.upload_to_notion.requests.request", return_value=malformed):
        result = test_notion_connection({"data_source_id": DS}, {"api_token": "secret"})
    assert not result["success"]


def test_connection_resolves_a_single_database_data_source():
    database = _response(200, {"data_sources": [{"id": DS}]})
    schema = _response(200, {"properties": {"Name": {"type": "title"}}})
    with patch("app.tasks.upload_to_notion.requests.request", side_effect=[database, schema]) as request:
        result = test_notion_connection({"database_id": DATABASE}, {"api_token": "secret"})
    assert result["success"] is True
    assert f"/v1/databases/{DATABASE}" in request.call_args_list[0].args[1]
    assert f"/v1/data_sources/{DS}" in request.call_args_list[1].args[1]


def test_connection_rejects_ambiguous_parent_choice():
    result = test_notion_connection({"data_source_id": DS, "database_id": DATABASE}, {"api_token": "secret"})
    assert result == {"success": False, "message": "Notion connection could not be verified"}


def test_pdf_single_part_upload_is_marked_uploaded_and_attached(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"pdf")
    responses = [
        _workspace(),
        _response(201, {"id": UPLOAD}),
        _response(200, {"id": UPLOAD, "status": "uploaded"}),
        _response(200, {"properties": {"Name": {"type": "title"}}}),
        _response(200, {"id": PAGE, "url": "https://notion.so/page-1"}),
    ]
    with patch("app.tasks.upload_to_notion.requests.request", side_effect=responses) as request:
        upload_to_notion(str(pdf), {"data_source_id": DS, "attach_pdf": True}, {"api_token": "secret"}, "task")
    send = request.call_args_list[2]
    assert "files" in send.kwargs and "Content-Type" not in send.kwargs["headers"]
    page = request.call_args_list[-1].kwargs["json"]
    assert page["children"][-1]["file"]["file_upload"]["id"] == UPLOAD
    assert all("/complete" not in call.args[1] for call in request.call_args_list)


def test_pdf_upload_requires_uploaded_status(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"pdf")
    with patch(
        "app.tasks.upload_to_notion.requests.request",
        side_effect=[_workspace(), _response(201, {"id": UPLOAD}), _response(200, {"id": UPLOAD, "status": "pending"})],
    ):
        with pytest.raises(RuntimeError, match="marked uploaded"):
            upload_to_notion(str(pdf), {"data_source_id": DS, "attach_pdf": True}, {"api_token": "secret"}, "task")


@pytest.mark.parametrize(
    "page_response",
    [
        _response(500, {}),
        _response(200, {}),
    ],
)
def test_page_creation_ambiguous_responses_are_not_safe_to_retry(tmp_path, page_response):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"pdf")
    schema = _response(200, {"properties": {"Name": {"type": "title"}}})
    with patch("app.tasks.upload_to_notion.requests.request", side_effect=[schema, page_response]):
        with pytest.raises(NotionPageCreationUncertain, match="inspect Notion"):
            upload_to_notion(str(pdf), {"data_source_id": DS}, {"api_token": "secret"}, "task")


def test_page_creation_transport_error_is_not_safe_to_retry(tmp_path):
    from requests import RequestException

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"pdf")
    schema = _response(200, {"properties": {"Name": {"type": "title"}}})
    with patch("app.tasks.upload_to_notion.requests.request", side_effect=[schema, RequestException("timeout")]):
        with pytest.raises(NotionPageCreationUncertain, match="inspect Notion"):
            upload_to_notion(str(pdf), {"data_source_id": DS}, {"api_token": "secret"}, "task")


def test_oversized_pdf_fails_before_page_create(tmp_path):
    pdf = tmp_path / "large.pdf"
    with open(pdf, "wb") as stream:
        stream.truncate(20 * 1024 * 1024 + 1)
    with patch("app.tasks.upload_to_notion.requests.request", return_value=_workspace(5 * 1024 * 1024)) as request:
        with pytest.raises(ValueError, match="workspace upload limit"):
            upload_to_notion(str(pdf), {"data_source_id": DS, "attach_pdf": True}, {"api_token": "secret"}, "task")
    assert request.call_count == 1


def test_global_task_does_not_retry_uncertain_page_creation():
    assert NotionPageCreationUncertain in upload_to_notion_global.dont_autoretry_for


def test_global_task_forwards_config_file_id_and_source_link(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"pdf")
    config = type(
        "Config",
        (),
        {
            "notion_enabled": True,
            "multi_user_enabled": False,
            "notion_api_token": "token",
            "notion_data_source_id": DS,
            "notion_database_id": None,
            "notion_title_property": "Name",
            "notion_attach_pdf": True,
            "notion_document_url_base": "https://docs.example",
        },
    )()
    with (
        patch("app.tasks.upload_to_notion.settings", config),
        patch("app.tasks.upload_to_notion.os.path.exists", return_value=True),
        patch("app.tasks.upload_to_notion.upload_to_notion", return_value={"status": "Completed"}) as provider,
        patch("app.tasks.upload_to_notion.log_task_progress"),
    ):
        result = upload_to_notion_global.apply(args=[str(pdf), 42]).result
    assert result["status"] == "Completed"
    provider.assert_called_once_with(
        str(pdf),
        {
            "data_source_id": DS,
            "database_id": None,
            "title_property": "Name",
            "attach_pdf": True,
            "document_url_base": "https://docs.example",
        },
        {"api_token": "token"},
        provider.call_args.args[3],
        file_id=42,
    )


def test_global_task_strips_whitespace_parent_id(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"pdf")
    config = type(
        "Config",
        (),
        {
            "notion_enabled": True,
            "multi_user_enabled": False,
            "notion_api_token": "token",
            "notion_data_source_id": "  ",
            "notion_database_id": " database ",
            "notion_title_property": "Name",
            "notion_attach_pdf": False,
            "notion_document_url_base": None,
        },
    )()
    with (
        patch("app.tasks.upload_to_notion.settings", config),
        patch("app.tasks.upload_to_notion.os.path.exists", return_value=True),
        patch("app.tasks.upload_to_notion.upload_to_notion", return_value={"status": "Completed"}) as provider,
        patch("app.tasks.upload_to_notion.log_task_progress"),
    ):
        upload_to_notion_global.apply(args=[str(pdf), 42])
    assert provider.call_args.args[1]["data_source_id"] is None
    assert provider.call_args.args[1]["database_id"] == "database"


@pytest.mark.parametrize("enabled,multi_user", [(False, False), (True, True)])
def test_global_task_gates_disabled_and_multi_user_without_provider_call(tmp_path, enabled, multi_user):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"pdf")
    config = type(
        "Config", (), {"notion_enabled": enabled, "multi_user_enabled": multi_user, "notion_api_token": "token"}
    )()
    with (
        patch("app.tasks.upload_to_notion.settings", config),
        patch("app.tasks.upload_to_notion.os.path.exists", return_value=True),
        patch("app.tasks.upload_to_notion.upload_to_notion") as provider,
    ):
        with pytest.raises(ValueError, match="Global Notion is disabled"):
            upload_to_notion_global.__wrapped__(str(pdf), 42)
    provider.assert_not_called()


def test_global_task_records_uncertain_failure_without_secret(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"pdf")
    config = type(
        "Config",
        (),
        {
            "notion_enabled": True,
            "multi_user_enabled": False,
            "notion_api_token": "secret",
            "notion_data_source_id": DS,
            "notion_database_id": None,
        },
    )()
    with (
        patch("app.tasks.upload_to_notion.settings", config),
        patch("app.tasks.upload_to_notion.os.path.exists", return_value=True),
        patch(
            "app.tasks.upload_to_notion.upload_to_notion",
            side_effect=NotionPageCreationUncertain("secret-token"),
        ) as provider,
        patch("app.tasks.upload_to_notion.log_task_progress") as progress,
    ):
        with pytest.raises(NotionPageCreationUncertain, match="secret-token"):
            upload_to_notion_global.__wrapped__(str(pdf), 42)
    provider.assert_called_once()
    assert any(call.args[2] == "failure" and "uncertain" in call.args[3] for call in progress.call_args_list)
    assert all("secret-token" not in str(call) for call in progress.call_args_list)


def test_global_task_records_sanitized_normal_failure(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"pdf")
    config = type(
        "Config",
        (),
        {
            "notion_enabled": True,
            "multi_user_enabled": False,
            "notion_api_token": "secret",
            "notion_data_source_id": DS,
            "notion_database_id": None,
        },
    )()
    with (
        patch("app.tasks.upload_to_notion.settings", config),
        patch("app.tasks.upload_to_notion.os.path.exists", return_value=True),
        patch("app.tasks.upload_to_notion.upload_to_notion", side_effect=RuntimeError("secret-token")),
        patch("app.tasks.upload_to_notion.log_task_progress") as progress,
    ):
        with pytest.raises(RuntimeError, match="secret-token"):
            upload_to_notion_global.__wrapped__(str(pdf), 42)
    assert any(call.args[2] == "failure" and call.args[3] == "Notion upload failed" for call in progress.call_args_list)
    assert all("secret-token" not in str(call) for call in progress.call_args_list)


def test_multipart_keeps_one_attachment_and_completes_before_page(tmp_path):
    pdf = tmp_path / "large.pdf"
    pdf.write_bytes(b"x" * (20 * 1024 * 1024 + 1))
    responses = [_workspace(), _response(201, {"id": UPLOAD})]
    responses += [_response(200, {"status": "pending"}) for _ in range(3)]
    responses += [
        _response(200, {"status": "uploaded"}),
        _response(200, {"properties": {"Name": {"type": "title"}}}),
        _response(200, {"id": PAGE}),
    ]
    with patch("app.tasks.upload_to_notion.requests.request", side_effect=responses) as request:
        result = upload_to_notion(str(pdf), {"data_source_id": DS, "attach_pdf": True}, {"api_token": "secret"}, "task")
    calls = request.call_args_list
    assert calls[1].kwargs["json"]["number_of_parts"] == 3
    assert [calls[i].kwargs["data"]["part_number"] for i in range(2, 5)] == ["1", "2", "3"]
    assert [len(calls[i].kwargs["files"]["file"][1]) for i in range(2, 5)] == [10 * 1024 * 1024, 10 * 1024 * 1024, 1]
    assert calls[5].args[1].endswith("/complete")
    assert result["delivery_mode"] == "multipart"
    assert len([b for b in calls[-1].kwargs["json"]["children"] if b["type"] == "file"]) == 1


def test_free_workspace_limit_applies_below_multipart_threshold(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"pdf")
    with patch("app.tasks.upload_to_notion.requests.request", return_value=_workspace(2)) as request:
        with pytest.raises(ValueError, match="workspace upload limit"):
            upload_to_notion(str(pdf), {"data_source_id": DS, "attach_pdf": True}, {"api_token": "secret"}, "task")
    assert request.call_count == 1


def test_workspace_oversize_link_fallback_creates_no_upload(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"pdf")
    responses = [
        _workspace(2),
        _response(200, {"properties": {"Name": {"type": "title"}}}),
        _response(200, {"id": PAGE}),
    ]
    with patch("app.tasks.upload_to_notion.requests.request", side_effect=responses) as request:
        result = upload_to_notion(
            str(pdf),
            {
                "data_source_id": DS,
                "attach_pdf": True,
                "size_policy": "link",
                "document_url_base": "https://docs.example",
            },
            {"api_token": "secret"},
            "task",
            file_id=9,
        )
    assert result["delivery_mode"] == "link"
    assert not any("file_uploads" in c.args[1] for c in request.call_args_list)
    assert not any(b["type"] == "file" for b in request.call_args.kwargs["json"]["children"])


def test_multipart_failure_never_creates_page(tmp_path):
    from app.tasks.upload_to_notion import _upload_pdf

    pdf = tmp_path / "large.pdf"
    with pdf.open("wb") as stream:
        stream.truncate(20 * 1024 * 1024 + 1)
    with patch(
        "app.tasks.upload_to_notion.requests.request",
        side_effect=[_workspace(), _response(201, {"id": UPLOAD}), _response(500, {})],
    ) as request:
        with pytest.raises(RuntimeError):
            _upload_pdf("secret", str(pdf))
    assert request.call_count == 3
