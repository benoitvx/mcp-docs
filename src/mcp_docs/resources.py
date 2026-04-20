"""MCP resource definitions for Docs."""

from mcp.server.fastmcp import Context

from mcp_docs.app import AppContext, mcp
from mcp_docs.client import DocsClient


def _get_client(ctx: Context) -> DocsClient:
    """Extract the DocsClient from the lifespan context."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return app_ctx.client


@mcp.resource("docs://user")
async def user_resource(ctx: Context) -> str:
    """Current authenticated user profile."""
    user = await _get_client(ctx).get_me()
    return user.model_dump_json()


@mcp.resource("docs://documents")
async def documents_resource(ctx: Context) -> str:
    """Recent documents list (last 10 updated)."""
    docs = await _get_client(ctx).list_documents(page_size=10)
    return docs.model_dump_json()
