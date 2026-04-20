"""MCP tool definitions for link sharing and favorites."""

import json
import logging

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from mcp_docs.app import AppContext, mcp
from mcp_docs.client import DocsClient
from mcp_docs.exceptions import DocsAPIError, DocsAuthError, DocsNotFoundError, DocsPermissionError

logger = logging.getLogger(__name__)

_LINK_REACHES = ("restricted", "authenticated", "public")
_LINK_ROLES = ("reader", "commenter", "editor")


def _get_client(ctx: Context) -> DocsClient:
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return app_ctx.client


def _error_response(err: DocsAPIError) -> str:
    logger.warning("API error: HTTP %d — %s", err.status_code, err.message)
    if isinstance(err, DocsAuthError):
        return "Authentication failed. Please check your credentials."
    if isinstance(err, DocsPermissionError):
        return "Access denied. You don't have permission to perform this action."
    if isinstance(err, DocsNotFoundError):
        return "Resource not found."
    return f"Request failed (HTTP {err.status_code})."


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True),
)
async def docs_update_link_configuration(
    ctx: Context,
    document_id: str,
    link_reach: str,
    link_role: str | None = None,
) -> str:
    """Configure how a document can be accessed via its share link.

    Args:
        document_id: UUID of the document.
        link_reach: "restricted" (only users with explicit access),
                    "authenticated" (any logged-in user), or "public" (anonymous).
        link_role: "reader", "commenter", or "editor". Must be None if
                   link_reach is "restricted".
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."
    if link_reach not in _LINK_REACHES:
        return f"Error: link_reach must be one of {', '.join(_LINK_REACHES)}."
    if link_reach == "restricted":
        if link_role is not None:
            return "Error: link_role must be null when link_reach is 'restricted'."
    else:
        if link_role not in _LINK_ROLES:
            return f"Error: link_role must be one of {', '.join(_LINK_ROLES)} when link_reach is not 'restricted'."

    try:
        data = await _get_client(ctx).update_link_configuration(document_id, link_reach, link_role)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps(
        {"link_reach": data.get("link_reach"), "link_role": data.get("link_role")},
        ensure_ascii=False,
    )


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def docs_list_favorites(
    ctx: Context,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """List the user's favorite documents.

    Args:
        page: Page number (starts at 1).
        page_size: Number of results per page (1-100).
    """
    if page < 1:
        return "Error: page must be >= 1."
    if not 1 <= page_size <= 100:
        return "Error: page_size must be between 1 and 100."

    try:
        data = await _get_client(ctx).list_favorites(page=page, page_size=page_size)
    except DocsAPIError as e:
        return _error_response(e)

    summary = {
        "count": data.count,
        "page": page,
        "page_size": page_size,
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "created_at": d.created_at.isoformat() if d.created_at else "",
                "updated_at": d.updated_at.isoformat() if d.updated_at else "",
            }
            for d in data.results
        ],
    }
    return json.dumps(summary, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def docs_add_favorite(ctx: Context, document_id: str) -> str:
    """Mark a document as favorite.

    Args:
        document_id: UUID of the document.
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."

    try:
        await _get_client(ctx).add_favorite(document_id)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"status": "favorited", "document_id": document_id}, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True),
)
async def docs_remove_favorite(ctx: Context, document_id: str) -> str:
    """Remove a document from favorites.

    Args:
        document_id: UUID of the document.
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."

    try:
        await _get_client(ctx).remove_favorite(document_id)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"status": "unfavorited", "document_id": document_id}, ensure_ascii=False)
