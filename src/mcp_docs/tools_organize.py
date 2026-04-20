"""MCP tool definitions for document organization (move, duplicate, trashbin)."""

import json
import logging

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from mcp_docs.app import AppContext, mcp
from mcp_docs.client import DocsClient
from mcp_docs.exceptions import DocsAPIError, DocsAuthError, DocsNotFoundError, DocsPermissionError

logger = logging.getLogger(__name__)

_MOVE_POSITIONS = ("first-child", "last-child", "left", "right", "first-sibling", "last-sibling")


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
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True),
)
async def docs_move_document(
    ctx: Context,
    document_id: str,
    target_document_id: str,
    position: str = "last-child",
) -> str:
    """Move a document in the hierarchy relative to a target document.

    Args:
        document_id: UUID of the document to move.
        target_document_id: UUID of the target document (parent or sibling).
        position: One of "first-child", "last-child" (default), "left", "right",
                  "first-sibling", "last-sibling".
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."
    if not target_document_id or not target_document_id.strip():
        return "Error: target_document_id is required."
    if position not in _MOVE_POSITIONS:
        return f"Error: position must be one of {', '.join(_MOVE_POSITIONS)}."

    try:
        data = await _get_client(ctx).move_document(document_id, target_document_id, position)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"status": "moved", "detail": data.get("message", "")}, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
async def docs_duplicate_document(
    ctx: Context,
    document_id: str,
    with_descendants: bool = False,
    with_accesses: bool = False,
) -> str:
    """Duplicate a document. The copy has title prefixed with "copy of".

    Args:
        document_id: UUID of the document to duplicate.
        with_descendants: If True, recursively duplicate all child documents.
        with_accesses: If True, copy access permissions and link configuration.
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."

    try:
        data = await _get_client(ctx).duplicate_document(
            document_id, with_descendants=with_descendants, with_accesses=with_accesses
        )
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"id": data.get("id"), "status": "duplicated"}, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def docs_list_trashbin(
    ctx: Context,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """List soft-deleted documents (within retention period).

    Only documents where the user is OWNER are returned.

    Args:
        page: Page number (starts at 1).
        page_size: Number of results per page (1-100).
    """
    if page < 1:
        return "Error: page must be >= 1."
    if not 1 <= page_size <= 100:
        return "Error: page_size must be between 1 and 100."

    try:
        data = await _get_client(ctx).list_trashbin(page=page, page_size=page_size)
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
                "updated_at": d.updated_at.isoformat() if d.updated_at else "",
            }
            for d in data.results
        ],
    }
    return json.dumps(summary, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def docs_restore_document(ctx: Context, document_id: str) -> str:
    """Restore a soft-deleted document from the trashbin.

    Args:
        document_id: UUID of the document to restore.
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."

    try:
        await _get_client(ctx).restore_document(document_id)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"status": "restored", "document_id": document_id}, ensure_ascii=False)
