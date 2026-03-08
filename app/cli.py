"""DocuElevate command-line interface.

Provides a pipe-friendly CLI for scripting and automation against the
DocuElevate REST API.  Authentication is via personal API tokens (the
same tokens managed at ``/api-tokens`` in the web UI).

Usage::

    docuelevate --url http://my-instance --token de_xxx list
    DOCUELEVATE_URL=http://my-instance DOCUELEVATE_API_TOKEN=de_xxx docuelevate list

Commands
--------
upload      Upload one or more local files for processing.
download    Download a processed (or original) file by ID.
search      Full-text search across all documents.
list        List documents with optional filtering.
token       Sub-commands: create / list / revoke API tokens.
"""

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import click
import requests

# ---------------------------------------------------------------------------
# Environment-variable defaults
# ---------------------------------------------------------------------------

ENV_URL = "DOCUELEVATE_URL"
ENV_TOKEN = "DOCUELEVATE_API_TOKEN"

_DEFAULT_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_headers(token: str) -> dict[str, str]:
    """Return Authorization headers for the given API token."""
    return {"Authorization": f"Bearer {token}"}


def _api(
    method: str,
    base_url: str,
    path: str,
    token: str,
    timeout: int = 60,
    **kwargs: Any,
) -> requests.Response:
    """Make an authenticated API request and return the response.

    Args:
        method: HTTP method (GET, POST, DELETE, …).
        base_url: The base URL of the DocuElevate instance.
        path: API path starting with ``/``.
        token: Plaintext API token.
        timeout: Request timeout in seconds (default: 60).
        **kwargs: Extra keyword arguments forwarded to :func:`requests.request`.

    Returns:
        The :class:`requests.Response` object.

    Raises:
        click.ClickException: On network errors.
    """
    url = base_url.rstrip("/") + path
    headers = _build_headers(token)
    try:
        resp = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    except requests.ConnectionError as exc:
        raise click.ClickException(f"Could not connect to {base_url}: {exc}") from exc
    except requests.Timeout as exc:
        raise click.ClickException(f"Request timed out: {exc}") from exc
    return resp


def _require_ok(resp: requests.Response) -> dict[str, Any] | list[Any]:
    """Assert a successful HTTP response and return parsed JSON.

    Args:
        resp: The response to check.

    Returns:
        Parsed JSON payload.

    Raises:
        click.ClickException: If the response status indicates an error.
    """
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise click.ClickException(f"API error {resp.status_code}: {detail}")
    try:
        return resp.json()
    except Exception:
        return {}


def _output(data: Any, fmt: str) -> None:
    """Write *data* to stdout in the requested format.

    Args:
        data: The value to serialise (dict, list, or primitive).
        fmt: Either ``"json"`` (machine-readable) or ``"table"`` (human-readable).
    """
    if fmt == "json":
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        _print_table(data)


def _print_table(data: Any) -> None:
    """Pretty-print a list of dicts as a fixed-width table.

    Falls back to JSON if the data is not a homogeneous list of dicts.

    Args:
        data: Data to render.
    """
    if isinstance(data, dict):
        # Single-object output — print as key: value pairs
        for key, value in data.items():
            click.echo(f"  {key}: {value}")
        return

    if not isinstance(data, list) or not data:
        click.echo(json.dumps(data, indent=2, default=str))
        return

    if not isinstance(data[0], dict):
        for item in data:
            click.echo(str(item))
        return

    # Determine column widths
    keys = list(data[0].keys())
    widths: dict[str, int] = {k: len(k) for k in keys}
    for row in data:
        for k in keys:
            widths[k] = max(widths[k], len(str(row.get(k, ""))))

    header = "  ".join(k.upper().ljust(widths[k]) for k in keys)
    separator = "  ".join("-" * widths[k] for k in keys)
    click.echo(header)
    click.echo(separator)
    for row in data:
        click.echo("  ".join(str(row.get(k, "")).ljust(widths[k]) for k in keys))


