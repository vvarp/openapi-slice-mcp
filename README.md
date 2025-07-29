# OpenAPI Slice MCP Server

An MCP (Model Context Protocol) server that helps you work with large OpenAPI specifications by extracting only the relevant portions for specific endpoints. This is particularly useful when working with LLMs that have context limitations - instead of loading an entire large OpenAPI spec, you can extract just the parts you need for a specific endpoint.

## Features

- **Endpoint-specific extraction**: Get minimal OpenAPI specs containing only the requested endpoint and its dependencies
- **Automatic dependency resolution**: Recursively finds and includes all referenced components (schemas, parameters, etc.)
- **Multiple formats**: Output in YAML or JSON format
- **File support**: Load OpenAPI specs from local YAML or JSON files
- **Remote support**: Fetch OpenAPI specs directly from URLs (HTTP/HTTPS)
- **Discovery tools**: List all available endpoints in a loaded specification

## Tools

The server provides the following MCP tools:

- `load_openapi_spec(file_path: str)` - Load an OpenAPI specification from a local YAML or JSON file
- `load_openapi_spec_from_url(url: str, timeout: int = 30)` - Load an OpenAPI specification from a remote URL
- `list_endpoints()` - List all available endpoints in the currently loaded specification
- `extract_endpoint_slice(path: str, method: str, output_format: str = "yaml")` - Extract a minimal spec slice for a specific endpoint
- `get_server_status()` - Get the current status of the server

## Usage

### Running the Server

```bash
uvx openapi-slice-mcp
```

The server runs using the STDIO transport and can be integrated with any MCP client.
