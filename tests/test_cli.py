"""Unit tests for app/cli.py — DocuElevate CLI tool.

Tests cover:
- Root command group option handling (URL, token, format)
- list command with various filters
- upload command (single file, batch, error handling)
- download command (with/without --output, Content-Disposition parsing)
- search command with filters
- token sub-commands (create, list, revoke)
- Helper functions (_build_headers, _api, _require_ok, _output, _print_table)
- Environment variable configuration
- Missing-token error handling
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests as req_module
from click.testing import CliRunner

from app.cli import (
    _api,
    _build_headers,
    _output,
    _print_table,
    _require_ok,
    cli,
    main,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(status_code: int = 200, json_data=None, text: str = "", headers: dict | None = None):
    """Create a mock requests.Response."""
    mock = MagicMock(spec=req_module.Response)
    mock.status_code = status_code
    mock.text = text
    mock.headers = headers or {}
    if json_data is not None:
        mock.json.return_value = json_data
    else:
        mock.json.side_effect = ValueError("No JSON")
    return mock


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildHeaders:
    def test_returns_authorization_header(self):
        headers = _build_headers("de_mytoken")
        assert headers == {"Authorization": "Bearer de_mytoken"}


@pytest.mark.unit
class TestApi:
    def test_successful_request(self):
        mock_resp = _make_response(200, json_data={"ok": True})
        with patch("app.cli.requests.request", return_value=mock_resp) as mock_req:
            resp = _api("GET", "http://localhost:8000", "/api/files", "de_tok")
        mock_req.assert_called_once()
        call_kwargs = mock_req.call_args
        assert call_kwargs[0][0] == "GET"
        assert call_kwargs[0][1] == "http://localhost:8000/api/files"
        assert resp.status_code == 200

    def test_strips_trailing_slash_from_base_url(self):
        mock_resp = _make_response(200, json_data={})
        with patch("app.cli.requests.request", return_value=mock_resp) as mock_req:
            _api("GET", "http://localhost:8000/", "/api/files", "de_tok")
        assert mock_req.call_args[0][1] == "http://localhost:8000/api/files"

    def test_connection_error_raises_click_exception(self):
        import click

        with patch("app.cli.requests.request", side_effect=req_module.ConnectionError("refused")):
            with pytest.raises(click.ClickException, match="Could not connect"):
                _api("GET", "http://localhost:8000", "/api/files", "de_tok")

    def test_timeout_raises_click_exception(self):
        import click

        with patch("app.cli.requests.request", side_effect=req_module.Timeout("timed out")):
            with pytest.raises(click.ClickException, match="timed out"):
                _api("GET", "http://localhost:8000", "/api/files", "de_tok")


@pytest.mark.unit
class TestRequireOk:
    def test_returns_json_on_success(self):
        mock_resp = _make_response(200, json_data={"data": [1, 2, 3]})
        result = _require_ok(mock_resp)
        assert result == {"data": [1, 2, 3]}

    def test_raises_on_400(self):
        import click

        mock_resp = _make_response(400, json_data={"detail": "Bad request"})
        with pytest.raises(click.ClickException, match="API error 400"):
            _require_ok(mock_resp)

    def test_raises_on_404(self):
        import click

        mock_resp = _make_response(404, json_data={"detail": "Not found"})
        with pytest.raises(click.ClickException, match="404"):
            _require_ok(mock_resp)

    def test_raises_on_500_with_text_fallback(self):
        import click

        mock_resp = _make_response(500, text="Internal Server Error")
        mock_resp.json.side_effect = ValueError("no json")
        with pytest.raises(click.ClickException, match="500"):
            _require_ok(mock_resp)

    def test_returns_empty_dict_when_no_json(self):
        mock_resp = _make_response(200)
        mock_resp.json.side_effect = ValueError("no json")
        result = _require_ok(mock_resp)
        assert result == {}


@pytest.mark.unit
class TestOutput:
    def test_json_format(self, capsys):
        _output({"key": "value"}, "json")
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == {"key": "value"}

    def test_table_format_dict(self, capsys):
        _output({"id": 1, "name": "test"}, "table")
        captured = capsys.readouterr()
        assert "id" in captured.out
        assert "name" in captured.out

    def test_table_format_list(self, capsys):
        _output([{"id": 1, "name": "file1"}, {"id": 2, "name": "file2"}], "table")
        captured = capsys.readouterr()
        assert "file1" in captured.out
        assert "file2" in captured.out

    def test_table_empty_list(self, capsys):
        _output([], "table")
        # Should not raise, output can be empty or a JSON representation
        capsys.readouterr()

    def test_table_non_dict_items(self, capsys):
        _output(["item1", "item2"], "table")
        captured = capsys.readouterr()
        assert "item1" in captured.out


@pytest.mark.unit
class TestPrintTable:
    def test_single_dict(self, capsys):
        _print_table({"id": 42, "name": "doc"})
        captured = capsys.readouterr()
        assert "42" in captured.out
        assert "doc" in captured.out

    def test_list_of_dicts(self, capsys):
        _print_table([{"id": 1, "name": "a"}, {"id": 2, "name": "bb"}])
        captured = capsys.readouterr()
        assert "ID" in captured.out
        assert "NAME" in captured.out
        assert "a" in captured.out
        assert "bb" in captured.out

    def test_fallback_json_for_non_dict_list_items(self, capsys):
        _print_table([1, 2, 3])
        captured = capsys.readouterr()
        assert "1" in captured.out

    def test_fallback_json_for_scalar(self, capsys):
        _print_table("plain string")
        capsys.readouterr()  # just assert no exception


# ---------------------------------------------------------------------------
# CLI integration tests via CliRunner
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMissingToken:
    """Commands must fail gracefully when no token is supplied."""

    def test_list_without_token(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--url", "http://localhost:8000", "list"])
        assert result.exit_code != 0
        assert "DOCUELEVATE_API_TOKEN" in result.output or "No API token" in result.output

    def test_upload_without_token(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4")
        runner = CliRunner()
        result = runner.invoke(cli, ["--url", "http://localhost:8000", "upload", str(f)])
        assert result.exit_code != 0

    def test_search_without_token(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--url", "http://localhost:8000", "search", "invoice"])
        assert result.exit_code != 0

    def test_token_create_without_token(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--url", "http://localhost:8000", "token", "create", "test"])
        assert result.exit_code != 0

    def test_token_list_without_token(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--url", "http://localhost:8000", "token", "list"])
        assert result.exit_code != 0

    def test_token_revoke_without_token(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--url", "http://localhost:8000", "token", "revoke", "--yes", "1"])
        assert result.exit_code != 0


@pytest.mark.unit
class TestListCommand:
    def test_list_success_table(self):
        files_data = {
            "files": [
                {
                    "id": 1,
                    "original_filename": "test.pdf",
                    "file_size": 1024,
                    "status": "completed",
                    "created_at": "2026-01-01T00:00:00",
                },
            ],
            "pagination": {"page": 1, "pages": 1, "total": 1},
        }
        mock_resp = _make_response(200, json_data=files_data)
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "list"])
        assert result.exit_code == 0
        assert "test.pdf" in result.output

    def test_list_success_json(self):
        files_data = {
            "files": [{"id": 1, "original_filename": "file.pdf"}],
            "pagination": {"page": 1, "pages": 1, "total": 1},
        }
        mock_resp = _make_response(200, json_data=files_data)
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "--format", "json", "list"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert parsed[0]["id"] == 1

    def test_list_with_filters(self):
        mock_resp = _make_response(200, json_data={"files": [], "pagination": {"page": 1, "pages": 0, "total": 0}})
        with patch("app.cli._api", return_value=mock_resp) as mock_api:
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--token", "de_tok", "list", "--status", "completed", "--mime-type", "application/pdf"],
            )
        assert result.exit_code == 0
        call_kwargs = mock_api.call_args[1]
        assert call_kwargs["params"]["status"] == "completed"
        assert call_kwargs["params"]["mime_type"] == "application/pdf"

    def test_list_api_error(self):
        mock_resp = _make_response(401, json_data={"detail": "Unauthorized"})
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_bad", "list"])
        assert result.exit_code != 0
        assert "401" in result.output

    def test_list_raw_list_response(self):
        """Handles when the API returns a plain list (not paginated dict)."""
        files_data = [{"id": 1, "original_filename": "a.pdf"}]
        mock_resp = _make_response(200, json_data=files_data)
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "--format", "json", "list"])
        assert result.exit_code == 0


@pytest.mark.unit
class TestUploadCommand:
    def test_upload_single_file_success(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_bytes(b"%PDF-1.4 content")
        mock_resp = _make_response(201, json_data={"task_id": "abc-123", "status": "queued"})
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "upload", str(f)])
        assert result.exit_code == 0
        assert "abc-123" in result.output

    def test_upload_multiple_files_success(self, tmp_path):
        files = []
        for i in range(3):
            f = tmp_path / f"file{i}.pdf"
            f.write_bytes(b"PDF")
            files.append(str(f))
        mock_resp = _make_response(201, json_data={"task_id": f"task-{0}", "status": "queued"})
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "upload", *files])
        assert result.exit_code == 0

    def test_upload_single_file_api_error(self, tmp_path):
        f = tmp_path / "bad.pdf"
        f.write_bytes(b"data")
        mock_resp = _make_response(413, json_data={"detail": "File too large"})
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "upload", str(f)])
        assert result.exit_code == 1
        assert "failed" in result.output.lower() or "error" in result.output.lower()

    def test_upload_json_output(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"PDF")
        mock_resp = _make_response(201, json_data={"task_id": "t1", "status": "queued"})
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "--format", "json", "upload", str(f)])
        assert result.exit_code == 0
        # Progress lines (stderr) are mixed with JSON stdout in CliRunner.
        # The JSON array is the last block in the output starting with '['.
        import re

        json_match = re.search(r"(\[\s*\{.*?\}\s*\])", result.output, re.DOTALL)
        assert json_match is not None, f"No JSON array found in: {result.output!r}"
        parsed = json.loads(json_match.group(1))
        assert isinstance(parsed, list)
        assert parsed[0]["status"] == "queued"

    def test_upload_partial_failure(self, tmp_path):
        """Mixed success/failure: exit code 1 if any upload fails."""
        f1 = tmp_path / "ok.pdf"
        f1.write_bytes(b"PDF")
        f2 = tmp_path / "fail.pdf"
        f2.write_bytes(b"PDF")

        ok_resp = _make_response(201, json_data={"task_id": "t1"})
        err_resp = _make_response(500, json_data={"detail": "Server error"})

        with patch("app.cli._api", side_effect=[ok_resp, err_resp]):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "upload", str(f1), str(f2)])
        assert result.exit_code == 1


@pytest.mark.unit
class TestDownloadCommand:
    def test_download_with_explicit_output(self, tmp_path):
        dest = tmp_path / "out.pdf"
        mock_resp = _make_response(200, headers={"content-disposition": 'attachment; filename="doc.pdf"'})
        mock_resp.iter_content.return_value = [b"PDF content"]
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            with runner.isolated_filesystem():
                result = runner.invoke(
                    cli,
                    ["--token", "de_tok", "download", "42", "--output", str(dest)],
                )
        assert result.exit_code == 0
        assert dest.exists()

    def test_download_filename_from_content_disposition(self, tmp_path):
        mock_resp = _make_response(200, headers={"content-disposition": 'attachment; filename="invoice.pdf"'})
        mock_resp.iter_content.return_value = [b"PDF data"]
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            with runner.isolated_filesystem():
                result = runner.invoke(cli, ["--token", "de_tok", "download", "7"])
        assert result.exit_code == 0
        assert "invoice.pdf" in result.output

    def test_download_filename_from_content_disposition_utf8(self, tmp_path):
        mock_resp = _make_response(
            200,
            headers={"content-disposition": "attachment; filename*=UTF-8''Rechnung%202026.pdf"},
        )
        mock_resp.iter_content.return_value = [b"PDF data"]
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            with runner.isolated_filesystem():
                result = runner.invoke(cli, ["--token", "de_tok", "download", "8"])
        assert result.exit_code == 0
        assert "Rechnung" in result.output

    def test_download_fallback_filename(self):
        mock_resp = _make_response(200, headers={"content-disposition": ""})
        mock_resp.iter_content.return_value = [b"data"]
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            with runner.isolated_filesystem():
                result = runner.invoke(cli, ["--token", "de_tok", "download", "99"])
        assert result.exit_code == 0
        assert "file_99" in result.output

    def test_download_api_error(self):
        mock_resp = _make_response(404, json_data={"detail": "Not found"})
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "download", "999"])
        assert result.exit_code != 0
        assert "404" in result.output

    def test_download_original_version(self, tmp_path):
        mock_resp = _make_response(200, headers={"content-disposition": 'attachment; filename="orig.pdf"'})
        mock_resp.iter_content.return_value = [b"original"]
        with patch("app.cli._api", return_value=mock_resp) as mock_api:
            runner = CliRunner()
            with runner.isolated_filesystem():
                result = runner.invoke(cli, ["--token", "de_tok", "download", "5", "--version", "original"])
        assert result.exit_code == 0
        call_kwargs = mock_api.call_args[1]
        assert call_kwargs["params"]["version"] == "original"


@pytest.mark.unit
class TestSearchCommand:
    def test_search_success_table(self):
        payload = {
            "results": [
                {
                    "file_id": 1,
                    "original_filename": "inv.pdf",
                    "document_type": "Invoice",
                    "tags": ["amazon"],
                }
            ],
            "total": 1,
            "pages": 1,
        }
        mock_resp = _make_response(200, json_data=payload)
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "search", "invoice"])
        assert result.exit_code == 0
        assert "inv.pdf" in result.output

    def test_search_success_json(self):
        payload = {"results": [{"file_id": 2}], "total": 1, "pages": 1}
        mock_resp = _make_response(200, json_data=payload)
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "--format", "json", "search", "test"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert parsed[0]["file_id"] == 2

    def test_search_with_filters_passed_to_api(self):
        payload = {"results": [], "total": 0, "pages": 0}
        mock_resp = _make_response(200, json_data=payload)
        with patch("app.cli._api", return_value=mock_resp) as mock_api:
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "--token",
                    "de_tok",
                    "search",
                    "contract",
                    "--document-type",
                    "Contract",
                    "--tags",
                    "legal",
                    "--language",
                    "en",
                    "--mime-type",
                    "application/pdf",
                ],
            )
        assert result.exit_code == 0
        params = mock_api.call_args[1]["params"]
        assert params["document_type"] == "Contract"
        assert params["tags"] == "legal"
        assert params["language"] == "en"
        assert params["mime_type"] == "application/pdf"

    def test_search_api_error(self):
        mock_resp = _make_response(400, json_data={"detail": "Invalid query"})
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "search", "bad"])
        assert result.exit_code != 0

    def test_search_plain_list_response(self):
        """Handles when API returns a plain list."""
        mock_resp = _make_response(200, json_data=[{"file_id": 3}])
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "--format", "json", "search", "x"])
        assert result.exit_code == 0


@pytest.mark.unit
class TestTokenCreate:
    def test_create_token_table(self):
        payload = {
            "id": 5,
            "name": "CI Pipeline",
            "token_prefix": "de_Abc123",
            "token": "de_Abc123_fulltoken",
            "is_active": True,
            "last_used_at": None,
            "last_used_ip": None,
            "created_at": "2026-01-01T00:00:00",
            "revoked_at": None,
        }
        mock_resp = _make_response(201, json_data=payload)
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "token", "create", "CI Pipeline"])
        assert result.exit_code == 0
        assert "de_Abc123_fulltoken" in result.output
        assert "CI Pipeline" in result.output

    def test_create_token_json(self):
        payload = {"id": 6, "name": "Script", "token": "de_full", "token_prefix": "de_fu"}
        mock_resp = _make_response(201, json_data=payload)
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "--format", "json", "token", "create", "Script"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["token"] == "de_full"

    def test_create_token_api_error(self):
        mock_resp = _make_response(422, json_data={"detail": "name too short"})
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "token", "create", "x"])
        assert result.exit_code != 0

    def test_create_token_unexpected_response_format(self):
        """If API returns a list instead of dict, should fail gracefully."""
        mock_resp = _make_response(201, json_data=[{"id": 1}])
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "token", "create", "bad"])
        assert result.exit_code != 0


@pytest.mark.unit
class TestTokenList:
    def test_list_tokens_table(self):
        payload = [
            {
                "id": 1,
                "name": "CI",
                "token_prefix": "de_Ab",
                "is_active": True,
                "last_used_at": "2026-01-15T10:00:00",
                "last_used_ip": "10.0.0.1",
                "created_at": "2026-01-01T00:00:00",
                "revoked_at": None,
            }
        ]
        mock_resp = _make_response(200, json_data=payload)
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "token", "list"])
        assert result.exit_code == 0
        assert "CI" in result.output

    def test_list_tokens_json(self):
        payload = [{"id": 2, "name": "S", "is_active": False}]
        mock_resp = _make_response(200, json_data=payload)
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "--format", "json", "token", "list"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed[0]["id"] == 2

    def test_list_tokens_unexpected_format(self):
        """If API returns a dict instead of list, should fail gracefully."""
        mock_resp = _make_response(200, json_data={"id": 1})
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "token", "list"])
        assert result.exit_code != 0


@pytest.mark.unit
class TestTokenRevoke:
    def test_revoke_with_yes_flag(self):
        mock_resp = _make_response(200, json_data={"detail": "Token revoked"})
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "token", "revoke", "--yes", "3"])
        assert result.exit_code == 0
        assert "revoked" in result.output.lower()

    def test_revoke_prompts_for_confirmation(self):
        mock_resp = _make_response(200, json_data={"detail": "Token revoked"})
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "token", "revoke", "3"], input="y\n")
        assert result.exit_code == 0

    def test_revoke_aborts_on_no(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--token", "de_tok", "token", "revoke", "3"], input="n\n")
        assert result.exit_code != 0

    def test_revoke_api_error(self):
        mock_resp = _make_response(404, json_data={"detail": "Token not found"})
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner()
            result = runner.invoke(cli, ["--token", "de_tok", "token", "revoke", "--yes", "999"])
        assert result.exit_code != 0
        assert "404" in result.output


@pytest.mark.unit
class TestEnvironmentVariables:
    def test_token_from_env_var(self):
        payload = {"files": [], "pagination": {"page": 1, "pages": 0, "total": 0}}
        mock_resp = _make_response(200, json_data=payload)
        with patch("app.cli._api", return_value=mock_resp):
            runner = CliRunner(env={"DOCUELEVATE_API_TOKEN": "de_envtoken"})
            result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0

    def test_url_from_env_var(self):
        payload = {"files": [], "pagination": {"page": 1, "pages": 0, "total": 0}}
        mock_resp = _make_response(200, json_data=payload)
        with patch("app.cli._api", return_value=mock_resp) as mock_api:
            runner = CliRunner(env={"DOCUELEVATE_URL": "http://my-server:9000", "DOCUELEVATE_API_TOKEN": "de_tok"})
            result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert mock_api.call_args[0][1] == "http://my-server:9000"

    def test_explicit_token_overrides_env(self):
        payload = {"files": [], "pagination": {"page": 1, "pages": 0, "total": 0}}
        mock_resp = _make_response(200, json_data=payload)
        with patch("app.cli._api", return_value=mock_resp) as mock_api:
            runner = CliRunner(env={"DOCUELEVATE_API_TOKEN": "de_env"})
            result = runner.invoke(cli, ["--token", "de_explicit", "list"])
        assert result.exit_code == 0
        # Token passed to _api should be the explicit one
        token_arg = mock_api.call_args[0][3]
        assert token_arg == "de_explicit"


@pytest.mark.unit
class TestMainEntryPoint:
    def test_main_invokes_cli(self):
        """main() should be callable without errors (help flag)."""
        runner = CliRunner()
        with patch("app.cli.cli") as mock_cli:
            main()
        mock_cli.assert_called_once()
