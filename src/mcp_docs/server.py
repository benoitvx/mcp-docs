"""MCP server entry point."""

import argparse
import asyncio
import sys

import mcp_docs.resources  # noqa: F401 — registers resources via decorators
import mcp_docs.tools  # noqa: F401 — registers tools via decorators
import mcp_docs.tools_access  # noqa: F401 — registers access/permission tools
from mcp_docs.app import mcp


async def _config_check() -> None:
    """Validate configuration and test API connectivity."""
    from mcp_docs.client import DocsClient
    from mcp_docs.config import DocsConfig

    try:
        config = DocsConfig()
    except Exception as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Config OK: base_url={config.base_url}, auth_mode={config.auth_mode}")

    try:
        client = DocsClient(config)
        user = await client.get_me()
        print(f"Auth OK: connected as {user.name} ({user.email})")
        await client.close()
    except Exception as e:
        print(f"Auth error: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Run the MCP server or validate configuration."""
    parser = argparse.ArgumentParser(prog="mcp-docs", description="MCP server for Docs (La Suite numerique)")
    parser.add_argument(
        "--config-check", action="store_true", help="Validate config and test API connection, then exit"
    )
    args = parser.parse_args()

    if args.config_check:
        asyncio.run(_config_check())
    else:
        mcp.run()


if __name__ == "__main__":
    main()
