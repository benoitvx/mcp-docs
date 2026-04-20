"""MCP tool definitions for Docs."""

import json
import logging

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from mcp_docs.app import AppContext, mcp
from mcp_docs.client import DocsClient
from mcp_docs.exceptions import DocsAPIError, DocsAuthError, DocsNotFoundError, DocsPermissionError


def _get_client(ctx: Context) -> DocsClient:
    """Extract the DocsClient from the lifespan context."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return app_ctx.client


logger = logging.getLogger(__name__)


def _error_response(err: DocsAPIError) -> str:
    """Return a safe error message without leaking internal details."""
    logger.warning("API error: HTTP %d — %s", err.status_code, err.message)
    if isinstance(err, DocsAuthError):
        return "Authentication failed. Please check your credentials."
    if isinstance(err, DocsPermissionError):
        return "Access denied. You don't have permission to perform this action."
    if isinstance(err, DocsNotFoundError):
        return "Document not found."
    return f"Request failed (HTTP {err.status_code})."


# --- P0 Tools ---


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def docs_list_documents(
    ctx: Context,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """List documents from Docs, ordered by last update.

    Returns a paginated list with document id, title, and timestamps.
    """
    if page < 1:
        return "Error: page must be >= 1."
    if not 1 <= page_size <= 100:
        return "Error: page_size must be between 1 and 100."

    try:
        data = await _get_client(ctx).list_documents(page=page, page_size=page_size)
    except DocsAPIError as e:
        return _error_response(e)

    summary = {
        "count": data.count,
        "page": page,
        "page_size": page_size,
        "documents": [
            {
                "id": doc.id,
                "title": doc.title,
                "created_at": doc.created_at.isoformat() if doc.created_at else "",
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else "",
            }
            for doc in data.results
        ],
    }
    return json.dumps(summary, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def docs_get_document_content(
    ctx: Context,
    document_id: str,
    content_format: str = "markdown",
) -> str:
    """Retrieve the content of a document by its ID.

    Args:
        document_id: UUID of the document.
        content_format: Output format — "markdown", "html", or "json".
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."
    if content_format not in ("markdown", "html", "json"):
        return "Error: content_format must be 'markdown', 'html', or 'json'."

    try:
        data = await _get_client(ctx).get_document_content(document_id, content_format)
    except DocsAPIError as e:
        return _error_response(e)

    if content_format == "markdown":
        return f"# {data.title}\n\n{data.content}" if data.title else data.content

    return data.model_dump_json()


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
async def docs_create_document(
    ctx: Context,
    title: str,
    markdown_content: str,
) -> str:
    """Create a new document in Docs from markdown content.

    Args:
        title: Document title.
        markdown_content: Markdown content for the document body.
    """
    if not title or not title.strip():
        return "Error: title is required."
    if not markdown_content or not markdown_content.strip():
        return "Error: markdown_content is required."

    try:
        data = await _get_client(ctx).create_document(markdown_content, title=title)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"id": data.id, "title": data.title or title}, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True),
)
async def docs_delete_document(
    ctx: Context,
    document_id: str,
) -> str:
    """Delete a document (soft delete — moved to trashbin).

    Args:
        document_id: UUID of the document to delete.
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."

    try:
        await _get_client(ctx).delete_document(document_id)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"status": "deleted", "document_id": document_id}, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True),
)
async def docs_update_document_title(
    ctx: Context,
    document_id: str,
    title: str,
) -> str:
    """Update the title of an existing document.

    Note: only the title can be updated. Updating document content is not
    supported yet — it requires Yjs-encoded payloads that the API does not
    accept in markdown form.

    Args:
        document_id: UUID of the document.
        title: New document title.
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."
    if not title or not title.strip():
        return "Error: title is required."

    try:
        data = await _get_client(ctx).update_document_title(document_id, title)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"id": data.id, "title": data.title}, ensure_ascii=False)


# --- P1 Tools ---


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def docs_search_documents(
    ctx: Context,
    query: str,
    page_size: int = 20,
) -> str:
    """Search documents by title or content.

    Args:
        query: Search query string.
        page_size: Number of results per page (1-100).
    """
    if not query or not query.strip():
        return "Error: query is required."
    if not 1 <= page_size <= 100:
        return "Error: page_size must be between 1 and 100."

    try:
        data = await _get_client(ctx).search_documents(query, page_size=page_size)
    except DocsAPIError as e:
        return _error_response(e)

    summary = {
        "count": data.count,
        "documents": [
            {
                "id": doc.id,
                "title": doc.title,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else "",
            }
            for doc in data.results
        ],
    }
    return json.dumps(summary, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def docs_get_me(ctx: Context) -> str:
    """Get information about the currently authenticated user."""
    try:
        data = await _get_client(ctx).get_me()
    except DocsAPIError as e:
        return _error_response(e)

    return data.model_dump_json()


# --- P2 Tools ---


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def docs_list_children(
    ctx: Context,
    document_id: str,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """List child documents (sub-pages) of a given parent document.

    Args:
        document_id: UUID of the parent document.
        page: Page number (starts at 1).
        page_size: Number of results per page (1-100).
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."
    if page < 1:
        return "Error: page must be >= 1."
    if not 1 <= page_size <= 100:
        return "Error: page_size must be between 1 and 100."

    try:
        data = await _get_client(ctx).list_children(document_id, page=page, page_size=page_size)
    except DocsAPIError as e:
        return _error_response(e)

    summary = {
        "count": data.count,
        "page": page,
        "page_size": page_size,
        "documents": [
            {
                "id": doc.id,
                "title": doc.title,
                "created_at": doc.created_at.isoformat() if doc.created_at else "",
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else "",
            }
            for doc in data.results
        ],
    }
    return json.dumps(summary, ensure_ascii=False)