# ---------------------------------------------------------------------------
# Root command group
# ---------------------------------------------------------------------------


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--url",
    envvar=ENV_URL,
    default=_DEFAULT_URL,
    show_default=True,
    show_envvar=True,
    help="Base URL of the DocuElevate instance.",
    metavar="URL",
)
@click.option(
    "--token",
    envvar=ENV_TOKEN,
    default=None,
    show_envvar=True,
    help="API token (de_…).  Required for all commands except help.",
    metavar="TOKEN",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Output format.  Use 'json' for machine-readable / pipe-friendly output.",
)
@click.option(
    "--timeout",
    default=60,
    show_default=True,
    envvar="DOCUELEVATE_TIMEOUT",
    show_envvar=True,
    type=int,
    help="HTTP request timeout in seconds.",
)
@click.version_option(package_name="docuelevate", prog_name="docuelevate")
@click.pass_context
def cli(ctx: click.Context, url: str, token: str | None, fmt: str, timeout: int) -> None:
    """DocuElevate CLI — interact with DocuElevate from the command line.

    Configure the target instance and credentials via options or environment
    variables:

    \b
      DOCUELEVATE_URL            Base URL of the instance (default: http://localhost:8000)
      DOCUELEVATE_API_TOKEN      Personal API token (de_…)
      DOCUELEVATE_TIMEOUT        HTTP request timeout in seconds (default: 60)

    Examples:

    \b
      # Upload a file
      docuelevate --token de_xxx upload report.pdf

    \b
      # List files as JSON for further processing
      docuelevate --token de_xxx --format json list | jq '.[].original_filename'

    \b
      # Search for invoices
      docuelevate --token de_xxx search "invoice amazon"
    """
    ctx.ensure_object(dict)
    ctx.obj["url"] = url
    ctx.obj["token"] = token
    ctx.obj["fmt"] = fmt
    ctx.obj["timeout"] = timeout


def _get_token(ctx: click.Context) -> str:
    """Return the token from context, raising ClickException if absent.

    Args:
        ctx: The current Click context.

    Returns:
        The API token string.

    Raises:
        click.ClickException: If no token has been provided.
    """
    token = ctx.obj.get("token")
    if not token:
        raise click.ClickException(f"No API token provided.  Use --token or set the {ENV_TOKEN} environment variable.")
    return token


# ---------------------------------------------------------------------------
# list command
# ---------------------------------------------------------------------------


@cli.command("list")
@click.option("--page", default=1, show_default=True, help="Page number.")
@click.option("--per-page", default=25, show_default=True, help="Items per page (max 200).")
@click.option("--search", default=None, help="Filter by filename substring.")
@click.option("--mime-type", default=None, help="Filter by MIME type (e.g. application/pdf).")
@click.option("--status", "file_status", default=None, help="Filter by status: pending, processing, completed, failed.")
@click.option("--sort-by", default="created_at", show_default=True, help="Sort field.")
@click.option("--sort-order", type=click.Choice(["asc", "desc"]), default="desc", show_default=True)
@click.pass_context
def list_files(
    ctx: click.Context,
    page: int,
    per_page: int,
    search: str | None,
    mime_type: str | None,
    file_status: str | None,
    sort_by: str,
    sort_order: str,
) -> None:
    """List documents stored in DocuElevate.

    Examples:

    \b
      docuelevate list
      docuelevate list --status completed --per-page 10
      docuelevate --format json list | jq '.[].original_filename'
    """
    token = _get_token(ctx)
    url: str = ctx.obj["url"]
    fmt: str = ctx.obj["fmt"]
    timeout: int = ctx.obj["timeout"]

    params: dict[str, Any] = {
        "page": page,
        "per_page": per_page,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }
    if search:
        params["search"] = search
    if mime_type:
        params["mime_type"] = mime_type
    if file_status:
        params["status"] = file_status

    resp = _api("GET", url, "/api/files", token, timeout=timeout, params=params)
    payload = _require_ok(resp)

    # Extract the list from the paginated response
    files: list[dict[str, Any]] = payload.get("files", payload) if isinstance(payload, dict) else payload  # type: ignore[assignment]
    pagination: dict[str, Any] = payload.get("pagination", {}) if isinstance(payload, dict) else {}

    if fmt == "json":
        _output(files, fmt)
    else:
        # Trim fields for readable table
        rows = [
            {
                "id": f.get("id"),
                "filename": f.get("original_filename"),
                "size": f.get("file_size"),
                "status": f.get("status"),
                "created_at": str(f.get("created_at", ""))[:19],
            }
            for f in files
        ]
        _output(rows, fmt)
        if pagination:
            click.echo(f"\nPage {pagination.get('page')}/{pagination.get('pages')}  ({pagination.get('total')} total)")


# ---------------------------------------------------------------------------
# upload command
# ---------------------------------------------------------------------------


