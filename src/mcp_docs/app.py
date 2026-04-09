"""FastMCP application instance and lifespan management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from mcp_docs.client import DocsClient, create_client_from_env


@dataclass
class AppContext:
    """Application context holding shared resources."""

    client: DocsClient


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage DocsClient lifecycle."""
    client = create_client_from_env()
    try:
        yield AppContext(client=client)
    finally:
        await client.close()


mcp = FastMCP("docs_mcp", lifespan=app_lifespan)
