# DocuElevate MCP adapter

This repository includes a read-only MCP server exposing `search_documents`
and `get_document`. The server forwards a dedicated DocuElevate API token to
the existing knowledge API, so the API continues to enforce owner, sharing,
and tenant visibility rules.

The adapter requires Python 3.11 or newer and MCP Python SDK 2.3.0 or newer.
Install its small dependency set with:

```shell
python -m pip install -r requirements-mcp.txt
```

The current token model is owner-bound and expiry-capable but does not yet
have separate read-only scopes. Use a dedicated, short-lived token for MCP.
The semantic knowledge index must be enabled and healthy for search results.

Install the adapter dependencies, then run it over stdio:

```shell
export DOCUELEVATE_URL=https://docuelevate.example
export DOCUELEVATE_API_TOKEN=de_your_token
python /absolute/path/to/DocuElevate/app/mcp_server.py
```

The stable adapter contract is version `1.0`. `search_documents` accepts
`query` (1–4000 characters), `limit` (1–50, default 8), and
`score_threshold` (0–1 or null, default 0.25). `get_document` accepts a
positive integer `document_id`. Both tools are read-only and preserve the
knowledge API's JSON and citation fields.

Example Claude Desktop configuration:

```json
{
  "mcpServers": {
    "docuelevate": {
      "command": "/absolute/path/to/venv/bin/python",
      "args": ["/absolute/path/to/DocuElevate/app/mcp_server.py"],
      "env": {
        "DOCUELEVATE_URL": "https://docuelevate.example",
        "DOCUELEVATE_API_TOKEN": "de_your_token"
      }
    }
  }
}
```

Cursor and other stdio MCP clients use the same command and environment.
Never put a token in tool arguments or commit it to a configuration file.
Use a dedicated, expiring token in the client process environment; the
current owner-bound token model has no separate read-only scopes. This first
version intentionally supports stdio only and does not provide a shared HTTP
MCP endpoint. Search also depends on the semantic index being enabled and
healthy.
