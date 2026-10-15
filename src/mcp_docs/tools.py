"""MCP tool definitions for Docs."""

import json
import logging
from pathlib import Path
from typing import cast

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
    logger.warning("API error: HTTP %d — %s — body=%s", err.status_code, err.message, err.body)
    if isinstance(err, DocsAuthError):
        return "Authentication failed. Please check your credentials."
    if isinstance(err, DocsPermissionError):
        return "Access denied. You don't have permission to perform this action."
    if isinstance(err, DocsNotFoundError):
        return "Document not found."
    return f"Request failed (HTTP {err.status_code})."


_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MiB


def _file_path_to_markdown(file_path: str) -> str:
    """Read and validate a local markdown file, returning its content.

    Raises ``ValueError`` with a short generic message on any refusal. The
    file content is never included in error messages, and the resolved path's
    symlinks are followed.

    Hard guards: absolute path, regular ``.md`` file, size <= 5 MiB, strict
    UTF-8 read. Error messages are self-contained (they must not leak file
    contents).
    """
    p = Path(file_path)
    if not p.is_absolute():
        raise ValueError("Error: file_path must be an absolute path to a .md file.")
    try:
        resolved = p.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError("Error: file_path must point to an existing .md file.") from None
    if not resolved.is_file():
        raise ValueError("Error: file_path must point to a regular .md file.")
    if resolved.suffix.lower() != ".md":
        raise ValueError("Error: file_path must be an absolute path to a .md file.")
    if resolved.stat().st_size > _MAX_FILE_SIZE:
        raise ValueError("Error: file_path exceeds the 5 MiB size limit.")
    try:
        return resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ValueError("Error: file_path is not valid UTF-8 markdown.") from None
    except OSError:
        raise ValueError("Error: file_path could not be read.") from None


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
        return f"# {data.title}\n\n{data.content or ''}" if data.title else (data.content or "")

    return data.model_dump_json()


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
async def docs_create_document(
    ctx: Context,
    title: str,
    markdown_content: str | None = None,
    file_path: str | None = None,
) -> str:
    """Create a new document in Docs from markdown content.

    Provide markdown_content OR file_path (exactly one of the two). For a
    large document (content > ~50 Ko), pass file_path instead of the text so
    the MCP call stays small: the server reads the file locally.

    Args:
        title: Document title.
        markdown_content: Markdown content for the document body.
        file_path: Absolute path to a local .md file (<= 5 MiB) to read.
    """
    if not title or not title.strip():
        return "Error: title is required."
    if (markdown_content is None) == (file_path is None):
        return "Error: provide exactly one of markdown_content or file_path."
    if file_path is not None:
        try:
            markdown = _file_path_to_markdown(file_path)
        except ValueError as e:
            return str(e)
    else:
        # markdown_content is not None here: both being None was rejected above.
        markdown = cast(str, markdown_content)
    if not markdown:
        return "Error: markdown_content is empty."

    try:
        data = await _get_client(ctx).create_document(markdown, title=title)
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

    Only documents the authenticated user created can be deleted. Shared
    documents (where the user has only an editor/owner access role) are
    refused, even if the backend would allow the deletion.

    Args:
        document_id: UUID of the document to delete.
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."

    client = _get_client(ctx)
    try:
        doc = await client.get_document(document_id)
        me = await client.get_me()
    except DocsAPIError as e:
        return _error_response(e)

    creator_id: str | None
    if isinstance(doc.creator, str):
        creator_id = doc.creator
    elif isinstance(doc.creator, dict):
        raw = doc.creator.get("id")
        creator_id = raw if isinstance(raw, str) else None
    else:
        creator_id = None

    if creator_id is None or creator_id != me.id:
        return "Error: you can only delete documents you created."

    try:
        await client.delete_document(document_id)
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


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True),
)
async def docs_update_document_content(
    ctx: Context,
    document_id: str,
    content: str | None = None,
    file_path: str | None = None,
) -> str:
    """Replace the content of a document with markdown.

    Provide content OR file_path (exactly one of the two). An empty content
    ("") is valid and empties the document. For a large document (content >
    ~50 Ko), pass file_path instead of the text so the MCP call stays small:
    the server reads the file locally.

    Markdown formatting is preserved: headings (# ##), bold (**text**),
    italic (*text*), bullet and numbered lists, blockquotes, code blocks,
    links, etc. Conversion is performed server-side.

    Args:
        document_id: UUID of the document.
        content: New content as markdown (or None if file_path is used).
        file_path: Absolute path to a local .md file (<= 5 MiB) to read.
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."
    if (content is None) == (file_path is None):
        return "Error: provide exactly one of content or file_path."
    if file_path is not None:
        try:
            markdown = _file_path_to_markdown(file_path)
        except ValueError as e:
            return str(e)
    else:
        # content is not None here: both being None was rejected above.
        markdown = cast(str, content)

    try:
        updated_id = await _get_client(ctx).update_document_content(document_id, markdown)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"id": updated_id, "status": "updated"}, ensure_ascii=False)


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
