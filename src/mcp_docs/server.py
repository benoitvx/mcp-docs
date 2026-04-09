"""MCP server entry point."""

import mcp_docs.tools  # noqa: F401 — registers tools via decorators
from mcp_docs.app import mcp


def main() -> None:
    """Run the MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
