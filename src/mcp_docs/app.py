"""FastMCP application instance and lifespan management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig


@dataclass
class AppContext:
    """Application context holding shared resources."""

    config: DocsConfig
    client: DocsClient


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage DocsClient lifecycle."""
    config = DocsConfig()
    client = DocsClient(config)
    try:
        yield AppContext(config=config, client=client)
    finally:
        await client.close()


mcp = FastMCP("docs_mcp", lifespan=app_lifespan)
