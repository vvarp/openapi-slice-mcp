import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import httpx
import yaml
from fastmcp import FastMCP


class OpenAPISpecProcessor:
    """Processes OpenAPI specifications and extracts relevant parts for specific endpoints."""

    def __init__(self, spec_data: Dict[str, Any]):
        self.spec = spec_data
        self._components = spec_data.get("components", {})
        self._paths = spec_data.get("paths", {})

    def extract_endpoint_slice(self, path: str, method: str) -> Dict[str, Any]:
        """Extract only the relevant parts of the OpenAPI spec for a specific endpoint."""
        method = method.lower()

        if path not in self._paths or method not in self._paths[path]:
            raise ValueError(f"Endpoint {method.upper()} {path} not found in spec")

        # Start with basic spec structure
        slice_spec = {
            "openapi": self.spec.get("openapi", "3.0.0"),
            "info": self.spec.get("info", {}),
            "servers": self.spec.get("servers", []),
            "paths": {path: {method: self._paths[path][method]}},
            "components": {},
        }

        # Find all referenced components for this endpoint
        referenced_schemas = self._find_referenced_components(self._paths[path][method])

        # Add only the referenced components
        if referenced_schemas:
            slice_spec["components"] = self._extract_components(referenced_schemas)

        return slice_spec

    def _find_referenced_components(self, endpoint_spec: Dict[str, Any]) -> Set[str]:
        """Recursively find all $ref components used by an endpoint."""
        refs = set()

        def extract_refs(obj: Any) -> None:
            if isinstance(obj, dict):
                if "$ref" in obj:
                    ref_path = obj["$ref"]
                    if ref_path.startswith("#/components/schemas/"):
                        schema_name = ref_path.split("/")[-1]
                        refs.add(schema_name)
                for value in obj.values():
                    extract_refs(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_refs(item)

        extract_refs(endpoint_spec)

        # Recursively find nested references
        found_new_refs = True
        while found_new_refs:
            found_new_refs = False
            current_refs = refs.copy()
            for ref in current_refs:
                if ref in self._components.get("schemas", {}):
                    schema = self._components["schemas"][ref]
                    old_count = len(refs)
                    extract_refs(schema)
                    if len(refs) > old_count:
                        found_new_refs = True

        return refs

    def _extract_components(self, schema_names: Set[str]) -> Dict[str, Any]:
        """Extract only the specified components from the full spec."""
        components = {}

        if schema_names and "schemas" in self._components:
            components["schemas"] = {}
            for name in schema_names:
                if name in self._components["schemas"]:
                    components["schemas"][name] = self._components["schemas"][name]

        # Copy other component types if they exist and might be referenced
        for comp_type in [
            "responses",
            "parameters",
            "examples",
            "requestBodies",
            "headers",
            "securitySchemes",
            "links",
            "callbacks",
        ]:
            if comp_type in self._components:
                # For now, include all of these - could be made more selective
                components[comp_type] = self._components[comp_type]

        return components

    def list_endpoints(self) -> List[Dict[str, str]]:
        """List all available endpoints in the spec."""
        endpoints = []
        for path, methods in self._paths.items():
            for method in methods.keys():
                if method not in ["parameters", "summary", "description"]:
                    endpoints.append(
                        {
                            "path": path,
                            "method": method.upper(),
                            "summary": methods[method].get("summary", ""),
                            "operationId": methods[method].get("operationId", ""),
                        }
                    )
        return endpoints


# Create the MCP server
mcp = FastMCP(
    name="OpenAPI Slice Server",
    instructions="""This server helps you work with large OpenAPI specifications by extracting only the relevant parts for specific endpoints.

    Use 'load_openapi_spec' to load a YAML or JSON OpenAPI specification from a local file.
    Use 'load_openapi_spec_from_url' to load an OpenAPI specification from a remote URL.
    Use 'list_endpoints' to see all available endpoints in the loaded spec.
    Use 'extract_endpoint_slice' to get a minimal OpenAPI spec containing only the specified endpoint and its dependencies.
    """,
)

# Global variable to store the loaded spec processor
current_processor: Optional[OpenAPISpecProcessor] = None


@mcp.tool
def load_openapi_spec(file_path: str) -> str:
    """Load an OpenAPI specification from a YAML or JSON file."""
    global current_processor

    try:
        path = Path(file_path)
        if not path.exists():
            return f"Error: File {file_path} does not exist"

        with open(path, "r", encoding="utf-8") as f:
            if path.suffix.lower() in [".yaml", ".yml"]:
                spec_data = yaml.safe_load(f)
            elif path.suffix.lower() == ".json":
                spec_data = json.load(f)
            else:
                return "Error: File must be a .yaml, .yml, or .json file"

        if not isinstance(spec_data, dict) or "paths" not in spec_data:
            return "Error: Invalid OpenAPI specification - must contain 'paths' section"

        current_processor = OpenAPISpecProcessor(spec_data)

        endpoints_count = len([path for path in spec_data.get("paths", {}).keys()])
        spec_title = spec_data.get("info", {}).get("title", "Unknown")
        spec_version = spec_data.get("info", {}).get("version", "Unknown")

        return f"Successfully loaded OpenAPI spec: {spec_title} v{spec_version} with {endpoints_count} paths"

    except yaml.YAMLError as e:
        return f"Error parsing YAML file: {str(e)}"
    except json.JSONDecodeError as e:
        return f"Error parsing JSON file: {str(e)}"
    except Exception as e:
        return f"Error loading file: {str(e)}"


@mcp.tool
def list_endpoints() -> str:
    """List all available endpoints in the currently loaded OpenAPI specification."""
    global current_processor

    if current_processor is None:
        return "Error: No OpenAPI specification loaded. Use 'load_openapi_spec' first."

    try:
        endpoints = current_processor.list_endpoints()

        if not endpoints:
            return "No endpoints found in the specification."

        result = "Available endpoints:\n\n"
        for endpoint in endpoints:
            result += f"• {endpoint['method']} {endpoint['path']}"
            if endpoint["summary"]:
                result += f" - {endpoint['summary']}"
            if endpoint["operationId"]:
                result += f" (operationId: {endpoint['operationId']})"
            result += "\n"

        return result

    except Exception as e:
        return f"Error listing endpoints: {str(e)}"


@mcp.tool
def extract_endpoint_slice(path: str, method: str, output_format: str = "yaml") -> str:
    """Extract a minimal OpenAPI spec slice containing only the specified endpoint and its dependencies.

    Args:
        path: The API path (e.g., '/users/{id}')
        method: The HTTP method (e.g., 'GET', 'POST')
        output_format: Output format, either 'yaml' or 'json' (default: 'yaml')
    """
    global current_processor

    if current_processor is None:
        return "Error: No OpenAPI specification loaded. Use 'load_openapi_spec' first."

    if output_format.lower() not in ["yaml", "json"]:
        return "Error: output_format must be 'yaml' or 'json'"

    try:
        slice_spec = current_processor.extract_endpoint_slice(path, method)

        if output_format.lower() == "json":
            return json.dumps(slice_spec, indent=2)
        else:
            return yaml.dump(slice_spec, default_flow_style=False, sort_keys=False)

    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error extracting endpoint slice: {str(e)}"


@mcp.tool
def load_openapi_spec_from_url(url: str, timeout: int = 30) -> str:
    """Load an OpenAPI specification from a remote URL.
    
    Args:
        url: The URL to fetch the OpenAPI specification from
        timeout: Request timeout in seconds (default: 30)
    """
    global current_processor
    
    try:
        # Validate URL
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            return "Error: Invalid URL provided"
        
        if parsed_url.scheme not in ['http', 'https']:
            return "Error: Only HTTP and HTTPS URLs are supported"
        
        # Fetch the specification
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '').lower()
            
            # Parse based on content type or URL extension
            if 'application/json' in content_type or url.lower().endswith('.json'):
                spec_data = response.json()
            elif ('application/yaml' in content_type or 
                  'application/x-yaml' in content_type or 
                  'text/yaml' in content_type or
                  url.lower().endswith(('.yaml', '.yml'))):
                spec_data = yaml.safe_load(response.text)
            else:
                # Try to parse as YAML first, then JSON
                try:
                    spec_data = yaml.safe_load(response.text)
                except yaml.YAMLError:
                    try:
                        spec_data = response.json()
                    except json.JSONDecodeError:
                        return "Error: Unable to parse response as YAML or JSON"
        
        if not isinstance(spec_data, dict) or "paths" not in spec_data:
            return "Error: Invalid OpenAPI specification - must contain 'paths' section"
        
        current_processor = OpenAPISpecProcessor(spec_data)
        
        endpoints_count = len([path for path in spec_data.get("paths", {}).keys()])
        spec_title = spec_data.get("info", {}).get("title", "Unknown")
        spec_version = spec_data.get("info", {}).get("version", "Unknown")
        
        return f"Successfully loaded OpenAPI spec from {url}: {spec_title} v{spec_version} with {endpoints_count} paths"
        
    except httpx.TimeoutException:
        return f"Error: Request timeout after {timeout} seconds"
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} - {e.response.reason_phrase}"
    except httpx.RequestError as e:
        return f"Error: Network request failed - {str(e)}"
    except yaml.YAMLError as e:
        return f"Error parsing YAML content: {str(e)}"
    except json.JSONDecodeError as e:
        return f"Error parsing JSON content: {str(e)}"
    except Exception as e:
        return f"Error loading specification from URL: {str(e)}"


@mcp.tool
def get_server_status() -> str:
    """Get the current status of the OpenAPI Slice server."""
    global current_processor

    if current_processor is None:
        return "Status: No OpenAPI specification loaded"

    try:
        endpoints = current_processor.list_endpoints()
        return f"Status: OpenAPI specification loaded with {len(endpoints)} endpoints available"
    except Exception as e:
        return f"Status: Error - {str(e)}"


def main():
    """Entry point for the OpenAPI Slice MCP server."""
    parser = argparse.ArgumentParser(
        description="OpenAPI Slice MCP Server - Extract relevant portions of OpenAPI specs"
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "http"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="Transport mode: stdio (default) or http",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("MCP_HOST", "0.0.0.0"),
        help="Host to bind to for HTTP transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8000")),
        help="Port to bind to for HTTP transport (default: 8000)",
    )

    args = parser.parse_args()

    if args.transport == "http":
        # Run with HTTP transport
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        # Run with stdio transport (default)
        mcp.run()


def main_http():
    """Entry point for HTTP-only mode (for convenience)."""
    import sys
    sys.argv.extend(["--transport", "http"])
    main()


if __name__ == "__main__":
    main()
