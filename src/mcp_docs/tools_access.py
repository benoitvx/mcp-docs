"""MCP tool definitions for document access and invitation management."""

import json
import logging

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from mcp_docs.app import AppContext, mcp
from mcp_docs.client import DocsClient
from mcp_docs.exceptions import DocsAPIError, DocsAuthError, DocsNotFoundError, DocsPermissionError

logger = logging.getLogger(__name__)

_VALID_ACCESS_ROLES = ("reader", "commenter", "editor", "administrator", "owner")
_VALID_INVITATION_ROLES = ("reader", "commenter", "editor", "administrator")


def _get_client(ctx: Context) -> DocsClient:
    """Extract the DocsClient from the lifespan context."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return app_ctx.client


def _error_response(err: DocsAPIError) -> str:
    """Return a safe error message without leaking internal details."""
    logger.warning("API error: HTTP %d — %s", err.status_code, err.message)
    if isinstance(err, DocsAuthError):
        return "Authentication failed. Please check your credentials."
    if isinstance(err, DocsPermissionError):
        return "Access denied. You don't have permission to perform this action."
    if isinstance(err, DocsNotFoundError):
        return "Resource not found."
    return f"Request failed (HTTP {err.status_code})."


# --- Access tools ---


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def docs_list_accesses(
    ctx: Context,
    document_id: str,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """List all users who have access to a document and their roles.

    Args:
        document_id: UUID of the document.
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
        data = await _get_client(ctx).list_accesses(document_id, page=page, page_size=page_size)
    except DocsAPIError as e:
        return _error_response(e)

    summary = {
        "count": data.count,
        "page": page,
        "page_size": page_size,
        "accesses": [
            {"id": a.id, "user": a.user, "role": a.role, "team": a.team}
            for a in data.results
        ],
    }
    return json.dumps(summary, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
async def docs_grant_access(
    ctx: Context,
    document_id: str,
    user_id: str,
    role: str,
) -> str:
    """Grant a user access to a document.

    Args:
        document_id: UUID of the document.
        user_id: UUID of the user to grant access to.
        role: Access role — "reader", "commenter", "editor", "administrator", or "owner".
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."
    if not user_id or not user_id.strip():
        return "Error: user_id is required."
    if role not in _VALID_ACCESS_ROLES:
        return f"Error: role must be one of {', '.join(_VALID_ACCESS_ROLES)}."

    try:
        access = await _get_client(ctx).grant_access(document_id, user_id, role)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"id": access.id, "user": access.user, "role": access.role}, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True),
)
async def docs_update_access(
    ctx: Context,
    document_id: str,
    access_id: str,
    role: str,
) -> str:
    """Update the role of an existing access entry on a document.

    Args:
        document_id: UUID of the document.
        access_id: UUID of the access entry to update.
        role: New role — "reader", "commenter", "editor", "administrator", or "owner".
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."
    if not access_id or not access_id.strip():
        return "Error: access_id is required."
    if role not in _VALID_ACCESS_ROLES:
        return f"Error: role must be one of {', '.join(_VALID_ACCESS_ROLES)}."

    try:
        access = await _get_client(ctx).update_access(document_id, access_id, role)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"id": access.id, "user": access.user, "role": access.role}, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True),
)
async def docs_revoke_access(
    ctx: Context,
    document_id: str,
    access_id: str,
) -> str:
    """Revoke a user's access to a document.

    Args:
        document_id: UUID of the document.
        access_id: UUID of the access entry to revoke.
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."
    if not access_id or not access_id.strip():
        return "Error: access_id is required."

    try:
        await _get_client(ctx).revoke_access(document_id, access_id)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"status": "revoked", "access_id": access_id}, ensure_ascii=False)


# --- Invitation tools ---


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
)
async def docs_list_invitations(
    ctx: Context,
    document_id: str,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """List pending invitations for a document.

    Args:
        document_id: UUID of the document.
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
        data = await _get_client(ctx).list_invitations(document_id, page=page, page_size=page_size)
    except DocsAPIError as e:
        return _error_response(e)

    summary = {
        "count": data.count,
        "page": page,
        "page_size": page_size,
        "invitations": [
            {"id": inv.id, "email": inv.email, "role": inv.role}
            for inv in data.results
        ],
    }
    return json.dumps(summary, ensure_ascii=False)


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
async def docs_create_invitation(
    ctx: Context,
    document_id: str,
    email: str,
    role: str,
) -> str:
    """Send an email invitation granting access to a document.

    Args:
        document_id: UUID of the document.
        email: Email address of the person to invite.
        role: Access role — "reader", "commenter", "editor", or "administrator".
    """
    if not document_id or not document_id.strip():
        return "Error: document_id is required."
    if not email or not email.strip():
        return "Error: email is required."
    if role not in _VALID_INVITATION_ROLES:
        return f"Error: role must be one of {', '.join(_VALID_INVITATION_ROLES)}."

    try:
        inv = await _get_client(ctx).create_invitation(document_id, email, role)
    except DocsAPIError as e:
        return _error_response(e)

    return json.dumps({"id": inv.id, "email": inv.email, "role": inv.role}, ensure_ascii=False)
