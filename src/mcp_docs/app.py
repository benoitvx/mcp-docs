"""FastMCP application instance and lifespan management."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from mcp_docs.client import DocsClient
from mcp_docs.config import DocsConfig, load_config
from mcp_docs.paths import log_file_path


def _configure_logging() -> None:
    """Attach a file handler to the ``mcp_docs`` logger.

    Claude Code does not capture the MCP subprocess stderr in its session logs,
    so warnings emitted by ``mcp_docs.client`` and ``mcp_docs.tools`` would
    otherwise be lost. We write them to ``$XDG_STATE_HOME/mcp-docs/server.log``
    (default ``~/.local/state/mcp-docs/server.log``). Idempotent: a marker
    attribute prevents adding the handler twice if ``app.py`` is re-imported.
    """
    logger = logging.getLogger("mcp_docs")
    if getattr(logger, "_mcp_docs_file_handler", False):
        return
    path = log_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger._mcp_docs_file_handler = True  # type: ignore[attr-defined]


_configure_logging()


@dataclass
class AppContext:
    """Application context holding shared resources."""

    config: DocsConfig
    client: DocsClient


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage DocsClient lifecycle."""
    config = load_config()
    client = DocsClient(config)
    try:
        yield AppContext(config=config, client=client)
    finally:
        await client.close()


mcp = FastMCP("docs_mcp", lifespan=app_lifespan)
