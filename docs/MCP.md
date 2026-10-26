# DocuElevate MCP adapter

This repository includes a read-only MCP server exposing `search_documents`
and `get_document`. The server forwards a dedicated DocuElevate API token to
the existing knowledge API, so the API continues to enforce owner, sharing,
and tenant visibility rules.

The current token model is owner-bound and expiry-capable but does not yet
have separate read-only scopes. Use a dedicated, short-lived token for MCP.
The semantic knowledge index must be enabled and healthy for search results.

Install the adapter dependencies, then run it over stdio:

```shell
export DOCUELEVATE_URL=https://docuelevate.example
export DOCUELEVATE_API_TOKEN=de_your_token
python -m app.mcp_server
```

Example Claude Desktop configuration:

```json
{
  "mcpServers": {
    "docuelevate": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/path/to/DocuElevate",
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