@cli.command("upload")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True, readable=True))
@click.option(
    "--batch-size",
    default=5,
    show_default=True,
    help="Maximum number of concurrent uploads (sequential when 1).",
)
@click.pass_context
def upload_files(ctx: click.Context, files: tuple[str, ...], batch_size: int) -> None:
    """Upload one or more local files for processing.

    Supports glob patterns and multiple arguments for batch uploads.

    Examples:

    \b
      docuelevate upload report.pdf
      docuelevate upload *.pdf invoice_*.png
      docuelevate upload --batch-size 3 /scans/*.pdf
    """
    token = _get_token(ctx)
    url: str = ctx.obj["url"]
    fmt: str = ctx.obj["fmt"]
    timeout: int = ctx.obj["timeout"]

    results: list[dict[str, Any]] = []
    failed = 0

    for i, file_path in enumerate(files, 1):
        path = Path(file_path)
        click.echo(f"[{i}/{len(files)}] Uploading {path.name}…", err=True)
        try:
            with path.open("rb") as fh:
                resp = _api(
                    "POST",
                    url,
                    "/api/ui-upload",
                    token,
                    timeout=timeout,
                    files={"file": (path.name, fh)},
                )
            if resp.status_code >= 400:
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text
                click.echo(f"  ERROR {resp.status_code}: {detail}", err=True)
                results.append({"file": path.name, "status": "error", "detail": detail})
                failed += 1
            else:
                data = resp.json()
                results.append({"file": path.name, "status": "queued", **data})
                click.echo(f"  OK  task_id={data.get('task_id', '?')}", err=True)
        except click.ClickException:
            raise
        except Exception as exc:
            click.echo(f"  ERROR: {exc}", err=True)
            results.append({"file": path.name, "status": "error", "detail": str(exc)})
            failed += 1

    _output(results, fmt)

    if failed:
        click.echo(f"\n{failed}/{len(files)} upload(s) failed.", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# download command
# ---------------------------------------------------------------------------


@cli.command("download")
@click.argument("file_id", type=int)
@click.option(
    "--output",
    "-o",
    default=None,
    help="Destination file path.  Defaults to the server-provided filename in the current directory.",
    type=click.Path(),
)
@click.option(
    "--version",
    type=click.Choice(["processed", "original"]),
    default="processed",
    show_default=True,
    help="Which version to download.",
)
@click.pass_context
def download_file(ctx: click.Context, file_id: int, output: str | None, version: str) -> None:
    """Download a file by its numeric ID.

    Examples:

    \b
      docuelevate download 42
      docuelevate download 42 --version original -o /tmp/orig.pdf
    """
    token = _get_token(ctx)
    url: str = ctx.obj["url"]
    timeout: int = ctx.obj["timeout"]

    resp = _api(
        "GET",
        url,
        f"/api/files/{file_id}/download",
        token,
        timeout=timeout,
        params={"version": version},
        stream=True,
    )
    _require_ok(resp)

    # Determine output filename
    if output:
        dest = Path(output)
    else:
        content_disp = resp.headers.get("content-disposition", "")
        filename = f"file_{file_id}"
        for raw_part in content_disp.split(";"):
            clean = raw_part.strip()
            if clean.startswith("filename="):
                filename = clean[len("filename=") :].strip('"').strip("'")
                break
            if clean.startswith("filename*="):
                raw = clean[len("filename*=") :]
                if raw.upper().startswith("UTF-8''"):
                    filename = unquote(raw[7:])
                    break
        dest = Path(filename)

    with dest.open("wb") as fh:
        for chunk in resp.iter_content(chunk_size=65536):
            fh.write(chunk)

    click.echo(f"Downloaded {dest} ({dest.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# search command
# ---------------------------------------------------------------------------


@cli.command("search")
@click.argument("query")
@click.option("--mime-type", default=None, help="Filter by MIME type.")
@click.option("--document-type", default=None, help="Filter by document type (e.g. Invoice).")
@click.option("--tags", default=None, help="Filter by tag.")
@click.option("--language", default=None, help="Filter by language code (e.g. en, de).")
@click.option("--page", default=1, show_default=True)
@click.option("--per-page", default=20, show_default=True, help="Results per page (max 100).")
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    mime_type: str | None,
    document_type: str | None,
    tags: str | None,
    language: str | None,
    page: int,
    per_page: int,
) -> None:
    """Full-text search across all documents.

    Examples:

    \b
      docuelevate search "invoice amazon"
      docuelevate search "contract" --document-type Contract --language en
      docuelevate --format json search "receipt" | jq '.[].file_id'
    """
    token = _get_token(ctx)
    url: str = ctx.obj["url"]
    fmt: str = ctx.obj["fmt"]
    timeout: int = ctx.obj["timeout"]

    params: dict[str, Any] = {"q": query, "page": page, "per_page": per_page}
    if mime_type:
        params["mime_type"] = mime_type
    if document_type:
        params["document_type"] = document_type
    if tags:
        params["tags"] = tags
    if language:
        params["language"] = language

    resp = _api("GET", url, "/api/search", token, timeout=timeout, params=params)
    payload = _require_ok(resp)

    results: list[dict[str, Any]] = (
        payload.get("results", payload) if isinstance(payload, dict) else payload  # type: ignore[assignment]
    )
    total: int = payload.get("total", len(results)) if isinstance(payload, dict) else len(results)
    pages: int = payload.get("pages", 1) if isinstance(payload, dict) else 1

    if fmt == "json":
        _output(results, fmt)
    else:
        rows = [
            {
                "file_id": r.get("file_id"),
                "filename": r.get("original_filename"),
                "type": r.get("document_type"),
                "tags": ",".join(r.get("tags") or []),
            }
            for r in results
        ]
        _output(rows, fmt)
        click.echo(f"\nPage {page}/{pages}  ({total} total results)")


# ---------------------------------------------------------------------------
# token sub-group
# ---------------------------------------------------------------------------


@cli.group("token")
@click.pass_context
def token_group(ctx: click.Context) -> None:
    """Manage personal API tokens.

    Tokens can be created, listed, and revoked.  Token rotation is achieved
    by creating a new token before revoking the old one.

    Examples:

    \b
      docuelevate token create "CI Pipeline"
      docuelevate token list
      docuelevate token revoke 3
    """


@token_group.command("create")
@click.argument("name")
@click.pass_context
def token_create(ctx: click.Context, name: str) -> None:
    """Create a new personal API token.

    The full token value is printed exactly once.  Store it securely.

    Examples:

    \b
      docuelevate token create "My script"
      docuelevate --format json token create "CI" | jq -r '.token'
    """
    token = _get_token(ctx)
    url: str = ctx.obj["url"]
    fmt: str = ctx.obj["fmt"]
    timeout: int = ctx.obj["timeout"]

    resp = _api("POST", url, "/api/api-tokens/", token, timeout=timeout, json={"name": name})
    payload = _require_ok(resp)

    if fmt == "json":
        _output(payload, fmt)
    else:
        if not isinstance(payload, dict):
            raise click.ClickException("Unexpected API response format.")
        click.echo("Token created successfully:")
        click.echo(f"  ID:     {payload.get('id')}")
        click.echo(f"  Name:   {payload.get('name')}")
        click.echo(f"  Prefix: {payload.get('token_prefix')}")
        click.echo(f"  Token:  {payload.get('token')}")
        click.echo()
        click.echo("Store this token securely — it will not be shown again.", err=True)


@token_group.command("list")
@click.pass_context
def token_list(ctx: click.Context) -> None:
    """List all your API tokens (active and revoked).

    Examples:

    \b
      docuelevate token list
      docuelevate --format json token list | jq '.[] | select(.is_active)'
    """
    token = _get_token(ctx)
    url: str = ctx.obj["url"]
    fmt: str = ctx.obj["fmt"]
    timeout: int = ctx.obj["timeout"]

    resp = _api("GET", url, "/api/api-tokens/", token, timeout=timeout)
    payload = _require_ok(resp)

    if fmt == "json":
        _output(payload, fmt)
    else:
        if not isinstance(payload, list):
            raise click.ClickException("Unexpected API response format.")
        rows = [
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "prefix": t.get("token_prefix"),
                "active": t.get("is_active"),
                "last_used": str(t.get("last_used_at") or "never")[:19],
                "created": str(t.get("created_at") or "")[:19],
            }
            for t in payload
        ]
        _output(rows, fmt)


@token_group.command("revoke")
@click.argument("token_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def token_revoke(ctx: click.Context, token_id: int, yes: bool) -> None:
    """Revoke an API token by its numeric ID.

    The token is soft-deleted (kept for audit) but immediately invalidated.

    Examples:

    \b
      docuelevate token revoke 3
      docuelevate token revoke 3 --yes
    """
    token = _get_token(ctx)
    url: str = ctx.obj["url"]
    timeout: int = ctx.obj["timeout"]

    if not yes:
        click.confirm(f"Revoke token {token_id}?", abort=True)

    resp = _api("DELETE", url, f"/api/api-tokens/{token_id}", token, timeout=timeout)
    _require_ok(resp)
    click.echo(f"Token {token_id} revoked.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the ``docuelevate`` console script."""
    cli(auto_envvar_prefix="DOCUELEVATE")  # type: ignore[call-arg]


if __name__ == "__main__":
    main()
