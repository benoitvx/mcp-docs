"""MCP tool definitions for Docs AI features (transform + translate)."""

import json
import logging

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from mcp_docs.app import AppContext, mcp
from mcp_docs.client import DocsClient
from mcp_docs.exceptions import DocsAPIError, DocsAuthError, DocsNotFoundError, DocsPermissionError

logger = logging.getLogger(__name__)

_AI_ACTIONS = ("prompt", "correct", "rephrase", "summarize", "beautify", "emojify")


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
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
async def docs_ai_transform(
    ctx: Context,
    document_id: str,
    text: str,
    action: str,
) -> str:
    """Apply an AI transformation to text using Docs' AI service.

    Returns the transformed text — does NOT modify the document. To persist the
    result, call docs_update_document_content with the returned text.

    Args:
        document_id: UUID of the document (used for scoping/quota).
        text: Text to transform. Must be non-empty.
        action: One of "prompt", "correct", "rephrase", "summarize",
                "beautify", "emojify".
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."
    if not text or not text.strip():
        return "Error: text is required."
    if action not in _AI_ACTIONS:
        return f"Error: action must be one of {', '.join(_AI_ACTIONS)}."

    try:
        answer = await _get_client(ctx).ai_transform(document_id, text, action)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"transformed_text": answer}, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
async def docs_ai_translate(
    ctx: Context,
    document_id: str,
    text: str,
    language: str,
) -> str:
    """Translate text into the given language using Docs' AI service.

    Returns the translated text — does NOT modify the document.

    Args:
        document_id: UUID of the document (used for scoping/quota).
        text: Text to translate. Must be non-empty.
        language: ISO language code (e.g., "en", "fr", "es", "de", "it").
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."
    if not text or not text.strip():
        return "Error: text is required."
    if not language or not language.strip():
        return "Error: language is required."

    try:
        answer = await _get_client(ctx).ai_translate(document_id, text, language)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"translated_text": answer}, ensure_ascii=False)
